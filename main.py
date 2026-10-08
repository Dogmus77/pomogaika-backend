"""
Pomogaika Wine API
Production-ready backend with real store data
"""

import logging

# Without this the root logger has no handler, Python's last-resort handler prints
# WARNING and above only, and every logger.info() in the backend never reached
# Render's logs.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import asyncio
from concurrent.futures import ThreadPoolExecutor

from sommelier import SommelierEngine
from wine_parser import WineAggregator, WineType, Wine as ParserWine
from content_routes import admin_router, public_router
from ai_routes import router as ai_router
from auth import require_admin

app = FastAPI(
    title="Pomogaika Wine API",
    description="Wine pairing API with real data from Spanish supermarkets",
    version="3.0.0"
)

# Content API routers (articles, events, experts, admin)
app.include_router(admin_router)
app.include_router(public_router)
app.include_router(ai_router)          # /ask, /pairings (2.3.0)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialization
sommelier = SommelierEngine()
executor = ThreadPoolExecutor(max_workers=8)

# Wine cache (updates every 30 minutes)
wine_cache = {
    "wines": [],
    "last_update": None,
    "is_loading": False
}

# Event: set when cache has data (requests wait for this)
cache_ready = asyncio.Event()


# === Startup: pre-warm cache ===

@app.on_event("startup")
async def startup_warmup():
    """Pre-warm wine cache on server start"""
    print("🚀 Starting cache warmup...")
    asyncio.create_task(_warmup_cache())


async def _warmup_cache():
    """Background task to fill cache"""
    try:
        await get_wines("46001")
        print(f"🔥 Cache warmed: {len(wine_cache['wines'])} wines ready")
    except Exception as e:
        print(f"⚠️ Cache warmup failed: {e}")
    finally:
        # Always signal ready (even if failed — don't block requests forever)
        cache_ready.set()


# === App Version Check ===

_LATEST_VERSIONS = {
    "ios": "2.2.1",
    "android": "2.3.0"
}

@app.get("/version")
async def get_latest_version():
    """Returns latest app versions for update checks"""
    return _LATEST_VERSIONS


# === Models ===

class WineResponse(BaseModel):
    id: str
    name: str
    brand: str
    price: float
    price_per_liter: float
    store: str
    url: str
    image_url: Optional[str] = None
    ean: Optional[str] = None
    region: Optional[str] = None
    wine_type: Optional[str] = None
    discount_price: Optional[float] = None
    discount_percent: Optional[int] = None
    match_score: Optional[int] = None
    expert_note: Optional[str] = None


class RecommendationResponse(BaseModel):
    total: int
    expert_summary: str
    recommended_style: str
    recommended_grapes: list[str]
    recommended_regions: list[str]
    wines: list[WineResponse]
    data_source: str  # "live" or "cache"


class ExpertRecommendation(BaseModel):
    style: str
    grape_varieties: list[str]
    regions: list[str]
    wine_type: str
    description: str
    priority: int


# === Wine Fetching ===

def fetch_wines_sync(postal_code: str = "46001") -> list[ParserWine]:
    """Sync fetch wines from stores — ALL types + premium queries in parallel"""
    import time
    start = time.time()
    
    aggregator = WineAggregator(postal_code=postal_code)
    
    # 1. Standard search by wine type
    all_wines = aggregator.search_all_types(
        wine_types=[WineType.TINTO, WineType.BLANCO, WineType.ROSADO, WineType.CAVA],
        limit_per_store=80
    )
    
    # 2. Premium-targeted search (reserva, gran reserva, premium regions)
    premium_wines = aggregator.search_premium(limit_per_query=40)
    
    # 3. Deduplicate by ID
    seen_ids = {w.id for w in all_wines}
    for pw in premium_wines:
        if pw.id not in seen_ids:
            seen_ids.add(pw.id)
            all_wines.append(pw)
    
    # 4. Exclude non-wine products (jamon, bread, rum, etc.)
    _EXCLUDE_KEYWORDS = [
        "jamon", "jam\u00F3n", "bocadillo", "bocata",
        "ron ", "ron a\u00F1ejo", "whisky", "whiskey", "ginebra", "vodka",
        "cerveza", "zumo", "refresco", "agua mineral",
        "aceite", "vinagre", "queso", "chorizo", "salchich",
        "pat\u00E9", "conserva", "lata de", "atun", "at\u00FAn",
        "cafe", "caf\u00E9", "capsula", "c\u00E1psula", "nespresso",
        "pimienta", "pimiento", "especias",
        # fruit: Masymas returned "Granadas" (pomegranates, 0.97 EUR) as a red wine,
        # and the price sort put it first under "reds under 10 EUR". Plural only:
        # D.O. Granada wines say "Granada".
        "granadas",
    ]
    all_wines = [
        w for w in all_wines
        if not any(kw in w.name.lower() for kw in _EXCLUDE_KEYWORDS)
    ]
    
    # 5. One entry per product id: the per-type queries overlap (the same bottle came
    # back twice under "reds"), and the apps key their lists by id.
    unique, seen = [], set()
    for w in all_wines:
        if w.id not in seen:
            seen.add(w.id)
            unique.append(w)
    all_wines = unique

    elapsed = time.time() - start
    print(f"\u23F1\uFE0F fetch_wines_sync: {len(all_wines)} wines ({len(premium_wines)} premium) in {elapsed:.1f}s")
    return all_wines


CACHE_TTL_SECONDS = 1800        # refresh the catalogue every 30 minutes
STORE_CARRYOVER_SECONDS = 6 * 3600  # keep a silent store's last wines for up to 6 hours
_refresh_tasks: set = set()


def _keep_previous_for_silent_stores(fresh: list, previous: list, store_updated: dict, now: float) -> list:
    """A store that returned nothing this time (blocked, down, timed out) keeps its
    previous wines for a while instead of vanishing from every result for 30 minutes."""
    answered = {w.store for w in fresh}
    for store in answered:
        store_updated[store] = now
    kept = [w for w in previous
            if w.store not in answered and now - store_updated.get(w.store, 0) < STORE_CARRYOVER_SECONDS]
    if kept:
        print(f"\u267B\uFE0F Keeping {len(kept)} cached wines for silent stores: {sorted({w.store for w in kept})}")
    return fresh + kept


async def _refresh_wines(postal_code: str) -> None:
    """Fetch the catalogue and swap it into the cache. Never raises.
    The caller must set wine_cache["is_loading"] = True before scheduling this."""
    import time
    try:
        loop = asyncio.get_event_loop()
        parser_wines = await loop.run_in_executor(executor, fetch_wines_sync, postal_code)
        fresh = [WineResponse(
            id=pw.id, name=pw.name, brand=pw.brand, price=pw.price,
            price_per_liter=pw.price_per_liter, store=pw.store, url=pw.url,
            image_url=pw.image_url, ean=pw.ean, region=pw.region, wine_type=pw.wine_type,
            discount_price=pw.discount_price, discount_percent=pw.discount_percent,
        ) for pw in parser_wines]
        now = time.time()
        wines = _keep_previous_for_silent_stores(
            fresh, wine_cache["wines"], wine_cache.setdefault("store_updated", {}), now)
        if wines:
            wine_cache["wines"] = wines
            wine_cache["last_update"] = now
            print(f"\u2705 Cache updated: {len(wines)} wines ({len(fresh)} fresh)")
        else:
            print("\u274C Refresh returned no wines, keeping the previous cache")
    except Exception as e:
        print(f"\u274C Error fetching wines: {e}")
    finally:
        wine_cache["is_loading"] = False


async def get_wines(postal_code: str = "46001") -> list[WineResponse]:
    """Wines from the cache. A stale cache is served immediately and refreshed in the
    background; only an empty cache (cold start) makes the caller wait for a fetch."""
    import time

    if wine_cache["wines"]:
        age = time.time() - (wine_cache["last_update"] or 0)
        if age >= CACHE_TTL_SECONDS and not wine_cache["is_loading"]:
            print(f"\u267B\uFE0F Cache is {age:.0f}s old, refreshing in the background")
            wine_cache["is_loading"] = True   # set before scheduling: no second refresh can start
            task = asyncio.create_task(_refresh_wines(postal_code))
            _refresh_tasks.add(task)
            task.add_done_callback(_refresh_tasks.discard)
        return wine_cache["wines"]

    # Nothing cached yet
    if wine_cache["is_loading"]:
        print("\u23F3 Already loading, returning current cache")
        return wine_cache["wines"]
    wine_cache["is_loading"] = True
    await _refresh_wines(postal_code)
    return wine_cache["wines"]


# === Endpoints ===

@app.get("/")
async def root():
    return {
        "name": "Pomogaika Wine API",
        "version": "2.0.0",
        "stores": ["Consum", "Mercadona", "Masymas", "DIA", "Condis"],
        "endpoints": ["/recommend", "/search", "/expert", "/health"]
    }


@app.get("/health")
async def health():
    import time
    cache_age = int(time.time() - wine_cache["last_update"]) if wine_cache["last_update"] else -1
    
    # Count wines per store
    store_counts = {}
    for w in wine_cache["wines"]:
        store_counts[w.store] = store_counts.get(w.store, 0) + 1
    
    return {
        "status": "ok",
        "cache_size": len(wine_cache["wines"]),
        "cache_age_seconds": cache_age,
        "is_loading": wine_cache["is_loading"],
        "stores": store_counts
    }


@app.get("/expert", response_model=list[ExpertRecommendation])
async def get_expert_recommendations(
    dish: str = Query(..., description="fish, meat, poultry, vegetables, pasta, cheese"),
    cooking_method: Optional[str] = Query(None, description="raw, steamed, grilled, fried, roasted, stewed, creamy, tomato, spicy"),
    meal_time: Optional[str] = Query(None, description="lunch, dinner, aperitivo"),
    cuisine: Optional[str] = Query(None, description="spanish, italian, asian, other, unknown")
):
    """Get sommelier expert recommendations"""
    recs = sommelier.get_recommendations(dish, cooking_method, meal_time, cuisine)
    
    return [
        ExpertRecommendation(
            style=rec.style.value,
            grape_varieties=rec.grape_varieties,
            regions=rec.regions,
            wine_type=rec.wine_type,
            description=rec.description,
            priority=rec.priority
        )
        for rec in recs
    ]


@app.get("/recommend", response_model=RecommendationResponse)
async def recommend_wines(
    dish: str = Query(..., description="Dish type: fish, meat, poultry, vegetables, pasta, cheese"),
    cooking_method: Optional[str] = Query(None, description="Cooking method: raw, steamed, grilled, fried, roasted, stewed, creamy, tomato, spicy"),
    meal_time: Optional[str] = Query(None, description="Meal time: lunch, dinner, aperitivo"),
    cuisine: Optional[str] = Query(None, description="Cuisine type: spanish, italian, asian, other, unknown"),
    min_price: float = Query(0, description="Minimum price"),
    max_price: float = Query(30.0, description="Maximum price"),
    postal_code: str = Query("46001", description="Postal code"),
    limit: int = Query(80, description="Number of results"),
    lang: str = Query("ru", description="Language: ru, uk, be, en, es")
):
    """Get wine recommendations with real store data"""
    
    # Wait for cache to be ready (max 90 seconds on cold start)
    try:
        await asyncio.wait_for(cache_ready.wait(), timeout=90)
    except asyncio.TimeoutError:
        print("⚠️ Cache warmup timeout, proceeding with what we have")
    
    # 1. Get expert recommendations
    # lang goes to the engine: its translation table covers every description it can
    # produce (the old duplicate table in this file missed 8, which came back in English).
    expert_recs = sommelier.get_recommendations(dish, cooking_method, meal_time, cuisine, lang=lang)
    
    if not expert_recs:
        raise HTTPException(status_code=400, detail="Could not find recommendations")
    
    primary_rec = expert_recs[0]
    
    # 2. Get wines from stores
    all_wines = await get_wines(postal_code)
    data_source = "live" if wine_cache["last_update"] else "cache"
    
    # 3. Filter by wine type
    filtered = [w for w in all_wines if w.wine_type == primary_rec.wine_type]
    
    # 4. Filter by price
    filtered = [w for w in filtered if min_price <= (w.discount_price or w.price) <= max_price]
    
    # 5. Score based on recommendations match
    def score_wine(wine: WineResponse) -> int:
        score = 50
        
        # +20 for region match
        if wine.region:
            for region in primary_rec.regions:
                if region.lower() in wine.region.lower():
                    score += 20
                    break
        
        # +15 for grape match in name
        for grape in primary_rec.grape_varieties:
            if grape.lower() in wine.name.lower():
                score += 15
                break
        
        # +10 for discount
        if wine.discount_price:
            score += 10
        
        # +5 for having region (quality)
        if wine.region:
            score += 5
        
        return min(score, 100)
    
    # 6. Add scores — on copies: these are the cached objects that /search also returns,
    # and writing into them leaked this dish's match scores and notes into everyone's search.
    scored = [
        w.model_copy(update={
            "match_score": score_wine(w),
            "expert_note": get_expert_note(w, primary_rec, lang),
        })
        for w in filtered
    ]

    # 7. Store-diverse selection: ensure each store is represented
    scored_wines = _diverse_selection(scored, limit)
    
    return RecommendationResponse(
        total=len(filtered),
        expert_summary=primary_rec.description,
        recommended_style=primary_rec.style.value,
        recommended_grapes=primary_rec.grape_varieties,
        recommended_regions=primary_rec.regions,
        wines=scored_wines,
        data_source=data_source
    )


def _diverse_selection(wines: list, limit: int, min_per_store: int = 3) -> list:
    """Select wines ensuring each store is represented fairly"""
    if len(wines) <= limit:
        wines.sort(key=lambda w: w.match_score or 0, reverse=True)
        return wines
    
    # Group by store
    by_store: dict[str, list] = {}
    for w in wines:
        by_store.setdefault(w.store, []).append(w)
    
    # Sort each store's wines by score
    for store in by_store:
        by_store[store].sort(key=lambda w: w.match_score or 0, reverse=True)
    
    selected = []
    selected_ids = set()
    
    # Phase 1: take top min_per_store from each store
    for store, store_wines in by_store.items():
        for w in store_wines[:min_per_store]:
            if w.id not in selected_ids:
                selected.append(w)
                selected_ids.add(w.id)
    
    # Phase 2: fill remaining slots by global score
    remaining = [w for w in wines if w.id not in selected_ids]
    remaining.sort(key=lambda w: w.match_score or 0, reverse=True)
    
    for w in remaining:
        if len(selected) >= limit:
            break
        selected.append(w)
    
    # Final sort by score
    selected.sort(key=lambda w: w.match_score or 0, reverse=True)
    return selected


# === Localization ===


REGION_NOTES = {
    "Rioja": {
        "ru": "Классическая Риоха — баланс фруктов, дуба и элегантности",
        "uk": "Класична Ріоха — баланс фруктів, дуба та елегантності",
        "be": "Класічная Рыёха — баланс фруктаў, дуба і элегантнасці",
        "en": "Classic Rioja — balance of fruit, oak and elegance",
        "es": "Rioja clásica — equilibrio de fruta, roble y elegancia",
    },
    "Ribera": {
        "ru": "Мощная Рибера дель Дуэро — интенсивность и глубина",
        "uk": "Потужна Рібера дель Дуеро — інтенсивність і глибина",
        "be": "Магутная Рыбера дэль Дуэра — інтэнсіўнасць і глыбіня",
        "en": "Powerful Ribera del Duero — intensity and depth",
        "es": "Ribera del Duero — intensidad y profundidad",
    },
    "Rías Baixas": {
        "ru": "Альбариньо из Галисии — минеральность и свежесть океана",
        "uk": "Альбаріньо з Галісії — мінеральність і свіжість океану",
        "be": "Альбарыньё з Галісіі — мінеральнасць і свежасць акіяна",
        "en": "Albariño from Galicia — ocean minerality and freshness",
        "es": "Albariño de Galicia — mineralidad y frescura del océano",
    },
    "Rueda": {
        "ru": "Свежий Вердехо — травы, цитрусы, хрустящая кислотность",
        "uk": "Свіжий Вердехо — трави, цитруси, хрустка кислотність",
        "be": "Свежы Вердэхо — травы, цытрусы, храсткая кіслотнасць",
        "en": "Fresh Verdejo — herbs, citrus, crisp acidity",
        "es": "Verdejo fresco — hierbas, cítricos, acidez crujiente",
    },
    "Priorat": {
        "ru": "Приорат — мощь и концентрация",
        "uk": "Пріорат — потужність і концентрація",
        "be": "Прыярат — магутнасць і канцэнтрацыя",
        "en": "Priorat — power and concentration",
        "es": "Priorat — potencia y concentración",
    },
    "Jumilla": {
        "ru": "Насыщенный Монастрель — чернослив, шоколад, специи",
        "uk": "Насичений Монастрель — чорнослив, шоколад, спеції",
        "be": "Насычаны Манастрэль — чарнаслівы, шакалад, спецыі",
        "en": "Rich Monastrell — prune, chocolate, spice",
        "es": "Monastrell intenso — ciruela, chocolate, especias",
    },
    "Bierzo": {
        "ru": "Элегантная Менсия — испанский ответ Пино Нуар",
        "uk": "Елегантна Менсія — іспанська відповідь Піно Нуар",
        "be": "Элегантная Менсія — іспанскі адказ Піно Нуар",
        "en": "Elegant Mencía — Spain's answer to Pinot Noir",
        "es": "Mencía elegante — la respuesta española al Pinot Noir",
    },
    "Navarra": {
        "ru": "Наварра — столица розовых вин",
        "uk": "Наварра — столиця рожевих вин",
        "be": "Навара — сталіца ружовых він",
        "en": "Navarra — capital of rosé wines",
        "es": "Navarra — capital del vino rosado",
    },
    "Penedès": {
        "ru": "Пенедес — родина испанской Кавы",
        "uk": "Пенедес — батьківщина іспанської Кави",
        "be": "Пенедэс — радзіма іспанскай Кавы",
        "en": "Penedès — home of Spanish Cava",
        "es": "Penedès — cuna del Cava español",
    },
}

WINE_TYPE_NOTES = {
    "cava": {
        "ru": "Испанское игристое методом шампанского — праздник в бокале",
        "uk": "Іспанське ігристе методом шампанського — свято в келиху",
        "be": "Іспанскае ігрыстае метадам шампанскага — свята ў келіху",
        "en": "Spanish sparkling, Champagne method — celebration in a glass",
        "es": "Espumoso español método champenoise — celebración en copa",
    },
}

DEFAULT_NOTE = {
    "ru": "Отличный выбор для вашего блюда",
    "uk": "Чудовий вибір для вашої страви",
    "be": "Выдатны выбар для вашай стравы",
    "en": "Excellent choice for your dish",
    "es": "Excelente elección para tu plato",
}


def get_expert_note(wine: WineResponse, rec, lang: str = "ru") -> str:
    """Generate localized expert tasting note"""
    if wine.region:
        for region_key, translations in REGION_NOTES.items():
            if region_key in wine.region:
                return translations.get(lang, translations.get("en", ""))
    
    if wine.wine_type and wine.wine_type in WINE_TYPE_NOTES:
        return WINE_TYPE_NOTES[wine.wine_type].get(lang, WINE_TYPE_NOTES[wine.wine_type].get("en", ""))
    
    return DEFAULT_NOTE.get(lang, DEFAULT_NOTE.get("en", ""))


@app.get("/search")
async def search_wines(
    query: Optional[str] = Query(None, description="Search query"),
    wine_type: Optional[str] = Query(None, description="tinto, blanco, rosado, cava"),
    region: Optional[str] = Query(None, description="DO Region"),
    min_price: float = Query(0, description="Minimum price"),
    max_price: float = Query(100.0, description="Maximum price"),
    store: Optional[str] = Query(None, description="consum, mercadona, masymas, dia, condis"),
    postal_code: str = Query("46001", description="Postal code"),
    limit: int = Query(80, description="Number of results")
):
    """Search wines with filters"""
    
    # Wait for cache to be ready
    try:
        await asyncio.wait_for(cache_ready.wait(), timeout=90)
    except asyncio.TimeoutError:
        pass
    
    all_wines = await get_wines(postal_code)
    filtered = all_wines
    
    # Filters
    if query:
        query_lower = query.lower()
        filtered = [w for w in filtered if query_lower in w.name.lower() or query_lower in (w.brand or "").lower()]
    
    if wine_type:
        filtered = [w for w in filtered if w.wine_type == wine_type]
    
    if region:
        region_lower = region.lower()
        filtered = [w for w in filtered if w.region and region_lower in w.region.lower()]
    
    if store:
        filtered = [w for w in filtered if w.store == store]
    
    # Price
    filtered = [w for w in filtered if min_price <= (w.discount_price or w.price) <= max_price]
    
    # Sort by price
    filtered.sort(key=lambda w: w.discount_price or w.price)
    
    return {
        "total": len(filtered),
        "wines": filtered[:limit]
    }


@app.get("/stores")
async def get_stores():
    """List of supported stores"""
    return {
        "stores": [
            {
                "id": "consum",
                "name": "Consum",
                "has_ean": True,
                "coverage": "Valencia, Cataluña, Murcia, Castilla-La Mancha"
            },
            {
                "id": "mercadona",
                "name": "Mercadona",
                "has_ean": False,
                "coverage": "Toda España"
            },
            {
                "id": "masymas",
                "name": "Masymas",
                "has_ean": True,
                "coverage": "Valencia, Alicante, Murcia"
            },
            {
                "id": "dia",
                "name": "DIA",
                "has_ean": False,
                "coverage": "Toda España"
            },
            {
                "id": "condis",
                "name": "Condis",
                "has_ean": False,
                "coverage": "Cataluña (Barcelona)"
            }
        ]
    }


@app.get("/debug/store/{store_name}")
async def debug_store(store_name: str, user=Depends(require_admin)):
    """Debug endpoint: test individual store parser"""
    import traceback
    
    result = {
        "store": store_name,
        "status": "unknown",
        "wines_count": 0,
        "error": None,
        "sample_wines": [],
        "raw_response_info": None,
    }
    
    try:
        if store_name == "masymas":
            from wine_parser import MasymasParser, WineType
            parser = MasymasParser()
            
            # Test raw HTTP request first
            import requests as req
            raw_resp = req.get(
                "https://tienda.masymas.com/api/rest/V1.0/catalog/searcher/products",
                params={"q": "vino tinto", "limit": "3", "showProducts": "true", "showRecommendations": "false", "showRecipes": "false"},
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept": "application/json",
                    "Referer": "https://tienda.masymas.com/es",
                },
                timeout=15
            )
            result["raw_response_info"] = {
                "status_code": raw_resp.status_code,
                "content_type": raw_resp.headers.get("content-type"),
                "body_length": len(raw_resp.text),
                "body_preview": raw_resp.text[:500],
            }
            
            wines = parser.search_wines(WineType.TINTO, limit=5)
            result["wines_count"] = len(wines)
            result["sample_wines"] = [
                {"name": w.name, "price": w.price, "brand": w.brand, "region": w.region}
                for w in wines[:3]
            ]
            result["status"] = "ok" if wines else "empty"
            
        elif store_name == "dia":
            from wine_parser import DIAParser, WineType
            parser = DIAParser()
            wines = parser.search_wines(WineType.TINTO, limit=5)
            result["wines_count"] = len(wines)
            result["sample_wines"] = [
                {"name": w.name, "price": w.price, "brand": w.brand, "region": w.region}
                for w in wines[:3]
            ]
            result["status"] = "ok" if wines else "empty"
            
        elif store_name == "consum":
            from wine_parser import ConsumParser, WineType
            parser = ConsumParser()
            wines = parser.search_wines(WineType.TINTO, limit=5)
            result["wines_count"] = len(wines)
            result["status"] = "ok" if wines else "empty"
            
        elif store_name == "mercadona":
            from wine_parser import MercadonaParser, WineType
            parser = MercadonaParser()
            wines = parser.search_wines(WineType.TINTO, limit=5)
            result["wines_count"] = len(wines)
            result["status"] = "ok" if wines else "empty"

        elif store_name == "condis":
            from wine_parser import CondisParser, WineType
            parser = CondisParser()
            wines = parser.search_wines(WineType.TINTO, limit=5)
            result["wines_count"] = len(wines)
            result["sample_wines"] = [
                {"name": w.name, "price": w.price, "brand": w.brand, "region": w.region}
                for w in wines[:3]
            ]
            result["status"] = "ok" if wines else "empty"

        else:
            result["error"] = f"Unknown store: {store_name}"
            
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"{type(e).__name__}: {str(e)}"
        result["traceback"] = traceback.format_exc()
    
    return result


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
