"""
SurveyGraph Frontend - WebSocket API
=====================================

实时任务进度推送。
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Dict, Set
import asyncio
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import execute_query
from core.security import verify_token
from config import TaskConfig

router = APIRouter()


class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        # task_id -> set of websocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # websocket -> user_id
        self.connection_users: Dict[WebSocket, int] = {}
        # websocket -> is_admin
        self.connection_admins: Dict[WebSocket, bool] = {}
    
    async def connect(self, websocket: WebSocket, task_id: str, user_id: int, is_admin: bool = False):
        """建立连接"""
        await websocket.accept()
        
        if task_id not in self.active_connections:
            self.active_connections[task_id] = set()
        
        self.active_connections[task_id].add(websocket)
        self.connection_users[websocket] = user_id
        self.connection_admins[websocket] = is_admin
    
    def disconnect(self, websocket: WebSocket, task_id: str):
        """断开连接"""
        if task_id in self.active_connections:
            self.active_connections[task_id].discard(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]
        
        if websocket in self.connection_users:
            del self.connection_users[websocket]
        
        if websocket in self.connection_admins:
            del self.connection_admins[websocket]
    
    async def send_to_task(self, task_id: str, message: dict):
        """向订阅特定任务的所有连接发送消息
        
        权限过滤策略（从后端直接过滤，不发送给前端）：
        - 普通用户：不发送 log 类型消息，不发送 progress 中的详细 message
        - 管理员：发送所有消息
        """
        if task_id not in self.active_connections:
            return
        
        disconnected = set()
        msg_type = message.get("type")
        
        for websocket in self.active_connections[task_id]:
            try:
                is_admin = self.connection_admins.get(websocket, False)
                
                # ========== 权限过滤逻辑 ==========
                
                # 1. 详细日志 (log) 仅发送给管理员，普通用户完全不发送
                if msg_type == "log" and not is_admin:
                    continue
                
                # 2. 进度更新 (progress)：对普通用户移除详细的 message 字段
                #    只保留步骤编号和进度百分比等基本信息
                if msg_type == "progress" and not is_admin:
                    # 创建简化版消息，不包含详细的执行日志
                    simplified_message = {
                        "type": "progress",
                        "data": {
                            "step": message.get("data", {}).get("step"),
                            "step_name": message.get("data", {}).get("step_name"),
                            "progress_percent": message.get("data", {}).get("progress_percent"),
                            # 不发送 message 字段，避免泄露详细执行信息
                        }
                    }
                    await websocket.send_json(simplified_message)
                    continue
                
                # 3. 其他消息类型（status, status_change, completion 等）正常发送
                await websocket.send_json(message)
                
            except Exception:
                disconnected.add(websocket)
        
        # 清理断开的连接
        for ws in disconnected:
            self.disconnect(ws, task_id)
    
    async def broadcast(self, message: dict):
        """向所有连接广播消息"""
        for task_id in list(self.active_connections.keys()):
            await self.send_to_task(task_id, message)


# 全局连接管理器
manager = ConnectionManager()


@router.websocket("/ws/{task_id}")
async def websocket_task_progress(
    websocket: WebSocket,
    task_id: str,
    token: str = Query(...)
):
    """
    WebSocket 端点：实时任务进度推送
    
    连接时需要提供 JWT token 进行认证。
    
    消息格式:
    {
        "type": "progress" | "log" | "status" | "error",
        "data": {...}
    }
    """
    # 验证 Token
    payload = verify_token(token, "access")
    if not payload:
        await websocket.close(code=4001, reason="Invalid token")
        return
    
    user_id = int(payload.get("sub", 0))
    is_admin = payload.get("role") == "admin"
    
    # 验证任务访问权限
    task_query = "SELECT user_id FROM tasks WHERE task_id = %s"
    task_result = await execute_query(task_query, (task_id,), fetch_one=True)
    
    if not task_result:
        await websocket.close(code=4004, reason="Task not found")
        return
    
    if task_result["user_id"] != user_id and not is_admin:
        await websocket.close(code=4003, reason="Access denied")
        return
    
    # 建立连接
    await manager.connect(websocket, task_id, user_id, is_admin)
    
    try:
        # 发送初始状态
        initial_status = await get_task_status(task_id)
        await websocket.send_json({
            "type": "status",
            "data": initial_status
        })
        
        # 保持连接并处理消息
        while True:
            try:
                # 等待客户端消息（心跳等）
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0  # 30秒超时
                )
                
                # 处理客户端消息
                message = json.loads(data)
                
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                
                elif message.get("type") == "get_status":
                    status = await get_task_status(task_id)
                    await websocket.send_json({
                        "type": "status",
                        "data": status
                    })
                
            except asyncio.TimeoutError:
                # 发送心跳
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except Exception:
                    break
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        manager.disconnect(websocket, task_id)


async def get_task_status(task_id: str) -> dict:
    """获取任务状态"""
    query = """
        SELECT task_id, status, current_step, current_step_name, 
               progress_percent, papers_count, relations_count, 
               sections_count, error_message
        FROM tasks WHERE task_id = %s
    """
    result = await execute_query(query, (task_id,), fetch_one=True)
    
    if not result:
        return {"error": "Task not found"}
    
    # 构建步骤状态
    steps = []
    current_step = result["current_step"]
    status = result["status"]
    
    for step_num, step_info in TaskConfig.PIPELINE_STEPS.items():
        step_status = "pending"
        if step_num < current_step:
            step_status = "completed"
        elif step_num == current_step:
            if status == "running":
                step_status = "running"
            elif status == "failed":
                step_status = "failed"
            elif status == "completed":
                step_status = "completed"
        
        steps.append({
            "step": step_num,
            "name": step_info["name"],
            "label": step_info["label"],
            "status": step_status
        })
    
    return {
        "task_id": result["task_id"],
        "status": result["status"],
        "current_step": result["current_step"],
        "current_step_name": result["current_step_name"],
        "progress_percent": result["progress_percent"],
        "papers_count": result["papers_count"],
        "relations_count": result["relations_count"],
        "sections_count": result["sections_count"],
        "error_message": result["error_message"],
        "steps": steps
    }


# ==========================================
# 供其他模块调用的推送函数
# ==========================================

async def push_progress(task_id: str, step: int, step_name: str, progress: int, message: str = None):
    """推送进度更新"""
    await manager.send_to_task(task_id, {
        "type": "progress",
        "data": {
            "step": step,
            "step_name": step_name,
            "progress_percent": progress,
            "message": message
        }
    })


async def push_log(task_id: str, level: str, message: str, step: int = None):
    """推送日志"""
    await manager.send_to_task(task_id, {
        "type": "log",
        "data": {
            "level": level,
            "message": message,
            "step": step
        }
    })


async def push_status_change(task_id: str, status: str, error_message: str = None):
    """推送状态变更"""
    await manager.send_to_task(task_id, {
        "type": "status_change",
        "data": {
            "status": status,
            "error_message": error_message
        }
    })


async def push_completion(task_id: str, success: bool, result: dict = None):
    """推送任务完成"""
    await manager.send_to_task(task_id, {
        "type": "completion",
        "data": {
            "success": success,
            "result": result
        }
    })