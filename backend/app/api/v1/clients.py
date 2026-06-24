from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from app.models.client import Client as ClientModel
from app.models.user import User as UserModel
from app.schemas.client import Client as ClientSchema, ClientCreate, ClientUpdate
from app.api import deps

router = APIRouter()

@router.get("/", response_model=List[ClientSchema])
def get_clients(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(deps.get_current_user)
):
    return db.query(ClientModel).filter(ClientModel.owner_id == current_user.id).all()

@router.get("/{client_id}", response_model=ClientSchema)
def get_client(client_id: int, db: Session = Depends(get_db), current_user: UserModel = Depends(deps.get_current_user)):
    client = db.query(ClientModel).filter(
        ClientModel.id == client_id, 
        ClientModel.owner_id == current_user.id
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client

@router.post("/", response_model=ClientSchema)
def create_client(client_in: ClientCreate, db: Session = Depends(get_db), current_user: UserModel = Depends(deps.get_current_user)):
    db_client = ClientModel(
        **client_in.model_dump(),
        owner_id=current_user.id
    )
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return db_client

@router.patch("/{client_id}", response_model=ClientSchema)
def update_client(client_id: int, client_in: ClientUpdate, db: Session = Depends(get_db), current_user: UserModel = Depends(deps.get_current_user)):
    db_client = db.query(ClientModel).filter(
        ClientModel.id == client_id,
        ClientModel.owner_id == current_user.id
    ).first()
    if not db_client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    update_data = client_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_client, key, value)

    db.commit()
    db.refresh(db_client)
    return db_client

@router.delete("/{client_id}", status_code=204)
def delete_client(client_id: int, db: Session = Depends(get_db), current_user: UserModel = Depends(deps.get_current_user)):
    db_client = db.query(ClientModel).filter(
        ClientModel.id == client_id,
        ClientModel.owner_id == current_user.id
    ).first()
    if not db_client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    db.delete(db_client)
    db.commit()
    return None