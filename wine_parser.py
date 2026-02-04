"""
Wine Parser PoC - Consum & Mercadona
Получение данных о винах из испанских супермаркетов
"""

import requests
import json
from dataclasses import dataclass, asdict
from typing import Optional
from enum import Enum


class WineType(Enum):
    TINTO = "tinto"
    BLANCO = "blanco"
    ROSADO = "rosado"
    ESPUMOSO = "espumoso"
    CAVA = "cava"


class Store(Enum):
    CONSUM = "consum"
    MERCADONA = "mercadona"


@dataclass
class Wine:
    """Унифицированная структура данных о вине"""
    id: str
    name: str
    brand: str
    price: float
    price_per_liter: float
    store: str
    url: str
    image_url: Optional[str] = None
    ean: Optional[str] = None  # Только Consum
    region: Optional[str] = None  # DO Rioja, Ribera del Duero, etc.
    wine_type: Optional[str] = None
    discount_price: Optional[float] = None
    discount_percent: Optional[int] = None


class ConsumParser:
    """
    Парсер для tienda.consum.es
    Использует REST API с привязкой к Codigo Postal
    """
    
    BASE_URL = "https://tienda.consum.es/api/rest/V1.0"
    
    def __init__(self, postal_code: str = "46001"):
        self.postal_code = postal_code
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
            "Accept": "application/json",
            "Accept-Language": "es-ES,es;q=0.9",
        })
    
    def search_wines(self, wine_type: WineType = WineType.TINTO, limit: int = 50) -> list[Wine]:
        """Поиск вин по типу"""
        query = f"vino {wine_type.value}"
        
        # New Consum API endpoint (changed from /catalog/product)
        url = f"{self.BASE_URL}/catalog/searcher/products"
        params = {
            "q": query,
            "limit": limit,
            "showRecommendations": "false",
            "showProducts": "true",
            "showRecipes": "false"
        }
        
        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            wines = []
            
            # Try different response structures
            products = []
            if isinstance(data, dict):
                # New structure: catalog is a dict with 'products' key inside
                catalog = data.get("catalog", {})
                
                if isinstance(catalog, dict):
                    products = catalog.get("products", [])
                elif isinstance(catalog, list):
                    products = catalog
                
                # Fallback to other keys
                if not products:
                    products = data.get("products", data.get("results", data.get("items", [])))
                    
            elif isinstance(data, list):
                products = data
            
            for item in products:
                wine = self._parse_product(item)
                if wine:
                    wines.append(wine)
            
            print(f"✅ Consum: {len(wines)} wines (from {len(products)} products)")
            return wines
            
        except requests.RequestException as e:
            print(f"❌ Consum API error: {e}")
            return []
        except Exception as e:
            print(f"❌ Consum parsing error: {e}")
            return []
    
    def _safe_get(self, data, key, default=None):
        """Safely get value from dict or list"""
        if isinstance(data, dict):
            return data.get(key, default)
        elif isinstance(data, list) and len(data) > 0:
            # If it's a list, try to get from first element
            if isinstance(data[0], dict):
                return data[0].get(key, default)
        return default
    
    def _parse_product(self, item: dict) -> Optional[Wine]:
        """Парсинг продукта в объект Wine"""
        try:
            # Handle both old and new API structures
            if isinstance(item, list):
                if len(item) == 0:
                    return None
                item = item[0] if isinstance(item[0], dict) else {"id": str(item[0])}
            
            # Базовые данные
            product_id = str(item.get("id", ""))
            
            # productData can be dict or list
            product_data = item.get("productData", {})
            if isinstance(product_data, list):
                product_data = product_data[0] if product_data else {}
            
            name = product_data.get("name", "") if isinstance(product_data, dict) else ""
            # Name could also be a dict in some cases
            if isinstance(name, dict):
                name = name.get("name", name.get("value", str(name)))
            name = str(name) if name else ""
            
            brand_data = product_data.get("brand", "") if isinstance(product_data, dict) else ""
            
            # Brand can be string or dict with 'name' key
            if isinstance(brand_data, dict):
                brand = brand_data.get("name", brand_data.get("id", ""))
            else:
                brand = str(brand_data) if brand_data else ""
            
            # Fallback: try direct fields if productData is empty
            if not name:
                fallback_name = item.get("name", item.get("displayName", item.get("title", "")))
                if isinstance(fallback_name, dict):
                    name = fallback_name.get("name", fallback_name.get("value", ""))
                else:
                    name = str(fallback_name) if fallback_name else ""
            if not brand:
                fallback_brand = item.get("brand", item.get("manufacturer", ""))
                if isinstance(fallback_brand, dict):
                    brand = fallback_brand.get("name", fallback_brand.get("id", ""))
                else:
                    brand = str(fallback_brand) if fallback_brand else ""
            
            # EAN код
            ean = product_data.get("ean", "") if isinstance(product_data, dict) else ""
            if isinstance(ean, dict):
                ean = ean.get("value", ean.get("code", ""))
            ean = str(ean) if ean else ""
            
            if not ean:
                fallback_ean = item.get("ean", item.get("gtin", ""))
                if isinstance(fallback_ean, dict):
                    ean = fallback_ean.get("value", fallback_ean.get("code", ""))
                else:
                    ean = str(fallback_ean) if fallback_ean else ""
            
            # Цены - handle different structures
            price_data = item.get("priceData", {})
            if isinstance(price_data, list):
                price_data = price_data[0] if price_data else {}
            
            # Debug price structure (removed)
            
            
            prices = price_data.get("prices", {}) if isinstance(price_data, dict) else {}
            if isinstance(prices, list):
                prices = prices[0] if prices else {}
            
            price = 0.0
            price_per_liter = 0.0
            
            if isinstance(prices, dict):
                # New structure: prices.value.centAmount
                value = prices.get("value", {})
                if isinstance(value, dict):
                    price = float(value.get("centAmount", 0) or 0)
                    price_per_liter = float(value.get("centUnitAmount", 0) or 0)
                
                # Fallback to old structure
                if price == 0:
                    price = float(prices.get("price", 0) or 0)
                if price_per_liter == 0:
                    price_per_liter = float(prices.get("pricePerUnit", 0) or 0)
            
            # Fallback price fields - check priceData directly
            if price == 0 and isinstance(price_data, dict):
                price = float(price_data.get("price", 0) or 0)
                if price == 0:
                    price = float(price_data.get("unitPrice", 0) or 0)
            
            # Fallback to item level
            if price == 0:
                price = float(item.get("price", item.get("unitPrice", 0)) or 0)
            if price_per_liter == 0:
                price_per_liter = float(item.get("pricePerUnit", item.get("referencePrice", 0)) or 0)
            
            # Skip if no valid price
            if price == 0:
                return None
            
            # Акционная цена
            discount_price = None
            discount_percent = None
            offers = price_data.get("offers", []) if isinstance(price_data, dict) else []
            if offers and isinstance(offers, list) and len(offers) > 0:
                offer = offers[0]
                if isinstance(offer, dict):
                    discount_price = float(offer.get("price", 0) or 0)
                    if price > 0 and discount_price > 0:
                        discount_percent = int((1 - discount_price / price) * 100)
            
            # URL и изображение
            slug = product_data.get("slug", "") if isinstance(product_data, dict) else ""
            if isinstance(slug, dict):
                slug = slug.get("value", slug.get("url", ""))
            slug = str(slug) if slug else ""
            
            if not slug:
                fallback_slug = item.get("slug", item.get("url", ""))
                if isinstance(fallback_slug, dict):
                    slug = fallback_slug.get("value", "")
                else:
                    slug = str(fallback_slug) if fallback_slug else ""
            
            url = f"https://tienda.consum.es/es/p/{slug}/{product_id}" if slug else f"https://tienda.consum.es/es/p/{product_id}"
            
            image_url = ""
            if isinstance(product_data, dict):
                img = product_data.get("imageURL", product_data.get("image", ""))
                if isinstance(img, dict):
                    image_url = img.get("url", img.get("src", ""))
                else:
                    image_url = str(img) if img else ""
            if not image_url:
                fallback_img = item.get("imageURL", item.get("image", item.get("thumbnail", "")))
                if isinstance(fallback_img, dict):
                    image_url = fallback_img.get("url", fallback_img.get("src", ""))
                else:
                    image_url = str(fallback_img) if fallback_img else ""
            
            # Определение региона из названия
            region = self._extract_region(name)
            
            return Wine(
                id=f"consum_{product_id}",
                name=name,
                brand=brand,
                price=price,
                price_per_liter=price_per_liter,
                store=Store.CONSUM.value,
                url=url,
                image_url=image_url,
                ean=ean,
                region=region,
                wine_type=self._extract_wine_type(name),
                discount_price=discount_price,
                discount_percent=discount_percent
            )
        except Exception as e:
            print(f"Error parsing Consum product: {e}")
            return None
    
    def _extract_region(self, name: str) -> Optional[str]:
        """Извлечение региона DO из названия"""
        regions = [
            "Rioja", "Ribera del Duero", "Rueda", "Rías Baixas",
            "Priorat", "Penedès", "Jumilla", "Toro", "Navarra",
            "La Mancha", "Valdepeñas", "Utiel-Requena", "Cariñena"
        ]
        name_lower = name.lower()
        for region in regions:
            if region.lower() in name_lower:
                return region
        return None
    
    def _extract_wine_type(self, name: str) -> Optional[str]:
        """Извлечение типа вина из названия"""
        name_lower = name.lower()
        if "tinto" in name_lower:
            return WineType.TINTO.value
        elif "blanco" in name_lower:
            return WineType.BLANCO.value
        elif "rosado" in name_lower:
            return WineType.ROSADO.value
        elif "cava" in name_lower:
            return WineType.CAVA.value
        elif "espumoso" in name_lower:
            return WineType.ESPUMOSO.value
        return None


class MercadonaParser:
    """
    Парсер для tienda.mercadona.es
    Использует Algolia API с привязкой к складу (warehouse)
    """
    
    ALGOLIA_APP_ID = "7UZJKL1DJ0"
    ALGOLIA_API_KEY = "9d8f2e39e90df472b4f2e559a116fe17"
    
    # Склады по регионам (из URL индекса products_prod_XXX_es)
    WAREHOUSES = {
        "valencia": "vlc1",
        "madrid": "mad1",
        "barcelona": "bcn1",
        "sevilla": "svq1",
        "malaga": "agp1",
    }
    
    def __init__(self, warehouse: str = "vlc1"):
        self.warehouse = warehouse
        self.index = f"products_prod_{warehouse}_es"
        self.base_url = f"https://{self.ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{self.index}/query"
        
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "x-algolia-api-key": self.ALGOLIA_API_KEY,
            "x-algolia-application-id": self.ALGOLIA_APP_ID,
        })
    
    def search_wines(self, wine_type: WineType = WineType.TINTO, limit: int = 50) -> list[Wine]:
        """Поиск вин по типу"""
        query = f"vino {wine_type.value}"
        
        payload = {
            "query": query,
            "hitsPerPage": limit,
            "page": 0
        }
        
        try:
            response = self.session.post(self.base_url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            wines = []
            hits = data.get("hits", [])
            for hit in hits:
                wine = self._parse_hit(hit)
                if wine:
                    wines.append(wine)
            
            print(f"✅ Mercadona: {len(wines)} wines (from {len(hits)} hits)")
            return wines
            
        except requests.RequestException as e:
            print(f"❌ Mercadona API error: {e}")
            return []
    
    def _parse_hit(self, hit: dict) -> Optional[Wine]:
        """Парсинг результата Algolia в объект Wine"""
        try:
            product_id = str(hit.get("id", ""))
            name = hit.get("display_name", "")
            brand = hit.get("brand", "")
            
            # Цены
            price_info = hit.get("price_instructions", {})
            price = float(price_info.get("unit_price", 0))
            price_per_liter = float(price_info.get("reference_price", 0))
            
            # Акция
            discount_price = None
            discount_percent = None
            previous_price = price_info.get("previous_unit_price")
            if previous_price:
                discount_price = price
                price = float(previous_price)
                discount_percent = int((1 - discount_price / price) * 100)
            
            # URL
            url = hit.get("share_url", f"https://tienda.mercadona.es/product/{product_id}")
            
            # Изображение
            image_url = hit.get("thumbnail", "")
            
            return Wine(
                id=f"mercadona_{product_id}",
                name=name,
                brand=brand,
                price=price,
                price_per_liter=price_per_liter,
                store=Store.MERCADONA.value,
                url=url,
                image_url=image_url,
                ean=None,  # Mercadona не возвращает EAN
                region=self._extract_region(name),
                wine_type=self._extract_wine_type(name),
                discount_price=discount_price,
                discount_percent=discount_percent
            )
        except Exception as e:
            print(f"Error parsing Mercadona hit: {e}")
            return None
    
    def _extract_region(self, name: str) -> Optional[str]:
        """Извлечение региона DO из названия"""
        regions = [
            "Rioja", "Ribera del Duero", "Rueda", "Rías Baixas",
            "Priorat", "Penedès", "Jumilla", "Toro", "Navarra",
            "La Mancha", "Valdepeñas", "Utiel-Requena", "Cariñena"
        ]
        name_lower = name.lower()
        for region in regions:
            if region.lower() in name_lower:
                return region
        return None
    
    def _extract_wine_type(self, name: str) -> Optional[str]:
        """Извлечение типа вина из названия"""
        name_lower = name.lower()
        if "tinto" in name_lower:
            return WineType.TINTO.value
        elif "blanco" in name_lower:
            return WineType.BLANCO.value
        elif "rosado" in name_lower:
            return WineType.ROSADO.value
        elif "cava" in name_lower:
            return WineType.CAVA.value
        elif "espumoso" in name_lower:
            return WineType.ESPUMOSO.value
        return None


class WineAggregator:
    """
    Агрегатор вин из всех магазинов
    """
    
    def __init__(self, postal_code: str = "46001"):
        self.postal_code = postal_code
        self.consum = ConsumParser(postal_code)
        self.mercadona = MercadonaParser()  # TODO: маппинг postal_code -> warehouse
    
    def search_all(self, wine_type: WineType = WineType.TINTO, limit_per_store: int = 20) -> list[Wine]:
        """Поиск вин во всех магазинах"""
        all_wines = []
        
        # Consum
        consum_wines = self.consum.search_wines(wine_type, limit_per_store)
        all_wines.extend(consum_wines)
        
        # Mercadona
        mercadona_wines = self.mercadona.search_wines(wine_type, limit_per_store)
        all_wines.extend(mercadona_wines)
        
        return all_wines
    
    def get_recommendations(
        self, 
        wine_type: WineType,
        max_price: float = 15.0,
        prefer_discount: bool = True
    ) -> list[Wine]:
        """
        Получение рекомендаций с фильтрацией
        """
        wines = self.search_all(wine_type, limit_per_store=50)
        
        # Фильтр по цене
        filtered = [w for w in wines if w.price <= max_price]
        
        # Сортировка
        if prefer_discount:
            # Сначала со скидкой, потом по цене
            filtered.sort(key=lambda w: (
                0 if w.discount_price else 1,
                w.price
            ))
        else:
            filtered.sort(key=lambda w: w.price)
        
        return filtered


def main():
    """Демонстрация работы парсеров"""
    print("🍷 Wine Parser PoC\n")
    
    aggregator = WineAggregator(postal_code="46001")
    
    # Поиск красных вин до 10€
    print("Searching for red wines under 10€...\n")
    wines = aggregator.get_recommendations(
        wine_type=WineType.TINTO,
        max_price=10.0,
        prefer_discount=True
    )
    
    print(f"\n📊 Found {len(wines)} wines:\n")
    
    for i, wine in enumerate(wines[:10], 1):
        discount_info = ""
        if wine.discount_price:
            discount_info = f" (🏷️ {wine.discount_price}€, -{wine.discount_percent}%)"
        
        region_info = f" [{wine.region}]" if wine.region else ""
        ean_info = f" EAN:{wine.ean}" if wine.ean else ""
        
        print(f"{i}. {wine.name}")
        print(f"   💰 {wine.price}€{discount_info} | {wine.price_per_liter}€/L")
        print(f"   🏪 {wine.store.upper()}{region_info}{ean_info}")
        print(f"   🔗 {wine.url}\n")


if __name__ == "__main__":
    main()
