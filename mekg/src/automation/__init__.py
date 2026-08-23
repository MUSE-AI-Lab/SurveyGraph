"""
MEKG Automation Module - 自动化构建

包含:
- IncrementalBuilder: 增量构建器
- CrawlerManager: 爬虫管理器
- PipelineOrchestrator: 流水线编排器
- MaintenanceManager: 维护管理器
- TopicBuilder: 主题构建器
"""

from mekg.src.automation.incremental_builder import IncrementalBuilder
from mekg.src.automation.crawler_manager import CrawlerManager
from mekg.src.automation.pipeline_orchestrator import (
    MEKGPipelineOrchestrator,
    BuildAction,
)
from mekg.src.automation.maintenance_manager import AutoMaintenanceManager as MaintenanceManager
from mekg.src.automation.topic_builder import TopicGraphBuilder as TopicBuilder

__all__ = [
    "IncrementalBuilder",
    "CrawlerManager",
    "MEKGPipelineOrchestrator",
    "BuildAction",
    "MaintenanceManager",
    "TopicBuilder",
]