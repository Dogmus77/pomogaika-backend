# Pomogaika Backend — Деплой

## 🚀 Быстрый деплой на Render (рекомендуется)

### Шаг 1: Создать репозиторий на GitHub

```bash
# В папке pomogaika-backend
git init
git add .
git commit -m "Initial commit"
gh repo create pomogaika-backend --public --push
```

Или вручную:
1. Зайти на github.com
2. New Repository → "pomogaika-backend"
3. Загрузить файлы через интерфейс

### Шаг 2: Подключить Render

1. Зайти на [render.com](https://render.com)
2. Sign up with GitHub
3. **New → Web Service**
4. Выбрать репозиторий `pomogaika-backend`
5. Настройки:
   - **Name:** `pomogaika-api`
   - **Region:** Frankfurt (ближе к Испании)
   - **Branch:** `main`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Plan:** Free
6. **Create Web Service**

### Шаг 3: Получить URL

После деплоя (2-3 минуты) получите URL типа:
```
https://pomogaika-api.onrender.com
```

### Шаг 4: Проверить работу

```bash
# Health check
curl https://pomogaika-api.onrender.com/health

# Тест рекомендаций
curl "https://pomogaika-api.onrender.com/recommend?dish=fish&cooking_method=grilled&max_price=15"

# Поиск вин
curl "https://pomogaika-api.onrender.com/search?wine_type=tinto&max_price=10"
```

---

## 📱 Обновить iOS приложение

После получения URL, обновить `APIService.swift`:

```swift
class APIService {
    static let shared = APIService()
    
    // Заменить на ваш URL
    private let baseURL = "https://pomogaika-api.onrender.com"
    
    // ... остальной код
}
```

---

## 🔧 Альтернативные платформы

### Railway

```bash
# Установить CLI
npm install -g @railway/cli

# Логин и деплой
railway login
railway init
railway up
```

### Heroku

```bash
heroku create pomogaika-api
git push heroku main
```

### VPS (DigitalOcean, etc.)

```bash
# На сервере
git clone https://github.com/YOUR_USERNAME/pomogaika-backend.git
cd pomogaika-backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 📊 API Endpoints

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/` | GET | Информация об API |
| `/health` | GET | Health check |
| `/recommend` | GET | Рекомендации вин |
| `/search` | GET | Поиск вин |
| `/expert` | GET | Экспертные рекомендации |
| `/stores` | GET | Список магазинов |

### Примеры запросов

```bash
# Рекомендации для рыбы гриль
GET /recommend?dish=fish&cooking_method=grilled&min_price=5&max_price=15

# Красные вина из Риохи
GET /search?wine_type=tinto&region=rioja&max_price=12

# Экспертные советы
GET /expert?dish=meat&cooking_method=stewed
```

---

## ⚠️ Важно

### Free tier ограничения (Render)

- Сервис "засыпает" после 15 минут неактивности
- Первый запрос после "сна" занимает 30-60 секунд
- 750 часов в месяц (достаточно для 1 сервиса 24/7)

### Решение для продакшена

1. **Платный план** ($7/мес) — сервис не засыпает
2. **Ping сервис** — настроить UptimeRobot для периодических запросов
3. **Кэширование** — вина кэшируются на 30 минут (уже реализовано)

---

## 🐛 Troubleshooting

### "Service unavailable"
- Подождите 30-60 секунд (сервис просыпается)
- Проверьте логи в Render Dashboard

### "No wines found"
- API магазинов могут быть временно недоступны
- Проверьте `/health` для статуса кэша

### Ошибки парсинга
- Consum/Mercadona могут менять API
- Проверьте логи, обновите парсеры при необходимости
