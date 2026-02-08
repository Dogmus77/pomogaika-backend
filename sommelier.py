"""
Wine Sommelier Engine
Expert wine pairing system with multi-language support

Core principles:
1. Wine intensity = dish intensity
2. Cooking method matters more than the protein
3. Sauce determines wine choice
4. Regional pairings (local food + local wine)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import copy


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
    BAKED = "baked"


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


# =============================================================================
# TRANSLATIONS — all sommelier texts in 5 languages (en is key / default)
# =============================================================================

TRANSLATIONS = {
    # --- Pairing descriptions ---
    "Fresh white with minerality enhances raw fish": {
        "ru": "Свежее белое с минеральностью раскроет сырую рыбу",
        "uk": "Свіже біле з мінеральністю розкриє сиру рибу",
        "be": "Свежае белае з мінеральнасцю раскрые сырую рыбу",
        "es": "Un blanco fresco y mineral realza el pescado crudo",
    },
    "Cava freshness is classic with raw fish": {
        "ru": "Свежесть Кавы — классика с сырой рыбой",
        "uk": "Свіжість Кави — класика з сирою рибою",
        "be": "Свежасць Кавы — класіка з сырой рыбай",
        "es": "La frescura del Cava es un clásico con pescado crudo",
    },
    "Delicate steamed fish needs an elegant wine": {
        "ru": "Деликатная рыба на пару требует элегантного вина",
        "uk": "Делікатна риба на парі потребує елегантного вина",
        "be": "Далікатная рыба на пары патрабуе элегантнага віна",
        "es": "El pescado al vapor necesita un vino elegante",
    },
    "Grilling adds intensity - needs fuller white": {
        "ru": "Гриль добавляет интенсивности — нужно полнотелое белое",
        "uk": "Гриль додає інтенсивності — потрібне повнотіле біле",
        "be": "Грыль дадае інтэнсіўнасці — трэба паўнацелае белае",
        "es": "La parrilla añade intensidad — necesita un blanco con cuerpo",
    },
    "Rose is versatile with grilled fish": {
        "ru": "Розовое универсально с рыбой на гриле",
        "uk": "Розове універсальне з рибою на грилі",
        "be": "Ружовае ўніверсальнае з рыбай на грылі",
        "es": "El rosado es versátil con pescado a la parrilla",
    },
    "Tomato sauce needs wine with good acidity": {
        "ru": "Томатный соус требует вина с хорошей кислотностью",
        "uk": "Томатний соус потребує вина з гарною кислотністю",
        "be": "Таматны соус патрабуе віна з добрай кіслотнасцю",
        "es": "La salsa de tomate necesita un vino con buena acidez",
    },
    "Light Mencia - bold but successful pairing": {
        "ru": "Лёгкая Менсия — смелый, но удачный выбор",
        "uk": "Легка Менсія — сміливий, але вдалий вибір",
        "be": "Лёгкая Менсія — смелы, але ўдалы выбар",
        "es": "Mencía ligero — un maridaje atrevido pero exitoso",
    },
    "Creamy sauce needs oaked white with body": {
        "ru": "Сливочный соус требует выдержанного белого с телом",
        "uk": "Вершковий соус потребує витриманого білого з тілом",
        "be": "Смятанкавы соус патрабуе вытрыманага белага з целам",
        "es": "La salsa cremosa necesita un blanco con barrica y cuerpo",
    },
    "Baked fish needs fuller white with body": {
        "ru": "Запечённая рыба требует полнотелого белого",
        "uk": "Запечена риба потребує повнотілого білого",
        "be": "Запечаная рыба патрабуе паўнацелага белага",
        "es": "El pescado al horno necesita un blanco con cuerpo",
    },
    "Classic: grilled steak + Tempranillo Crianza": {
        "ru": "Классика: стейк на гриле + Темпранильо Крианса",
        "uk": "Класика: стейк на грилі + Темпранільо Кріанса",
        "be": "Класіка: стэйк на грылі + Тэмпранілья Крыянса",
        "es": "Clásico: chuletón a la brasa + Tempranillo Crianza",
    },
    "For rich meat - powerful Priorat": {
        "ru": "Для насыщенного мяса — мощный Приорат",
        "uk": "Для насиченого м'яса — потужний Пріорат",
        "be": "Для насычанага мяса — магутны Прыярат",
        "es": "Para carne rica — un potente Priorat",
    },
    "Roasted meat + aged Tempranillo - perfect": {
        "ru": "Запечённое мясо + выдержанное Темпранильо — идеально",
        "uk": "Запечене м'ясо + витримане Темпранільо — ідеально",
        "be": "Запечанае мяса + вытрыманае Тэмпранілья — ідэальна",
        "es": "Carne asada + Tempranillo envejecido — perfecto",
    },
    "Stewed meat needs rich wine with tannins": {
        "ru": "Тушёное мясо требует насыщенного вина с танинами",
        "uk": "Тушковане м'ясо потребує насиченого вина з танінами",
        "be": "Тушанае мяса патрабуе насычанага віна з танінамі",
        "es": "El estofado necesita un vino rico con taninos",
    },
    "Spicy meat loves fruity Garnacha": {
        "ru": "Острое мясо любит фруктовую Гарначу",
        "uk": "Гостре м'ясо любить фруктову Гарначу",
        "be": "Вострае мяса любіць фруктовую Гарначу",
        "es": "La carne picante adora la Garnacha afrutada",
    },
    "Tomato sauce pairs well with Crianza": {
        "ru": "Томатный соус отлично сочетается с Крианса",
        "uk": "Томатний соус чудово поєднується з Кріанса",
        "be": "Таматны соус выдатна спалучаецца з Крыянса",
        "es": "La salsa de tomate marida bien con un Crianza",
    },
    "Creamy sauce needs softer red wine": {
        "ru": "Сливочный соус требует мягкого красного вина",
        "uk": "Вершковий соус потребує м'якого червоного вина",
        "be": "Смятанкавы соус патрабуе мяккага чырвонага віна",
        "es": "La salsa cremosa necesita un tinto suave",
    },
    "Raw meat like tartare needs light elegant red": {
        "ru": "Сырое мясо, как тартар, требует лёгкого элегантного красного",
        "uk": "Сире м'ясо, як тартар, потребує легкого елегантного червоного",
        "be": "Сырое мяса, як тартар, патрабуе лёгкага элегантнага чырвонага",
        "es": "La carne cruda como el tartar necesita un tinto ligero y elegante",
    },
    "Baked meat pairs beautifully with aged Tempranillo": {
        "ru": "Запечённое мясо прекрасно сочетается с выдержанным Темпранильо",
        "uk": "Запечене м'ясо чудово поєднується з витриманим Темпранільо",
        "be": "Запечанае мяса цудоўна спалучаецца з вытрыманым Тэмпранілья",
        "es": "La carne al horno marida con un Tempranillo envejecido",
    },
    "Grilled poultry loves light fruity reds": {
        "ru": "Птица на гриле любит лёгкое фруктовое красное",
        "uk": "Птиця на грилі любить легке фруктове червоне",
        "be": "Птушка на грылі любіць лёгкае фруктовае чырвонае",
        "es": "Las aves a la parrilla adoran los tintos ligeros y afrutados",
    },
    "Oaked white is elegant with grilled chicken": {
        "ru": "Выдержанное в дубе белое элегантно с курицей гриль",
        "uk": "Витримане в дубі біле елегантне з курчам на грилі",
        "be": "Вытрыманае ў дубе белае элегантнае з курыцай грыль",
        "es": "Un blanco con barrica es elegante con pollo a la parrilla",
    },
    "Roast chicken pairs with medium reds": {
        "ru": "Запечённая курица сочетается со средним красным",
        "uk": "Запечена курка поєднується із середнім червоним",
        "be": "Запечаная курыца спалучаецца з сярэднім чырвоным",
        "es": "El pollo asado marida con tintos de cuerpo medio",
    },
    "Creamy chicken needs rich oaked white": {
        "ru": "Курица в сливках требует богатого белого с выдержкой",
        "uk": "Курка у вершках потребує багатого білого з витримкою",
        "be": "Курыца ў смятанцы патрабуе багатага белага з вытрымкай",
        "es": "El pollo en crema necesita un blanco rico con barrica",
    },
    "Baked poultry pairs with rich oaked white": {
        "ru": "Запечённая птица сочетается с богатым выдержанным белым",
        "uk": "Запечена птиця поєднується з багатим витриманим білим",
        "be": "Запечаная птушка спалучаецца з багатым вытрыманым белым",
        "es": "Las aves al horno maridan con un blanco rico con barrica",
    },
    "Fresh salads pair with crisp white wines": {
        "ru": "Свежие салаты сочетаются с хрустящим белым вином",
        "uk": "Свіжі салати поєднуються з хрустким білим вином",
        "be": "Свежыя салаты спалучаюцца з хрумсткім белым віном",
        "es": "Las ensaladas frescas maridan con blancos crujientes",
    },
    "Rose is perfect with grilled vegetables": {
        "ru": "Розовое идеально с овощами на гриле",
        "uk": "Розове ідеальне з овочами на грилі",
        "be": "Ружовае ідэальнае з гародніной на грылі",
        "es": "El rosado es perfecto con verduras a la parrilla",
    },
    "Light white for delicate steamed veggies": {
        "ru": "Лёгкое белое для деликатных овощей на пару",
        "uk": "Легке біле для делікатних овочів на парі",
        "be": "Лёгкае белае для далікатнай гародніны на пары",
        "es": "Un blanco ligero para verduras al vapor",
    },
    "Tomato dishes pair beautifully with rose": {
        "ru": "Томатные блюда прекрасно сочетаются с розовым",
        "uk": "Томатні страви чудово поєднуються з розовим",
        "be": "Таматныя стравы цудоўна спалучаюцца з ружовым",
        "es": "Los platos con tomate maridan perfectamente con rosado",
    },
    "Baked vegetables love a good rose": {
        "ru": "Запечённые овощи любят хорошее розовое",
        "uk": "Запечені овочі люблять добре розове",
        "be": "Запечаная гародніна любіць добрае ружовае",
        "es": "Las verduras al horno adoran un buen rosado",
    },
    "Tomato pasta loves Spanish Crianza": {
        "ru": "Паста с томатом любит испанское Крианса",
        "uk": "Паста з томатом любить іспанське Кріанса",
        "be": "Паста з таматам любіць іспанскае Крыянса",
        "es": "La pasta con tomate adora un Crianza español",
    },
    "Rich creamy pasta needs oaked white": {
        "ru": "Паста в сливочном соусе требует белого с выдержкой в дубе",
        "uk": "Паста у вершковому соусі потребує білого з витримкою в дубі",
        "be": "Паста ў смятанкавым соусе патрабуе белага з вытрымкай у дубе",
        "es": "La pasta cremosa necesita un blanco con barrica",
    },
    "Baked pasta pairs with medium bodied red": {
        "ru": "Запечённая паста сочетается со средним красным",
        "uk": "Запечена паста поєднується із середнім червоним",
        "be": "Запечаная паста спалучаецца з сярэднім чырвоным",
        "es": "La pasta al horno marida con un tinto de cuerpo medio",
    },
    "Grilled cheese with fruity young red": {
        "ru": "Сыр на гриле с фруктовым молодым красным",
        "uk": "Сир на грилі з фруктовим молодим червоним",
        "be": "Сыр на грылі з фруктовым маладым чырвоным",
        "es": "Queso a la parrilla con un tinto joven afrutado",
    },
    # Default recommendations
    "Fresh white wine for fish": {
        "ru": "Свежее белое вино для рыбы",
        "uk": "Свіже біле вино для риби",
        "be": "Свежае белае віно для рыбы",
        "es": "Vino blanco fresco para pescado",
    },
    "Red Tempranillo - classic with meat": {
        "ru": "Красное Темпранильо — классика к мясу",
        "uk": "Червоне Темпранільо — класика до м'яса",
        "be": "Чырвонае Тэмпранілья — класіка да мяса",
        "es": "Tempranillo tinto — un clásico con carne",
    },
    "Light red pairs well with poultry": {
        "ru": "Лёгкое красное отлично подходит к птице",
        "uk": "Легке червоне чудово підходить до птиці",
        "be": "Лёгкае чырвонае выдатна падыходзіць да птушкі",
        "es": "Un tinto ligero marida bien con aves",
    },
    "Fresh Verdejo white for vegetables": {
        "ru": "Свежий белый Вердехо для овощей",
        "uk": "Свіжий білий Вердехо для овочів",
        "be": "Свежы белы Вердэхо для гародніны",
        "es": "Verdejo blanco fresco para verduras",
    },
    "Versatile red for pasta": {
        "ru": "Универсальное красное для пасты",
        "uk": "Універсальне червоне для пасти",
        "be": "Універсальнае чырвонае для пасты",
        "es": "Un tinto versátil para pasta",
    },
    "Aged red wine for cheese": {
        "ru": "Выдержанное красное вино для сыра",
        "uk": "Витримане червоне вино для сиру",
        "be": "Вытрыманае чырвонае віно для сыру",
        "es": "Vino tinto envejecido para queso",
    },
    # Meal time specials
    "Cava - perfect choice for aperitivo": {
        "ru": "Кава — идеальный выбор для аперитива",
        "uk": "Кава — ідеальний вибір для аперитиву",
        "be": "Кава — ідэальны выбар для аперытыву",
        "es": "Cava — la elección perfecta para el aperitivo",
    },
    "Rich aged red wine - perfect digestif to end the meal": {
        "ru": "Насыщенное выдержанное красное — идеальный дижестив",
        "uk": "Насичене витримане червоне — ідеальний дижестив",
        "be": "Насычанае вытрыманае чырвонае — ідэальны дыжэстыў",
        "es": "Un tinto envejecido y rico — el digestivo perfecto",
    },
    # Expert notes (used by main.py get_expert_note)
    "Classic Rioja - balance of fruit and oak": {
        "ru": "Классическая Риоха — баланс фруктов и дуба",
        "uk": "Класична Ріоха — баланс фруктів і дуба",
        "be": "Класічная Рыёха — баланс фруктаў і дуба",
        "es": "Rioja clásica — equilibrio de fruta y roble",
    },
    "Ribera del Duero - intensity and depth": {
        "ru": "Рибера дель Дуэро — интенсивность и глубина",
        "uk": "Рібера дель Дуеро — інтенсивність і глибина",
        "be": "Рыбера дэль Дуэра — інтэнсіўнасць і глыбіня",
        "es": "Ribera del Duero — intensidad y profundidad",
    },
    "Albarino from Galicia - ocean minerality": {
        "ru": "Альбариньо из Галисии — минеральность океана",
        "uk": "Альбаріньо з Галісії — мінеральність океану",
        "be": "Альбарынья з Галісіі — мінеральнасць акіяна",
        "es": "Albariño de Galicia — mineralidad del océano",
    },
    "Verdejo - herbs and citrus": {
        "ru": "Вердехо — травы и цитрусы",
        "uk": "Вердехо — трави та цитруси",
        "be": "Вердэхо — травы і цытрусы",
        "es": "Verdejo — hierbas y cítricos",
    },
    "Priorat - power and concentration": {
        "ru": "Приорат — мощь и концентрация",
        "uk": "Пріорат — потужність і концентрація",
        "be": "Прыярат — моц і канцэнтрацыя",
        "es": "Priorat — potencia y concentración",
    },
    "Monastrell - prune and spice": {
        "ru": "Монастрель — чернослив и специи",
        "uk": "Монастрель — чорнослив і спеції",
        "be": "Манастрэль — чарнаслів і спецыі",
        "es": "Monastrell — ciruela y especias",
    },
    "Mencia - elegance of Bierzo": {
        "ru": "Менсия — элегантность Бьерсо",
        "uk": "Менсія — елегантність Б'єрсо",
        "be": "Менсія — элегантнасць Б'ерса",
        "es": "Mencía — elegancia del Bierzo",
    },
    "Navarra - capital of rose wines": {
        "ru": "Наварра — столица розовых вин",
        "uk": "Наварра — столиця рожевих вин",
        "be": "Навара — сталіца ружовых він",
        "es": "Navarra — capital de los rosados",
    },
    "Penedes - home of Spanish Cava": {
        "ru": "Пенедес — родина испанской Кавы",
        "uk": "Пенедес — батьківщина іспанської Кави",
        "be": "Пенедэс — радзіма іспанскай Кавы",
        "es": "Penedés — hogar del Cava español",
    },
    "Spanish sparkling - celebration in a glass": {
        "ru": "Испанское игристое — праздник в бокале",
        "uk": "Іспанське ігристе — свято в келиху",
        "be": "Іспанскае ігрыстае — свята ў келіху",
        "es": "Espumoso español — una celebración en copa",
    },
    "Excellent choice for your dish": {
        "ru": "Отличный выбор для вашего блюда",
        "uk": "Чудовий вибір для вашої страви",
        "be": "Выдатны выбар для вашай стравы",
        "es": "Excelente elección para tu plato",
    },
}


def translate(text: str, lang: str) -> str:
    """Translate a description string to the given language.
    Falls back to English (original) if lang='en' or translation is missing."""
    if lang == "en" or lang not in ("ru", "uk", "be", "es"):
        return text
    entry = TRANSLATIONS.get(text)
    if entry and lang in entry:
        return entry[lang]
    return text


class SommelierEngine:
    """Expert sommelier system"""

    SPANISH_GRAPES = {
        "albarino": {"type": "white", "body": "light", "regions": ["Rias Baixas"]},
        "verdejo": {"type": "white", "body": "light", "regions": ["Rueda"]},
        "godello": {"type": "white", "body": "medium", "regions": ["Valdeorras", "Bierzo"]},
        "viura": {"type": "white", "body": "light", "regions": ["Rioja"]},
        "chardonnay": {"type": "white", "body": "full", "regions": ["Penedes", "Navarra"]},
        "macabeo": {"type": "white", "body": "light", "regions": ["Penedes", "Rioja"]},
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
            WineRecommendation(WineStyle.WHITE_LIGHT, ["albarino", "verdejo"], ["Rias Baixas", "Rueda"], "blanco", "Fresh white with minerality enhances raw fish", ["albarino", "verdejo", "blanco"], 1),
            WineRecommendation(WineStyle.SPARKLING, ["macabeo", "xarello", "parellada"], ["Penedes"], "cava", "Cava freshness is classic with raw fish", ["cava", "brut"], 2),
        ],
        ("fish", "steamed"): [
            WineRecommendation(WineStyle.WHITE_LIGHT, ["albarino", "godello"], ["Rias Baixas", "Valdeorras"], "blanco", "Delicate steamed fish needs an elegant wine", ["albarino", "godello", "blanco"], 1),
        ],
        ("fish", "grilled"): [
            WineRecommendation(WineStyle.WHITE_FULL, ["godello", "chardonnay"], ["Valdeorras", "Penedes"], "blanco", "Grilling adds intensity - needs fuller white", ["godello", "chardonnay", "fermentado barrica"], 1),
            WineRecommendation(WineStyle.ROSE, ["garnacha", "tempranillo"], ["Navarra", "Rioja"], "rosado", "Rose is versatile with grilled fish", ["rosado", "garnacha"], 2),
        ],
        ("fish", "tomato"): [
            WineRecommendation(WineStyle.ROSE, ["garnacha", "tempranillo"], ["Navarra", "Cigales"], "rosado", "Tomato sauce needs wine with good acidity", ["rosado"], 1),
            WineRecommendation(WineStyle.RED_LIGHT, ["mencia"], ["Bierzo"], "tinto", "Light Mencia - bold but successful pairing", ["mencia", "bierzo", "tinto joven"], 2),
        ],
        ("fish", "creamy"): [
            WineRecommendation(WineStyle.WHITE_FULL, ["chardonnay", "viura"], ["Penedes", "Rioja"], "blanco", "Creamy sauce needs oaked white with body", ["chardonnay", "blanco fermentado barrica", "blanco crianza"], 1),
        ],
        ("fish", "baked"): [
            WineRecommendation(WineStyle.WHITE_FULL, ["godello", "chardonnay"], ["Valdeorras", "Penedes"], "blanco", "Baked fish needs fuller white with body", ["godello", "chardonnay", "blanco barrica"], 1),
        ],

        # === MEAT ===
        ("meat", "raw"): [
            WineRecommendation(WineStyle.RED_LIGHT, ["mencia", "garnacha"], ["Bierzo", "Navarra"], "tinto", "Raw meat like tartare needs light elegant red", ["mencia", "tinto joven"], 1),
        ],
        ("meat", "grilled"): [
            WineRecommendation(WineStyle.RED_MEDIUM, ["tempranillo"], ["Rioja", "Ribera del Duero"], "tinto", "Classic: grilled steak + Tempranillo Crianza", ["tempranillo", "crianza", "rioja", "ribera"], 1),
            WineRecommendation(WineStyle.RED_FULL, ["garnacha", "carinena"], ["Priorat"], "tinto", "For rich meat - powerful Priorat", ["priorat", "garnacha"], 2),
        ],
        ("meat", "roasted"): [
            WineRecommendation(WineStyle.RED_MEDIUM, ["tempranillo"], ["Rioja", "Ribera del Duero", "Toro"], "tinto", "Roasted meat + aged Tempranillo - perfect", ["reserva", "gran reserva", "tempranillo"], 1),
        ],
        ("meat", "stewed"): [
            WineRecommendation(WineStyle.RED_FULL, ["monastrell", "garnacha"], ["Jumilla", "Yecla", "Priorat"], "tinto", "Stewed meat needs rich wine with tannins", ["monastrell", "jumilla", "garnacha"], 1),
        ],
        ("meat", "spicy"): [
            WineRecommendation(WineStyle.RED_MEDIUM, ["garnacha"], ["Campo de Borja", "Navarra"], "tinto", "Spicy meat loves fruity Garnacha", ["garnacha", "campo de borja"], 1),
        ],
        ("meat", "tomato"): [
            WineRecommendation(WineStyle.RED_MEDIUM, ["tempranillo", "garnacha"], ["Rioja", "Navarra"], "tinto", "Tomato sauce pairs well with Crianza", ["crianza", "tinto"], 1),
        ],
        ("meat", "creamy"): [
            WineRecommendation(WineStyle.RED_LIGHT, ["mencia", "tempranillo"], ["Bierzo", "Rioja"], "tinto", "Creamy sauce needs softer red wine", ["mencia", "tinto joven"], 1),
        ],
        ("meat", "baked"): [
            WineRecommendation(WineStyle.RED_MEDIUM, ["tempranillo", "garnacha"], ["Rioja", "Ribera del Duero"], "tinto", "Baked meat pairs beautifully with aged Tempranillo", ["crianza", "reserva", "tempranillo"], 1),
        ],

        # === POULTRY ===
        ("poultry", "grilled"): [
            WineRecommendation(WineStyle.RED_LIGHT, ["mencia", "garnacha"], ["Bierzo", "Navarra"], "tinto", "Grilled poultry loves light fruity reds", ["mencia", "garnacha", "tinto joven"], 1),
            WineRecommendation(WineStyle.WHITE_FULL, ["chardonnay", "godello"], ["Penedes", "Valdeorras"], "blanco", "Oaked white is elegant with grilled chicken", ["chardonnay", "godello", "blanco barrica"], 2),
        ],
        ("poultry", "roasted"): [
            WineRecommendation(WineStyle.RED_MEDIUM, ["tempranillo", "garnacha"], ["Rioja", "Navarra"], "tinto", "Roast chicken pairs with medium reds", ["crianza", "tempranillo", "garnacha"], 1),
        ],
        ("poultry", "creamy"): [
            WineRecommendation(WineStyle.WHITE_FULL, ["chardonnay", "viura"], ["Penedes", "Rioja"], "blanco", "Creamy chicken needs rich oaked white", ["chardonnay", "blanco crianza"], 1),
        ],
        ("poultry", "baked"): [
            WineRecommendation(WineStyle.WHITE_FULL, ["chardonnay", "godello"], ["Penedes", "Valdeorras"], "blanco", "Baked poultry pairs with rich oaked white", ["chardonnay", "godello", "blanco barrica"], 1),
        ],

        # === VEGETABLES ===
        ("vegetables", "raw"): [
            WineRecommendation(WineStyle.WHITE_LIGHT, ["verdejo", "albarino"], ["Rueda", "Rias Baixas"], "blanco", "Fresh salads pair with crisp white wines", ["verdejo", "albarino", "blanco"], 1),
        ],
        ("vegetables", "grilled"): [
            WineRecommendation(WineStyle.ROSE, ["garnacha", "tempranillo"], ["Navarra", "Rioja"], "rosado", "Rose is perfect with grilled vegetables", ["rosado", "garnacha"], 1),
        ],
        ("vegetables", "steamed"): [
            WineRecommendation(WineStyle.WHITE_LIGHT, ["verdejo", "albarino"], ["Rueda", "Rias Baixas"], "blanco", "Light white for delicate steamed veggies", ["verdejo", "albarino", "blanco"], 1),
        ],
        ("vegetables", "tomato"): [
            WineRecommendation(WineStyle.ROSE, ["garnacha"], ["Navarra", "Cigales"], "rosado", "Tomato dishes pair beautifully with rose", ["rosado", "garnacha"], 1),
        ],
        ("vegetables", "baked"): [
            WineRecommendation(WineStyle.ROSE, ["garnacha", "tempranillo"], ["Navarra", "Rioja"], "rosado", "Baked vegetables love a good rose", ["rosado", "garnacha"], 1),
        ],

        # === PASTA ===
        ("pasta", "tomato"): [
            WineRecommendation(WineStyle.RED_MEDIUM, ["tempranillo", "garnacha"], ["Rioja", "Navarra"], "tinto", "Tomato pasta loves Spanish Crianza", ["crianza", "tempranillo", "tinto"], 1),
        ],
        ("pasta", "creamy"): [
            WineRecommendation(WineStyle.WHITE_FULL, ["chardonnay", "godello"], ["Penedes", "Valdeorras"], "blanco", "Rich creamy pasta needs oaked white", ["chardonnay", "godello", "blanco barrica"], 1),
        ],
        ("pasta", "baked"): [
            WineRecommendation(WineStyle.RED_MEDIUM, ["tempranillo", "garnacha"], ["Rioja", "Navarra"], "tinto", "Baked pasta pairs with medium bodied red", ["crianza", "tinto"], 1),
        ],

        # === CHEESE ===
        ("cheese", "grilled"): [
            WineRecommendation(WineStyle.RED_LIGHT, ["garnacha", "tempranillo"], ["Navarra", "Rioja"], "tinto", "Grilled cheese with fruity young red", ["tinto joven", "garnacha"], 1),
        ],
    }

    DEFAULT_RECOMMENDATIONS = {
        "fish": [
            WineRecommendation(WineStyle.WHITE_LIGHT, ["albarino", "verdejo"], ["Rias Baixas", "Rueda"], "blanco", "Fresh white wine for fish", ["blanco", "albarino", "verdejo"], 1),
        ],
        "meat": [
            WineRecommendation(WineStyle.RED_MEDIUM, ["tempranillo"], ["Rioja", "Ribera del Duero"], "tinto", "Red Tempranillo - classic with meat", ["tinto", "crianza", "tempranillo", "rioja"], 1),
        ],
        "poultry": [
            WineRecommendation(WineStyle.RED_LIGHT, ["mencia", "garnacha"], ["Bierzo", "Navarra"], "tinto", "Light red pairs well with poultry", ["tinto joven", "mencia", "garnacha"], 1),
        ],
        "vegetables": [
            WineRecommendation(WineStyle.WHITE_LIGHT, ["verdejo"], ["Rueda"], "blanco", "Fresh Verdejo white for vegetables", ["verdejo", "rueda", "blanco"], 1),
        ],
        "pasta": [
            WineRecommendation(WineStyle.RED_LIGHT, ["tempranillo"], ["Rioja"], "tinto", "Versatile red for pasta", ["tinto joven"], 1),
        ],
        "cheese": [
            WineRecommendation(WineStyle.RED_MEDIUM, ["tempranillo"], ["Rioja", "Ribera del Duero"], "tinto", "Aged red wine for cheese", ["crianza", "reserva"], 1),
        ],
    }

    MEAL_TIME_MODIFIERS = {
        "lunch": {"prefer_light": True, "avoid_full_bodied": True},
        "dinner": {"prefer_light": False, "avoid_full_bodied": False},
        "aperitivo": {"prefer_sparkling": True, "prefer_light": True},
        "digestivo": {"prefer_full_bodied": True, "prefer_aged": True},
    }

    CUISINE_MODIFIERS = {
        "spanish": {"preferred_regions": ["Rioja", "Ribera del Duero", "Rias Baixas"]},
        "italian": {"prefer_acidic": True},
        "asian": {"prefer_aromatic": True, "prefer_off_dry": True},
        "other": {},
        "unknown": {},
    }

    def get_recommendations(
        self,
        dish: str,
        cooking_method: Optional[str] = None,
        meal_time: Optional[str] = None,
        cuisine: Optional[str] = None,
        lang: str = "en",
        max_results: int = 3
    ) -> list[WineRecommendation]:
        """Get wine recommendations with optional localization via lang param."""
        recommendations = []

        # 1. Exact match (dish + cooking method)
        if cooking_method:
            key = (dish, cooking_method)
            if key in self.PAIRING_MATRIX:
                recommendations = copy.deepcopy(self.PAIRING_MATRIX[key])

        # 2. Fallback to defaults
        if not recommendations and dish in self.DEFAULT_RECOMMENDATIONS:
            recommendations = copy.deepcopy(self.DEFAULT_RECOMMENDATIONS[dish])

        # 3. Meal time modifiers
        if meal_time and meal_time in self.MEAL_TIME_MODIFIERS:
            modifier = self.MEAL_TIME_MODIFIERS[meal_time]

            if modifier.get("prefer_sparkling"):
                recommendations.insert(0, WineRecommendation(
                    WineStyle.SPARKLING, ["macabeo", "xarello", "parellada"], ["Penedes"],
                    "cava", "Cava - perfect choice for aperitivo", ["cava", "brut"], 0
                ))

            if modifier.get("avoid_full_bodied"):
                for rec in recommendations:
                    if rec.style in [WineStyle.RED_FULL, WineStyle.WHITE_FULL]:
                        rec.priority += 2

            if modifier.get("prefer_full_bodied"):
                recommendations.insert(0, WineRecommendation(
                    WineStyle.RED_FULL, ["tempranillo", "monastrell"],
                    ["Rioja", "Ribera del Duero", "Jumilla"], "tinto",
                    "Rich aged red wine - perfect digestif to end the meal",
                    ["reserva", "gran reserva", "crianza"], 0
                ))

        # 4. Sort
        recommendations.sort(key=lambda x: x.priority)

        # 5. Translate descriptions to requested language
        if lang != "en":
            for rec in recommendations:
                rec.description = translate(rec.description, lang)

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

    for test_lang in ["en", "ru", "es"]:
        recs = sommelier.get_recommendations("fish", "grilled", "dinner", lang=test_lang)
        print(f"\n=== lang={test_lang} ===")
        for i, rec in enumerate(recs, 1):
            print(f"  {i}. {rec.description}")
