# Развёртывание проекта

Нужны Linux-сервер с Docker Engine и Compose v2 и домен, направленный на сервер.
Откройте порты 80/443; порты 8000/5432 не публикуйте.
Все команды выполняйте из корня проекта по очереди. При ошибке не продолжайте.

## 1. Вставить тексты документов

| Файл | Что вставить |
| --- | --- |
| `app/documents/personal_data_consent.txt` | Утверждённый текст согласия на обработку персональных данных |
| `app/documents/privacy_policy.txt` | Утверждённый текст политики обработки персональных данных |

Сохраните файлы в UTF-8. Вставляйте обычный текст, без HTML: абзацы и переносы
строк сохранятся на сайте. Заголовки страниц уже есть, повторять их в файлах не нужно.
Укажите реальные реквизиты оператора и контакты в утверждённых текстах.

Больше ничего менять не нужно: ссылки и галочки подключены, текст показывается
автоматически. Ручного версионирования нет. Не начинайте приём заявок с пустыми
документами. После изменения текста пересоберите и перезапустите приложение
(`docker compose build app && docker compose up -d app`).

## 2. Заполнить окружение

Все три сервиса получают настройки через `env_file: .env`; `--env-file` не нужен.
Если файл уже есть, приведите его к production-шаблону — команда ниже его
не перезаписывает. Один файл, включая секреты, передаётся всем трём контейнерам.

```sh
test -f .env || cp deploy/production.env.example .env
chmod 600 .env
docker run --rm python:3.12-slim python -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_hex(32)); print('SECRET_KEY=' + secrets.token_hex(32))"
nano .env
```

| Переменная | Что указать |
| --- | --- |
| `DOMAIN` | Домен сайта без https, порта и пути |
| `ACME_EMAIL` | Рабочий email администратора для TLS-сертификата |
| `POSTGRES_PASSWORD`, `SECRET_KEY` | Два разных значения из команды генерации |
| `SMARTCAPTCHA_CLIENT_KEY` | Клиентский ключ Yandex SmartCaptcha, `ysc1_...` |
| `SMARTCAPTCHA_SERVER_KEY` | Серверный ключ SmartCaptcha, `ysc2_...` |
| `POSTGRES_USER`, `POSTGRES_DB` | Пользователь и имя новой БД; можно оставить `sportclub` |
| `UNIVERSITY_EMAIL_DOMAIN` | Разрешённый домен почты участников; сейчас `study.utmn.ru` |
| `APP_TIMEZONE` | Часовой пояс отображения; сейчас `Asia/Yekaterinburg` |
| `REQUEST_LIMIT_PER_MINUTE` | Запросы с одного IP в минуту; сейчас 120 |
| `REGISTRATION_LIMIT_PER_MINUTE` | Отправки заявок с одного IP в минуту; сейчас 10 |
| `ADMIN_LOGIN_ACCOUNT_LIMIT`, `ADMIN_LOGIN_IP_LIMIT` | Попытки входа на логин/IP; сейчас 5/30 |
| `ADMIN_LOGIN_WINDOW_SECONDS` | Окно ограничения входа в секундах; сейчас 900 |
| `CSP_CAPTCHA_REPORT_ONLY` | Сначала `true`, после проверки виджета переключить на `false` |
| `APP_NAME`, `APP_VERSION` | Название сайта и версия приложения |
| `PRODUCTION` | Обязательно `true` |
| `APP_DEBUG`, `DATABASE_ECHO` | Обязательно `false` |
| `SESSION_COOKIE_SECURE`, `CAPTCHA_ENABLED` | Обязательно `true` |
| `CSP_REPORT_ONLY` | Оставить `false` |
| `PUBLIC_BASE_URL`, `SMARTCAPTCHA_ALLOWED_HOSTS` | Уже собираются из `DOMAIN` в шаблоне |
| `DATABASE_URL` | Уже собирается из настроек БД; хост должен быть `postgres`, не `localhost` |

Создайте CAPTCHA в Yandex Cloud и разрешите тот же домен, что указан в `DOMAIN`.
Не отключайте проверку доменов. Секреты не добавляйте в Git.
Production-флаги, HTTPS-адрес и строка подключения теперь тоже находятся в `.env`.
Значения вида `${DOMAIN}` Compose подставит автоматически. Не используйте здесь
локальный `DATABASE_URL` с хостом `localhost`.

## 3. Проверить настройки и собрать образ

```sh
docker compose config --quiet
docker compose build
docker compose run --rm --no-deps app python -m scripts.check_deployment
```

Диагностика должна завершиться с кодом 0 без `configuration_error`.
Она проверяет настройки, но не реальные ключи и сертификат.

## 4. Создать новую БД

```sh
docker compose up -d postgres
```

PostgreSQL создаст новую БД автоматически. Данные сохраняются в Docker-томе.
Не выполняйте `docker compose down -v`: это удалит БД
и хранилище сертификатов. Настройте резервное копирование БД вне сервера.

## 5. Применить миграции и создать администратора

```sh
docker compose run --rm app alembic upgrade head
docker compose run --rm app python -m app.cli.create_admin --login admin
```

Введите пароль администратора дважды, минимум 12 символов.
Миграции нужно применять также перед запуском каждой обновлённой версии.

## 6. Запустить и проверить

```sh
docker compose up -d app proxy
docker compose ps
docker compose logs --tail=100 app proxy
```

Откройте `https://ВАШ-ДОМЕН` и `https://ВАШ-ДОМЕН/admin`, войдите под созданным
администратором. Caddy получает сертификат автоматически; при ошибках проверьте
DNS, порты 80/443 и логи `proxy`.

Проверьте расписание, индивидуальную и командную заявки с настоящей CAPTCHA,
согласия и Excel. Затем установите `CSP_CAPTCHA_REPORT_ONLY=false` и примените:

```sh
docker compose up -d app
```

Повторите заявку в браузере: CAPTCHA должна работать и без проверочного режима CSP.
Открывайте публичную регистрацию только после успешной проверки.
