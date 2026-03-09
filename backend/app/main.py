import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional

from app.core.config import settings
from app.agents.master import MasterAgent
from app.agents.registry import get_registered_agents
from app.agents.base import AgentResponse
from app.models.memory import init_db

# Initialize Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# Core State
agents = get_registered_agents()
master = MasterAgent(agents)

@app.on_event("startup")
def on_startup():
    init_db()

class ChatRequest(BaseModel):
    query: str
    session_id: str = "default-session"

@app.get("/")
async def root():
    return {"status": "online", "project": settings.PROJECT_NAME}

@app.post(f"{settings.API_V1_STR}/chat", response_model=AgentResponse)
async def chat(request: ChatRequest):
    """
    Stateful chat endpoint.
    """
    try:
        response = await master.route_and_process(request.query, request.session_id)
        return response
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
