"""
Pomogaika Wine API
Production-ready backend с реальными данными магазинов
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import asyncio
from concurrent.futures import ThreadPoolExecutor

from sommelier import SommelierEngine
from wine_parser import WineAggregator, WineType, Wine as ParserWine

app = FastAPI(
    title="Pomogaika Wine API",
    description="API для подбора вина к еде с реальными данными Consum & Mercadona",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация
sommelier = SommelierEngine()
executor = ThreadPoolExecutor(max_workers=4)

# Кэш вин (обновляется каждые 30 минут)
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
    data_source: str  # "live" или "cache"


class ExpertRecommendation(BaseModel):
    style: str
    grape_varieties: list[str]
    regions: list[str]
    wine_type: str
    description: str
    priority: int


# === Wine Fetching ===

def fetch_wines_sync(postal_code: str = "46001") -> list[ParserWine]:
    """Синхронное получение вин из магазинов"""
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
    """Асинхронное получение вин с кэшированием"""
    import time
    
    # Проверяем кэш (30 минут)
    if wine_cache["wines"] and wine_cache["last_update"]:
        if time.time() - wine_cache["last_update"] < 1800:  # 30 min
            return wine_cache["wines"]
    
    # Получаем свежие данные
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
        
        # Обновляем кэш
        wine_cache["wines"] = wines
        wine_cache["last_update"] = time.time()
        
        return wines
        
    except Exception as e:
        print(f"Error fetching wines: {e}")
        # Возвращаем кэш если есть
        if wine_cache["wines"]:
            return wine_cache["wines"]
        return []


# === Endpoints ===

@app.get("/")
async def root():
    return {
        "name": "Pomogaika Wine API",
        "version": "2.0.0",
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
    meal_time: Optional[str] = Query(None, description="lunch, dinner, aperitivo"),
    cuisine: Optional[str] = Query(None, description="spanish, italian, asian, indian, mediterranean, bbq")
):
    """Получить экспертные рекомендации сомелье"""
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
    dish: str = Query(..., description="Тип блюда"),
    cooking_method: Optional[str] = Query(None, description="Способ приготовления"),
    meal_time: Optional[str] = Query(None, description="Время приёма пищи"),
    cuisine: Optional[str] = Query(None, description="Тип кухни"),
    min_price: float = Query(0, description="Минимальная цена"),
    max_price: float = Query(30.0, description="Максимальная цена"),
    postal_code: str = Query("46001", description="Почтовый индекс"),
    limit: int = Query(15, description="Количество результатов")
):
    """Получить рекомендации вин с реальными данными магазинов"""
    
    # 1. Получаем экспертные рекомендации
    expert_recs = sommelier.get_recommendations(dish, cooking_method, meal_time, cuisine)
    
    if not expert_recs:
        raise HTTPException(status_code=400, detail="Не удалось подобрать рекомендации")
    
    primary_rec = expert_recs[0]
    
    # 2. Получаем вина из магазинов
    all_wines = await get_wines(postal_code)
    data_source = "live" if wine_cache["last_update"] else "cache"
    
    # 3. Фильтруем по типу вина
    filtered = [w for w in all_wines if w.wine_type == primary_rec.wine_type]
    
    # 4. Фильтруем по цене
    filtered = [w for w in filtered if min_price <= (w.discount_price or w.price) <= max_price]
    
    # 5. Scoring на основе соответствия рекомендациям
    def score_wine(wine: WineResponse) -> int:
        score = 50
        
        # +20 за совпадение региона
        if wine.region:
            for region in primary_rec.regions:
                if region.lower() in wine.region.lower():
                    score += 20
                    break
        
        # +15 за совпадение сорта в названии
        for grape in primary_rec.grape_varieties:
            if grape.lower() in wine.name.lower():
                score += 15
                break
        
        # +10 за скидку
        if wine.discount_price:
            score += 10
        
        # +5 за наличие региона (качество)
        if wine.region:
            score += 5
        
        return min(score, 100)
    
    # 6. Добавляем score и сортируем
    scored_wines = []
    for wine in filtered:
        wine.match_score = score_wine(wine)
        wine.expert_note = get_expert_note(wine, primary_rec)
        scored_wines.append(wine)
    
    scored_wines.sort(key=lambda w: w.match_score or 0, reverse=True)
    
    return RecommendationResponse(
        total=len(scored_wines),
        expert_summary=primary_rec.description,
        recommended_style=primary_rec.style.value,
        recommended_grapes=primary_rec.grape_varieties,
        recommended_regions=primary_rec.regions,
        wines=scored_wines[:limit],
        data_source=data_source
    )


def get_expert_note(wine: WineResponse, rec) -> str:
    """Генерация экспертной заметки"""
    if wine.region:
        if "Rioja" in wine.region:
            return "Классическая Риоха — баланс фруктов и дуба"
        elif "Ribera" in wine.region:
            return "Рибера дель Дуэро — интенсивность и глубина"
        elif "Rías Baixas" in wine.region:
            return "Альбариньо из Галисии — минеральность океана"
        elif "Rueda" in wine.region:
            return "Вердехо — травы и цитрусы"
        elif "Priorat" in wine.region:
            return "Приорат — мощь и концентрация"
        elif "Jumilla" in wine.region:
            return "Монастрель — чернослив и специи"
        elif "Bierzo" in wine.region:
            return "Менсия — элегантность Бьерсо"
        elif "Navarra" in wine.region:
            return "Наварра — столица розовых вин"
        elif "Penedès" in wine.region:
            return "Пенедес — дом испанской Кавы"
    
    if wine.wine_type == "cava":
        return "Испанское игристое — праздник в бокале"
    
    return f"Отличный выбор для вашего блюда"


@app.get("/search")
async def search_wines(
    query: Optional[str] = Query(None, description="Поисковый запрос"),
    wine_type: Optional[str] = Query(None, description="tinto, blanco, rosado, cava"),
    region: Optional[str] = Query(None, description="Регион DO"),
    min_price: float = Query(0, description="Минимальная цена"),
    max_price: float = Query(100.0, description="Максимальная цена"),
    store: Optional[str] = Query(None, description="consum, mercadona"),
    postal_code: str = Query("46001", description="Почтовый индекс"),
    limit: int = Query(30, description="Количество результатов")
):
    """Поиск вин с фильтрами"""
    
    all_wines = await get_wines(postal_code)
    filtered = all_wines
    
    # Фильтры
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
    
    # Цена
    filtered = [w for w in filtered if min_price <= (w.discount_price or w.price) <= max_price]
    
    # Сортировка по цене
    filtered.sort(key=lambda w: w.discount_price or w.price)
    
    return {
        "total": len(filtered),
        "wines": filtered[:limit]
    }


@app.get("/stores")
async def get_stores():
    """Список поддерживаемых магазинов"""
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
