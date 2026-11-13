from __future__ import annotations

import json
import logging
from datetime import datetime

from app.agents.llm_provider import get_provider
from app.schemas.workflow import WorkflowPlan, WorkflowStep
from app.tools.registry import registry

logger = logging.getLogger(__name__)

class TravelClarificationRequired(ValueError):
    """Raised when a travel workflow needs additional user information."""


GOAL_INTERPRETER_PROMPT = """You are the goal interpreter for Warik AI.

Convert the user's goal into a structured workflow.

CURRENT DATE: {current_date}

AVAILABLE TOOLS:
{tools_desc}

Return exactly this JSON structure:
{{
  "goal_title": "Short title",
  "goal_description": "Description",
  "context": {{"destination": "Destination"}},
  "steps": [
    {{
      "id": "step_id",
      "description": "Description",
      "tool": "exact_tool_name",
      "params": {{}},
      "depends_on": [],
      "approval_required": false,
      "required": true,
      "dep_policy": "all_success",
      "max_retries": 0
    }}
  ]
}}

TRAVEL RULES:

1. For a trip or itinerary, use generate_advanced_itinerary.
1a. Extract the destination as a place name only. Do not append traveller counts,
    dates, budgets, origin details, or the words "for X people".
1b. Preserve administrative context when supplied: "Jaipur, Rajasthan, India"
    is one destination, not three destinations.
1c. For multiple stops, separate only clearly requested stops using "and",
    "to", or an explicit route arrow. Do not split a place on commas.
1d. If the destination is ambiguous, ask for clarification rather than guessing.
2. Preserve all requested cities in their original order.
3. Never use search_places_geoapify when using generate_advanced_itinerary.
4. Itinerary parameters:
   - destination
   - days
   - optional origin, budget, travellers
   - include_hotels
   - check_in
   - check_out
5. If the user requests hotels, set include_hotels=true on generate_advanced_itinerary.
6. When hotels are requested, pass check_in and check_out to generate_advanced_itinerary.
7. Do not create a separate search_hotels_stayapi step. The advanced itinerary handles hotel searches for each city.
8. For flights, use search_flights_real with:
   - origin
   - destination
   - date (one YYYY-MM-DD date per step)
9. For cab links, use get_cab_links with:
   - pickup_location
   - dropoff_location
10. Supplementary flight and cab steps must be optional.
11. Supplementary discovery steps must not depend on one another.
12. The itinerary is required.
13. Always include compile_trip_summary.
14. The summary must depend on every discovery step, including the itinerary.
15. The summary is required and must use dep_policy tolerate_failure.
16. Do not invent dates, locations, prices or user preferences.
17. For trip budget calculations, use calculate_trip_budget only when the
    user requests a budget calculation and required values are known.
18. Never invent separate transportation, food or accommodation budget tools.
19. Return only valid JSON. No markdown or commentary.
"""


class GoalInterpreter:
    def __init__(self):
        self.provider = get_provider()

    @staticmethod

    def _normalize_travel_steps(steps_raw: list, context: dict) -> list:
        """Normalize travel parameters and create a non-duplicated workflow."""

        steps = []
        discovery_ids = []

        # Detect whether hotels were requested and collect their dates.
        hotel_steps = [
            step for step in steps_raw
            if step.get("tool") == "search_hotels_stayapi"
        ]

        hotel_requested = bool(hotel_steps)

        hotel_params = {}
        if hotel_steps:
            hotel_params = dict(hotel_steps[0].get("params") or {})

        def first_value(*values):
            return next(
                (
                    value for value in values
                    if value is not None and value != ""
                ),
                None,
            )

        def is_real_value(value) -> bool:
            if not isinstance(value, str):
                return False

            normalized = value.strip().lower()
            invalid_values = {
                "",
                "user's origin",
                "users origin",
                "user's preferred date",
                "user's preferred check-in date",
                "user's preferred check-out date",
                "preferred date",
                "unknown",
                "null",
                "none",
                "n/a",
                "not provided",
            }
            return (
                normalized not in invalid_values
                and not normalized.startswith("user's preferred")
                and not normalized.startswith("users preferred")
                and not normalized.startswith("<")
            )

        def is_valid_date(value) -> bool:
            if not is_real_value(value):
                return False

            try:
                parsed = datetime.strptime(value.strip(), "%Y-%m-%d")
                return parsed.strftime("%Y-%m-%d") == value.strip()
            except (TypeError, ValueError):
                return False

        hotel_check_in = first_value(
            context.get("check_in"),
            context.get("checkin"),
            hotel_params.get("check_in"),
            hotel_params.get("checkin"),
        )

        hotel_check_out = first_value(
            context.get("check_out"),
            context.get("checkout"),
            hotel_params.get("check_out"),
            hotel_params.get("checkout"),
        )

        hotel_travellers = first_value(
            context.get("travellers"),
            hotel_params.get("travellers"),
        )

        for raw_step in steps_raw:
            step = dict(raw_step)
            tool = step.get("tool", "")
            params = dict(step.get("params") or {})

            # The advanced itinerary owns all hotel searches.
            # Remove standalone hotel steps to prevent duplicate calls.
            if tool == "search_hotels_stayapi":
                continue

            if tool == "generate_advanced_itinerary":
                params["destination"] = first_value(
                    params.get("destination"),
                    context.get("destination"),
                    "",
                )
                if isinstance(params["destination"], str):
                    params["destination"] = " ".join(params["destination"].split())

                # Enable integrated hotel discovery only when both dates
                # are real ISO dates and checkout is after check-in.
                hotel_was_requested = (
                    hotel_requested or bool(params.get("include_hotels"))
                )

                requested_check_in = first_value(
                    params.get("check_in"),
                    params.get("checkin"),
                    hotel_check_in,
                )
                requested_check_out = first_value(
                    params.get("check_out"),
                    params.get("checkout"),
                    hotel_check_out,
                )

                hotel_dates_valid = (
                    is_valid_date(requested_check_in)
                    and is_valid_date(requested_check_out)
                )

                if hotel_was_requested and not hotel_dates_valid:
                    raise TravelClarificationRequired(
                        "What are your hotel check-in and check-out dates? "
                        "Please provide both dates in YYYY-MM-DD format."
                    )

                if hotel_dates_valid:
                    check_in_date = datetime.strptime(
                        requested_check_in.strip(), "%Y-%m-%d"
                    ).date()
                    check_out_date = datetime.strptime(
                        requested_check_out.strip(), "%Y-%m-%d"
                    ).date()

                    if check_out_date <= check_in_date:
                        raise TravelClarificationRequired(
                            "Your hotel check-out date must be after your "
                            "check-in date. Please provide the correct dates."
                        )

                params["include_hotels"] = hotel_was_requested

                if hotel_was_requested:
                    params["check_in"] = requested_check_in.strip()
                    params["check_out"] = requested_check_out.strip()

                    if hotel_travellers is not None:
                        params["travellers"] = hotel_travellers
                else:
                    params["check_in"] = None
                    params["check_out"] = None

                params.pop("checkin", None)
                params.pop("checkout", None)

                step["required"] = True
                step["depends_on"] = []
                step["dep_policy"] = "all_success"
                step["params"] = params

                steps.append(step)

                if step.get("id"):
                    discovery_ids.append(step["id"])

                continue

            if tool == "search_flights_real":
                params["origin"] = first_value(
                    params.get("origin"),
                    params.get("from"),
                    "",
                )

                params["destination"] = first_value(
                    params.get("destination"),
                    params.get("to"),
                    "",
                )

                date_value = first_value(
                    params.get("date"),
                    params.get("dates"),
                    "",
                )

                if isinstance(date_value, list):
                    date_value = (
                        date_value[0] if date_value else ""
                    )

                if isinstance(date_value, str):
                    date_value = date_value.split(",")[0].strip()

                params.pop("from", None)
                params.pop("to", None)
                params.pop("dates", None)
                params["date"] = date_value

                # Flight discovery is supplementary. Skip it entirely when
                # the model has supplied placeholders or incomplete details.
                if not (
                    is_real_value(params["origin"])
                    and is_real_value(params["destination"])
                    and is_valid_date(date_value)
                ):
                    logger.warning(
                        "Skipping flight search because origin, destination, "
                        "or date is missing/invalid: origin=%r destination=%r date=%r",
                        params["origin"],
                        params["destination"],
                        date_value,
                    )
                    continue

                params["origin"] = params["origin"].strip()
                params["destination"] = params["destination"].strip()
                params["date"] = date_value.strip()

                step["required"] = False
                step["depends_on"] = []
                step["dep_policy"] = "tolerate_failure"
                step["params"] = params

                steps.append(step)

                if step.get("id"):
                    discovery_ids.append(step["id"])

                continue

            if tool == "get_cab_links":
                pickup = first_value(
                    params.get("pickup_location"),
                    params.get("from"),
                )
                dropoff = first_value(
                    params.get("dropoff_location"),
                    params.get("to"),
                )

                # Cab discovery is supplementary. Never manufacture either
                # location or infer one from the itinerary destination.
                if not (
                    is_real_value(pickup)
                    and is_real_value(dropoff)
                ):
                    logger.info(
                        "Skipping optional cab links because pickup or "
                        "drop-off was not explicitly resolved."
                    )
                    continue

                params["pickup_location"] = pickup.strip()
                params["dropoff_location"] = dropoff.strip()
                params.pop("from", None)
                params.pop("to", None)

                step["required"] = False
                step["depends_on"] = []
                step["dep_policy"] = "tolerate_failure"
                step["params"] = params

                steps.append(step)

                if step.get("id"):
                    discovery_ids.append(step["id"])

                continue

            if tool == "compile_trip_summary":
                step["required"] = True
                step["approval_required"] = False
                step["dep_policy"] = "tolerate_failure"
                step["params"] = {
                    "destination": context.get("destination", "")
                }

                steps.append(step)
                continue

            steps.append(step)

        # Find or create the final summary step.
        summary = next(
            (
                step for step in steps
                if step.get("tool") == "compile_trip_summary"
            ),
            None,
        )

        if summary is None and discovery_ids:
            summary = {
                "id": "compile_trip_summary",
                "description": "Compile the completed trip discoveries.",
                "tool": "compile_trip_summary",
                "params": {
                    "destination": context.get("destination", "")
                },
                "depends_on": [],
                "approval_required": False,
                "required": True,
                "dep_policy": "tolerate_failure",
                "max_retries": 0,
            }

            steps.append(summary)

        if summary is not None:
            summary["depends_on"] = discovery_ids

        return steps

    async def interpret(
        self,
        user_message: str,
        conversation_context: str = "",
    ) -> dict:
        tools_desc = "\n".join(
            f"- {tool.name}: {tool.description}"
            for tool in registry._tools.values()
        )

        system = GOAL_INTERPRETER_PROMPT.format(
            tools_desc=tools_desc,
            current_date=datetime.now().strftime("%Y-%m-%d"),
        )

        user_input = user_message
        if conversation_context:
            user_input = (
                f"Context:\n{conversation_context}\n\n"
                f"User's goal: {user_message}"
            )

        raw = await self.provider._call(
            system,
            user_input,
            force_json=True,
        )

        if raw == "LLM_FAILED":
            return {
                "plan": None,
                "needs_clarification": False,
                "clarification_question": None,
            }

        try:
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned)

            steps_raw = data.get("steps", [])
            if not steps_raw:
                return {
                    "plan": None,
                    "needs_clarification": False,
                    "clarification_question": None,
                }

            context = data.get("context", {}) or {}

            has_travel = any(
                step.get("tool") == "generate_advanced_itinerary"
                for step in steps_raw
            )

            if has_travel:
                steps_raw = self._normalize_travel_steps(
                    steps_raw,
                    context,
                )

            plan = WorkflowPlan(
                goal_title=data.get("goal_title", "User goal"),
                goal_description=data.get("goal_description", ""),
                context=context,
                steps=[WorkflowStep(**step) for step in steps_raw],
            )

            return {
                "plan": plan,
                "needs_clarification": False,
                "clarification_question": None,
            }

        except TravelClarificationRequired as exc:
            return {
                "plan": None,
                "needs_clarification": True,
                "clarification_question": str(exc),
            }

        except Exception as exc:
            logger.error(
                "Goal parse failed: %s | raw: %s",
                exc,
                raw[:300],
            )
            return {
                "plan": None,
                "needs_clarification": False,
                "clarification_question": None,
            }
