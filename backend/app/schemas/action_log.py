from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ActionLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    action: str
    tool_name: Optional[str]
    payload: Optional[dict]
    result_status: str
    result_message: Optional[str]
    created_at: datetime