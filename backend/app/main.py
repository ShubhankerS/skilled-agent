import logging
import io
from fastapi import FastAPI, HTTPException, UploadError, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.core.security import InputValidator, rate_limiter
from app.agents.master import MasterAgent
from app.agents.registry import get_registered_agents
from app.agents.base import AgentResponse
from app.models.memory import init_db

# Install structured JSON logging before anything else logs.
# From this point on, every logger.info/warning/error in the entire app
# emits a JSON object instead of a plain text string.
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# CORS — allows the frontend origin(s) to call this API from the browser.
# Origins are read from settings so they can differ per environment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core State
agents = get_registered_agents()
master = MasterAgent(agents)

@app.on_event("startup")
def on_startup():
    init_db()

class ChatRequest(BaseModel):
    query: str
    session_id: str = ""  # Empty triggers auto-generation of a UUID in the validator
    image_b64: Optional[str] = None

@app.get("/")
async def root():
    return {"status": "online", "project": settings.PROJECT_NAME}

@app.post(f"{settings.API_V1_STR}/chat")
async def chat(request: ChatRequest):
    """
    Stateful streaming chat endpoint with Multi-Modal support.
    Security checks run before the request reaches the agent layer.
    """
    # 1. Ensure session_id is a valid UUID (auto-generate if missing/invalid)
    session_id = InputValidator.validate_session_id(request.session_id)

    # 2. Rate limit: reject if this session has exceeded requests-per-minute
    if not rate_limiter.is_allowed(session_id):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please slow down."
        )

    # 3. Validate the query (length + injection patterns)
    try:
        query = InputValidator.validate_query(request.query)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return StreamingResponse(
        master.route_and_process_stream(query, session_id, request.image_b64),
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
        # Log the full exception internally for debugging, but never expose
        # internal details (file paths, DB strings, stack traces) to the caller.
        logger.error(f"Upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Document upload failed. Please try again.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
