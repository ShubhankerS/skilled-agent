import asyncio
import json
import logging
from typing import List, Dict, Optional, AsyncGenerator

from litellm import acompletion
from app.agents.base import BaseAgent, AgentResponse
from app.core.config import settings
from app.core.reliability import TokenBudget, TIMEOUT_LLM_ROUTING, TIMEOUT_WEB_SEARCH
from app.services.memory import MemoryManager
from app.services.rag import RAGPipeline
from app.tools.web_search import WebSearchTool

logger = logging.getLogger(__name__)

# One shared token budget instance for the routing call.
# The response call budget lives in each sub-agent.
_routing_budget = TokenBudget(model=settings.DEFAULT_MODEL)


class MasterAgent:
    """
    Orchestrator: routes each request to the right sub-agent, gathers context,
    executes tools, then delegates response generation to the chosen agent.
    """

    def __init__(self, sub_agents: List[BaseAgent]):
        self.sub_agents = {agent.name: agent for agent in sub_agents}
        self.rag = RAGPipeline()
        self.system_prompt = self._generate_routing_prompt()

    def _generate_routing_prompt(self) -> str:
        agent_descriptions = "\n".join(
            [f"- {a.name}: {a.description}" for a in self.sub_agents.values()]
        )
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

    async def route_and_process_stream(
        self,
        query: str,
        session_id: str,
        image_b64: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        try:
            history = MemoryManager.get_history(session_id)
            context = await self.rag.query(query)

            # Step 1: Build the user message (text + optional image)
            user_content = [{"type": "text", "text": query}]
            if image_b64:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                })

            # Step 2: Routing decision
            # Enforce token budget before the call so we never exceed the context window.
            routing_messages = _routing_budget.enforce([
                {"role": "system", "content": f"{self.system_prompt}\n\nRAG Context: {json.dumps(context)}"},
                *history,
                {"role": "user", "content": user_content},
            ])

            # acompletion is LiteLLM's async version — doesn't block the event loop.
            # asyncio.wait_for enforces a hard timeout: if Gemini takes >15s to
            # return the routing JSON, we raise TimeoutError instead of hanging.
            routing_response = await asyncio.wait_for(
                acompletion(
                    model=settings.DEFAULT_MODEL,
                    messages=routing_messages,
                    response_format={"type": "json_object"},
                ),
                timeout=TIMEOUT_LLM_ROUTING,
            )

            decision = json.loads(routing_response.choices[0].message.content)
            target_agent = decision.get("next_agent", "master")
            tools = decision.get("tools_to_use", [])
            logger.info(f"Routing decision: agent={target_agent}, tools={tools}")

            # Step 3: Tool execution (web search)
            search_context = ""
            if "WEB_SEARCH" in tools:
                yield "🔍 Searching the web...\n\n"
                try:
                    # Web search is synchronous; run it in a thread so it doesn't
                    # block the async event loop, with its own timeout.
                    results = await asyncio.wait_for(
                        asyncio.to_thread(WebSearchTool.search, query),
                        timeout=TIMEOUT_WEB_SEARCH,
                    )
                    search_context = f"\nWeb Results: {json.dumps(results)}"
                except asyncio.TimeoutError:
                    logger.warning("Web search timed out — proceeding without results")
                    search_context = ""

            # Step 4: Delegate to the actual sub-agent
            # If the LLM returns an agent name we don't have, fall back gracefully.
            agent = self.sub_agents.get(target_agent) or next(iter(self.sub_agents.values()))
            actual_agent_name = agent.name

            full_content = ""
            async for token in agent.process_stream(
                query=query,
                history=history,
                context=context,
                search_context=search_context,
            ):
                full_content += token
                yield token

            MemoryManager.add_message(session_id, "assistant", full_content, actual_agent_name)

        except asyncio.TimeoutError:
            logger.error("LLM routing call timed out")
            yield "The request timed out. Please try again."
        except Exception as e:
            logger.error(f"Routing error: {e}", exc_info=True)
            yield "I encountered an error processing your request. Please try again."
