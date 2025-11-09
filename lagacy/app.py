# FILE: ./app.py
import json
import os
import re

import pandas as pd
import streamlit as st

from src.main import run_main_crew
from src.utils.streamlit_callback import StreamlitCallbackHandler


def strip_markdown_json(s: str | None) -> str:
    """Return s without markdown code fences; tolerate None by returning empty string."""
    if not s:
        return ""
    match = re.search(r"```json\s*([\s\S]*?)\s*```", s)
    if match:
        return match.group(1)
    match = re.search(r"```\s*([\s\S]*?)\s*```", s)
    if match:
        return match.group(1)
    return s


def _json_text(obj: object) -> str | None:
    """Safely get JSON text from obj.json which may be a property or a method."""
    try:
        val = getattr(obj, "json", None)
        if callable(val):
            try:
                res = val()
                return res if isinstance(res, str) else None
            except Exception:
                return None
        if isinstance(val, str):
            return val
        return None
    except Exception:
        return None


def get_next_chat_response():
    """Simulates an LLM checking st.session_state.criteria to ask the next question."""
    if "criteria" not in st.session_state:
        st.session_state.criteria = {
            "city": None,
            "price": None,
            "size": None,
            "commute_target": None,
        }

    if st.session_state.criteria["city"] is None:
        return "Hello! I can help you find a rental. What city are you looking to live in?"
    if st.session_state.criteria["price"] is None:
        return "Got it. What's your maximum monthly budget (e.g., 1500)?"
    if st.session_state.criteria["size"] is None:
        return "Okay. What's the minimum size you need (in m²)?"
    if st.session_state.criteria["commute_target"] is None:
        return (
            "Great. Finally, what is your primary commute destination "
            "(e.g., an office or university address)?"
        )

    st.session_state.search_ready = True
    return f"""
    Perfect! I have all your criteria:
    - **City:** {st.session_state.criteria['city']}
    - **Budget:** €{st.session_state.criteria['price']}
    - **Min Size:** {st.session_state.criteria['size']} m²
    - **Commute To:** {st.session_state.criteria['commute_target']}
    
    Press the 'Start Search' button below when you are ready.
    """


def update_criteria_from_prompt(prompt: str):
    """Extract user-provided criteria from chat messages."""
    if st.session_state.criteria["city"] is None:
        st.session_state.criteria["city"] = prompt
        return
    if st.session_state.criteria["price"] is None:
        try:
            st.session_state.criteria["price"] = int("".join(filter(str.isdigit, prompt)))
        except Exception:
            st.session_state.criteria["price"] = 1500
        return
    if st.session_state.criteria["size"] is None:
        try:
            st.session_state.criteria["size"] = int("".join(filter(str.isdigit, prompt)))
        except Exception:
            st.session_state.criteria["size"] = 50
        return
    if st.session_state.criteria["commute_target"] is None:
        st.session_state.criteria["commute_target"] = prompt
        return


def get_user_profile():
    """Helper function to build the user profile dictionary."""
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


def parse_crew_result(final_result) -> tuple[str, str | None]:
    """Normalize crew output (list RootModel, dict/raw/string) into (text, image_path)."""
    image_path: str | None = None

    # RootModel list? (Pydantic v2 RootModel / v1 custom models)
    try:
        root_list = final_result.root  # type: ignore[attr-defined]
    except AttributeError:
        root_list = None
    if isinstance(root_list, list):
        result_text = str(root_list)
    else:
        json_txt = _json_text(final_result)
        if json_txt:
            try:
                parsed = json.loads(json_txt)
                if isinstance(parsed, dict):
                    result_text = parsed.get("result") or str(parsed)
                else:
                    result_text = str(parsed)
            except Exception:
                result_text = str(final_result)
        elif hasattr(final_result, "raw") and isinstance(final_result.raw, str):
            result_text = final_result.raw
        else:
            result_text = str(final_result)

    if "Screenshot saved as " in result_text:
        path_part = result_text.split("Screenshot saved as ")[-1].strip().rstrip(".")
        if os.path.exists(path_part) and path_part.endswith(".png"):
            image_path = path_part

    return result_text, image_path


def main():
    st.set_page_config(page_title="🤖 Pararius AI Scout (Fixed)", layout="wide")
    st.title("🤖 Pararius AI Scout (Pydantic parsing fixed)")

    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.session_state.criteria = {
            "city": None,
            "price": None,
            "size": None,
            "commute_target": None,
        }
        st.session_state.search_ready = False
        st.session_state.search_results = None
        st.session_state.final_result_md = ""
        first_msg = get_next_chat_response()
        st.session_state.messages.append({"role": "assistant", "content": first_msg})

    col_chat, col_log = st.columns([2, 1.5])

    with col_chat:
        st.subheader("1. AI Chat & Results")
        chat_container = st.container(height=500, border=True)
        with chat_container:
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    if "content" in message:
                        st.markdown(message["content"])
                    elif "image" in message:
                        st.image(message["image"], caption="Application Proof")

        if st.session_state.search_ready and st.session_state.search_results is None:
            if st.button("🚀 Start Search Top 5", type="primary", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": "Start search!"})
                with chat_container:
                    with st.chat_message("user"):
                        st.markdown("Start search!")

                with st.spinner(
                    "🕵️‍♂️ Searching listings... Ranking listings... (this may take a moment)"
                ):
                    log_container = col_log.container(height=500, border=True)
                    streamlit_callback = StreamlitCallbackHandler(log_container)
                    crew_inputs = {"criteria": st.session_state.criteria}

                    try:
                        final_result = run_main_crew(
                            "housing_search", crew_inputs, streamlit_callback
                        )
                        results_list: list = []

                        # Normalize final_result to list
                        if isinstance(final_result, list):
                            results_list = final_result
                        else:
                            try:
                                root_list = final_result.root  # type: ignore[attr-defined]
                            except AttributeError:
                                root_list = None
                            if isinstance(root_list, list):
                                results_list = root_list
                            elif isinstance(final_result, dict):
                                json_txt = _json_text(final_result)
                                if json_txt:
                                    try:
                                        final_result = json.loads(json_txt)
                                    except Exception:
                                        pass
                                if "results" in final_result and isinstance(
                                    final_result["results"], list
                                ):
                                    results_list = final_result["results"]
                                elif "listings" in final_result and isinstance(
                                    final_result["listings"], list
                                ):
                                    results_list = final_result["listings"]
                                elif "result" in final_result and isinstance(
                                    final_result["result"], list
                                ):
                                    results_list = final_result["result"]
                                else:
                                    st.session_state.final_result_md = (
                                        "Search finished, but output format unexpected "
                                        "(not a list). Raw: "
                                        f"{str(final_result)}"
                                    )
                            elif isinstance(final_result, str):
                                clean_json_str = strip_markdown_json(final_result)
                                try:
                                    parsed = json.loads(clean_json_str)
                                    if isinstance(parsed, list):
                                        results_list = parsed
                                except Exception as e:
                                    st.session_state.final_result_md = (
                                        "Search finished, but failed parsing string: "
                                        f"{e}. Raw: {final_result}"
                                    )
                            else:
                                st.session_state.final_result_md = (
                                    "Search finished, but output type unsupported: "
                                    f"{type(final_result)}"
                                )

                        st.session_state.search_results = results_list
                        st.session_state.final_result_md = (
                            f"Found {len(results_list)} matching listings!"
                        )
                        if not results_list and not st.session_state.final_result_md:
                            st.session_state.final_result_md = (
                                "Search finished, no matching listings found."
                            )

                    except Exception as e:
                        st.session_state.final_result_md = f"Error while running crew: {e}"

                st.session_state.messages.append(
                    {"role": "assistant", "content": st.session_state.final_result_md}
                )
                st.rerun()

        if st.session_state.search_results is not None:
            with chat_container:
                st.subheader("Top 5 Matches")

                # Ensure search_results is a list
                if not isinstance(st.session_state.search_results, list):
                    st.error("Result is not a list; cannot display.")
                    results_df = pd.DataFrame()
                else:
                    results_df = pd.DataFrame(st.session_state.search_results)

                # Check if DataFrame empty or missing key columns
                if results_df.empty:
                    st.warning("Got a result but the list is empty.")
                elif "title" not in results_df.columns or "url" not in results_df.columns:
                    st.error("Missing 'title' or 'url' field in data; cannot show apply buttons.")
                    st.dataframe(results_df, use_container_width=True)
                else:
                    st.dataframe(results_df, use_container_width=True)
                    st.markdown("---")

                    # --- Feature: Apply All Button ---
                    if st.button(
                        "🚀🚀 Apply to ALL Top 5",
                        type="primary",
                        use_container_width=True,
                        key="apply_all",
                    ):
                        st.session_state.messages.append(
                            {"role": "user", "content": "Apply to all Top 5!"}
                        )
                        with st.spinner(
                            "🚀 Batch applying... (this can take a few minutes, don't close) ☕"
                        ):
                            user_profile_dict = get_user_profile()
                            total = len(st.session_state.search_results)

                            for i, listing in enumerate(st.session_state.search_results):
                                # Reset log container each iteration
                                log_container = col_log.container(height=500, border=True)
                                log_container.info(
                                    f"--- Applying {i+1}/{total}: {listing.get('title')} ---"
                                )
                                streamlit_callback = StreamlitCallbackHandler(log_container)

                                crew_inputs = {
                                    "user_profile": json.dumps(user_profile_dict),
                                    "listing_details": json.dumps(listing),
                                }

                                try:
                                    final_result = run_main_crew(
                                        "housing_apply", crew_inputs, streamlit_callback
                                    )
                                    result_text, image_path = parse_crew_result(final_result)

                                    st.session_state.messages.append(
                                        {"role": "assistant", "content": result_text}
                                    )
                                    if image_path:
                                        st.session_state.messages.append(
                                            {"role": "assistant", "image": image_path}
                                        )

                                except Exception as e:
                                    err_msg = f"Listing #{i+1} application failed: {e}"
                                    st.session_state.messages.append(
                                        {"role": "assistant", "content": err_msg}
                                    )

                        st.session_state.messages.append(
                            {"role": "assistant", "content": "✅ Batch apply finished!"}
                        )
                        st.rerun()

                    st.markdown("---")
                    st.markdown("Or apply to a single listing:")

                    # --- Single apply buttons ---
                    for i, listing in enumerate(st.session_state.search_results):
                        if st.button(
                            f"Apply listing #{i+1} ({listing.get('title', 'N/A')})",
                            key=f"apply_{i}",
                            use_container_width=True,
                        ):
                            with st.spinner(
                                f"🚀 ApplyAgent logging in and applying listing #{i+1}..."
                            ):
                                log_container = col_log.container(height=500, border=True)
                                streamlit_callback = StreamlitCallbackHandler(log_container)
                                user_profile_dict = get_user_profile()

                                crew_inputs = {
                                    "user_profile": json.dumps(user_profile_dict),
                                    "listing_details": json.dumps(listing),
                                }

                                try:
                                    final_result = run_main_crew(
                                        "housing_apply", crew_inputs, streamlit_callback
                                    )
                                    result_text, image_path = parse_crew_result(final_result)

                                    st.session_state.messages.append(
                                        {"role": "assistant", "content": result_text}
                                    )
                                    if image_path:
                                        st.session_state.messages.append(
                                            {"role": "assistant", "image": image_path}
                                        )

                                except Exception as e:
                                    err_msg = f"An error occurred: {e}"
                                    st.session_state.messages.append(
                                        {"role": "assistant", "content": err_msg}
                                    )
                            st.rerun()

    if prompt := st.chat_input("Your message..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)

        update_criteria_from_prompt(prompt)
        response = get_next_chat_response()
        st.session_state.messages.append({"role": "assistant", "content": response})
        with chat_container:
            with st.chat_message("assistant"):
                st.markdown(response)

        if st.session_state.search_ready:
            st.rerun()

    with col_log:
        st.subheader("2. AI Execution Log")
        if not any(st.session_state.get(key) for key in ["search_ready", "search_results"]):
            st.container(height=500, border=True).markdown(
                "*(Agent thoughts will stream here during execution...)*"
            )


if __name__ == "__main__":
    main()
