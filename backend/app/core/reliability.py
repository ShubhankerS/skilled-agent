"""
Reliability module: token budget enforcement and timeout constants.

Responsibilities:
  1. TokenBudget — counts tokens in a message list and trims conversation
                   history if the total would exceed the model's context window.
  2. TIMEOUT_*   — named constants for every external call timeout so they
                   are set in one place and easy to tune.
"""
import logging
from typing import List, Dict, Any

import litellm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timeout constants (seconds)
# Every external I/O call should be wrapped in asyncio.wait_for() with one
# of these values. Centralising them here means tuning is a one-line change.
# ---------------------------------------------------------------------------
TIMEOUT_LLM_ROUTING = 15    # routing decision call — should be fast
TIMEOUT_LLM_RESPONSE = 60   # streaming response call — may take longer
TIMEOUT_WEB_SEARCH = 10     # DuckDuckGo — fail fast if down
TIMEOUT_RAG_QUERY = 10      # Qdrant vector search


class TokenBudget:
    """
    Enforces a token budget on a message list before it is sent to the LLM.

    Strategy:
      The assembled message list has three logical parts:
        1. System prompt  — never trimmed (essential instructions + RAG context)
        2. History        — trimmed oldest-first until budget is met
        3. Current user message — never trimmed (it's the thing being answered)

    We count total tokens. If over budget, we drop history messages from the
    oldest end (index 1 onward, skipping the system message at index 0)
    until we're within the limit or history is exhausted.

    Why not trim RAG context?
      RAG chunks are the most relevant retrieved knowledge for this specific
      query. Losing them degrades answer quality more than losing old history.
    """

    # Leave headroom for the model's response tokens.
    # Most models have a combined input+output limit; we reserve this for output.
    RESPONSE_BUFFER = 1000
    # Small fuzz factor because token counters can be slightly off
    COUNT_BUFFER = 100

    def __init__(self, model: str, max_tokens: int = 8192):
        """
        Args:
            model:      The LiteLLM model string (e.g. "gemini/gemini-2.0-flash").
                        Used to select the correct tokenizer.
            max_tokens: The model's context window size in tokens.
                        Gemini 2.0 Flash supports 1M tokens, but we default
                        conservatively to 8192 for cost control.
        """
        self.model = model
        self.budget = max(0, max_tokens - self.RESPONSE_BUFFER - self.COUNT_BUFFER)

    def _count(self, messages: List[Dict]) -> int:
        """Counts tokens in a message list using LiteLLM's tokenizer."""
        try:
            return litellm.token_counter(model=self.model, messages=messages)
        except Exception:
            # If the tokenizer fails (e.g. unknown model), estimate conservatively:
            # ~4 characters per token is a reasonable average for English text.
            total_chars = sum(len(str(m.get("content", ""))) for m in messages)
            return total_chars // 4

    def enforce(self, messages: List[Dict]) -> List[Dict]:
        """
        Returns a (possibly trimmed) copy of messages that fits within budget.

        The message list structure expected:
          messages[0]  = system message (always kept)
          messages[1:-1] = history turns (trimmed from oldest if needed)
          messages[-1] = current user message (always kept)

        If there are fewer than 3 messages, returns as-is.
        """
        if len(messages) < 3:
            return messages

        total = self._count(messages)
        if total <= self.budget:
            return messages

        system_msg = messages[0]
        user_msg = messages[-1]
        history = list(messages[1:-1])  # copy so we don't mutate the original

        trimmed = 0
        while history and self._count([system_msg] + history + [user_msg]) > self.budget:
            history.pop(0)  # drop oldest history message
            trimmed += 1

        if trimmed:
            logger.warning(
                f"Token budget: trimmed {trimmed} history message(s) to fit within "
                f"{self.budget} token budget (model={self.model})"
            )

        return [system_msg] + history + [user_msg]
