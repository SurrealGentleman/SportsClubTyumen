# ССК «Ладья» — ТюмГУ

Сайт спортивного клуба: расписание секций, соревнования, индивидуальные и
командные заявки, админка и выгрузка участников в Excel.
Стек: Python 3.12, FastAPI, Jinja2, SQLAlchemy, PostgreSQL 17, Alembic, SQLAdmin.

## Что где находится

| Путь | Назначение |
| --- | --- |
| `app/main.py` | Сборка приложения, роутеров, админки и middleware |
| `app/routers/` | HTML-страницы и приём форм |
| `app/api/` | JSON API; `/api/v1/health` — доступность процесса, не проверка БД |
| `app/services/` | Правила заявок, серверная CAPTCHA, формирование Excel |
| `app/models/`, `app/schemas/` | Таблицы БД и проверка входных данных |
| `app/db/` | Подключение к БД, фабрика сессий и зависимости |
| `app/admin/` | Админка, вход, CSRF и политика ограничения входа |
| `app/core/` | Конфигурация, CSP/заголовки, лимиты, время, branding и согласия |
| `app/templates/`, `app/static/` | Шаблоны, CSS, JS и изображения |
| `app/documents/` | Два обычных UTF-8 текста: согласие и политика |
| `app/cli/create_admin.py` | Разовое создание администратора с интерактивным паролем |
| `migrations/`, `alembic.ini` | История изменений БД; не удалять при передаче |
| `tests/` | Безопасность и критические сценарии; не входят в образ |
| `scripts/check_deployment.py` | Ручная проверка production-настроек без секретов и соединения с БД |
| `deploy/` | Шаблон production-окружения и конфигурация Caddy/HTTPS |
| `Dockerfile`, `docker-compose.yml` | Production-образ и единственный Compose для сервера |

HTML формируется на сервере. Роутеры обращаются к сервисам и БД, шаблоны только
показывают данные. Синхронные операции БД выполняются вне event loop; сессия не
удерживается во время запроса CAPTCHA. Отдельный слой repositories не нужен
для текущего размера приложения.

## Что важно при сопровождении

- Основные адреса: `/`, `/schedule`, `/sports/{slug}`, `/competitions`, `/admin`.
- Slug создаётся автоматически; название команды уникально внутри соревнования.
  Для командного соревнования обязательны минимум и максимум участников.
- Даты со временем хранятся как UTC, показываются в `APP_TIMEZONE`
  (по умолчанию Тюмень, `Asia/Yekaterinburg`, UTC+5).
- Пути всех логотипов и favicon меняются в `app/core/branding.py`.
- Тексты документов вставляются в `app/documents/personal_data_consent.txt` и
  `app/documents/privacy_policy.txt` (обычный UTF-8, без HTML). Сейчас файлы пустые;
  заполните их до приёма заявок. Код и номера версий менять не нужно: идентификатор
  согласия вычисляется автоматически из текста. Заявка хранит дату и точную копию
  принятого согласия; последующие изменения файлов не меняют старые заявки.
- Защита: CSRF админки и POST-выход, Argon2, лимиты входа/форм в общей БД,
  SmartCaptcha, security headers и CSP. HTTPS/Secure-cookie обязательны в production.
- `scripts/check_deployment.py` проверяет конфигурацию перед запуском Uvicorn
  в Compose и блокирует старт без production-настроек; его можно запустить
  отдельно при установке и обновлениях. Постоянным процессом он не работает.
  Старый `security_audit.py` удалён: его проверки SQL-инъекций перенесены в тесты.

## Локальный запуск и проверки

Скопируйте `.env.example` в `.env`, укажите подключение к отдельно запущенной
локальной PostgreSQL в `DATABASE_URL`. Для локальной работы без CAPTCHA явно
задайте `CAPTCHA_ENABLED=false`. Секреты не коммитить.
Compose в репозитории предназначен только для production.

```sh
poetry install --no-root
poetry run alembic upgrade head
poetry run python -m app.cli.create_admin --login admin
poetry run uvicorn app.main:app --reload
poetry run pytest -q
poetry run ruff check .
```

Адрес: `http://localhost:8000`. Для браузерной проверки CSP установите Chrome и задайте
`RUN_CSP_BROWSER=1` (при необходимости `CHROME_BIN` — путь к браузеру).
Тесты используют отдельную SQLite, а не рабочую PostgreSQL.

Для production используется тот же путь `.env`, но шаблон
`deploy/production.env.example`. Compose автоматически читает этот файл из
корня проекта через `env_file: .env` для всех трёх сервисов, включая секреты;
передавать `--env-file` не нужно. Все параметры приложения перечислены в шаблоне.
Настройки локальной разработки и production не смешивайте: внутри Docker хост
БД — `postgres`, а `PRODUCTION=true`.
Порядок production-развёртывания: [DEPLOYMENT.md](DEPLOYMENT.md).
