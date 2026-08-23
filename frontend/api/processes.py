"""
SurveyGraph Frontend - 进程管理 API
====================================

提供进程状态查询、日志获取等接口。
主要用于调试和监控。
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
import logging

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import User
from core.security import get_current_user
from services.process_manager import process_manager, ProcessInfo
from services.pipeline_service import get_pipeline_status, get_task_logs, get_running_tasks

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/running", summary="获取所有运行中的任务进程")
async def list_running_processes(
    current_user: User = Depends(get_current_user)
):
    """
    获取所有运行中的任务进程列表
    
    返回每个进程的 PID、任务 ID、启动时间等信息。
    """
    running_tasks = process_manager.get_all_running_tasks()
    
    result = []
    for process_info in running_tasks:
        result.append({
            "task_id": process_info.task_id,
            "pid": process_info.pid,
            "started_at": process_info.started_at,
            "status": process_info.status,
            "log_file": process_info.log_file
        })
    
    return {
        "total": len(result),
        "processes": result
    }


@router.get("/{task_id}", summary="获取任务进程详情")
async def get_process_info(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取指定任务的进程详情
    
    包括 PID、状态、日志文件路径等信息。
    """
    process_info = process_manager.get_process_info(task_id)
    
    if not process_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="进程信息不存在"
        )
    
    # 检查进程是否还在运行
    is_running = process_manager.is_task_running(task_id)
    
    return {
        "task_id": process_info.task_id,
        "pid": process_info.pid,
        "command": process_info.command,
        "started_at": process_info.started_at,
        "status": process_info.status,
        "is_running": is_running,
        "log_file": process_info.log_file,
        "exit_code": process_info.exit_code
    }


@router.get("/{task_id}/logs", summary="获取任务进程日志")
async def get_process_logs(
    task_id: str,
    lines: int = Query(100, ge=1, le=10000, description="返回的行数"),
    current_user: User = Depends(get_current_user)
):
    """
    获取任务进程的原始日志
    
    从日志文件中读取最后 N 行日志。
    """
    logs = get_task_logs(task_id, lines)
    
    return {
        "task_id": task_id,
        "total_lines": len(logs),
        "logs": logs
    }


@router.post("/{task_id}/stop", summary="停止任务进程")
async def stop_process(
    task_id: str,
    force: bool = Query(False, description="是否强制终止"),
    current_user: User = Depends(get_current_user)
):
    """
    停止指定任务的进程
    
    - **force=False**: 发送 SIGTERM 信号，允许进程优雅退出
    - **force=True**: 发送 SIGKILL 信号，强制终止进程
    """
    # 检查进程是否存在
    process_info = process_manager.get_process_info(task_id)
    if not process_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="进程信息不存在"
        )
    
    # 检查进程是否在运行
    if not process_manager.is_task_running(task_id):
        return {
            "message": "进程已经停止",
            "task_id": task_id,
            "status": process_info.status
        }
    
    # 停止进程
    success = await process_manager.stop_task(task_id, force=force)
    
    if success:
        return {
            "message": "进程已停止",
            "task_id": task_id,
            "force": force
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="停止进程失败"
        )


@router.get("/{task_id}/status", summary="获取任务 Pipeline 状态")
async def get_task_pipeline_status(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取任务的 Pipeline 状态
    
    包括当前步骤、进度、进程信息等。
    """
    status_info = await get_pipeline_status(task_id)
    
    if "error" in status_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=status_info["error"]
        )
    
    return status_info


@router.post("/cleanup", summary="清理旧的进程信息")
async def cleanup_old_processes(
    max_age_hours: int = Query(72, ge=1, le=720, description="最大保留时间（小时）"),
    current_user: User = Depends(get_current_user)
):
    """
    清理旧的进程信息文件
    
    删除超过指定时间的已完成/失败任务的进程信息。
    """
    # 只有管理员可以执行清理
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    
    from services.pipeline_service import cleanup_old_processes
    cleanup_old_processes(max_age_hours)
    
    return {
        "message": f"已清理超过 {max_age_hours} 小时的进程信息"
    }