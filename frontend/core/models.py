"""
SurveyGraph Frontend - 数据模型
================================

定义用户、任务、日志等数据模型。
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum
import json


class UserRole(str, Enum):
    """用户角色"""
    USER = "user"
    ADMIN = "admin"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class LogLevel(str, Enum):
    """日志级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    DEBUG = "debug"


@dataclass
class User:
    """用户模型"""
    id: int
    username: str
    email: str
    password_hash: str
    role: UserRole = UserRole.USER
    daily_quota: int = 1
    bonus_quota: int = 0
    invite_code: Optional[str] = None
    invited_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "User":
        """从字典创建用户对象"""
        if data is None:
            return None
        return cls(
            id=data.get("id"),
            username=data.get("username"),
            email=data.get("email"),
            password_hash=data.get("password_hash"),
            role=UserRole(data.get("role", "user")),
            daily_quota=data.get("daily_quota", 1),
            bonus_quota=data.get("bonus_quota", 0),
            invite_code=data.get("invite_code"),
            invited_by=data.get("invited_by"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )
    
    def to_dict(self, exclude_password: bool = True) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role.value,
            "daily_quota": self.daily_quota,
            "bonus_quota": self.bonus_quota,
            "invite_code": self.invite_code,
            "invited_by": self.invited_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if not exclude_password:
            result["password_hash"] = self.password_hash
        return result
    
    @property
    def total_quota(self) -> int:
        """总配额 = 每日配额 + 永久奖励配额"""
        return self.daily_quota + self.bonus_quota
    
    @property
    def is_admin(self) -> bool:
        """是否是管理员"""
        return self.role == UserRole.ADMIN


@dataclass
class Task:
    """任务模型"""
    id: int
    task_id: str
    user_id: int
    topic: str
    keywords: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    current_step: int = 0
    current_step_name: Optional[str] = None
    progress_percent: int = 0
    config: Optional[Dict[str, Any]] = None
    uploaded_files: Optional[List[Dict[str, str]]] = None
    enable_arxiv_search: bool = True
    output_dir: Optional[str] = None
    mekg_data_path: Optional[str] = None
    outline_path: Optional[str] = None
    pdf_path: Optional[str] = None
    evaluation_path: Optional[str] = None
    visualization_path: Optional[str] = None
    papers_count: int = 0
    relations_count: int = 0
    sections_count: int = 0
    retry_count: int = 0
    last_retry_date: Optional[date] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """从字典创建任务对象"""
        if data is None:
            return None
        
        # 解析 JSON 字段
        config = data.get("config")
        if isinstance(config, str):
            config = json.loads(config) if config else None
        
        uploaded_files = data.get("uploaded_files")
        if isinstance(uploaded_files, str):
            uploaded_files = json.loads(uploaded_files) if uploaded_files else None
        
        return cls(
            id=data.get("id"),
            task_id=data.get("task_id"),
            user_id=data.get("user_id"),
            topic=data.get("topic"),
            keywords=data.get("keywords"),
            status=TaskStatus(data.get("status", "pending")),
            current_step=data.get("current_step", 0),
            current_step_name=data.get("current_step_name"),
            progress_percent=data.get("progress_percent", 0),
            config=config,
            uploaded_files=uploaded_files,
            enable_arxiv_search=data.get("enable_arxiv_search", True),
            output_dir=data.get("output_dir"),
            mekg_data_path=data.get("mekg_data_path"),
            outline_path=data.get("outline_path"),
            pdf_path=data.get("pdf_path"),
            evaluation_path=data.get("evaluation_path"),
            visualization_path=data.get("visualization_path"),
            papers_count=data.get("papers_count", 0),
            relations_count=data.get("relations_count", 0),
            sections_count=data.get("sections_count", 0),
            retry_count=data.get("retry_count", 0),
            last_retry_date=data.get("last_retry_date"),
            error_message=data.get("error_message"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            completed_at=data.get("completed_at"),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "user_id": self.user_id,
            "topic": self.topic,
            "keywords": self.keywords,
            "status": self.status.value,
            "current_step": self.current_step,
            "current_step_name": self.current_step_name,
            "progress_percent": self.progress_percent,
            "config": self.config,
            "uploaded_files": self.uploaded_files,
            "enable_arxiv_search": self.enable_arxiv_search,
            "output_dir": self.output_dir,
            "mekg_data_path": self.mekg_data_path,
            "outline_path": self.outline_path,
            "pdf_path": self.pdf_path,
            "evaluation_path": self.evaluation_path,
            "visualization_path": self.visualization_path,
            "papers_count": self.papers_count,
            "relations_count": self.relations_count,
            "sections_count": self.sections_count,
            "retry_count": self.retry_count,
            "last_retry_date": self.last_retry_date.isoformat() if self.last_retry_date else None,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
    
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self.status == TaskStatus.RUNNING
    
    @property
    def is_completed(self) -> bool:
        """是否已完成"""
        return self.status == TaskStatus.COMPLETED
    
    @property
    def is_failed(self) -> bool:
        """是否失败"""
        return self.status == TaskStatus.FAILED
    
    @property
    def can_retry(self) -> bool:
        """是否可以重试"""
        from config import TaskConfig
        
        # 检查当日重试次数
        today = date.today()
        if self.last_retry_date == today:
            return self.retry_count < TaskConfig.MAX_RETRY_PER_DAY
        return True


@dataclass
class TaskLog:
    """任务日志模型"""
    id: int
    task_id: int
    step: int
    step_name: Optional[str] = None
    level: LogLevel = LogLevel.INFO
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskLog":
        """从字典创建日志对象"""
        if data is None:
            return None
        
        # 解析 JSON 字段
        details = data.get("details")
        if isinstance(details, str):
            details = json.loads(details) if details else None
        
        return cls(
            id=data.get("id"),
            task_id=data.get("task_id"),
            step=data.get("step", 0),
            step_name=data.get("step_name"),
            level=LogLevel(data.get("level", "info")),
            message=data.get("message"),
            details=details,
            created_at=data.get("created_at"),
        )
    
    def to_dict(self, include_details: bool = True) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "id": self.id,
            "task_id": self.task_id,
            "step": self.step,
            "step_name": self.step_name,
            "level": self.level.value,
            "message": self.message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_details:
            result["details"] = self.details
        return result


@dataclass
class Invitation:
    """邀请记录模型"""
    id: int
    inviter_id: int
    invitee_id: int
    invite_code: str
    bonus_granted: bool = False
    created_at: Optional[datetime] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Invitation":
        """从字典创建邀请记录对象"""
        if data is None:
            return None
        return cls(
            id=data.get("id"),
            inviter_id=data.get("inviter_id"),
            invitee_id=data.get("invitee_id"),
            invite_code=data.get("invite_code"),
            bonus_granted=data.get("bonus_granted", False),
            created_at=data.get("created_at"),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "inviter_id": self.inviter_id,
            "invitee_id": self.invitee_id,
            "invite_code": self.invite_code,
            "bonus_granted": self.bonus_granted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# Pydantic 模型用于 API 请求/响应验证
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List


class UserCreate(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    invite_code: Optional[str] = Field(None, max_length=20)


class UserLogin(BaseModel):
    """用户登录请求"""
    username: str
    password: str


class UserResponse(BaseModel):
    """用户响应"""
    id: int
    username: str
    email: str
    role: str
    is_admin: bool = False  # 是否是管理员
    daily_quota: int
    bonus_quota: int
    invite_code: Optional[str]
    created_at: Optional[str]


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TaskCreate(BaseModel):
    """创建任务请求"""
    topic: str = Field(..., min_length=1, max_length=500)
    keywords: Optional[str] = None
    enable_arxiv_search: bool = True
    config: Optional[Dict[str, Any]] = None


class TaskUpdate(BaseModel):
    """更新任务请求"""
    topic: Optional[str] = None
    keywords: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class TaskResponse(BaseModel):
    """任务响应"""
    id: int
    task_id: str
    user_id: int
    topic: str
    keywords: Optional[str]
    status: str
    current_step: int
    current_step_name: Optional[str]
    progress_percent: int
    papers_count: int
    relations_count: int
    sections_count: int
    error_message: Optional[str]
    config: Optional[Dict[str, Any]] = None
    created_at: Optional[str]
    updated_at: Optional[str]
    completed_at: Optional[str]


class TaskLogResponse(BaseModel):
    """任务日志响应"""
    id: int
    task_id: int
    step: int
    step_name: Optional[str]
    level: str
    message: Optional[str]
    created_at: Optional[str]


class OutlineSection(BaseModel):
    """大纲章节"""
    number: str
    title: str
    description: Optional[str] = None
    level: int = 1
    subsections: Optional[List["OutlineSection"]] = None


class OutlineUpdate(BaseModel):
    """更新大纲请求"""
    title: str
    sections: List[OutlineSection]


class RetryRequest(BaseModel):
    """重试请求"""
    from_step: Optional[int] = None  # 从哪个步骤开始重试，None 表示从失败处继续


class QuotaResponse(BaseModel):
    """配额响应"""
    daily_quota: int
    bonus_quota: int
    total_quota: int
    used_today: int
    remaining_today: int


class InviteCodeResponse(BaseModel):
    """邀请码响应"""
    invite_code: str
    invite_url: str
    invited_count: int


# 允许 OutlineSection 自引用
OutlineSection.model_rebuild()