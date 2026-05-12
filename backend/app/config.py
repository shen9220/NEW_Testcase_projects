from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # AI
    deepseek_api_key: str = ""

    # Server
    port: int = 8000
    hostname: str = "localhost"

    # Data directory (relative to backend/)
    data_dir: str = "data"

    model_config = {
        "env_file": ".env",
        "env_prefix": "COZE_",
        "extra": "ignore",
    }


settings = Settings()
