"""
Append-only audit trail.

Every request that reaches the agent layer gets one audit record written here.
The record captures: session, query, routing decision, tools used, RAG sources
cited, which agent responded, and how long everything took.

Why a flat JSONL file?
  - Append-only: we only ever write new lines, never edit or delete.
    This is the key property of an audit trail — immutability.
  - JSONL (JSON Lines): one JSON object per line. Human-readable with
    `tail -f`, grep-able, and loadable into any analytics tool or SIEM.
  - Independent of the database: if Postgres is down, requests can still
    be audited. The audit trail is the last line of accountability.

Format of each record:
  {
    "timestamp":   "2026-03-25T10:23:01.123Z",
    "session_id":  "a1b2c3d4-...",
    "query":       "What is quantum entanglement?",  # first 200 chars only
    "agent":       "researcher",
    "tools_used":  ["WEB_SEARCH"],
    "rag_sources": [{"source": "physics_101.pdf", "chunk": 2}, ...],
    "duration_ms": 1843,
    "status":      "ok"   # or "error" / "timeout"
  }
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Default audit log path. Override via AUDIT_LOG_PATH env var for production.
_DEFAULT_AUDIT_PATH = os.environ.get("AUDIT_LOG_PATH", "audit.jsonl")


def write_audit_record(
    session_id: str,
    query: str,
    agent: str,
    tools_used: List[str],
    rag_sources: List[Dict[str, Any]],
    duration_ms: int,
    status: str = "ok",
    audit_path: Optional[str] = None,
) -> None:
    """
    Appends one audit record to the JSONL audit file.

    Args:
        session_id:  The validated UUID session identifier.
        query:       The user's query (truncated to 200 chars for the record).
        agent:       Name of the agent that handled the request.
        tools_used:  List of tool names that were invoked (e.g. ["WEB_SEARCH"]).
        rag_sources: List of metadata dicts from the RAG chunks that were retrieved.
                     Each dict typically has {"source": filename, "chunk": index}.
        duration_ms: Total request processing time in milliseconds.
        status:      "ok", "error", or "timeout".
        audit_path:  Override the file path (used in tests to write to a temp file).
    """
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "query": query[:200],   # cap at 200 chars — enough for audit, not full storage
        "agent": agent,
        "tools_used": tools_used,
        "rag_sources": rag_sources,
        "duration_ms": duration_ms,
        "status": status,
    }

    path = audit_path or _DEFAULT_AUDIT_PATH

    try:
        # "a" mode: append only — never overwrites existing records
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as e:
        # Audit write failure must never crash the main request path.
        # Log the error and continue — the user still gets their response.
        logger.error(f"Failed to write audit record: {e}", exc_info=True)
