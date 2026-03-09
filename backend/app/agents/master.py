import json
import logging
import base64
from typing import List, Dict, Optional, AsyncGenerator
from litellm import completion
from app.agents.base import BaseAgent, AgentResponse
from app.core.config import settings
from app.services.memory import MemoryManager
from app.services.rag import RAGPipeline
from app.tools.web_search import WebSearchTool

logger = logging.getLogger(__name__)

class MasterAgent:
    """
    Orchestrator with Multi-Modal, RAG, and Tool Execution capabilities.
    """
    def __init__(self, sub_agents: List[BaseAgent]):
        self.sub_agents = {agent.name: agent for agent in sub_agents}
        self.rag = RAGPipeline()
        self.system_prompt = self._generate_routing_prompt()

    def _generate_routing_prompt(self) -> str:
        agent_descriptions = "\n".join([f"- {a.name}: {a.description}" for a in self.sub_agents.values()])
        return (
            "You are the Master Orchestrator with vision and web search abilities.\n"
            f"AVAILABLE EXPERTS:\n{agent_descriptions}\n\n"
            "ROUTING RULES:\n"
            "1. Route based on domain expert description.\n"
            "2. If real-time info is needed, include 'WEB_SEARCH' in your 'tools_to_use' field.\n"
            "3. If an image is provided, analyze it first.\n"
            "RESPONSE FORMAT (JSON):\n"
            '{ "next_agent": "expert_name", "tools_to_use": ["WEB_SEARCH"], "reasoning": "..." }'
        )

    async def route_and_process_stream(self, query: str, session_id: str, image_b64: Optional[str] = None) -> AsyncGenerator[str, None]:
        try:
            history = MemoryManager.get_history(session_id)
            context = await self.rag.query(query)
            
            # Step 1: Handle Multi-Modal Message
            user_content = [{"type": "text", "text": query}]
            if image_b64:
                user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}})

            # Step 2: Routing Decision
            response = completion(
                model=settings.DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": f"{self.system_prompt}\n\nRAG Context: {json.dumps(context)}"},
                    *history,
                    {"role": "user", "content": user_content}
                ],
                response_format={"type": "json_object"}
            )
            
            decision = json.loads(response.choices[0].message.content)
            target_agent = decision.get("next_agent", "master")
            tools = decision.get("tools_to_use", [])

            # Step 3: Tool Execution (Web Search)
            search_context = ""
            if "WEB_SEARCH" in tools:
                yield "🔍 Searching the web...\n\n"
                results = WebSearchTool.search(query)
                search_context = f"\nWeb Results: {json.dumps(results)}"

            # Step 4: Final Processing
            full_content = ""
            messages = [
                {"role": "system", "content": f"You are the {target_agent}. {search_context}\nContext: {json.dumps(context)}"},
                *history,
                {"role": "user", "content": user_content}
            ]

            async_res = completion(model=settings.DEFAULT_MODEL, messages=messages, stream=True)
            for chunk in async_res:
                token = chunk.choices[0].delta.content
                if token:
                    full_content += token
                    yield token

            MemoryManager.add_message(session_id, "assistant", full_content, target_agent)

        except Exception as e:
            logger.error(f"Routing error: {e}")
            yield f"Error: {str(e)}"
