# FILE: ./src/main.py
from .crew_factory import get_crew


def run_main_crew(user_goal, crew_type, streamlit_callback=None):
    """
    Assembles and runs the AI crew using the factory.
    """

    # Get the configured crew and inputs from the factory
    crew, inputs = get_crew(crew_type, user_goal, streamlit_callback)

    print(f"Starting Crew: {crew_type}...")
    result = crew.kickoff(inputs=inputs)
    print("AI Crew finished.")

    return result
