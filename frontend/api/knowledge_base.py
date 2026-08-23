"""
SurveyGraph Frontend - 个人知识库 API
========================================

提供用户个人知识库管理功能：
- 添加文件到知识库（关联已上传的PDF）
- 从知识库移除文件（仅删除关联，不删除实际文件）
- 获取知识库文件列表
- 更新文件信息（标题、描述、标签）
"""

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import hashlib
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import AppConfig
from core.models import User
from core.security import get_current_user
from core.database import get_cursor, execute_query, execute_insert, execute_update

router = APIRouter()


# ==================== Pydantic 模型 ====================

class KnowledgeBaseFileAdd(BaseModel):
    """添加文件到知识库的请求"""
    filename: str = Field(..., min_length=1, max_length=255)
    file_path: str = Field(..., min_length=1, max_length=500)
    file_size: int = Field(default=0, ge=0)
    title: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    tags: Optional[str] = Field(None, max_length=500)


class KnowledgeBaseFileUpdate(BaseModel):
    """更新知识库文件信息的请求"""
    title: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    tags: Optional[str] = Field(None, max_length=500)


class KnowledgeBaseFileBatchAdd(BaseModel):
    """批量添加文件到知识库的请求"""
    files: List[KnowledgeBaseFileAdd]


class KnowledgeBaseFileResponse(BaseModel):
    """知识库文件响应"""
    id: int
    user_id: int
    filename: str
    file_path: str
    file_size: int
    file_hash: Optional[str]
    title: Optional[str]
    description: Optional[str]
    tags: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]


# ==================== API 端点 ====================

@router.get("", summary="获取个人知识库文件列表")
async def list_knowledge_base_files(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    tags: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户的知识库文件列表
    
    参数:
    - page: 页码（从1开始）
    - page_size: 每页数量（最大100）
    - search: 搜索关键词（搜索文件名、标题、描述）
    - tags: 标签过滤（逗号分隔）
    """
    # 限制分页参数
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    offset = (page - 1) * page_size
    
    # 构建查询条件
    conditions = ["user_id = %s"]
    params = [current_user.id]
    
    if search:
        conditions.append("(filename LIKE %s OR title LIKE %s OR description LIKE %s)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern, search_pattern])
    
    if tags:
        # 支持多标签过滤（任意匹配）
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_list:
            tag_conditions = []
            for tag in tag_list:
                tag_conditions.append("tags LIKE %s")
                params.append(f"%{tag}%")
            conditions.append(f"({' OR '.join(tag_conditions)})")
    
    where_clause = " AND ".join(conditions)
    
    # 查询总数
    count_query = f"SELECT COUNT(*) as total FROM user_knowledge_base WHERE {where_clause}"
    count_result = await execute_query(count_query, tuple(params), fetch_one=True)
    total = count_result["total"] if count_result else 0
    
    # 查询文件列表
    list_query = f"""
        SELECT id, user_id, filename, file_path, file_size, file_hash, 
               title, description, tags, created_at, updated_at
        FROM user_knowledge_base 
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([page_size, offset])
    files = await execute_query(list_query, tuple(params))
    
    # 格式化响应
    file_list = []
    for f in files:
        file_list.append({
            "id": f["id"],
            "user_id": f["user_id"],
            "filename": f["filename"],
            "file_path": f["file_path"],
            "file_size": f["file_size"],
            "file_hash": f["file_hash"],
            "title": f["title"],
            "description": f["description"],
            "tags": f["tags"],
            "created_at": f["created_at"].isoformat() if f["created_at"] else None,
            "updated_at": f["updated_at"].isoformat() if f["updated_at"] else None,
        })
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "files": file_list
    }


@router.post("", summary="添加文件到知识库")
async def add_to_knowledge_base(
    file_info: KnowledgeBaseFileAdd,
    current_user: User = Depends(get_current_user)
):
    """
    将已上传的文件添加到个人知识库
    
    注意：文件必须已经存在于共享PDF目录中
    """
    # 验证文件是否存在
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在，请先上传文件"
        )
    
    # 计算文件哈希（用于去重检测）
    file_hash = None
    try:
        with open(file_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
    except Exception:
        pass
    
    # 检查是否已存在相同文件
    check_query = """
        SELECT id FROM user_knowledge_base 
        WHERE user_id = %s AND file_path = %s
    """
    existing = await execute_query(check_query, (current_user.id, str(file_path)), fetch_one=True)
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该文件已在知识库中"
        )
    
    # 获取实际文件大小
    actual_size = file_path.stat().st_size if file_path.exists() else file_info.file_size
    
    # 插入记录
    insert_query = """
        INSERT INTO user_knowledge_base 
        (user_id, filename, file_path, file_size, file_hash, title, description, tags)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    file_id = await execute_insert(insert_query, (
        current_user.id,
        file_info.filename,
        str(file_path),
        actual_size,
        file_hash,
        file_info.title or file_info.filename,
        file_info.description,
        file_info.tags
    ))
    
    return {
        "message": "文件已添加到知识库",
        "id": file_id,
        "filename": file_info.filename,
        "file_path": str(file_path)
    }


@router.post("/batch", summary="批量添加文件到知识库")
async def batch_add_to_knowledge_base(
    request: KnowledgeBaseFileBatchAdd,
    current_user: User = Depends(get_current_user)
):
    """
    批量将已上传的文件添加到个人知识库
    """
    results = []
    success_count = 0
    error_count = 0
    
    for file_info in request.files:
        try:
            # 验证文件是否存在
            file_path = Path(file_info.file_path)
            if not file_path.exists():
                results.append({
                    "filename": file_info.filename,
                    "success": False,
                    "error": "文件不存在"
                })
                error_count += 1
                continue
            
            # 检查是否已存在
            check_query = """
                SELECT id FROM user_knowledge_base 
                WHERE user_id = %s AND file_path = %s
            """
            existing = await execute_query(check_query, (current_user.id, str(file_path)), fetch_one=True)
            
            if existing:
                results.append({
                    "filename": file_info.filename,
                    "success": False,
                    "error": "文件已在知识库中",
                    "id": existing["id"]
                })
                error_count += 1
                continue
            
            # 计算文件哈希
            file_hash = None
            try:
                with open(file_path, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()
            except Exception:
                pass
            
            # 获取实际文件大小
            actual_size = file_path.stat().st_size if file_path.exists() else file_info.file_size
            
            # 插入记录
            insert_query = """
                INSERT INTO user_knowledge_base 
                (user_id, filename, file_path, file_size, file_hash, title, description, tags)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            file_id = await execute_insert(insert_query, (
                current_user.id,
                file_info.filename,
                str(file_path),
                actual_size,
                file_hash,
                file_info.title or file_info.filename,
                file_info.description,
                file_info.tags
            ))
            
            results.append({
                "filename": file_info.filename,
                "success": True,
                "id": file_id
            })
            success_count += 1
            
        except Exception as e:
            results.append({
                "filename": file_info.filename,
                "success": False,
                "error": str(e)
            })
            error_count += 1
    
    return {
        "message": f"批量添加完成：成功 {success_count} 个，失败 {error_count} 个",
        "success_count": success_count,
        "error_count": error_count,
        "results": results
    }


@router.get("/{file_id}", summary="获取知识库文件详情")
async def get_knowledge_base_file(
    file_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    获取知识库中指定文件的详细信息
    """
    query = """
        SELECT id, user_id, filename, file_path, file_size, file_hash, 
               title, description, tags, created_at, updated_at
        FROM user_knowledge_base 
        WHERE id = %s AND user_id = %s
    """
    file_info = await execute_query(query, (file_id, current_user.id), fetch_one=True)
    
    if not file_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在或无权访问"
        )
    
    # 检查实际文件是否存在
    file_exists = Path(file_info["file_path"]).exists()
    
    return {
        "id": file_info["id"],
        "user_id": file_info["user_id"],
        "filename": file_info["filename"],
        "file_path": file_info["file_path"],
        "file_size": file_info["file_size"],
        "file_hash": file_info["file_hash"],
        "title": file_info["title"],
        "description": file_info["description"],
        "tags": file_info["tags"],
        "file_exists": file_exists,
        "created_at": file_info["created_at"].isoformat() if file_info["created_at"] else None,
        "updated_at": file_info["updated_at"].isoformat() if file_info["updated_at"] else None,
    }


@router.put("/{file_id}", summary="更新知识库文件信息")
async def update_knowledge_base_file(
    file_id: int,
    update_info: KnowledgeBaseFileUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    更新知识库文件的标题、描述、标签等信息
    """
    # 检查文件是否存在且属于当前用户
    check_query = "SELECT id FROM user_knowledge_base WHERE id = %s AND user_id = %s"
    existing = await execute_query(check_query, (file_id, current_user.id), fetch_one=True)
    
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在或无权访问"
        )
    
    # 构建更新语句
    update_fields = []
    params = []
    
    if update_info.title is not None:
        update_fields.append("title = %s")
        params.append(update_info.title)
    
    if update_info.description is not None:
        update_fields.append("description = %s")
        params.append(update_info.description)
    
    if update_info.tags is not None:
        update_fields.append("tags = %s")
        params.append(update_info.tags)
    
    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有提供要更新的字段"
        )
    
    params.extend([file_id, current_user.id])
    update_query = f"""
        UPDATE user_knowledge_base 
        SET {', '.join(update_fields)}
        WHERE id = %s AND user_id = %s
    """
    
    await execute_update(update_query, tuple(params))
    
    return {
        "message": "文件信息已更新",
        "id": file_id
    }


@router.delete("/{file_id}", summary="从知识库移除文件")
async def remove_from_knowledge_base(
    file_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    从个人知识库中移除文件
    
    注意：这只会删除知识库中的关联记录，不会删除实际的PDF文件
    """
    # 检查文件是否存在且属于当前用户
    check_query = """
        SELECT id, filename, file_path FROM user_knowledge_base 
        WHERE id = %s AND user_id = %s
    """
    existing = await execute_query(check_query, (file_id, current_user.id), fetch_one=True)
    
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在或无权访问"
        )
    
    # 删除记录
    delete_query = "DELETE FROM user_knowledge_base WHERE id = %s AND user_id = %s"
    await execute_update(delete_query, (file_id, current_user.id))
    
    return {
        "message": "文件已从知识库移除",
        "id": file_id,
        "filename": existing["filename"],
        "note": "实际文件未被删除，仍保留在服务器上"
    }


@router.delete("", summary="批量从知识库移除文件")
async def batch_remove_from_knowledge_base(
    file_ids: str,  # 逗号分隔的ID列表
    current_user: User = Depends(get_current_user)
):
    """
    批量从个人知识库中移除文件
    
    参数:
    - file_ids: 逗号分隔的文件ID列表，如 "1,2,3"
    """
    try:
        ids = [int(id.strip()) for id in file_ids.split(",") if id.strip()]
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的文件ID格式"
        )
    
    if not ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请提供要删除的文件ID"
        )
    
    # 删除属于当前用户的记录
    placeholders = ",".join(["%s"] * len(ids))
    delete_query = f"""
        DELETE FROM user_knowledge_base 
        WHERE id IN ({placeholders}) AND user_id = %s
    """
    params = ids + [current_user.id]
    
    deleted_count = await execute_update(delete_query, tuple(params))
    
    return {
        "message": f"已从知识库移除 {deleted_count} 个文件",
        "deleted_count": deleted_count,
        "note": "实际文件未被删除，仍保留在服务器上"
    }