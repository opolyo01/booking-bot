from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    app_name: str = "Booking Bot"
    debug: bool = False
    secret_key: str

    database_url: str
    redis_url: str

    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    google_calendar_id: str = "primary"
    google_owner_email: str  # your email — only this account gets admin access

    pinecone_api_key: str
    pinecone_index_name: str = "booking-bot"

    anthropic_api_key: str
    openai_api_key: str  # used for text-embedding-3-small only

    resend_api_key: str
    from_email: str

    vapi_api_key: str
    vapi_webhook_secret: str

    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
