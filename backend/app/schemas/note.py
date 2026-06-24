from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class NoteBase(BaseModel):
    content: str

class NoteCreate(NoteBase):
    client_id: int

class NoteUpdate(NoteBase):
    pass

class Note(NoteBase):
    id: int
    client_id: int
    owner_id: int
    created_at: datetime

    model_config = {
        "from_attributes": True
    }