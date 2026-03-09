from typing import List, Dict
from sqlmodel import Session, select
from app.models.memory import engine, ChatMessage, SessionHistory

class MemoryManager:
    """
    Handles fetching and storing chat history to PostgreSQL.
    """
    @staticmethod
    def get_history(session_id: str, limit: int = 10) -> List[Dict[str, str]]:
        with Session(engine) as session:
            statement = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.desc()).limit(limit)
            results = session.exec(statement).all()
            # Return in chronological order
            return [{"role": m.role, "content": m.content} for m in reversed(results)]

    @staticmethod
    def add_message(session_id: str, role: str, content: str, source_agent: str = None):
        with Session(engine) as session:
            msg = ChatMessage(session_id=session_id, role=role, content=content, source_agent=source_agent)
            session.add(msg)
            session.commit()
