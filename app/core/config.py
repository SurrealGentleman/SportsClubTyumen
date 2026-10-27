from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Спортивный клуб ТюмГУ"
    app_version: str = "0.1.0"
    app_debug: bool = False

    database_url: str
    database_echo: bool = False
    secret_key: str = "change-me-in-production"
    session_cookie_secure: bool = False
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
