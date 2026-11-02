from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import User, UserPreference
from app.schemas.user import UserPreferenceResponse, UserPreferenceUpdate

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("/", response_model=UserPreferenceResponse)
def get_preferences(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserPreferenceResponse:
    pref = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    if pref is None:
        pref = UserPreference(user_id=user.id)
        db.add(pref)
        db.commit()
        db.refresh(pref)
    return UserPreferenceResponse.model_validate(pref)


@router.put("/", response_model=UserPreferenceResponse)
def update_preferences(
    payload: UserPreferenceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserPreferenceResponse:
    pref = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    if pref is None:
        pref = UserPreference(user_id=user.id)
        db.add(pref)

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(pref, key, value)

    db.commit()
    db.refresh(pref)
    return UserPreferenceResponse.model_validate(pref)