import logging
import io
from fastapi import FastAPI, HTTPException, UploadError, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter

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

@app.post(f"{settings.API_V1_STR}/chat")
async def chat(request: ChatRequest):
    """
    Stateful streaming chat endpoint.
    """
    return StreamingResponse(
        master.route_and_process_stream(request.query, request.session_id),
        media_type="text/event-stream"
    )

@app.post(f"{settings.API_V1_STR}/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Uploads and indexes a PDF or Text document for RAG.
    """
    try:
        content = ""
        if file.content_type == "application/pdf":
            pdf = PdfReader(io.BytesIO(await file.read()))
            for page in pdf.pages:
                content += page.extract_text()
        else:
            content = (await file.read()).decode("utf-8")

        # Chunking
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        chunks = text_splitter.split_text(content)

        # Indexing
        metadata = [{"source": file.filename, "chunk": i} for i in range(len(chunks))]
        await master.rag.embed_and_store(chunks, metadata)

        return {"status": "success", "chunks_indexed": len(chunks)}
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
