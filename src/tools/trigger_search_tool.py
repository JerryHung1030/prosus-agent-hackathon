# FILE: ./src/tools/trigger_search_tool.py
"""Tool to trigger the housing search workflow.
Use this after the conversation agent has collected ALL required info.
Required fields: city, max_price, min_size, commute_target.
"""
import json

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class TriggerSearchInput(BaseModel):
    """Input parameters for triggering the search."""

    city: str = Field(..., description="City name")
    max_price: int = Field(..., description="Maximum monthly price in euros")
    min_size: int = Field(..., description="Minimum size in square meters")
    commute_target: str = Field(..., description="Commute destination address or landmark")


class TriggerSearchTool(BaseTool):
    name: str = "trigger_housing_search"
    description: str = (
        "Trigger the housing search workflow. Once ALL user requirements "
        "(city, budget, size, commute target) are collected, use this tool to "
        "start searching for listings. It launches the Search Agent and Ranking "
        "Agent to find and evaluate the best options."
    )
    args_schema: type[BaseModel] = TriggerSearchInput

    def _run(
        self,
        city: str,
        max_price: int,
        min_size: int,
        commute_target: str,
    ) -> str:
        """Trigger the search workflow.

        Args:
            city: City name
            max_price: Maximum monthly price (euros)
            min_size: Minimum required size in square meters
            commute_target: Commute destination (address or landmark)

        Returns:
            A JSON string indicating the search trigger and echoing the criteria.
        """
        # Build search criteria payload
        criteria = {
            "city": city,
            "max_price": max_price,
            "min_size": min_size,
            "commute_target": commute_target,
        }

        # Return structured signal for upstream orchestration layer
        return json.dumps(
            {
                "action": "TRIGGER_SEARCH",
                "criteria": criteria,
                "message": (
                    f"All information collected. Initiating search in {city} "
                    f"(budget €{max_price}, minimum {min_size}m², commute to {commute_target})."
                ),
            }
        )


# Export tool instance
trigger_search_tool = TriggerSearchTool()
