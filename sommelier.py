"""
Wine Sommelier Engine
Экспертная система подбора вина к еде

Основные принципы:
1. Интенсивность вина = интенсивность блюда
2. Способ приготовления важнее продукта
3. Соус определяет выбор вина
4. Региональные сочетания (местная еда + местное вино)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CookingMethod(Enum):
    """Способ приготовления"""
    RAW = "raw"              # Сырое (тартар, карпаччо)
    STEAMED = "steamed"      # На пару
    GRILLED = "grilled"      # Гриль / на углях
    FRIED = "fried"          # Жареное
    ROASTED = "roasted"      # Запечённое
    STEWED = "stewed"        # Тушёное
    CREAMY = "creamy"        # В сливочном соусе
    TOMATO = "tomato"        # В томатном соусе
    SPICY = "spicy"          # Острое


class WineStyle(Enum):
    """Стиль вина"""
    WHITE_LIGHT = "white_light"        # Лёгкое белое
    WHITE_AROMATIC = "white_aromatic"  # Ароматное белое
    WHITE_FULL = "white_full"          # Полнотелое белое
    ROSE = "rose"                      # Розовое
    RED_LIGHT = "red_light"            # Лёгкое красное
    RED_MEDIUM = "red_medium"          # Среднее красное
    RED_FULL = "red_full"              # Полнотелое красное
    SPARKLING = "sparkling"            # Игристое (Кава)


@dataclass
class WineRecommendation:
    """Рекомендация вина"""
    style: WineStyle
    grape_varieties: list[str]      # Сорта винограда
    regions: list[str]              # Регионы DO
    wine_type: str                  # tinto/blanco/rosado/cava
    description: str                # Почему это вино подходит
    search_terms: list[str]         # Термины для поиска в магазинах
    priority: int                   # Приоритет (1 = лучший выбор)


class SommelierEngine:
    """
    Экспертная система сомелье
    """
    
    # Испанские сорта винограда
    SPANISH_GRAPES = {
        # Белые
        "albarino": {"type": "white", "body": "light", "regions": ["Rías Baixas"]},
        "verdejo": {"type": "white", "body": "light", "regions": ["Rueda"]},
        "godello": {"type": "white", "body": "medium", "regions": ["Valdeorras", "Bierzo"]},
        "viura": {"type": "white", "body": "light", "regions": ["Rioja"]},
        "chardonnay": {"type": "white", "body": "full", "regions": ["Penedès", "Navarra"]},
        "macabeo": {"type": "white", "body": "light", "regions": ["Penedès", "Rioja"]},
        
        # Красные
        "tempranillo": {"type": "red", "body": "medium", "regions": ["Rioja", "Ribera del Duero", "Toro"]},
        "garnacha": {"type": "red", "body": "medium", "regions": ["Priorat", "Navarra", "Campo de Borja"]},
        "monastrell": {"type": "red", "body": "full", "regions": ["Jumilla", "Yecla", "Alicante"]},
        "mencia": {"type": "red", "body": "light", "regions": ["Bierzo", "Ribeira Sacra"]},
        "bobal": {"type": "red", "body": "medium", "regions": ["Utiel-Requena"]},
        "cariñena": {"type": "red", "body": "full", "regions": ["Priorat", "Cariñena"]},
    }
    
    # Матрица сочетаний: (dish, cooking_method) -> рекомендации
    PAIRING_MATRIX = {
        # === РЫБА ===
        ("fish", "raw"): [
            WineRecommendation(
                style=WineStyle.WHITE_LIGHT,
                grape_varieties=["albarino", "verdejo"],
                regions=["Rías Baixas", "Rueda"],
                wine_type="blanco",
                description="Свежее белое с минеральностью подчеркнёт вкус сырой рыбы",
                search_terms=["albariño", "verdejo", "blanco"],
                priority=1
            ),
            WineRecommendation(
                style=WineStyle.SPARKLING,
                grape_varieties=["macabeo", "xarello", "parellada"],
                regions=["Penedès"],
                wine_type="cava",
                description="Кава с её свежестью — классика к сырой рыбе",
                search_terms=["cava", "brut"],
                priority=2
            ),
        ],
        ("fish", "steamed"): [
            WineRecommendation(
                style=WineStyle.WHITE_LIGHT,
                grape_varieties=["albarino", "godello"],
                regions=["Rías Baixas", "Valdeorras"],
                wine_type="blanco",
                description="Деликатная рыба на пару требует тонкого вина",
                search_terms=["albariño", "godello", "blanco"],
                priority=1
            ),
        ],
        ("fish", "grilled"): [
            WineRecommendation(
                style=WineStyle.WHITE_FULL,
                grape_varieties=["godello", "chardonnay"],
                regions=["Valdeorras", "Penedès"],
                wine_type="blanco",
                description="Гриль добавляет интенсивности — нужно более плотное белое",
                search_terms=["godello", "chardonnay", "fermentado barrica"],
                priority=1
            ),
            WineRecommendation(
                style=WineStyle.ROSE,
                grape_varieties=["garnacha", "tempranillo"],
                regions=["Navarra", "Rioja"],
                wine_type="rosado",
                description="Розовое — универсальный выбор для рыбы гриль",
                search_terms=["rosado", "garnacha"],
                priority=2
            ),
        ],
        ("fish", "tomato"): [
            WineRecommendation(
                style=WineStyle.ROSE,
                grape_varieties=["garnacha", "tempranillo"],
                regions=["Navarra", "Cigales"],
                wine_type="rosado",
                description="Томатный соус требует вина с хорошей кислотностью",
                search_terms=["rosado"],
                priority=1
            ),
            WineRecommendation(
                style=WineStyle.RED_LIGHT,
                grape_varieties=["mencia"],
                regions=["Bierzo"],
                wine_type="tinto",
                description="Лёгкое красное Менсия — смелый, но удачный выбор",
                search_terms=["mencía", "bierzo", "tinto joven"],
                priority=2
            ),
        ],
        ("fish", "creamy"): [
            WineRecommendation(
                style=WineStyle.WHITE_FULL,
                grape_varieties=["chardonnay", "viura"],
                regions=["Penedès", "Rioja"],
                wine_type="blanco",
                description="Сливочный соус требует выдержанного белого с телом",
                search_terms=["chardonnay", "blanco fermentado barrica", "blanco crianza"],
                priority=1
            ),
        ],
        
        # === МЯСО ===
        ("meat", "grilled"): [
            WineRecommendation(
                style=WineStyle.RED_MEDIUM,
                grape_varieties=["tempranillo"],
                regions=["Rioja", "Ribera del Duero"],
                wine_type="tinto",
                description="Классика: стейк на гриле + Темпранильо Крианса",
                search_terms=["tempranillo", "crianza", "rioja", "ribera"],
                priority=1
            ),
            WineRecommendation(
                style=WineStyle.RED_FULL,
                grape_varieties=["garnacha", "cariñena"],
                regions=["Priorat"],
                wine_type="tinto",
                description="Для насыщенного мяса — мощный Приорат",
                search_terms=["priorat", "garnacha"],
                priority=2
            ),
        ],
        ("meat", "roasted"): [
            WineRecommendation(
                style=WineStyle.RED_MEDIUM,
                grape_varieties=["tempranillo"],
                regions=["Rioja", "Ribera del Duero", "Toro"],
                wine_type="tinto",
                description="Запечённое мясо + выдержанное Темпранильо — идеально",
                search_terms=["reserva", "gran reserva", "tempranillo"],
                priority=1
            ),
        ],
        ("meat", "stewed"): [
            WineRecommendation(
                style=WineStyle.RED_FULL,
                grape_varieties=["monastrell", "garnacha"],
                regions=["Jumilla", "Yecla", "Priorat"],
                wine_type="tinto",
                description="Тушёное мясо требует насыщенного вина с танинами",
                search_terms=["monastrell", "jumilla", "garnacha"],
                priority=1
            ),
        ],
        ("meat", "spicy"): [
            WineRecommendation(
                style=WineStyle.RED_MEDIUM,
                grape_varieties=["garnacha"],
                regions=["Campo de Borja", "Navarra"],
                wine_type="tinto",
                description="Фруктовая Гарнача смягчит остроту",
                search_terms=["garnacha", "joven"],
                priority=1
            ),
        ],
        
        # === ПТИЦА ===
        ("poultry", "grilled"): [
            WineRecommendation(
                style=WineStyle.RED_LIGHT,
                grape_varieties=["mencia", "garnacha"],
                regions=["Bierzo", "Navarra"],
                wine_type="tinto",
                description="Лёгкое красное для птицы гриль",
                search_terms=["mencía", "garnacha", "joven"],
                priority=1
            ),
            WineRecommendation(
                style=WineStyle.WHITE_FULL,
                grape_varieties=["chardonnay", "godello"],
                regions=["Penedès", "Valdeorras"],
                wine_type="blanco",
                description="Насыщенное белое — отличная альтернатива",
                search_terms=["chardonnay", "godello"],
                priority=2
            ),
        ],
        ("poultry", "roasted"): [
            WineRecommendation(
                style=WineStyle.RED_LIGHT,
                grape_varieties=["tempranillo", "mencia"],
                regions=["Rioja", "Bierzo"],
                wine_type="tinto",
                description="Запечённая птица + молодое Темпранильо",
                search_terms=["tinto joven", "crianza"],
                priority=1
            ),
        ],
        ("poultry", "creamy"): [
            WineRecommendation(
                style=WineStyle.WHITE_FULL,
                grape_varieties=["chardonnay"],
                regions=["Penedès", "Navarra"],
                wine_type="blanco",
                description="Курица в сливках = Шардоне с выдержкой в дубе",
                search_terms=["chardonnay", "fermentado barrica"],
                priority=1
            ),
        ],
        
        # === ОВОЩИ ===
        ("vegetables", "raw"): [
            WineRecommendation(
                style=WineStyle.WHITE_LIGHT,
                grape_varieties=["verdejo", "sauvignon blanc"],
                regions=["Rueda"],
                wine_type="blanco",
                description="Свежий салат + хрустящее Вердехо",
                search_terms=["verdejo", "rueda", "sauvignon"],
                priority=1
            ),
        ],
        ("vegetables", "grilled"): [
            WineRecommendation(
                style=WineStyle.ROSE,
                grape_varieties=["garnacha"],
                regions=["Navarra", "Cigales"],
                wine_type="rosado",
                description="Овощи гриль отлично сочетаются с розовым",
                search_terms=["rosado", "garnacha"],
                priority=1
            ),
            WineRecommendation(
                style=WineStyle.WHITE_AROMATIC,
                grape_varieties=["verdejo", "godello"],
                regions=["Rueda", "Valdeorras"],
                wine_type="blanco",
                description="Ароматное белое подчеркнёт вкус овощей",
                search_terms=["verdejo", "godello"],
                priority=2
            ),
        ],
        ("vegetables", "stewed"): [
            WineRecommendation(
                style=WineStyle.RED_LIGHT,
                grape_varieties=["tempranillo", "garnacha"],
                regions=["Rioja", "Navarra"],
                wine_type="tinto",
                description="Тушёные овощи (писто) + лёгкое красное",
                search_terms=["tinto joven", "garnacha"],
                priority=1
            ),
        ],
        
        # === ПАСТА ===
        ("pasta", "tomato"): [
            WineRecommendation(
                style=WineStyle.RED_LIGHT,
                grape_varieties=["tempranillo"],
                regions=["Rioja", "La Mancha"],
                wine_type="tinto",
                description="Томатный соус + молодое Темпранильо с кислотностью",
                search_terms=["tinto joven", "tempranillo"],
                priority=1
            ),
        ],
        ("pasta", "creamy"): [
            WineRecommendation(
                style=WineStyle.WHITE_FULL,
                grape_varieties=["chardonnay", "viura"],
                regions=["Penedès", "Rioja"],
                wine_type="blanco",
                description="Карбонара или Альфредо + выдержанное белое",
                search_terms=["chardonnay", "blanco crianza"],
                priority=1
            ),
        ],
        ("pasta", "grilled"): [  # С мясом
            WineRecommendation(
                style=WineStyle.RED_MEDIUM,
                grape_varieties=["tempranillo", "bobal"],
                regions=["Ribera del Duero", "Utiel-Requena"],
                wine_type="tinto",
                description="Паста с мясом требует структурного красного",
                search_terms=["crianza", "tempranillo", "bobal"],
                priority=1
            ),
        ],
        
        # === СЫР ===
        ("cheese", "raw"): [  # Свежий сыр
            WineRecommendation(
                style=WineStyle.WHITE_LIGHT,
                grape_varieties=["verdejo", "albarino"],
                regions=["Rueda", "Rías Baixas"],
                wine_type="blanco",
                description="Свежий сыр + свежее белое",
                search_terms=["verdejo", "albariño"],
                priority=1
            ),
        ],
        ("cheese", "roasted"): [  # Выдержанный сыр (Manchego и т.д.)
            WineRecommendation(
                style=WineStyle.RED_MEDIUM,
                grape_varieties=["tempranillo"],
                regions=["Rioja", "Ribera del Duero"],
                wine_type="tinto",
                description="Выдержанный Манчего + Ресерва — классика",
                search_terms=["reserva", "crianza", "tempranillo"],
                priority=1
            ),
            WineRecommendation(
                style=WineStyle.RED_FULL,
                grape_varieties=["monastrell"],
                regions=["Jumilla"],
                wine_type="tinto",
                description="Мощный Монастрель для очень выдержанного сыра",
                search_terms=["monastrell", "jumilla"],
                priority=2
            ),
        ],
    }
    
    # Дефолтные рекомендации по типу блюда
    DEFAULT_RECOMMENDATIONS = {
        "fish": [
            WineRecommendation(
                style=WineStyle.WHITE_LIGHT,
                grape_varieties=["albarino", "verdejo"],
                regions=["Rías Baixas", "Rueda"],
                wine_type="blanco",
                description="Белое вино — классический выбор к рыбе",
                search_terms=["blanco", "albariño", "verdejo"],
                priority=1
            ),
        ],
        "meat": [
            WineRecommendation(
                style=WineStyle.RED_MEDIUM,
                grape_varieties=["tempranillo"],
                regions=["Rioja", "Ribera del Duero"],
                wine_type="tinto",
                description="Красное Темпранильо — классика к мясу",
                search_terms=["tinto", "crianza", "tempranillo", "rioja"],
                priority=1
            ),
        ],
        "poultry": [
            WineRecommendation(
                style=WineStyle.RED_LIGHT,
                grape_varieties=["mencia", "garnacha"],
                regions=["Bierzo", "Navarra"],
                wine_type="tinto",
                description="Лёгкое красное отлично подходит к птице",
                search_terms=["tinto joven", "mencía", "garnacha"],
                priority=1
            ),
        ],
        "vegetables": [
            WineRecommendation(
                style=WineStyle.WHITE_LIGHT,
                grape_varieties=["verdejo"],
                regions=["Rueda"],
                wine_type="blanco",
                description="Свежее белое Вердехо к овощам",
                search_terms=["verdejo", "rueda", "blanco"],
                priority=1
            ),
        ],
        "pasta": [
            WineRecommendation(
                style=WineStyle.RED_LIGHT,
                grape_varieties=["tempranillo"],
                regions=["Rioja"],
                wine_type="tinto",
                description="Универсальное красное к пасте",
                search_terms=["tinto joven"],
                priority=1
            ),
        ],
        "cheese": [
            WineRecommendation(
                style=WineStyle.RED_MEDIUM,
                grape_varieties=["tempranillo"],
                regions=["Rioja", "Ribera del Duero"],
                wine_type="tinto",
                description="Выдержанное красное к сыру",
                search_terms=["crianza", "reserva"],
                priority=1
            ),
        ],
    }
    
    # Модификаторы по времени приёма пищи
    MEAL_TIME_MODIFIERS = {
        "lunch": {
            "prefer_light": True,
            "avoid_full_bodied": True,
            "description": "Для обеда лучше выбрать более лёгкое вино"
        },
        "dinner": {
            "prefer_light": False,
            "avoid_full_bodied": False,
            "description": "Для ужина можно выбрать более насыщенное вино"
        },
        "aperitivo": {
            "prefer_sparkling": True,
            "prefer_light": True,
            "description": "Для аперитива идеальны игристые и лёгкие вина"
        },
    }
    
    # Модификаторы по типу кухни
    CUISINE_MODIFIERS = {
        "spanish": {
            "preferred_regions": ["Rioja", "Ribera del Duero", "Rías Baixas"],
            "description": "Испанская кухня + испанское вино — идеальное сочетание"
        },
        "italian": {
            "prefer_acidic": True,
            "description": "К итальянской кухне нужны вина с хорошей кислотностью"
        },
        "asian": {
            "prefer_aromatic": True,
            "prefer_off_dry": True,
            "description": "К азиатской кухне подойдут ароматные, слегка сладкие вина"
        },
        "indian": {
            "prefer_fruity": True,
            "avoid_tannic": True,
            "description": "К острой индийской кухне — фруктовые вина без танинов"
        },
        "mediterranean": {
            "preferred_regions": ["Penedès", "Priorat", "Navarra"],
            "description": "Средиземноморская кухня любит местные вина"
        },
        "bbq": {
            "prefer_full_bodied": True,
            "description": "Барбекю требует насыщенных вин с характером"
        },
    }
    
    def get_recommendations(
        self,
        dish: str,
        cooking_method: Optional[str] = None,
        meal_time: Optional[str] = None,
        cuisine: Optional[str] = None,
        max_results: int = 3
    ) -> list[WineRecommendation]:
        """
        Получить рекомендации вина
        
        Args:
            dish: Тип блюда (fish, meat, poultry, vegetables, pasta, cheese)
            cooking_method: Способ приготовления (raw, steamed, grilled, etc.)
            meal_time: Время приёма пищи (lunch, dinner, aperitivo)
            cuisine: Тип кухни (spanish, italian, asian, etc.)
            max_results: Максимальное количество рекомендаций
        """
        recommendations = []
        
        # 1. Ищем точное совпадение (блюдо + способ приготовления)
        if cooking_method:
            key = (dish, cooking_method)
            if key in self.PAIRING_MATRIX:
                recommendations = self.PAIRING_MATRIX[key].copy()
        
        # 2. Если не нашли — берём дефолтные по типу блюда
        if not recommendations and dish in self.DEFAULT_RECOMMENDATIONS:
            recommendations = self.DEFAULT_RECOMMENDATIONS[dish].copy()
        
        # 3. Применяем модификаторы времени
        if meal_time and meal_time in self.MEAL_TIME_MODIFIERS:
            modifier = self.MEAL_TIME_MODIFIERS[meal_time]
            
            # Для аперитива добавляем игристое в начало
            if modifier.get("prefer_sparkling"):
                sparkling_rec = WineRecommendation(
                    style=WineStyle.SPARKLING,
                    grape_varieties=["macabeo", "xarello", "parellada"],
                    regions=["Penedès"],
                    wine_type="cava",
                    description="Кава — идеальный выбор для аперитива",
                    search_terms=["cava", "brut"],
                    priority=0
                )
                recommendations.insert(0, sparkling_rec)
            
            # Для обеда понижаем приоритет полнотелых вин
            if modifier.get("avoid_full_bodied"):
                for rec in recommendations:
                    if rec.style in [WineStyle.RED_FULL, WineStyle.WHITE_FULL]:
                        rec.priority += 2
        
        # 4. Сортируем по приоритету
        recommendations.sort(key=lambda x: x.priority)
        
        return recommendations[:max_results]
    
    def get_search_queries(self, recommendations: list[WineRecommendation]) -> list[str]:
        """Получить поисковые запросы для магазинов"""
        queries = []
        for rec in recommendations:
            # Основной запрос: тип + регион
            for region in rec.regions[:1]:  # Берём первый регион
                queries.append(f"vino {rec.wine_type} {region}")
            
            # Запрос по сорту винограда
            for grape in rec.grape_varieties[:1]:
                queries.append(f"vino {grape}")
            
            # Дополнительные термины
            for term in rec.search_terms[:2]:
                if term not in queries:
                    queries.append(f"vino {term}")
        
        return list(dict.fromkeys(queries))  # Убираем дубликаты, сохраняя порядок


# Пример использования
if __name__ == "__main__":
    sommelier = SommelierEngine()
    
    # Рыба на гриле к ужину
    recs = sommelier.get_recommendations(
        dish="fish",
        cooking_method="grilled",
        meal_time="dinner"
    )
    
    print("🍷 Рекомендации для рыбы гриль на ужин:\n")
    for i, rec in enumerate(recs, 1):
        print(f"{i}. {rec.style.value}")
        print(f"   Сорта: {', '.join(rec.grape_varieties)}")
        print(f"   Регионы: {', '.join(rec.regions)}")
        print(f"   {rec.description}\n")
    
    print("Поисковые запросы:", sommelier.get_search_queries(recs))
