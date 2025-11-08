# FILE: ./src/tasks/housing_tasks.py
import json
from typing import Any

from crewai import Task
from pydantic import BaseModel, ConfigDict, RootModel

from src.tools import backend_api_tool, google_maps_tool, listing_ranker_tool

# --- Output JSON schema for ranking task ---


class RankedListingItem(BaseModel):
    match_score: float
    commute_time: str
    # Allow extra keys from backend (title, url, price_amount, area_m2, etc.)
    model_config = ConfigDict(extra="allow")


class RankedListingsOutput(RootModel[list[RankedListingItem]]):
    pass


# --- SEARCH CREW TASKS ---


def create_housing_search_task(agent, criteria: dict[str, Any]):
    """Task: Fetch raw listings from backend."""
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
            "!!Most Important!! OUTPUT RULE: "
            "Return the FULL, UNMODIFIED JSON list of ranked listings (Top 5) "
            "exactly as you received it from the listing_ranker_tool. "
            "Do NOT remove any fields (like id, url, title). Your final answer MUST be "
            "the complete JSON list from that tool."
        ),
        expected_output=(
            "The full JSON list of the Top 5 ranked listings, "
            "including all original fields (id, url, title, etc.) "
            "plus the new 'match_score' and 'commute_time' fields."
        ),
        agent=agent,
        tools=[google_maps_tool, listing_ranker_tool],
        output_json=RankedListingsOutput,
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
