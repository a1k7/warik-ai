from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import TravelPlan, TravelStop, User
from app.schemas.travel import TravelPlanCreate, TravelPlanResponse, TravelPlanUpdate

router = APIRouter(prefix="/travel", tags=["travel"])


@router.post("/", response_model=TravelPlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: TravelPlanCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TravelPlanResponse:
    plan = TravelPlan(
        user_id=user.id,
        title=payload.title,
        origin=payload.origin,
        destination=payload.destination,
        start_date=payload.start_date,
        end_date=payload.end_date,
        travellers=payload.travellers,
        budget=payload.budget,
        currency=payload.currency,
        notes=payload.notes,
    )
    db.add(plan)
    db.flush()

    for idx, stop in enumerate(payload.stops):
        db.add(
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

    db.commit()
    db.refresh(plan)
    return TravelPlanResponse.model_validate(plan)


@router.get("/", response_model=list[TravelPlanResponse])
def list_plans(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TravelPlanResponse]:
    plans = (
        db.query(TravelPlan)
        .filter(TravelPlan.user_id == user.id)
        .order_by(TravelPlan.created_at.desc())
        .all()
    )
    return [TravelPlanResponse.model_validate(p) for p in plans]


@router.get("/{plan_id}", response_model=TravelPlanResponse)
def get_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TravelPlanResponse:
    plan = db.get(TravelPlan, plan_id)
    if plan is None or plan.user_id != user.id:
        raise HTTPException(status_code=404, detail="Travel plan not found")
    return TravelPlanResponse.model_validate(plan)


@router.put("/{plan_id}", response_model=TravelPlanResponse)
def update_plan(
    plan_id: int,
    payload: TravelPlanUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TravelPlanResponse:
    plan = db.get(TravelPlan, plan_id)
    if plan is None or plan.user_id != user.id:
        raise HTTPException(status_code=404, detail="Travel plan not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(plan, key, value)

    db.commit()
    db.refresh(plan)
    return TravelPlanResponse.model_validate(plan)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    plan = db.get(TravelPlan, plan_id)
    if plan is None or plan.user_id != user.id:
        raise HTTPException(status_code=404, detail="Travel plan not found")

    db.delete(plan)
    db.commit()