# FILE: ./src/tools/batch_commute_tool.py
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# Import both the existing google_maps_tool and the new matrix tool
from .google_maps_tool import google_maps_tool, google_maps_matrix_tool


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
        """
        Compute commute times for all listings.
        
        Strategy:
        1. Try batch Distance Matrix API first (fast, efficient)
        2. Fall back to parallel individual directions calls if batch fails
        """
        if not listings:
            return []
        
        # Build origin addresses
        origins = []
        valid_indices = []  # Track which listings have valid addresses
        
        for i, listing in enumerate(listings):
            origin = (
                f"{listing.get('street', '')}, "
                f"{listing.get('city', '')} "
                f"{listing.get('postal_code', '')}, Netherlands"
            )
            if "None" not in origin and origin.strip() != ", , Netherlands":
                origins.append(origin)
                valid_indices.append(i)
        
        # Initialize all with fallback value
        commute_times: list[str] = ["999 mins (Invalid Address)"] * len(listings)
        
        # Try batch Matrix API first if we have valid origins
        if origins and len(origins) > 1:
            print(f"[Batch] Attempting Distance Matrix API for {len(origins)} listings")
            try:
                matrix_results = google_maps_matrix_tool._run(
                    origins=origins, 
                    destination=destination, 
                    mode="transit"
                )
                
                # Map results back to original listing positions
                if len(matrix_results) == len(origins):
                    for result_idx, listing_idx in enumerate(valid_indices):
                        commute_times[listing_idx] = matrix_results[result_idx]
                    
                    print(f"[Batch] Successfully used Distance Matrix API")
                    return commute_times
                else:
                    print(f"[Batch] Matrix API returned unexpected length, falling back")
            except Exception as e:
                print(f"[Batch] Matrix API failed ({e}), falling back to individual calls")
        
        # Fallback: Use parallel individual directions calls (original behavior)
        print(f"[Fallback] Using parallel individual direction calls for {len(listings)} listings")
        
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

        return commute_times


# Export tool instance
batch_commute_tool = BatchCommuteTool()
