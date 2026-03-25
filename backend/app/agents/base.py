from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator
import json
from pydantic import BaseModel, Field

class AgentResponse(BaseModel):
    """Standardized response from any agent in the system."""
    content: str = Field(..., description="The textual response from the agent.")
    source_agent: str = Field(..., description="The name of the agent that generated the response.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata (e.g., token usage, citations).")

class BaseAgent(ABC):
    """
    Abstract Base Class for all agents. 
    Follows the 'Contract' pattern for modularity.
    """
    @property
    @abstractmethod
    def name(self) -> str:
        """The identifier used by the Master Agent for routing."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """The capability description used by the Master Agent's LLM to decide routing."""
        pass

    @abstractmethod
    async def process_stream(
        self,
        query: str,
        history: List[Dict[str, str]],
        context: Optional[List[Dict]] = None,
        search_context: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        The core execution logic of the sub-agent, yielding tokens.

        Args:
            query:          The user's current message.
            history:        Previous conversation turns from memory.
            context:        RAG-retrieved document chunks from Qdrant.
            search_context: Formatted web search results string (empty if not searched).
        """
        pass
