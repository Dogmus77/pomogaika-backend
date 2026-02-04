"""
Wine Sommelier Engine
Expert wine pairing system

Core principles:
1. Wine intensity = dish intensity
2. Cooking method matters more than the protein
3. Sauce determines wine choice
4. Regional pairings (local food + local wine)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CookingMethod(Enum):
    """Cooking method"""
    RAW = "raw"
    STEAMED = "steamed"
    GRILLED = "grilled"
    FRIED = "fried"
    ROASTED = "roasted"
    STEWED = "stewed"
    CREAMY = "creamy"
    TOMATO = "tomato"
    SPICY = "spicy"


class WineStyle(Enum):
    """Wine style"""
    WHITE_LIGHT = "white_light"
    WHITE_AROMATIC = "white_aromatic"
    WHITE_FULL = "white_full"
    ROSE = "rose"
    RED_LIGHT = "red_light"
    RED_MEDIUM = "red_medium"
    RED_FULL = "red_full"
    SPARKLING = "sparkling"


@dataclass
class WineRecommendation:
    """Wine recommendation"""
    style: WineStyle
    grape_varieties: list[str]
    regions: list[str]
    wine_type: str
    description: str
    search_terms: list[str]
    priority: int


class SommelierEngine:
    """Expert sommelier system"""
    
    SPANISH_GRAPES = {
        # White
        "albarino": {"type": "white", "body": "light", "regions": ["Rias Baixas"]},
        "verdejo": {"type": "white", "body": "light", "regions": ["Rueda"]},
        "godello": {"type": "white", "body": "medium", "regions": ["Valdeorras", "Bierzo"]},
        "viura": {"type": "white", "body": "light", "regions": ["Rioja"]},
        "chardonnay": {"type": "white", "body": "full", "regions": ["Penedes", "Navarra"]},
        "macabeo": {"type": "white", "body": "light", "regions": ["Penedes", "Rioja"]},
        
        # Red
        "tempranillo": {"type": "red", "body": "medium", "regions": ["Rioja", "Ribera del Duero", "Toro"]},
        "garnacha": {"type": "red", "body": "medium", "regions": ["Priorat", "Navarra", "Campo de Borja"]},
        "monastrell": {"type": "red", "body": "full", "regions": ["Jumilla", "Yecla", "Alicante"]},
        "mencia": {"type": "red", "body": "light", "regions": ["Bierzo", "Ribeira Sacra"]},
        "bobal": {"type": "red", "body": "medium", "regions": ["Utiel-Requena"]},
        "carinena": {"type": "red", "body": "full", "regions": ["Priorat", "Carinena"]},
    }
    
    PAIRING_MATRIX = {
        # === FISH ===
        ("fish", "raw"): [
            WineRecommendation(
                style=WineStyle.WHITE_LIGHT,
                grape_varieties=["albarino", "verdejo"],
                regions=["Rias Baixas", "Rueda"],
                wine_type="blanco",
                description="Fresh white with minerality enhances raw fish",
                search_terms=["albarino", "verdejo", "blanco"],
                priority=1
            ),
            WineRecommendation(
                style=WineStyle.SPARKLING,
                grape_varieties=["macabeo", "xarello", "parellada"],
                regions=["Penedes"],
                wine_type="cava",
                description="Cava freshness is classic with raw fish",
                search_terms=["cava", "brut"],
                priority=2
            ),
        ],
        ("fish", "steamed"): [
            WineRecommendation(
                style=WineStyle.WHITE_LIGHT,
                grape_varieties=["albarino", "godello"],
                regions=["Rias Baixas", "Valdeorras"],
                wine_type="blanco",
                description="Delicate steamed fish needs an elegant wine",
                search_terms=["albarino", "godello", "blanco"],
                priority=1
            ),
        ],
        ("fish", "grilled"): [
            WineRecommendation(
                style=WineStyle.WHITE_FULL,
                grape_varieties=["godello", "chardonnay"],
                regions=["Valdeorras", "Penedes"],
                wine_type="blanco",
                description="Grilling adds intensity - needs fuller white",
                search_terms=["godello", "chardonnay", "fermentado barrica"],
                priority=1
            ),
            WineRecommendation(
                style=WineStyle.ROSE,
                grape_varieties=["garnacha", "tempranillo"],
                regions=["Navarra", "Rioja"],
                wine_type="rosado",
                description="Rose is versatile with grilled fish",
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
                description="Tomato sauce needs wine with good acidity",
                search_terms=["rosado"],
                priority=1
            ),
            WineRecommendation(
                style=WineStyle.RED_LIGHT,
                grape_varieties=["mencia"],
                regions=["Bierzo"],
                wine_type="tinto",
                description="Light Mencia - bold but successful pairing",
                search_terms=["mencia", "bierzo", "tinto joven"],
                priority=2
            ),
        ],
        ("fish", "creamy"): [
            WineRecommendation(
                style=WineStyle.WHITE_FULL,
                grape_varieties=["chardonnay", "viura"],
                regions=["Penedes", "Rioja"],
                wine_type="blanco",
                description="Creamy sauce needs oaked white with body",
                search_terms=["chardonnay", "blanco fermentado barrica", "blanco crianza"],
                priority=1
            ),
        ],
        
        # === MEAT ===
        ("meat", "grilled"): [
            WineRecommendation(
                style=WineStyle.RED_MEDIUM,
                grape_varieties=["tempranillo"],
                regions=["Rioja", "Ribera del Duero"],
                wine_type="tinto",
                description="Classic: grilled steak + Tempranillo Crianza",
                search_terms=["tempranillo", "crianza", "rioja", "ribera"],
                priority=1
            ),
            WineRecommendation(
                style=WineStyle.RED_FULL,
                grape_varieties=["garnacha", "carinena"],
                regions=["Priorat"],
                wine_type="tinto",
                description="For rich meat - powerful Priorat",
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
                description="Roasted meat + aged Tempranillo - perfect",
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
                description="Stewed meat needs rich wine with tannins",
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
                description="Spicy meat loves fruity Garnacha",
                search_terms=["garnacha", "campo de borja"],
                priority=1
            ),
        ],
        ("meat", "tomato"): [
            WineRecommendation(
                style=WineStyle.RED_MEDIUM,
                grape_varieties=["tempranillo", "garnacha"],
                regions=["Rioja", "Navarra"],
                wine_type="tinto",
                description="Tomato sauce pairs well with Crianza",
                search_terms=["crianza", "tinto"],
                priority=1
            ),
        ],
        ("meat", "creamy"): [
            WineRecommendation(
                style=WineStyle.RED_LIGHT,
                grape_varieties=["mencia", "tempranillo"],
                regions=["Bierzo", "Rioja"],
                wine_type="tinto",
                description="Creamy sauce needs softer red wine",
                search_terms=["mencia", "tinto joven"],
                priority=1
            ),
        ],
        
        # === POULTRY ===
        ("poultry", "grilled"): [
            WineRecommendation(
                style=WineStyle.RED_LIGHT,
                grape_varieties=["mencia", "garnacha"],
                regions=["Bierzo", "Navarra"],
                wine_type="tinto",
                description="Grilled poultry loves light fruity reds",
                search_terms=["mencia", "garnacha", "tinto joven"],
                priority=1
            ),
            WineRecommendation(
                style=WineStyle.WHITE_FULL,
                grape_varieties=["chardonnay", "godello"],
                regions=["Penedes", "Valdeorras"],
                wine_type="blanco",
                description="Oaked white is elegant with grilled chicken",
                search_terms=["chardonnay", "godello", "blanco barrica"],
                priority=2
            ),
        ],
        ("poultry", "roasted"): [
            WineRecommendation(
                style=WineStyle.RED_MEDIUM,
                grape_varieties=["tempranillo", "garnacha"],
                regions=["Rioja", "Navarra"],
                wine_type="tinto",
                description="Roast chicken pairs with medium reds",
                search_terms=["crianza", "tempranillo", "garnacha"],
                priority=1
            ),
        ],
        ("poultry", "creamy"): [
            WineRecommendation(
                style=WineStyle.WHITE_FULL,
                grape_varieties=["chardonnay", "viura"],
                regions=["Penedes", "Rioja"],
                wine_type="blanco",
                description="Creamy chicken needs rich oaked white",
                search_terms=["chardonnay", "blanco crianza"],
                priority=1
            ),
        ],
        
        # === VEGETABLES ===
        ("vegetables", "grilled"): [
            WineRecommendation(
                style=WineStyle.ROSE,
                grape_varieties=["garnacha", "tempranillo"],
                regions=["Navarra", "Rioja"],
                wine_type="rosado",
                description="Rose is perfect with grilled vegetables",
                search_terms=["rosado", "garnacha"],
                priority=1
            ),
        ],
        ("vegetables", "steamed"): [
            WineRecommendation(
                style=WineStyle.WHITE_LIGHT,
                grape_varieties=["verdejo", "albarino"],
                regions=["Rueda", "Rias Baixas"],
                wine_type="blanco",
                description="Light white for delicate steamed veggies",
                search_terms=["verdejo", "albarino", "blanco"],
                priority=1
            ),
        ],
        ("vegetables", "tomato"): [
            WineRecommendation(
                style=WineStyle.ROSE,
                grape_varieties=["garnacha"],
                regions=["Navarra", "Cigales"],
                wine_type="rosado",
                description="Tomato dishes pair beautifully with rose",
                search_terms=["rosado", "garnacha"],
                priority=1
            ),
        ],
        
        # === PASTA ===
        ("pasta", "tomato"): [
            WineRecommendation(
                style=WineStyle.RED_MEDIUM,
                grape_varieties=["tempranillo", "garnacha"],
                regions=["Rioja", "Navarra"],
                wine_type="tinto",
                description="Tomato pasta loves Spanish Crianza",
                search_terms=["crianza", "tempranillo", "tinto"],
                priority=1
            ),
        ],
        ("pasta", "creamy"): [
            WineRecommendation(
                style=WineStyle.WHITE_FULL,
                grape_varieties=["chardonnay", "godello"],
                regions=["Penedes", "Valdeorras"],
                wine_type="blanco",
                description="Rich creamy pasta needs oaked white",
                search_terms=["chardonnay", "godello", "blanco barrica"],
                priority=1
            ),
        ],
        
        # === CHEESE ===
        ("cheese", "grilled"): [
            WineRecommendation(
                style=WineStyle.RED_LIGHT,
                grape_varieties=["garnacha", "tempranillo"],
                regions=["Navarra", "Rioja"],
                wine_type="tinto",
                description="Grilled cheese with fruity young red",
                search_terms=["tinto joven", "garnacha"],
                priority=1
            ),
        ],
    }
    
    # Default recommendations by dish type
    DEFAULT_RECOMMENDATIONS = {
        "fish": [
            WineRecommendation(
                style=WineStyle.WHITE_LIGHT,
                grape_varieties=["albarino", "verdejo"],
                regions=["Rias Baixas", "Rueda"],
                wine_type="blanco",
                description="Fresh white wine for fish",
                search_terms=["blanco", "albarino", "verdejo"],
                priority=1
            ),
        ],
        "meat": [
            WineRecommendation(
                style=WineStyle.RED_MEDIUM,
                grape_varieties=["tempranillo"],
                regions=["Rioja", "Ribera del Duero"],
                wine_type="tinto",
                description="Red Tempranillo - classic with meat",
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
                description="Light red pairs well with poultry",
                search_terms=["tinto joven", "mencia", "garnacha"],
                priority=1
            ),
        ],
        "vegetables": [
            WineRecommendation(
                style=WineStyle.WHITE_LIGHT,
                grape_varieties=["verdejo"],
                regions=["Rueda"],
                wine_type="blanco",
                description="Fresh Verdejo white for vegetables",
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
                description="Versatile red for pasta",
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
                description="Aged red wine for cheese",
                search_terms=["crianza", "reserva"],
                priority=1
            ),
        ],
    }
    
    MEAL_TIME_MODIFIERS = {
        "lunch": {
            "prefer_light": True,
            "avoid_full_bodied": True,
            "description": "Lighter wines for midday meals"
        },
        "dinner": {
            "prefer_light": False,
            "avoid_full_bodied": False,
            "description": "Fuller wines for evening dining"
        },
        "aperitivo": {
            "prefer_sparkling": True,
            "prefer_light": True,
            "description": "Sparkling and light wines to start"
        },
    }
    
    CUISINE_MODIFIERS = {
        "spanish": {
            "preferred_regions": ["Rioja", "Ribera del Duero", "Rias Baixas"],
            "description": "Spanish cuisine + Spanish wine - perfect match"
        },
        "italian": {
            "prefer_acidic": True,
            "description": "Italian food needs wines with good acidity"
        },
        "asian": {
            "prefer_aromatic": True,
            "prefer_off_dry": True,
            "description": "Asian cuisine pairs with aromatic wines"
        },
        "indian": {
            "prefer_fruity": True,
            "avoid_tannic": True,
            "description": "Spicy Indian food needs fruity wines"
        },
        "mediterranean": {
            "preferred_regions": ["Penedes", "Priorat", "Navarra"],
            "description": "Mediterranean cuisine loves local wines"
        },
        "bbq": {
            "prefer_full_bodied": True,
            "description": "BBQ needs bold wines with character"
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
        """Get wine recommendations"""
        recommendations = []
        
        # 1. Find exact match (dish + cooking method)
        if cooking_method:
            key = (dish, cooking_method)
            if key in self.PAIRING_MATRIX:
                recommendations = self.PAIRING_MATRIX[key].copy()
        
        # 2. Fallback to defaults by dish type
        if not recommendations and dish in self.DEFAULT_RECOMMENDATIONS:
            recommendations = self.DEFAULT_RECOMMENDATIONS[dish].copy()
        
        # 3. Apply meal time modifiers
        if meal_time and meal_time in self.MEAL_TIME_MODIFIERS:
            modifier = self.MEAL_TIME_MODIFIERS[meal_time]
            
            # For aperitivo, add sparkling at the top
            if modifier.get("prefer_sparkling"):
                sparkling_rec = WineRecommendation(
                    style=WineStyle.SPARKLING,
                    grape_varieties=["macabeo", "xarello", "parellada"],
                    regions=["Penedes"],
                    wine_type="cava",
                    description="Cava - perfect choice for aperitivo",
                    search_terms=["cava", "brut"],
                    priority=0
                )
                recommendations.insert(0, sparkling_rec)
            
            # For lunch, lower priority of full-bodied wines
            if modifier.get("avoid_full_bodied"):
                for rec in recommendations:
                    if rec.style in [WineStyle.RED_FULL, WineStyle.WHITE_FULL]:
                        rec.priority += 2
        
        # 4. Sort by priority
        recommendations.sort(key=lambda x: x.priority)
        
        return recommendations[:max_results]
    
    def get_search_queries(self, recommendations: list[WineRecommendation]) -> list[str]:
        """Get search queries for stores"""
        queries = []
        for rec in recommendations:
            for region in rec.regions[:1]:
                queries.append(f"vino {rec.wine_type} {region}")
            
            for grape in rec.grape_varieties[:1]:
                queries.append(f"vino {grape}")
            
            for term in rec.search_terms[:2]:
                if term not in queries:
                    queries.append(f"vino {term}")
        
        return list(dict.fromkeys(queries))


if __name__ == "__main__":
    sommelier = SommelierEngine()
    
    recs = sommelier.get_recommendations(
        dish="fish",
        cooking_method="grilled",
        meal_time="dinner"
    )
    
    print("Wine recommendations for grilled fish dinner:\n")
    for i, rec in enumerate(recs, 1):
        print(f"{i}. {rec.style.value}")
        print(f"   Grapes: {', '.join(rec.grape_varieties)}")
        print(f"   Regions: {', '.join(rec.regions)}")
        print(f"   {rec.description}\n")
    
    print("Search queries:", sommelier.get_search_queries(recs))
