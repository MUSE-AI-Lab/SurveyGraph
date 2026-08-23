"""
SurveyGraph Frontend - 任务 API
================================

任务创建、查询、控制、结果获取等接口。
"""

from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Query
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel
from datetime import date, datetime
from typing import List, Optional, Dict, Tuple, Any
from dataclasses import dataclass, field
import json
import os
import uuid
import aiofiles

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import TaskConfig, AppConfig, PROJECT_ROOT
from core.database import execute_query, execute_insert, execute_update
from core.models import (
    User, Task, TaskStatus, TaskLog, LogLevel,
    TaskCreate, TaskUpdate, TaskResponse, TaskLogResponse,
    OutlineUpdate, RetryRequest
)
from core.security import get_current_user, get_current_user_optional

router = APIRouter()


# ==========================================
# 关键词生成请求模型
# ==========================================

class GenerateKeywordsRequest(BaseModel):
    topic: str


# ==========================================
# 关键词生成 API
# ==========================================

@router.post("/generate-keywords", summary="生成关键词")
async def generate_keywords(
    request: GenerateKeywordsRequest,
    current_user: User = Depends(get_current_user)
):
    """
    根据研究主题自动生成相关关键词
    
    - **topic**: 研究主题 (必填)
    
    返回关键词列表，每个关键词包含文本和建议权重
    """
    topic = request.topic.strip()
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请提供研究主题"
        )
    
    try:
        # 尝试使用 LLM 生成关键词
        keywords = await generate_keywords_with_llm(topic)
        return {"keywords": keywords}
    except Exception as e:
        # 如果 LLM 调用失败，使用简单的关键词提取
        keywords = extract_simple_keywords(topic)
        return {"keywords": keywords, "fallback": True}


async def generate_keywords_with_llm(topic: str) -> List[Dict[str, Any]]:
    """
    使用 LLM 生成关键词
    """
    try:
        # 尝试导入 ChatAgent
        from src.models.LLM import ChatAgent
        from src.configs.config import DEFAULT_CHATAGENT_MODEL
        
        agent = ChatAgent()
        
        prompt = f"""You are an expert in academic research. Given the research topic below, generate 5-8 relevant keywords that would be useful for literature search.

Research Topic: {topic}

Requirements:
1. Keywords should be specific academic terms, not generic words
2. Include the main topic as the first keyword with weight 1.0
3. Include related concepts, methods, and applications
4. Each keyword should be a meaningful phrase (2-4 words preferred)
5. Avoid single common words like "large", "model", "language" alone

For each keyword, also provide a relevance weight between 0.5 and 1.0 (1.0 being most relevant).

Return the result as a JSON array with objects containing "keyword" and "weight" fields.
Example format for topic "Large Language Model Function Calling":
[
  {{"keyword": "large language model function calling", "weight": 1.0}},
  {{"keyword": "tool use in LLMs", "weight": 0.95}},
  {{"keyword": "API integration with language models", "weight": 0.9}},
  {{"keyword": "LLM agents", "weight": 0.85}},
  {{"keyword": "function invocation", "weight": 0.8}},
  {{"keyword": "structured output generation", "weight": 0.75}}
]

Only return the JSON array, no other text."""

        # 使用正确的异步方法
        response = await agent.async_remote_chat(
            text_content=prompt,
            temperature=0.3,
            model=DEFAULT_CHATAGENT_MODEL,
            timeout=60
        )
        
        # 解析 JSON 响应
        import re
        # 尝试提取 JSON 数组
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            keywords_data = json.loads(json_match.group())
            # 验证格式
            result = []
            for item in keywords_data:
                if isinstance(item, dict) and "keyword" in item:
                    keyword = str(item["keyword"]).strip()
                    # 过滤掉太短或太通用的关键词
                    if len(keyword) >= 3 and keyword.lower() not in {'the', 'and', 'for', 'with'}:
                        result.append({
                            "keyword": keyword,
                            "weight": float(item.get("weight", 0.8))
                        })
            if result:
                return result
        
        # 如果解析失败，回退到简单提取
        raise ValueError("Failed to parse LLM response")
        
    except ImportError as e:
        # ChatAgent 不可用，使用简单提取
        raise ValueError(f"LLM not available: {e}")
    except Exception as e:
        raise ValueError(f"LLM error: {str(e)}")


def extract_simple_keywords(topic: str) -> List[Dict[str, Any]]:
    """
    简单的关键词提取（不使用 LLM）
    基于主题文本进行分词和提取
    """
    import re
    
    # 移除常见的停用词
    stop_words = {
        'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
        'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
        'about', 'into', 'through', 'during', 'before', 'after', 'above',
        'below', 'between', 'under', 'again', 'further', 'then', 'once',
        'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each',
        'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not',
        'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'using',
        'based', 'approach', 'method', 'methods', 'study', 'research', 'survey',
        'review', 'analysis', 'comprehensive', 'towards', 'via'
    }
    
    # 提取单词和短语
    words = re.findall(r'\b[a-zA-Z]{2,}\b', topic.lower())
    
    # 过滤停用词
    filtered_words = [w for w in words if w not in stop_words]
    
    # 提取可能的短语（连续的非停用词）
    phrases = []
    current_phrase = []
    for word in topic.lower().split():
        clean_word = re.sub(r'[^a-zA-Z]', '', word)
        if clean_word and clean_word not in stop_words:
            current_phrase.append(clean_word)
        else:
            if len(current_phrase) >= 2:
                phrases.append(' '.join(current_phrase))
            current_phrase = []
    if len(current_phrase) >= 2:
        phrases.append(' '.join(current_phrase))
    
    # 合并结果
    keywords = []
    seen = set()
    
    # 首先添加短语（权重更高）
    for phrase in phrases[:4]:
        if phrase not in seen:
            seen.add(phrase)
            keywords.append({"keyword": phrase, "weight": 0.9})
    
    # 然后添加单词
    for word in filtered_words:
        if word not in seen and len(keywords) < 8:
            seen.add(word)
            keywords.append({"keyword": word, "weight": 0.7})
    
    # 如果关键词太少，添加原始主题
    if len(keywords) < 3:
        keywords.insert(0, {"keyword": topic, "weight": 1.0})
    
    return keywords[:8]


# ==========================================
# 任务 CRUD
# ==========================================

@router.post("", response_model=TaskResponse, summary="创建新任务")
async def create_task(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_user)
):
    """
    创建新的综述生成任务
    
    - **topic**: 综述主题 (必填)
    - **keywords**: 关键词 (可选，逗号分隔)
    - **enable_arxiv_search**: 是否开启 arXiv 搜索 (默认开启)
    - **config**: 高级配置参数 (可选)
    """
    # 检查配额
    today = date.today()
    query = "SELECT COUNT(*) as count FROM tasks WHERE user_id = %s AND DATE(created_at) = %s"
    result = await execute_query(query, (current_user.id, today), fetch_one=True)
    used_today = result["count"] if result else 0
    
    total_quota = current_user.daily_quota + current_user.bonus_quota
    if used_today >= total_quota:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"今日配额已用完 ({used_today}/{total_quota})，请明天再试或邀请好友获取更多次数"
        )
    
    # 如果不开启 arXiv 搜索，检查是否有上传的文档
    # (这个检查在实际上传文件后进行)
    
    # 生成任务 ID（使用 UUID 避免重名）
    short_uuid = uuid.uuid4().hex[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_id = f"{timestamp}_{short_uuid}"
    
    # 合并配置
    config = TaskConfig.DEFAULT_PIPELINE_CONFIG.copy()
    if task_data.config:
        config.update(task_data.config)
    
    # 创建任务记录
    insert_query = """
        INSERT INTO tasks (
            task_id, user_id, topic, keywords, status, 
            current_step, current_step_name, progress_percent,
            config, enable_arxiv_search
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    db_id = await execute_insert(insert_query, (
        task_id,
        current_user.id,
        task_data.topic,
        task_data.keywords,
        TaskStatus.PENDING.value,
        0,
        "NOT_STARTED",
        0,
        json.dumps(config),
        task_data.enable_arxiv_search
    ))
    
    # 获取创建的任务
    task = await get_task_by_id(db_id)
    
    return task_to_response(task)


@router.get("", summary="获取任务列表")
async def list_tasks(
    status: Optional[str] = Query(None, description="按状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    all: bool = Query(False, description="是否查看所有用户的任务（仅管理员）"),
    search: Optional[str] = Query(None, description="搜索主题"),
    current_user: User = Depends(get_current_user)
):
    """
    获取任务列表
    
    - **status**: 按状态筛选 (pending/running/paused/completed/failed)
    - **page**: 页码
    - **page_size**: 每页数量
    - **all**: 是否查看所有用户的任务（仅管理员有效）
    - **search**: 搜索主题关键词
    """
    offset = (page - 1) * page_size
    
    # 构建查询
    where_clauses = []
    params = []
    
    # 如果不是管理员或者没有请求查看所有任务，只显示当前用户的任务
    if not current_user.is_admin or not all:
        where_clauses.append("t.user_id = %s")
        params.append(current_user.id)
    
    if status:
        where_clauses.append("t.status = %s")
        params.append(status)
    
    if search:
        where_clauses.append("t.topic LIKE %s")
        params.append(f"%{search}%")
    
    where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    # 查询总数
    count_query = f"SELECT COUNT(*) as count FROM tasks t {where_clause}"
    count_result = await execute_query(count_query, tuple(params), fetch_one=True)
    total = count_result["count"] if count_result else 0
    
    # 查询列表（如果是管理员查看所有任务，包含用户名）
    if current_user.is_admin and all:
        list_query = f"""
            SELECT t.*, u.username as owner_username
            FROM tasks t
            LEFT JOIN users u ON t.user_id = u.id
            {where_clause}
            ORDER BY t.created_at DESC
            LIMIT %s OFFSET %s
        """
    else:
        list_query = f"""
            SELECT t.*, NULL as owner_username
            FROM tasks t
            {where_clause}
            ORDER BY t.created_at DESC
            LIMIT %s OFFSET %s
        """
    params.extend([page_size, offset])
    results = await execute_query(list_query, tuple(params))
    
    tasks = []
    for row in results:
        task_response = task_to_response(Task.from_dict(row))
        # 添加任务所有者用户名（仅管理员查看所有任务时）
        if current_user.is_admin and all and row.get("owner_username"):
            task_response_dict = task_response.model_dump() if hasattr(task_response, 'model_dump') else task_response.__dict__
            task_response_dict["owner_username"] = row["owner_username"]
            tasks.append(task_response_dict)
        else:
            tasks.append(task_response)
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "tasks": tasks,
        "is_admin_view": current_user.is_admin and all
    }


@router.get("/{task_id}", response_model=TaskResponse, summary="获取任务详情")
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取指定任务的详细信息
    
    优先从 checkpoint.json 读取进度信息
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此任务"
        )
    
    # 从 checkpoint.json 读取进度信息并合并
    return await task_to_response_with_checkpoint(task)


@router.put("/{task_id}", summary="更新任务配置")
async def update_task(
    task_id: str,
    task_data: TaskUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    更新任务配置
    
    - **config**: 任务配置（包括暂停点等）
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作此任务"
        )
    
    # 检查状态 - 只有pending状态的任务可以修改配置
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法修改运行中任务的配置"
        )
    
    # 合并配置
    current_config = task.config or {}
    if task_data.config:
        current_config.update(task_data.config)
    
    # 更新任务
    await execute_update(
        "UPDATE tasks SET config = %s, updated_at = NOW() WHERE id = %s",
        (json.dumps(current_config), task.id)
    )
    
    # 获取更新后的任务
    updated_task = await get_task_by_id(task.id)
    
    return task_to_response(updated_task)


@router.delete("/{task_id}", summary="删除任务")
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    删除指定任务
    
    会自动终止正在运行的进程（如果有的话）
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权删除此任务"
        )
    
    # 如果任务正在运行，先强制终止进程
    from services.process_manager import process_manager
    
    if process_manager.is_task_running(task_id):
        # 强制终止进程
        await process_manager.stop_task(task_id, force=True)
    
    # 清理进程信息文件
    process_info = process_manager.get_process_info(task_id)
    if process_info:
        process_info.delete()
    
    # 删除任务日志
    await execute_update("DELETE FROM task_logs WHERE task_id = %s", (task.id,))
    
    # 删除任务
    await execute_update("DELETE FROM tasks WHERE id = %s", (task.id,))
    
    return {"message": "任务已删除，相关进程已终止"}


# ==========================================
# 任务控制
# ==========================================

@router.post("/{task_id}/start", summary="启动任务")
async def start_task(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    启动指定任务
    
    - 如果任务是 PENDING 状态，从头开始执行
    - 如果任务是 PAUSED 状态，从断点恢复执行
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作此任务"
        )
    
    # 检查状态
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="任务已在运行中"
        )
    
    if task.status == TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="任务已完成，如需重新生成请使用重试功能"
        )
    
    # 判断是否需要从断点恢复
    # PAUSED 状态或者 current_step > 0 表示任务之前已经执行过
    should_resume = task.status == TaskStatus.PAUSED or task.current_step > 0
    
    # 更新状态
    await execute_update(
        "UPDATE tasks SET status = %s, updated_at = NOW() WHERE id = %s",
        (TaskStatus.RUNNING.value, task.id)
    )
    
    # 启动 Pipeline (异步)
    from services.pipeline_service import start_pipeline
    await start_pipeline(task_id, resume=should_resume)
    
    return {"message": f"任务已{'从断点恢复' if should_resume else '启动'}"}


@router.post("/{task_id}/pause", summary="暂停任务")
async def pause_task(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    暂停指定任务
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作此任务"
        )
    
    # 检查状态
    if task.status != TaskStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能暂停运行中的任务"
        )
    
    # 更新状态
    await execute_update(
        "UPDATE tasks SET status = %s, updated_at = NOW() WHERE id = %s",
        (TaskStatus.PAUSED.value, task.id)
    )
    
    # 暂停 Pipeline
    from services.pipeline_service import pause_pipeline
    await pause_pipeline(task_id)
    
    return {"message": "任务已暂停"}


@router.post("/{task_id}/cancel", summary="取消任务")
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    取消指定任务
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作此任务"
        )
    
    # 更新状态
    await execute_update(
        "UPDATE tasks SET status = %s, error_message = %s, updated_at = NOW() WHERE id = %s",
        (TaskStatus.FAILED.value, "用户取消", task.id)
    )
    
    # 取消 Pipeline
    from services.pipeline_service import cancel_pipeline
    await cancel_pipeline(task_id)
    
    return {"message": "任务已取消"}


@router.post("/{task_id}/retry", summary="重试任务")
async def retry_task(
    task_id: str,
    retry_data: RetryRequest,
    current_user: User = Depends(get_current_user)
):
    """
    重试指定任务
    
    - **from_step**: 从哪个步骤开始重试 (可选，默认从失败处继续)
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作此任务"
        )
    
    # 检查重试次数
    today = date.today()
    if task.last_retry_date == today:
        if task.retry_count >= TaskConfig.MAX_RETRY_PER_DAY:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"今日重试次数已达上限 ({TaskConfig.MAX_RETRY_PER_DAY} 次)"
            )
        new_retry_count = task.retry_count + 1
    else:
        new_retry_count = 1
    
    # 确定从哪个步骤开始
    from_step = retry_data.from_step if retry_data.from_step is not None else task.current_step
    
    # 更新任务状态
    await execute_update(
        """UPDATE tasks SET 
            status = %s, 
            current_step = %s,
            retry_count = %s,
            last_retry_date = %s,
            error_message = NULL,
            updated_at = NOW()
        WHERE id = %s""",
        (TaskStatus.RUNNING.value, from_step, new_retry_count, today, task.id)
    )
    
    # 启动 Pipeline (从指定步骤)
    from services.pipeline_service import start_pipeline
    await start_pipeline(task_id, resume=True, from_step=from_step)
    
    return {
        "message": f"任务已从步骤 {from_step} 开始重试",
        "retry_count": new_retry_count,
        "max_retry": TaskConfig.MAX_RETRY_PER_DAY
    }


# ==========================================
# 任务日志
# ==========================================

@router.get("/{task_id}/logs", summary="获取任务日志")
async def get_task_logs(
    task_id: str,
    level: Optional[str] = Query(None, description="按级别筛选"),
    step: Optional[int] = Query(None, description="按步骤筛选"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量"),
    current_user: User = Depends(get_current_user)
):
    """
    获取任务日志
    
    - 普通用户只能看到简化日志 (info 级别)
    - 管理员可以看到所有级别的详细日志
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此任务"
        )
    
    # 构建查询
    where_clause = "WHERE task_id = %s"
    params = [task.id]
    
    # 普通用户不返回详细日志列表，只返回空列表
    # 前端会根据任务状态显示简化的进度信息
    if not current_user.is_admin:
        return {
            "total": 0,
            "logs": []
        }
    
    if level:
        where_clause += " AND level = %s"
        params.append(level)
    
    if step is not None:
        where_clause += " AND step = %s"
        params.append(step)
    
    query = f"""
        SELECT * FROM task_logs {where_clause}
        ORDER BY created_at DESC
        LIMIT %s
    """
    params.append(limit)
    
    results = await execute_query(query, tuple(params))
    
    logs = []
    for row in results:
        log = TaskLog.from_dict(row)
        # 普通用户不返回 details
        logs.append(log.to_dict(include_details=current_user.is_admin))
    
    return {
        "total": len(logs),
        "logs": logs
    }


@router.get("/{task_id}/progress", summary="获取任务进度")
async def get_task_progress(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取任务进度信息
    
    优先从 checkpoint.json 读取进度，如果不存在则从数据库读取。
    返回当前步骤、进度百分比、各步骤状态等
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此任务"
        )
    
    # 尝试从 checkpoint.json 读取进度信息
    checkpoint_data = None
    checkpoint_path = PROJECT_ROOT / "outputs" / task_id / "checkpoint.json"
    if checkpoint_path.exists():
        try:
            async with aiofiles.open(checkpoint_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                checkpoint_data = json.loads(content)
        except Exception:
            pass
    
    # 使用 checkpoint 数据覆盖数据库中的进度信息
    current_step = task.current_step
    current_step_name = task.current_step_name
    papers_count = task.papers_count
    relations_count = task.relations_count
    sections_count = task.sections_count
    task_status = task.status  # 默认使用数据库中的状态
    
    if checkpoint_data:
        current_step = checkpoint_data.get("step", current_step)
        current_step_name = checkpoint_data.get("step_name", current_step_name)
        papers_count = checkpoint_data.get("papers_count", papers_count)
        relations_count = checkpoint_data.get("relations_count", relations_count)
        sections_count = checkpoint_data.get("sections_count", sections_count)
        
        # 根据 checkpoint 中的 step_name 更新状态
        # checkpoint 是任务进度的真实来源，应该优先使用 checkpoint 的状态
        checkpoint_step_name = checkpoint_data.get("step_name", "")
        
        if checkpoint_step_name == "COMPLETED" or current_step >= 11:
            # checkpoint 显示已完成
            task_status = TaskStatus.COMPLETED
        elif checkpoint_step_name == "FAILED":
            # checkpoint 显示失败
            task_status = TaskStatus.FAILED
        elif current_step > 0 and current_step < 11:
            # checkpoint 显示任务正在进行中（step 在 1-10 之间）
            if task.status == TaskStatus.PAUSED:
                task_status = TaskStatus.PAUSED
            elif task.status == TaskStatus.RUNNING:
                task_status = TaskStatus.RUNNING
            elif task.status.value in ["completed", "failed", "cancelled"]:
                # 数据库状态与 checkpoint 不一致，以 checkpoint 为准
                task_status = TaskStatus.RUNNING
            else:
                task_status = task.status
    
    # 计算进度百分比 (基于步骤数，总共11步，0-10为执行步骤，11为完成)
    if current_step >= 11:
        progress_percent = 100
    else:
        progress_percent = int((current_step / 11) * 100)
    
    # 构建步骤状态
    steps = []
    for step_num, step_info in TaskConfig.PIPELINE_STEPS.items():
        step_status = "pending"
        if step_num < current_step:
            step_status = "completed"
        elif step_num == current_step:
            if task_status == TaskStatus.RUNNING:
                step_status = "running"
            elif task_status == TaskStatus.FAILED:
                step_status = "failed"
            elif task_status == TaskStatus.COMPLETED or current_step >= 11:
                step_status = "completed"
            else:
                step_status = "pending"
        
        steps.append({
            "step": step_num,
            "name": step_info["name"],
            "label": step_info["label"],
            "description": step_info["description"],
            "status": step_status
        })
    
    # 获取进程状态（如果任务正在运行）
    process_info = None
    if task.status == TaskStatus.RUNNING:
        try:
            from services.process_manager import process_manager
            pinfo = process_manager.get_process_info(task_id)
            if pinfo:
                process_info = {
                    "pid": pinfo.pid,
                    "status": pinfo.status,
                    "started_at": pinfo.started_at,
                    "is_running": process_manager.is_task_running(task_id)
                }
        except Exception:
            pass
    
    return {
        "task_id": task.task_id,
        "status": task_status.value if hasattr(task_status, 'value') else task_status,
        "current_step": current_step,
        "current_step_name": current_step_name,
        "progress_percent": progress_percent,
        "papers_count": papers_count,
        "relations_count": relations_count,
        "sections_count": sections_count,
        "error_message": task.error_message,
        "steps": steps,
        "process": process_info,
        "checkpoint_source": "file" if checkpoint_data else "database"
    }


@router.get("/{task_id}/results", summary="获取任务结果")
async def get_task_results(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取任务的所有结果数据
    
    包括 PDF URL、Markdown 内容、知识图谱数据、评估报告等
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此任务"
        )
    
    results = {
        "task_id": task.task_id,
        "topic": task.topic,
        "status": task.status.value,
    }
    
    task_dir = PROJECT_ROOT / "outputs" / task.task_id
    
    # PDF URL
    pdf_path = task_dir / "survey.pdf"
    if not pdf_path.exists():
        pdf_path = task_dir / "survey_wtmk.pdf"
    if pdf_path.exists():
        results["pdf_url"] = f"/api/tasks/{task_id}/pdf"
    
    # Markdown 内容
    latex_path = task_dir / "latex" / "survey.tex"
    if latex_path.exists():
        try:
            with open(latex_path, 'r', encoding='utf-8') as f:
                latex_content = f.read()
            results["markdown_content"] = latex_to_markdown(latex_content)
        except Exception:
            pass
    
    # MEKG 数据
    mekg_path = task_dir / "mekg" / "mekg_data.json"
    if mekg_path.exists():
        try:
            with open(mekg_path, 'r', encoding='utf-8') as f:
                raw_mekg_data = json.load(f)
            # 转换为前端期望的格式
            results["mekg_data"] = convert_mekg_to_frontend_format(raw_mekg_data)
        except Exception:
            pass
    
    # 评估报告 - 优先使用双语 HTML 报告
    eval_dir = task_dir / "evaluation"
    
    # 检查中文 HTML 报告
    eval_zh_path = eval_dir / "evaluation_report_zh.html"
    if eval_zh_path.exists():
        results["evaluation_report_zh_url"] = f"/api/tasks/{task_id}/evaluation/zh"
    
    # 检查英文 HTML 报告
    eval_en_path = eval_dir / "evaluation_report_en.html"
    if eval_en_path.exists():
        results["evaluation_report_en_url"] = f"/api/tasks/{task_id}/evaluation/en"
    
    # 回退到 Markdown 格式（如果没有 HTML 报告）
    if "evaluation_report_zh_url" not in results and "evaluation_report_en_url" not in results:
        eval_path = task_dir / "evaluation_report.md"
        if not eval_path.exists():
            eval_path = eval_dir / "evaluation_report.md"
        if eval_path.exists():
            try:
                with open(eval_path, 'r', encoding='utf-8') as f:
                    results["evaluation_report"] = f.read()
            except Exception:
                pass
    
    # 可视化数据
    vis_path = task_dir / "visualization_data.json"
    if vis_path.exists():
        try:
            with open(vis_path, 'r', encoding='utf-8') as f:
                results["visualization_data"] = json.load(f)
        except Exception:
            pass
    
    return results


# ==========================================
# 大纲管理
# ==========================================

@router.get("/{task_id}/outline", summary="获取大纲")
async def get_outline(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取任务的大纲
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此任务"
        )
    
    # 检查大纲文件是否存在
    outline_path = PROJECT_ROOT / "outputs" / task.task_id / "outline.json"
    if not outline_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="大纲尚未生成"
        )
    
    async with aiofiles.open(outline_path, 'r', encoding='utf-8') as f:
        content = await f.read()
        outline = json.loads(content)
    
    return outline


@router.put("/{task_id}/outline", summary="更新大纲")
async def update_outline(
    task_id: str,
    outline_data: OutlineUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    更新任务的大纲
    
    更新后可以从大纲生成步骤重新开始
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作此任务"
        )
    
    # 检查状态
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法修改运行中任务的大纲"
        )
    
    # 保存大纲
    outline_path = PROJECT_ROOT / "outputs" / task.task_id / "outline.json"
    outline_path.parent.mkdir(parents=True, exist_ok=True)
    
    outline_dict = {
        "title": outline_data.title,
        "topic": task.topic,
        "sections": [s.model_dump() for s in outline_data.sections]
    }
    
    async with aiofiles.open(outline_path, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(outline_dict, ensure_ascii=False, indent=2))
    
    # 同时更新 SurveyX 格式的大纲
    surveyx_outline = convert_to_surveyx_outline(outline_dict)
    surveyx_path = PROJECT_ROOT / "outputs" / task.task_id / "outlines.json"
    
    async with aiofiles.open(surveyx_path, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(surveyx_outline, ensure_ascii=False, indent=2))
    
    return {"message": "大纲已更新"}


# ==========================================
# 结果获取
# ==========================================

@router.get("/{task_id}/mekg", summary="获取知识图谱数据")
async def get_mekg_data(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取任务的 MEKG 知识图谱数据
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此任务"
        )
    
    # 读取 MEKG 数据
    mekg_path = PROJECT_ROOT / "outputs" / task.task_id / "mekg" / "mekg_data.json"
    if not mekg_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识图谱数据尚未生成"
        )
    
    async with aiofiles.open(mekg_path, 'r', encoding='utf-8') as f:
        content = await f.read()
        mekg_data = json.loads(content)
    
    return mekg_data


@router.get("/{task_id}/visualization", summary="获取可视化数据")
async def get_visualization_data(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取任务的可视化数据
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此任务"
        )
    
    # 读取可视化数据
    vis_path = PROJECT_ROOT / "outputs" / task.task_id / "visualization_data.json"
    if not vis_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="可视化数据尚未生成"
        )
    
    async with aiofiles.open(vis_path, 'r', encoding='utf-8') as f:
        content = await f.read()
        vis_data = json.loads(content)
    
    return vis_data


@router.get("/{task_id}/hierarchy_visualization", response_class=HTMLResponse, summary="获取层级可视化")
async def get_hierarchy_visualization(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取任务的层级可视化页面
    
    认证方式支持：
    1. HTTP Bearer Token (Authorization header)
    2. Cookie (access_token) - 适用于新标签页打开
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此任务"
        )
    
    # 读取 MEKG 数据
    mekg_path = PROJECT_ROOT / "outputs" / task.task_id / "mekg" / "mekg_data.json"
    if not mekg_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识图谱数据尚未生成"
        )
    
    async with aiofiles.open(mekg_path, 'r', encoding='utf-8') as f:
        content = await f.read()
        mekg_data = json.loads(content)
    
    # 使用新的列表式布局引擎 (复刻 visualization_server.py)
    layout_engine = ListLayoutEngine()
    nodes_data = layout_engine.build_nodes(mekg_data)
    
    # 提取关系数据
    edges_data = []
    relations = mekg_data.get("relations", [])
    
    # 建立节点ID集合用于过滤
    node_ids = set(n['id'] for n in nodes_data)
    
    # 节点ID映射 (处理可能的ID不一致)
    # visualization_server.py 中构建节点ID时做了一些替换，这里需要保持一致
    # 但由于我们直接在 build_nodes 中生成了 ID，所以关系数据中的 ID 需要尝试匹配
    
    # 简单的 ID 规范化函数
    def normalize_id(raw_id):
        return raw_id # 暂时假设 ID 是一致的，如果不一致需要在 ListLayoutEngine 中处理
        
    for rel in relations:
        source = rel.get('source') or rel.get('from')
        target = rel.get('target') or rel.get('to')
        
        # 尝试找到对应的节点 ID
        # 在 ListLayoutEngine 中，paper ID 保持原样，但 category/subcategory ID 重新生成了
        # 关系通常是 paper-paper 之间的，所以应该能直接匹配
        
        if source in node_ids and target in node_ids:
            edges_data.append({
                'source': source,
                'target': target,
                'type': rel.get('type', 'related'),
                'confidence': rel.get('confidence', 1.0),
                'evidence': rel.get('evidence', '')
            })
            
    # 构建层级边
    hierarchy_edges = []
    for node in nodes_data:
        if node.get('parentId'):
            hierarchy_edges.append({
                'source': node['parentId'],
                'target': node['id'],
                'type': 'hierarchy'
            })
            
    # 读取模板
    template_path = Path(__file__).parent.parent / "templates" / "hierarchy_template.html"
    if not template_path.exists():
        raise HTTPException(status_code=500, detail="可视化模板文件丢失")
        
    async with aiofiles.open(template_path, 'r', encoding='utf-8') as f:
        template = await f.read()
        
    # 替换数据
    html_content = template.replace('{{TITLE}}', f"{task.topic} - Hierarchy")
    html_content = html_content.replace('{{NODES_DATA}}', json.dumps(nodes_data, ensure_ascii=False))
    html_content = html_content.replace('{{EDGES_DATA}}', json.dumps(edges_data, ensure_ascii=False))
    html_content = html_content.replace('{{HIERARCHY_DATA}}', json.dumps(hierarchy_edges, ensure_ascii=False))
    
    return HTMLResponse(content=html_content)


@router.get("/{task_id}/pdf", summary="下载 PDF")
async def download_pdf(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    下载生成的 PDF 文件
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此任务"
        )
    
    # 查找 PDF 文件
    pdf_path = PROJECT_ROOT / "outputs" / task.task_id / "survey.pdf"
    if not pdf_path.exists():
        pdf_path = PROJECT_ROOT / "outputs" / task.task_id / "survey_wtmk.pdf"
    
    if not pdf_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF 文件尚未生成"
        )
    
    return FileResponse(
        path=str(pdf_path),
        filename=f"{task.topic[:50]}_survey.pdf",
        media_type="application/pdf"
    )


@router.get("/{task_id}/download", summary="下载任务结果包")
async def download_task_results(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    下载任务的所有结果文件（ZIP压缩包）
    包含：PDF、Markdown、LaTeX源码、知识图谱数据、评估报告等
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此任务"
        )
    
    task_dir = PROJECT_ROOT / "outputs" / task.task_id
    if not task_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务结果目录不存在"
        )
        
    # 创建临时 ZIP 文件
    import zipfile
    import io
    from fastapi.responses import StreamingResponse
    
    # 使用内存中的 ZIP 文件
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # 1. 添加 PDF
        pdf_path = task_dir / "survey.pdf"
        if not pdf_path.exists():
            pdf_path = task_dir / "survey_wtmk.pdf"
        if pdf_path.exists():
            zip_file.write(pdf_path, arcname="survey.pdf")
            
        # 2. 添加 Markdown
        # 尝试从 LaTeX 转换或直接读取 md 文件
        latex_path = task_dir / "latex" / "survey.tex"
        if latex_path.exists():
            try:
                with open(latex_path, 'r', encoding='utf-8') as f:
                    latex_content = f.read()
                md_content = latex_to_markdown(latex_content)
                zip_file.writestr("survey.md", md_content)
                # 也添加 LaTeX 源码
                zip_file.write(latex_path, arcname="source/survey.tex")
                # 添加参考文献
                bib_path = task_dir / "latex" / "references.bib"
                if bib_path.exists():
                    zip_file.write(bib_path, arcname="source/references.bib")
            except Exception:
                pass
                
        # 3. 添加评估报告
        eval_path = task_dir / "evaluation" / "evaluation_report.md"
        if not eval_path.exists():
            eval_path = task_dir / "evaluation_report.md"
        if eval_path.exists():
            zip_file.write(eval_path, arcname="evaluation_report.md")
            
        # 4. 添加 MEKG 数据
        mekg_path = task_dir / "mekg" / "mekg_data.json"
        if mekg_path.exists():
            zip_file.write(mekg_path, arcname="data/mekg_data.json")
            
        # 5. 添加可视化数据
        vis_path = task_dir / "visualization_data.json"
        if vis_path.exists():
            zip_file.write(vis_path, arcname="data/visualization_data.json")
            
        # 6. 添加生成的图片
        img_dir = task_dir / "ai_generated_images"
        if img_dir.exists():
            for img_file in img_dir.glob("*.png"):
                zip_file.write(img_file, arcname=f"images/{img_file.name}")
    
    # 重置指针位置
    zip_buffer.seek(0)
    
    # 返回流式响应
    filename = f"{task.topic[:30].replace(' ', '_')}_results.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/{task_id}/markdown", summary="获取 Markdown 内容")
async def get_markdown(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取生成的 Markdown 内容
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此任务"
        )
    
    # 读取 LaTeX 文件并转换为 Markdown (简化版)
    latex_path = PROJECT_ROOT / "outputs" / task.task_id / "latex" / "survey.tex"
    if not latex_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="内容尚未生成"
        )
    
    async with aiofiles.open(latex_path, 'r', encoding='utf-8') as f:
        latex_content = await f.read()
    
    # 简单的 LaTeX 到 Markdown 转换
    markdown_content = latex_to_markdown(latex_content)
    
    return {
        "content": markdown_content,
        "format": "markdown"
    }


@router.get("/{task_id}/evaluation", summary="获取评测报告")
async def get_evaluation(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取评测报告（Markdown 格式）
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此任务"
        )
    
    # 读取评测报告
    eval_path = PROJECT_ROOT / "outputs" / task.task_id / "evaluation_report.md"
    if not eval_path.exists():
        # 尝试读取 evaluation 目录下的报告
        eval_path = PROJECT_ROOT / "outputs" / task.task_id / "evaluation" / "evaluation_report.md"
    
    if not eval_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="评测报告尚未生成"
        )
    
    async with aiofiles.open(eval_path, 'r', encoding='utf-8') as f:
        content = await f.read()
    
    return {
        "content": content,
        "format": "markdown"
    }


@router.get("/{task_id}/evaluation/{lang}", response_class=HTMLResponse, summary="获取双语评测报告")
async def get_evaluation_html(
    task_id: str,
    lang: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取双语评测报告（HTML 格式）
    
    - **lang**: 语言选择，zh 为中文，en 为英文
    """
    if lang not in ['zh', 'en']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="语言参数无效，请使用 'zh' 或 'en'"
        )
    
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此任务"
        )
    
    # 读取对应语言的 HTML 报告
    eval_path = PROJECT_ROOT / "outputs" / task.task_id / "evaluation" / f"evaluation_report_{lang}.html"
    
    if not eval_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{'中文' if lang == 'zh' else '英文'}评测报告尚未生成"
        )
    
    async with aiofiles.open(eval_path, 'r', encoding='utf-8') as f:
        content = await f.read()
    
    return HTMLResponse(content=content)


# ==========================================
# 文件上传
# ==========================================

@router.post("/{task_id}/upload", summary="上传文档")
async def upload_file(
    task_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    为任务上传文档
    
    支持 PDF 和 Markdown 格式
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作此任务"
        )
    
    # 检查文件类型
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    
    if ext not in AppConfig.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型，允许的类型: {', '.join(AppConfig.ALLOWED_EXTENSIONS)}"
        )
    
    # 检查文件大小
    content = await file.read()
    if len(content) > AppConfig.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件过大，最大允许 {AppConfig.MAX_UPLOAD_SIZE // 1024 // 1024}MB"
        )
    
    # 保存文件到共享目录
    # 使用文件内容的哈希或文件名来避免重复
    # 这里简单使用文件名，如果文件名相同则覆盖（或者检查是否存在）
    
    # 确保共享目录存在
    AppConfig.ensure_dirs()
    shared_dir = AppConfig.SHARED_PDF_DIR
    
    # 如果是 PDF，保存到共享目录
    if ext == 'pdf':
        file_path = shared_dir / filename
        # 如果文件已存在，可以选择跳过或覆盖。这里选择覆盖以确保最新
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
    else:
        # 非 PDF 文件（如 md, txt）仍然保存到任务目录，或者也保存到共享目录？
        # 用户说 "把pdf和解析好的文本啥的都放在一个目录"
        # 所以全部保存到共享目录
        file_path = shared_dir / filename
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
    
    # 更新任务的上传文件列表
    uploaded_files = task.uploaded_files or []
    
    # 检查是否已经有同名文件，如果有则更新
    existing_index = -1
    for i, f in enumerate(uploaded_files):
        if f.get("filename") == filename:
            existing_index = i
            break
    
    file_info = {
        "filename": filename,
        "path": str(file_path),
        "type": ext,
        "size": len(content)
    }
    
    if existing_index >= 0:
        uploaded_files[existing_index] = file_info
    else:
        uploaded_files.append(file_info)
    
    await execute_update(
        "UPDATE tasks SET uploaded_files = %s, updated_at = NOW() WHERE id = %s",
        (json.dumps(uploaded_files), task.id)
    )
    
    return {
        "message": "文件上传成功",
        "filename": filename,
        "size": len(content)
    }


@router.delete("/{task_id}/upload/{filename}", summary="删除上传的文件")
async def delete_uploaded_file(
    task_id: str,
    filename: str,
    current_user: User = Depends(get_current_user)
):
    """
    删除已上传的文件
    """
    task = await get_task_by_task_id(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作此任务"
        )
    
    # 删除文件
    # 注意：如果是共享文件，删除可能会影响其他任务
    # 所以这里只从任务记录中移除，不物理删除文件
    # 或者检查是否有其他任务引用该文件（比较复杂）
    # 暂时策略：不物理删除共享文件
    
    # file_path = AppConfig.SHARED_PDF_DIR / filename
    # if file_path.exists():
    #     os.remove(file_path)
    
    # 更新任务的上传文件列表
    uploaded_files = task.uploaded_files or []
    uploaded_files = [f for f in uploaded_files if f.get("filename") != filename]
    
    await execute_update(
        "UPDATE tasks SET uploaded_files = %s, updated_at = NOW() WHERE id = %s",
        (json.dumps(uploaded_files), task.id)
    )
    
    return {"message": "文件已删除"}


# ==========================================
# 辅助函数
# ==========================================

async def get_task_by_id(task_db_id: int) -> Optional[Task]:
    """根据数据库 ID 获取任务"""
    query = "SELECT * FROM tasks WHERE id = %s"
    result = await execute_query(query, (task_db_id,), fetch_one=True)
    return Task.from_dict(result) if result else None


async def get_task_by_task_id(task_id: str) -> Optional[Task]:
    """根据任务 ID 获取任务"""
    query = "SELECT * FROM tasks WHERE task_id = %s"
    result = await execute_query(query, (task_id,), fetch_one=True)
    return Task.from_dict(result) if result else None


def task_to_response(task: Task) -> TaskResponse:
    """将 Task 对象转换为 TaskResponse（不读取 checkpoint）"""
    return TaskResponse(
        id=task.id,
        task_id=task.task_id,
        user_id=task.user_id,
        topic=task.topic,
        keywords=task.keywords,
        status=task.status.value,
        current_step=task.current_step,
        current_step_name=task.current_step_name,
        progress_percent=task.progress_percent,
        papers_count=task.papers_count,
        relations_count=task.relations_count,
        sections_count=task.sections_count,
        error_message=task.error_message,
        config=task.config,
        created_at=task.created_at.isoformat() if task.created_at else None,
        updated_at=task.updated_at.isoformat() if task.updated_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None
    )


async def read_checkpoint_data(task_id: str) -> Optional[Dict[str, Any]]:
    """读取 checkpoint.json 文件中的进度数据"""
    checkpoint_path = PROJECT_ROOT / "outputs" / task_id / "checkpoint.json"
    if checkpoint_path.exists():
        try:
            async with aiofiles.open(checkpoint_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except Exception:
            pass
    return None


async def task_to_response_with_checkpoint(task: Task) -> TaskResponse:
    """
    将 Task 对象转换为 TaskResponse，优先使用 checkpoint.json 中的进度数据
    """
    # 尝试读取 checkpoint 数据
    checkpoint_data = await read_checkpoint_data(task.task_id)
    
    # 使用 checkpoint 数据覆盖数据库中的进度信息
    current_step = task.current_step
    current_step_name = task.current_step_name
    papers_count = task.papers_count
    relations_count = task.relations_count
    sections_count = task.sections_count
    status = task.status.value  # 默认使用数据库中的状态
    
    if checkpoint_data:
        current_step = checkpoint_data.get("step", current_step)
        current_step_name = checkpoint_data.get("step_name", current_step_name)
        papers_count = checkpoint_data.get("papers_count", papers_count)
        relations_count = checkpoint_data.get("relations_count", relations_count)
        sections_count = checkpoint_data.get("sections_count", sections_count)
        
        # 根据 checkpoint 中的 step_name 更新状态
        # checkpoint 是任务进度的真实来源，应该优先使用 checkpoint 的状态
        checkpoint_step_name = checkpoint_data.get("step_name", "")
        
        if checkpoint_step_name == "COMPLETED" or current_step >= 11:
            # checkpoint 显示已完成
            status = "completed"
        elif checkpoint_step_name == "FAILED":
            # checkpoint 显示失败
            status = "failed"
        elif current_step > 0 and current_step < 11:
            # checkpoint 显示任务正在进行中（step 在 1-10 之间）
            # 即使数据库状态是 completed，也应该以 checkpoint 为准
            # 因为 checkpoint 是任务执行过程中实时更新的
            if task.status == TaskStatus.PAUSED:
                # 如果数据库显示暂停，保持暂停状态
                status = "paused"
            else:
                # 否则显示为运行中（或者根据数据库状态判断）
                # 如果数据库状态是 running，保持 running
                # 如果数据库状态是其他（如 completed 但 checkpoint 显示未完成），说明数据不一致
                # 此时以 checkpoint 为准，显示为 running
                if task.status == TaskStatus.RUNNING:
                    status = "running"
                elif task.status.value in ["completed", "failed", "cancelled"]:
                    # 数据库状态与 checkpoint 不一致，以 checkpoint 为准
                    # 任务可能被中断后重新运行，checkpoint 是最新状态
                    status = "running"
                else:
                    status = task.status.value
    
    # 计算进度百分比 (基于步骤数，总共11步，0-10为执行步骤，11为完成)
    if current_step >= 11:
        progress_percent = 100
    else:
        progress_percent = int((current_step / 11) * 100)
    
    return TaskResponse(
        id=task.id,
        task_id=task.task_id,
        user_id=task.user_id,
        topic=task.topic,
        keywords=task.keywords,
        status=status,
        current_step=current_step,
        current_step_name=current_step_name,
        progress_percent=progress_percent,
        papers_count=papers_count,
        relations_count=relations_count,
        sections_count=sections_count,
        error_message=task.error_message,
        config=task.config,
        created_at=task.created_at.isoformat() if task.created_at else None,
        updated_at=task.updated_at.isoformat() if task.updated_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None
    )


def convert_to_surveyx_outline(outline: dict) -> dict:
    """将大纲转换为 SurveyX 格式"""
    def convert_section(section: dict, level: int = 1) -> dict:
        result = {
            "title": section.get("title", ""),
            "description": section.get("description", ""),
        }
        
        subsections = section.get("subsections", [])
        if subsections:
            result["subsections"] = [
                convert_section(sub, level + 1) for sub in subsections
            ]
        
        return result
    
    return {
        "title": outline.get("title", ""),
        "sections": [convert_section(s) for s in outline.get("sections", [])]
    }


def convert_mekg_to_frontend_format(raw_data: dict) -> dict:
    """
    将 MEKG 原始数据格式转换为前端期望的格式
    
    原始格式包含: topic, papers_count, relations_count, categories, papers, relations
    前端期望格式: nodes, edges/links, papers
    
    注意: ECharts 图表要求边的 source/target 必须与节点的 name 属性匹配
    """
    nodes = []
    edges = []
    node_id_to_name = {}  # 映射 id -> name，用于边的转换
    node_names_set = set()  # 用于跟踪已添加的节点名称
    
    papers = raw_data.get("papers", [])
    relations = raw_data.get("relations", [])
    categories = raw_data.get("categories", {})
    
    # 1. 从 categories 创建概念/关键词节点（优先处理，因为这些节点名称简短）
    for category_name, subcategories in categories.items():
        if category_name not in node_names_set:
            node_names_set.add(category_name)
            node_id_to_name[category_name] = category_name
            nodes.append({
                "id": category_name,
                "name": category_name,
                "type": "concept",
                "category": "concept",
                "weight": sum(subcategories.values()) if isinstance(subcategories, dict) else 1
            })
        
        # 添加子类别节点
        if isinstance(subcategories, dict):
            for subcategory_name, count in subcategories.items():
                if subcategory_name not in node_names_set:
                    node_names_set.add(subcategory_name)
                    node_id_to_name[subcategory_name] = subcategory_name
                    nodes.append({
                        "id": subcategory_name,
                        "name": subcategory_name,
                        "type": "keyword",
                        "category": "keyword",
                        "weight": count
                    })
                # 添加类别到子类别的边
                edges.append({
                    "source": category_name,
                    "target": subcategory_name,
                    "weight": count
                })
    
    # 2. 从 papers 创建论文节点（限制数量，避免图谱过于复杂）
    max_paper_nodes = 50  # 最多显示50篇论文节点
    for idx, paper in enumerate(papers[:max_paper_nodes]):
        paper_id = paper.get("id", f"paper_{idx}")
        # 使用论文标题的前30个字符作为节点名称
        paper_title = paper.get("title", "Unknown Paper")
        paper_name = paper_title[:30] + "..." if len(paper_title) > 30 else paper_title
        
        # 确保名称唯一
        original_name = paper_name
        counter = 1
        while paper_name in node_names_set:
            paper_name = f"{original_name}_{counter}"
            counter += 1
        
        node_names_set.add(paper_name)
        node_id_to_name[paper_id] = paper_name
        
        nodes.append({
            "id": paper_id,
            "name": paper_name,
            "type": "paper",
            "category": "paper",
            "weight": max(1, paper.get("citations", 0) or 0),
            "year": paper.get("year"),
            "authors": paper.get("authors", []),
            "full_title": paper_title
        })
        
        # 创建论文到类别的边
        paper_category = paper.get("category")
        paper_subcategory = paper.get("subcategory")
        
        if paper_category and paper_category in node_names_set:
            edges.append({
                "source": paper_name,
                "target": paper_category,
                "weight": 1
            })
        
        if paper_subcategory and paper_subcategory in node_names_set:
            edges.append({
                "source": paper_name,
                "target": paper_subcategory,
                "weight": 1
            })
    
    # 3. 提取作者节点（限制数量）
    author_count = {}
    author_papers = {}  # 记录作者对应的论文
    for paper in papers[:100]:  # 统计前100篇论文的作者
        paper_id = paper.get("id")
        for author in paper.get("authors", [])[:3]:  # 每篇论文最多3个作者
            if author:
                author_count[author] = author_count.get(author, 0) + 1
                if author not in author_papers:
                    author_papers[author] = []
                author_papers[author].append(paper_id)
    
    # 只添加出现次数较多的作者（前20个）
    top_authors = sorted(author_count.items(), key=lambda x: -x[1])[:20]
    for author, count in top_authors:
        if author not in node_names_set:
            node_names_set.add(author)
            node_id_to_name[author] = author
            nodes.append({
                "id": author,
                "name": author,
                "type": "author",
                "category": "author",
                "weight": count
            })
            
            # 添加作者到论文的边
            for paper_id in author_papers.get(author, [])[:5]:  # 每个作者最多连接5篇论文
                if paper_id in node_id_to_name:
                    edges.append({
                        "source": author,
                        "target": node_id_to_name[paper_id],
                        "weight": 1
                    })
    
    # 4. 处理 relations（如果存在）- 需要转换 id 到 name
    for relation in relations[:500]:  # 限制关系数量
        source = relation.get("source") or relation.get("from")
        target = relation.get("target") or relation.get("to")
        weight = relation.get("weight", 1)
        
        if source and target:
            # 尝试将 id 转换为 name
            source_name = node_id_to_name.get(source, source)
            target_name = node_id_to_name.get(target, target)
            
            # 只添加两端节点都存在的边
            if source_name in node_names_set and target_name in node_names_set:
                edges.append({
                    "source": source_name,
                    "target": target_name,
                    "weight": weight
                })
    
    # 去重边
    unique_edges = []
    edge_set = set()
    for edge in edges:
        edge_key = (edge["source"], edge["target"])
        if edge_key not in edge_set:
            edge_set.add(edge_key)
            unique_edges.append(edge)
    
    return {
        "topic": raw_data.get("topic", ""),
        "papers_count": raw_data.get("papers_count", len(papers)),
        "relations_count": raw_data.get("relations_count", len(unique_edges)),
        "nodes": nodes,
        "edges": unique_edges,
        "links": unique_edges,  # 兼容两种命名
        "papers": papers,
        "categories": categories
    }


def latex_to_markdown(latex: str) -> str:
    """简单的 LaTeX 到 Markdown 转换"""
    import re
    
    md = latex
    
    # 移除 LaTeX 前导内容
    md = re.sub(r'\\documentclass.*?\\begin\{document\}', '', md, flags=re.DOTALL)
    md = re.sub(r'\\end\{document\}', '', md)
    
    # 标题转换
    md = re.sub(r'\\title\{([^}]*)\}', r'# \1\n', md)
    md = re.sub(r'\\section\{([^}]*)\}', r'## \1\n', md)
    md = re.sub(r'\\subsection\{([^}]*)\}', r'### \1\n', md)
    md = re.sub(r'\\subsubsection\{([^}]*)\}', r'#### \1\n', md)
    
    # 格式转换
    md = re.sub(r'\\textbf\{([^}]*)\}', r'**\1**', md)
    md = re.sub(r'\\textit\{([^}]*)\}', r'*\1*', md)
    md = re.sub(r'\\emph\{([^}]*)\}', r'*\1*', md)
    
    # 列表转换
    md = re.sub(r'\\begin\{itemize\}', '', md)
    md = re.sub(r'\\end\{itemize\}', '', md)
    md = re.sub(r'\\begin\{enumerate\}', '', md)
    md = re.sub(r'\\end\{enumerate\}', '', md)
    md = re.sub(r'\\item\s*', '- ', md)
    
    # 引用转换
    md = re.sub(r'\\cite\{([^}]*)\}', r'[\1]', md)
    
    # 移除其他 LaTeX 命令
    md = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', '', md)
    md = re.sub(r'\\[a-zA-Z]+', '', md)
    
    # 清理多余空行
    md = re.sub(r'\n{3,}', '\n\n', md)
    
    return md.strip()


# ==========================================
# 层级可视化辅助类
# ==========================================

class ListLayoutEngine:
    """
    列表式布局引擎 - 复刻 visualization_server.py 的布局逻辑
    
    布局特点:
    - Topic 在顶部
    - Category 水平排列
    - SubCategory 在 Category 下方垂直排列
    - Paper 在 SubCategory 右侧垂直列表排列
    """
    
    def build_nodes(self, mekg_data: Dict[str, Any]) -> List[Dict]:
        nodes = []
        topic = mekg_data.get("topic", "Survey")
        categories = mekg_data.get("categories", {})
        papers = mekg_data.get("papers", [])
        
        # 布局参数
        CATEGORY_SPACING_X = 500  # 分类水平间距
        SUBCATEGORY_SPACING_Y = 150 # 子分类垂直间距
        PAPER_SPACING_Y = 60      # 论文垂直间距
        PAPER_OFFSET_X = 250      # 论文相对于子分类的水平偏移
        
        # 1. 根节点 (Topic)
        root_id = f"topic_{topic.replace(' ', '_')}"
        nodes.append({
            "id": root_id, "title": topic, "fullTitle": topic, "type": "topic",
            "level": 0, "x": 0, "y": 0, "width": 240, "height": 70, "parentId": None
        })
        
        # 预处理论文数据
        paper_by_subcat = {}
        for paper in papers:
            cat = paper.get("category", "Other")
            subcat = paper.get("subcategory", "Other")
            key = f"subcat_{cat}_{subcat}".replace(' ', '_').replace('&', 'and')
            if key not in paper_by_subcat:
                paper_by_subcat[key] = []
            paper_by_subcat[key].append(paper)

        # 计算每个分类的总高度
        cat_list = list(categories.items())
        total_width = len(cat_list) * CATEGORY_SPACING_X
        current_cat_x = -total_width / 2 + CATEGORY_SPACING_X / 2
        
        for cat_idx, (category, subcats) in enumerate(cat_list):
            cat_id = f"cat_{category.replace(' ', '_').replace('&', 'and')}"
            
            # 2. 分类节点 (Category)
            nodes.append({
                "id": cat_id, "title": category[:30], "fullTitle": category, "type": "category",
                "level": 1, "x": current_cat_x, "y": 200, "width": 220, "height": 55, "parentId": root_id
            })
            
            # 计算该分类下所有子分类和论文的高度
            current_subcat_y = 350
            
            # 确保 subcats 是字典
            if not isinstance(subcats, dict):
                subcats = {"Default": subcats}
            
            for subcat_idx, (subcategory, count) in enumerate(subcats.items()):
                subcat_id = f"subcat_{category}_{subcategory}".replace(' ', '_').replace('&', 'and')
                
                # 获取该子分类下的论文
                subcat_papers = paper_by_subcat.get(subcat_id, [])
                # 按引用数排序，取前20篇 (比参考代码多一点，但避免无限多)
                sorted_papers = sorted(subcat_papers, key=lambda x: x.get("citations", 0) or 0, reverse=True)[:20]
                
                # 计算子分类块的高度
                block_height = max(len(sorted_papers) * PAPER_SPACING_Y, 60)
                
                # 3. 子分类节点 (SubCategory)
                nodes.append({
                    "id": subcat_id, "title": subcategory[:25], "fullTitle": subcategory, "type": "subcategory",
                    "level": 2, "x": current_cat_x, "y": current_subcat_y + block_height / 2 - 30, # 垂直居中
                    "width": 180, "height": 48, "parentId": cat_id, "paperCount": count
                })
                
                # 4. 论文节点 (Paper) - 垂直列表排列
                paper_start_y = current_subcat_y
                for paper_idx, paper in enumerate(sorted_papers):
                    paper_id = paper.get("id", f"paper_{paper_idx}")
                    
                    nodes.append({
                        "id": paper_id, "title": paper.get("title", "")[:40], "fullTitle": paper.get("title", ""),
                        "type": "paper", "level": 3,
                        "x": current_cat_x + PAPER_OFFSET_X,
                        "y": paper_start_y + paper_idx * PAPER_SPACING_Y,
                        "width": 200, "height": 45, "parentId": subcat_id,
                        "year": paper.get("year"), "citations": paper.get("citations", 0)
                    })
                
                current_subcat_y += block_height + 40 # 增加子分类间距
                
            current_cat_x += CATEGORY_SPACING_X

        return nodes