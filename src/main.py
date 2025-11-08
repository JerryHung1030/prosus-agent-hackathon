# FILE: ./src/main.py
"""Main entrypoint helpers for running crews.

Ensures environment variables from .env are loaded before any CrewAI/LLM
initialization by importing src.config.
"""

# Load environment (.env) and propagate keys (e.g., OPENAI_API_KEY) early
from . import config as _config  # noqa: F401
from .crew_factory import get_crew


def run_main_crew(crew_type: str, inputs: dict, streamlit_callback=None):
    """
    Assembles and runs the AI crew using the factory.
    'inputs' is now a dictionary passed to the factory.
    """

    # Get the configured crew and tasks from the factory
    # The factory now embeds the inputs into the tasks
    crew, kickoff_inputs = get_crew(crew_type, inputs, streamlit_callback)

    print(f"Starting Crew: {crew_type}...")
    # kickoff_inputs is now an empty dict, as data is in the tasks
    result = crew.kickoff(inputs=kickoff_inputs)
    print("AI Crew finished.")

    return result
