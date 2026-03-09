from datetime import datetime
from typing import Optional, List, Dict
from sqlmodel import SQLModel, Field, create_engine, Session, select
from app.core.config import settings

class ChatMessage(SQLModel, table=True):
    """
    Relational model to store every interaction.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    role: str # 'user' or 'assistant'
    content: str
    source_agent: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class SessionHistory(SQLModel, table=True):
    """
    Meta info about a chat session.
    """
    session_id: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

# Database Engine
engine = create_engine(settings.DATABASE_URL)

def init_db():
    SQLModel.metadata.create_all(engine)
