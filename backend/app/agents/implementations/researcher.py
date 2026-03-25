import asyncio
import json
import logging
from typing import List, Dict, Optional, AsyncGenerator

from litellm import acompletion
from app.agents.base import BaseAgent
from app.core.config import settings
from app.core.reliability import TokenBudget, TIMEOUT_LLM_RESPONSE

logger = logging.getLogger(__name__)

# Per-agent token budget — enforced before each response call.
_response_budget = TokenBudget(model=settings.DEFAULT_MODEL)


class ResearcherAgent(BaseAgent):
    """
    An agent specialized in deep-dive research and fact-finding.
    Grounds answers in RAG-retrieved documents and web search results
    passed in by the Master Agent.
    """

    @property
    def name(self) -> str:
        return "researcher"

    @property
    def description(self) -> str:
        return "Best for deep research, summarizing complex topics, and fact-finding."

    def _build_system_prompt(self, context: Optional[List[Dict]], search_context: str) -> str:
        """
        Assembles the researcher's system prompt by injecting whatever context
        the Master Agent collected — RAG chunks, web results, or both.
        The LLM is instructed to ground its answer in these sources.
        """
        parts = [
            "You are a Research Expert. Provide detailed, well-structured, and accurate information.",
            "Always ground your answer in the sources provided below.",
            "If the sources do not contain enough information, say so clearly rather than guessing.",
        ]

        if context:
            rag_text = json.dumps(context, indent=2)
            parts.append(f"\n--- Knowledge Base (from uploaded documents) ---\n{rag_text}")

        if search_context:
            parts.append(f"\n--- Web Search Results ---\n{search_context}")

        if not context and not search_context:
            parts.append(
                "\nNo external sources were retrieved for this query. "
                "Answer from your training knowledge."
            )

        return "\n".join(parts)

    async def process_stream(
        self,
        query: str,
        history: List[Dict[str, str]],
        context: Optional[List[Dict]] = None,
        search_context: str = "",
    ) -> AsyncGenerator[str, None]:
        system_prompt = self._build_system_prompt(context, search_context)

        # Enforce token budget before the call — trims history if needed.
        messages = _response_budget.enforce([
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": query},
        ])

        try:
            # acompletion with stream=True returns an async iterator of chunks.
            # asyncio.wait_for covers the initial connection; individual chunks
            # stream freely once the connection is established.
            response = await asyncio.wait_for(
                acompletion(model=settings.DEFAULT_MODEL, messages=messages, stream=True),
                timeout=TIMEOUT_LLM_RESPONSE,
            )

            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content

        except asyncio.TimeoutError:
            logger.error("Researcher LLM call timed out")
            yield "\n\n[Response timed out. Please try again.]"
