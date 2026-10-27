from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import urlsplit


class Settings(BaseSettings):
    app_name: str = "Спортивный клуб ТюмГУ"
    app_version: str = "0.1.0"
    app_debug: bool = False

    database_url: str
    database_echo: bool = False
    secret_key: str = "change-me-in-production"
    session_cookie_secure: bool = False
    production: bool = False
    render: bool = False
    render_external_url: str = ""
    public_base_url: str = ""
    csp_report_only: bool = False
    csp_captcha_report_only: bool = True
    request_limit_per_minute: int = Field(default=120, ge=1)
    registration_limit_per_minute: int = Field(default=10, ge=1)
    admin_login_account_limit: int = Field(default=5, ge=1)
    admin_login_ip_limit: int = Field(default=30, ge=1)
    admin_login_window_seconds: int = Field(default=900, ge=1)
    university_email_domain: str = "utmn.ru"
    app_timezone: str = "Asia/Yekaterinburg"
    captcha_enabled: bool = True
    smartcaptcha_client_key: str = ""
    smartcaptcha_server_key: SecretStr = SecretStr("")
    smartcaptcha_allowed_hosts: str = ""

    @property
    def secure_cookies(self) -> bool:
        return self.https_deployment or self.session_cookie_secure

    @property
    def https_deployment(self) -> bool:
        return self.production or self.render

    @property
    def external_url(self) -> str:
        return self.public_base_url or self.render_external_url

    def validate_production(self) -> None:
        if not self.https_deployment:
            return
        url = urlsplit(self.external_url)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "PUBLIC_BASE_URL должен содержать HTTPS-адрес сайта без пути."
            )
        if not self.production:
            return
        if self.app_debug or self.database_echo:
            raise ValueError("Для production отключите APP_DEBUG и DATABASE_ECHO.")
        if len(self.secret_key) < 32 or self.secret_key in {
            "change_me",
            "change-me-in-production",
        }:
            raise ValueError(
                "Для production задайте случайный SECRET_KEY от 32 символов."
            )
        if not self.captcha_enabled or not self.captcha_ready:
            raise ValueError("Для production настройте и включите SmartCaptcha.")
        if not self.smartcaptcha_client_key.startswith("ysc1_") or not (
            self.smartcaptcha_server_key.get_secret_value().startswith("ysc2_")
        ):
            raise ValueError(
                "Проверьте типы клиентского и серверного ключей SmartCaptcha."
            )
        if url.netloc.lower() not in self.captcha_allowed_hosts:
            raise ValueError(
                "Домен PUBLIC_BASE_URL отсутствует в SMARTCAPTCHA_ALLOWED_HOSTS."
            )

    @property
    def captcha_allowed_hosts(self) -> set[str]:
        return {
            host.strip().lower()
            for host in self.smartcaptcha_allowed_hosts.split(",")
            if host.strip()
        }

    @property
    def captcha_ready(self) -> bool:
        return bool(
            self.smartcaptcha_client_key.strip()
            and self.smartcaptcha_server_key.get_secret_value().strip()
            and self.captcha_allowed_hosts
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
