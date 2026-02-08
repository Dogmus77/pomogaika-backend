"""
Pomogaika Wine API
Production-ready backend with real store data and multi-language support
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import asyncio
from concurrent.futures import ThreadPoolExecutor

from sommelier import SommelierEngine, translate
from wine_parser import WineAggregator, WineType, Wine as ParserWine

app = FastAPI(
    title="Pomogaika Wine API",
    description="Wine pairing API with real data from Consum & Mercadona",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialization
sommelier = SommelierEngine()
executor = ThreadPoolExecutor(max_workers=4)

# Wine cache (updates every 30 minutes)
wine_cache = {
    "wines": [],
    "last_update": None
}


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
    """Sync fetch wines from stores"""
    aggregator = WineAggregator(postal_code=postal_code)
    all_wines = []
    
    for wine_type in [WineType.TINTO, WineType.BLANCO, WineType.ROSADO, WineType.CAVA]:
        try:
            wines = aggregator.search_all(wine_type, limit_per_store=30)
            all_wines.extend(wines)
        except Exception as e:
            print(f"Error fetching {wine_type.value}: {e}")
    
    return all_wines


async def get_wines(postal_code: str = "46001") -> list[WineResponse]:
    """Async fetch wines with caching"""
    import time
    
    # Check cache (30 min)
    if wine_cache["wines"] and wine_cache["last_update"]:
        if time.time() - wine_cache["last_update"] < 1800:  # 30 min
            return wine_cache["wines"]
    
    # Get fresh data
    loop = asyncio.get_event_loop()
    try:
        parser_wines = await loop.run_in_executor(executor, fetch_wines_sync, postal_code)
        
        wines = []
        for pw in parser_wines:
            wines.append(WineResponse(
                id=pw.id,
                name=pw.name,
                brand=pw.brand,
                price=pw.price,
                price_per_liter=pw.price_per_liter,
                store=pw.store,
                url=pw.url,
                image_url=pw.image_url,
                ean=pw.ean,
                region=pw.region,
                wine_type=pw.wine_type,
                discount_price=pw.discount_price,
                discount_percent=pw.discount_percent
            ))
        
        # Update cache
        wine_cache["wines"] = wines
        wine_cache["last_update"] = time.time()
        
        return wines
        
    except Exception as e:
        print(f"Error fetching wines: {e}")
        # Return cache if available
        if wine_cache["wines"]:
            return wine_cache["wines"]
        return []


# === Endpoints ===

@app.get("/")
async def root():
    return {
        "name": "Pomogaika Wine API",
        "version": "2.1.0",
        "stores": ["Consum", "Mercadona"],
        "endpoints": ["/recommend", "/search", "/expert", "/health"]
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "cache_size": len(wine_cache["wines"]),
        "cache_age_seconds": int(
            (import_time() - wine_cache["last_update"]) if wine_cache["last_update"] else 0
        )
    }


def import_time():
    import time
    return time.time()


@app.get("/expert", response_model=list[ExpertRecommendation])
async def get_expert_recommendations(
    dish: str = Query(..., description="fish, meat, poultry, vegetables, pasta, cheese"),
    cooking_method: Optional[str] = Query(None, description="raw, steamed, grilled, fried, roasted, stewed, creamy, tomato, spicy"),
    meal_time: Optional[str] = Query(None, description="lunch, dinner, aperitivo, digestivo"),
    cuisine: Optional[str] = Query(None, description="spanish, italian, asian, other"),
    lang: str = Query("en", description="Language: ru, uk, be, en, es")
):
    """Get sommelier expert recommendations (localized)"""
    recs = sommelier.get_recommendations(dish, cooking_method, meal_time, cuisine, lang=lang)
    
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
    cooking_method: Optional[str] = Query(None, description="Cooking method"),
    meal_time: Optional[str] = Query(None, description="Meal time: lunch, dinner, aperitivo, digestivo"),
    cuisine: Optional[str] = Query(None, description="Cuisine type"),
    min_price: float = Query(0, description="Minimum price"),
    max_price: float = Query(30.0, description="Maximum price"),
    postal_code: str = Query("46001", description="Postal code"),
    limit: int = Query(15, description="Number of results"),
    lang: str = Query("en", description="Language: ru, uk, be, en, es")
):
    """Get wine recommendations with real store data (localized)"""
    
    # 1. Get expert recommendations (already translated via lang)
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
        
        if wine.region:
            for region in primary_rec.regions:
                if region.lower() in wine.region.lower():
                    score += 20
                    break
        
        for grape in primary_rec.grape_varieties:
            if grape.lower() in wine.name.lower():
                score += 15
                break
        
        if wine.discount_price:
            score += 10
        
        if wine.region:
            score += 5
        
        return min(score, 100)
    
    # 6. Add scores and sort
    scored_wines = []
    for wine in filtered:
        wine.match_score = score_wine(wine)
        wine.expert_note = get_expert_note(wine, primary_rec, lang)
        scored_wines.append(wine)
    
    scored_wines.sort(key=lambda w: w.match_score or 0, reverse=True)
    
    return RecommendationResponse(
        total=len(scored_wines),
        expert_summary=primary_rec.description,  # already translated by sommelier
        recommended_style=primary_rec.style.value,
        recommended_grapes=primary_rec.grape_varieties,
        recommended_regions=primary_rec.regions,
        wines=scored_wines[:limit],
        data_source=data_source
    )


def get_expert_note(wine: WineResponse, rec, lang: str = "en") -> str:
    """Generate expert tasting note (localized)"""
    note = "Excellent choice for your dish"
    
    if wine.region:
        if "Rioja" in wine.region:
            note = "Classic Rioja - balance of fruit and oak"
        elif "Ribera" in wine.region:
            note = "Ribera del Duero - intensity and depth"
        elif "Rías Baixas" in wine.region or "Rias Baixas" in wine.region:
            note = "Albarino from Galicia - ocean minerality"
        elif "Rueda" in wine.region:
            note = "Verdejo - herbs and citrus"
        elif "Priorat" in wine.region:
            note = "Priorat - power and concentration"
        elif "Jumilla" in wine.region:
            note = "Monastrell - prune and spice"
        elif "Bierzo" in wine.region:
            note = "Mencia - elegance of Bierzo"
        elif "Navarra" in wine.region:
            note = "Navarra - capital of rose wines"
        elif "Penedès" in wine.region or "Penedes" in wine.region:
            note = "Penedes - home of Spanish Cava"
    elif wine.wine_type == "cava":
        note = "Spanish sparkling - celebration in a glass"
    
    return translate(note, lang)


@app.get("/search")
async def search_wines(
    query: Optional[str] = Query(None, description="Search query"),
    wine_type: Optional[str] = Query(None, description="tinto, blanco, rosado, cava"),
    region: Optional[str] = Query(None, description="DO Region"),
    min_price: float = Query(0, description="Minimum price"),
    max_price: float = Query(100.0, description="Maximum price"),
    store: Optional[str] = Query(None, description="consum, mercadona"),
    postal_code: str = Query("46001", description="Postal code"),
    limit: int = Query(30, description="Number of results")
):
    """Search wines with filters"""
    
    all_wines = await get_wines(postal_code)
    filtered = all_wines
    
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
    
    filtered = [w for w in filtered if min_price <= (w.discount_price or w.price) <= max_price]
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
            }
        ]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
