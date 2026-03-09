import json
import logging
from typing import List, Dict, Optional
from litellm import completion
from app.agents.base import BaseAgent, AgentResponse
from app.core.config import settings
from app.services.memory import MemoryManager
from app.services.rag import RAGPipeline

logger = logging.getLogger(__name__)

class MasterAgent:
    """
    The orchestrator that analyzes intent and routes tasks to specialized agents.
    It now incorporates RAG context and persistent memory.
    """
    def __init__(self, sub_agents: List[BaseAgent]):
        self.sub_agents = {agent.name: agent for agent in sub_agents}
        self.rag = RAGPipeline()
        self.system_prompt = self._generate_routing_prompt()

    def _generate_routing_prompt(self) -> str:
        """Dynamically generates the prompt based on registered agents."""
        agent_descriptions = "\n".join(
            [f"- {a.name}: {a.description}" for a in self.sub_agents.values()]
        )
        return (
            "You are the Master Orchestrator for an AI Agent Stack.\n"
            "Your job is to analyze the user's query, history, and provided context to decide which expert agent to route it to.\n\n"
            "AVAILABLE EXPERTS:\n"
            f"{agent_descriptions}\n\n"
            "ROUTING RULES:\n"
            "1. If the query clearly matches an expert's domain, route to that agent.\n"
            "2. If the query is a simple greeting or general chat, answer directly as 'master'.\n"
            "3. Use the 'context' and 'history' to inform your routing decision.\n\n"
            "RESPONSE FORMAT (MUST BE JSON):\n"
            '{ "next_agent": "agent_name_or_master", "reasoning": "why you chose this agent" }'
        )

    async def route_and_process(self, query: str, session_id: str) -> AgentResponse:
        """Route the query using history and RAG context."""
        try:
            # 1. Fetch History and RAG Context
            history = MemoryManager.get_history(session_id)
            context = await self.rag.query(query)
            context_str = json.dumps(context)

            # Store user message
            MemoryManager.add_message(session_id, "user", query)

            # 2. LLM Routing Decision
            response = completion(
                model=settings.DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": f"{self.system_prompt}\n\nCONTEXT:\n{context_str}"},
                    *history,
                    {"role": "user", "content": query}
                ],
                response_format={"type": "json_object"}
            )
            
            decision = json.loads(response.choices[0].message.content)
            target_agent_name = decision.get("next_agent", "master")

            # 3. Delegation or Direct Answer
            if target_agent_name in self.sub_agents and target_agent_name != "master":
                agent = self.sub_agents[target_agent_name]
                agent_res = await agent.process(query, history)
            else:
                master_res = completion(
                    model=settings.DEFAULT_MODEL,
                    messages=[
                        {"role": "system", "content": "You are the Master Agent. Answer using the context and history."},
                        *history,
                        {"role": "user", "content": f"Context: {context_str}\nQuery: {query}"}
                    ]
                )
                agent_res = AgentResponse(
                    content=master_res.choices[0].message.content,
                    source_agent="master"
                )

            # Store assistant response
            MemoryManager.add_message(session_id, "assistant", agent_res.content, agent_res.source_agent)
            return agent_res

        except Exception as e:
            logger.error(f"Routing error: {e}")
            return AgentResponse(content=f"Error: {str(e)}", source_agent="master")
