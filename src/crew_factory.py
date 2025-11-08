# FILE: src/crew_factory.py
from typing import Any

from crewai import Crew, Process

# Import your new agents and tasks
from .agents.housing_agents import create_apply_agent, create_ranking_agent, create_search_agent
from .tasks.housing_tasks import (
    create_housing_apply_task,
    create_housing_rank_task,
    create_housing_search_task,
)
from .utils.streamlit_callback import StreamlitCallbackHandler, create_step_callback


def get_crew(
    crew_type: str,
    inputs: dict,
    streamlit_callback: StreamlitCallbackHandler | None = None,
):
    """
    Factory function to create and configure a Crew based on type.
    'inputs' is now a dictionary containing all necessary data.
    """
    agents = []
    tasks = []

    if crew_type == "housing_search":
        # --- 1. Create the Housing Search Crew ---

        # Build callbacks
        search_cb = create_step_callback(streamlit_callback, "SearchAgent")
        rank_cb = create_step_callback(streamlit_callback, "RankingAgent")

        # Create agents
        search_agent = create_search_agent(step_callback=search_cb)
        ranking_agent = create_ranking_agent(step_callback=rank_cb)

        agents = [search_agent, ranking_agent]

        # Create tasks
        # We pass the criteria dict (which is inside the 'inputs' dict)
        criteria = inputs.get("criteria") or {}
        search_task = create_housing_search_task(search_agent, criteria)
        rank_task = create_housing_rank_task(ranking_agent, criteria)

        tasks = [search_task, rank_task]

    elif crew_type == "housing_apply":
        # --- 2. Create the Housing Apply Crew ---

        # Build callback
        apply_cb = create_step_callback(streamlit_callback, "ApplyAgent")

        # Create agent
        apply_agent = create_apply_agent(step_callback=apply_cb)

        agents = [apply_agent]

        # Create task
        user_profile = inputs.get("user_profile") or "{}"
        listing_details = inputs.get("listing_details") or "{}"
        apply_task = create_housing_apply_task(apply_agent, user_profile, listing_details)

        tasks = [apply_task]

    else:
        raise ValueError(f"Unknown crew_type: {crew_type}")

    # Assemble the crew
    agents_any: list[Any] = agents
    crew = Crew(
        agents=agents_any,
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )

    # Note: We return the crew, but the 'inputs' dictionary is
    # now handled by the app, so we don't need to return it.
    # The 'inputs' for kickoff() will be an empty dict,
    # because we already embedded the data *into* the task descriptions.
    return crew, {}
