"""项目配置模块。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """统一管理环境变量，避免在代码中硬编码配置。"""

    app_name: str = "创新实践基地共享设备和物料管理智能体"
    app_env: str = "dev"
    database_url: str = "sqlite:///./smart_lab.db"

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

    # 指定读取 .env 文件，便于本地快速启动。
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# 创建全局配置实例，供项目各模块直接复用。
settings = Settings()
