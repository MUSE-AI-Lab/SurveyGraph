"""
SurveyGraph Frontend - 用户 API
================================

用户配额、邀请码等用户相关接口。
"""

from fastapi import APIRouter, HTTPException, status, Depends
from datetime import date
from typing import List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import TaskConfig, AppConfig
from core.database import execute_query, execute_update
from core.models import (
    User,
    QuotaResponse, InviteCodeResponse
)
from core.security import (
    get_current_user,
    get_user_by_invite_code,
)

router = APIRouter()


@router.get("/quota", response_model=QuotaResponse, summary="获取用户配额信息")
async def get_quota(current_user: User = Depends(get_current_user)):
    """
    获取当前用户的配额信息
    
    返回:
    - **daily_quota**: 每日配额
    - **bonus_quota**: 永久奖励配额
    - **total_quota**: 总配额
    - **used_today**: 今日已使用
    - **remaining_today**: 今日剩余
    """
    # 查询今日已使用的次数
    today = date.today()
    query = """
        SELECT COUNT(*) as count FROM tasks 
        WHERE user_id = %s AND DATE(created_at) = %s
    """
    result = await execute_query(query, (current_user.id, today), fetch_one=True)
    used_today = result["count"] if result else 0
    
    total_quota = current_user.daily_quota + current_user.bonus_quota
    remaining_today = max(0, total_quota - used_today)
    
    return QuotaResponse(
        daily_quota=current_user.daily_quota,
        bonus_quota=current_user.bonus_quota,
        total_quota=total_quota,
        used_today=used_today,
        remaining_today=remaining_today
    )


@router.get("/invite-code", response_model=InviteCodeResponse, summary="获取邀请码")
async def get_invite_code(current_user: User = Depends(get_current_user)):
    """
    获取当前用户的邀请码和邀请链接
    
    返回:
    - **invite_code**: 邀请码
    - **invite_url**: 邀请链接
    - **invited_count**: 已邀请人数
    """
    # 查询已邀请人数
    query = "SELECT COUNT(*) as count FROM invitations WHERE inviter_id = %s"
    result = await execute_query(query, (current_user.id,), fetch_one=True)
    invited_count = result["count"] if result else 0
    
    # 构建邀请链接
    invite_url = f"/register?invite={current_user.invite_code}"
    
    return InviteCodeResponse(
        invite_code=current_user.invite_code,
        invite_url=invite_url,
        invited_count=invited_count
    )


@router.post("/apply-invite", summary="使用邀请码")
async def apply_invite_code(
    invite_code: str,
    current_user: User = Depends(get_current_user)
):
    """
    使用邀请码获取奖励
    
    注意：此接口用于已注册用户补填邀请码的场景。
    如果用户注册时已填写邀请码，则不能再次使用。
    
    - **invite_code**: 邀请码
    """
    # 检查用户是否已经被邀请过
    if current_user.invited_by:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="您已经使用过邀请码"
        )
    
    # 检查邀请码是否有效
    inviter = await get_user_by_invite_code(invite_code)
    if not inviter:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的邀请码"
        )
    
    # 不能使用自己的邀请码
    if inviter.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能使用自己的邀请码"
        )
    
    # 更新当前用户
    await execute_update(
        "UPDATE users SET invited_by = %s, bonus_quota = bonus_quota + %s WHERE id = %s",
        (inviter.id, TaskConfig.INVITE_BONUS_QUOTA, current_user.id)
    )
    
    # 更新邀请人
    await execute_update(
        "UPDATE users SET bonus_quota = bonus_quota + %s WHERE id = %s",
        (TaskConfig.INVITE_BONUS_QUOTA, inviter.id)
    )
    
    # 记录邀请关系
    from core.database import execute_insert
    await execute_insert(
        "INSERT INTO invitations (inviter_id, invitee_id, invite_code, bonus_granted) VALUES (%s, %s, %s, %s)",
        (inviter.id, current_user.id, invite_code, True)
    )
    
    return {
        "message": f"邀请码使用成功！您和邀请人各获得 {TaskConfig.INVITE_BONUS_QUOTA} 次永久生成次数"
    }


@router.get("/invitations", summary="获取邀请记录")
async def get_invitations(current_user: User = Depends(get_current_user)):
    """
    获取当前用户的邀请记录
    
    返回邀请的用户列表
    """
    query = """
        SELECT u.id, u.username, u.created_at, i.bonus_granted
        FROM invitations i
        JOIN users u ON i.invitee_id = u.id
        WHERE i.inviter_id = %s
        ORDER BY i.created_at DESC
    """
    results = await execute_query(query, (current_user.id,))
    
    invitations = []
    for row in results:
        invitations.append({
            "user_id": row["id"],
            "username": row["username"],
            "registered_at": row["created_at"].isoformat() if row["created_at"] else None,
            "bonus_granted": row["bonus_granted"]
        })
    
    return {
        "total": len(invitations),
        "invitations": invitations
    }


@router.get("/stats", summary="获取用户统计信息")
async def get_user_stats(current_user: User = Depends(get_current_user)):
    """
    获取当前用户的统计信息
    
    返回:
    - 任务总数
    - 已完成任务数
    - 失败任务数
    - 今日任务数
    """
    user_id = current_user.id
    today = date.today()
    
    # 任务总数
    total_query = "SELECT COUNT(*) as count FROM tasks WHERE user_id = %s"
    total_result = await execute_query(total_query, (user_id,), fetch_one=True)
    total_tasks = total_result["count"] if total_result else 0
    
    # 已完成任务数
    completed_query = "SELECT COUNT(*) as count FROM tasks WHERE user_id = %s AND status = 'completed'"
    completed_result = await execute_query(completed_query, (user_id,), fetch_one=True)
    completed_tasks = completed_result["count"] if completed_result else 0
    
    # 失败任务数
    failed_query = "SELECT COUNT(*) as count FROM tasks WHERE user_id = %s AND status = 'failed'"
    failed_result = await execute_query(failed_query, (user_id,), fetch_one=True)
    failed_tasks = failed_result["count"] if failed_result else 0
    
    # 今日任务数
    today_query = "SELECT COUNT(*) as count FROM tasks WHERE user_id = %s AND DATE(created_at) = %s"
    today_result = await execute_query(today_query, (user_id, today), fetch_one=True)
    today_tasks = today_result["count"] if today_result else 0
    
    # 运行中任务数
    running_query = "SELECT COUNT(*) as count FROM tasks WHERE user_id = %s AND status = 'running'"
    running_result = await execute_query(running_query, (user_id,), fetch_one=True)
    running_tasks = running_result["count"] if running_result else 0
    
    return {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "failed_tasks": failed_tasks,
        "running_tasks": running_tasks,
        "today_tasks": today_tasks,
        "success_rate": round(completed_tasks / total_tasks * 100, 1) if total_tasks > 0 else 0
    }