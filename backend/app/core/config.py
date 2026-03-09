from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # App Settings
    PROJECT_NAME: str = "Skilled Agent Stack"
    API_V1_STR: str = "/api/v1"
    
    # LLM Settings
    GEMINI_API_KEY: str
    DEFAULT_MODEL: str = "gemini/gemini-2.0-flash" # The fastest modern model
    
    # Vector DB (RAG)
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: Optional[str] = None
    
    # Database
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/skilled_agent"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

settings = Settings()
