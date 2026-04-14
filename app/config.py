"""Application settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized environment-backed configuration."""

    app_name: str = "创新实践基地共享设备和物料管理智能体"
    app_env: str = "dev"
    database_url: str = "sqlite:///./smart_lab.db"

    jwt_secret: str = "change-me-in-env"
    jwt_expire_minutes: int = 720

    qiniu_access_key: str = ""
    qiniu_secret_key: str = ""
    qiniu_bucket: str = ""
    qiniu_domain: str = ""
    qiniu_upload_token_expire: int = 3600

    llm_enabled: bool = True
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout: int = 30

    alert_dedup_window_seconds: int = 300
    notify_in_app_enabled: bool = True
    notify_webhook_enabled: bool = False
    notify_webhook_url: str = ""
    notify_timeout: int = 5
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 1000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
