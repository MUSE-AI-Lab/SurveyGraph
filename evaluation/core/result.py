"""
评测结果数据结构
================

定义评测结果的数据结构。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime
import json


@dataclass
class DimensionResult:
    """单个维度的评测结果"""
    
    name: str                           # 维度名称
    score: float                        # 维度得分 (0.0-1.0)
    weight: float                       # 权重
    metrics: Dict[str, float]           # 详细指标
    details: Dict[str, Any] = field(default_factory=dict)  # 详细信息
    
    @property
    def weighted_score(self) -> float:
        """加权得分"""
        return self.score * self.weight
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "name": self.name,
            "score": round(self.score, 4),
            "weight": self.weight,
            "weighted_score": round(self.weighted_score, 4),
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
            "details": self.details
        }


@dataclass
class EvaluationResult:
    """完整评测结果"""
    
    # 基本信息
    survey_path: str = ""
    mekg_path: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # 各维度结果
    reference_quality: Optional[DimensionResult] = None
    structural_soundness: Optional[DimensionResult] = None
    content_integrity: Optional[DimensionResult] = None
    ethics_integrity: Optional[DimensionResult] = None
    rich_media_quality: Optional[DimensionResult] = None
    
    # 综合得分 (0-100)
    overall_score: float = 0.0
    
    # 所有指标汇总
    all_metrics: Dict[str, float] = field(default_factory=dict)
    
    # 建议
    recommendations: List[str] = field(default_factory=list)
    
    # 错误信息
    errors: List[str] = field(default_factory=list)
    
    def calculate_overall_score(self) -> float:
        """计算综合得分"""
        dimensions = [
            self.reference_quality,
            self.structural_soundness,
            self.content_integrity,
            self.ethics_integrity,
            self.rich_media_quality
        ]
        
        total_weighted_score = 0.0
        total_weight = 0.0
        
        for dim in dimensions:
            if dim is not None:
                total_weighted_score += dim.weighted_score
                total_weight += dim.weight
        
        if total_weight > 0:
            self.overall_score = (total_weighted_score / total_weight) * 100
        else:
            self.overall_score = 0.0
        
        return self.overall_score
    
    def collect_all_metrics(self) -> Dict[str, float]:
        """收集所有指标"""
        self.all_metrics = {}
        
        dimensions = [
            ("reference_quality", self.reference_quality),
            ("structural_soundness", self.structural_soundness),
            ("content_integrity", self.content_integrity),
            ("ethics_integrity", self.ethics_integrity),
            ("rich_media_quality", self.rich_media_quality)
        ]
        
        for dim_name, dim in dimensions:
            if dim is not None:
                for metric_name, metric_value in dim.metrics.items():
                    self.all_metrics[metric_name] = metric_value
        
        return self.all_metrics
    
    def get_dimension_scores(self) -> Dict[str, float]:
        """获取各维度得分"""
        scores = {}
        
        if self.reference_quality:
            scores["reference_quality"] = self.reference_quality.score * 100
        if self.structural_soundness:
            scores["structural_soundness"] = self.structural_soundness.score * 100
        if self.content_integrity:
            scores["content_integrity"] = self.content_integrity.score * 100
        if self.ethics_integrity:
            scores["ethics_integrity"] = self.ethics_integrity.score * 100
        if self.rich_media_quality:
            scores["rich_media_quality"] = self.rich_media_quality.score * 100
        
        return scores
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "survey_path": self.survey_path,
            "mekg_path": self.mekg_path,
            "timestamp": self.timestamp,
            "overall_score": round(self.overall_score, 2),
            "dimension_scores": self.get_dimension_scores(),
            "dimensions": {
                "reference_quality": self.reference_quality.to_dict() if self.reference_quality else None,
                "structural_soundness": self.structural_soundness.to_dict() if self.structural_soundness else None,
                "content_integrity": self.content_integrity.to_dict() if self.content_integrity else None,
                "ethics_integrity": self.ethics_integrity.to_dict() if self.ethics_integrity else None,
                "rich_media_quality": self.rich_media_quality.to_dict() if self.rich_media_quality else None
            },
            "all_metrics": {k: round(v, 4) for k, v in self.all_metrics.items()},
            "recommendations": self.recommendations,
            "errors": self.errors
        }
    
    def to_json(self, indent: int = 2) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
    
    def save(self, path: str):
        """保存到文件"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())
    
    @classmethod
    def load(cls, path: str) -> "EvaluationResult":
        """从文件加载"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        result = cls(
            survey_path=data.get("survey_path", ""),
            mekg_path=data.get("mekg_path", ""),
            timestamp=data.get("timestamp", ""),
            overall_score=data.get("overall_score", 0.0),
            all_metrics=data.get("all_metrics", {}),
            recommendations=data.get("recommendations", []),
            errors=data.get("errors", [])
        )
        
        # 加载各维度结果
        dimensions = data.get("dimensions", {})
        
        if dimensions.get("reference_quality"):
            d = dimensions["reference_quality"]
            result.reference_quality = DimensionResult(
                name=d["name"],
                score=d["score"],
                weight=d["weight"],
                metrics=d["metrics"],
                details=d.get("details", {})
            )
        
        if dimensions.get("structural_soundness"):
            d = dimensions["structural_soundness"]
            result.structural_soundness = DimensionResult(
                name=d["name"],
                score=d["score"],
                weight=d["weight"],
                metrics=d["metrics"],
                details=d.get("details", {})
            )
        
        if dimensions.get("content_integrity"):
            d = dimensions["content_integrity"]
            result.content_integrity = DimensionResult(
                name=d["name"],
                score=d["score"],
                weight=d["weight"],
                metrics=d["metrics"],
                details=d.get("details", {})
            )
        
        if dimensions.get("ethics_integrity"):
            d = dimensions["ethics_integrity"]
            result.ethics_integrity = DimensionResult(
                name=d["name"],
                score=d["score"],
                weight=d["weight"],
                metrics=d["metrics"],
                details=d.get("details", {})
            )
        
        if dimensions.get("rich_media_quality"):
            d = dimensions["rich_media_quality"]
            result.rich_media_quality = DimensionResult(
                name=d["name"],
                score=d["score"],
                weight=d["weight"],
                metrics=d["metrics"],
                details=d.get("details", {})
            )
        
        return result
    
    def __str__(self) -> str:
        """字符串表示"""
        lines = [
            "",
            "=" * 60,
            "📊 MEKG Survey Evaluation Results",
            "=" * 60,
            "",
            f"Overall Score: {self.overall_score:.2f}/100",
            "",
            "Dimension Scores:",
            "-" * 40
        ]
        
        dimension_scores = self.get_dimension_scores()
        for name, score in dimension_scores.items():
            display_name = name.replace("_", " ").title()
            lines.append(f"  • {display_name}: {score:.2f}")
        
        lines.extend([
            "",
            "Key Metrics:",
            "-" * 40
        ])
        
        key_metrics = ["wcr", "cc", "sc", "tc", "citation_faithfulness", "writing_quality"]
        for metric in key_metrics:
            if metric in self.all_metrics:
                lines.append(f"  • {metric.upper()}: {self.all_metrics[metric]:.4f}")
        
        if self.recommendations:
            lines.extend([
                "",
                "Recommendations:",
                "-" * 40
            ])
            for rec in self.recommendations[:5]:
                lines.append(f"  • {rec}")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)