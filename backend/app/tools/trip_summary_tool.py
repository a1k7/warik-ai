from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.tools.base import BaseTool, ToolContext, ToolResult


class CompileTripSummaryInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    destination: str = ""
    dependency_results: dict = Field(default_factory=dict)
    dependency_failures: dict = Field(default_factory=dict)


class CompileTripSummaryTool(BaseTool):
    name = "compile_trip_summary"
    description = "Compile a trip summary from whatever discovery steps succeeded."
    capability = "travel"
    input_schema = CompileTripSummaryInput
    requires_confirmation = False
    is_mutating = False

    @staticmethod
    def _get_hotel_key(hotel: dict) -> tuple:
        """Create a stable key to prevent duplicate hotel entries."""
        booking_url = hotel.get("booking_url")

        if booking_url:
            return ("url", booking_url.strip().lower())

        return (
            hotel.get("name", "").strip().lower(),
            hotel.get("city", "").strip().lower(),
            hotel.get("check_in"),
            hotel.get("check_out"),
        )

    @classmethod
    def _merge_hotels(cls, *hotel_lists: Any) -> list[dict]:
        """Merge hotel sources while avoiding duplicate entries."""
        merged = []
        seen = set()

        for hotel_list in hotel_lists:
            if not isinstance(hotel_list, list):
                continue

            for hotel in hotel_list:
                if not isinstance(hotel, dict):
                    continue

                key = cls._get_hotel_key(hotel)

                if key in seen:
                    continue

                seen.add(key)
                merged.append(hotel)

        return merged

    def execute(
        self,
        ctx: ToolContext,
        params: CompileTripSummaryInput,
    ) -> ToolResult:

        results = params.dependency_results or {}
        failures = params.dependency_failures or {}

        flights = []
        standalone_hotels = []
        itinerary_hotels = []
        cabs = {}
        itinerary = None

        for dep_id, dep in results.items():
            if not isinstance(dep, dict):
                continue

            tool = str(dep.get("tool", "")).lower()
            data = dep.get("result") or {}

            if not isinstance(data, dict):
                continue

            # Flight discovery
            if "flight" in tool:
                items = data.get("items", [])
                if isinstance(items, list):
                    flights.extend(
                        item for item in items
                        if isinstance(item, dict)
                    )

            # Standalone hotel discovery (backward compatibility)
            elif "hotel" in tool:
                items = data.get("items", [])
                if isinstance(items, list):
                    standalone_hotels.extend(
                        item for item in items
                        if isinstance(item, dict)
                    )

            # Cab / transport discovery
            elif "cab" in tool or "transport" in tool:
                links = data.get("links", {})
                if isinstance(links, dict):
                    cabs.update(links)

            # Advanced itinerary discovery
            elif "itinerary" in tool:
                itinerary = data

                embedded_hotels = data.get("hotels", [])

                if isinstance(embedded_hotels, list):
                    itinerary_hotels.extend(
                        hotel for hotel in embedded_hotels
                        if isinstance(hotel, dict)
                    )

        # Merge both hotel sources without duplicates.
        hotels = self._merge_hotels(
            itinerary_hotels,
            standalone_hotels,
        )

        # Preserve dependency failures.
        summary_failures = [
            {
                "tool": failure.get("tool", ""),
                "error": failure.get("error", ""),
            }
            for failure in failures.values()
            if isinstance(failure, dict)
        ]

        # Surface hotel-search issues recorded by the itinerary tool.
        if isinstance(itinerary, dict):
            notes = itinerary.get("notes", [])

            if isinstance(notes, list):
                for note in notes:
                    if (
                        isinstance(note, str)
                        and note.startswith("Hotel search issue:")
                    ):
                        summary_failures.append({
                            "tool": "hotel_search",
                            "error": note.removeprefix(
                                "Hotel search issue:"
                            ).strip(),
                        })

        summary_data = {
            "type": "trip_summary",
            "destination": params.destination or "Your Trip",
            "flights": flights,
            "hotels": hotels,
            "cabs": cabs,
            "itinerary": itinerary,
            "failures": summary_failures,
        }

        return ToolResult(
            success=True,
            message="I've compiled your trip plan.",
            data=summary_data,
        )