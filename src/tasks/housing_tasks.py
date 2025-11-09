# FILE: ./src/tasks/housing_tasks.py
import json
from typing import Any

from crewai import Task
from pydantic import BaseModel, ConfigDict, RootModel

# 1. Important: use batch_commute_tool (not google_maps_tool)
#    This addresses the "slow" behavior observed in logs.
from src.tools import backend_api_tool, batch_commute_tool, listing_ranker_tool

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
    # Standardize keys to align with conversation & tools
    query_summary = {
        "city": criteria.get("city"),
        "max_price": criteria.get("max_price"),
        "min_size": criteria.get("min_size"),
    }
    return Task(
        description=(
            # 2. As requested: change limit from 20 to 10
            "Fetch up to 10 housing listings. Use backend_api_tool exactly once with filters: "
            f"{query_summary}. OUTPUT RULE: Return ONLY a JSON list (e.g. [] or [{{...}}])."
        ),
        expected_output="A pure JSON list of listing objects.",
        agent=agent,
        tools=[backend_api_tool],
    )


def create_housing_rank_task(agent, criteria: dict[str, Any]):
    """Task: Rank listings with commute times."""
    commute_target = criteria.get("commute_target")
    # Normalize keys for ranking tool (ensure max_price/min_size present)
    normalized = {
        "city": criteria.get("city"),
        "max_price": criteria.get("max_price"),
        "min_size": criteria.get("min_size"),
        "commute_target": commute_target,
    }
    criteria_json = json.dumps(normalized)

    # --- 3. Important: optimized task description ---
    # Explicitly instruct the Agent to use the batch tool for speed.
    return Task(
        description=(
            "Rank housing listings. Input is a JSON list from the search task. "
            "STEP 1: Call `batch_commute_tool` ONCE. "
            f"You MUST pass the full `listings` list and the `destination`='{commute_target}'. "
            "This tool will return a list of commute time strings.\n\n"
            "STEP 2: Call `listing_ranker_tool` ONCE. "
            "You MUST pass the 'listings' list, the 'commute_times' list (from Step 1), "
            f"and the 'criteria' dictionary: {criteria_json}.\n\n"
            "!!Most Important!! OUTPUT RULE: "
            "Return the FULL, UNMODIFIED JSON list of ranked listings (Top 5) "
            "exactly as you received it from the listing_ranker_tool. "
            "Do NOT remove any fields."
        ),
        expected_output=(
            "The full JSON list of the Top 5 ranked listings, "
            "including all original fields (id, url, title, etc.) "
            "plus the new 'match_score' and 'commute_time' fields."
        ),
        agent=agent,
        # 4. Important: update tools for this task
    tools=[batch_commute_tool, listing_ranker_tool],
        output_json=RankedListingsOutput,
    )


# --- APPLY CREW TASK ---
# (task unchanged)
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
