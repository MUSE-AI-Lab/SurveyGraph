"""
评测器基类
==========

定义评测器的抽象基类。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pathlib import Path
import logging

from evaluation.config import EvaluationConfig


logger = logging.getLogger(__name__)


class BaseEvaluator(ABC):
    """评测器基类"""
    
    def __init__(
        self,
        config: Optional[EvaluationConfig] = None,
        mekg_data: Optional[Dict[str, Any]] = None
    ):
        """
        初始化评测器
        
        Args:
            config: 评测配置
            mekg_data: MEKG数据（可选）
        """
        self.config = config or EvaluationConfig()
        self.mekg_data = mekg_data or {}
        
        # 预处理MEKG数据
        if self.mekg_data:
            self._preprocess_mekg_data()
    
    def _preprocess_mekg_data(self):
        """预处理MEKG数据"""
        # 构建论文索引
        self.papers = {}
        for paper in self.mekg_data.get("papers", []):
            paper_id = paper.get("id") or paper.get("paper_id", "")
            if paper_id:
                self.papers[paper_id] = paper
        
        # 获取关系列表
        self.relations = self.mekg_data.get("relations", [])
        
        # 获取分类信息
        self.categories = self.mekg_data.get("categories", {})
        
        logger.debug(f"预处理MEKG数据: {len(self.papers)} 篇论文, {len(self.relations)} 条关系")
    
    @property
    @abstractmethod
    def name(self) -> str:
        """评测器名称"""
        pass
    
    @property
    @abstractmethod
    def weight(self) -> float:
        """评测器权重"""
        pass
    
    @abstractmethod
    def evaluate(
        self,
        survey_content: str,
        survey_outline: Optional[Dict] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行评测
        
        Args:
            survey_content: 综述内容
            survey_outline: 综述大纲（可选）
            **kwargs: 其他参数
            
        Returns:
            评测结果字典，包含:
            - score: 总分 (0.0-1.0)
            - metrics: 详细指标
            - details: 详细信息
        """
        pass
    
    def _log_start(self):
        """记录评测开始"""
        logger.info(f"{'='*60}")
        logger.info(f"开始 {self.name} 评测")
        logger.info(f"{'='*60}")
    
    def _log_end(self, score: float):
        """记录评测结束"""
        logger.info(f"{self.name} 评测完成: {score:.4f}")
    
    def _safe_divide(self, numerator: float, denominator: float, default: float = 0.0) -> float:
        """安全除法"""
        if denominator == 0:
            return default
        return numerator / denominator