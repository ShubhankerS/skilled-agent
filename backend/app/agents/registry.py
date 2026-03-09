from typing import List
from app.agents.base import BaseAgent
from app.agents.implementations.researcher import ResearcherAgent

# This is the central registry for all agents. 
# New agents are added here to be automatically detected by the Master Agent.

def get_registered_agents() -> List[BaseAgent]:
    """Returns a list of all active sub-agents."""
    return [
        ResearcherAgent(),
        # Add future agents here (e.g., CodingAgent, FinanceAgent)
    ]
