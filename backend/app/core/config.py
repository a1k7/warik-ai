
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Warik AI"
    environment: str = "development"
    database_url: str = "sqlite:///./warik.db"
    cors_origins: str = "http://localhost:5173"

    # Authentication
    jwt_secret: str = "dev-only-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    # Gnani AI — Speech services
    gnani_api_key: str = ""
    gnani_org_id: str = ""
    gnani_user_id: str = ""
    gnani_stt_url: str = "https://api.vachana.ai/stt/v3"
    gnani_tts_url: str = "https://api.gnani.ai/v1/tts/inference"

    voice_enabled: bool = False
    voice_usage_limit_seconds: int = Field(default=300, gt=0)

    # Voice upload and processing limits
    voice_max_upload_bytes: int = Field(
        default=10 * 1024 * 1024,
        gt=0,
    )
    voice_max_duration_seconds: int = Field(
        default=120,
        gt=0,
    )
    voice_tts_char_limit: int = Field(
        default=1000,
        gt=0,
    )

    # LLM
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:latest"

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Travel and food integrations
    geoapify_api_key: str = ""
    duffel_api_key: str = ""
    stayapi_key: str = ""
    reef_api_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
