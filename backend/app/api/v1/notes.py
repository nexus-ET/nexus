from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from app.models.note import Note as NoteModel
from app.models.client import Client as ClientModel
from app.models.user import User as UserModel
from app.schemas.note import Note, NoteCreate
from app.api import deps

router = APIRouter()

@router.post("/", response_model=Note)
def create_note(
    note_in: NoteCreate, 
    db: Session = Depends(get_db), 
    current_user: UserModel = Depends(deps.get_current_user)
):
    # Check if the client exists and belongs to the user
    client = db.query(ClientModel).filter(
        ClientModel.id == note_in.client_id, 
        ClientModel.owner_id == current_user.id
    ).first()
    
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    db_note = NoteModel(
        content=note_in.content,
        client_id=note_in.client_id,
        owner_id=current_user.id
    )
    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    return db_note

@router.get("/client/{client_id}", response_model=List[Note])
def get_notes_for_client(
    client_id: int, 
    db: Session = Depends(get_db), 
    current_user: UserModel = Depends(deps.get_current_user)
):
    return db.query(NoteModel).filter(
        NoteModel.client_id == client_id, 
        NoteModel.owner_id == current_user.id
    ).all()