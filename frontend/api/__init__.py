"""
SurveyGraph Frontend - API Module
==================================

API 路由模块。
"""

from fastapi import APIRouter

from .auth import router as auth_router
from .users import router as users_router
from .tasks import router as tasks_router
from .admin import router as admin_router
from .websocket import router as websocket_router
from .processes import router as processes_router
from .upload import router as upload_router
from .knowledge_base import router as knowledge_base_router

# 创建主路由
api_router = APIRouter()

# 注册子路由
api_router.include_router(auth_router, prefix="/auth", tags=["认证"])
api_router.include_router(users_router, prefix="/user", tags=["用户"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["任务"])
api_router.include_router(admin_router, prefix="/admin", tags=["管理员"])
api_router.include_router(processes_router, prefix="/processes", tags=["进程管理"])
api_router.include_router(upload_router, prefix="/upload", tags=["文件上传"])
api_router.include_router(knowledge_base_router, prefix="/knowledge-base", tags=["个人知识库"])

__all__ = [
    "api_router",
    "auth_router",
    "users_router",
    "tasks_router",
    "admin_router",
    "websocket_router",
    "processes_router",
    "upload_router",
    "knowledge_base_router",
]