# FILE: src/crew_factory.py
from typing import Any

from crewai import Crew, Process

from .agents.research_agents import create_research_agent, create_writer_agent
from .tasks import create_research_task, create_writing_task
from .utils.streamlit_callback import create_step_callback


def get_crew(crew_type: str, user_goal: str, streamlit_callback=None):
    """
    Factory function to create and configure a Crew based on type.
    """

    # Build per-agent step callbacks when we have a Streamlit handler
    researcher_step_cb = None
    writer_step_cb = None
    if streamlit_callback is not None:
        researcher_step_cb = create_step_callback(streamlit_callback, "researcher_agent")
        writer_step_cb = create_step_callback(streamlit_callback, "writer_agent")

    agents = []
    tasks = []

    if crew_type == "research":
        # Create agents with their own step callbacks so progress logs render in Streamlit
        researcher = create_research_agent(step_callback=researcher_step_cb)
        writer = create_writer_agent(step_callback=writer_step_cb)

        agents = [researcher, writer]
        tasks = [create_research_task(researcher), create_writing_task(writer)]

    # (Future) other crew types could go here

    else:
        raise ValueError(f"Unknown crew_type: {crew_type}")

    # Assemble the crew (agent-level callbacks already wired via step_callback)
    agents_any: list[Any] = agents

    crew = Crew(
        agents=agents_any,
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )

    inputs = {"user_goal": user_goal}

    return crew, inputs
