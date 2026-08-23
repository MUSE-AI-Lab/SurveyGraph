"""
SurveyGraph Frontend - Pipeline 服务
=====================================

调用 mekg_run.py 执行综述生成流水线。
使用独立进程管理器，支持 FastAPI 重启后恢复任务监控。
"""

import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import logging

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import TaskConfig, PROJECT_ROOT
from core.database import execute_query, execute_update
from core.models import TaskStatus, LogLevel
from services.task_service import TaskService
from services.process_manager import process_manager, ProcessInfo

logger = logging.getLogger(__name__)

# 任务锁，防止重复启动
_task_locks: Dict[str, asyncio.Lock] = {}


async def start_pipeline(
    task_id: str,
    resume: bool = False,
    from_step: Optional[int] = None
):
    """
    启动 Pipeline
    
    使用独立进程管理器启动任务，进程与 FastAPI 完全解耦。
    即使 FastAPI 重启，任务进程也会继续运行。
    
    Args:
        task_id: 任务 ID
        resume: 是否从断点恢复
        from_step: 从指定步骤开始（仅在 resume=True 时有效）
    """
    # 获取任务
    task = await TaskService.get_task_by_task_id(task_id)
    if not task:
        logger.error(f"Task not found: {task_id}")
        return
    
    # 获取或创建锁
    if task_id not in _task_locks:
        _task_locks[task_id] = asyncio.Lock()
    
    async with _task_locks[task_id]:
        # 检查是否已在运行（通过进程管理器检查）
        if process_manager.is_task_running(task_id):
            logger.warning(f"Task already running: {task_id}")
            return
        
        # 更新状态
        await TaskService.update_task_status(task_id, TaskStatus.RUNNING)
        
        # 添加日志
        await TaskService.add_task_log(
            task.id,
            step=from_step or task.current_step,
            step_name=TaskConfig.PIPELINE_STEPS.get(from_step or task.current_step, {}).get("name", "UNKNOWN"),
            level=LogLevel.INFO,
            message=f"任务{'从断点恢复' if resume else '开始'}执行"
        )
        
        # 使用进程管理器启动任务
        try:
            # 获取上传文件列表和 arXiv 搜索设置
            uploaded_files = task.uploaded_files or []
            enable_arxiv_search = getattr(task, 'enable_arxiv_search', True)
            
            process_info = await process_manager.start_task(
                task_id=task_id,
                topic=task.topic,
                config=task.config,
                resume=resume,
                from_step=from_step,
                uploaded_files=uploaded_files,
                enable_arxiv_search=enable_arxiv_search
            )
            
            logger.info(f"Task {task_id} started with PID {process_info.pid}")
            
            # 启动日志监控（异步）
            asyncio.create_task(_monitor_task_logs(task_id, task.id))
            
        except Exception as e:
            logger.error(f"Failed to start task {task_id}: {e}")
            await TaskService.fail_task(task_id, str(e))
            raise


async def _monitor_task_logs(task_id: str, task_db_id: int):
    """
    监控任务日志文件并更新进度
    
    从日志文件中读取输出，解析进度信息并更新数据库。
    同时通过 WebSocket 推送实时更新到前端。
    
    进度检测策略（双重保障）：
    1. 主要方式：解析日志文件中的步骤标记
    2. 备选方式：定期读取 checkpoint.json 文件（更可靠）
    
    暂停点逻辑：
    - 暂停点设置为步骤N，表示在步骤N完成后暂停
    - 当检测到步骤N+1开始时，说明步骤N已完成，此时触发暂停
    """
    from api.websocket import push_progress, push_log, push_status_change
    
    current_step = 0
    previous_step = 0  # 记录上一个步骤，用于暂停点检测
    last_position = 0
    last_progress_push = 0  # 上次推送进度的时间戳
    last_checkpoint_check = 0  # 上次检查 checkpoint 的时间戳
    
    # 获取日志文件路径
    process_info = process_manager.get_process_info(task_id)
    if not process_info or not process_info.log_file:
        logger.warning(f"No log file found for task {task_id}")
        return
    
    log_file = Path(process_info.log_file)
    
    # 获取 checkpoint.json 路径（与日志文件同级目录的上一级）
    # 日志文件路径: outputs/{task_id}/logs/pipeline.log
    # checkpoint 路径: outputs/{task_id}/checkpoint.json
    checkpoint_file = log_file.parent.parent / "checkpoint.json"
    
    # 等待日志文件创建
    for _ in range(30):  # 最多等待 30 秒
        if log_file.exists():
            break
        await asyncio.sleep(1)
    
    if not log_file.exists():
        logger.warning(f"Log file not created for task {task_id}")
        return
    
    logger.info(f"Starting log monitor for task {task_id}, log file: {log_file}")
    
    # 推送初始状态
    try:
        await push_status_change(task_id, "running")
    except Exception as e:
        logger.warning(f"Failed to push initial status: {e}")
    
    # 获取任务配置中的暂停点
    task = await TaskService.get_task_by_task_id(task_id)
    pause_points = []
    if task and task.config:
        pause_points = task.config.get("pause_points", [])
    
    while True:
        try:
            # 检查进程是否还在运行
            if not process_manager.is_task_running(task_id):
                # 读取剩余日志
                await _process_remaining_logs(log_file, last_position, task_id, task_db_id, current_step)
                break
            
            # 定期检查 checkpoint.json（每 3 秒检查一次，作为日志解析的补充）
            import time
            now = time.time()
            if now - last_checkpoint_check >= 3:
                checkpoint_step = _read_checkpoint_step(checkpoint_file)
                if checkpoint_step is not None and checkpoint_step > current_step:
                    # checkpoint 显示的步骤比当前检测到的步骤更新
                    logger.info(f"Task {task_id} step updated from checkpoint: {current_step} -> {checkpoint_step}")
                    previous_step = current_step
                    current_step = checkpoint_step
                    step_name = TaskConfig.PIPELINE_STEPS.get(current_step, {}).get("name", f"STEP_{current_step}")
                    progress = _get_step_progress(current_step)
                    
                    # 更新数据库
                    await TaskService.update_task_progress(
                        task_id,
                        current_step=current_step,
                        current_step_name=step_name,
                        progress_percent=progress
                    )
                    
                    # 添加日志
                    await TaskService.add_task_log(
                        task_db_id,
                        step=current_step,
                        step_name=step_name,
                        level=LogLevel.INFO,
                        message=f"开始执行: {step_name} (从 checkpoint 检测)"
                    )
                    
                    # 推送进度
                    try:
                        await push_progress(task_id, current_step, step_name, progress, f"开始执行: {step_name}")
                        last_progress_push = now
                    except Exception as e:
                        logger.warning(f"Failed to push progress: {e}")
                
                last_checkpoint_check = now
            
            # 读取新的日志内容
            if log_file.exists():
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(last_position)
                    new_content = f.read()
                    last_position = f.tell()
                
                if new_content:
                    for line in new_content.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        
                        # 解析输出，更新进度
                        step_info = _parse_pipeline_output(line)
                        
                        if step_info:
                            # 检查是否是错误信息
                            if step_info.get("is_error"):
                                await TaskService.add_task_log(
                                    task_db_id,
                                    step=current_step,
                                    step_name=TaskConfig.PIPELINE_STEPS.get(current_step, {}).get("name", ""),
                                    level=LogLevel.ERROR,
                                    message=step_info.get("message", line)
                                )
                                try:
                                    await push_log(task_id, "error", step_info.get("message", line), current_step)
                                except Exception:
                                    pass
                                continue
                            
                            new_step = step_info.get("step", current_step)
                            step_name = step_info.get("step_name", "")
                            progress = step_info.get("progress", 0)
                            message = step_info.get("message", "")
                            
                            # 步骤变化或进度更新
                            if new_step != current_step or new_step > 0:
                                # 检查是否到达暂停点（在步骤变化时检查）
                                # 暂停点逻辑：当检测到新步骤开始时，说明上一个步骤已完成
                                # 如果上一个步骤在暂停点列表中，则暂停任务
                                should_pause = False
                                pause_at_step = 0
                                pause_step_name = ""
                                
                                if new_step != current_step and previous_step > 0:
                                    # 步骤发生变化，检查上一个步骤是否是暂停点
                                    if previous_step in pause_points and previous_step < 11:
                                        should_pause = True
                                        pause_at_step = previous_step
                                        pause_step_name = TaskConfig.PIPELINE_STEPS.get(previous_step, {}).get("label", f"步骤{previous_step}")
                                        logger.info(f"Task {task_id} completed pause point step {previous_step}, will pause before step {new_step}")
                                
                                # 更新步骤记录
                                if new_step != current_step:
                                    previous_step = current_step
                                    current_step = new_step
                                    logger.info(f"Task {task_id} step changed to {current_step} ({step_name})")
                                
                                # 更新数据库
                                await TaskService.update_task_progress(
                                    task_id,
                                    current_step=current_step,
                                    current_step_name=step_name,
                                    progress_percent=progress,
                                    papers_count=step_info.get("papers_count"),
                                    relations_count=step_info.get("relations_count"),
                                    sections_count=step_info.get("sections_count")
                                )
                                
                                # 添加日志
                                await TaskService.add_task_log(
                                    task_db_id,
                                    step=current_step,
                                    step_name=step_name,
                                    level=LogLevel.INFO,
                                    message=message or f"开始执行: {step_name}"
                                )
                                
                                # 推送进度（限制频率，每秒最多一次）
                                import time
                                now = time.time()
                                if now - last_progress_push >= 1:
                                    try:
                                        await push_progress(task_id, current_step, step_name, progress, message)
                                        last_progress_push = now
                                    except Exception as e:
                                        logger.warning(f"Failed to push progress: {e}")
                                
                                # 如果需要暂停，在更新进度后执行暂停
                                if should_pause:
                                    logger.info(f"Task {task_id} pausing after step {pause_at_step} ({pause_step_name})")
                                    
                                    # 暂停任务
                                    await pause_pipeline(task_id)
                                    
                                    # 添加暂停日志
                                    await TaskService.add_task_log(
                                        task_db_id,
                                        step=pause_at_step,
                                        step_name=pause_step_name,
                                        level=LogLevel.INFO,
                                        message=f"任务在步骤 {pause_at_step} ({pause_step_name}) 完成后暂停，等待用户确认继续"
                                    )
                                    
                                    # 推送暂停状态
                                    try:
                                        await push_status_change(task_id, "paused")
                                    except Exception:
                                        pass
                                    
                                    return  # 退出监控循环
                        
                        # 检测错误（即使没有匹配到步骤模式）
                        elif "error" in line.lower() or "failed" in line.lower() or "❌" in line:
                            # 排除一些常见的非错误日志
                            if not any(x in line.lower() for x in ["no error", "without error", "error_message"]):
                                await TaskService.add_task_log(
                                    task_db_id,
                                    step=current_step,
                                    step_name=TaskConfig.PIPELINE_STEPS.get(current_step, {}).get("name", ""),
                                    level=LogLevel.ERROR,
                                    message=line
                                )
                                try:
                                    await push_log(task_id, "error", line, current_step)
                                except Exception:
                                    pass
                        
                        # 检测警告
                        elif "warning" in line.lower() or "⚠️" in line:
                            await TaskService.add_task_log(
                                task_db_id,
                                step=current_step,
                                step_name=TaskConfig.PIPELINE_STEPS.get(current_step, {}).get("name", ""),
                                level=LogLevel.WARNING,
                                message=line
                            )
                            try:
                                await push_log(task_id, "warning", line, current_step)
                            except Exception:
                                pass
            
            await asyncio.sleep(0.5)  # 每 0.5 秒检查一次，提高响应速度
            
        except Exception as e:
            logger.error(f"Error monitoring logs for {task_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await asyncio.sleep(5)
    
    logger.info(f"Log monitor ended for task {task_id}")


async def _process_remaining_logs(log_file: Path, last_position: int, task_id: str, task_db_id: int, current_step: int):
    """处理剩余的日志内容"""
    try:
        if log_file.exists():
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(last_position)
                remaining = f.read()
            
            for line in remaining.splitlines():
                line = line.strip()
                if not line:
                    continue
                
                step_info = _parse_pipeline_output(line)
                if step_info:
                    new_step = step_info.get("step", current_step)
                    if new_step != current_step:
                        current_step = new_step
                        await TaskService.update_task_progress(
                            task_id,
                            current_step=current_step,
                            current_step_name=step_info.get("step_name", ""),
                            progress_percent=step_info.get("progress", 0)
                        )
    except Exception as e:
        logger.error(f"Error processing remaining logs: {e}")


def _read_checkpoint_step(checkpoint_file: Path) -> Optional[int]:
    """
    读取 checkpoint.json 文件获取当前步骤
    
    这是比日志解析更可靠的进度检测方式，因为 checkpoint 是由 pipeline 主动保存的。
    
    Args:
        checkpoint_file: checkpoint.json 文件路径
        
    Returns:
        当前步骤编号，如果读取失败返回 None
    """
    try:
        if not checkpoint_file.exists():
            return None
        
        import json
        with open(checkpoint_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        step = data.get("step")
        if isinstance(step, int):
            return step
        return None
    except Exception as e:
        logger.debug(f"Failed to read checkpoint: {e}")
        return None


def _get_step_progress(step: int) -> int:
    """
    根据步骤编号获取对应的进度百分比
    
    Args:
        step: 步骤编号
        
    Returns:
        进度百分比
    """
    step_progress_map = {
        0: 0,
        1: 10,   # MEKG_BUILT
        2: 20,   # OUTLINE_GENERATED
        3: 35,   # CONTENT_GENERATED
        4: 50,   # POST_REFINED
        5: 60,   # TABLES_GENERATED
        6: 70,   # VISUALS_GENERATED
        7: 80,   # EVALUATED
        8: 85,   # CRITICAL_ANALYZED
        9: 90,   # LATEX_GENERATED
        10: 95,  # VISUALIZATION_DONE
        11: 100, # COMPLETED
    }
    return step_progress_map.get(step, 0)


def _parse_pipeline_output(text: str) -> Optional[Dict[str, Any]]:
    """解析 Pipeline 输出，提取步骤和进度信息
    
    支持多种日志格式：
    1. mekg_run.py 的输出格式: "Step 1-4: Running MEKG Pipeline..."
    2. pipeline.py 的输出格式: "📋 Step 2: 生成大纲..." 或 "✍️ Step 3: ..."
    3. 各模块的日志格式: "Step 1: 生成 Top-down 大纲..."
    
    注意：日志中可能包含 emoji 字符，正则表达式需要能够处理这种情况。
    """
    import re
    
    # 先移除常见的 emoji 前缀，简化匹配
    # 常见的 emoji: 📋 ✍️ 📥 🔧 📊 🎨 📈 📄 🚀 ✅ ❌ ⚠️ 💾 等
    clean_text = re.sub(r'^[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF\s]+', '', text.strip())
    
    # 步骤检测模式 - 支持多种格式
    # 格式: (pattern, step_number, step_name, progress)
    step_patterns = [
        # 完成状态检测 - 必须放在最前面，使用更严格的模式
        # 只匹配明确表示整个任务完成的日志，而不是单个步骤完成
        (r"All\s*steps\s*completed|Pipeline\s*completed\s*successfully|🎉.*All.*completed|全部.*完成|任务.*完成", 11, "COMPLETED", 100),
        
        # mekg_run.py 格式 - 各步骤检测
        # Step 1: MEKG 构建
        (r"Step\s*1[-:]?\s*4|MEKG\s*Pipeline|Running\s*MEKG|论文采集|图谱构建|Collection.*Graph", 1, "MEKG_BUILT", 10),
        
        # Step 2: 大纲生成
        (r"Step\s*2[:\s]|生成大纲|Outline|大纲生成|Top-down|Bottom-up|合并大纲", 2, "OUTLINE_GENERATED", 20),
        
        # Step 3: 内容生成 - 增强匹配模式
        # 匹配: "Step 3:", "Step 3 ", "生成Survey主体内容", "ContentGenerator", "ReflectiveContentGenerator"
        (r"Step\s*3[:\s]|生成Survey|Survey主体|ContentGenerator|ReflectiveContentGenerator|生成内容|Content|内容生成|Writing|撰写|Phase\s*1.*generating\s*content", 3, "CONTENT_GENERATED", 35),
        
        # Step 4: 文本优化
        (r"Step\s*4[:\s]|文本优化|Refin|PostRefin|优化内容", 4, "POST_REFINED", 50),
        
        # Step 5: 表格生成
        (r"Step\s*5[:\s]|表格生成|Table|生成表格|generate_tables", 5, "TABLES_GENERATED", 60),
        
        # Step 6: 视觉元素生成
        (r"Step\s*6[:\s]|视觉元素|Visual|图表|Figure|动态视觉|generate_dynamic_visuals", 6, "VISUALS_GENERATED", 70),
        
        # Step 7: 质量评估
        (r"Step\s*7[:\s]|质量评估|Evaluat|评估|evaluation|GlobalReflector|EvolutionaryAnalyzer", 7, "EVALUATED", 80),
        
        # Step 7.5: 批判性分析
        (r"Step\s*7\.5|批判分析|Critical|批判性|CriticalAnalysis", 8, "CRITICAL_ANALYZED", 85),
        
        # Step 8: LaTeX 生成
        (r"Step\s*8[:\s]|LaTeX|Latex|latex|生成LaTeX|LatexTextBuilder", 9, "LATEX_GENERATED", 90),
        
        # Step 9: 可视化导出
        (r"Step\s*9[:\s]|可视化|Visualization|导出|visualization_data", 10, "VISUALIZATION_DONE", 95),
        
        # PDF 编译
        (r"Compiling\s*PDF|编译\s*PDF|PDF\s*generated|PDF生成", 9, "LATEX_GENERATED", 92),
    ]
    
    # 同时在原始文本和清理后的文本中搜索
    for pattern, step, name, progress in step_patterns:
        if re.search(pattern, text, re.IGNORECASE) or re.search(pattern, clean_text, re.IGNORECASE):
            result = {
                "step": step,
                "step_name": name,
                "progress": progress,
                "message": text.strip()
            }
            
            # 提取统计信息
            # 论文数量
            papers_match = re.search(r'(\d+)\s*(?:篇|papers?|论文)', text, re.IGNORECASE)
            if papers_match:
                result["papers_count"] = int(papers_match.group(1))
            
            # 关系数量
            relations_match = re.search(r'(\d+)\s*(?:个|relations?|关系)', text, re.IGNORECASE)
            if relations_match:
                result["relations_count"] = int(relations_match.group(1))
            
            # 章节数量
            sections_match = re.search(r'(\d+)\s*(?:个|章节|sections?)', text, re.IGNORECASE)
            if sections_match:
                result["sections_count"] = int(sections_match.group(1))
            
            return result
    
    # 检测错误信息
    if re.search(r'error|failed|❌|exception|traceback', text, re.IGNORECASE):
        return {
            "step": -1,
            "step_name": "ERROR",
            "progress": -1,
            "message": text.strip(),
            "is_error": True
        }
    
    return None


async def pause_pipeline(task_id: str):
    """
    暂停 Pipeline
    
    使用进程管理器停止任务进程。
    """
    # 使用进程管理器停止任务
    success = await process_manager.stop_task(task_id, force=False)
    
    if success:
        await TaskService.update_task_status(task_id, TaskStatus.PAUSED)
        
        # 添加日志
        task = await TaskService.get_task_by_task_id(task_id)
        if task:
            await TaskService.add_task_log(
                task.id,
                step=task.current_step,
                step_name=task.current_step_name or "",
                level=LogLevel.INFO,
                message="任务已暂停"
            )
        
        logger.info(f"Task {task_id} paused")
    else:
        logger.warning(f"Failed to pause task {task_id}")


async def cancel_pipeline(task_id: str):
    """
    取消 Pipeline
    
    使用进程管理器强制停止任务进程。
    """
    # 使用进程管理器强制停止任务
    await process_manager.stop_task(task_id, force=True)
    
    await TaskService.update_task_status(task_id, TaskStatus.FAILED, "用户取消")
    
    # 添加日志
    task = await TaskService.get_task_by_task_id(task_id)
    if task:
        await TaskService.add_task_log(
            task.id,
            step=task.current_step,
            step_name=task.current_step_name or "",
            level=LogLevel.INFO,
            message="任务已取消"
        )
    
    logger.info(f"Task {task_id} cancelled")


async def get_pipeline_status(task_id: str) -> Dict[str, Any]:
    """
    获取 Pipeline 状态
    
    通过进程管理器获取进程状态。
    """
    # 通过进程管理器检查运行状态
    is_running = process_manager.is_task_running(task_id)
    process_info = process_manager.get_process_info(task_id)
    
    task = await TaskService.get_task_by_task_id(task_id)
    if not task:
        return {"error": "Task not found"}
    
    result = {
        "task_id": task_id,
        "is_running": is_running,
        "status": task.status.value,
        "current_step": task.current_step,
        "current_step_name": task.current_step_name,
        "progress_percent": task.progress_percent
    }
    
    # 添加进程信息
    if process_info:
        result["process"] = {
            "pid": process_info.pid,
            "started_at": process_info.started_at,
            "process_status": process_info.status,
            "log_file": process_info.log_file
        }
    
    return result


def get_running_tasks() -> list:
    """
    获取所有运行中的任务
    
    通过进程管理器获取运行中的任务列表。
    """
    running = process_manager.get_all_running_tasks()
    return [p.task_id for p in running]


async def recover_running_tasks():
    """
    恢复运行中任务的监控
    
    FastAPI 重启后调用此函数，恢复对正在运行的任务的监控。
    """
    logger.info("Recovering running task monitors...")
    
    # 恢复进程管理器的监控
    await process_manager.recover_monitors()
    
    # 为每个运行中的任务启动日志监控
    running_tasks = process_manager.get_all_running_tasks()
    
    for process_info in running_tasks:
        task = await TaskService.get_task_by_task_id(process_info.task_id)
        if task:
            logger.info(f"Recovering log monitor for task {process_info.task_id}")
            asyncio.create_task(_monitor_task_logs(process_info.task_id, task.id))
    
    logger.info(f"Recovered {len(running_tasks)} task monitors")


def get_task_logs(task_id: str, lines: int = 100) -> list:
    """
    获取任务的原始日志
    
    Args:
        task_id: 任务 ID
        lines: 返回的行数
    
    Returns:
        日志行列表
    """
    return process_manager.get_task_logs(task_id, lines)


def cleanup_old_processes(max_age_hours: int = 72):
    """
    清理旧的进程信息
    
    Args:
        max_age_hours: 最大保留时间（小时）
    """
    process_manager.cleanup_old_processes(max_age_hours)