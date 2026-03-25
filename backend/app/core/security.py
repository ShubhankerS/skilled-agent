"""
Security module: input validation and rate limiting.

Two responsibilities:
  1. InputValidator  — rejects malformed or malicious chat inputs before they
                       reach the agent layer.
  2. RateLimiter     — enforces a per-session sliding-window request cap so
                       no single session can exhaust the LLM budget.
"""
import re
import time
import uuid
import logging
from collections import deque, defaultdict
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt injection patterns
# These are phrases commonly used to try to override a system prompt.
# The list is intentionally conservative — we match on lower-cased input.
# ---------------------------------------------------------------------------
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"disregard\s+(all\s+)?(previous\s+)?instructions",
        r"you\s+are\s+now\s+",
        r"forget\s+(everything|all)\s+",
        r"new\s+instructions?\s*:",
        r"system\s*prompt\s*:",
        r"reveal\s+(your\s+)?(system\s+)?prompt",
        r"print\s+(your\s+)?(system\s+)?instructions",
        r"override\s+(your\s+)?instructions",
    ]
]


class InputValidator:
    """
    Validates a chat query before it is processed by the agent layer.
    Raises ValueError with a user-safe message if validation fails.
    """

    @staticmethod
    def validate_query(query: str) -> str:
        """
        Checks query length and scans for prompt injection patterns.
        Returns the (stripped) query if valid, raises ValueError if not.
        """
        query = query.strip()

        if not query:
            raise ValueError("Query cannot be empty.")

        if len(query) > settings.MAX_QUERY_LENGTH:
            raise ValueError(
                f"Query is too long. Maximum allowed length is {settings.MAX_QUERY_LENGTH} characters."
            )

        for pattern in _INJECTION_PATTERNS:
            if pattern.search(query):
                logger.warning("Prompt injection attempt detected and blocked.")
                raise ValueError("Your message contains patterns that are not allowed.")

        return query

    @staticmethod
    def validate_session_id(session_id: str) -> str:
        """
        Ensures session_id is a valid UUID string.
        If empty or invalid, generates and returns a fresh UUID.

        Why UUIDs? They are random enough to be unguessable and have a
        well-defined format, making path traversal attacks impossible.
        """
        if not session_id or session_id == "default-session":
            new_id = str(uuid.uuid4())
            logger.info(f"Generated new session_id: {new_id}")
            return new_id

        try:
            uuid.UUID(session_id)
            return session_id
        except ValueError:
            new_id = str(uuid.uuid4())
            logger.warning(
                f"Invalid session_id format received; replaced with new UUID: {new_id}"
            )
            return new_id


class RateLimiter:
    """
    In-memory sliding-window rate limiter keyed by session_id.

    How it works:
      - Each session has a deque (double-ended queue) of request timestamps.
      - On each request, old timestamps outside the 60-second window are
        dropped from the left of the deque.
      - If the deque length >= RATE_LIMIT_RPM, the request is rejected.
      - Otherwise the current timestamp is appended and the request proceeds.

    Trade-off: This is in-memory and per-process. In a multi-worker deployment
    you would use Redis instead. Fine for single-process development and
    staging; note this limitation before horizontal scaling.
    """

    _WINDOW_SECONDS = 60

    def __init__(self):
        # defaultdict means accessing a missing key auto-creates an empty deque
        self._requests: defaultdict[str, deque] = defaultdict(deque)

    def is_allowed(self, session_id: str) -> bool:
        """
        Returns True if the session is within the rate limit, False if exceeded.
        Side effect: records this request timestamp if allowed.
        """
        now = time.monotonic()
        window = self._requests[session_id]

        # Drop timestamps older than the sliding window
        while window and now - window[0] > self._WINDOW_SECONDS:
            window.popleft()

        if len(window) >= settings.RATE_LIMIT_RPM:
            logger.warning(f"Rate limit exceeded for session: {session_id}")
            return False

        window.append(now)
        return True


# Module-level singleton — one rate limiter shared across all requests
rate_limiter = RateLimiter()
