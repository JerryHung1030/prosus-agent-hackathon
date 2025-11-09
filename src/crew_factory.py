# FILE: src/crew_factory.py
from typing import Any

from crewai import Crew, Process

# Import your new agents and tasks
from .agents.housing_agents import (
    create_apply_agent,
    create_master_agent,
    create_ranking_agent,
    create_search_agent,
)
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

    elif crew_type == "conversation":
        # --- 3. Create the Conversation Crew with Master Agent ---
        from crewai import Task

        # Build callbacks
        master_cb = create_step_callback(streamlit_callback, "MasterAgent")
        search_cb = create_step_callback(streamlit_callback, "SearchAgent")
        rank_cb = create_step_callback(streamlit_callback, "RankingAgent")

        # Create all agents
        master_agent = create_master_agent(step_callback=master_cb)
        search_agent = create_search_agent(step_callback=search_cb)
        ranking_agent = create_ranking_agent(step_callback=rank_cb)

        agents = [master_agent, search_agent, ranking_agent]

        # Get conversation context
        session_id = inputs.get("session_id")
        user_message = inputs.get("message", "")
        conversation_history = inputs.get("conversation_history", "")
        current_criteria = inputs.get("current_criteria", {})

        # Create conversation task
        task_description = f"""
You are having a conversation with a user looking for rental housing.

CONVERSATION HISTORY:
{conversation_history}

CURRENT COLLECTED INFORMATION:
- City: {current_criteria.get('city') or 'NOT YET PROVIDED ❌'}
- Budget (max price): {current_criteria.get('max_price') or 'NOT YET PROVIDED ❌'}
- Minimum size: {current_criteria.get('min_size') or 'NOT YET PROVIDED ❌'}
- Commute destination: {current_criteria.get('commute_target') or 'NOT YET PROVIDED ❌'}

USER'S NEW MESSAGE:
{user_message}

YOUR TASK:
1. Respond naturally to the user's message.
2. Extract any housing criteria mentioned by the user (city, budget, size, commute location).
3. IMPORTANT: In your response, ALWAYS clearly tell the user what information you still need.
   - Example: "Great! I've recorded that your city is Amsterdam. Now, I still need to know: your budget, minimum size, and commute location. What is your budget?"
   - Example: "Awesome! Now I have the city and your budget. I still need: minimum size and commute location. How large should the property be at minimum?"
4. If the user asks what is missing (for example: "What's still needed?"), list all missing information clearly.
5. **CRITICAL - MANDATORY TOOL USE**: Check the CURRENT COLLECTED INFORMATION section above.
   If ALL 4 pieces show actual values (NOT "NOT YET PROVIDED"):
   - City: has a value
   - Budget (max price): has a number
   - Minimum size: has a number
   - Commute destination: has a value
   
   Then you MUST IMMEDIATELY use the trigger_housing_search tool.
   DO NOT just respond with text saying you will search.
   DO NOT delegate to other agents yet.
   FIRST use the tool trigger_housing_search with:
   - city: the collected city name
   - max_price: the collected budget number (as integer)
   - min_size: the collected size number (as integer)
   - commute_target: the collected commute destination string
   
6. Always ask for ONE piece of information at a time when collecting.

RESPONSE FORMAT:
Provide your response as JSON with this structure:
{{
    "response": "Your natural language response (MUST include what's still needed)",
    "extracted_criteria": {{
        "city": "extracted city or null",
        "max_price": "extracted price number or null",
        "min_size": "extracted size number or null",
        "commute_target": "extracted location or null"
    }},
    "is_complete": "true or false",
    "next_question": "What to ask next, or null if complete"
}}
"""

        master_task = Task(
            description=task_description,
            expected_output="A JSON response with the agent's reply and extracted criteria, or search results if all info is collected",
            agent=master_agent,
        )

        tasks = [master_task]

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
