"""ORM models — every model must be imported here so SQLAlchemy
registers it with the metadata before `Base.metadata.create_all`."""

from app.models.action_log import ActionLog
from app.models.conversation import Conversation, Message
from app.models.expense import Expense
from app.models.food import FavoriteRestaurant
from app.models.memory import Memory
from app.models.reminder import Reminder
from app.models.task import Task
from app.models.travel import TravelPlan, TravelStop
from app.models.user import User, UserPreference
from app.models.voice_usage import VoiceUsage

__all__ = [
    "ActionLog",
    "Conversation",
    "Expense",
    "FavoriteRestaurant",
    "Memory",
    "Message",
    "Reminder",
    "Task",
    "TravelPlan",
    "TravelStop",
    "User",
    "UserPreference",
    "VoiceUsage",
]