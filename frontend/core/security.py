"""
SurveyGraph Frontend - 安全模块
================================

JWT 认证、密码哈希、权限验证等安全相关功能。
"""

from datetime import datetime, timedelta
from typing import Optional, Union
import secrets
import string

from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status, Request, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import JWTConfig
from core.database import execute_query
from core.models import User, UserRole

# Bearer Token 认证
security = HTTPBearer(auto_error=False)


def get_password_hash(password: str) -> str:
    """
    生成密码哈希
    
    直接使用 bcrypt 库,绕过 passlib 的兼容性问题。
    
    Args:
        password: 明文密码
        
    Returns:
        str: 密码哈希
    """
    # 将密码编码为字节
    password_bytes = password.encode('utf-8')
    # 生成盐并哈希
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码
    
    直接使用 bcrypt 库,绕过 passlib 的兼容性问题。
    
    Args:
        plain_password: 明文密码
        hashed_password: 密码哈希
        
    Returns:
        bool: 是否匹配
    """
    try:
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    创建访问令牌
    
    Args:
        data: 要编码的数据
        expires_delta: 过期时间增量
        
    Returns:
        str: JWT 令牌
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=JWTConfig.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        JWTConfig.SECRET_KEY,
        algorithm=JWTConfig.ALGORITHM
    )
    
    return encoded_jwt


def create_refresh_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    创建刷新令牌
    
    Args:
        data: 要编码的数据
        expires_delta: 过期时间增量
        
    Returns:
        str: JWT 刷新令牌
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=JWTConfig.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "type": "refresh"
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        JWTConfig.SECRET_KEY,
        algorithm=JWTConfig.ALGORITHM
    )
    
    return encoded_jwt


def verify_token(token: str, token_type: str = "access") -> Optional[dict]:
    """
    验证令牌
    
    Args:
        token: JWT 令牌
        token_type: 令牌类型 ("access" 或 "refresh")
        
    Returns:
        dict: 解码后的数据，验证失败返回 None
    """
    try:
        payload = jwt.decode(
            token,
            JWTConfig.SECRET_KEY,
            algorithms=[JWTConfig.ALGORITHM]
        )
        
        # 检查令牌类型
        if payload.get("type") != token_type:
            return None
        
        return payload
    except JWTError:
        return None


def generate_invite_code(length: int = 8) -> str:
    """
    生成邀请码
    
    Args:
        length: 邀请码长度
        
    Returns:
        str: 邀请码
    """
    # 使用大写字母和数字，排除容易混淆的字符
    alphabet = string.ascii_uppercase + string.digits
    alphabet = alphabet.replace('O', '').replace('0', '').replace('I', '').replace('1', '').replace('L', '')
    
    return ''.join(secrets.choice(alphabet) for _ in range(length))


async def get_user_by_id(user_id: int) -> Optional[User]:
    """
    根据 ID 获取用户
    
    Args:
        user_id: 用户 ID
        
    Returns:
        User: 用户对象，不存在返回 None
    """
    query = "SELECT * FROM users WHERE id = %s"
    result = await execute_query(query, (user_id,), fetch_one=True)
    return User.from_dict(result) if result else None


async def get_user_by_username(username: str) -> Optional[User]:
    """
    根据用户名获取用户
    
    Args:
        username: 用户名
        
    Returns:
        User: 用户对象，不存在返回 None
    """
    query = "SELECT * FROM users WHERE username = %s"
    result = await execute_query(query, (username,), fetch_one=True)
    return User.from_dict(result) if result else None


async def get_user_by_email(email: str) -> Optional[User]:
    """
    根据邮箱获取用户
    
    Args:
        email: 邮箱
        
    Returns:
        User: 用户对象，不存在返回 None
    """
    query = "SELECT * FROM users WHERE email = %s"
    result = await execute_query(query, (email,), fetch_one=True)
    return User.from_dict(result) if result else None


async def get_user_by_invite_code(invite_code: str) -> Optional[User]:
    """
    根据邀请码获取用户
    
    Args:
        invite_code: 邀请码
        
    Returns:
        User: 用户对象，不存在返回 None
    """
    query = "SELECT * FROM users WHERE invite_code = %s"
    result = await execute_query(query, (invite_code,), fetch_one=True)
    return User.from_dict(result) if result else None


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    access_token: Optional[str] = Cookie(None)
) -> User:
    """
    获取当前登录用户（依赖注入）
    
    支持两种认证方式：
    1. HTTP Bearer Token (Authorization header)
    2. Cookie (access_token)
    
    Args:
        request: FastAPI Request 对象
        credentials: HTTP Bearer 认证凭据
        access_token: Cookie 中的访问令牌
        
    Returns:
        User: 当前用户
        
    Raises:
        HTTPException: 认证失败
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = None
    
    # 优先使用 Bearer Token
    if credentials is not None:
        token = credentials.credentials
    # 其次使用 Cookie
    elif access_token:
        token = access_token
    
    if token is None:
        raise credentials_exception
    
    payload = verify_token(token, "access")
    
    if payload is None:
        raise credentials_exception
    
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    user = await get_user_by_id(int(user_id))
    if user is None:
        raise credentials_exception
    
    return user


async def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    access_token: Optional[str] = Cookie(None)
) -> Optional[User]:
    """
    获取当前登录用户（可选，不强制要求登录）
    
    支持两种认证方式：
    1. HTTP Bearer Token (Authorization header)
    2. Cookie (access_token)
    
    Args:
        request: FastAPI Request 对象
        credentials: HTTP Bearer 认证凭据
        access_token: Cookie 中的访问令牌
        
    Returns:
        User: 当前用户，未登录返回 None
    """
    token = None
    
    # 优先使用 Bearer Token
    if credentials is not None:
        token = credentials.credentials
    # 其次使用 Cookie
    elif access_token:
        token = access_token
    
    if token is None:
        return None
    
    try:
        payload = verify_token(token, "access")
        if payload is None:
            return None
        
        user_id = payload.get("sub")
        if user_id is None:
            return None
        
        return await get_user_by_id(int(user_id))
    except Exception:
        return None


async def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    获取当前管理员用户（依赖注入）
    
    Args:
        current_user: 当前用户
        
    Returns:
        User: 当前管理员用户
        
    Raises:
        HTTPException: 非管理员
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    
    return current_user


def create_tokens_for_user(user: User) -> dict:
    """
    为用户创建访问令牌和刷新令牌
    
    Args:
        user: 用户对象
        
    Returns:
        dict: 包含 access_token, refresh_token, token_type, expires_in
    """
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role": user.role.value}
    )
    
    refresh_token = create_refresh_token(
        data={"sub": str(user.id)}
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": JWTConfig.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # 秒
    }