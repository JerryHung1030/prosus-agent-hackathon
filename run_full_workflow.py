# FILE: ./run_full_workflow.py
import json
import os
import re

# CrewAI entry point
from src.main import run_main_crew

# Pydantic model for safe extraction
from src.tasks.housing_tasks import RankedListingsOutput


def strip_markdown_json(s: str | None) -> str:
    """Remove markdown code fences from a JSON string if present."""
    if not s:
        return ""
    m = re.search(r"```json\s*([\s\S]*?)\s*```", s)
    if m:
        return m.group(1)
    m = re.search(r"```\s*([\s\S]*?)\s*```", s)
    if m:
        return m.group(1)
    return s


def get_user_profile():
    """Helper: build user profile from environment variables."""
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


def parse_search_result(crew_output_obj) -> list:
    """Extract list of ranked listings from CrewOutput / RootModel / JSON."""
    extracted_result = None

    # 1. Try .to_pydantic() if available
    if hasattr(crew_output_obj, "to_pydantic"):
        try:
            # Expected to return RankedListingsOutput
            extracted_result = crew_output_obj.to_pydantic()
            print("[Debug] Successfully extracted result via .to_pydantic()")
        except Exception as e:
            print(f"[Warn] Failed to call .to_pydantic(): {e}")

    # 2. Fallback: last task output
    if extracted_result is None and hasattr(crew_output_obj, "tasks") and crew_output_obj.tasks:
        try:
            # Acquire final task output
            extracted_result = crew_output_obj.tasks[-1].output
            print("[Debug] Successfully extracted result via .tasks[-1].output")
        except Exception as e:
            print(f"[Warn] Failed to read .tasks[-1].output: {e}")

    # 3. Last resort: object itself
    if extracted_result is None:
        extracted_result = crew_output_obj

    # CrewOutput-specific attributes (final_output/output/raw)
    try:
        final_output = getattr(extracted_result, "final_output", None)
        if isinstance(final_output, list):
            print("[Debug] Result from CrewOutput.final_output (list)")
            return final_output
        if isinstance(final_output, str):
            try:
                parsed = json.loads(strip_markdown_json(final_output))
                if isinstance(parsed, list):
                    print("[Debug] Result from CrewOutput.final_output (json string)")
                    return parsed
            except Exception:
                pass
    except Exception:
        pass

    try:
        output_attr = getattr(extracted_result, "output", None)
        if isinstance(output_attr, list):
            print("[Debug] Result from CrewOutput.output (list)")
            return output_attr
        if isinstance(output_attr, str):
            try:
                parsed = json.loads(strip_markdown_json(output_attr))
                if isinstance(parsed, list):
                    print("[Debug] Result from CrewOutput.output (json string)")
                    return parsed
            except Exception:
                pass
    except Exception:
        pass

    try:
        raw = getattr(extracted_result, "raw", None)
        if isinstance(raw, str):
            parsed = json.loads(strip_markdown_json(raw))
            if isinstance(parsed, list):
                print("[Debug] Result parsed from CrewOutput.raw")
                return parsed
    except Exception:
        pass

    # Pydantic v2 RootModel?
    if isinstance(extracted_result, RankedListingsOutput):
        print("[Debug] Result is RankedListingsOutput")
        return extracted_result.root

    # v1 style .root attribute
    if hasattr(extracted_result, "root") and isinstance(
        getattr(extracted_result, "root", None), list
    ):
        print("[Debug] Result has .root attribute")
        return extracted_result.root

    # Plain list already
    if isinstance(extracted_result, list):
        print("[Debug] Result is a plain list")
        return extracted_result

    # Try .json() (v1/v2) for list
    try:
        json_fn = getattr(extracted_result, "json", None)
        if callable(json_fn):
            txt = json_fn()
            if isinstance(txt, str):
                parsed = json.loads(txt)
                if isinstance(parsed, list):
                    print("[Debug] Result parsed from .json()")
                    return parsed
    except Exception:
        pass

    # String JSON list (Final Answer as text)
    if isinstance(extracted_result, str):
        try:
            clean = strip_markdown_json(extracted_result)
            parsed = json.loads(clean)
            if isinstance(parsed, list):
                print("[Debug] Result parsed from JSON string")
                return parsed
        except Exception:
            pass

    print(f"[Warn] Unexpected parsed result type: {type(extracted_result)}")
    return []


def parse_apply_result(apply_result) -> str:
    """Extract textual apply result from CrewOutput / task output."""
    if hasattr(apply_result, "raw") and isinstance(apply_result.raw, str):
        return apply_result.raw

    # Fallback: maybe CrewOutput tasks
    if hasattr(apply_result, "tasks") and apply_result.tasks:
        try:
            return str(apply_result.tasks[-1].output)
        except Exception:
            pass

    return str(apply_result)


def main():
    """Run full search -> auto-apply workflow."""

    # 1. Define inputs (hardcoded for CLI run)
    hardcoded_criteria = {
        "city": "Eindhoven",
        "price": 1500,
        "size": 50,
        "commute_target": "Groene Loper 3, 5612 AE Eindhoven",
    }
    user_profile = get_user_profile()

    print("=" * 70)
    print("--- 1. STARTING FULL WORKFLOW (SEARCH + AUTO-APPLY) ---")
    print(f"Criteria: {json.dumps(hardcoded_criteria)}")
    print("=" * 70)

    # 2. Run housing_search crew
    try:
        search_inputs = {"criteria": hardcoded_criteria}
        # Note: streamlit_callback=None since not running in Streamlit

        # search_result_obj is a CrewOutput
        search_result_obj = run_main_crew("housing_search", search_inputs, None)

        # 3. Parse search result
        top_listings = parse_search_result(search_result_obj)

        if not top_listings:
            print("\n" + "=" * 70)
            print("--- 2. SEARCH COMPLETE (NO RESULTS) ---")
            print("Search finished, but no listings were found.")
            print("=" * 70)
            return

        print("\n" + "=" * 70)
        print(f"--- 2. SEARCH COMPLETE (Found {len(top_listings)}) ---")
        for i, listing in enumerate(top_listings):
            print(
                f"  {i+1}. {listing.get('title')} (Score: {listing.get('match_score')}, "
                f"Commute: {listing.get('commute_time')})"
            )
        print("=" * 70)

        # 4. Loop auto-applications via housing_apply crew
        print(f"\n--- 3. STARTING AUTO-APPLY for {len(top_listings)} listings ---")

        for i, listing in enumerate(top_listings):
            print(
                f"\n--- Applying to listing {i+1}/{len(top_listings)}: {listing.get('title')} ---"
            )

            try:
                apply_inputs = {
                    "user_profile": json.dumps(user_profile),
                    "listing_details": json.dumps(listing),
                }

                # Invoke apply crew per listing
                apply_result = run_main_crew("housing_apply", apply_inputs, None)

                result_text = parse_apply_result(apply_result)
                print(f"[APPLY RESULT ({i+1})]: {result_text}")

            except Exception as e_apply:
                print(f"\n[ERROR] Applying to listing {i+1} FAILED: {e_apply}\n")

        print("\n" + "=" * 70)
        print("--- 4. FULL WORKFLOW COMPLETE ---")
        print("=" * 70)

    except Exception as e_search:
        print(f"\n[FATAL ERROR] Error during main search workflow: {e_search}\n")


if __name__ == "__main__":
    main()
