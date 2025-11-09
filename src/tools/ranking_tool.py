# FILE: ./src/tools/ranking_tool.py

import re
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class RankingInput(BaseModel):
    criteria: dict[str, Any] = Field(
        description="User's search criteria (price, size, commute_target)."
    )
    listings: list[dict[str, Any]] = Field(
        description="List of listings from RAG search."
    )
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

        # --- 1. Price Score (New Logic) ---
        # 100 = 遠低於預算, 0 = 預算的 1.5 倍
        price_score = 0.0
        try:
            list_price = float(listing.get("price") or listing.get("price_amount") or 0)
            # Standardize on 'max_price' in criteria
            user_price = float(criteria.get("max_price", 0))
            if user_price > 0:
                # 價格越低越好。如果價格是 0，得 100 分。
                # 如果價格等於 user_price * 1.5，得 0 分。
                ratio = list_price / (user_price * 1.5)
                price_score = max(0, 100 * (1 - ratio))
            else:
                price_score = 100.0  # 如果沒有預算限制，則價格不重要
        except Exception:
            price_score = 30.0  # 懲罰壞數據

        # --- 2. Size Score (New Logic) ---
        # 100 = 遠大於需求, 0 = 0 m²
        size_score = 0.0
        try:
            list_size = float(listing.get("size_m2") or listing.get("area_m2") or 0)
            # Standardize on 'min_size' in criteria
            user_size = float(criteria.get("min_size", 0))
            if user_size > 0:
                # 面積越大越好。如果面積是 user_size * 1.5 (或更大)，得 100 分。
                # 如果面積是 0，得 0 分。
                ratio = list_size / (user_size * 1.5)
                size_score = min(100, 100 * ratio)
            else:
                size_score = 100.0  # 如果沒有面積需求，則不重要
        except Exception:
            size_score = 30.0  # 懲罰壞數據

        # --- 3. Commute Score (New Logic) ---
        # 100 = 0 分鐘, 0 = 60 分鐘 (或更久)
        commute_score = 0.0
        try:
            match = re.search(r"(\d+)", commute_str or "")
            time_val = int(match.group(1)) if match else 999

            # 線性計分：每多 1 分鐘，分數就越低。
            # 超過 60 分鐘都是 0 分。
            ratio = time_val / 60.0
            commute_score = max(0, 100 * (1 - ratio))
        except Exception:
            commute_score = 0.0  # 懲罰壞數據

        # --- Final weighted score ---
        final_score = (
            (price_score * weights["price"])
            + (size_score * weights["size"])
            + (commute_score * weights["commute"])
        )

        return round(final_score, 2)

    def _run(
        self,
        criteria: dict[str, Any],
        listings: list[dict[str, Any]],
        commute_times: list[str],
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
        sorted_listings = sorted(
            scored_listings, key=lambda x: x["match_score"], reverse=True
        )
        # Return Top 5 to match task description (if fewer than 5, return all)
        return sorted_listings[:5]


# Export an instance
listing_ranker_tool = ListingRankerTool()
