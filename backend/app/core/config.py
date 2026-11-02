from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Warik AI"
    environment: str = "development"

    database_url: str = "sqlite:///./warik.db"
    cors_origins: str = "http://localhost:5173"

    # Auth
    jwt_secret: str = "dev-only-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    # Gnani AI (backend-only)
    gnani_api_key: str = ""
    gnani_org_id: str = ""
    gnani_user_id: str = ""
    gnani_stt_url: str = "https://api.vachana.ai/stt/v3"
    gnani_tts_url: str = "https://api.gnani.ai/v1/tts/inference"
    gnani_tts_model: str = "timbre"
    gnani_tts_voice: str = "Pranav"
    gnani_tts_language: str = "en-IN"
    
    # Voice feature flags
    voice_enabled: bool = True
    voice_max_upload_bytes: int = 5 * 1024 * 1024
    voice_max_duration_seconds: int = 30
    voice_usage_limit_seconds: int = 300
    voice_tts_char_limit: int = 2000

    # LLM Providers
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:latest"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Travel APIs
    duffel_api_key: str = ""
    stayapi_key: str = ""
    geoapify_api_key: str = ""  # <-- ADDED THIS
    ola_maps_api_key: str = ""

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