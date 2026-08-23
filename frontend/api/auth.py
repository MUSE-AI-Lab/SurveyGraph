"""
SurveyGraph Frontend - 认证 API
================================

用户注册、登录、登出、Token 刷新等认证相关接口。
"""

from fastapi import APIRouter, HTTPException, status, Depends, Response
from fastapi.responses import JSONResponse
from datetime import date
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import TaskConfig
from core.database import execute_query, execute_insert, execute_update
from core.models import (
    User, UserRole,
    UserCreate, UserLogin, UserResponse, TokenResponse
)
from core.security import (
    get_password_hash,
    verify_password,
    create_tokens_for_user,
    verify_token,
    generate_invite_code,
    get_user_by_username,
    get_user_by_email,
    get_user_by_invite_code,
    get_user_by_id,
    get_current_user,
)

router = APIRouter()


# Cookie 配置
COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30天（秒）
COOKIE_SECURE = False  # 生产环境应设为 True（仅 HTTPS）
COOKIE_HTTPONLY = True  # 防止 JavaScript 访问
COOKIE_SAMESITE = "lax"  # 防止 CSRF


def set_auth_cookies(response: Response, tokens: dict):
    """设置认证 Cookie"""
    response.set_cookie(
        key="access_token",
        value=tokens["access_token"],
        max_age=COOKIE_MAX_AGE,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/"
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        max_age=COOKIE_MAX_AGE,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/"
    )


def clear_auth_cookies(response: Response):
    """清除认证 Cookie"""
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")


@router.post("/register", response_model=TokenResponse, summary="用户注册")
async def register(user_data: UserCreate, response: Response):
    """
    用户注册
    
    - **username**: 用户名 (3-50字符)
    - **email**: 邮箱
    - **password**: 密码 (6-100字符)
    - **invite_code**: 邀请码 (可选)
    
    成功后会自动设置认证 Cookie（30天有效期）
    """
    # 检查用户名是否已存在
    existing_user = await get_user_by_username(user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )
    
    # 检查邮箱是否已存在
    existing_email = await get_user_by_email(user_data.email)
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已被注册"
        )
    
    # 处理邀请码
    inviter_id = None
    if user_data.invite_code:
        inviter = await get_user_by_invite_code(user_data.invite_code)
        if not inviter:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的邀请码"
            )
        inviter_id = inviter.id
    
    # 生成用户的邀请码
    new_invite_code = generate_invite_code()
    
    # 创建用户
    password_hash = get_password_hash(user_data.password)
    
    query = """
        INSERT INTO users (username, email, password_hash, role, daily_quota, bonus_quota, invite_code, invited_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    # 如果有邀请人，新用户和邀请人各得一个永久次数
    bonus_quota = TaskConfig.INVITE_BONUS_QUOTA if inviter_id else 0
    
    user_id = await execute_insert(query, (
        user_data.username,
        user_data.email,
        password_hash,
        UserRole.USER.value,
        TaskConfig.DEFAULT_DAILY_QUOTA,
        bonus_quota,
        new_invite_code,
        inviter_id
    ))
    
    # 如果有邀请人，给邀请人增加永久次数
    if inviter_id:
        # 更新邀请人的 bonus_quota
        await execute_update(
            "UPDATE users SET bonus_quota = bonus_quota + %s WHERE id = %s",
            (TaskConfig.INVITE_BONUS_QUOTA, inviter_id)
        )
        
        # 记录邀请关系
        await execute_insert(
            "INSERT INTO invitations (inviter_id, invitee_id, invite_code, bonus_granted) VALUES (%s, %s, %s, %s)",
            (inviter_id, user_id, user_data.invite_code, True)
        )
    
    # 获取新创建的用户
    user = await get_user_by_id(user_id)
    
    # 生成 Token
    tokens = create_tokens_for_user(user)
    
    # 设置 Cookie
    set_auth_cookies(response, tokens)
    
    return TokenResponse(**tokens)


@router.post("/login", response_model=TokenResponse, summary="用户登录")
async def login(login_data: UserLogin, response: Response):
    """
    用户登录
    
    - **username**: 用户名
    - **password**: 密码
    
    成功后会自动设置认证 Cookie（30天有效期）
    """
    # 查找用户
    user = await get_user_by_username(login_data.username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    # 验证密码
    if not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    # 生成 Token
    tokens = create_tokens_for_user(user)
    
    # 设置 Cookie
    set_auth_cookies(response, tokens)
    
    return TokenResponse(**tokens)


@router.post("/refresh", response_model=TokenResponse, summary="刷新 Token")
async def refresh_token(refresh_token: str, response: Response):
    """
    使用刷新令牌获取新的访问令牌
    
    - **refresh_token**: 刷新令牌
    
    成功后会自动更新认证 Cookie
    """
    # 验证刷新令牌
    payload = verify_token(refresh_token, "refresh")
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌"
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌"
        )
    
    # 获取用户
    user = await get_user_by_id(int(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在"
        )
    
    # 生成新的 Token
    tokens = create_tokens_for_user(user)
    
    # 更新 Cookie
    set_auth_cookies(response, tokens)
    
    return TokenResponse(**tokens)


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
async def get_me(current_user: User = Depends(get_current_user)):
    """
    获取当前登录用户的信息
    """
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role.value,
        is_admin=current_user.is_admin,
        daily_quota=current_user.daily_quota,
        bonus_quota=current_user.bonus_quota,
        invite_code=current_user.invite_code,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None
    )


@router.post("/logout", summary="用户登出")
async def logout(response: Response, current_user: User = Depends(get_current_user)):
    """
    用户登出
    
    会清除认证 Cookie。
    """
    clear_auth_cookies(response)
    return {"message": "登出成功"}


@router.post("/change-password", summary="修改密码")
async def change_password(
    old_password: str,
    new_password: str,
    current_user: User = Depends(get_current_user)
):
    """
    修改密码
    
    - **old_password**: 旧密码
    - **new_password**: 新密码 (至少6位)
    """
    # 验证旧密码
    if not verify_password(old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码错误"
        )
    
    # 验证新密码长度
    if len(new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码至少需要6位"
        )
    
    # 更新密码
    new_password_hash = get_password_hash(new_password)
    await execute_update(
        "UPDATE users SET password_hash = %s WHERE id = %s",
        (new_password_hash, current_user.id)
    )
    
    return {"message": "密码修改成功"}