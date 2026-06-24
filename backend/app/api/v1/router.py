# app/api/v1/router.py
from fastapi import APIRouter
from . import clients, users, login, notes, analytics, notifications # 👈 ADDED: analytics & notifications
from .endpoints.leads import router as leads_router

api_router = APIRouter()

api_router.include_router(login.router, tags=["auth"])
api_router.include_router(clients.router, prefix="/clients", tags=["clients"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(notes.router, prefix="/notes", tags=["notes"])

# 🚀 The leads engine endpoints mounted cleanly under /api/v1/leads
api_router.include_router(leads_router, prefix="/leads", tags=["leads"])

# 📊 Dashboard metric bridges
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])         # 👈 ADDED
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"]) # 👈 ADDED