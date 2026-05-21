# Price Tracker

Отслеживание цен на Wildberries, Ozon, Яндекс.Маркет и AliExpress с уведомлениями в Telegram при снижении цены.

## Возможности

- Добавление товаров по ссылке с любого из поддерживаемых маркетплейсов
- Автоматическая проверка цен по расписанию
- График истории цен для каждого товара
- Уведомление в Telegram когда цена упала на заданный процент
- Веб-интерфейс с тёмной темой
- Поддержка нескольких пользователей через Telegram Chat ID

## Установка

**1. Клонируйте репозиторий**
```bash
git clone https://gitflic.ru/project/ваш_ник/listuseful.git
cd listuseful
```

**2. Создайте виртуальное окружение**
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac / Linux
source .venv/bin/activate
```

**3. Установите зависимости**
```bash
pip install -r requirements.txt
```

**4. Создайте файл настроек**
```bash
# Windows
copy .env.example .env

# Mac / Linux
cp .env.example .env
```

Откройте `.env` и вставьте токен бота:
```
TELEGRAM_BOT_TOKEN=токен_от_BotFather
CHECK_INTERVAL_HOURS=6
DEFAULT_THRESHOLD_PERCENT=5.0
DATABASE_URL=sqlite:///./price_tracker.db
LOG_LEVEL=INFO
```

Токен получить у [@BotFather](https://t.me/BotFather) — команда `/newbot`.

## Запуск

```bash
uvicorn app.main:app --reload
```

Откройте браузер: `http://localhost:8000`

## Первый запуск

1. При открытии сайта введите ваш Telegram Chat ID
2. Узнать его можно у бота [@userinfobot](https://t.me/userinfobot) — напишите ему `/start`
3. После ввода Chat ID можно добавлять товары

## Добавление товара

Вставьте ссылку на товар в поле ввода и нажмите **Добавить**. Поддерживаются ссылки вида:

```
https://www.wildberries.ru/catalog/123456789/detail.aspx
https://www.ozon.ru/product/название-123456789/
https://market.yandex.ru/product--название/123456789
https://www.aliexpress.com/item/123456789.html
```

## Структура проекта

```
listuseful/
├── app/
│   ├── main.py           # FastAPI приложение, все роуты
│   ├── models.py         # Модели базы данных
│   ├── schemas.py        # Pydantic схемы
│   ├── config.py         # Настройки из .env
│   ├── database.py       # Подключение к SQLite
│   ├── notifier.py       # Отправка уведомлений в Telegram
│   ├── parsers/
│   │   ├── wildberries.py
│   │   ├── ozon.py
│   │   ├── yandex_market.py
│   │   └── aliexpress.py
│   └── tasks/
│       ├── scheduler.py  # Планировщик проверок
│       └── check_prices.py
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── requirements.txt
└── .env.example
```

## Надёжность парсеров

| Маркетплейс | Метод | Надёжность |
|---|---|---|
| Wildberries | Публичный API | Высокая |
| Ozon | Неофициальный API | Средняя |
| Яндекс.Маркет | Скрапинг HTML | Средняя |
| AliExpress | Скрапинг JS | Низкая |

> Ozon, Яндекс.Маркет и AliExpress могут блокировать запросы. В таком случае попробуйте добавить товар позже или использовать прокси.

## Уведомление в Telegram

При снижении цены на величину не менее заданного порога бот пришлёт сообщение:

```
📉 Цена снизилась!

Название товара

Было: 2 500 ₽
Стало: 1 990 ₽
Скидка: −510 ₽ (20.4%)

Открыть товар
```

Если у товара есть фото — оно будет прикреплено к сообщению.
