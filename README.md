# Price Tracker

A self-hosted web app that monitors product prices across Russian and global marketplaces (Wildberries, Ozon, Яндекс Маркет, AliExpress) and sends Telegram alerts when prices drop below your threshold.

---

## Features

- Track products from Wildberries, Ozon, Яндекс Маркет, AliExpress by article/product ID
- Stores full price history in a local SQLite database
- Inline sparkline and full price-history chart (Chart.js) in the browser
- Telegram bot notifications when a price drops by your configured percentage
- Scheduled background checks (configurable interval, default 60 min)
- On-demand manual refresh via the UI
- Per-product configurable alert threshold
- Dark-theme responsive single-page frontend (no framework, pure HTML/CSS/JS)

---

## Project Structure

```
listuseful/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py           # FastAPI app + API routes
│   │   ├── database.py       # SQLAlchemy engine & session
│   │   ├── models.py         # Product & PriceHistory ORM models
│   │   ├── schemas.py        # Pydantic request/response schemas
│   │   ├── crud.py           # Database operations
│   │   ├── scheduler.py      # APScheduler background price checks
│   │   ├── telegram_notify.py# Telegram bot alerts via httpx
│   │   └── parsers/
│   │       ├── base.py           # BaseParser ABC + ProductInfo dataclass
│   │       ├── wildberries.py    # Wildberries card API parser
│   │       ├── ozon.py           # Ozon composer API parser
│   │       ├── yandex_market.py  # Yandex Market HTML/JSON-LD parser
│   │       └── aliexpress.py     # AliExpress runParams + JSON-LD parser
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html   # Single-page app shell
│   ├── style.css    # Dark-theme responsive styles
│   └── app.js       # Vanilla JS: fetch, render, charts
└── README.md
```

---

## Quick Start

### 1. Clone / enter the project directory

```bash
cd /path/to/listuseful
```

### 2. Set up the Python environment

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```
TELEGRAM_BOT_TOKEN=123456:ABC-your-token
TELEGRAM_CHAT_ID=987654321
CHECK_INTERVAL_MINUTES=60
DATABASE_URL=sqlite:///./products.db
```

- `TELEGRAM_BOT_TOKEN` — create a bot via [@BotFather](https://t.me/BotFather)
- `TELEGRAM_CHAT_ID` — your personal or group chat ID (use [@userinfobot](https://t.me/userinfobot) to find it)
- Leave both empty to disable Telegram notifications

### 4. Start the server

```bash
# From the backend/ directory (with .venv active):
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open your browser at: **http://localhost:8000**

The frontend is served directly by FastAPI from the `frontend/` directory.

---

## API Reference

All endpoints are under `/api/`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/products` | List all tracked products with price history |
| `POST` | `/api/products` | Add a new product (fetches price immediately) |
| `DELETE` | `/api/products/{id}` | Remove a product and its history |
| `PATCH` | `/api/products/{id}` | Update alert threshold |
| `POST` | `/api/refresh` | Trigger an immediate price check for all products |

### POST /api/products — request body

```json
{
  "article": "123456789",
  "marketplace": "wildberries",
  "alert_threshold": 5.0
}
```

`marketplace` must be one of: `wildberries`, `ozon`, `yandex_market`, `aliexpress`.

---

## How Parsers Work

Each marketplace has a dedicated parser in `backend/app/parsers/`:

| Marketplace | Strategy |
|-------------|----------|
| Wildberries | JSON API at `card.wb.ru` — no HTML parsing needed |
| Ozon | Composer JSON API (`/api/composer-api.bx/page/json/v2`) — walks widget tree |
| Яндекс Маркет | HTTP + BeautifulSoup, extracts JSON-LD `Product` schema |
| AliExpress | HTTP + BeautifulSoup, extracts `window.runParams` or JSON-LD |

> **Note:** Marketplace websites frequently change their structure. Parsers may need updates if they stop returning data.

---

## Telegram Notifications

When a price check finds a price **lower** than the previous price **by at least `alert_threshold`%**, a message is sent to the configured chat:

```
Price drop!

Product Name
Marketplace

Was: 1 200.00 ₽
Now: 990.00 ₽
Discount: -17.5%

https://www.wildberries.ru/catalog/...
```

---

## Development Tips

### Run with auto-reload

```bash
uvicorn app.main:app --reload
```

### Inspect the database

```bash
sqlite3 backend/products.db ".tables"
sqlite3 backend/products.db "SELECT * FROM products;"
sqlite3 backend/products.db "SELECT * FROM price_history ORDER BY recorded_at DESC LIMIT 20;"
```

### Test a parser manually

```python
import asyncio
from app.parsers import fetch_product

async def test():
    info = await fetch_product("wildberries", "123456789")
    print(info)

asyncio.run(test())
```

### Frontend development without the backend

Set `const API = 'http://localhost:8000';` at the top of `frontend/app.js` and open `frontend/index.html` directly in a browser while the backend runs separately.

---

## Requirements

- Python 3.10+
- Modern browser (Chrome, Firefox, Safari, Edge)
- Internet access for marketplace scraping
- (Optional) Telegram bot token for price alerts

---

## License

MIT