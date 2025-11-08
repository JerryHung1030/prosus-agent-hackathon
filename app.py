# FILE: ./app.py
import json
import os

import pandas as pd
import streamlit as st

from src.main import run_main_crew
from src.utils.streamlit_callback import StreamlitCallbackHandler


# --- Mock LLM Call for Chat (For Hackathon) ---
# (This section is unchanged)
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

    # All criteria are full!
    st.session_state.search_ready = True
    return f"""
    Perfect! I have all your criteria:
    - **City:** {st.session_state.criteria['city']}
    - **Budget:** €{st.session_state.criteria['price']}
    - **Min Size:** {st.session_state.criteria['size']} m²
    - **Commute To:** {st.session_state.criteria['commute_target']}
    
    Press the 'Start Search' button below when you are ready.
    """


def update_criteria_from_prompt(prompt):
    """Simulates an LLM extracting data from the user's prompt."""
    if st.session_state.criteria["city"] is None:
        st.session_state.criteria["city"] = prompt
        return
    if st.session_state.criteria["price"] is None:
        # Simple number extraction
        try:
            st.session_state.criteria["price"] = int("".join(filter(str.isdigit, prompt)))
        except Exception:
            st.session_state.criteria["price"] = 1500  # default fallback
        return
    if st.session_state.criteria["size"] is None:
        try:
            st.session_state.criteria["size"] = int("".join(filter(str.isdigit, prompt)))
        except Exception:
            st.session_state.criteria["size"] = 50  # default fallback
        return
    if st.session_state.criteria["commute_target"] is None:
        st.session_state.criteria["commute_target"] = prompt
        return


def main():
    st.set_page_config(page_title="Pararius AI Scout", layout="wide")
    st.title("🤖 Pararius AI Scout")

    # --- Initialize Session State ---
    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.session_state.criteria = {
            "city": None,
            "price": None,
            "size": None,
            "commute_target": None,
        }
        st.session_state.search_ready = False  # Gate for running search
        st.session_state.search_results = None  # To store the Top 5
        st.session_state.final_result_md = ""  # To store text output

        # Add the first welcome message
        first_msg = get_next_chat_response()
        st.session_state.messages.append({"role": "assistant", "content": first_msg})

    # --- Column Layout ---
    col_chat, col_log = st.columns([2, 1.5])  # Chat is wider

    with col_chat:
        st.subheader("1. AI Chat & Results")

        # --- Chat History ---
        chat_container = st.container(height=500, border=True)
        with chat_container:
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    # --- MODIFIED: Handle text OR image messages ---
                    if "content" in message:
                        st.markdown(message["content"])
                    elif "image" in message:
                        st.image(message["image"], caption="Application Proof")
                    # --- END MODIFICATION ---

        # --- Search Control ---
        # (This section is unchanged)
        if st.session_state.search_ready and st.session_state.search_results is None:
            if st.button("🚀 Start Search for Top 5", type="primary"):
                st.session_state.messages.append({"role": "user", "content": "Start Search!"})
                with chat_container:
                    with st.chat_message("user"):
                        st.markdown("Start Search!")

                # --- THIS IS THE SEARCH CREW KICKOFF ---
                with st.spinner(
                    "🕵️‍♂️ SearchAgent is scanning... RankingAgent is calculating... "
                    "(This may take a minute)"
                ):
                    log_container = col_log.container(height=500, border=True)
                    streamlit_callback = StreamlitCallbackHandler(log_container)

                    crew_inputs = {"criteria": st.session_state.criteria}

                    try:
                        final_result = run_main_crew(
                            "housing_search", crew_inputs, streamlit_callback
                        )

                        # Store results
                        try:
                            json_str = getattr(final_result, "json", None)
                            if json_str:
                                parsed = json.loads(json_str)
                            else:
                                parsed = json.loads(str(final_result))

                            if isinstance(parsed, dict):
                                if "results" in parsed:
                                    results_list = parsed["results"]
                                elif "listings" in parsed:
                                    results_list = parsed["listings"]
                                else:
                                    results_list = []
                            elif isinstance(parsed, list):
                                results_list = parsed
                            else:
                                results_list = []

                            st.session_state.search_results = results_list
                            st.session_state.final_result_md = (
                                f"Found {len(results_list)} matching properties!"
                            )
                        except Exception as e:
                            print(f"Error parsing JSON: {e}")
                            st.session_state.search_results = []
                            st.session_state.final_result_md = (
                                "Search finished, but I couldn't parse the output. Raw data: "
                                f"{final_result}"
                            )

                    except Exception as e:
                        st.session_state.final_result_md = f"An error occurred: {e}"

                # Update chat
                st.session_state.messages.append(
                    {"role": "assistant", "content": st.session_state.final_result_md}
                )
                st.rerun()  # Rerun to display results

        # --- Display Results & Apply Buttons ---
        if st.session_state.search_results is not None:
            with chat_container:
                st.subheader("Top 5 Matches")
                df = pd.DataFrame(st.session_state.search_results)
                st.dataframe(df)

                st.markdown("---")
                st.markdown("Select a property to apply for:")

                for i, listing in enumerate(st.session_state.search_results):
                    if st.button(
                        f"Apply for Listing #{i+1} ({listing.get('title', 'N/A')})",
                        key=f"apply_{i}",
                    ):

                        # --- THIS IS THE APPLY CREW KICKOFF ---
                        with st.spinner(
                            f"🚀 ApplyAgent is logging in and applying for Listing #{i+1}..."
                        ):
                            log_container = col_log.container(height=500, border=True)
                            streamlit_callback = StreamlitCallbackHandler(log_container)

                            user_profile = {
                                # Reads from .env file
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

                            crew_inputs = {
                                "user_profile": json.dumps(user_profile),
                                "listing_details": json.dumps(listing),
                            }

                            try:
                                final_result = run_main_crew(
                                    "housing_apply", crew_inputs, streamlit_callback
                                )

                                # Normalize result to string for chat display and parsing
                                result_text = None
                                # Some Crew outputs may expose .raw/.json; prefer text-like content
                                if hasattr(final_result, "raw") and isinstance(
                                    final_result.raw, str
                                ):
                                    result_text = final_result.raw
                                else:
                                    try:
                                        result_text = str(final_result)
                                    except Exception:
                                        result_text = ""

                                # Always store the text message
                                st.session_state.messages.append(
                                    {"role": "assistant", "content": result_text}
                                )

                                # Try to find and add the image
                                image_path = None
                                if isinstance(result_text, str) and (
                                    "Screenshot saved as " in result_text
                                ):
                                    try:
                                        # Parse path like 'outputs/submission_proof_...png'
                                        path_part = (
                                            result_text.split("Screenshot saved as ")[-1]
                                            .strip()
                                            .rstrip(".")
                                        )

                                        if os.path.exists(path_part) and path_part.endswith(".png"):
                                            image_path = path_part
                                    except Exception as e:
                                        print(f"Error parsing image path: {e}")

                                # If image found, add it as a new message
                                if image_path:
                                    st.session_state.messages.append(
                                        {"role": "assistant", "image": image_path}
                                    )

                            except Exception as e:
                                st.session_state.final_result_md = f"An error occurred: {e}"
                                st.session_state.messages.append(
                                    {
                                        "role": "assistant",
                                        "content": st.session_state.final_result_md,
                                    }
                                )

                        st.rerun()

        # --- Chat Input Box ---
        # (This section is unchanged)
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
        st.subheader("2. AI Reasoning Log")
        if not any(st.session_state.get(key) for key in ["search_ready", "search_results"]):
            st.container(height=500, border=True).markdown(
                "*(Agent's thought process will appear here when a job is running...)*"
            )


if __name__ == "__main__":
    main()
