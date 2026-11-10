import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "service": "warik-ai-backend",
            "database": "ok",
        }
    except SQLAlchemyError:
        logger.exception("Health check database query failed")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "service": "warik-ai-backend",
                "database": "unavailable",
            },
        )
