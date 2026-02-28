# CLAUDE.md — Pomogaika Backend

## What is this

Python/FastAPI backend for Pomogaika wine recommendation app. Parses real-time wine data from 4 Spanish supermarket chains (Consum, Mercadona, Masymas, DIA) and provides AI sommelier recommendations.

**Production URL:** https://pomogaika-api.onrender.com
**Privacy policy:** https://pomogaika.info/privacy-policy.html
**Contact:** info@pomogaika.es

## Quick Start

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## File Structure

| File | Purpose |
|---|---|
| `main.py` | FastAPI server — endpoints, caching, wine fetching, localized expert notes |
| `sommelier.py` | Sommelier engine — pairing matrix (dish + cooking + cuisine → wine style/grapes/regions) |
| `wine_parser.py` | Store parsers: ConsumParser, MercadonaParser, MasymasParser, DIAParser, WineAggregator |
| `render.yaml` | Render.com deployment config (Frankfurt, free tier, Python 3.11) |
| `requirements.txt` | fastapi, uvicorn, requests, pydantic, httpx |
| `Procfile` | `uvicorn main:app` for Render |

## API Endpoints

| Endpoint | Purpose | Key Params |
|---|---|---|
| `GET /recommend` | AI sommelier recommendations | `dish`, `cooking_method`, `meal_time`, `cuisine`, `min_price`, `max_price`, `lang`, `limit` (default 80) |
| `GET /search` | Wine catalog search | `query`, `wine_type`, `min_price`, `max_price`, `store`, `limit` (default 80) |
| `GET /stores` | List supported stores | — |
| `GET /health` | Health check + cache stats | — |
| `GET /debug/store/{name}` | Debug individual store parser | — |

## Architecture

### Data Pipeline
1. `fetch_wines_sync()` loads wines from 4 stores in parallel:
   - Standard search: `limit_per_store=80` per wine type (tinto, blanco, rosado, cava)
   - Premium search: `search_premium(limit_per_query=40)` — 10 queries (reserva, gran reserva, crianza rioja, ribera del duero, priorat, etc.)
2. Non-wine exclusion filter removes: jamon, bocadillo, ron, whisky, cerveza, queso, chorizo, aceite, vinagre, paté, conserva, atún, etc.
3. Results cached for 30 minutes
4. Cache pre-warms on startup (postal_code="46001")
5. Cold start: up to 90 seconds (Render free tier spins down)

### Sommelier Engine (sommelier.py)
- Pairing matrix: dish + cooking_method + cuisine → recommended wine style, grapes, regions
- `translate_summary()` and `get_expert_note()` return localized text
- Region-specific tasting notes (Rioja, Ribera del Duero, Priorat, Rías Baixas, etc.)

### Server-side Localization
- `lang` parameter: `ru`, `uk`, `be`, `en`, `es`
- Expert summaries, tasting notes, region descriptions — all localized on server
- Translation dicts: `SUMMARY_TRANSLATIONS`, `REGION_NOTES`, `WINE_TYPE_NOTES`, `DEFAULT_NOTE`

## Stores

| Store | ID | Coverage |
|---|---|---|
| Consum | `consum` | Valencia, Cataluña, Murcia |
| Mercadona | `mercadona` | All Spain |
| Masymas | `masymas` | Valencia, Alicante, Murcia |
| DIA | `dia` | All Spain |

## Deployment (Render)

- Region: Frankfurt, free tier
- Auto-deploy from git push
- Health check: `/health`
- Timeout: 120s configured in mobile clients
- Cache refresh: every 30 minutes

## Wine Types

| Type | API value | Description |
|---|---|---|
| Red | `tinto` | — |
| White | `blanco` | — |
| Rosé | `rosado` | — |
| Cava | `cava` | Cava + Corpinnat |
| Sparkling | `espumoso` | Other sparkling |

## Common Mistakes to Avoid

1. **Non-wine products in results** — always maintain the exclusion filter in `fetch_wines_sync()`
2. **Missing `lang` parameter** — all localized endpoints MUST accept and use `lang`
3. **Duplicate wines** — deduplicate by ID when merging standard + premium searches
4. **Cache race conditions** — `is_loading` flag prevents multiple simultaneous fetches
5. **Hardcoded postal code** — default is "46001" (Valencia), but should be parameterizable
