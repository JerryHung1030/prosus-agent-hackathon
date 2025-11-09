# FILE: ./src/agents/housing_agents.py
from crewai import Agent

from src.tools import (
    backend_api_tool,
    batch_commute_tool,
    listing_ranker_tool,
    motivation_builder_tool,
    pararius_form_tool,
    trigger_search_tool,
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
        tools=[backend_api_tool],
        allow_delegation=False,
        verbose=True,
        step_callback=step_callback,
    )


def create_ranking_agent(step_callback=None) -> Agent:
    return Agent(
        role="Commute & Data Analyst",
        goal="Analyze listings efficiently and rank them based on commute and criteria.",
        backstory=(
            "You are an efficient data analyst. Your job is to take a list of properties "
            "and rank them intelligently:\n"
            "- If there are 10 or fewer listings, you skip the ranking process entirely "
            "and assign all listings a score of 100 with commute_time='N/A' to save time.\n"
            "- If there are more than 10 listings, you use the BATCH commute tool to find "
            "real commute data for all of them, and then use the ranking tool to score and "
            "sort them, returning the top 5.\n"
            "You optimize for efficiency and avoid unnecessary computation."
        ),
        tools=[batch_commute_tool, listing_ranker_tool],
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


def create_conversation_agent(step_callback=None) -> Agent:
    """Conversational agent that interacts with users to collect housing search
    criteria and triggers the search once all criteria are gathered."""
    return Agent(
        role="Housing Search Consultant",
        goal=(
            "STRICT RULE: You MUST collect ALL 4 pieces of information before triggering search:\n"
            "1. City\n"
            "2. Max Price/Budget\n"
            "3. Minimum Size\n"
            "4. Commute Target\n\n"
            "Once ALL 4 are collected, you MUST use the "
            "trigger_housing_search tool to start the search."
        ),
        backstory=(
            "You are a strict but friendly housing consultant. "
            "Your job is to collect EXACTLY 4 pieces "
            "of information from users:\n"
            "1. City - which city they want to live in\n"
            "2. Budget - their maximum monthly rent (in euros)\n"
            "3. Size - minimum apartment size they need (in m²)\n"
            "4. Commute - where they need to commute to (address or landmark)\n\n"
            "RULES:\n"
            "- Ask questions ONE at a time in a natural way\n"
            "- Extract information from user responses\n"
            "- Keep track of what you've collected\n"
            "- DO NOT proceed until you have ALL 4 pieces\n"
            "- Once you have all 4, you MUST call trigger_housing_search tool "
            "with the collected data\n"
            "- DO NOT make up or assume any information"
        ),
        tools=[trigger_search_tool],  # Tool to trigger the search
        allow_delegation=False,
        verbose=True,
        step_callback=step_callback,
        memory=True,  # Enable memory
    )


def create_master_agent(step_callback=None) -> Agent:
    """Master agent that can converse and delegate search tasks to other agents."""
    return Agent(
        role="Housing Search Master Coordinator",
        goal=(
            "Collect housing search criteria and trigger the search ONLY with user consent:\n"
            "STEP 1: Collect ALL 4 pieces: city, budget (max_price), size (min_size), "
            "commute location (commute_target)\n"
            "STEP 2: Once ALL 4 are collected, ASK FOR USER CONFIRMATION\n"
            "STEP 3: ONLY if user explicitly consents (says 'yes', 'search', 'go ahead'), "
            "USE the trigger_housing_search tool\n"
            "STEP 4: If user says 'no', 'stop', 'don't apply', 'wait' - NEVER trigger the search"
        ),
        backstory=(
            "You are a housing search coordinator with ONE critical tool: "
            "trigger_housing_search.\n\n"
            "Your process is STRICT:\n"
            "1. Chat with users to collect exactly 4 pieces of information:\n"
            "   - city (string)\n"
            "   - max_price (integer, in euros)\n"
            "   - min_size (integer, in m²)\n"
            "   - commute_target (string, address or landmark)\n"
            "2. Ask ONE question at a time naturally\n"
            "3. When you have ALL 4 pieces with actual values, ASK FOR CONFIRMATION:\n"
            "   'Would you like me to start the search now?'\n"
            "4. RESPECT USER CONSENT:\n"
            "   - If user says YES ('search', 'go ahead', 'yes') → USE trigger_housing_search tool\n"
            "   - If user says NO ('don't apply', 'stop', 'not yet', 'wait') → DO NOT trigger\n"
            "   - If user updates criteria → Update but wait for new confirmation\n"
            "5. NEVER trigger search without explicit user consent!\n"
            "6. The tool will return a signal that triggers the backend to run the search crew\n\n"
            "Remember: Consent is MANDATORY. Never auto-trigger even when all data is complete!"
        ),
        tools=[trigger_search_tool],
        allow_delegation=True,  # Allow delegation
        verbose=True,
        step_callback=step_callback,
        memory=True,
    )
