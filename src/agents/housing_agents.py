# FILE: ./src/agents/housing_agents.py
from crewai import Agent

from src.tools import (
    backend_api_tool,
    google_maps_tool,
    listing_ranker_tool,
    motivation_builder_tool,
    pararius_form_tool,
)


def create_search_agent(step_callback=None) -> Agent:
    """Agent responsible for retrieving listings from the backend API."""
    return Agent(
        role="Listing Scout",
        goal="Find up to 20 candidate rental listings from the backend API.",
        backstory=(
            "You specialize in querying the internal property API "
            "to find listings matching user criteria."
        ),
        # Attach backend API tool (was empty before)
        tools=[backend_api_tool],  # previously empty
        allow_delegation=False,
        verbose=True,
        step_callback=step_callback,
    )


def create_ranking_agent(step_callback=None) -> Agent:
    return Agent(
        role="Commute & Data Analyst",
        goal="Analyze listings, find REAL commute times, and rank the top 5.",
        backstory=(
            "You are a data analyst. Your job is to take a list of properties, "
            "use the Google Maps tool to find real commute data for each one, "
            "and then use a ranking tool to score and sort them."
        ),
        # Attach Google Maps + ranking tools (maps tool was missing before)
        tools=[google_maps_tool, listing_ranker_tool],  # previously missing google_maps_tool
        allow_delegation=False,
        verbose=True,
        step_callback=step_callback,
    )


def create_apply_agent(step_callback=None) -> Agent:
    # Agent already correct; no modifications needed
    return Agent(
        role="Application Assistant",
        goal=(
            "Generate a motivation letter and fill out the application form for "
            "ONE specific property."
        ),
        backstory=(
            "You are a precise and reliable assistant. You take a user's profile and one property, "
            "generate a motivation letter, and then automatically log in and fill the application "
            "form, taking a screenshot as proof."
        ),
        tools=[motivation_builder_tool, pararius_form_tool],
        allow_delegation=False,
        verbose=True,
        step_callback=step_callback,
    )
