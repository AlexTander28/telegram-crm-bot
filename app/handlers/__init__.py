"""Aiogram routers for clients and managers."""

from app.handlers.client import router as client_router
from app.handlers.manager import router as manager_router

__all__ = ["client_router", "manager_router"]

