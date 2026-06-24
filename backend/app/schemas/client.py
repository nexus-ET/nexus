from pydantic import BaseModel, EmailStr
from typing import Optional

class ClientBase(BaseModel):
    name: str
    email: EmailStr
    company: Optional[str] = None
    phone_number: Optional[str] = None
    address: Optional[str] = None

class ClientCreate(ClientBase):
    pass

class ClientUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    company: Optional[str] = None
    phone_number: Optional[str] = None
    address: Optional[str] = None

class Client(ClientBase):
    id: int

    model_config = {
        "from_attributes": True
    }