# FILE: ./app.py
# (Perfected Factory Version)

import streamlit as st

from src.main import run_main_crew
from src.utils.streamlit_callback import StreamlitCallbackHandler


def main():
    # --- 1. Page Configuration ---
    st.set_page_config(
        page_title="Prosus AI Agent", layout="wide", initial_sidebar_state="expanded"
    )

    st.title("🤖 Prosus Agentic AI Framework")

    # --- 2. Sidebar (Inputs & Controls) ---
    with st.sidebar:
        st.header("1. Select Crew")
        crew_type = st.selectbox(
            "Which AI team do you want to run?", ("research",)  # Add "finance" here when ready
        )

        st.header("2. Define Goal")
        user_goal = st.text_area(
            "What is the objective for the AI crew?",
            (
                "Analyze the OLX market for second-hand electronics in the Netherlands "
                "and write a short report."
            ),
            height=150,
        )

        st.header("3. Controls")
        col_run, col_clear = st.columns(2)
        with col_run:
            run_button = st.button("Run AI Crew", type="primary", use_container_width=True)
        with col_clear:
            clear_button = st.button("Clear Output", use_container_width=True)

    # --- 3. Main Content (Outputs) ---
    st.header("Outputs")
    col_result, col_log = st.columns(2)

    with col_result:
        st.subheader("Final Result")
        # Define the result container *before* the logic block
        result_container = st.empty()

    with col_log:
        st.subheader("Agent Reasoning Log")
        # Define the log container *before* the logic block
        log_container = st.container(height=500, border=True)

    # --- 4. Logic (Controller) ---

    # Set default placeholders
    if not run_button or clear_button:
        result_container.markdown("*(Final report will appear here...)*")
        log_container.markdown("*(Agent's thought process will appear here...)*")

    if clear_button:
        # Streamlit reruns, and the containers are naturally empty
        # We just add a small toast message for user feedback
        st.toast("Outputs cleared!")

    # Main execution logic
    if run_button and not clear_button:
        # Clear containers for the new run
        log_container.empty()
        result_container.info("⏳ Crew is running... Please wait.", icon="⏳")

        # Instantiate our custom callback handler
        streamlit_callback = StreamlitCallbackHandler(log_container)

        try:
            # Pass the crew_type to the runner
            final_result = run_main_crew(user_goal, crew_type, streamlit_callback)

            # Display final result
            result_container.empty()  # Clear the "Processing..." message
            result_container.markdown(final_result)

        except Exception as e:
            result_container.empty()  # Clear the "Processing..." message
            st.error(f"An error occurred: {e}")
            # The log_container (passed to callback) will already have logs up to the error


if __name__ == "__main__":
    main()
