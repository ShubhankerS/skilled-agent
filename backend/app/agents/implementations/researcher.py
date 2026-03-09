import asyncio
from typing import List, Dict
from litellm import completion
from app.agents.base import BaseAgent, AgentResponse
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

    async def process(self, query: str, history: List[Dict[str, str]]) -> AgentResponse:
        # Example: Using LiteLLM to perform the task
        response = completion(
            model=settings.DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "You are a Research Expert. Provide detailed, well-structured information."},
                {"role": "user", "content": query}
            ]
        )
        
        return AgentResponse(
            content=response.choices[0].message.content,
            source_agent=self.name,
            metadata={"model": settings.DEFAULT_MODEL}
        )
