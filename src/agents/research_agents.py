# FILE: ./src/agents/research_agents.py
from crewai import Agent

from src.tools import all_tools


def create_research_agent(step_callback=None, tools=None, verbose=True) -> Agent:
    """
    Factory for the Researcher Agent.
    Injects callbacks so on_agent_action/on_tool_end fire correctly in Streamlit.
    Args:
        step_callback: Optional[Callable]
        tools: Optional[List[BaseTool]];
        verbose: bool
    """
    return Agent(
        role="Senior Market Researcher",
        goal="Find and analyze market data to answer the user's request.",
        backstory=(
            "You are an expert market researcher with a keen eye for "
            "data and trends. You use your set of tools to gather "
            "relevant information and provide insightful analysis."
        ),
        tools=tools or all_tools,
        allow_delegation=False,
        verbose=verbose,
        step_callback=step_callback,
    )


def create_writer_agent(step_callback=None, verbose=True) -> Agent:
    """
    Factory for the Writer Agent.
    Injects callbacks so reasoning logs render in Streamlit.
    """
    return Agent(
        role="Professional Report Writer",
        goal=(
            "Compose a clear, concise, and insightful report based on the researcher's findings."
        ),
        backstory=(
            "You are a skilled writer, known for your ability to "
            "transform complex data into an easy-to-understand report. "
            "You take the findings from the researcher and craft the "
            "perfect final answer."
        ),
        allow_delegation=False,
        verbose=verbose,
        step_callback=step_callback,
    )
