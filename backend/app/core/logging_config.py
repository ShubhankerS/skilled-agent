"""
Structured JSON logging configuration.

Why JSON logs?
  Plain text logs like "INFO:app.master:routing decision agent=researcher"
  are readable in a terminal but not queryable. Log aggregation tools
  (Datadog, Grafana Loki, CloudWatch) need structured data to answer
  questions like "how many requests were routed to the researcher agent
  in the last hour?" or "which sessions had errors today?"

  With JSON logs, every field is a first-class queryable attribute.

Usage:
  Call setup_logging() once at application startup (in main.py).
  Then use logging normally anywhere in the codebase:

    logger = logging.getLogger(__name__)
    logger.info("routing_decision", extra={"agent": "researcher", "session_id": "abc"})

  This emits:
    {"timestamp": "2026-03-25T10:23:01.123Z", "level": "INFO",
     "logger": "app.agents.master", "message": "routing_decision",
     "agent": "researcher", "session_id": "abc"}
"""
import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """
    Formats a LogRecord as a single-line JSON object.

    Standard fields always present:
      timestamp  — ISO 8601 UTC
      level      — DEBUG / INFO / WARNING / ERROR / CRITICAL
      logger     — dotted module name (e.g. "app.agents.master")
      message    — the formatted log message

    Extra fields:
      Any key=value pairs passed via the `extra` dict on a log call are
      merged into the JSON object. This is how callers add context like
      session_id, agent_name, duration_ms, etc.
    """

    # These are standard LogRecord attributes — we handle them explicitly
    # and exclude them from the "extra" passthrough to avoid duplication.
    _STANDARD_ATTRS = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "message",
        "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()

        obj: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
        }

        # Include exception info if present
        if record.exc_info:
            obj["exception"] = self.formatException(record.exc_info)

        # Merge any extra fields the caller passed
        for key, value in record.__dict__.items():
            if key not in self._STANDARD_ATTRS:
                obj[key] = value

        return json.dumps(obj, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    """
    Installs JSON structured logging on the root logger.
    Call this once at application startup before any other imports that log.

    Args:
        level: The minimum log level to emit. Defaults to INFO.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Remove any existing handlers (e.g. basicConfig defaults)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # Silence noisy third-party libraries at WARNING+ only
    # LiteLLM and httpx log a lot of request detail at INFO which clutters output
    for noisy_lib in ("LiteLLM", "httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy_lib).setLevel(logging.WARNING)
