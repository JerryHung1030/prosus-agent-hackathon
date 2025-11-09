# FILE: ./src/tools/batch_commute_tool.py
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# Import the existing google_maps_tool so we can reuse its _run method
from .google_maps_tool import google_maps_tool


class BatchCommuteInput(BaseModel):
    listings: list[dict[str, Any]] = Field(
        description="Full listings list returned from backend_api_tool."
    )
    destination: str = Field(
        description="User's primary commute destination (e.g., office address)."
    )


class BatchCommuteTool(BaseTool):
    name: str = "batch_commute_tool"
    description: str = (
        "Compute commute times for all listings in parallel. "
        "Input is the complete listings list and the destination."
    )
    args_schema: type[BaseModel] = BatchCommuteInput

    def _get_commute_for_listing(self, listing: dict[str, Any], destination: str) -> str:
        """Helper: call google_maps_tool for a single listing."""
        try:
            origin = (
                f"{listing.get('street', '')}, "
                f"{listing.get('city', '')} "
                f"{listing.get('postal_code', '')}, Netherlands"
            )
            if "None" in origin or origin.strip() == ", , Netherlands":
                return "999 mins (Invalid Address)"

            # Reuse existing tool's logic
            return google_maps_tool._run(origin=origin, destination=destination, mode="transit")
        except Exception as e:
            return f"999 mins (Error: {e})"

    def _run(self, listings: list[dict[str, Any]], destination: str) -> list[str]:
        commute_times: list[str] = [""] * len(listings)

        # Use ThreadPoolExecutor to parallelize network requests
        # max_workers=20 allows up to 20 concurrent requests
        with ThreadPoolExecutor(max_workers=20) as executor:
            # Map each future to its index
            future_to_index = {
                executor.submit(self._get_commute_for_listing, listing, destination): i
                for i, listing in enumerate(listings)
            }

            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    result = future.result()
                    commute_times[index] = result
                except Exception as e:
                    commute_times[index] = f"999 mins (Error: {e})"

        # Ensure length matches input
        if len(commute_times) != len(listings):
            return ["999 mins (Processing Error)"] * len(listings)

        return commute_times


# Export tool instance
batch_commute_tool = BatchCommuteTool()
