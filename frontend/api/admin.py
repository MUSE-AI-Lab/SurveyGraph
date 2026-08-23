"""
SurveyGraph Frontend - 管理员 API
==================================

管理员专用接口：用户管理、任务管理、系统监控等。
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from datetime import date, datetime
from typing import Optional, List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from config import TaskConfig, PROJECT_ROOT
from core.database import execute_query, execute_update
from core.models import User, Task, TaskStatus, UserRole
from core.security import get_current_admin

router = APIRouter()


# ==========================================
# 用户管理
# ==========================================

@router.get("/users", summary="获取所有用户")
async def list_users(
    role: Optional[str] = Query(None, description="按角色筛选"),
    search: Optional[str] = Query(None, description="搜索用户名或邮箱"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: User = Depends(get_current_admin)
):
    """
    获取所有用户列表（管理员专用）
    """
    offset = (page - 1) * page_size
    
    where_clauses = []
    params = []
    
    if role:
        where_clauses.append("role = %s")
        params.append(role)
    
    if search:
        where_clauses.append("(username LIKE %s OR email LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    # 查询总数
    count_query = f"SELECT COUNT(*) as count FROM users {where_sql}"
    count_result = await execute_query(count_query, tuple(params), fetch_one=True)
    total = count_result["count"] if count_result else 0
    
    # 查询列表
    list_query = f"""
        SELECT id, username, email, role, daily_quota, bonus_quota, 
               invite_code, invited_by, created_at
        FROM users {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([page_size, offset])
    results = await execute_query(list_query, tuple(params))
    
    users = []
    for row in results:
        users.append({
            "id": row["id"],
            "username": row["username"],
            "email": row["email"],
            "role": row["role"],
            "daily_quota": row["daily_quota"],
            "bonus_quota": row["bonus_quota"],
            "invite_code": row["invite_code"],
            "invited_by": row["invited_by"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None
        })
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "users": users
    }


@router.get("/users/{user_id}", summary="获取用户详情")
async def get_user(
    user_id: int,
    admin: User = Depends(get_current_admin)
):
    """
    获取指定用户的详细信息（管理员专用）
    """
    query = """
        SELECT id, username, email, role, daily_quota, bonus_quota,
               invite_code, invited_by, created_at, updated_at
        FROM users WHERE id = %s
    """
    result = await execute_query(query, (user_id,), fetch_one=True)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 获取用户的任务统计
    stats_query = """
        SELECT 
            COUNT(*) as total_tasks,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_tasks,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_tasks,
            SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running_tasks
        FROM tasks WHERE user_id = %s
    """
    stats_result = await execute_query(stats_query, (user_id,), fetch_one=True)
    
    # 获取邀请统计
    invite_query = "SELECT COUNT(*) as count FROM invitations WHERE inviter_id = %s"
    invite_result = await execute_query(invite_query, (user_id,), fetch_one=True)
    
    return {
        "id": result["id"],
        "username": result["username"],
        "email": result["email"],
        "role": result["role"],
        "daily_quota": result["daily_quota"],
        "bonus_quota": result["bonus_quota"],
        "invite_code": result["invite_code"],
        "invited_by": result["invited_by"],
        "created_at": result["created_at"].isoformat() if result["created_at"] else None,
        "updated_at": result["updated_at"].isoformat() if result["updated_at"] else None,
        "stats": {
            "total_tasks": stats_result["total_tasks"] if stats_result else 0,
            "completed_tasks": stats_result["completed_tasks"] if stats_result else 0,
            "failed_tasks": stats_result["failed_tasks"] if stats_result else 0,
            "running_tasks": stats_result["running_tasks"] if stats_result else 0,
            "invited_count": invite_result["count"] if invite_result else 0
        }
    }


@router.put("/users/{user_id}", summary="修改用户信息")
async def update_user(
    user_id: int,
    role: Optional[str] = None,
    daily_quota: Optional[int] = None,
    bonus_quota: Optional[int] = None,
    admin: User = Depends(get_current_admin)
):
    """
    修改用户信息（管理员专用）
    
    - **role**: 用户角色 (user/admin)
    - **daily_quota**: 每日配额
    - **bonus_quota**: 永久奖励配额
    """
    # 检查用户是否存在
    check_query = "SELECT id FROM users WHERE id = %s"
    result = await execute_query(check_query, (user_id,), fetch_one=True)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 构建更新语句
    updates = []
    params = []
    
    if role is not None:
        if role not in [UserRole.USER.value, UserRole.ADMIN.value]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的角色"
            )
        updates.append("role = %s")
        params.append(role)
    
    if daily_quota is not None:
        if daily_quota < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="配额不能为负数"
            )
        updates.append("daily_quota = %s")
        params.append(daily_quota)
    
    if bonus_quota is not None:
        if bonus_quota < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="配额不能为负数"
            )
        updates.append("bonus_quota = %s")
        params.append(bonus_quota)
    
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有要更新的字段"
        )
    
    update_query = f"UPDATE users SET {', '.join(updates)}, updated_at = NOW() WHERE id = %s"
    params.append(user_id)
    
    await execute_update(update_query, tuple(params))
    
    return {"message": "用户信息已更新"}


# ==========================================
# 任务管理
# ==========================================

@router.get("/tasks", summary="获取所有任务")
async def list_all_tasks(
    status: Optional[str] = Query(None, description="按状态筛选"),
    user_id: Optional[int] = Query(None, description="按用户筛选"),
    search: Optional[str] = Query(None, description="搜索主题"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: User = Depends(get_current_admin)
):
    """
    获取所有任务列表（管理员专用）
    """
    offset = (page - 1) * page_size
    
    where_clauses = []
    params = []
    
    if status:
        where_clauses.append("t.status = %s")
        params.append(status)
    
    if user_id:
        where_clauses.append("t.user_id = %s")
        params.append(user_id)
    
    if search:
        where_clauses.append("t.topic LIKE %s")
        params.append(f"%{search}%")
    
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    # 查询总数
    count_query = f"SELECT COUNT(*) as count FROM tasks t {where_sql}"
    count_result = await execute_query(count_query, tuple(params), fetch_one=True)
    total = count_result["count"] if count_result else 0
    
    # 查询列表（包含用户名）
    list_query = f"""
        SELECT t.*, u.username
        FROM tasks t
        LEFT JOIN users u ON t.user_id = u.id
        {where_sql}
        ORDER BY t.created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([page_size, offset])
    results = await execute_query(list_query, tuple(params))
    
    tasks = []
    for row in results:
        tasks.append({
            "id": row["id"],
            "task_id": row["task_id"],
            "user_id": row["user_id"],
            "username": row["username"],
            "topic": row["topic"],
            "status": row["status"],
            "current_step": row["current_step"],
            "current_step_name": row["current_step_name"],
            "progress_percent": row["progress_percent"],
            "papers_count": row["papers_count"],
            "error_message": row["error_message"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None
        })
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "tasks": tasks
    }


@router.get("/tasks/{task_id}/logs", summary="获取任务详细日志")
async def get_task_detailed_logs(
    task_id: str,
    level: Optional[str] = Query(None, description="按级别筛选"),
    step: Optional[int] = Query(None, description="按步骤筛选"),
    limit: int = Query(500, ge=1, le=5000),
    admin: User = Depends(get_current_admin)
):
    """
    获取任务的详细日志（管理员专用，包含 debug 级别和详细信息）
    """
    # 获取任务
    task_query = "SELECT id FROM tasks WHERE task_id = %s"
    task_result = await execute_query(task_query, (task_id,), fetch_one=True)
    
    if not task_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    task_db_id = task_result["id"]
    
    # 构建查询
    where_clauses = ["task_id = %s"]
    params = [task_db_id]
    
    if level:
        where_clauses.append("level = %s")
        params.append(level)
    
    if step is not None:
        where_clauses.append("step = %s")
        params.append(step)
    
    where_sql = "WHERE " + " AND ".join(where_clauses)
    
    query = f"""
        SELECT * FROM task_logs {where_sql}
        ORDER BY created_at DESC
        LIMIT %s
    """
    params.append(limit)
    
    results = await execute_query(query, tuple(params))
    
    logs = []
    for row in results:
        logs.append({
            "id": row["id"],
            "task_id": row["task_id"],
            "step": row["step"],
            "step_name": row["step_name"],
            "level": row["level"],
            "message": row["message"],
            "details": row["details"],  # 管理员可以看到详细信息
            "created_at": row["created_at"].isoformat() if row["created_at"] else None
        })
    
    return {
        "total": len(logs),
        "logs": logs
    }


@router.post("/tasks/{task_id}/force-retry", summary="强制重试任务")
async def force_retry_task(
    task_id: str,
    from_step: int = 0,
    admin: User = Depends(get_current_admin)
):
    """
    强制重试任务（管理员专用，不受重试次数限制）
    """
    # 获取任务
    task_query = "SELECT * FROM tasks WHERE task_id = %s"
    task_result = await execute_query(task_query, (task_id,), fetch_one=True)
    
    if not task_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    task = Task.from_dict(task_result)
    
    # 如果是从头开始，重置所有进度字段
    if from_step == 0:
        await execute_update(
            """UPDATE tasks SET
                status = %s,
                current_step = 0,
                current_step_name = 'NOT_STARTED',
                progress_percent = 0,
                papers_count = 0,
                relations_count = 0,
                sections_count = 0,
                error_message = NULL,
                completed_at = NULL,
                updated_at = NOW()
            WHERE id = %s""",
            (TaskStatus.RUNNING.value, task.id)
        )
    else:
        # 否则只更新状态和步骤
        await execute_update(
            """UPDATE tasks SET
                status = %s,
                current_step = %s,
                error_message = NULL,
                updated_at = NOW()
            WHERE id = %s""",
            (TaskStatus.RUNNING.value, from_step, task.id)
        )
    
    # 如果是从头开始，删除 checkpoint 文件并设置 resume=False
    resume = True
    if from_step == 0:
        resume = False
        # 删除 checkpoint 文件
        checkpoint_path = PROJECT_ROOT / "outputs" / task_id / "checkpoint.json"
        if checkpoint_path.exists():
            try:
                os.remove(checkpoint_path)
            except Exception:
                pass
    
    # 启动 Pipeline
    from services.pipeline_service import start_pipeline
    await start_pipeline(task_id, resume=resume, from_step=from_step)
    
    return {"message": f"任务已从步骤 {from_step} 强制重试"}


@router.post("/tasks/{task_id}/force-cancel", summary="强制取消任务")
async def force_cancel_task(
    task_id: str,
    admin: User = Depends(get_current_admin)
):
    """
    强制取消任务（管理员专用）
    """
    # 获取任务
    task_query = "SELECT id FROM tasks WHERE task_id = %s"
    task_result = await execute_query(task_query, (task_id,), fetch_one=True)
    
    if not task_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 更新状态
    await execute_update(
        "UPDATE tasks SET status = %s, error_message = %s, updated_at = NOW() WHERE id = %s",
        (TaskStatus.FAILED.value, "管理员强制取消", task_result["id"])
    )
    
    # 取消 Pipeline
    from services.pipeline_service import cancel_pipeline
    await cancel_pipeline(task_id)
    
    return {"message": "任务已强制取消"}


# ==========================================
# 系统监控
# ==========================================

@router.get("/stats", summary="获取系统统计")
async def get_system_stats(admin: User = Depends(get_current_admin)):
    """
    获取系统统计信息（管理员专用）
    """
    today = date.today()
    
    # 用户统计
    user_stats_query = """
        SELECT 
            COUNT(*) as total_users,
            SUM(CASE WHEN role = 'admin' THEN 1 ELSE 0 END) as admin_count,
            SUM(CASE WHEN DATE(created_at) = %s THEN 1 ELSE 0 END) as today_registered
        FROM users
    """
    user_stats = await execute_query(user_stats_query, (today,), fetch_one=True)
    
    # 任务统计
    task_stats_query = """
        SELECT 
            COUNT(*) as total_tasks,
            SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running_tasks,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_tasks,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_tasks,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_tasks,
            SUM(CASE WHEN DATE(created_at) = %s THEN 1 ELSE 0 END) as today_created,
            SUM(CASE WHEN DATE(completed_at) = %s THEN 1 ELSE 0 END) as today_completed
        FROM tasks
    """
    task_stats = await execute_query(task_stats_query, (today, today), fetch_one=True)
    
    # 邀请统计
    invite_stats_query = """
        SELECT 
            COUNT(*) as total_invitations,
            SUM(CASE WHEN DATE(created_at) = %s THEN 1 ELSE 0 END) as today_invitations
        FROM invitations
    """
    invite_stats = await execute_query(invite_stats_query, (today,), fetch_one=True)
    
    return {
        "users": {
            "total": user_stats["total_users"] if user_stats else 0,
            "admins": user_stats["admin_count"] if user_stats else 0,
            "today_registered": user_stats["today_registered"] if user_stats else 0
        },
        "tasks": {
            "total": task_stats["total_tasks"] if task_stats else 0,
            "running": task_stats["running_tasks"] if task_stats else 0,
            "completed": task_stats["completed_tasks"] if task_stats else 0,
            "failed": task_stats["failed_tasks"] if task_stats else 0,
            "pending": task_stats["pending_tasks"] if task_stats else 0,
            "today_created": task_stats["today_created"] if task_stats else 0,
            "today_completed": task_stats["today_completed"] if task_stats else 0
        },
        "invitations": {
            "total": invite_stats["total_invitations"] if invite_stats else 0,
            "today": invite_stats["today_invitations"] if invite_stats else 0
        },
        "timestamp": datetime.now().isoformat()
    }


@router.get("/running-tasks", summary="获取运行中的任务")
async def get_running_tasks(admin: User = Depends(get_current_admin)):
    """
    获取当前运行中的任务列表（管理员专用）
    """
    query = """
        SELECT t.*, u.username
        FROM tasks t
        LEFT JOIN users u ON t.user_id = u.id
        WHERE t.status = 'running'
        ORDER BY t.updated_at DESC
    """
    results = await execute_query(query)
    
    tasks = []
    for row in results:
        tasks.append({
            "task_id": row["task_id"],
            "username": row["username"],
            "topic": row["topic"],
            "current_step": row["current_step"],
            "current_step_name": row["current_step_name"],
            "progress_percent": row["progress_percent"],
            "started_at": row["updated_at"].isoformat() if row["updated_at"] else None
        })
    
    return {
        "count": len(tasks),
        "tasks": tasks
    }