# Спортивный клуб ТюмГУ

Монолитное FastAPI-приложение для расписания тренировок, публикации соревнований
и приёма заявок студентов ТюмГУ. Реализованы backend-каркас, конфигурация
PostgreSQL, модели SQLAlchemy, Alembic, Docker Compose и защищённая панель SQLAdmin.

## Стек

- Python 3.12+
- FastAPI
- PostgreSQL и psycopg 3
- SQLAlchemy 2.x
- Alembic
- SQLAdmin
- Poetry
- Docker Compose

## Подготовка окружения

```powershell
Copy-Item .env.example .env
poetry install --no-root
```

Перед использованием вне локальной разработки замените `POSTGRES_PASSWORD` и
`SECRET_KEY` в `.env`.

## Локальный запуск

Запустите PostgreSQL:

```powershell
docker compose up -d postgres
```

Примените миграции и запустите приложение:

```powershell
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload
```

Health endpoint: `GET http://localhost:8000/api/v1/health`.

## Публичные страницы

- `/` — главная страница клуба;
- `/schedule` — активные спортивные направления;
- `/sports/{slug}` — расписание выбранной секции;
- `/competitions` — опубликованные соревнования;
- `/competitions/{slug}` — информация о соревновании.
- `/competitions/{slug}/register` — индивидуальная или командная заявка.

Страницы формируются на сервере через Jinja2, используют Bootstrap 5 и получают
расписание и соревнования из базы данных. Наполнение создаётся через `/admin`.

## Административная панель

После применения миграций создайте первого администратора. Пароль запрашивается
интерактивно и не сохраняется в истории терминала:

```powershell
poetry run python -m app.cli.create_admin --login admin
```

Панель доступна по адресу `http://localhost:8000/admin`. В ней можно управлять
видами спорта, тренировками, соревнованиями, заявками и участниками заявок.
В списке соревнований выберите одну строку и нажмите «Выгрузить заявки в Excel».
Файл содержит отдельную строку для каждого участника команды; для индивидуальной
заявки поле «Команда» остаётся пустым. Название и параметры соревнования вынесены
в шапку отчёта, а общие ячейки командной заявки объединяются на все строки её
участников.

Slug вида спорта и соревнования создаётся автоматически из названия. При
совпадении к адресу добавляется числовой суффикс. Название команды уникально в
рамках одного соревнования без учёта регистра букв.

Все даты со временем хранятся в PostgreSQL как точные моменты времени в UTC.
Админка, публичные страницы и Excel-файлы вводят и показывают их в часовом поясе
Тюмени `Asia/Yekaterinburg` (UTC+5). Его можно изменить через `APP_TIMEZONE`.

Для production-развёртывания с HTTPS установите в `.env`:

```env
SESSION_COOKIE_SECURE=true
```

## Запуск через Docker Compose

```powershell
docker compose up --build
```

Сервис `app` ожидает готовности `postgres`, применяет миграции и запускает Uvicorn
на `http://localhost:8000`.

## Проверки

```powershell
poetry run pytest
poetry run ruff check .
poetry run ruff format . --check
poetry run alembic upgrade head --sql
docker compose config --quiet
```

## Модели первого этапа

- `Sport` — вид спорта;
- `Training` — тренировка и её группа;
- `Competition` — соревнование с индивидуальной или командной регистрацией;
- `Registration` — заявка;
- `RegistrationMember` — участник заявки;
- `Admin` — администратор с хешем пароля.

Публичные пользовательские аккаунты и OAuth не используются. Дополнительная
полировка интерфейса относится к следующему этапу.
