from datetime import datetime, timezone
from typing import Optional, List, Dict
from sqlmodel import SQLModel, Field, create_engine, Session, select
from app.core.config import settings

def _utcnow() -> datetime:
    """Returns the current UTC time as a timezone-aware datetime object.
    Replaces the deprecated datetime.utcnow() which returned a naive datetime."""
    return datetime.now(timezone.utc)

class ChatMessage(SQLModel, table=True):
    """
    Relational model to store every interaction.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    role: str
    content: str
    source_agent: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)

class SessionHistory(SQLModel, table=True):
    """
    Meta info about a chat session.
    """
    session_id: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    last_updated: datetime = Field(default_factory=_utcnow)

# Database Engine
engine = create_engine(settings.DATABASE_URL)

def init_db():
    SQLModel.metadata.create_all(engine)
