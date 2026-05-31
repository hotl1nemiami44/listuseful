# Price Tracker

Отслеживание цен на Ozon, Wildberries, Яндекс.Маркет, AliExpress с уведомлениями в Telegram.

## Установка

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # вписать TELEGRAM_BOT_TOKEN
```

Токен получить у [@BotFather](https://t.me/BotFather).

### Браузерный фолбэк (опционально)

WB работает через свой JSON API без браузера. Для сайтов с тяжёлым
антиботом (Я.Маркет, иногда Ozon) можно доустановить браузер:

```bash
pip install -r requirements-browser.txt
playwright install chromium
```

## Диагностика

Если парсер не работает — запусти и пришли вывод:

```bash
python scripts/diagnose.py
# или для конкретного товара:
python scripts/diagnose.py https://www.wildberries.ru/catalog/968907071/detail.aspx
```

## Запуск

```bash
uvicorn app.main:app --reload
```

Открыть `http://localhost:8000/docs` — Swagger UI.

## Использование

Узнать свой `chat_id`: написать боту [@userinfobot](https://t.me/userinfobot).

Добавить товар:

```bash
curl -X POST http://localhost:8000/products \
  -H "X-Chat-Id: 123456789" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.wildberries.ru/catalog/123456789/detail.aspx", "threshold_percent": 5}'
```

Принудительная проверка:

```bash
curl -X POST http://localhost:8000/products/1/check -H "X-Chat-Id: 123456789"
```