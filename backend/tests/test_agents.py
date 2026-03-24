"""
Tests for agent delegation logic and researcher behavior.
These are the "eval" cases — does the system route correctly and
does the researcher ground its answers in the provided context?
"""
import asyncio
import uuid
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.agents.base import BaseAgent
from app.agents.implementations.researcher import ResearcherAgent


class TestResearcherAgent:
    def test_name_and_description_set(self):
        agent = ResearcherAgent()
        assert agent.name == "researcher"
        assert len(agent.description) > 10

    def test_system_prompt_with_rag_context(self):
        agent = ResearcherAgent()
        context = [{"text": "The speed of light is 299,792,458 m/s"}]
        prompt = agent._build_system_prompt(context=context, search_context="")
        assert "Knowledge Base" in prompt
        assert "299,792,458" in prompt

    def test_system_prompt_with_web_results(self):
        agent = ResearcherAgent()
        prompt = agent._build_system_prompt(context=None, search_context="Result: Paris is the capital of France")
        assert "Web Search Results" in prompt
        assert "Paris" in prompt

    def test_system_prompt_both_sources(self):
        agent = ResearcherAgent()
        prompt = agent._build_system_prompt(
            context=[{"text": "DNA stands for deoxyribonucleic acid"}],
            search_context="Web: DNA was discovered in 1869",
        )
        assert "Knowledge Base" in prompt
        assert "Web Search Results" in prompt

    def test_system_prompt_no_sources_honest_fallback(self):
        agent = ResearcherAgent()
        prompt = agent._build_system_prompt(context=None, search_context="")
        assert "No external sources" in prompt

    def test_system_prompt_empty_context_list_honest_fallback(self):
        agent = ResearcherAgent()
        prompt = agent._build_system_prompt(context=[], search_context="")
        assert "No external sources" in prompt

    def test_process_stream_signature(self):
        import inspect
        agent = ResearcherAgent()
        sig = inspect.signature(agent.process_stream)
        params = list(sig.parameters.keys())
        assert "query" in params
        assert "history" in params
        assert "context" in params
        assert "search_context" in params

    def test_yields_timeout_message_on_timeout(self):
        import app.agents.implementations.researcher as mod

        async def fake_timeout(*a, **kw):
            raise asyncio.TimeoutError()

        async def run():
            with patch.object(mod, "acompletion", side_effect=fake_timeout), \
                 patch.object(mod, "TIMEOUT_LLM_RESPONSE", 0.01):
                agent = mod.ResearcherAgent()
                tokens = []
                async for t in agent.process_stream("q", []):
                    tokens.append(t)
                return "".join(tokens)

        result = asyncio.run(run())
        assert "timed out" in result.lower()


class TestMasterAgentDelegation:
    """Verifies the master delegates to sub-agents, not its own LLM call."""

    def _build_master(self, spy_agent):
        from app.agents.master import MasterAgent
        with patch("app.services.rag.RAGPipeline.__init__", return_value=None):
            master = MasterAgent.__new__(MasterAgent)
            master.sub_agents = {spy_agent.name: spy_agent}
            master.rag = MagicMock()
            master.rag.query = AsyncMock(return_value=[{"source": "test.pdf", "chunk": 0}])
            master.system_prompt = "routing prompt"
            return master

    def test_master_calls_subagent_not_own_llm(self, fresh_session_id):
        """acompletion must be called exactly once (routing) — sub-agent handles the response."""

        class SpyAgent(BaseAgent):
            called = False
            @property
            def name(self): return "researcher"
            @property
            def description(self): return "spy"
            async def process_stream(self, query, history, context=None, search_context=""):
                SpyAgent.called = True
                yield "response_token"

        SpyAgent.called = False
        master = self._build_master(SpyAgent())
        routing_resp = MagicMock()
        routing_resp.choices[0].message.content = '{"next_agent": "researcher", "tools_to_use": []}'

        async def run():
            tokens = []
            with patch("app.agents.master.acompletion", return_value=routing_resp) as mock_llm:
                async for t in master.route_and_process_stream("test query", fresh_session_id):
                    tokens.append(t)
                assert mock_llm.call_count == 1, f"Expected 1 LLM call (routing), got {mock_llm.call_count}"
            return tokens

        tokens = asyncio.run(run())
        assert SpyAgent.called, "Sub-agent process_stream was never invoked"
        assert "response_token" in tokens

    def test_rag_sources_passed_to_audit(self, fresh_session_id, tmp_path):
        """RAG sources retrieved must appear in the audit record."""
        import json
        import app.core.audit as audit_mod

        audit_file = str(tmp_path / "audit.jsonl")

        class MinimalAgent(BaseAgent):
            @property
            def name(self): return "researcher"
            @property
            def description(self): return "minimal"
            async def process_stream(self, query, history, context=None, search_context=""):
                yield "ok"

        master = self._build_master(MinimalAgent())
        master.rag.query = AsyncMock(return_value=[
            {"source": "doc.pdf", "chunk": 0},
            {"source": "doc.pdf", "chunk": 1},
        ])
        routing_resp = MagicMock()
        routing_resp.choices[0].message.content = '{"next_agent": "researcher", "tools_to_use": []}'

        async def run():
            with patch("app.agents.master.acompletion", return_value=routing_resp), \
                 patch.object(audit_mod, "_DEFAULT_AUDIT_PATH", audit_file):
                async for _ in master.route_and_process_stream("test", fresh_session_id):
                    pass

        asyncio.run(run())

        with open(audit_file) as f:
            record = json.loads(f.read())

        assert len(record["rag_sources"]) == 2
        assert record["rag_sources"][0]["source"] == "doc.pdf"

    def test_unknown_agent_falls_back_gracefully(self, fresh_session_id):
        class FallbackAgent(BaseAgent):
            called = False
            @property
            def name(self): return "researcher"
            @property
            def description(self): return "fallback"
            async def process_stream(self, query, history, context=None, search_context=""):
                FallbackAgent.called = True
                yield "fallback_token"

        FallbackAgent.called = False
        master = self._build_master(FallbackAgent())
        routing_resp = MagicMock()
        # LLM returns an agent name that doesn't exist
        routing_resp.choices[0].message.content = '{"next_agent": "nonexistent_wizard", "tools_to_use": []}'

        async def run():
            tokens = []
            with patch("app.agents.master.acompletion", return_value=routing_resp):
                async for t in master.route_and_process_stream("test", fresh_session_id):
                    tokens.append(t)
            return tokens

        tokens = asyncio.run(run())
        assert FallbackAgent.called, "Fallback agent was not invoked"
        assert "fallback_token" in tokens
