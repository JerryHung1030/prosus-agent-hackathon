# FILE: ./src/tools/web_search_tool.py

from crewai_tools import TavilySearchTool

from src.config import TAVILY_API_KEY

if not TAVILY_API_KEY:
    raise ValueError("TAVILY_API_KEY not found.")

# Exported instance used by the tool registry
web_search_tool = TavilySearchTool(max_results=3)
print("Web search tool (Tavily) initialized.")
