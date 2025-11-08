# FILE: ./src/tools/backend_api_tool.py
import json
import os
import time
from typing import Literal

import httpx
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# Base URL of the property backend API (env BACKEND_BASE_URL overrides).
BASE_URL = os.getenv("BACKEND_BASE_URL", "http://136.244.109.212:8000")


class ListingsInput(BaseModel):
    # All filters are optional; agent may omit them. Provide explicit defaults so validation passes.
    city: str | None = Field(default=None, description="Filter by city name")
    max_price: int | None = Field(default=None, description="Maximum price")
    min_price: int | None = Field(default=None, description="Minimum price")
    min_size: int | None = Field(default=None, description="Minimum size in m2")
    q: str | None = Field(default=None, description="Keyword search query (optional)")
    order_by: Literal["price_amount", "area_m2", "first_seen"] | None = Field(
        default="first_seen", description="Sort field"
    )
    order_dir: Literal["asc", "desc"] | None = Field(default="desc", description="Sort direction")
    limit: int = Field(default=20, description="Number of results to return")


class BackendApiTool(BaseTool):
    name: str = "backend_api_tool"
    description: str = "Queries the backend API to get a list of rental listings based on criteria."
    args_schema: type[BaseModel] = ListingsInput

    def _run(
        self,
        city: str | None = None,
        max_price: int | None = None,
        min_price: int | None = None,
        min_size: int | None = None,
        q: str | None = None,
        order_by: str = "first_seen",
        order_dir: str = "desc",
        limit: int = 20,
    ) -> str:

        # Build query parameter dict
        params = {
            "city": city,
            "max_price": max_price,
            "min_price": min_price,
            "area_m2_min": min_size,  # Assumes backend expects 'area_m2_min' for minimum size
            "q": q,
            "order_by": order_by,
            "order_dir": order_dir,
            "limit": limit,
        }

        # Remove parameters with None values
        query_params = {k: v for k, v in params.items() if v is not None}

        attempts = 3
        last_error: str | None = None
        for i in range(attempts):
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(f"{BASE_URL}/listings", params=query_params)
                    response.raise_for_status()  # Raise on 4xx/5xx
                    # Normalize output: return ONLY the list of items if present
                    try:
                        data = response.json()
                        if isinstance(data, dict) and "items" in data:
                            return json.dumps(data.get("items", []))
                        # Already a list or unknown shape
                        return response.text
                    except Exception:
                        # Fallback to raw text
                        return response.text
            except (httpx.ReadTimeout, httpx.ConnectTimeout):
                last_error = "timeout"
            except httpx.HTTPStatusError as e:
                return (
                    f"API request failed with status {e.response.status_code}: "
                    f"{e.response.text}"
                )
            except httpx.RequestError as e:
                last_error = f"request error: {str(e)}"

            # Simple linear backoff: 1s, 2s between attempts
            if i < attempts - 1:
                time.sleep(1.0 * (i + 1))

        return (
            "An error occurred while calling the backend API: " f"{last_error or 'unknown error'}"
        )


# Export tool instance
backend_api_tool = BackendApiTool()
