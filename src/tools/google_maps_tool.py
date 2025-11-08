# FILE: src/tools/google_maps_tool.py
import os
from datetime import datetime, timedelta

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# Attempt to import googlemaps; if unavailable or no API key, operate in fallback mode.
try:  # pragma: no cover
    import googlemaps  # type: ignore

    _GMAPS_IMPORTED = True
except Exception:  # pragma: no cover
    googlemaps = None  # type: ignore
    _GMAPS_IMPORTED = False

API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
if _GMAPS_IMPORTED and API_KEY:
    gmaps = googlemaps.Client(key=API_KEY)  # type: ignore[arg-type]
else:
    gmaps = None  # Fallback: tool returns placeholder commute times


class CommuteInput(BaseModel):
    origin: str = Field(description="The starting address (e.g., the listing address).")
    destination: str = Field(
        description="The destination address (e.g., the user's commute target)."
    )
    mode: str = Field(
        default="transit", description="Mode of transport (transit, driving, walking, bicycling)."
    )


class GoogleMapsTool(BaseTool):
    name: str = "google_maps_tool"
    description: str = (
        "Calculates commute time and a route summary via Google Maps. "
        "Falls back to a large placeholder value when API/key not available "
        "so ranking can still proceed."
    )
    args_schema: type[BaseModel] = CommuteInput

    def _summarize_steps(self, steps, mode: str) -> str:
        """Create a compact 'via ...' summary from steps."""
        parts = []
        for s in steps or []:
            tm = s.get("travel_mode")
            if tm == "TRANSIT":
                td = s.get("transit_details", {}) or {}
                line = td.get("line", {}) or {}
                label = (
                    line.get("short_name")
                    or line.get("name")
                    or (line.get("vehicle") or {}).get("name")
                    or "transit"
                )
                parts.append(str(label))
            elif tm == "WALKING":
                parts.append("walking")
            elif tm == "BICYCLING":
                parts.append("bicycling")
            elif tm == "DRIVING":
                parts.append("driving")

        # remove consecutive duplicates
        compact = []
        for p in parts:
            if not compact or compact[-1] != p:
                compact.append(p)

        return " + ".join(compact) if compact else mode

    def _run(self, origin: str, destination: str, mode: str = "transit") -> str:
        # Fallback early if client not initialized
        if gmaps is None:
            return "999 mins"  # large number so downstream ranking penalizes commute
        try:
            # Next Monday 08:30 (always the NEXT one)
            now = datetime.now()
            days_ahead = (7 - now.weekday()) % 7 or 7
            next_monday_8_30 = (now + timedelta(days=days_ahead)).replace(
                hour=8, minute=30, second=0, microsecond=0
            )

            routes = gmaps.directions(
                origin,
                destination,
                mode=mode,
                departure_time=next_monday_8_30,
            )
            if not routes:
                return "No route found."

            leg = routes[0]["legs"][0]
            duration_text = leg.get("duration", {}).get("text", "?")
            distance_text = leg.get("distance", {}).get("text", "?")

            # For driving, show traffic time if available
            traffic_text = None
            if mode == "driving":
                traffic_text = leg.get("duration_in_traffic", {}).get("text")

            steps = leg.get("steps", [])
            via_summary = self._summarize_steps(steps, mode)

            if mode == "driving" and traffic_text:
                # e.g., [DRIVING] 14 mins (in traffic: 18 mins), 6.1 km via driving
                return (
                    f"[{mode.upper()}] {duration_text} (in traffic: {traffic_text}), "
                    f"{distance_text} via {via_summary}"
                )
            else:
                # e.g., [TRANSIT] 13 mins, 6.2 km via Metro 52 + walking
                return f"[{mode.upper()}] {duration_text}, {distance_text} via {via_summary}"

        except Exception as e:
            return f"Error with Google Maps API: {str(e)}"


google_maps_tool = GoogleMapsTool()
