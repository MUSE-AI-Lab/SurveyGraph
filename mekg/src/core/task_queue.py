"""
Task Queue System
=================

异步任务队列系统，支持：
- 优先级调度
- 任务依赖
- 并发控制
- 任务状态追踪
- 超时处理
- 错误重试

使用方法:
    queue = TaskQueue(max_workers=10)
    
    # 提交任务
    task_id = await queue.submit("my_task", my_func, arg1, arg2, priority=1)
    
    # 等待结果
    result = await queue.wait(task_id)
    
    # 提交带依赖的任务
    task_id = await queue.submit(
        "dependent_task",
        my_func,
        depends_on=["task1", "task2"]
    )
"""

from __future__ import annotations

import asyncio
import uuid
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Set,
    Union,
)
from heapq import heappush, heappop
import threading
from contextlib import asynccontextmanager

from loguru import logger


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"          # 等待执行
    QUEUED = "queued"            # 已入队
    RUNNING = "running"          # 执行中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 失败
    CANCELLED = "cancelled"      # 已取消
    TIMEOUT = "timeout"          # 超时


@dataclass
class Task:
    """
    任务定义
    
    Attributes:
        id: 任务 ID
        name: 任务名称
        func: 任务函数
        args: 位置参数
        kwargs: 关键字参数
        priority: 优先级（越大越优先）
        depends_on: 依赖的任务 ID 列表
        timeout: 超时时间（秒）
        max_retries: 最大重试次数
        status: 任务状态
        result: 任务结果
        error: 错误信息
        created_at: 创建时间
        started_at: 开始时间
        completed_at: 完成时间
    """
    id: str
    name: str
    func: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    depends_on: List[str] = field(default_factory=list)
    timeout: Optional[float] = None
    max_retries: int = 0
    
    # 状态信息
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    retry_count: int = 0
    
    # 时间信息
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def __lt__(self, other: "Task") -> bool:
        """用于优先级队列比较（优先级高的排前面）"""
        return self.priority > other.priority
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "priority": self.priority,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "result": str(self.result)[:100] if self.result else None,
            "error": self.error,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class TaskQueue:
    """
    异步任务队列
    
    支持：
    - 优先级调度
    - 任务依赖
    - 并发控制
    - 超时处理
    - 错误重试
    
    使用示例:
        queue = TaskQueue(max_workers=10)
        await queue.start()
        
        # 提交任务
        task_id = await queue.submit("task1", my_func, arg1)
        
        # 等待结果
        result = await queue.wait(task_id)
        
        # 停止队列
        await queue.stop()
    """
    
    def __init__(
        self,
        max_workers: int = 10,
        default_timeout: Optional[float] = None,
        default_max_retries: int = 0
    ):
        """
        初始化任务队列
        
        Args:
            max_workers: 最大并发工作数
            default_timeout: 默认超时时间
            default_max_retries: 默认最大重试次数
        """
        self.max_workers = max_workers
        self.default_timeout = default_timeout
        self.default_max_retries = default_max_retries
        
        # 任务存储
        self._tasks: Dict[str, Task] = {}
        self._priority_queue: List[Task] = []
        self._running_tasks: Set[str] = set()
        
        # 同步原语
        self._lock = asyncio.Lock()
        self._task_available = asyncio.Event()
        self._task_completed: Dict[str, asyncio.Event] = {}
        
        # 工作状态
        self._running = False
        self._workers: List[asyncio.Task] = []
        
        # 统计信息
        self._stats = {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "timeout": 0,
            "retried": 0,
        }
    
    async def start(self) -> None:
        """启动任务队列"""
        if self._running:
            return
        
        self._running = True
        
        # 启动工作协程
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)
        
        logger.info(f"TaskQueue started with {self.max_workers} workers")
    
    async def stop(self, wait: bool = True, timeout: float = 30.0) -> None:
        """
        停止任务队列
        
        Args:
            wait: 是否等待当前任务完成
            timeout: 等待超时时间
        """
        self._running = False
        self._task_available.set()  # 唤醒所有等待的工作协程
        
        if wait and self._workers:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._workers, return_exceptions=True),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning("TaskQueue stop timeout, cancelling workers")
                for worker in self._workers:
                    worker.cancel()
        
        self._workers.clear()
        logger.info("TaskQueue stopped")
    
    async def submit(
        self,
        name: str,
        func: Callable,
        *args,
        priority: int = 0,
        depends_on: Optional[List[str]] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        提交任务
        
        Args:
            name: 任务名称
            func: 任务函数（可以是同步或异步函数）
            *args: 位置参数
            priority: 优先级（越大越优先）
            depends_on: 依赖的任务 ID 列表
            timeout: 超时时间
            max_retries: 最大重试次数
            **kwargs: 关键字参数
            
        Returns:
            任务 ID
        """
        task_id = str(uuid.uuid4())[:8]
        
        task = Task(
            id=task_id,
            name=name,
            func=func,
            args=args,
            kwargs=kwargs,
            priority=priority,
            depends_on=depends_on or [],
            timeout=timeout if timeout is not None else self.default_timeout,
            max_retries=max_retries if max_retries is not None else self.default_max_retries,
        )
        
        async with self._lock:
            self._tasks[task_id] = task
            self._task_completed[task_id] = asyncio.Event()
            
            # 检查依赖是否满足
            if self._check_dependencies(task):
                task.status = TaskStatus.QUEUED
                heappush(self._priority_queue, task)
                self._task_available.set()
            
            self._stats["submitted"] += 1
        
        logger.debug(f"Task submitted: {task_id} ({name})")
        return task_id
    
    async def wait(
        self,
        task_id: str,
        timeout: Optional[float] = None
    ) -> Any:
        """
        等待任务完成
        
        Args:
            task_id: 任务 ID
            timeout: 等待超时时间
            
        Returns:
            任务结果
            
        Raises:
            KeyError: 任务不存在
            asyncio.TimeoutError: 等待超时
            Exception: 任务执行失败
        """
        if task_id not in self._tasks:
            raise KeyError(f"Task not found: {task_id}")
        
        event = self._task_completed.get(task_id)
        if event:
            try:
                await asyncio.wait_for(event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                raise asyncio.TimeoutError(f"Waiting for task {task_id} timeout")
        
        task = self._tasks[task_id]
        
        if task.status == TaskStatus.COMPLETED:
            return task.result
        elif task.status == TaskStatus.FAILED:
            raise Exception(f"Task failed: {task.error}")
        elif task.status == TaskStatus.CANCELLED:
            raise asyncio.CancelledError(f"Task cancelled: {task_id}")
        elif task.status == TaskStatus.TIMEOUT:
            raise asyncio.TimeoutError(f"Task timeout: {task_id}")
        else:
            raise Exception(f"Unexpected task status: {task.status}")
    
    async def wait_all(
        self,
        task_ids: List[str],
        timeout: Optional[float] = None
    ) -> List[Any]:
        """
        等待多个任务完成
        
        Args:
            task_ids: 任务 ID 列表
            timeout: 等待超时时间
            
        Returns:
            任务结果列表
        """
        tasks = [self.wait(tid, timeout=timeout) for tid in task_ids]
        return await asyncio.gather(*tasks, return_exceptions=True)
    
    async def cancel(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否成功取消
        """
        async with self._lock:
            if task_id not in self._tasks:
                return False
            
            task = self._tasks[task_id]
            
            # 只能取消等待中或排队中的任务
            if task.status in (TaskStatus.PENDING, TaskStatus.QUEUED):
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now()
                self._stats["cancelled"] += 1
                
                # 通知等待者
                if task_id in self._task_completed:
                    self._task_completed[task_id].set()
                
                logger.debug(f"Task cancelled: {task_id}")
                return True
            
            return False
    
    def get_status(self, task_id: str) -> Optional[str]:
        """
        获取任务状态
        
        Args:
            task_id: 任务 ID
            
        Returns:
            任务状态字符串
        """
        if task_id in self._tasks:
            return self._tasks[task_id].status.value
        return None
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """
        获取任务对象
        
        Args:
            task_id: 任务 ID
            
        Returns:
            Task 对象
        """
        return self._tasks.get(task_id)
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return dict(self._stats)
    
    def _check_dependencies(self, task: Task) -> bool:
        """
        检查任务依赖是否满足
        
        Args:
            task: 任务对象
            
        Returns:
            依赖是否满足
        """
        for dep_id in task.depends_on:
            if dep_id not in self._tasks:
                return False
            dep_task = self._tasks[dep_id]
            if dep_task.status != TaskStatus.COMPLETED:
                return False
        return True
    
    async def _check_pending_tasks(self) -> None:
        """检查等待中的任务，将依赖满足的任务加入队列"""
        async with self._lock:
            for task in self._tasks.values():
                if task.status == TaskStatus.PENDING:
                    if self._check_dependencies(task):
                        task.status = TaskStatus.QUEUED
                        heappush(self._priority_queue, task)
                        self._task_available.set()
    
    async def _worker(self, worker_id: int) -> None:
        """
        工作协程
        
        Args:
            worker_id: 工作协程 ID
        """
        logger.debug(f"Worker {worker_id} started")
        
        while self._running:
            # 等待任务
            await self._task_available.wait()
            
            if not self._running:
                break
            
            # 获取任务
            task = None
            async with self._lock:
                if self._priority_queue:
                    task = heappop(self._priority_queue)
                    task.status = TaskStatus.RUNNING
                    task.started_at = datetime.now()
                    self._running_tasks.add(task.id)
                
                # 如果队列空了，清除事件
                if not self._priority_queue:
                    self._task_available.clear()
            
            if task is None:
                continue
            
            # 执行任务
            try:
                result = await self._execute_task(task)
                
                async with self._lock:
                    task.status = TaskStatus.COMPLETED
                    task.result = result
                    task.completed_at = datetime.now()
                    self._stats["completed"] += 1
                
                logger.debug(f"Task completed: {task.id} ({task.name})")
                
            except asyncio.TimeoutError:
                async with self._lock:
                    task.status = TaskStatus.TIMEOUT
                    task.error = "Task execution timeout"
                    task.completed_at = datetime.now()
                    self._stats["timeout"] += 1
                
                logger.warning(f"Task timeout: {task.id} ({task.name})")
                
            except Exception as e:
                # 检查是否需要重试
                if task.retry_count < task.max_retries:
                    async with self._lock:
                        task.retry_count += 1
                        task.status = TaskStatus.QUEUED
                        heappush(self._priority_queue, task)
                        self._task_available.set()
                        self._stats["retried"] += 1
                    
                    logger.warning(
                        f"Task failed, retrying ({task.retry_count}/{task.max_retries}): "
                        f"{task.id} ({task.name}) - {e}"
                    )
                else:
                    async with self._lock:
                        task.status = TaskStatus.FAILED
                        task.error = str(e)
                        task.completed_at = datetime.now()
                        self._stats["failed"] += 1
                    
                    logger.error(f"Task failed: {task.id} ({task.name}) - {e}")
            
            finally:
                async with self._lock:
                    self._running_tasks.discard(task.id)
                    
                    # 通知等待者
                    if task.id in self._task_completed:
                        self._task_completed[task.id].set()
                
                # 检查依赖此任务的其他任务
                await self._check_pending_tasks()
        
        logger.debug(f"Worker {worker_id} stopped")
    
    async def _execute_task(self, task: Task) -> Any:
        """
        执行任务
        
        Args:
            task: 任务对象
            
        Returns:
            任务结果
        """
        # 判断是否是协程函数
        if asyncio.iscoroutinefunction(task.func):
            coro = task.func(*task.args, **task.kwargs)
        else:
            # 在线程池中运行同步函数
            loop = asyncio.get_event_loop()
            coro = loop.run_in_executor(
                None,
                lambda: task.func(*task.args, **task.kwargs)
            )
        
        # 应用超时
        if task.timeout:
            return await asyncio.wait_for(coro, timeout=task.timeout)
        else:
            return await coro


@asynccontextmanager
async def task_queue_context(
    max_workers: int = 10,
    **kwargs
):
    """
    任务队列上下文管理器
    
    使用示例:
        async with task_queue_context(max_workers=10) as queue:
            task_id = await queue.submit("task", my_func)
            result = await queue.wait(task_id)
    """
    queue = TaskQueue(max_workers=max_workers, **kwargs)
    await queue.start()
    try:
        yield queue
    finally:
        await queue.stop()


# ============================================================================
# 便捷函数
# ============================================================================

async def run_parallel(
    tasks: List[tuple[str, Callable, tuple, dict]],
    max_workers: int = 10,
    timeout: Optional[float] = None
) -> List[Any]:
    """
    并行运行多个任务
    
    Args:
        tasks: 任务列表，每个元素为 (name, func, args, kwargs)
        max_workers: 最大并发数
        timeout: 超时时间
        
    Returns:
        结果列表
        
    使用示例:
        results = await run_parallel([
            ("task1", func1, (arg1,), {}),
            ("task2", func2, (arg2,), {"key": "value"}),
        ])
    """
    async with task_queue_context(max_workers=max_workers) as queue:
        task_ids = []
        for name, func, args, kwargs in tasks:
            task_id = await queue.submit(name, func, *args, timeout=timeout, **kwargs)
            task_ids.append(task_id)
        
        return await queue.wait_all(task_ids, timeout=timeout)


async def run_with_dependencies(
    tasks: Dict[str, tuple[Callable, tuple, dict, List[str]]],
    max_workers: int = 10,
    timeout: Optional[float] = None
) -> Dict[str, Any]:
    """
    运行带依赖的任务
    
    Args:
        tasks: 任务字典，key 为任务名，value 为 (func, args, kwargs, depends_on)
        max_workers: 最大并发数
        timeout: 超时时间
        
    Returns:
        结果字典
        
    使用示例:
        results = await run_with_dependencies({
            "task1": (func1, (arg1,), {}, []),
            "task2": (func2, (arg2,), {}, ["task1"]),
            "task3": (func3, (), {}, ["task1", "task2"]),
        })
    """
    async with task_queue_context(max_workers=max_workers) as queue:
        task_ids = {}
        
        # 提交所有任务
        for name, (func, args, kwargs, depends_on) in tasks.items():
            # 将依赖名称转换为任务 ID
            dep_ids = [task_ids[dep] for dep in depends_on if dep in task_ids]
            
            task_id = await queue.submit(
                name, func, *args,
                depends_on=dep_ids,
                timeout=timeout,
                **kwargs
            )
            task_ids[name] = task_id
        
        # 等待所有任务完成
        results = {}
        for name, task_id in task_ids.items():
            try:
                results[name] = await queue.wait(task_id, timeout=timeout)
            except Exception as e:
                results[name] = e
        
        return results