# FILE: ./src/tasks/research_tasks.py
from crewai import Task


def create_research_task(agent):
    return Task(
        description=(
            "Conduct a thorough analysis based on this user goal: '{user_goal}'. "
            "Use your tools to find market data, trends, and "
            "any relevant internal knowledge (from the RAG tool)."
        ),
        expected_output=(
            "A comprehensive report with all findings, including data points, trends, "
            "and key insights."
        ),
        agent=agent,
    )


def create_writing_task(agent):
    return Task(
        description=(
            "Based on the research findings, write a final, well-structured report for the "
            "user. The report must directly address their original goal: '{user_goal}'."
        ),
        expected_output=(
            "A final, polished report in markdown format that answers the user's goal."
        ),
        agent=agent,
    )
