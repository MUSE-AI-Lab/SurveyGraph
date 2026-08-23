"""
报告生成器
==========

生成Markdown格式的评测报告。
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path

from evaluation.core.result import EvaluationResult, DimensionResult


class ReportGenerator:
    """评测报告生成器"""
    
    def __init__(self, result: EvaluationResult):
        """
        初始化报告生成器
        
        Args:
            result: 评测结果
        """
        self.result = result
    
    def generate(self) -> str:
        """
        生成Markdown报告
        
        Returns:
            报告内容
        """
        sections = [
            self._generate_header(),
            self._generate_overview(),
            self._generate_dimension_details(),
            self._generate_metrics_table(),
            self._generate_recommendations(),
            self._generate_footer()
        ]
        
        return "\n\n".join(sections)
    
    def _generate_header(self) -> str:
        """生成报告头部"""
        return f"""# 📊 MEKG Survey Evaluation Report

**Generated**: {self.result.timestamp}  
**Survey**: {self.result.survey_path}
"""
    
    def _generate_overview(self) -> str:
        """生成概览部分"""
        dimension_scores = self.result.get_dimension_scores()
        
        # 生成评分条
        def score_bar(score: float) -> str:
            filled = int(score / 10)
            empty = 10 - filled
            return "█" * filled + "░" * empty
        
        lines = [
            "## 📈 Overview",
            "",
            f"### Overall Score: **{self.result.overall_score:.1f}/100**",
            "",
            "| Dimension | Score | Weight | Bar |",
            "|-----------|-------|--------|-----|"
        ]
        
        dimension_names = {
            "reference_quality": "📚 Reference Quality",
            "structural_soundness": "📋 Structural Soundness",
            "content_integrity": "✍️ Content Integrity",
            "ethics_integrity": "⚖️ Ethics & Integrity",
            "rich_media_quality": "📊 Rich Media Quality"
        }
        
        weights = {
            "reference_quality": 0.25,
            "structural_soundness": 0.20,
            "content_integrity": 0.25,
            "ethics_integrity": 0.15,
            "rich_media_quality": 0.15
        }
        
        for dim_key, dim_name in dimension_names.items():
            score = dimension_scores.get(dim_key, 0)
            weight = weights.get(dim_key, 0) * 100
            bar = score_bar(score)
            lines.append(f"| {dim_name} | {score:.1f} | {weight:.0f}% | {bar} |")
        
        lines.append(f"| **Overall** | **{self.result.overall_score:.1f}** | 100% | {score_bar(self.result.overall_score)} |")
        
        return "\n".join(lines)
    
    def _generate_dimension_details(self) -> str:
        """生成各维度详细信息"""
        sections = ["## 📋 Detailed Analysis"]
        
        # 1. Reference Quality
        if self.result.reference_quality:
            sections.append(self._format_dimension_section(
                "1. Reference Quality",
                self.result.reference_quality,
                [
                    ("WCR (Weighted Centrality Recall)", "wcr", "核心论文覆盖率"),
                    ("CC (Community Coverage)", "cc", "社区覆盖率"),
                    ("Bibliographic Integrity", "bibliographic_integrity", "文献完整性"),
                    ("Citation Faithfulness", "citation_faithfulness", "引用忠实度")
                ]
            ))
        
        # 2. Structural Soundness
        if self.result.structural_soundness:
            sections.append(self._format_dimension_section(
                "2. Structural Soundness",
                self.result.structural_soundness,
                [
                    ("SC (Structural Coherence)", "sc", "结构一致性"),
                    ("Structural Completeness", "structural_completeness", "结构完整性"),
                    ("Content-Structure Fidelity", "content_structure_fidelity", "内容-结构一致性")
                ]
            ))
        
        # 3. Content Integrity
        if self.result.content_integrity:
            sections.append(self._format_dimension_section(
                "3. Content Integrity",
                self.result.content_integrity,
                [
                    ("General Factualness", "general_factualness", "通用事实性"),
                    ("Writing Quality", "writing_quality", "写作质量"),
                    ("Scholarly Depth", "scholarly_depth", "学术深度"),
                    ("TC (Temporal Coverage)", "tc", "时间覆盖率")
                ]
            ))
        
        # 4. Ethics & Integrity
        if self.result.ethics_integrity:
            sections.append(self._format_dimension_section(
                "4. Ethics & Integrity",
                self.result.ethics_integrity,
                [
                    ("Originality", "originality", "原创性"),
                    ("Societal Impact", "societal_impact", "社会影响讨论"),
                    ("Fairness", "fairness", "公平性与偏见")
                ]
            ))
        
        # 5. Rich Media Quality
        if self.result.rich_media_quality:
            sections.append(self._format_dimension_section(
                "5. Rich Media Quality",
                self.result.rich_media_quality,
                [
                    ("Figure Quality", "figure_quality", "图片质量"),
                    ("Table Quality", "table_quality", "表格质量"),
                    ("Visual-Content Alignment", "visual_content_alignment", "视觉-内容对齐"),
                    ("Resource Accessibility", "resource_accessibility", "资源可访问性")
                ]
            ))
        
        return "\n\n".join(sections)
    
    def _format_dimension_section(
        self,
        title: str,
        dimension: DimensionResult,
        metrics_info: List[tuple]
    ) -> str:
        """格式化维度章节"""
        lines = [
            f"### {title}",
            "",
            f"**Score**: {dimension.score * 100:.1f}/100",
            "",
            "| Metric | Score | Description |",
            "|--------|-------|-------------|"
        ]
        
        for metric_name, metric_key, description in metrics_info:
            score = dimension.metrics.get(metric_key, 0)
            score_str = f"{score:.2%}" if score <= 1 else f"{score:.2f}"
            lines.append(f"| {metric_name} | {score_str} | {description} |")
        
        # 添加详细信息
        details = dimension.details
        if details:
            lines.append("")
            lines.append("**Details**:")
            
            # 显示关键详细信息
            for key, value in list(details.items())[:3]:
                if isinstance(value, dict):
                    continue
                if isinstance(value, list):
                    if len(value) > 0:
                        lines.append(f"- {key}: {', '.join(str(v) for v in value[:5])}")
                else:
                    lines.append(f"- {key}: {value}")
        
        return "\n".join(lines)
    
    def _generate_metrics_table(self) -> str:
        """生成指标汇总表"""
        lines = [
            "## 📊 All Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|"
        ]
        
        # 按类别组织指标
        metric_categories = {
            "Reference": ["wcr", "cc", "bibliographic_integrity", "citation_faithfulness"],
            "Structure": ["sc", "structural_completeness", "content_structure_fidelity"],
            "Content": ["general_factualness", "writing_quality", "scholarly_depth", "tc"],
            "Ethics": ["originality", "societal_impact", "fairness"],
            "Media": ["figure_quality", "table_quality", "visual_content_alignment", "resource_accessibility"]
        }
        
        for category, metrics in metric_categories.items():
            lines.append(f"| **{category}** | |")
            for metric in metrics:
                if metric in self.result.all_metrics:
                    value = self.result.all_metrics[metric]
                    value_str = f"{value:.4f}" if value <= 1 else f"{value:.2f}"
                    lines.append(f"| {metric} | {value_str} |")
        
        return "\n".join(lines)
    
    def _generate_recommendations(self) -> str:
        """生成建议部分"""
        lines = [
            "## 💡 Recommendations",
            ""
        ]
        
        if self.result.recommendations:
            for rec in self.result.recommendations:
                lines.append(f"- {rec}")
        else:
            lines.append("- No specific recommendations. The survey quality is good.")
        
        return "\n".join(lines)
    
    def _generate_footer(self) -> str:
        """生成报告尾部"""
        # 生成错误信息（如果有）
        error_section = ""
        if self.result.errors:
            error_lines = [
                "## ⚠️ Errors",
                ""
            ]
            for error in self.result.errors:
                error_lines.append(f"- {error}")
            error_section = "\n".join(error_lines) + "\n\n"
        
        return f"""{error_section}---

*Generated by MEKG Survey Evaluation System*  
*Timestamp: {self.result.timestamp}*
"""


def generate_report(result: EvaluationResult, output_path: Optional[Path] = None) -> str:
    """
    生成评测报告的便捷函数
    
    Args:
        result: 评测结果
        output_path: 输出路径（可选）
        
    Returns:
        报告内容
    """
    generator = ReportGenerator(result)
    report = generator.generate()
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding='utf-8')
    
    return report