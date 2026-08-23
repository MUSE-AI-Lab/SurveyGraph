"""
SurveyGraph Frontend - 任务服务
================================

任务相关的业务逻辑。
"""

from datetime import date, datetime
from typing import Optional, List, Dict, Any
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import TaskConfig, PROJECT_ROOT
from core.database import execute_query, execute_insert, execute_update
from core.models import Task, TaskStatus, TaskLog, LogLevel


class TaskService:
    """任务服务类"""
    
    @staticmethod
    async def get_task_by_id(task_db_id: int) -> Optional[Task]:
        """根据数据库 ID 获取任务"""
        query = "SELECT * FROM tasks WHERE id = %s"
        result = await execute_query(query, (task_db_id,), fetch_one=True)
        return Task.from_dict(result) if result else None
    
    @staticmethod
    async def get_task_by_task_id(task_id: str) -> Optional[Task]:
        """根据任务 ID 获取任务"""
        query = "SELECT * FROM tasks WHERE task_id = %s"
        result = await execute_query(query, (task_id,), fetch_one=True)
        return Task.from_dict(result) if result else None
    
    @staticmethod
    async def get_user_tasks(
        user_id: int,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """获取用户的任务列表"""
        offset = (page - 1) * page_size
        
        where_clause = "WHERE user_id = %s"
        params = [user_id]
        
        if status:
            where_clause += " AND status = %s"
            params.append(status)
        
        # 查询总数
        count_query = f"SELECT COUNT(*) as count FROM tasks {where_clause}"
        count_result = await execute_query(count_query, tuple(params), fetch_one=True)
        total = count_result["count"] if count_result else 0
        
        # 查询列表
        list_query = f"""
            SELECT * FROM tasks {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([page_size, offset])
        results = await execute_query(list_query, tuple(params))
        
        tasks = [Task.from_dict(row) for row in results]
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "tasks": tasks
        }
    
    @staticmethod
    async def create_task(
        user_id: int,
        topic: str,
        keywords: Optional[str] = None,
        enable_arxiv_search: bool = True,
        config: Optional[Dict[str, Any]] = None
    ) -> Task:
        """创建新任务"""
        # 生成任务 ID
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
        topic_slug = topic.replace(" ", "_")[:20]
        task_id = f"{timestamp}_{topic_slug}"
        
        # 合并配置
        final_config = TaskConfig.DEFAULT_PIPELINE_CONFIG.copy()
        if config:
            final_config.update(config)
        
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
            user_id,
            topic,
            keywords,
            TaskStatus.PENDING.value,
            0,
            "NOT_STARTED",
            0,
            json.dumps(final_config),
            enable_arxiv_search
        ))
        
        return await TaskService.get_task_by_id(db_id)
    
    @staticmethod
    async def update_task_status(
        task_id: str,
        status: TaskStatus,
        error_message: Optional[str] = None
    ):
        """更新任务状态"""
        if error_message:
            await execute_update(
                "UPDATE tasks SET status = %s, error_message = %s, updated_at = NOW() WHERE task_id = %s",
                (status.value, error_message, task_id)
            )
        else:
            await execute_update(
                "UPDATE tasks SET status = %s, updated_at = NOW() WHERE task_id = %s",
                (status.value, task_id)
            )
    
    @staticmethod
    async def update_task_progress(
        task_id: str,
        current_step: int,
        current_step_name: str,
        progress_percent: int,
        papers_count: Optional[int] = None,
        relations_count: Optional[int] = None,
        sections_count: Optional[int] = None
    ):
        """更新任务进度"""
        updates = [
            "current_step = %s",
            "current_step_name = %s",
            "progress_percent = %s",
            "updated_at = NOW()"
        ]
        params = [current_step, current_step_name, progress_percent]
        
        if papers_count is not None:
            updates.append("papers_count = %s")
            params.append(papers_count)
        
        if relations_count is not None:
            updates.append("relations_count = %s")
            params.append(relations_count)
        
        if sections_count is not None:
            updates.append("sections_count = %s")
            params.append(sections_count)
        
        params.append(task_id)
        
        query = f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = %s"
        await execute_update(query, tuple(params))
    
    @staticmethod
    async def complete_task(
        task_id: str,
        output_dir: str,
        mekg_data_path: Optional[str] = None,
        outline_path: Optional[str] = None,
        pdf_path: Optional[str] = None,
        evaluation_path: Optional[str] = None,
        visualization_path: Optional[str] = None
    ):
        """标记任务完成"""
        await execute_update(
            """UPDATE tasks SET 
                status = %s,
                current_step = %s,
                current_step_name = %s,
                progress_percent = 100,
                output_dir = %s,
                mekg_data_path = %s,
                outline_path = %s,
                pdf_path = %s,
                evaluation_path = %s,
                visualization_path = %s,
                completed_at = NOW(),
                updated_at = NOW()
            WHERE task_id = %s""",
            (
                TaskStatus.COMPLETED.value,
                11,  # COMPLETED step
                "COMPLETED",
                output_dir,
                mekg_data_path,
                outline_path,
                pdf_path,
                evaluation_path,
                visualization_path,
                task_id
            )
        )
    
    @staticmethod
    async def fail_task(task_id: str, error_message: str):
        """标记任务失败"""
        await execute_update(
            """UPDATE tasks SET 
                status = %s,
                error_message = %s,
                updated_at = NOW()
            WHERE task_id = %s""",
            (TaskStatus.FAILED.value, error_message, task_id)
        )
    
    @staticmethod
    async def add_task_log(
        task_db_id: int,
        step: int,
        step_name: str,
        level: LogLevel,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """添加任务日志"""
        await execute_insert(
            """INSERT INTO task_logs (task_id, step, step_name, level, message, details)
            VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                task_db_id,
                step,
                step_name,
                level.value,
                message,
                json.dumps(details) if details else None
            )
        )
    
    @staticmethod
    async def get_task_logs(
        task_db_id: int,
        level: Optional[str] = None,
        step: Optional[int] = None,
        limit: int = 100,
        include_details: bool = False
    ) -> List[TaskLog]:
        """获取任务日志"""
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
        
        return [TaskLog.from_dict(row) for row in results]
    
    @staticmethod
    async def check_user_quota(user_id: int, daily_quota: int, bonus_quota: int) -> Dict[str, Any]:
        """检查用户配额"""
        today = date.today()
        
        query = "SELECT COUNT(*) as count FROM tasks WHERE user_id = %s AND DATE(created_at) = %s"
        result = await execute_query(query, (user_id, today), fetch_one=True)
        used_today = result["count"] if result else 0
        
        total_quota = daily_quota + bonus_quota
        remaining = max(0, total_quota - used_today)
        
        return {
            "daily_quota": daily_quota,
            "bonus_quota": bonus_quota,
            "total_quota": total_quota,
            "used_today": used_today,
            "remaining_today": remaining,
            "can_create": remaining > 0
        }
    
    @staticmethod
    async def check_retry_limit(task: Task) -> Dict[str, Any]:
        """检查重试限制"""
        today = date.today()
        
        if task.last_retry_date == today:
            remaining = TaskConfig.MAX_RETRY_PER_DAY - task.retry_count
        else:
            remaining = TaskConfig.MAX_RETRY_PER_DAY
        
        return {
            "retry_count": task.retry_count if task.last_retry_date == today else 0,
            "max_retry": TaskConfig.MAX_RETRY_PER_DAY,
            "remaining": remaining,
            "can_retry": remaining > 0
        }
    
    @staticmethod
    async def increment_retry_count(task_id: str):
        """增加重试次数"""
        today = date.today()
        
        # 获取当前任务
        task = await TaskService.get_task_by_task_id(task_id)
        if not task:
            return
        
        if task.last_retry_date == today:
            new_count = task.retry_count + 1
        else:
            new_count = 1
        
        await execute_update(
            "UPDATE tasks SET retry_count = %s, last_retry_date = %s WHERE task_id = %s",
            (new_count, today, task_id)
        )
    
    @staticmethod
    def get_output_paths(task_id: str) -> Dict[str, Path]:
        """获取任务的输出路径"""
        output_dir = PROJECT_ROOT / "outputs" / task_id
        
        return {
            "output_dir": output_dir,
            "mekg_data": output_dir / "mekg" / "mekg_data.json",
            "outline": output_dir / "outline.json",
            "outlines": output_dir / "outlines.json",
            "pdf": output_dir / "survey.pdf",
            "pdf_wtmk": output_dir / "survey_wtmk.pdf",
            "latex": output_dir / "latex" / "survey.tex",
            "evaluation": output_dir / "evaluation_report.md",
            "visualization": output_dir / "visualization_data.json",
            "checkpoint": output_dir / "checkpoint.json",
            "tmp": output_dir / "tmp",
            "papers": output_dir / "papers",
        }