# FILE: ./src/tasks/housing_tasks.py
import json
from typing import Any

from crewai import Task

from src.tools import backend_api_tool, google_maps_tool, listing_ranker_tool

# --- SEARCH CREW TASKS ---


def create_housing_search_task(agent, criteria: dict[str, Any]):
    """Task: Fetch raw listings from backend.

    Agent MUST:
    1. Call backend_api_tool exactly once.
    2. Pass filters if present: city, max_price (price), min_size (size).
    3. Return ONLY a valid JSON list of listing objects (no explanation, no prose).
    4. If no listings found, return [] (still JSON list).
    """
    query_summary = {
        "city": criteria.get("city"),
        "max_price": criteria.get("price"),
        "min_size": criteria.get("size"),
    }
    return Task(
        description=(
            "Fetch up to 20 housing listings. Use backend_api_tool exactly once with filters: "
            f"{query_summary}. OUTPUT RULE: Return ONLY a JSON list (e.g. [] or [{{...}}])."
        ),
        expected_output="A pure JSON list of listing objects.",
        agent=agent,
        tools=[backend_api_tool],
    )


def create_housing_rank_task(agent, criteria: dict[str, Any]):
    """Task: Rank listings with commute times."""
    commute_target = criteria.get("commute_target")
    # Hard-code criteria as JSON string in the prompt to prevent misuse
    criteria_json = json.dumps(criteria)

    return Task(
        description=(
            "Rank housing listings. Input is JSON list from search; if empty return []. "
            "Else build origin addresses: 'street, city postal_code, Netherlands'. Get commute "
            f"duration to '{commute_target}' using google_maps_tool (fallback '999 mins' if fields "
            "missing or API unavailable).\n\n"
            "Then call listing_ranker_tool ONCE. You MUST use the following dictionary as the "
            f"'criteria' argument: {criteria_json}. You must also pass the 'listings' list and the "
            "'commute_times' list.\n\n"
            "OUTPUT RULE: Return ONLY a JSON list (Top 5 or fewer) including match_score and "
            "commute_time."
        ),
        expected_output="A pure JSON list of ranked listings with match_score and commute_time.",
        agent=agent,
        tools=[google_maps_tool, listing_ranker_tool],
        # output_json not supported as boolean in CrewAI 1.3.0; rely on clear description instead.
    )


# --- APPLY CREW TASK ---


def create_housing_apply_task(agent, user_profile: str, listing_details: str):
    return Task(
        description=f"""
        Apply for the following single property.
        
        USER PROFILE:
        {user_profile}
        
        LISTING DETAILS:
        {listing_details}

        STEP 1: Use the motivation_builder_tool to generate the perfect motivation letter.
        STEP 2: Use the pararius_login_and_contact_filler tool. You must pass this tool:
            - The user's username and password (from the profile).
            - The listing's contact URL (from the listing details).
            - The motivation message you just generated.
            - All other profile data (salutation, employment_status, etc.)
        """,
        expected_output="A final confirmation message, including the path to the saved screenshot.",
        agent=agent,
    )
