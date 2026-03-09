import asyncio
from typing import List, Dict, AsyncGenerator
from litellm import completion
from app.agents.base import BaseAgent
from app.core.config import settings

class ResearcherAgent(BaseAgent):
    """
    An agent specialized in deep-dive research and fact-finding.
    """
    @property
    def name(self) -> str:
        return "researcher"

    @property
    def description(self) -> str:
        return "Best for deep research, summarizing complex topics, and fact-finding."

    async def process_stream(self, query: str, history: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        # Perform research with streaming
        response = completion(
            model=settings.DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "You are a Research Expert. Provide detailed, well-structured information."},
                *history,
                {"role": "user", "content": query}
            ],
            stream=True
        )
        
        for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                yield content
