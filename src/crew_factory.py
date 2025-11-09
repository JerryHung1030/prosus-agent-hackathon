# FILE: src/crew_factory.py
from typing import Any
import logging
import re

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
        import json

        # Get conversation context
        session_id = inputs.get("session_id")
        user_message = inputs.get("message", "")
        conversation_history = inputs.get("conversation_history", "")
        current_criteria = inputs.get("current_criteria", {})

        # ✅ DETECT URL IN USER MESSAGE - Run web_reason as subcrew
        url_match = re.search(r'https?://[^\s]+', user_message)
        if url_match:
            url = url_match.group(0)
            logging.info(f"🔗 Detected URL in conversation: {url}")
            logging.info(f"🤖 Running web_reason subcrew for internal extraction")

            # Step 1: Run web_reason crew internally to extract data
            from .agents.web_agents import create_web_reasoning_agent, DEFAULT_COMMUTE_TARGETS

            reasoning_cb = create_step_callback(streamlit_callback, "WebReasoningAgent")
            reasoning_agent = create_web_reasoning_agent(step_callback=reasoning_cb)

            # Build city defaults hint
            city_defaults = "\n".join([f"  - {city} → {target}" for city, target in DEFAULT_COMMUTE_TARGETS.items()])

            # Create autonomous reasoning task
            reasoning_task = Task(
                description=f"""
🔗 Analyze this housing listing URL and extract search parameters:
{url}

Use your WebsiteSearchTool to retrieve and analyze this page.

Extract these 4 canonical fields:
1. city: The city where the listing is located
2. price: Monthly rent in euros (as integer)
3. min_size: Total property size in m² (as integer)
4. commute_target: The most likely commute destination (ALWAYS inferred, never null)

### Commute Target Inference Rules:
- NEVER return null, "unknown", or leave it empty
- Use these defaults for major cities:
{city_defaults}
- For smaller cities, use "City Center" or "Central Station"
- Consider context: "student housing" → university, "business district" → downtown

### Output Format:
Return ONLY valid JSON:
{{
  "city": "Groningen",
  "price": 875,
  "min_size": 17,
  "commute_target": "Groningen City Center"
}}
""",
                expected_output="JSON object with city, price, min_size, commute_target (always inferred)",
                agent=reasoning_agent,
            )

            # Run subcrew to get extraction results
            subcrew = Crew(
                agents=[reasoning_agent],
                tasks=[reasoning_task],
                process=Process.sequential,
                verbose=True,
            )
            
            logging.info(f"🔄 Executing web_reason subcrew...")
            web_result = subcrew.kickoff()
            
            # Step 2: Parse the extracted data
            extracted = {}
            try:
                # Try to parse as JSON
                result_str = str(web_result)
                extracted = json.loads(result_str)
                logging.info(f"✅ Extracted data: {extracted}")
            except json.JSONDecodeError:
                # Try to find JSON in the response
                json_match = re.search(r'\{[^}]+\}', result_str)
                if json_match:
                    try:
                        extracted = json.loads(json_match.group(0))
                        logging.info(f"✅ Extracted data from text: {extracted}")
                    except:
                        logging.warning(f"⚠️ Could not parse JSON from web_reason result")
                        extracted = {}
            except Exception as e:
                logging.error(f"❌ Error parsing web_reason result: {e}")
                extracted = {}

            # Step 3: Update current_criteria with extracted data
            if extracted:
                current_criteria.update({
                    "city": extracted.get("city"),
                    "max_price": extracted.get("price"),
                    "min_size": extracted.get("min_size"),
                    "commute_target": extracted.get("commute_target"),
                })
                logging.info(f"📝 Updated criteria: {current_criteria}")

            # Step 4: Create verification task for MasterAgent
            master_cb = create_step_callback(streamlit_callback, "MasterAgent")
            master_agent = create_master_agent(step_callback=master_cb)

            verification_task = Task(
                description=f"""
You are coordinating a conversation about housing search and applications.

EXTRACTED DATA from URL:
{json.dumps(extracted, indent=2)}

CONVERSATION HISTORY:
{conversation_history}

USER'S CURRENT MESSAGE:
{user_message}

---
### YOUR JOB:
- Interpret user intent based on their most recent message.
- Never trigger a search or application without clear **positive consent**.
- Explicitly detect **negative or cancel intentions** (e.g., "no", "not now", "don't apply", "stop", "cancel", "wait", "later").
  If detected, acknowledge and halt the action politely.
- If the user updates any parameter (like budget or commute target), update the criteria but do **not trigger** unless the user confirms.

---
### DECISION RULES:

1. **If user explicitly says YES or gives consent** (e.g., "search", "find", "go ahead", "yes"):
   - Set `"ready_to_search": true`.
   - Use the trigger_housing_search tool with:
     - city: {extracted.get('city')}
     - max_price: {extracted.get('price')}
     - min_size: {extracted.get('min_size')}
     - commute_target: {extracted.get('commute_target')}

2. **If user explicitly says NO or cancels** (e.g., "don't apply", "stop", "not yet", "wait", "no thanks", "no"):
   - Set `"ready_to_search": false`.
   - Include a message like:
     > "Got it, I'll pause for now and won't apply or search until you ask me to continue."

3. **If user updates criteria but hasn't confirmed:**
   - Set `"is_complete": true` but `"ready_to_search": false`.
   - Update the field they mentioned
   - Ask: "Would you like me to search with these updated criteria?"

4. **If user neither confirms nor cancels yet (first time seeing the data):**
   - Present the extracted data in a friendly way:
     > "I analyzed that listing! It's in {extracted.get('city', 'unknown city')}, priced at €{extracted.get('price', '?')}/month, with {extracted.get('min_size', '?')}m² of space."
     > "I've inferred the commute target as '{extracted.get('commute_target', 'unknown')}' based on the location."
   - Set `"ready_to_search": false` and ask politely:
     > "Would you like me to search for similar listings with these criteria?"

5. **If extraction failed** (empty data):
   - Apologize and ask the user to provide the criteria manually.

---
### RESPONSE FORMAT:

Always respond as valid JSON:
{{
  "response": "<your natural language reply to user>",
  "extracted_criteria": {{
    "city": "{extracted.get('city')}",
    "max_price": {extracted.get('price')},
    "min_size": {extracted.get('min_size')},
    "commute_target": "{extracted.get('commute_target')}"
  }},
  "is_complete": true,
  "ready_to_search": true or false
}}

**CRITICAL**: If `"ready_to_search": false`, NEVER use the `trigger_housing_search` tool.
Only trigger it when user explicitly says yes or gives clear consent.
""",
                expected_output="Structured JSON response with explicit user intent and ready_to_search flag.",
                agent=master_agent,
            )

            # Return crew with verification task
            agents_any: list[Any] = [master_agent]
            crew = Crew(
                agents=agents_any,
                tasks=[verification_task],
                process=Process.sequential,
                verbose=True,
            )
            return crew, {}

        # Build callbacks for normal conversation flow
        master_cb = create_step_callback(streamlit_callback, "MasterAgent")
        search_cb = create_step_callback(streamlit_callback, "SearchAgent")
        rank_cb = create_step_callback(streamlit_callback, "RankingAgent")

        # Create all agents
        master_agent = create_master_agent(step_callback=master_cb)
        search_agent = create_search_agent(step_callback=search_cb)
        ranking_agent = create_ranking_agent(step_callback=rank_cb)

        agents = [master_agent, search_agent, ranking_agent]

        # Create conversation task
        task_description = f"""
You are coordinating a conversation about housing search and applications.

CONVERSATION HISTORY:
{conversation_history}

CURRENT COLLECTED INFORMATION:
- City: {current_criteria.get('city') or 'NOT YET PROVIDED ❌'}
- Budget (max price): {current_criteria.get('max_price') or 'NOT YET PROVIDED ❌'}
- Minimum size: {current_criteria.get('min_size') or 'NOT YET PROVIDED ❌'}
- Commute destination: {current_criteria.get('commute_target') or 'NOT YET PROVIDED ❌'}

USER'S NEW MESSAGE:
{user_message}

---
### YOUR JOB:
- Interpret user intent based on their most recent message.
- Never trigger a search or application without clear **positive consent**.
- Explicitly detect **negative or cancel intentions** (e.g., "no", "not now", "don't apply", "stop", "cancel", "wait", "later").
  If detected, acknowledge and halt the action politely.
- If the user updates any parameter (like budget or commute target), update the criteria but do **not trigger** unless the user confirms.

---
### DECISION RULES:

1. **If collecting criteria and information is still INCOMPLETE:**
   - Respond naturally to extract missing information.
   - Ask for ONE piece of information at a time.
   - Clearly tell the user what information you still need.
   - Example: "Great! I've recorded that your city is Amsterdam. Now, I still need to know: your budget, minimum size, and commute location. What is your budget?"
   - Set `"is_complete": false` and `"ready_to_search": false`.

2. **If ALL 4 criteria are complete BUT user has not given consent yet:**
   - Check if ALL 4 pieces show actual values (NOT "NOT YET PROVIDED"):
     * City: has a value
     * Budget (max price): has a number
     * Minimum size: has a number
     * Commute destination: has a value
   - Set `"is_complete": true` but `"ready_to_search": false`.
   - Ask politely: "Great! I have all the information. Would you like me to start the search now?"
   - DO NOT trigger the search yet.

3. **If user explicitly says YES or gives consent** (e.g., "search", "find", "go ahead", "yes", "start"):
   - Set `"ready_to_search": true`.
   - Use the trigger_housing_search tool with:
     - city: the collected city name
     - max_price: the collected budget number (as integer)
     - min_size: the collected size number (as integer)
     - commute_target: the collected commute destination string

4. **If user explicitly says NO or cancels** (e.g., "don't apply", "stop", "not yet", "wait", "no thanks", "no", "cancel"):
   - Set `"ready_to_search": false`.
   - Include a message like:
     > "Got it, I'll pause for now and won't apply or search until you ask me to continue."

5. **If user updates criteria** (e.g., "make it 800 euros max", "change commute to Zernike"):
   - Extract and update the relevant field in extracted_criteria.
   - Set `"is_complete": true` but `"ready_to_search": false`.
   - Confirm the change and ask: "Updated! Your budget is now €800. Want me to start the search with this new limit?"

6. **If user asks what is missing** (e.g., "What's still needed?"):
   - List all missing information clearly.

---
### RESPONSE FORMAT:

Always respond as valid JSON:
{{
  "response": "<your natural language reply to user>",
  "extracted_criteria": {{
    "city": "extracted city or null",
    "max_price": "extracted price number or null",
    "min_size": "extracted size number or null",
    "commute_target": "extracted location or null"
  }},
  "is_complete": true or false,
  "ready_to_search": true or false,
  "next_question": "What to ask next, or null if complete"
}}

**CRITICAL**: If `"ready_to_search": false`, NEVER use the `trigger_housing_search` tool.
Only trigger it when user explicitly says yes or gives clear consent.
"""

        master_task = Task(
            description=task_description,
            expected_output="A JSON response with the agent's reply and extracted criteria, or search results if all info is collected",
            agent=master_agent,
        )

        tasks = [master_task]

    elif crew_type == "web_reason":
        # --- 4a. Create the Web Reasoning Crew (with mandatory commute inference) ---
        from crewai import Task
        from .agents.web_agents import create_web_reasoning_agent, DEFAULT_COMMUTE_TARGETS

        # Build callback
        reasoning_cb = create_step_callback(streamlit_callback, "WebReasoningAgent")

        # Create reasoning agent
        reasoning_agent = create_web_reasoning_agent(step_callback=reasoning_cb)

        agents = [reasoning_agent]

        # Get URL from inputs
        url = inputs.get("url", "")
        if not url:
            raise ValueError("URL is required for web_reason crew_type")

        # Build city defaults hint
        city_defaults = "\n".join([f"  - {city} → {target}" for city, target in DEFAULT_COMMUTE_TARGETS.items()])

        # Create reasoning task with mandatory commute_target inference
        reasoning_task = Task(
            description=f"""
You are analyzing the following housing listing:
{url}

Use your WebsiteSearchTool to retrieve and interpret the full page content.

You must reason about the listing and extract the **canonical housing search parameters**:
1. city: The city or municipality where the listing is located.
2. price: The monthly rent in euros (integer).
3. min_size: The total property size in m² (integer).
4. commute_target: The **most likely commute destination**, inferred from context.

### Important Rules for commute_target:
- NEVER return null, "unknown", or leave it empty.
- If the listing is in a major city, infer the main business hub or downtown area.
  Standard defaults:
{city_defaults}
- If it's a smaller city not in the list, choose the central train station or main city center.
- Use your reasoning and world knowledge to pick the most probable destination.
- Consider neighborhood context: "Zuid" areas often mean business districts, "Centrum" means downtown.
- For student housing, infer the nearest university campus.

### Output Format
Return ONLY a valid JSON object with this schema:
{{
  "city": "Amsterdam",
  "price": 1450,
  "min_size": 55,
  "commute_target": "Amsterdam Zuidas"
}}

Be precise and always fill all four fields. The commute_target is MANDATORY.
""",
            expected_output="JSON object with fields: city, price, min_size, commute_target (always inferred, never null).",
            agent=reasoning_agent,
        )

        tasks = [reasoning_task]

    elif crew_type == "web_analysis":
        # --- 4b. Create the Web Analysis Crew (general extraction with confirmation) ---
        from crewai import Task
        from .agents.web_agents import create_web_explorer_agent, create_data_confirmation_agent

        # Build callbacks
        explorer_cb = create_step_callback(streamlit_callback, "WebExplorer")
        confirm_cb = create_step_callback(streamlit_callback, "DataConfirmation")

        # Create agents
        explorer_agent = create_web_explorer_agent(step_callback=explorer_cb)
        confirm_agent = create_data_confirmation_agent(step_callback=confirm_cb)

        agents = [explorer_agent, confirm_agent]

        # Get URL from inputs
        url = inputs.get("url", "")
        if not url:
            raise ValueError("URL is required for web_analysis crew_type")

        # Create exploration task
        exploration_task = Task(
            description=f"""
Analyze and extract structured data from the following URL:
{url}

YOUR TASK:
1. Use the web_extractor_tool to fetch and parse the page.
2. Identify what type of content it is (property listing, profile, general).
3. Extract all relevant structured data.
4. Present the findings in a clear, structured JSON format.

IMPORTANT EXTRACTION GUIDELINES:
- For property listings: Extract price, location, size, bedrooms, furnished status, pets policy, etc.
- For profile pages: Extract name, job title, company, location, estimated salary range, skills.
- For general content: Extract title, description, main headings, key information.

EXPECTED OUTPUT:
Return a JSON object with:
- url: the analyzed URL
- extract_type: 'property', 'profile', or 'general'
- All extracted fields (varies by type)
- confirmed: false (user has not confirmed yet)
- status: 'success' or 'error'

Remember: DO NOT take any automated actions yet. This is the data extraction phase only.
""",
            expected_output="A JSON object containing all extracted structured data from the URL",
            agent=explorer_agent,
        )

        # Create confirmation task
        confirmation_task = Task(
            description=f"""
Review the extracted data and present it clearly to the user for confirmation.

YOUR TASK:
1. Take the JSON data extracted from the URL.
2. Present it in a clear, human-readable format.
3. If it's a property listing, ask: "Would you like me to search for similar listings in this area?"
4. If it's a profile, explain the estimated salary range and other details.
5. Ask the user to confirm the data or request corrections.
6. Explain what will happen if they confirm (e.g., "I'll trigger a housing search with these criteria").

IMPORTANT:
- Make the data easy to understand
- Clearly state what action will be taken upon confirmation
- Allow the user to modify any field before proceeding
- DO NOT use any tools - this is just communication with the user

If the user confirms AND it's a property listing:
- Inform them that the explorer agent will now trigger the housing search
- Return confirmation status: confirmed=true

EXPECTED OUTPUT:
A clear message to the user with:
1. Formatted extracted data
2. Question asking for confirmation or corrections
3. Explanation of next steps if confirmed
""",
            expected_output="A user-friendly presentation of the data with a clear call-to-action for confirmation",
            agent=confirm_agent,
            context=[exploration_task],
        )

        tasks = [exploration_task, confirmation_task]

        # If this is a follow-up request (user has confirmed), add search trigger task
        if inputs.get("confirmed") and inputs.get("extract_type") == "property":
            # Create search trigger task
            search_trigger_task = Task(
                description=f"""
The user has confirmed the extracted property data. Now trigger the housing search.

Use the trigger_housing_search tool with the confirmed data:
- city: {inputs.get('city') or inputs.get('location')}
- max_price: {inputs.get('price') or inputs.get('max_price')}
- min_size: {inputs.get('size_m2') or inputs.get('min_size')}
- commute_target: {inputs.get('commute_target')}

This will automatically start the housing_search crew to find similar listings.

EXPECTED OUTPUT:
Confirmation that the search has been triggered and what to expect next.
""",
                expected_output="Confirmation message that the housing search has been initiated",
                agent=explorer_agent,
                context=[exploration_task, confirmation_task],
            )
            tasks.append(search_trigger_task)

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
