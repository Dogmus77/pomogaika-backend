# Pomogaika 2.3.0 — API contract for the new endpoints

Base URL: https://pomogaika-api.onrender.com
Both endpoints are public (no auth), JSON in/out, deployed BEFORE the apps ship.
Backend never returns mock data from these endpoints.

## POST /ask  — "Спроси сомелье"

Turns a free-text request into questionnaire answers. It does NOT return wines:
the app takes `params` and runs its existing flow exactly as if the user had
filled in the questionnaire (pairing → GET /recommend, party → its party search).

Request:
```json
{"text": "паэлья с морепродуктами на компанию до 10 евро", "lang": "ru"}
```
- `text`: required, 2..300 chars after trimming, any of the 5 languages.
- `lang`: ru | uk | be | en | es (UI language).

Response 200, understood:
```json
{
  "understood": true,
  "mode": "pairing",
  "params": {
    "meal_time": "dinner",
    "dishes": ["fish"],
    "cooking_method": "grilled",
    "cuisine": "spanish",
    "min_price": 2,
    "max_price": 10,
    "party_wine_preference": null,
    "party_occasion": null
  }
}
```
Response 200, not about food / wine / an occasion:
```json
{"understood": false}
```

`mode` = "pairing" | "party".

`params` values are EXACTLY the apps' enum rawValues:
- `meal_time`: lunch | dinner | aperitivo | digestivo | party | null
  (always "party" when mode = "party"; may be null in pairing mode)
- `dishes`: ordered list, most important first, values from
  fish | meat | poultry | vegetables | pasta | cheese.
  pairing mode: at least 1 item. party mode: [].
- `cooking_method`: grilled | stewed | steamed | fried | creamy | tomato | unknown | null
- `cuisine`: spanish | italian | asian | other | unknown | null
- `min_price`, `max_price`: numbers in euros, clamped by the server to the app's
  slider range 2..50, min_price <= max_price. Defaults when the user said nothing
  about price: 2 and 15 (the questionnaire default).
- `party_wine_preference`: red_dry | white_dry | rose | sparkling | semi_sweet | surprise | null
  (non-null only in party mode; "surprise" when unspecified)
- `party_occasion`: birthday | friends_dinner | business_visit | just_because | doesnt_matter | null
  (non-null only in party mode; "doesnt_matter" when unspecified)

Errors (body `{"detail": "..."}`):
- 422 — text missing / too short / too long
- 429 — rate limit (10 requests per minute per IP)
- 502 — the model failed; the app shows an error with Retry and a way to the questionnaire

Typical latency 1–3 s; the app should use a 30 s timeout for this call.

## POST /pairings — "С чем подать"

Request:
```json
{"wine_id": "mercadona_12345", "name": "Viña Albali Reserva", "wine_type": "tinto",
 "region": "Valdepeñas", "grape": "Tempranillo", "lang": "ru"}
```
- `wine_id`: required (cache key). Apps must NOT call this for empty ids or ids starting with "mock_".
- `name`: required. `wine_type`, `region`, `grape`: optional/null.
- `lang`: ru | uk | be | en | es.

Response 200:
```json
{"dishes": [
  {"dish": "Ягнёнок на гриле с розмарином", "why": "Танины смягчают жир, травы подчёркивают аромат."},
  {"dish": "...", "why": "..."}
]}
```
- 3 or 4 items, in `lang`, `why` is one short sentence.

Errors: 422 (bad request), 429 (rate limit 30/min per IP), 502 (model failure).
Server caches by (wine_id, lang); repeat calls are instant. App: 30 s timeout,
hide the section on failure after a small Retry, never block the wine sheet.

## Unchanged, for reference
- GET /recommend?dish=&cooking_method=&meal_time=&cuisine=&min_price=&max_price=&postal_code=&limit=&lang=
  (single `dish`: the app sends dishes[0])
- GET /search?query=&wine_type=&min_price=&max_price=&postal_code=&limit=
- POST /device-token {device_id, fcm_token, platform, language}
