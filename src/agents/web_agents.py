# FILE: ./src/agents/web_agents.py
"""
Web exploration agents for analyzing arbitrary URLs and extracting structured data.
"""
from crewai import Agent

from src.tools.web_extractor_tool import web_extractor_tool
from src.tools.trigger_search_tool import trigger_search_tool


# FILE: src/agents/web_agents.py
"""
Web agents for analyzing and extracting data from arbitrary URLs.
"""

from crewai import Agent
from typing import Optional


# Default commute targets for major Dutch cities
DEFAULT_COMMUTE_TARGETS = {
    "Amsterdam": "Zuidas",
    "Rotterdam": "Rotterdam Central Station",
    "The Hague": "Den Haag Centraal",
    "Utrecht": "Utrecht Science Park",
    "Eindhoven": "High Tech Campus",
    "Delft": "TU Delft Campus",
    "Leiden": "Leiden Central Station",
    "Haarlem": "Haarlem Station",
    "Almere": "Almere Centrum",
    "Groningen": "Groningen Central Station",
}


def create_web_reasoning_agent(step_callback=None) -> Agent:
    """
    Autonomous reasoning agent that interprets a listing link and extracts
    structured search parameters including an inferred commute target.
    
    This agent ALWAYS infers a commute_target, even if not explicitly stated,
    using geographic, linguistic, and contextual reasoning.
    """
    from crewai_tools import WebsiteSearchTool
    
    website_search_tool = WebsiteSearchTool()
    
    return Agent(
        role="Web Reasoning & Extraction Agent",
        goal=(
            "Given a housing or listing URL, analyze the content, reason about it, "
            "and extract the essential structured search criteria: city, price, "
            "minimum size (m²), and a logically inferred commute target. "
            "The commute_target must ALWAYS be inferred even if not explicitly stated."
        ),
        backstory=(
            "You are a location-savvy real-estate reasoning analyst. "
            "You understand how people choose apartments relative to work or city hubs. "
            "You infer the most probable commute destination using reasoning "
            "about the city, neighborhood, and listing context. "
            f"You know the major business districts: {', '.join([f'{k}→{v}' for k, v in DEFAULT_COMMUTE_TARGETS.items()])}. "
            "You NEVER leave commute_target empty or null."
        ),
        tools=[website_search_tool],
        allow_delegation=False,
        verbose=True,
        step_callback=step_callback,
    )


def create_web_explorer_agent(step_callback=None) -> Agent:
    """
    Main agent for web exploration and data extraction.
    Uses the web_extractor_tool to fetch and parse web pages.
    """
    from ..tools.web_extractor_tool import web_extractor_tool
    from ..tools.trigger_search_tool import trigger_search_tool
    
    return Agent(
        role="Web Content Explorer",
        goal=(
            "Extract structured data from any URL by analyzing the page content. "
            "Identify property listings, LinkedIn profiles, or general information. "
            "Present findings in a clear, structured format for user confirmation."
        ),
        backstory=(
            "You are an expert web analyst who can extract meaningful data from any webpage. "
            "You understand property listings, professional profiles, and general content. "
            "You're skilled at identifying key information like prices, sizes, locations, "
            "job titles, salaries, and other relevant details. You present data clearly "
            "and help users make informed decisions."
        ),
        tools=[web_extractor_tool, trigger_search_tool],
        allow_delegation=False,
        verbose=True,
        step_callback=step_callback,
    )


def create_link_analyzer_agent(step_callback=None) -> Agent:
    """
    Agent specialized in analyzing links and determining the best action to take.
    Works in conjunction with the web explorer agent.
    """
    return Agent(
        role="Link Analysis Specialist",
        goal=(
            "Analyze URLs and determine the type of content, then coordinate "
            "appropriate extraction and follow-up actions."
        ),
        backstory=(
            "You specialize in understanding what kind of content lives at a URL. "
            "You can detect if a link is a property listing, a profile page, or general content. "
            "You work with the Web Explorer to extract data and suggest next steps to the user."
        ),
        tools=[web_extractor_tool],
        allow_delegation=True,
        verbose=True,
        step_callback=step_callback,
    )


def create_data_confirmation_agent(step_callback=None) -> Agent:
    """
    Agent responsible for presenting extracted data and obtaining user confirmation.
    """
    return Agent(
        role="Data Confirmation Specialist",
        goal=(
            "Present extracted data clearly and obtain explicit user confirmation "
            "before triggering any automated actions."
        ),
        backstory=(
            "You excel at communicating with users. You present data in a clear, "
            "structured format and always ensure the user understands what action "
            "will be taken if they confirm. You never proceed without explicit approval."
        ),
        tools=[],  # No tools needed, just communication
        allow_delegation=False,
        verbose=True,
        step_callback=step_callback,
    )
