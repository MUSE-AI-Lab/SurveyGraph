"""
MEKG Core Module
================

核心基础设施模块，包含：
- LLM 服务层
- 协议接口
- 依赖注入容器
- 任务队列
- 增量处理
"""

from mekg.src.core.llm_service import LLMService, LLMServiceConfig
from mekg.src.core.protocols import (
    PaperCollectorProtocol,
    OutlineGeneratorProtocol,
    ContentGeneratorProtocol,
    EvaluatorProtocol,
    LatexGeneratorProtocol,
)
from mekg.src.core.container import PipelineComponents, ComponentContainer
from mekg.src.core.task_queue import TaskQueue, Task, TaskStatus
from mekg.src.core.incremental import IncrementalStateStore, ContentHasher

__all__ = [
    # LLM Service
    "LLMService",
    "LLMServiceConfig",
    # Protocols
    "PaperCollectorProtocol",
    "OutlineGeneratorProtocol", 
    "ContentGeneratorProtocol",
    "EvaluatorProtocol",
    "LatexGeneratorProtocol",
    # Container
    "PipelineComponents",
    "ComponentContainer",
    # Task Queue
    "TaskQueue",
    "Task",
    "TaskStatus",
    # Incremental
    "IncrementalStateStore",
    "ContentHasher",
]