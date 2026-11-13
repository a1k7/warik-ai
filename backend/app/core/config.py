
from functools import lru_cache

from pydantic import Field, model_validator
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
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

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
    # Worldwide OpenStreetMap-based travel discovery
    nominatim_url: str = "https://nominatim.openstreetmap.org/search"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    geo_user_agent: str = "WarikAI/1.0 (travel planning; configure contact details)"
    geo_timeout_seconds: float = Field(default=12.0, gt=0, le=60)
    overpass_timeout_seconds: float = Field(default=25.0, gt=0, le=90)
    nominatim_min_interval_seconds: float = Field(default=1.1, ge=1.0, le=10.0)

    # Legacy optional provider key retained for backward compatibility.
    geoapify_api_key: str = ""
    duffel_api_key: str = ""
    stayapi_key: str = ""
    reef_api_key: str = ""

    # External commerce integrations. Disabled or mock by default.
    swiggy_token_encryption_key: str = ""
    swiggy_client_id: str = ""
    swiggy_redirect_uri: str = "http://localhost:8000/api/integrations/swiggy/oauth/callback"
    swiggy_frontend_return_url: str = "http://localhost:5173/settings"
    swiggy_authorize_url: str = "https://mcp.swiggy.com/auth/authorize"
    swiggy_token_url: str = "https://mcp.swiggy.com/auth/token"
    swiggy_logout_url: str = "https://mcp.swiggy.com/auth/logout"
    swiggy_oauth_scope: str = "mcp:tools"
    swiggy_mode: str = "mock"
    swiggy_food_mcp_url: str = "https://mcp.swiggy.com/food"
    swiggy_instamart_mcp_url: str = "https://mcp.swiggy.com/im"
    swiggy_dineout_mcp_url: str = "https://mcp.swiggy.com/dineout"
    swiggy_scenes_mcp_url: str = "https://mcp.swiggy.com/scenes"

    # Agoda: affiliate handoff only until approved partner access exists.
    agoda_mode: str = "redirect_only"
    agoda_affiliate_url: str = ""
    agoda_affiliate_id: str = ""
    agoda_api_key: str = ""

    # Booking.com Demand API: disabled until partner access is approved.
    booking_mode: str = "disabled"
    booking_api_base_url: str = ""
    booking_api_token: str = ""
    booking_affiliate_id: str = ""

    @model_validator(mode="after")
    def validate_runtime_configuration(self):
        provider = self.llm_provider.strip().lower()

        if provider not in {"ollama", "groq"}:
            raise ValueError("LLM_PROVIDER must be 'ollama' or 'groq'.")

        if self.environment.strip().lower() == "production":
            if (
                self.jwt_secret == "dev-only-secret-change-me"
                or len(self.jwt_secret) < 32
            ):
                raise ValueError(
                    "Production requires a JWT_SECRET of at least 32 characters."
                )

            if provider == "groq" and not self.groq_api_key.strip():
                raise ValueError(
                    "GROQ_API_KEY is required when LLM_PROVIDER=groq."
                )

            database_url = self.database_url.strip().lower()
            if not database_url.startswith(
                (
                    "postgres://",
                    "postgresql://",
                    "postgresql+psycopg://",
                )
            ):
                raise ValueError(
                    "Production requires PostgreSQL; SQLite is not allowed."
                )

            origins = self.cors_origin_list

            if not origins or "*" in origins:
                raise ValueError(
                    "Production requires explicit CORS_ORIGINS; "
                    "wildcard or empty origins are not allowed."
                )

            if any(not origin.startswith("https://") for origin in origins):
                raise ValueError(
                    "Production CORS origins must use HTTPS."
                )

        return self

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
