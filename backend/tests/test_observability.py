"""
Tests for the observability layer: structured logging, audit trail.
"""
import json
import logging
import os
import tempfile
import uuid
import pytest
from app.core.logging_config import JsonFormatter, setup_logging
from app.core.audit import write_audit_record


class TestJsonFormatter:
    def _make_record(self, msg, level=logging.INFO, extra=None):
        """Helper: create a LogRecord the way logging does internally."""
        record = logging.LogRecord(
            name="app.test",
            level=level,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        if extra:
            for k, v in extra.items():
                setattr(record, k, v)
        return record

    def test_output_is_valid_json(self):
        formatter = JsonFormatter()
        record = self._make_record("hello world")
        output = formatter.format(record)
        parsed = json.loads(output)   # raises if invalid JSON
        assert parsed["message"] == "hello world"

    def test_standard_fields_present(self):
        formatter = JsonFormatter()
        record = self._make_record("test event")
        parsed = json.loads(formatter.format(record))
        assert "timestamp" in parsed
        assert "level" in parsed
        assert "logger" in parsed
        assert "message" in parsed

    def test_extra_fields_included(self):
        formatter = JsonFormatter()
        record = self._make_record("routing", extra={"session_id": "abc-123", "agent": "researcher"})
        parsed = json.loads(formatter.format(record))
        assert parsed["session_id"] == "abc-123"
        assert parsed["agent"] == "researcher"

    def test_level_name_correct(self):
        formatter = JsonFormatter()
        for level, name in [(logging.INFO, "INFO"), (logging.WARNING, "WARNING"), (logging.ERROR, "ERROR")]:
            record = self._make_record("msg", level=level)
            parsed = json.loads(formatter.format(record))
            assert parsed["level"] == name

    def test_timestamp_is_iso8601(self):
        from datetime import datetime
        formatter = JsonFormatter()
        record = self._make_record("ts test")
        parsed = json.loads(formatter.format(record))
        # Should parse without error
        datetime.fromisoformat(parsed["timestamp"])


class TestAuditTrail:
    def test_writes_valid_jsonl_record(self, fresh_session_id, tmp_path):
        audit_file = str(tmp_path / "test_audit.jsonl")
        write_audit_record(
            session_id=fresh_session_id,
            query="What is DNA?",
            agent="researcher",
            tools_used=["WEB_SEARCH"],
            rag_sources=[{"source": "biology.pdf", "chunk": 0}],
            duration_ms=523,
            audit_path=audit_file,
        )
        with open(audit_file) as f:
            lines = f.readlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["session_id"] == fresh_session_id
        assert record["agent"] == "researcher"
        assert record["tools_used"] == ["WEB_SEARCH"]
        assert record["duration_ms"] == 523
        assert record["status"] == "ok"

    def test_multiple_records_appended(self, fresh_session_id, tmp_path):
        audit_file = str(tmp_path / "multi.jsonl")
        for i in range(3):
            write_audit_record(
                session_id=fresh_session_id,
                query=f"query {i}",
                agent="researcher",
                tools_used=[],
                rag_sources=[],
                duration_ms=100 * i,
                audit_path=audit_file,
            )
        with open(audit_file) as f:
            lines = f.readlines()
        assert len(lines) == 3
        # Each line is independent valid JSON
        for line in lines:
            json.loads(line)

    def test_query_truncated_to_200_chars(self, fresh_session_id, tmp_path):
        audit_file = str(tmp_path / "trunc.jsonl")
        long_query = "x" * 500
        write_audit_record(
            session_id=fresh_session_id,
            query=long_query,
            agent="researcher",
            tools_used=[],
            rag_sources=[],
            duration_ms=0,
            audit_path=audit_file,
        )
        with open(audit_file) as f:
            record = json.loads(f.read())
        assert len(record["query"]) == 200

    def test_rag_sources_recorded(self, fresh_session_id, tmp_path):
        audit_file = str(tmp_path / "rag.jsonl")
        sources = [
            {"source": "paper1.pdf", "chunk": 0},
            {"source": "paper1.pdf", "chunk": 1},
            {"source": "notes.txt", "chunk": 2},
        ]
        write_audit_record(
            session_id=fresh_session_id,
            query="test",
            agent="researcher",
            tools_used=[],
            rag_sources=sources,
            duration_ms=0,
            audit_path=audit_file,
        )
        with open(audit_file) as f:
            record = json.loads(f.read())
        assert record["rag_sources"] == sources

    def test_error_status_recorded(self, fresh_session_id, tmp_path):
        audit_file = str(tmp_path / "err.jsonl")
        write_audit_record(
            session_id=fresh_session_id,
            query="test",
            agent="unknown",
            tools_used=[],
            rag_sources=[],
            duration_ms=0,
            status="error",
            audit_path=audit_file,
        )
        with open(audit_file) as f:
            record = json.loads(f.read())
        assert record["status"] == "error"

    def test_write_failure_does_not_raise(self, fresh_session_id):
        """Audit write failure must never crash the main request path."""
        write_audit_record(
            session_id=fresh_session_id,
            query="test",
            agent="researcher",
            tools_used=[],
            rag_sources=[],
            duration_ms=0,
            audit_path="/nonexistent_dir/audit.jsonl",  # will fail silently
        )
        # If we reach here without an exception, the test passes


class TestTokenBudget:
    """Eval cases: does the token budget correctly protect context window?"""

    def test_small_messages_pass_through_unchanged(self):
        from app.core.reliability import TokenBudget
        budget = TokenBudget(model="gpt-3.5-turbo", max_tokens=8192)
        msgs = [
            {"role": "system", "content": "You are an assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "What is 2+2?"},
        ]
        assert budget.enforce(msgs) == msgs

    def test_oversized_history_trimmed(self):
        from app.core.reliability import TokenBudget
        budget = TokenBudget(model="gpt-3.5-turbo", max_tokens=300)
        history = [{"role": "user", "content": "history " * 20} for _ in range(10)]
        msgs = [{"role": "system", "content": "sys"}, *history, {"role": "user", "content": "current"}]
        result = budget.enforce(msgs)
        assert result[0]["role"] == "system"
        assert result[-1]["content"] == "current"
        assert len(result) < len(msgs)
