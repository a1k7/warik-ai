"""Document schemas."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    mime_type: str
    page_count: int
    char_count: int
    created_at: datetime


class DocumentUploadResponse(BaseModel):
    document_id: int
    filename: str
    page_count: int
    char_count: int
    preview: str  # First 300 chars