import asyncio
import json
import logging
import time
from typing import List, Dict, Optional, AsyncGenerator

from litellm import acompletion
from app.agents.base import BaseAgent, AgentResponse
from app.core.config import settings
from app.core.reliability import TokenBudget, TIMEOUT_LLM_ROUTING, TIMEOUT_WEB_SEARCH
from app.core.audit import write_audit_record
from app.services.memory import MemoryManager
from app.services.rag import RAGPipeline
from app.tools.web_search import WebSearchTool

logger = logging.getLogger(__name__)

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
        start_time = time.monotonic()
        tools_used: List[str] = []
        actual_agent_name = "unknown"
        rag_sources: List[Dict] = []
        status = "ok"

        try:
            history = MemoryManager.get_history(session_id)
            context = await self.rag.query(query)

            # Extract RAG source metadata for audit trail and citation tracking.
            # Each context item is the payload dict stored at upload time,
            # typically {"source": "filename.pdf", "chunk": 2, ...}
            rag_sources = [c for c in context if c]

            # Step 1: Build the user message (text + optional image)
            user_content = [{"type": "text", "text": query}]
            if image_b64:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                })

            # Step 2: Routing decision
            routing_messages = _routing_budget.enforce([
                {"role": "system", "content": f"{self.system_prompt}\n\nRAG Context: {json.dumps(context)}"},
                *history,
                {"role": "user", "content": user_content},
            ])

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
            tools_used = decision.get("tools_to_use", [])

            # Structured log — fields appear as top-level keys in JSON output
            logger.info(
                "routing_decision",
                extra={
                    "session_id": session_id,
                    "agent": target_agent,
                    "tools": tools_used,
                    "rag_source_count": len(rag_sources),
                },
            )

            # Step 3: Tool execution (web search)
            search_context = ""
            if "WEB_SEARCH" in tools_used:
                yield "🔍 Searching the web...\n\n"
                try:
                    results = await asyncio.wait_for(
                        asyncio.to_thread(WebSearchTool.search, query),
                        timeout=TIMEOUT_WEB_SEARCH,
                    )
                    search_context = f"\nWeb Results: {json.dumps(results)}"
                except asyncio.TimeoutError:
                    logger.warning(
                        "web_search_timeout",
                        extra={"session_id": session_id},
                    )
                    search_context = ""

            # Step 4: Delegate to the actual sub-agent
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
            status = "timeout"
            logger.error("routing_timeout", extra={"session_id": session_id})
            yield "The request timed out. Please try again."
        except Exception as e:
            status = "error"
            logger.error("routing_error", extra={"session_id": session_id, "error": str(e)}, exc_info=True)
            yield "I encountered an error processing your request. Please try again."
        finally:
            # Always write the audit record — even on error or timeout.
            # "finally" runs whether the try block succeeded or raised.
            duration_ms = int((time.monotonic() - start_time) * 1000)
            write_audit_record(
                session_id=session_id,
                query=query,
                agent=actual_agent_name,
                tools_used=tools_used,
                rag_sources=rag_sources,
                duration_ms=duration_ms,
                status=status,
            )
            logger.info(
                "request_complete",
                extra={
                    "session_id": session_id,
                    "agent": actual_agent_name,
                    "duration_ms": duration_ms,
                    "status": status,
                },
            )
