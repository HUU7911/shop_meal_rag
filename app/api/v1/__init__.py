from fastapi import APIRouter

from app.api.v1 import admin, auth, chat, conversations, feedback, health, history, users

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(conversations.router, tags=["conversations"])
api_router.include_router(history.router, tags=["history"])
api_router.include_router(feedback.router, tags=["feedback"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(users.router, prefix="/admin/users", tags=["admin-users"])