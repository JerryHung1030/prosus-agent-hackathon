# FILE: ./test_full_chain.py
# ------------------------------------------------------------------
# !! This is your new primary integration test file !!
#
# This script simulates the full automated workflow:
# 1. Simulate a conversation with the conversation_agent to collect criteria.
# 2. Listen for the "trigger_search_tool" signal.
# 3. Trigger the housing_search crew.
# 4. Trigger the housing_apply crew.
#
# How to run:
# 1. Ensure your .env is configured (OPENAI_API_KEY, GOOGLE_MAPS_API_KEY,
#    PARARIUS_USER, PARARIUS_PASS)
# 2. Run in your terminal:
#    python test_full_chain.py
# ------------------------------------------------------------------

import json
import os
import re
import uuid
from typing import Any  # 'dict' is built-in; remove invalid import

from pydantic import ValidationError

# Import CrewAI runner
from src.main import run_main_crew

# Import Pydantic model to safely parse results
from src.tasks.housing_tasks import RankedListingsOutput


def get_user_profile():
    """Helper: Build user profile from environment variables."""
    return {
        "username": os.getenv("PARARIUS_USER", "xxx"),
        "password": os.getenv("PARARIUS_PASS", "xxx"),
        "salutation": "0",
        "employment_status": "3",
        "gross_income": "[1000,1500]",
        "guarantor": "3",
        "living_situation": "1",
        "has_pets": False,
        "start_date": "2025-12-01",
        "rental_duration": "5",
        "current_situation": "i_dont_rent_or_own_a_roof_yet",
        "full_name": "Jerry Hung",
        "email": os.getenv("PARARIUS_USER", "xxx"),
        "phone": "+31612345678",
    }


def strip_markdown_json(s: str | None) -> str:
    """Remove markdown fences from a JSON-formatted string if present."""
    if not s:
        return ""
    m = re.search(r"```json\s*([\s\S]*?)\s*```", s)
    if m:
        return m.group(1)
    m = re.search(r"```\s*([\s\S]*?)\s*```", s)
    if m:
        return m.group(1)
    return s


def parse_conversation_result(crew_output_obj) -> dict[str, Any]:
    """Parse the conversation crew output and return either a trigger signal or chat response."""
    try:
        # CrewOutput object contains multiple tasks; we care about the last one
        final_task_output = crew_output_obj.tasks[-1].output

        # Check whether the agent invoked the trigger_search_tool
        if final_task_output.tool_calls:
            tool_call = final_task_output.tool_calls[0]
            if tool_call.name == "trigger_housing_search":
                print("[Debug] 'trigger_housing_search' tool call detected.")
                return {
                    "action": "TRIGGER_SEARCH",
                    "criteria": tool_call.args,
                    "response": f"Tool call: trigger_housing_search with {tool_call.args}",
                }

        # If there's no tool call, it should be a raw string containing a JSON response
        raw_output = final_task_output.raw
        parsed_json = json.loads(strip_markdown_json(raw_output))
        print(f"[Debug] Parsed chat response: {parsed_json}")
        return {
            "action": "CONTINUE_CHAT",
            "criteria": parsed_json.get("extracted_criteria", {}),
            "response": parsed_json.get("response", "No response found."),
        }

    except (IndexError, AttributeError, json.JSONDecodeError, TypeError) as e:
        print(f"[Warn] Could not parse conversation output: {e}")
        print(f"[Debug] Raw output object: {crew_output_obj}")
        return {
            "action": "ERROR",
            "criteria": {},
            "response": f"Failed to parse agent output: {e}",
        }


def parse_search_result(crew_output_obj) -> list:
    """Helper to extract a list of listings from a Pydantic RootModel or task output."""
    try:
        # .to_pydantic() is preferred in CrewAI >1.0
        pydantic_obj = crew_output_obj.to_pydantic()
        if isinstance(pydantic_obj, RankedListingsOutput):
            print("[Debug] Successfully extracted list via .to_pydantic()")
            return pydantic_obj.root
    except (ValidationError, AttributeError, Exception):
        pass

    # Fallback: check the last task's output
    try:
        task_output = crew_output_obj.tasks[-1].output
        if isinstance(task_output, RankedListingsOutput):
            print("[Debug] Successfully extracted list via .tasks[-1].output")
            return task_output.root
    except (IndexError, AttributeError):
        pass

    print(f"[Warn] Could not parse search result object: {type(crew_output_obj)}")
    return []


def parse_apply_result(apply_result) -> str:
    """Helper to extract text from the apply result object."""
    if hasattr(apply_result, "raw") and isinstance(apply_result.raw, str):
        return apply_result.raw
    if hasattr(apply_result, "tasks") and apply_result.tasks:
        try:
            return str(apply_result.tasks[-1].output.raw)
        except Exception:
            pass
    return str(apply_result)


def main_test_chain():
    """Run the full "Conversation -> Search -> Auto-Apply" chained workflow."""
    session_id = str(uuid.uuid4())
    user_profile = get_user_profile()
    conversation_history = []
    current_criteria = {}

    # --- 1. Simulated conversation inputs ---
    # Pretend to be the user and provide information step-by-step
    mock_user_inputs = [
        "Hi, I need help finding a place.",
        "I want to live in Eindhoven.",
        "My budget is around 1500.",
        "It needs to be at least 50 square meters.",
        "I need to commute to 'Groene Loper 3, 5612 AE Eindhoven'.",
    ]

    print("=" * 70)
    print("--- 1. STARTING CONVERSATION FLOW ---")
    print(f"Session ID: {session_id}")
    print("=" * 70)

    final_criteria = None

    for i, message in enumerate(mock_user_inputs):
        print(f"\n[User Message {i+1}]: {message}")
        conversation_history.append(f"User: {message}")

        inputs = {
            "session_id": session_id,
            "message": message,
            # Only send the most recent 5 conversation turns
            "conversation_history": "\n".join(conversation_history[-5:]),
            "current_criteria": current_criteria,
        }

        # --- Call Conversation Crew ---
        try:
            conversation_result_obj = run_main_crew("conversation", inputs, None)
            parsed_response = parse_conversation_result(conversation_result_obj)

            print(f"[Agent Response]: {parsed_response['response']}")
            conversation_history.append(f"Agent: {parsed_response['response']}")

            # Update the tracked criteria
            if parsed_response.get("criteria"):
                # Filter out null values
                updates = {k: v for k, v in parsed_response["criteria"].items() if v is not None}
                if updates:
                    current_criteria.update(updates)
                    print(f"[Debug] Updated criteria: {current_criteria}")

            # --- Check if a trigger was emitted ---
            if parsed_response["action"] == "TRIGGER_SEARCH":
                print("\n" + "=" * 70)
                print("--- 1b. CONVERSATION COMPLETE ---")
                print("Agent successfully triggered search!")
                final_criteria = parsed_response["criteria"]
                break

        except Exception as e:
            print(f"[FATAL ERROR] Conversation crew failed: {e}")
            return

    # Check whether all criteria were collected successfully
    if not final_criteria:
        print("\n" + "=" * 70)
        print("--- TEST FAILED: Conversation did not trigger search ---")
        print(f"Final collected criteria: {current_criteria}")
        print("=" * 70)
        return

    # --- 2. Run "housing_search" Crew ---
    print("\n" + "=" * 70)
    print("--- 2. STARTING SEARCH FLOW ---")
    print(f"Using criteria: {json.dumps(final_criteria)}")
    print("=" * 70)

    try:
        search_inputs = {"criteria": final_criteria}
        search_result_obj = run_main_crew("housing_search", search_inputs, None)

        top_listings = parse_search_result(search_result_obj)

        if not top_listings:
            print("\n" + "=" * 70)
            print("--- 2b. SEARCH COMPLETE (NO RESULTS) ---")
            print("Search finished, but no listings were found.")
            print("=" * 70)
            return

        print("\n" + "=" * 70)
        print(f"--- 2b. SEARCH COMPLETE (Found {len(top_listings)}) ---")
        for i, listing in enumerate(top_listings):
            print(
                f"  {i+1}. {listing.get('title')} (Score: {listing.get('match_score')}, "
                f"Commute: {listing.get('commute_time')})"
            )
        print("=" * 70)

    except Exception as e_search:
        print(f"\n[FATAL ERROR] Error during main search workflow: {e_search}\n")
        return

    # --- 3. Automatically loop and run "housing_apply" Crew ---
    print(f"\n--- 3. STARTING AUTO-APPLY for {len(top_listings)} listings ---")

    for i, listing in enumerate(top_listings):
        print(f"\n--- Applying to listing {i+1}/{len(top_listings)}: {listing.get('title')} ---")
        try:
            apply_inputs = {
                "user_profile": json.dumps(user_profile),
                "listing_details": json.dumps(listing),
            }
            apply_result = run_main_crew("housing_apply", apply_inputs, None)
            result_text = parse_apply_result(apply_result)
            print(f"[APPLY RESULT ({i+1})]: {result_text}")

        except Exception as e_apply:
            print(f"\n[ERROR] Applying to listing {i+1} FAILED: {e_apply}\n")

    print("\n" + "=" * 70)
    print("--- 4. FULL CHAIN TEST COMPLETE ---")
    print("=" * 70)


if __name__ == "__main__":
    main_test_chain()
