from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List

class Settings(BaseSettings):
    # App Settings
    PROJECT_NAME: str = "Skilled Agent Stack"
    API_V1_STR: str = "/api/v1"

    # LLM Settings
    GEMINI_API_KEY: str
    DEFAULT_MODEL: str = "gemini/gemini-2.0-flash"

    # Vector DB (RAG)
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: Optional[str] = None

    # Database
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/skilled_agent"

    # Security
    # Comma-separated list of allowed origins for CORS.
    # Example in .env:  ALLOWED_ORIGINS=http://localhost:3000,https://yourapp.com
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    # Max requests per minute per session_id before we return HTTP 429.
    RATE_LIMIT_RPM: int = 20
    # Max characters allowed in a single chat query.
    MAX_QUERY_LENGTH: int = 4000

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

settings = Settings()
