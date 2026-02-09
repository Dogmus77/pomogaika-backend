"""
Pomogaika Wine API
Production-ready backend with real store data
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
    description="Wine pairing API with real data from Consum & Mercadona",
    version="2.0.0"
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
        "version": "2.0.0",
        "stores": ["Consum", "Mercadona", "Masymas", "DIA"],
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
    limit: int = Query(15, description="Number of results"),
    lang: str = Query("ru", description="Language: ru, uk, be, en, es")
):
    """Get wine recommendations with real store data"""
    
    # 1. Get expert recommendations
    expert_recs = sommelier.get_recommendations(dish, cooking_method, meal_time, cuisine)
    
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
    
    # 6. Add scores and sort
    scored_wines = []
    for wine in filtered:
        wine.match_score = score_wine(wine)
        wine.expert_note = get_expert_note(wine, primary_rec, lang)
        scored_wines.append(wine)
    
    scored_wines.sort(key=lambda w: w.match_score or 0, reverse=True)
    
    return RecommendationResponse(
        total=len(scored_wines),
        expert_summary=translate_summary(primary_rec.description, lang),
        recommended_style=primary_rec.style.value,
        recommended_grapes=primary_rec.grape_varieties,
        recommended_regions=primary_rec.regions,
        wines=scored_wines[:limit],
        data_source=data_source
    )


# === Localization ===

SUMMARY_TRANSLATIONS = {
    "Fresh white with minerality enhances raw fish": {
        "ru": "Свежее белое с минеральностью — идеально к сырой рыбе",
        "uk": "Свіже біле з мінеральністю — ідеально до сирої риби",
        "be": "Свежае белае з мінеральнасцю — ідэальна да сырой рыбы",
        "en": "Fresh white with minerality enhances raw fish",
        "es": "Blanco fresco con mineralidad — ideal para pescado crudo",
    },
    "Cava freshness is classic with raw fish": {
        "ru": "Свежесть Кавы — классика к сырой рыбе",
        "uk": "Свіжість Кави — класика до сирої риби",
        "be": "Свежасць Кавы — класіка да сырой рыбы",
        "en": "Cava freshness is classic with raw fish",
        "es": "La frescura del Cava es clásica con pescado crudo",
    },
    "Delicate steamed fish needs an elegant wine": {
        "ru": "Деликатная рыба на пару требует элегантного вина",
        "uk": "Делікатна риба на парі потребує елегантного вина",
        "be": "Далікатная рыба на пары патрабуе элегантнага віна",
        "en": "Delicate steamed fish needs an elegant wine",
        "es": "El pescado al vapor necesita un vino elegante",
    },
    "Grilling adds intensity - needs fuller white": {
        "ru": "Гриль добавляет интенсивности — нужно плотное белое",
        "uk": "Гриль додає інтенсивності — потрібне щільне біле",
        "be": "Грыль дадае інтэнсіўнасці — патрэбна шчыльнае белае",
        "en": "Grilling adds intensity - needs fuller white",
        "es": "La parrilla añade intensidad — necesita blanco con cuerpo",
    },
    "Rose is versatile with grilled fish": {
        "ru": "Розовое универсально к рыбе на гриле",
        "uk": "Рожеве універсальне до риби на грилі",
        "be": "Ружовае ўніверсальнае да рыбы на грылі",
        "en": "Rosé is versatile with grilled fish",
        "es": "El rosado es versátil con pescado a la parrilla",
    },
    "Tomato sauce needs wine with good acidity": {
        "ru": "К томатному соусу — вино с хорошей кислотностью",
        "uk": "До томатного соусу — вино з гарною кислотністю",
        "be": "Да таматнага соусу — віно з добрай кіслотнасцю",
        "en": "Tomato sauce needs wine with good acidity",
        "es": "La salsa de tomate necesita vino con buena acidez",
    },
    "Light Mencia - bold but successful pairing": {
        "ru": "Лёгкая Менсия — смелое, но удачное сочетание",
        "uk": "Легка Менсія — сміливе, але вдале поєднання",
        "be": "Лёгкая Менсія — смелае, але ўдалае спалучэнне",
        "en": "Light Mencía — bold but successful pairing",
        "es": "Mencía ligera — maridaje atrevido pero exitoso",
    },
    "Creamy sauce needs oaked white with body": {
        "ru": "К сливочному соусу — выдержанное белое с телом",
        "uk": "До вершкового соусу — витримане біле з тілом",
        "be": "Да смятанкавага соусу — вытрыманае белае з целам",
        "en": "Creamy sauce needs oaked white with body",
        "es": "La salsa cremosa necesita blanco con crianza y cuerpo",
    },
    "Classic: grilled steak + Tempranillo Crianza": {
        "ru": "Классика: стейк на гриле + Темпранильо Крианса",
        "uk": "Класика: стейк на грилі + Темпранільо Кріанса",
        "be": "Класіка: стэйк на грылі + Тэмпранільё Крыянса",
        "en": "Classic: grilled steak + Tempranillo Crianza",
        "es": "Clásico: chuletón a la parrilla + Tempranillo Crianza",
    },
    "For rich meat - powerful Priorat": {
        "ru": "Для насыщенного мяса — мощный Приорат",
        "uk": "Для насиченого м'яса — потужний Пріорат",
        "be": "Для насычанага мяса — магутны Прыярат",
        "en": "For rich meat — powerful Priorat",
        "es": "Para carne rica — un potente Priorat",
    },
    "Roasted meat + aged Tempranillo - perfect": {
        "ru": "Запечённое мясо + выдержанное Темпранильо — идеально",
        "uk": "Запечене м'ясо + витримане Темпранільо — ідеально",
        "be": "Запечанае мяса + вытрыманае Тэмпранільё — ідэальна",
        "en": "Roasted meat + aged Tempranillo — perfect",
        "es": "Carne asada + Tempranillo envejecido — perfecto",
    },
    "Stewed meat needs rich wine with tannins": {
        "ru": "Тушёное мясо требует насыщенного вина с танинами",
        "uk": "Тушковане м'ясо потребує насиченого вина з танінами",
        "be": "Тушанае мяса патрабуе насычанага віна з танінамі",
        "en": "Stewed meat needs rich wine with tannins",
        "es": "El estofado necesita vino con cuerpo y taninos",
    },
    "Spicy meat loves fruity Garnacha": {
        "ru": "К острому мясу — фруктовая Гарнача",
        "uk": "До гострого м'яса — фруктова Гарнача",
        "be": "Да вострага мяса — фруктовая Гарнача",
        "en": "Spicy meat loves fruity Garnacha",
        "es": "La carne especiada adora la Garnacha afrutada",
    },
    "Tomato sauce pairs well with Crianza": {
        "ru": "Томатный соус отлично сочетается с Крианса",
        "uk": "Томатний соус чудово поєднується з Кріанса",
        "be": "Таматны соус выдатна спалучаецца з Крыянса",
        "en": "Tomato sauce pairs well with Crianza",
        "es": "La salsa de tomate marida bien con Crianza",
    },
    "Creamy sauce needs softer red wine": {
        "ru": "К сливочному соусу — мягкое красное вино",
        "uk": "До вершкового соусу — м'яке червоне вино",
        "be": "Да смятанкавага соусу — мяккае чырвонае віно",
        "en": "Creamy sauce needs softer red wine",
        "es": "La salsa cremosa necesita un tinto suave",
    },
    "Grilled poultry loves light fruity reds": {
        "ru": "Птица на гриле любит лёгкие фруктовые красные",
        "uk": "Птиця на грилі любить легкі фруктові червоні",
        "be": "Птушка на грылі любіць лёгкія фруктовыя чырвоныя",
        "en": "Grilled poultry loves light fruity reds",
        "es": "Las aves a la parrilla adoran tintos ligeros y afrutados",
    },
    "Oaked white is elegant with grilled chicken": {
        "ru": "Выдержанное белое элегантно с курицей гриль",
        "uk": "Витримане біле елегантне з курчам на грилі",
        "be": "Вытрыманае белае элегантнае з курыцай грыль",
        "en": "Oaked white is elegant with grilled chicken",
        "es": "Un blanco con barrica es elegante con pollo a la parrilla",
    },
    "Roast chicken pairs with medium reds": {
        "ru": "Запечённая курица сочетается со средними красными",
        "uk": "Запечена курка поєднується з середніми червоними",
        "be": "Запечаная курыца спалучаецца з сярэднімі чырвонымі",
        "en": "Roast chicken pairs with medium reds",
        "es": "El pollo asado combina con tintos medios",
    },
    "Creamy chicken needs rich oaked white": {
        "ru": "Курица в сливках требует насыщенного белого с дубом",
        "uk": "Курка у вершках потребує насиченого білого з дубом",
        "be": "Курыца ў смятанцы патрабуе насычанага белага з дубам",
        "en": "Creamy chicken needs rich oaked white",
        "es": "El pollo en crema necesita blanco con crianza en barrica",
    },
    "Rose is perfect with grilled vegetables": {
        "ru": "Розовое идеально с овощами на гриле",
        "uk": "Рожеве ідеальне з овочами на грилі",
        "be": "Ружовае ідэальнае з гароднінай на грылі",
        "en": "Rosé is perfect with grilled vegetables",
        "es": "El rosado es perfecto con verduras a la parrilla",
    },
    "Light white for delicate steamed veggies": {
        "ru": "Лёгкое белое для деликатных овощей на пару",
        "uk": "Легке біле для делікатних овочів на парі",
        "be": "Лёгкае белае для далікатнай гародніны на пары",
        "en": "Light white for delicate steamed veggies",
        "es": "Blanco ligero para verduras al vapor",
    },
    "Tomato dishes pair beautifully with rose": {
        "ru": "Блюда с томатом прекрасно сочетаются с розовым",
        "uk": "Страви з томатом чудово поєднуються з рожевим",
        "be": "Стравы з таматам цудоўна спалучаюцца з ружовым",
        "en": "Tomato dishes pair beautifully with rosé",
        "es": "Los platos con tomate combinan perfectamente con rosado",
    },
    "Tomato pasta loves Spanish Crianza": {
        "ru": "Паста с томатом любит испанскую Крианса",
        "uk": "Паста з томатом любить іспанську Кріанса",
        "be": "Паста з таматам любіць іспанскую Крыянса",
        "en": "Tomato pasta loves Spanish Crianza",
        "es": "La pasta con tomate adora un Crianza español",
    },
    "Rich creamy pasta needs oaked white": {
        "ru": "Паста в сливочном соусе требует белого с дубом",
        "uk": "Паста у вершковому соусі потребує білого з дубом",
        "be": "Паста ў смятанкавым соусе патрабуе белага з дубам",
        "en": "Rich creamy pasta needs oaked white",
        "es": "La pasta cremosa necesita blanco con barrica",
    },
    "Grilled cheese with fruity young red": {
        "ru": "Сыр на гриле с фруктовым молодым красным",
        "uk": "Сир на грилі з фруктовим молодим червоним",
        "be": "Сыр на грылі з фруктовым маладым чырвоным",
        "en": "Grilled cheese with fruity young red",
        "es": "Queso a la parrilla con tinto joven afrutado",
    },
    "Fresh white wine for fish": {
        "ru": "Свежее белое вино к рыбе",
        "uk": "Свіже біле вино до риби",
        "be": "Свежае белае віно да рыбы",
        "en": "Fresh white wine for fish",
        "es": "Vino blanco fresco para pescado",
    },
    "Red Tempranillo - classic with meat": {
        "ru": "Красное Темпранильо — классика к мясу",
        "uk": "Червоне Темпранільо — класика до м'яса",
        "be": "Чырвонае Тэмпранільё — класіка да мяса",
        "en": "Red Tempranillo — classic with meat",
        "es": "Tempranillo tinto — clásico con carne",
    },
    "Light red pairs well with poultry": {
        "ru": "Лёгкое красное хорошо сочетается с птицей",
        "uk": "Легке червоне добре поєднується з птицею",
        "be": "Лёгкае чырвонае добра спалучаецца з птушкай",
        "en": "Light red pairs well with poultry",
        "es": "Un tinto ligero combina bien con aves",
    },
    "Fresh Verdejo white for vegetables": {
        "ru": "Свежий белый Вердехо к овощам",
        "uk": "Свіжий білий Вердехо до овочів",
        "be": "Свежы белы Вердэхо да гародніны",
        "en": "Fresh Verdejo white for vegetables",
        "es": "Verdejo fresco para verduras",
    },
    "Versatile red for pasta": {
        "ru": "Универсальное красное к пасте",
        "uk": "Універсальне червоне до пасти",
        "be": "Універсальнае чырвонае да пасты",
        "en": "Versatile red for pasta",
        "es": "Tinto versátil para pasta",
    },
    "Aged red wine for cheese": {
        "ru": "Выдержанное красное к сыру",
        "uk": "Витримане червоне до сиру",
        "be": "Вытрыманае чырвонае да сыру",
        "en": "Aged red wine for cheese",
        "es": "Tinto envejecido para queso",
    },
    "Cava - perfect choice for aperitivo": {
        "ru": "Кава — идеальный выбор для аперитива",
        "uk": "Кава — ідеальний вибір для аперитиву",
        "be": "Кава — ідэальны выбар для аперытыву",
        "en": "Cava — perfect choice for aperitif",
        "es": "Cava — elección perfecta para el aperitivo",
    },
}

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


def translate_summary(description: str, lang: str) -> str:
    """Translate sommelier summary to target language"""
    if description in SUMMARY_TRANSLATIONS:
        return SUMMARY_TRANSLATIONS[description].get(lang, SUMMARY_TRANSLATIONS[description].get("en", description))
    return description


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
    store: Optional[str] = Query(None, description="consum, mercadona, masymas, dia"),
    postal_code: str = Query("46001", description="Postal code"),
    limit: int = Query(30, description="Number of results")
):
    """Search wines with filters"""
    
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
                "has_ean": False,
                "coverage": "Valencia, Alicante, Murcia",
                "status": "stub"
            },
            {
                "id": "dia",
                "name": "DIA",
                "has_ean": False,
                "coverage": "Toda España",
                "status": "stub"
            }
        ]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
