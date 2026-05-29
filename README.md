# 🧴 INCIbot — Telegram-бот для персонализированной оценки косметики по составу

Telegram-бот, который анализирует INCI-состав косметического средства и выдаёт **персонализированную оценку** с пояснениями и предупреждениями — с учётом типа кожи, аллергенов и предпочтений конкретного пользователя.

Под капотом — большая языковая модель DeepSeek 3.2 через Yandex Cloud AI Studio, RAG-модуль с базой знаний по ингредиентам, парсер Wildberries, OCR для распознавания состава с фотографий этикеток и верификатор ответов на основе LLM-as-a-Judge.

> Проект разработан как выпускная квалификационная работа по направлению «Прикладная информатика» (УрФУ, ИРИТ-РТФ, РИ-420930). Полный цикл: архитектура, схема БД, парсинг, RAG, промпт-инжиниринг, верификатор, подсистема безопасности, OCR, тестирование, деплой.

---

## ✨ Возможности

- **4 способа передать состав:**
  1. 📷 Фото этикетки → OCR-распознавание (Yandex Vision, точность 82,5%)
  2. 🔗 Ссылка на товар Wildberries → автоматический парсинг состава
  3. 🔍 Название товара → поиск по каталогу WB, выбор из 5 вариантов
  4. ⌨️ Прямой ввод текста состава
- **Персонализация** — оценка с учётом типа кожи, аллергенов и предпочтений
- **Структурированный ответ** — оценка 0–10, объяснение, warnings, рекомендации
- **Верификатор** — второй LLM (YandexGPT Pro 5.1) проверяет каждый ответ на галлюцинации
- **Безопасность** — защита от prompt injection (17 паттернов), rate limiting, логирование
- **152-ФЗ** — явное согласие, право на удаление данных, хранение в ЦОД РФ

---

## 🏗️ Архитектура

```
Telegram-клиент
      │  HTTPS
      ▼
 aiogram 3.x (Long Polling)
      │
      ▼
 Оркестратор (message.py)
 ┌────┴────────────────────────────────────────┐
 │                                              │
 ▼                ▼              ▼              ▼
InputSanitizer  CosmeticParser  PromptBuilder  ResponseVerifier
RateLimiter     OCRModule       IngredientRAG  (LLM-as-a-Judge)
 │                │              │              │
 ▼                ▼              ▼              ▼
security_events  WB CDN API    ingredients   YandexGPT Pro
(PostgreSQL)     WB Search API  .json         t=0.0
                 Yandex Vision
                    OCR
                                 │
                                 ▼
                           YandexGPTClient
                           DeepSeek 3.2
                           (основная модель)
                                 │
                                 ▼
                           PostgreSQL 16
                           users · history
```

### Модули

| Файл | Назначение |
|---|---|
| `main.py` | Точка входа, инициализация бота и диспетчера |
| `message.py` | Оркестратор: маршрутизация запросов, обработчики текста и фото |
| `start.py` | Приветствие, пользовательское соглашение, команды /help, /stats |
| `profile.py` | FSM-диалог настройки профиля (тип кожи → аллергены → предпочтения) |
| `cosmetic_parser.py` | Парсер Wildberries: CDN API + Search API + извлечение состава |
| `ocr_module.py` | OCR-pipeline: Yandex Vision → блок состава → очистка → валидация INCI |
| `rag_module.py` | RAG: поиск по базе 248 ингредиентов, формирование контекста для промпта |
| `prompt_builder.py` | Сборка промпта: RAG-контекст + профиль + состав + OCR-warnings |
| `yandex_client.py` | Клиент Yandex Cloud AI Studio (DeepSeek / YandexGPT / Qwen) |
| `verifier.py` | LLM-as-a-Judge: проверка галлюцинаций и аллергенов |
| `sanitizer.py` | InputSanitizer: 14 HIGH + 4 LOW паттерна защиты |
| `rate_limiter.py` | Sliding window: 2/10с · 5/мин · 30/ч |
| `models.py` | SQLAlchemy-модели: User, History, SecurityEvent |
| `repository.py` | Паттерн Repository: абстракция над PostgreSQL |
| `db.py` | Инициализация БД, движок asyncpg |
| `config.py` | Загрузка .env, разрешение путей к файлам |

---

## 🛠️ Стек

| Категория | Технология |
|---|---|
| Язык | Python 3.13 (asyncio) |
| Telegram | aiogram 3.27, Long Polling |
| LLM | Yandex Cloud AI Studio — DeepSeek 3.2 (основной), YandexGPT Pro 5.1 (верификатор) |
| OCR | Yandex Vision OCR |
| БД | PostgreSQL 16, SQLAlchemy 2.0 async, asyncpg |
| RAG | ingredients.json (248 ингредиентов, Renude.co) |
| INCI-база | inci_ingredients.json (7 338 ингредиентов, specialchem.com) |
| Деплой | Yandex Compute Cloud, Ubuntu 22.04, Docker Compose, systemd |
| Логирование | loguru |

---

## 🚀 Запуск

### Требования

- Python 3.11+
- Docker и Docker Compose
- Токен Telegram-бота ([@BotFather](https://t.me/BotFather))
- Yandex Cloud AI Studio: API-ключ, folder ID, ID промптов для LLM и верификатора

### 1. Клонировать репозиторий

```bash
git clone https://github.com/Slry1/INCIbot.git
cd INCIbot
```

### 2. Создать `.env`

```env
BOT_TOKEN=your_telegram_bot_token

YANDEX_API_KEY=your_yandex_api_key
YANDEX_FOLDER_ID=your_folder_id
YANDEX_PROMPT_ID=deepseek_prompt_id
YANDEX_PROMPT_ID_VERIFIER=verifier_prompt_id

POSTGRES_PASSWORD=your_db_password
POSTGRES_USER=incibot
POSTGRES_DB=incibot

DATABASE_URL=postgresql+asyncpg://incibot:your_db_password@db:5432/incibot

RAG_DATA_PATH=llm/data/ingredients.json
INCI_DB_PATH=llm/data/inci_ingredients.json

ADMIN_IDS=your_telegram_id
VERIFIER_ENABLED=true
```

### 3. Запустить через Docker Compose

```bash
docker compose build --no-cache
docker compose up -d
```

### 4. Проверить

```bash
docker compose ps
docker logs incibot_bot -f
```

Открыть бота в Telegram и отправить `/start`.

---

## 💬 Команды

| Команда | Описание |
|---|---|
| `/start` | Запуск, приветствие, соглашение на обработку данных |
| `/help` | Справка: способы ввода и шкала оценок |
| `/how_it_works` | Как работает система: технологии и критерии |
| `/settings` | Настройка профиля через FSM-диалог |
| `/my_data` | Просмотр персональных данных |
| `/delete_data` | Удаление всех данных пользователя |
| `/agreement` | Текст пользовательского соглашения |
| `/stats` | Статистика системы (только для администраторов) |

Чтобы оценить средство — нажать «📝 Оценить состав» и отправить фото этикетки, ссылку WB, название товара или состав текстом.

---

## 📊 Результаты тестирования

| Компонент | Метрика | Результат |
|---|---|---|
| Парсер Wildberries | Success Rate | 87% (26/30 товаров) |
| Парсер Wildberries | Среднее время | 1,1 сек |
| OCR-модуль | API Success Rate | 100% (166/166 фото) |
| OCR-модуль | Точность (exact + fuzzy) | 82,5% |
| Верификатор | Hallucination Detection Rate | 100% (n=5 итераций) |
| Верификатор | False Positive Rate | 0% |
| Верификатор | Среднее время проверки | 889 мс |
| Стабильность оценок | Stability Rate | 100% (30 прогонов) |
| Стабильность оценок | Коэффициент вариации | 4,3% |
| Allergen Detection Rate | ADR на тестовой выборке | 100% (n=40) |
| Экспертная валидация | Корреляция Спирмена ρ | 0,89 |
| Экспертная валидация | MAE | 1,30 балла (шкала 0–10) |

**Сравнение LLM-моделей** (промпт v1, 20 составов):

| Модель | ρ | MAE | ADR |
|---|---|---|---|
| **DeepSeek 3.2** | **0,90** | **1,85** | **100%** |
| YandexGPT 5.1 PRO | 0,88 | 2,05 | 71,4% |
| Qwen3 235B | 0,88 | 2,25 | 85,7% |
| YandexGPT 5 Lite | 0,82 | — | 42,9% |

DeepSeek 3.2 выбран как основная модель — единственная с ADR (Alleregn Detection Rate) 100% при FP 0%.

---

## 📁 Структура проекта

```
yandexgpt_bot/
├── bot/
│   ├── handlers/
│   │   ├── message.py           # оркестратор: обработчики текста и фото
│   │   ├── profile.py           # FSM настройки профиля
│   │   └── start.py             # /start, /help, /how_it_works, /stats
│   ├── cosmetic_parser.py       # парсер Wildberries (CDN + Search API)
│   ├── main.py                  # точка входа, инициализация бота
│   └── ocr_module.py            # OCR-pipeline (Yandex Vision)
├── database/
│   ├── db.py                    # инициализация БД, движок asyncpg
│   ├── models.py                # SQLAlchemy-модели (User, History, SecurityEvent)
│   └── repository.py            # Repository pattern
├── llm/
│   ├── data/
│   │   ├── ingredients.json     # RAG-база (248 ингредиентов, Renude.co)
│   │   ├── inci_ingredients.json # INCI-база (7 338 ингредиентов, specialchem)
│   │   └── results/             # результаты бенчмарков
│   ├── prompt_builder.py        # сборка промпта
│   ├── rag_module.py            # RAG-модуль
│   ├── rate_limiter.py          # rate limiting (sliding window)
│   ├── sanitizer.py             # защита от prompt injection
│   ├── verifier.py              # верификатор LLM-as-a-Judge
│   └── yandex_client.py         # LLM-клиент (Yandex Cloud AI Studio)
├── config.py                    # конфигурация из .env
├── DeepSeek_PROMPT              # системный промпт основной модели
├── VERIFIER_PROMPT              # промпт верификатора
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env                         # не коммитить
```

---

## 🧪 Тестирование

```bash
# Тесты sanitizer (без API)
pytest test_sanitizer.py -v

# Тесты парсера WB (реальные запросы)
pytest test_wb_parser.py -v -s

# Бенчмарк верификатора
python benchmark_verifier.py

# Тест стабильности оценок
python benchmark_stability.py

# Allergen Detection Rate (40 кейсов, ~5 мин)
python run_allergen_benchmark.py

# Экспертная валидация (20 составов)
python run_expert_benchmark.py
python expert_validation.py --scores scores.json
```

---

## ⚖️ Правовое соответствие

- **152-ФЗ** — явное согласие при первом запуске, право на забвение (`/delete_data`), хранение в ЦОД Yandex Cloud на территории РФ, минимизация обрабатываемых данных
- **ФЗ-38 «О рекламе», ст. 18.1** — раскрытие критериев оценки (`/how_it_works`), отсутствие брендовых рекомендаций
- **ТР ТС 009/2011** — учёт ограничений по раскрытию составов (концентрации <1%, парфюмерные композиции)

Оценки носят **рекомендательный характер** и не являются медицинским заключением. Бот не заменяет консультацию дерматолога, аллерголога или косметолога.

---

## 📄 Лицензия

MIT
