import asyncio
import json
from typing import List, Dict
from litellm import completion
from app.agents.master import MasterAgent
from app.agents.registry import get_registered_agents
from app.core.config import settings

# Sample Evaluation Dataset
EVAL_DATASET = [
    {
        "query": "What is the capital of France?",
        "expected_keywords": ["Paris"],
        "description": "General knowledge check"
    },
    {
        "query": "Search the web for the current price of Bitcoin.",
        "expected_keywords": ["Bitcoin", "price", "$"],
        "description": "Tool use (Web Search) check"
    }
]

async def run_evaluation():
    agents = get_registered_agents()
    master = MasterAgent(agents)
    results = []

    print(f"🚀 Starting Evaluation on {len(EVAL_DATASET)} cases...\n")

    for case in EVAL_DATASET:
        print(f"Testing: {case['description']}...")
        full_response = ""
        
        async for token in master.route_and_process_stream(case['query'], "eval-session"):
            if not token.startswith("🔍"): # Ignore tool status tokens
                full_response += token
        
        # Simple Keyword Scoring
        score = sum(1 for word in case['expected_keywords'] if word.lower() in full_response.lower())
        passed = score > 0
        
        results.append({
            "case": case['description'],
            "passed": passed,
            "response_snippet": full_response[:100] + "..."
        })

    print("\n--- EVALUATION SUMMARY ---")
    for r in results:
        status = "✅ PASSED" if r['passed'] else "❌ FAILED"
        print(f"{status} | {r['case']}")

if __name__ == "__main__":
    asyncio.run(run_evaluation())
