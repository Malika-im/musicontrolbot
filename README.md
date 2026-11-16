# 🎵 AI Telegram Bot для создания минусовок, разделения аудио и транспонирования

Полноценный, масштабируемый и готовый к production-запуску Telegram-бот на базе искусственного интеллекта для обработки музыкальных треков, создания чистых минусовок, разделения на stems (вокал, бас, ударные, инструменты), извлечения бэк-вокала, умного редактирования по тексту и изменения тональности (Pitch Shifting) с сохранением BPM и длительности.

---

## 🌟 Ключевые возможности

1. **Создание минусовок (Backing Tracks):**
   - Удаление вокала с максимальной чистотой через PyTorch-модель Meta Demucs (HTDemucs).
   - Сведение инструментальной части (ударные + бас + аккомпанемент).
2. **Разделение и управление вокалом:**
   - Извлечение чистого голоса исполнителя (Lead Vocals).
   - Изоляция бэк-вокала (гармонии, даблы, хоровые партии).
   - Удаление бэк-вокала с сохранением солирующего голоса.
   - Минусовка с сохранением бэк-вокала.
3. **Разделение на инструменты (Stems Separation):**
   - Ударные (Drums).
   - Бас-линия (Bass).
   - Аккомпанемент / Прочее (Other, Piano, Guitar).
4. **Умное редактирование (Smart AudioEditPlanner):**
   - Пользователь пишет запрос естественным языком:
     - *«Оставь только бэк-вокал»*
     - *«Убери основной голос, но оставь все бэки»*
     - *«Оставь слова "я тебя люблю"»*
     - *«Удали все слова, кроме припева»*
     - *«Сделай минусовку на тон ниже»*
   - Интеграция с **OpenAI Whisper** для определения временных меток слов (`word_timestamps`) и бесшовного вырезания/сохранения фраз с кроссфейдом.
   - Проверка осуществимости (feasibility check) и уточняющие вопросы при неоднозначности.
5. **Изменение тональности (Pitch Shifting / Transposition) [Раздел 13]:**
   - Изменение высоты тона по равномерно темперированной шкале (1 полутон = 1 semitone, 1 тон = 2 semitones).
   - **Строгое сохранение длительности, темпа (BPM), структуры песни и стереобазы** без изменения скорости воспроизведения!
   - Автоматическое определение исходной тональности (алгоритм Крамхансла-Шмуклера на базе Librosa Chroma) и темпа (BPM).
   - Отображение тональности до и после (например: *C major* $\to$ *Bb major* при -2 полутонах).
   - Инлайн-кнопки ($-1$, $-2$, $-3$, $+1$, $+2$, $+3$, ручной ввод) и текстовые команды.
   - Нормализация уровня и защита от цифрового клиппинга.
6. **Поддерживаемые форматы и источники:**
   - Аудиофайлы: **MP3, WAV, FLAC, M4A, OGG, AAC**.
   - Голосовые сообщения Telegram и видеозаписи (извлечение звуковой дорожки).
   - Внешние HTTP/HTTPS ссылки с защитой от **SSRF** (блокировка приватных IP, локалхоста и AWS metadata).
7. **Инфраструктура и безопасность:**
   - Работа исключительно через **Telegram Webhook** с проверкой секрета `X-Telegram-Bot-Api-Secret-Token`.
   - Дедупликация входящих обновлений Telegram через **Redis**.
   - Асинхронная очередь задач через **Celery** и **Redis**.
   - База данных **PostgreSQL** (SQLAlchemy 2.0 async + Alembic).
   - Ограничение размера файла (до 50 МБ), длительности (до 15 мин), лимиты параллельных задач пользователя.
   - Автоматическая очистка временных stems и файлов по истечении срока хранения.

---

## 🏛 Архитектура проекта

Проект построен по принципам **Clean Architecture** и **SOLID**:

```
ai-music-bot/
├── app/
│   ├── main.py                     # FastAPI application factory и lifespan
│   ├── api/
│   │   ├── routes.py               # /webhook/{secret}, /health, /
│   │   └── dependencies.py        # Аутентификация webhook и сессии DB
│   ├── bot/
│   │   ├── bot_service.py          # TelegramBotService (HTTPX клиент Bot API)
│   │   ├── dispatcher.py           # Роутер сообщений и inline callback'ов
│   │   ├── handlers/               # Command, Media, Smart Text хэндлеры
│   │   └── keyboards/              # Inline клавиатуры (Stems, Pitch, Results)
│   ├── core/
│   │   ├── config.py               # Pydantic Settings (.env)
│   │   ├── logging.py              # Структурированное логирование
│   │   ├── security.py             # Валидация webhook токена и SSRF guard
│   │   └── exceptions.py           # Иерархия доменных исключений
│   ├── database/
│   │   ├── connection.py           # Async SQLAlchemy engine и Redis pool
│   │   ├── models.py               # Users, AudioFiles, ProcessingTasks
│   │   └── repositories.py         # Репозитории доступа к данным
│   ├── storage/
│   │   └── storage_service.py      # Управление диском, UUID-путями и cleanup
│   ├── services/
│   │   ├── audio_download_service.py    # Безопасное скачивание (Telegram/URL)
│   │   ├── audio_validation_service.py  # Проверка MIME, magic bytes, duration
│   │   ├── audio_separation_service.py  # Координация Demucs
│   │   ├── vocal_separation_service.py  # Создание минусовки и извлечение вокала
│   │   ├── background_vocal_service.py  # Изоляция бэк-вокала (Mid/Side)
│   │   ├── speech_recognition_service.py# Whisper таймкоды слов
│   │   ├── audio_pitch_service.py       # Pitch shifting и гармонический анализ
│   │   ├── audio_mixing_service.py      # Сведение дорожек и маскирование фраз
│   │   ├── audio_edit_planner.py        # Преобразование текста в AudioPlan
│   │   └── task_manager.py              # Жизненный цикл задач и лимиты
│   ├── audio/
│   │   ├── pitch_shifter.py        # Librosa Pitch Shift с сохранением длительности
│   │   ├── key_detector.py         # Определение тональности и BPM
│   │   ├── ffmpeg_utils.py         # FFmpeg / soundfile конвертация и микширование
│   │   └── audio_effects.py        # Кроссфейд и маскирование временных интервалов
│   ├── ai/
│   │   ├── demucs_engine.py        # HTDemucs PyTorch runner
│   │   ├── backing_vocal_engine.py # Mid/Side спектральное разделение
│   │   ├── whisper_engine.py       # OpenAI Whisper word-timestamps runner
│   │   └── llm_client.py           # Эвристический семантический парсер + OpenAI
│   └── workers/
│       ├── celery_app.py           # Celery конфигурация (Redis broker)
│       └── tasks.py                # Фоновая обработка и статус-уведомления
├── alembic/                        # Миграции базы данных
├── tests/                          # Модульные и интеграционные тесты
├── docker-compose.yml              # Оркестрация (api, worker, postgres, redis)
├── Dockerfile                      # Production multi-stage сборка
├── requirements.txt                # Зависимости
└── .env.example                    # Шаблон конфигурации
```

---

## 🚀 Быстрый старт с Docker Compose

### 1. Предварительные требования
- Установленный **Docker** и **Docker Compose v2+**.
- Для ускорения нейросетей рекомендуется GPU NVIDIA с установленным **NVIDIA Container Toolkit** (при отсутствии GPU обработка автоматически выполняется на CPU).

### 2. Клонирование и настройка окружения
```bash
cp .env.example .env
```

Отредактируйте `.env`:
```ini
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ123456789
TELEGRAM_WEBHOOK_URL=https://your-domain.com
TELEGRAM_WEBHOOK_SECRET=your_super_secret_token_random_string_64_chars

POSTGRES_PASSWORD=your_strong_postgres_password
DEVICE=cuda   # или 'cpu', если нет видеокарты
DEMUCS_MODEL=htdemucs
WHISPER_MODEL=base
```

### 3. Запуск контейнеров
```bash
docker compose up -d --build
```

Docker Compose автоматически запустит 4 сервиса:
- `aimusic_postgres` — СУБД PostgreSQL 16.
- `aimusic_redis` — Кэш и брокер задач Redis 7.
- `aimusic_api` — FastAPI Webhook сервис с автоприменением миграций Alembic.
- `aimusic_worker` — Celery AI воркер с моделями Demucs, Whisper и Librosa.

### 4. Проверка работоспособности
```bash
curl http://localhost:8000/health
```
Ожидаемый ответ:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected",
  "redis": "connected"
}
```

---

## 🤖 Настройка Telegram Bot и Webhook

1. **Создайте бота в Telegram:**
   - Откройте [@BotFather](https://t.me/BotFather).
   - Отправьте команду `/newbot`, укажите имя и username.
   - Скопируйте полученный **HTTP API Token** в `TELEGRAM_BOT_TOKEN` в файле `.env`.

2. **Настройка Webhook:**
   Telegram API требует публичный HTTPS URL. При старте в production режиме приложение **самостоятельно регистрирует webhook** в Telegram с передачей `TELEGRAM_WEBHOOK_SECRET`.

   Для ручной проверки или перерегистрации:
   ```bash
   curl -F "url=https://your-domain.com/webhook/<PATH_HASH>" \
        -F "secret_token=your_super_secret_token" \
        https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook
   ```

   Проверить статус вебхука:
   ```bash
   curl https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo
   ```

---

## 🎹 Изменение тональности (Раздел 13)

Модуль `AudioPitchService` обеспечивает качественное транспонирование аудиоматериалов:

- **Точность и шаг:**
  $$\pm 1 \text{ полутон (semitone)}, \pm 2 \text{ полутона (1 тон)}, \pm 3 \dots \pm 12 \text{ полутонов}$$
- **Инвариантность темпа:**
  Используется фазовый вокодер Librosa (`librosa.effects.pitch_shift`) в сочетании с передискретизацией. Длительность трека и сетка BPM остаются идентичными оригиналу с погрешностью менее 0.05 сек.
- **Определение тональности:**
  Хрома-анализ (CQT) и сопоставление с профилями тональностей Крамхансла-Шмуклера для всех 12 мажорных и 12 минорных тональностей.
  - Пример: исходный трек $C\text{ major} - 2\text{ semitones} = Bb\text{ major}$.
- **Защита от клиппинга:**
  Автоматическое выравнивание пиковых амплитуд с запасом headroom ($0.95$).

---

## 🧪 Тестирование

Проект покрыт полным набором модульных и интеграционных тестов:
- Тестирование транспонирования на $+1, +2, +3, -1, -2, -3$ полутона с проверкой сохранения длительности и стерео.
- Тестирование формул транспонирования тональностей.
- Тестирование валидации файлов (размер, длительность, magic-байты, санитизация имен).
- Тестирование защиты от SSRF (приватные сети, loopback, cloud metadata).
- Тестирование планировщика естественного языка (AudioEditPlanner).
- Тестирование вебхука, секретных заголовков и дедупликации через Redis.
- Тестирование маскирования слов по таймкодам Whisper с кроссфейдами.

Запуск тестов:
```bash
pytest -v
```

---

## 🌐 Развертывание на VPS сервере

### 1. Подготовка сервера (Ubuntu 22.04 / 24.04 LTS)
```bash
# Обновление пакетов
sudo apt update && sudo apt upgrade -y

# Установка Docker и Nginx
sudo apt install -y curl git certbot python3-certbot-nginx nginx
curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh
sudo usermod -aG docker $USER
```

### 2. Клонирование репозитория
```bash
git clone https://github.com/your-username/ai-music-bot.git /opt/ai-music-bot
cd /opt/ai-music-bot
cp .env.example .env
nano .env # заполните токены и публичный домен
```

### 3. Настройка Nginx с SSL (Certbot)
Создайте конфиг `/etc/nginx/sites-available/aimusic`:
```nginx
server {
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 60M;
    }
}
```

Активируйте и выпустите бесплатный SSL-сертификат Let's Encrypt:
```bash
sudo ln -s /etc/nginx/sites-available/aimusic /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d your-domain.com
```

### 4. Запуск проекта
```bash
docker compose up -d
```

Бот готов к обработке входящих музыкальных треков!
