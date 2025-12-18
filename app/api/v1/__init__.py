"""
API v1 Routes
"""

from fastapi import APIRouter
from .agent import router as agent_router
from .convert import router as convert_router

api_router = APIRouter()
api_router.include_router(agent_router, prefix="/agent", tags=["agent"])
api_router.include_router(convert_router, tags=["convert"])

__all__ = ["api_router"]
