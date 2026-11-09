from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401
from app.api.agent import router as agent_router
from app.api.auth import router as auth_router
from app.api.expenses import router as expenses_router
from app.api.food import router as food_router
from app.api.health import router as health_router
from app.api.memory import router as memory_router
from app.api.preferences import router as preferences_router
from app.api.reminders import router as reminders_router
from app.api.saved import router as saved_router
from app.api.tasks import router as tasks_router
from app.api.travel import router as travel_router
from app.api.voice import router as voice_router
from app.api.conversations import router as conversations_router
from app.api.bookings import router as bookings_router
from app.api.workflows import router as workflows_router  # NEW
from app.core.config import settings
from app.database.base import Base
from app.database.session import engine
from app.api.documents import router as documents_router
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title=settings.app_name,
    version="0.7.0",
    description="Warik AI — your AI companion for everyday life.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(agent_router, prefix="/api")
app.include_router(voice_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(saved_router, prefix="/api")
app.include_router(reminders_router, prefix="/api")
app.include_router(expenses_router, prefix="/api")
app.include_router(preferences_router, prefix="/api")
app.include_router(travel_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(food_router, prefix="/api")
app.include_router(conversations_router, prefix="/api")
app.include_router(bookings_router, prefix="/api")
app.include_router(workflows_router, prefix="/api")  # NEW
app.include_router(documents_router, prefix="/api")
@app.get("/", tags=["root"])
def root() -> dict[str, str]:
    return {
        "message": "Warik AI backend is running",
        "docs": "/docs",
        "health": "/api/health",
    }