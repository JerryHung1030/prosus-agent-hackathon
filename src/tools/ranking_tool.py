# FILE: ./src/tools/ranking_tool.py

import re
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class RankingInput(BaseModel):
    criteria: dict[str, Any] = Field(
        description="User's search criteria (price, size, commute_target)."
    )
    listings: list[dict[str, Any]] = Field(description="List of listings from RAG search.")
    commute_times: list[str] = Field(
        description="List of commute times (as strings, e.g., '25 mins') from the Web Search tool."
    )


class ListingRankerTool(BaseTool):
    name: str = "listing_ranker_tool"
    description: str = (
        "Calculates a match score for listings based on price, size, and commute time."
    )
    args_schema: type[BaseModel] = RankingInput

    def _calculate_score(
        self, listing: dict[str, Any], criteria: dict[str, Any], commute_str: str
    ) -> float:
        weights = {"price": 0.4, "size": 0.3, "commute": 0.3}

        # 1. Price Score
        price_score = 100.0
        try:
            # Accept multiple price keys from different sources
            list_price = float(
                listing.get("price") or listing.get("price_amount") or listing.get("rent") or 0
            )
            user_price = float(criteria.get("price", 0))
            if list_price > user_price > 0:
                price_score = (user_price / list_price) * 100
        except Exception:
            price_score = 50.0  # Penalize bad data

        # 2. Size Score
        size_score = 100.0
        try:
            # Accept multiple size keys
            list_size = float(listing.get("size_m2") or listing.get("area_m2") or 0)
            user_size = float(criteria.get("size", 0))
            if list_size < user_size and user_size > 0:
                size_score = (list_size / user_size) * 100
        except Exception:
            size_score = 50.0  # Penalize bad data

        # 3. Commute Score
        commute_score = 0.0
        try:
            # Extract first integer anywhere in the string (e.g., "[TRANSIT] 25 mins")
            match = re.search(r"(\d+)", commute_str or "")
            time_val = int(match.group(1)) if match else 999
            if time_val <= 20:
                commute_score = 100.0
            elif time_val <= 30:
                commute_score = 90.0
            elif time_val <= 45:
                commute_score = 75.0
            else:
                commute_score = 50.0
        except Exception:
            commute_score = 50.0  # Penalize if search failed

        # Final weighted score
        final_score = (
            (price_score * weights["price"])
            + (size_score * weights["size"])
            + (commute_score * weights["commute"])
        )

        return round(final_score, 2)

    def _run(
        self, criteria: dict[str, Any], listings: list[dict[str, Any]], commute_times: list[str]
    ) -> list[dict[str, Any]]:

        if len(listings) != len(commute_times):
            return [
                {
                    "error": (
                        "Mismatch between listings ("
                        f"{len(listings)}) and commute_times ({len(commute_times)})"
                    )
                }
            ]

        scored_listings = []
        for i, listing in enumerate(listings):
            commute_str = commute_times[i]
            score = self._calculate_score(listing, criteria, commute_str)

            listing_copy = listing.copy()
            listing_copy["match_score"] = score
            listing_copy["commute_time"] = commute_str
            scored_listings.append(listing_copy)

        # Sort by score descending
        sorted_listings = sorted(scored_listings, key=lambda x: x["match_score"], reverse=True)

        return sorted_listings[:5]  # Return Top 5


# Export an instance
listing_ranker_tool = ListingRankerTool()
