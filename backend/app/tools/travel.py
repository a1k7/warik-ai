from app.models import TravelPlan, TravelStop
from app.schemas.travel import TravelPlanCreate
from app.tools.base import BaseTool, ToolContext, ToolResult


class CreateTravelPlanTool(BaseTool):
    name = "create_travel_plan"
    description = "Create a travel plan with origin, destination, dates, budget and optional stops."
    input_schema = TravelPlanCreate
    requires_confirmation = True

    def confirmation_prompt(self, params: TravelPlanCreate) -> str:
        return f"create a travel plan from {params.origin} to {params.destination}"

    def execute(self, ctx: ToolContext, params: TravelPlanCreate) -> ToolResult:
        plan = TravelPlan(
            user_id=ctx.user.id,
            title=params.title,
            origin=params.origin,
            destination=params.destination,
            start_date=params.start_date,
            end_date=params.end_date,
            travellers=params.travellers,
            budget=params.budget,
            currency=params.currency,
            notes=params.notes,
        )
        ctx.db.add(plan)
        ctx.db.flush()

        for idx, stop in enumerate(params.stops):
            ctx.db.add(
                TravelStop(
                    travel_plan_id=plan.id,
                    order_index=idx,
                    name=stop.name,
                    notes=stop.notes,
                    arrival=stop.arrival,
                    departure=stop.departure,
                    estimated_cost=stop.estimated_cost,
                )
            )

        ctx.db.commit()
        ctx.db.refresh(plan)

        budget_line = f" budget ₹{plan.budget}" if plan.budget else ""
        return ToolResult(
            success=True,
            message=(
                f"Created travel plan '{plan.title}': {plan.origin} → {plan.destination}"
                f" ({plan.travellers} traveller{'s' if plan.travellers != 1 else ''}){budget_line}."
            ),
            data={"travel_plan_id": plan.id, "stops": len(params.stops)},
        )

    def verify(self, ctx: ToolContext, params: TravelPlanCreate, result: ToolResult) -> dict:
        from app.models import TravelPlan
        plan_id = (result.data or {}).get("travel_plan_id")
        saved = (ctx.db.query(TravelPlan).filter(TravelPlan.id == plan_id,
                 TravelPlan.user_id == ctx.user.id).one_or_none() if plan_id else None)
        stops = list(saved.stops) if saved else []
        expected_stops = list(params.stops)
        stops_match = len(stops) == len(expected_stops) and all(
            actual.name == expected.name and (actual.notes or None) == (expected.notes or None)
            for actual, expected in zip(stops, expected_stops)
        )
        matches = bool(saved and saved.title == params.title and saved.origin == params.origin
                       and saved.destination == params.destination
                       and saved.start_date == params.start_date and saved.end_date == params.end_date
                       and saved.travellers == params.travellers
                       and ((saved.budget is None and params.budget is None)
                            or (saved.budget is not None and params.budget is not None
                                and str(saved.budget) == str(params.budget)))
                       and saved.currency == params.currency and stops_match)
        return {"verified": matches, "method": "database_record_and_stops_lookup",
                "evidence": {"travel_plan_id": plan_id, "record_found": saved is not None,
                             "user_scope_checked": True, "stop_count": len(stops),
                             "stops_matched": stops_match, "fields_matched": matches}}
