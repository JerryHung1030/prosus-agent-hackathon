# FILE: ./src/tools/motivation_builder_tool.py

"""Tool to build a motivation letter for Pararius listings."""

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class MotivationInput(BaseModel):
    user: dict = Field(description="User profile info (name, email, phone, etc.)")
    preferences: dict = Field(description="Housing preferences and constraints")
    work_or_study: dict = Field(description="Employment or student status details")
    listing: dict = Field(description="Listing context like title, location, highlights")
    style: dict = Field(description="Tone/length/language preferences", default_factory=dict)


class MotivationBuilderTool(BaseTool):
    name: str = "motivation_builder"
    description: str = (
        "Builds a concise, polite motivation letter for a specific listing based on user profile, "
        "preferences, and listing context. Returns a single string ready to paste."
    )
    args_schema: type[BaseModel] = MotivationInput

    def _run(
        self,
        user: dict,
        preferences: dict,
        work_or_study: dict,
        listing: dict,
        style: dict | None = None,
    ) -> str:
        # Reserved for future i18n/format tuning
        _tone = (style or {}).get("tone", "polite and concise")
        _lang = (style or {}).get("language", "English")
        _len = (style or {}).get("length", "120-180 words")

        full_name = user.get("full_name", "Applicant")
        email = user.get("email", "")
        phone = user.get("phone", "")

        status = work_or_study.get("status", "professional")
        org = work_or_study.get("organization", "")
        guar = work_or_study.get("guarantor_available", False)
        refs = preferences.get("references_available", False)

        earliest = preferences.get("earliest_move_in", "soon")
        lease = preferences.get("lease_duration", "long-term")
        budget = preferences.get("max_budget")
        smoking = preferences.get("smoking", False)
        pets = preferences.get("pets", False)
        schedule = preferences.get("schedule_availability", "flexible")

        location = listing.get("location", "")
        highlights = listing.get("highlights", [])
        highlights_text = ", ".join(highlights) if highlights else "its features"

        extras = []
        if not smoking:
            extras.append("I do not smoke")
        if not pets:
            extras.append("I have no pets")
        extras_text = "; ".join(extras) if extras else ""

        budget_text = f"My budget is around €{budget}." if budget else ""
        support_text_parts = []
        if refs:
            support_text_parts.append("references")
        if guar:
            support_text_parts.append("a guarantor")
        support_text = (
            "I can provide " + " and ".join(support_text_parts) + " if needed."
            if support_text_parts
            else ""
        )

        lines = [
            "Dear landlord,",
            (
                f"My name is {full_name}, a {status}"
                f"{(' at ' + org) if org else ''}. "
                f"I’m looking to move around {earliest} for a {lease} lease."
            ),
            f"Your listing in {location} stood out to me, especially {highlights_text}.",
            (
                f"I’m quiet and responsible. {extras_text}"
                if extras_text
                else "I’m quiet and responsible."
            ),
            budget_text,
            support_text,
            f"I’m available for viewings {schedule}.",
            "",
            "Thank you for your time. I’d be happy to discuss further.",
            "Best regards,",
            f"{full_name}",
            (f"{email} | {phone}" if phone else f"{email}") if email else (phone or ""),
        ]

        # Filter empty lines and join
        message = "\n".join([ln for ln in lines if ln and ln.strip() != ""])
        return message


motivation_builder_tool = MotivationBuilderTool()
