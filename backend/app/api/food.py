from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import FavoriteRestaurant, User
from app.schemas.food import (
    FavoriteRestaurantCreate,
    FavoriteRestaurantResponse,
    FoodSearchRequest,
    FoodSearchResponse,
)

router = APIRouter(prefix="/food", tags=["food"])


@router.post("/search", response_model=FoodSearchResponse)
def search_food(
    payload: FoodSearchRequest,
) -> FoodSearchResponse:
    """Discover restaurants.

    This prototype does not have a live provider (e.g. Google Places) configured.
    Instead of fabricating ratings or hours, we generate external search links.
    """
    query = payload.location
    if payload.preference:
        query += f" {payload.preference}"
    if payload.budget:
        query += f" {payload.budget}"

    google_maps_url = f"https://www.google.com/maps/search/?api=1&{urlencode({'query': query})}"
    zomato_url = f"https://www.zomato.com/search?{urlencode({'q': query})}"

    disclaimer = (
        "Live restaurant discovery is not configured in this local prototype. "
        "The links below will open external search results based on your criteria. "
        "Warik AI does not claim to verify live ratings or availability."
    )

    return FoodSearchResponse(
        disclaimer=disclaimer,
        external_links={
            "Google Maps": google_maps_url,
            "Zomato": zomato_url,
        },
    )


@router.post("/favorites", response_model=FavoriteRestaurantResponse, status_code=status.HTTP_201_CREATED)
def add_favorite(
    payload: FavoriteRestaurantCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FavoriteRestaurantResponse:
    fav = FavoriteRestaurant(
        user_id=user.id,
        name=payload.name,
        location=payload.location,
        notes=payload.notes,
    )
    db.add(fav)
    db.commit()
    db.refresh(fav)
    return FavoriteRestaurantResponse.model_validate(fav)


@router.get("/favorites", response_model=list[FavoriteRestaurantResponse])
def list_favorites(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FavoriteRestaurantResponse]:
    favs = (
        db.query(FavoriteRestaurant)
        .filter(FavoriteRestaurant.user_id == user.id)
        .order_by(FavoriteRestaurant.created_at.desc())
        .all()
    )
    return [FavoriteRestaurantResponse.model_validate(f) for f in favs]


@router.delete("/favorites/{fav_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_favorite(
    fav_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    fav = db.get(FavoriteRestaurant, fav_id)
    if fav is None or fav.user_id != user.id:
        raise HTTPException(status_code=404, detail="Favorite not found")

    db.delete(fav)
    db.commit()