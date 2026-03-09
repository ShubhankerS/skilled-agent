from duckduckgo_search import DDGS
from typing import List, Dict

class WebSearchTool:
    """
    Provides real-time web search capabilities for agents.
    """
    @staticmethod
    def search(query: str, max_results: int = 3) -> List[Dict[str, str]]:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=max_results)
            return [
                {"title": r["title"], "snippet": r["body"], "link": r["href"]}
                for r in results
            ]
