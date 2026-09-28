from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Спортивный клуб ТюмГУ"
    app_version: str = "0.1.0"
    app_debug: bool = False

    database_url: str
    database_echo: bool = False
    secret_key: str = "change-me-in-production"
    session_cookie_secure: bool = False
    university_email_domain: str = "utmn.ru"
    app_timezone: str = "Asia/Yekaterinburg"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
