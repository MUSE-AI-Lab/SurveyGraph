"""
增强版报告生成器
================

生成专业的多格式评测报告：
- 详细的Markdown报告
- 结构化的JSON数据
- 可视化图表（雷达图、柱状图）
- 专业的报告海报/信息图
"""

import json
import math
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field

from evaluation.core.result import EvaluationResult, DimensionResult


@dataclass
class ReportConfig:
    """报告配置"""
    # 输出格式
    generate_markdown: bool = True
    generate_json: bool = True
    generate_charts: bool = True
    generate_poster: bool = True
    generate_html: bool = True  # 新增：生成 HTML 报告
    
    # 样式配置
    theme: str = "professional"  # professional, minimal, colorful
    language: str = "zh"  # zh, en
    
    # 图表配置
    chart_width: int = 800
    chart_height: int = 600
    chart_dpi: int = 150
    
    # 报告详细程度
    detail_level: str = "full"  # brief, standard, full


class EnhancedReportGenerator:
    """增强版评测报告生成器"""
    
    # 维度信息配置
    DIMENSION_INFO = {
        "reference_quality": {
            "name_zh": "引用质量",
            "name_en": "Reference Quality",
            "icon": "📚",
            "color": "#4CAF50",
            "description_zh": "评估综述对核心文献的覆盖程度和引用的准确性",
            "description_en": "Evaluates coverage of core literature and citation accuracy"
        },
        "structural_soundness": {
            "name_zh": "结构完整性",
            "name_en": "Structural Soundness",
            "icon": "📋",
            "color": "#2196F3",
            "description_zh": "评估综述的组织结构和逻辑连贯性",
            "description_en": "Evaluates organization structure and logical coherence"
        },
        "content_integrity": {
            "name_zh": "内容质量",
            "name_en": "Content Integrity",
            "icon": "✍️",
            "color": "#FF9800",
            "description_zh": "评估内容的准确性、深度和写作质量",
            "description_en": "Evaluates content accuracy, depth and writing quality"
        },
        "ethics_integrity": {
            "name_zh": "伦理与完整性",
            "name_en": "Ethics & Integrity",
            "icon": "⚖️",
            "color": "#9C27B0",
            "description_zh": "评估原创性、社会影响讨论和公平性",
            "description_en": "Evaluates originality, societal impact discussion and fairness"
        },
        "rich_media_quality": {
            "name_zh": "富媒体质量",
            "name_en": "Rich Media Quality",
            "icon": "📊",
            "color": "#E91E63",
            "description_zh": "评估图表质量和视觉内容的有效性",
            "description_en": "Evaluates figure/table quality and visual content effectiveness"
        }
    }
    
    # 指标信息配置
    METRIC_INFO = {
        "wcr": {"name_zh": "加权中心性召回率", "name_en": "Weighted Centrality Recall", "description_zh": "核心论文覆盖程度"},
        "cc": {"name_zh": "社区覆盖率", "name_en": "Community Coverage", "description_zh": "研究方向覆盖程度"},
        "bibliographic_integrity": {"name_zh": "文献完整性", "name_en": "Bibliographic Integrity", "description_zh": "引用信息的完整性"},
        "citation_faithfulness": {"name_zh": "引用忠实度", "name_en": "Citation Faithfulness", "description_zh": "引用内容的准确性"},
        "sc": {"name_zh": "结构一致性", "name_en": "Structural Coherence", "description_zh": "大纲与内容的一致性"},
        "structural_completeness": {"name_zh": "结构完整性", "name_en": "Structural Completeness", "description_zh": "必要章节的完整性"},
        "content_structure_fidelity": {"name_zh": "内容-结构一致性", "name_en": "Content-Structure Fidelity", "description_zh": "内容与标题的匹配度"},
        "general_factualness": {"name_zh": "通用事实性", "name_en": "General Factualness", "description_zh": "事实陈述的准确性"},
        "writing_quality": {"name_zh": "写作质量", "name_en": "Writing Quality", "description_zh": "语言表达的清晰度"},
        "scholarly_depth": {"name_zh": "学术深度", "name_en": "Scholarly Depth", "description_zh": "分析的深度和专业性"},
        "tc": {"name_zh": "时间覆盖率", "name_en": "Temporal Coverage", "description_zh": "时间范围的覆盖程度"},
        "rubric_score": {"name_zh": "评分细则得分", "name_en": "Rubric Score", "description_zh": "基于学术评审标准的综合评估"},
        "originality": {"name_zh": "原创性", "name_en": "Originality", "description_zh": "内容的原创程度"},
        "societal_impact": {"name_zh": "社会影响讨论", "name_en": "Societal Impact", "description_zh": "社会影响的讨论程度"},
        "fairness": {"name_zh": "公平性", "name_en": "Fairness", "description_zh": "偏见和公平性的讨论"},
        "figure_quality": {"name_zh": "图片质量", "name_en": "Figure Quality", "description_zh": "图片的清晰度和相关性"},
        "table_quality": {"name_zh": "表格质量", "name_en": "Table Quality", "description_zh": "表格的信息量和格式"},
        "visual_content_alignment": {"name_zh": "视觉-内容对齐", "name_en": "Visual-Content Alignment", "description_zh": "图表与文本的关联度"},
        "resource_accessibility": {"name_zh": "资源可访问性", "name_en": "Resource Accessibility", "description_zh": "链接和资源的有效性"}
    }
    
    def __init__(self, result: EvaluationResult, config: Optional[ReportConfig] = None):
        """
        初始化报告生成器
        
        Args:
            result: 评测结果
            config: 报告配置
        """
        self.result = result
        self.config = config or ReportConfig()
    
    def generate_all(self, output_dir: Path) -> Dict[str, Path]:
        """
        生成所有格式的报告
        
        Args:
            output_dir: 输出目录
            
        Returns:
            生成的文件路径字典
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        generated_files = {}
        
        # 生成Markdown报告
        if self.config.generate_markdown:
            md_path = output_dir / "evaluation_report.md"
            md_content = self.generate_markdown()
            md_path.write_text(md_content, encoding='utf-8')
            generated_files["markdown"] = md_path
        
        # 生成JSON数据
        if self.config.generate_json:
            json_path = output_dir / "evaluation_data.json"
            json_content = self.generate_json()
            json_path.write_text(json_content, encoding='utf-8')
            generated_files["json"] = json_path
        
        # 生成可视化图表
        if self.config.generate_charts:
            charts_dir = output_dir / "charts"
            charts_dir.mkdir(exist_ok=True)
            chart_paths = self.generate_charts(charts_dir)
            generated_files["charts"] = chart_paths
        
        # 生成报告海报
        if self.config.generate_poster:
            poster_path = output_dir / "evaluation_poster.svg"
            poster_content = self.generate_poster_svg()
            poster_path.write_text(poster_content, encoding='utf-8')
            generated_files["poster"] = poster_path
        
        # 生成 HTML 报告（中英文双语）
        if self.config.generate_html:
            from evaluation.report.html_generator import HTMLReportGenerator, HTMLReportConfig
            
            html_config = HTMLReportConfig(
                language=self.config.language,
                include_all_metrics=True,
                include_recommendations=True
            )
            html_generator = HTMLReportGenerator(self.result, html_config)
            html_files = html_generator.generate_both_languages(output_dir)
            generated_files["html"] = html_files
        
        return generated_files
    
    # ==================== Markdown 报告生成 ====================
    
    def generate_markdown(self) -> str:
        """生成详细的Markdown报告"""
        sections = [
            self._md_header(),
            self._md_executive_summary(),
            self._md_score_overview(),
            self._md_dimension_analysis(),
            self._md_metrics_deep_dive(),
            self._md_strengths_weaknesses(),
            self._md_recommendations(),
            self._md_appendix(),
            self._md_footer()
        ]
        
        return "\n\n".join(filter(None, sections))
    
    def _md_header(self) -> str:
        """生成报告头部"""
        survey_name = Path(self.result.survey_path).stem if self.result.survey_path else "Unknown"
        
        return f"""<div align="center">

# 📊 综述质量评测报告
## Survey Quality Evaluation Report

---

**评测对象**: `{survey_name}`  
**生成时间**: {self.result.timestamp}  
**评测系统**: MEKG Survey Evaluation System v2.0

</div>

---
"""
    
    def _md_executive_summary(self) -> str:
        """生成执行摘要"""
        score = self.result.overall_score
        grade = self._get_grade(score)
        grade_color = self._get_grade_color(score)
        
        # 获取最高和最低维度
        dim_scores = self.result.get_dimension_scores()
        if dim_scores:
            best_dim = max(dim_scores.items(), key=lambda x: x[1])
            worst_dim = min(dim_scores.items(), key=lambda x: x[1])
            best_info = self.DIMENSION_INFO.get(best_dim[0], {})
            worst_info = self.DIMENSION_INFO.get(worst_dim[0], {})
        else:
            best_dim = worst_dim = None
            best_info = worst_info = {}
        
        summary = f"""## 📋 执行摘要 | Executive Summary

<table>
<tr>
<td width="50%" valign="top">

### 🎯 综合评分

<div align="center">

# {score:.1f}<sup>/100</sup>

**评级: {grade}**

</div>

</td>
<td width="50%" valign="top">

### 📈 关键发现

| 指标 | 结果 |
|:-----|:-----|
| 🏆 最强维度 | {best_info.get('icon', '')} {best_info.get('name_zh', 'N/A')} ({best_dim[1]:.1f}分) |
| ⚠️ 待改进维度 | {worst_info.get('icon', '')} {worst_info.get('name_zh', 'N/A')} ({worst_dim[1]:.1f}分) |
| 📊 评测维度数 | {len(dim_scores)} |
| ⏱️ 评测时间 | {self.result.timestamp[:10]} |

</td>
</tr>
</table>
"""
        return summary
    
    def _md_score_overview(self) -> str:
        """生成评分概览"""
        dim_scores = self.result.get_dimension_scores()
        
        # 生成评分条
        def score_bar(score: float, width: int = 20) -> str:
            filled = int(score / 100 * width)
            empty = width - filled
            return "█" * filled + "░" * empty
        
        # 生成维度表格
        rows = []
        for dim_key, score in dim_scores.items():
            info = self.DIMENSION_INFO.get(dim_key, {})
            weight = self._get_dimension_weight(dim_key)
            bar = score_bar(score)
            status = self._get_status_emoji(score)
            rows.append(f"| {info.get('icon', '')} {info.get('name_zh', dim_key)} | {score:.1f} | {weight*100:.0f}% | `{bar}` | {status} |")
        
        return f"""## 📊 评分概览 | Score Overview

### 各维度得分

| 维度 | 得分 | 权重 | 进度条 | 状态 |
|:-----|-----:|-----:|:-------|:----:|
{chr(10).join(rows)}
| **综合得分** | **{self.result.overall_score:.1f}** | **100%** | `{score_bar(self.result.overall_score)}` | {self._get_status_emoji(self.result.overall_score)} |

### 评分等级说明

| 等级 | 分数范围 | 说明 |
|:----:|:--------:|:-----|
| 🏆 优秀 | 90-100 | 综述质量卓越，各方面表现出色 |
| ✅ 良好 | 75-89 | 综述质量良好，有小幅改进空间 |
| ⚠️ 中等 | 60-74 | 综述质量一般，需要针对性改进 |
| ❌ 待改进 | 0-59 | 综述质量不足，需要大幅改进 |
"""
    
    def _md_dimension_analysis(self) -> str:
        """生成各维度详细分析"""
        sections = ["## 📋 维度详细分析 | Dimension Analysis"]
        
        dimensions = [
            ("reference_quality", self.result.reference_quality),
            ("structural_soundness", self.result.structural_soundness),
            ("content_integrity", self.result.content_integrity),
            ("ethics_integrity", self.result.ethics_integrity),
            ("rich_media_quality", self.result.rich_media_quality)
        ]
        
        for idx, (dim_key, dim_result) in enumerate(dimensions, 1):
            if dim_result:
                sections.append(self._md_dimension_section(idx, dim_key, dim_result))
        
        return "\n\n".join(sections)
    
    def _md_dimension_section(self, idx: int, dim_key: str, dim_result: DimensionResult) -> str:
        """生成单个维度的详细分析"""
        info = self.DIMENSION_INFO.get(dim_key, {})
        score = dim_result.score * 100
        
        # 生成指标表格
        metric_rows = []
        for metric_key, metric_value in dim_result.metrics.items():
            metric_info = self.METRIC_INFO.get(metric_key, {})
            value_str = f"{metric_value:.1%}" if metric_value <= 1 else f"{metric_value:.2f}"
            status = self._get_status_emoji(metric_value * 100 if metric_value <= 1 else metric_value)
            metric_rows.append(f"| {metric_info.get('name_zh', metric_key)} | {value_str} | {metric_info.get('description_zh', '')} | {status} |")
        
        # 生成详细信息
        details_section = ""
        if dim_result.details:
            details_items = []
            for key, value in list(dim_result.details.items())[:5]:
                if isinstance(value, (int, float)):
                    details_items.append(f"- **{key}**: {value}")
                elif isinstance(value, list) and len(value) > 0:
                    details_items.append(f"- **{key}**: {len(value)} 项")
                elif isinstance(value, str) and len(value) < 100:
                    details_items.append(f"- **{key}**: {value}")
            if details_items:
                details_section = "\n**详细信息**:\n" + "\n".join(details_items)
        
        return f"""### {idx}. {info.get('icon', '')} {info.get('name_zh', dim_key)}

<table>
<tr>
<td width="30%" align="center">

**得分**

# {score:.1f}

{self._get_status_emoji(score)} {self._get_grade(score)}

</td>
<td width="70%">

**说明**: {info.get('description_zh', '')}

| 指标 | 得分 | 说明 | 状态 |
|:-----|-----:|:-----|:----:|
{chr(10).join(metric_rows)}

{details_section}

</td>
</tr>
</table>
"""
    
    def _md_metrics_deep_dive(self) -> str:
        """生成指标深度分析"""
        if not self.result.all_metrics:
            return ""
        
        # 按类别组织指标
        categories = {
            "引用相关": ["wcr", "cc", "bibliographic_integrity", "citation_faithfulness"],
            "结构相关": ["sc", "structural_completeness", "content_structure_fidelity"],
            "内容相关": ["general_factualness", "writing_quality", "scholarly_depth", "tc", "rubric_score"],
            "伦理相关": ["originality", "societal_impact", "fairness"],
            "媒体相关": ["figure_quality", "table_quality", "visual_content_alignment", "resource_accessibility"]
        }
        
        sections = ["## 📈 指标深度分析 | Metrics Deep Dive"]
        
        for category, metrics in categories.items():
            rows = []
            for metric in metrics:
                if metric in self.result.all_metrics:
                    value = self.result.all_metrics[metric]
                    info = self.METRIC_INFO.get(metric, {})
                    value_str = f"{value:.1%}" if value <= 1 else f"{value:.2f}"
                    bar = "█" * int(value * 10 if value <= 1 else value / 10) + "░" * (10 - int(value * 10 if value <= 1 else value / 10))
                    rows.append(f"| {info.get('name_zh', metric)} | {value_str} | `{bar}` |")
            
            if rows:
                sections.append(f"""
### {category}

| 指标 | 得分 | 可视化 |
|:-----|-----:|:-------|
{chr(10).join(rows)}
""")
        
        return "\n".join(sections)
    
    def _md_strengths_weaknesses(self) -> str:
        """生成优势与不足分析"""
        strengths = []
        weaknesses = []
        
        # 分析各维度
        dimensions = [
            ("reference_quality", self.result.reference_quality),
            ("structural_soundness", self.result.structural_soundness),
            ("content_integrity", self.result.content_integrity),
            ("ethics_integrity", self.result.ethics_integrity),
            ("rich_media_quality", self.result.rich_media_quality)
        ]
        
        for dim_key, dim_result in dimensions:
            if dim_result:
                info = self.DIMENSION_INFO.get(dim_key, {})
                score = dim_result.score * 100
                
                if score >= 80:
                    strengths.append(f"- {info.get('icon', '')} **{info.get('name_zh', dim_key)}** ({score:.1f}分): 表现优秀")
                elif score < 60:
                    weaknesses.append(f"- {info.get('icon', '')} **{info.get('name_zh', dim_key)}** ({score:.1f}分): 需要改进")
        
        # 分析具体指标
        for metric, value in self.result.all_metrics.items():
            info = self.METRIC_INFO.get(metric, {})
            score = value * 100 if value <= 1 else value
            
            if score >= 90:
                strengths.append(f"- ✨ **{info.get('name_zh', metric)}**: {value:.1%} - 表现卓越")
            elif score < 50:
                weaknesses.append(f"- ⚠️ **{info.get('name_zh', metric)}**: {value:.1%} - 明显不足")
        
        return f"""## 💪 优势与不足 | Strengths & Weaknesses

### ✅ 优势亮点

{chr(10).join(strengths[:5]) if strengths else "- 暂无突出优势"}

### ⚠️ 改进空间

{chr(10).join(weaknesses[:5]) if weaknesses else "- 暂无明显不足"}
"""
    
    def _md_recommendations(self) -> str:
        """生成改进建议"""
        if not self.result.recommendations:
            return ""
        
        rec_items = []
        for i, rec in enumerate(self.result.recommendations, 1):
            rec_items.append(f"{i}. {rec}")
        
        return f"""## 💡 改进建议 | Recommendations

{chr(10).join(rec_items)}

### 📌 优先级建议

| 优先级 | 建议 | 预期收益 |
|:------:|:-----|:---------|
| 🔴 高 | 优先改进得分最低的维度 | 显著提升综合得分 |
| 🟡 中 | 加强引用质量和内容深度 | 提升学术价值 |
| 🟢 低 | 优化图表和格式 | 改善阅读体验 |
"""
    
    def _md_appendix(self) -> str:
        """生成附录"""
        return f"""## 📎 附录 | Appendix

### A. 评测方法说明

本评测系统基于MEKG (Methods-Entity Knowledge Graph) 知识图谱，采用多维度评估方法：

1. **引用质量评测**: 基于PageRank算法识别核心论文，评估覆盖率
2. **结构完整性评测**: 分析综述结构与标准学术综述的一致性
3. **内容质量评测**: 使用LLM评估写作质量和学术深度
4. **伦理完整性评测**: 检测原创性和社会影响讨论
5. **富媒体质量评测**: 评估图表质量和视觉内容有效性

### B. 评分标准

| 维度 | 权重 | 主要指标 |
|:-----|-----:|:---------|
| 引用质量 | 25% | WCR, CC, 文献完整性, 引用忠实度 |
| 结构完整性 | 20% | SC, 结构完整性, 内容-结构一致性 |
| 内容质量 | 25% | 事实性, 写作质量, 学术深度, 时间覆盖 |
| 伦理完整性 | 15% | 原创性, 社会影响, 公平性 |
| 富媒体质量 | 15% | 图片质量, 表格质量, 视觉对齐, 资源可访问性 |

### C. 原始数据

<details>
<summary>点击展开完整指标数据</summary>

```json
{json.dumps(self.result.all_metrics, ensure_ascii=False, indent=2)}
```

</details>
"""
    
    def _md_footer(self) -> str:
        """生成报告尾部"""
        return f"""---

<div align="center">

**📊 MEKG Survey Evaluation System**

*Powered by Knowledge Graph & Large Language Models*

生成时间: {self.result.timestamp}

</div>
"""
    
    # ==================== JSON 数据生成 ====================
    
    def generate_json(self) -> str:
        """生成详细的JSON数据"""
        data = {
            "meta": {
                "version": "2.0",
                "generator": "MEKG Survey Evaluation System",
                "timestamp": self.result.timestamp,
                "survey_path": self.result.survey_path
            },
            "summary": {
                "overall_score": round(self.result.overall_score, 2),
                "grade": self._get_grade(self.result.overall_score),
                "dimension_count": len(self.result.get_dimension_scores()),
                "metric_count": len(self.result.all_metrics)
            },
            "dimensions": {},
            "metrics": {
                "all": self.result.all_metrics,
                "by_category": self._categorize_metrics()
            },
            "analysis": {
                "strengths": self._identify_strengths(),
                "weaknesses": self._identify_weaknesses(),
                "recommendations": self.result.recommendations
            },
            "visualization_data": {
                "radar_chart": self._prepare_radar_data(),
                "bar_chart": self._prepare_bar_data(),
                "gauge_chart": self._prepare_gauge_data()
            }
        }
        
        # 添加各维度详细数据
        dimensions = [
            ("reference_quality", self.result.reference_quality),
            ("structural_soundness", self.result.structural_soundness),
            ("content_integrity", self.result.content_integrity),
            ("ethics_integrity", self.result.ethics_integrity),
            ("rich_media_quality", self.result.rich_media_quality)
        ]
        
        for dim_key, dim_result in dimensions:
            if dim_result:
                info = self.DIMENSION_INFO.get(dim_key, {})
                data["dimensions"][dim_key] = {
                    "name": info.get("name_zh", dim_key),
                    "name_en": info.get("name_en", dim_key),
                    "icon": info.get("icon", ""),
                    "color": info.get("color", "#000000"),
                    "score": round(dim_result.score * 100, 2),
                    "weight": dim_result.weight,
                    "weighted_score": round(dim_result.weighted_score * 100, 2),
                    "grade": self._get_grade(dim_result.score * 100),
                    "metrics": {k: round(v, 4) for k, v in dim_result.metrics.items()},
                    "details": dim_result.details
                }
        
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def _categorize_metrics(self) -> Dict[str, Dict[str, float]]:
        """按类别组织指标"""
        categories = {
            "reference": ["wcr", "cc", "bibliographic_integrity", "citation_faithfulness"],
            "structure": ["sc", "structural_completeness", "content_structure_fidelity"],
            "content": ["general_factualness", "writing_quality", "scholarly_depth", "tc", "rubric_score"],
            "ethics": ["originality", "societal_impact", "fairness"],
            "media": ["figure_quality", "table_quality", "visual_content_alignment", "resource_accessibility"]
        }
        
        result = {}
        for category, metrics in categories.items():
            result[category] = {m: self.result.all_metrics.get(m, 0) for m in metrics if m in self.result.all_metrics}
        
        return result
    
    def _identify_strengths(self) -> List[Dict[str, Any]]:
        """识别优势"""
        strengths = []
        for metric, value in self.result.all_metrics.items():
            score = value * 100 if value <= 1 else value
            if score >= 80:
                info = self.METRIC_INFO.get(metric, {})
                strengths.append({
                    "metric": metric,
                    "name": info.get("name_zh", metric),
                    "score": round(score, 2),
                    "level": "excellent" if score >= 90 else "good"
                })
        return sorted(strengths, key=lambda x: x["score"], reverse=True)[:5]
    
    def _identify_weaknesses(self) -> List[Dict[str, Any]]:
        """识别不足"""
        weaknesses = []
        for metric, value in self.result.all_metrics.items():
            score = value * 100 if value <= 1 else value
            if score < 60:
                info = self.METRIC_INFO.get(metric, {})
                weaknesses.append({
                    "metric": metric,
                    "name": info.get("name_zh", metric),
                    "score": round(score, 2),
                    "level": "poor" if score < 40 else "needs_improvement"
                })
        return sorted(weaknesses, key=lambda x: x["score"])[:5]
    
    def _prepare_radar_data(self) -> Dict[str, Any]:
        """准备雷达图数据"""
        dim_scores = self.result.get_dimension_scores()
        labels = []
        values = []
        
        for dim_key, score in dim_scores.items():
            info = self.DIMENSION_INFO.get(dim_key, {})
            labels.append(info.get("name_zh", dim_key))
            values.append(round(score, 2))
        
        return {"labels": labels, "values": values, "max_value": 100}
    
    def _prepare_bar_data(self) -> Dict[str, Any]:
        """准备柱状图数据"""
        dim_scores = self.result.get_dimension_scores()
        data = []
        
        for dim_key, score in dim_scores.items():
            info = self.DIMENSION_INFO.get(dim_key, {})
            data.append({
                "name": info.get("name_zh", dim_key),
                "value": round(score, 2),
                "color": info.get("color", "#000000")
            })
        
        return {"data": data}
    
    def _prepare_gauge_data(self) -> Dict[str, Any]:
        """准备仪表盘数据"""
        return {
            "value": round(self.result.overall_score, 2),
            "min": 0,
            "max": 100,
            "thresholds": [
                {"value": 60, "color": "#f44336"},
                {"value": 75, "color": "#ff9800"},
                {"value": 90, "color": "#4caf50"}
            ]
        }
    
    # ==================== 可视化图表生成 ====================
    
    def generate_charts(self, output_dir: Path) -> Dict[str, Path]:
        """
        生成可视化图表
        
        Args:
            output_dir: 输出目录
            
        Returns:
            生成的图表文件路径
        """
        charts = {}
        
        # 生成雷达图 SVG
        radar_path = output_dir / "radar_chart.svg"
        radar_svg = self._generate_radar_svg()
        radar_path.write_text(radar_svg, encoding='utf-8')
        charts["radar"] = radar_path
        
        # 生成柱状图 SVG
        bar_path = output_dir / "bar_chart.svg"
        bar_svg = self._generate_bar_svg()
        bar_path.write_text(bar_svg, encoding='utf-8')
        charts["bar"] = bar_path
        
        # 生成仪表盘 SVG
        gauge_path = output_dir / "gauge_chart.svg"
        gauge_svg = self._generate_gauge_svg()
        gauge_path.write_text(gauge_svg, encoding='utf-8')
        charts["gauge"] = gauge_path
        
        return charts
    
    def _generate_radar_svg(self) -> str:
        """生成雷达图 SVG"""
        dim_scores = self.result.get_dimension_scores()
        if not dim_scores:
            return self._empty_svg("No data available")
        
        # SVG 参数
        width, height = 500, 500
        cx, cy = width // 2, height // 2
        radius = 180
        
        # 计算各点位置
        n = len(dim_scores)
        angle_step = 2 * math.pi / n
        
        # 生成背景网格
        grid_lines = []
        for level in [0.2, 0.4, 0.6, 0.8, 1.0]:
            r = radius * level
            points = []
            for i in range(n):
                angle = -math.pi / 2 + i * angle_step
                x = cx + r * math.cos(angle)
                y = cy + r * math.sin(angle)
                points.append(f"{x},{y}")
            grid_lines.append(f'<polygon points="{" ".join(points)}" fill="none" stroke="#e0e0e0" stroke-width="1"/>')
        
        # 生成轴线
        axis_lines = []
        for i in range(n):
            angle = -math.pi / 2 + i * angle_step
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            axis_lines.append(f'<line x1="{cx}" y1="{cy}" x2="{x}" y2="{y}" stroke="#e0e0e0" stroke-width="1"/>')
        
        # 生成数据多边形
        data_points = []
        labels = []
        for i, (dim_key, score) in enumerate(dim_scores.items()):
            angle = -math.pi / 2 + i * angle_step
            r = radius * (score / 100)
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            data_points.append(f"{x},{y}")
            
            # 标签位置
            label_r = radius + 30
            label_x = cx + label_r * math.cos(angle)
            label_y = cy + label_r * math.sin(angle)
            info = self.DIMENSION_INFO.get(dim_key, {})
            label_text = info.get("name_zh", dim_key)[:4]  # 截取前4个字符
            labels.append(f'<text x="{label_x}" y="{label_y}" text-anchor="middle" font-size="12" fill="#333">{label_text}</text>')
            labels.append(f'<text x="{label_x}" y="{label_y + 14}" text-anchor="middle" font-size="10" fill="#666">{score:.0f}</text>')
        
        data_polygon = f'<polygon points="{" ".join(data_points)}" fill="rgba(33, 150, 243, 0.3)" stroke="#2196F3" stroke-width="2"/>'
        
        # 生成数据点
        data_dots = []
        for i, (dim_key, score) in enumerate(dim_scores.items()):
            angle = -math.pi / 2 + i * angle_step
            r = radius * (score / 100)
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            data_dots.append(f'<circle cx="{x}" cy="{y}" r="5" fill="#2196F3"/>')
        
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
    <rect width="100%" height="100%" fill="white"/>
    <text x="{cx}" y="30" text-anchor="middle" font-size="16" font-weight="bold" fill="#333">维度评分雷达图</text>
    {"".join(grid_lines)}
    {"".join(axis_lines)}
    {data_polygon}
    {"".join(data_dots)}
    {"".join(labels)}
</svg>'''
    
    def _generate_bar_svg(self) -> str:
        """生成柱状图 SVG"""
        dim_scores = self.result.get_dimension_scores()
        if not dim_scores:
            return self._empty_svg("No data available")
        
        # SVG 参数
        width, height = 600, 400
        margin = {"top": 50, "right": 30, "bottom": 80, "left": 60}
        chart_width = width - margin["left"] - margin["right"]
        chart_height = height - margin["top"] - margin["bottom"]
        
        n = len(dim_scores)
        bar_width = chart_width / n * 0.7
        bar_gap = chart_width / n * 0.3
        
        bars = []
        labels = []
        values = []
        
        for i, (dim_key, score) in enumerate(dim_scores.items()):
            info = self.DIMENSION_INFO.get(dim_key, {})
            color = info.get("color", "#2196F3")
            
            x = margin["left"] + i * (bar_width + bar_gap) + bar_gap / 2
            bar_height = (score / 100) * chart_height
            y = margin["top"] + chart_height - bar_height
            
            bars.append(f'<rect x="{x}" y="{y}" width="{bar_width}" height="{bar_height}" fill="{color}" rx="4"/>')
            
            # 标签
            label_x = x + bar_width / 2
            label_y = height - margin["bottom"] + 20
            label_text = info.get("name_zh", dim_key)[:4]
            labels.append(f'<text x="{label_x}" y="{label_y}" text-anchor="middle" font-size="11" fill="#333">{label_text}</text>')
            
            # 数值
            value_y = y - 8
            values.append(f'<text x="{label_x}" y="{value_y}" text-anchor="middle" font-size="12" font-weight="bold" fill="#333">{score:.1f}</text>')
        
        # Y轴刻度
        y_ticks = []
        for tick in [0, 25, 50, 75, 100]:
            y = margin["top"] + chart_height - (tick / 100) * chart_height
            y_ticks.append(f'<line x1="{margin["left"]}" y1="{y}" x2="{width - margin["right"]}" y2="{y}" stroke="#e0e0e0" stroke-width="1"/>')
            y_ticks.append(f'<text x="{margin["left"] - 10}" y="{y + 4}" text-anchor="end" font-size="10" fill="#666">{tick}</text>')
        
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
    <rect width="100%" height="100%" fill="white"/>
    <text x="{width/2}" y="30" text-anchor="middle" font-size="16" font-weight="bold" fill="#333">各维度得分对比</text>
    {"".join(y_ticks)}
    {"".join(bars)}
    {"".join(labels)}
    {"".join(values)}
</svg>'''
    
    def _generate_gauge_svg(self) -> str:
        """生成仪表盘 SVG"""
        score = self.result.overall_score
        
        # SVG 参数
        width, height = 400, 300
        cx, cy = width // 2, height - 60
        radius = 120
        
        # 计算角度 (180度范围)
        start_angle = math.pi
        end_angle = 0
        score_angle = start_angle - (score / 100) * math.pi
        
        # 背景弧
        def arc_path(start: float, end: float, r: float) -> str:
            x1 = cx + r * math.cos(start)
            y1 = cy + r * math.sin(start)
            x2 = cx + r * math.cos(end)
            y2 = cy + r * math.sin(end)
            large_arc = 1 if abs(end - start) > math.pi else 0
            return f"M {x1} {y1} A {r} {r} 0 {large_arc} 1 {x2} {y2}"
        
        # 颜色区域
        colors = [
            (math.pi, math.pi * 0.6, "#f44336"),      # 红色 0-40
            (math.pi * 0.6, math.pi * 0.25, "#ff9800"),  # 橙色 40-75
            (math.pi * 0.25, 0, "#4caf50")            # 绿色 75-100
        ]
        
        color_arcs = []
        for start, end, color in colors:
            path = arc_path(start, end, radius)
            color_arcs.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="20" stroke-linecap="round" opacity="0.3"/>')
        
        # 得分弧
        score_path = arc_path(start_angle, score_angle, radius)
        score_color = "#f44336" if score < 60 else "#ff9800" if score < 75 else "#4caf50"
        
        # 指针
        pointer_x = cx + (radius - 30) * math.cos(score_angle)
        pointer_y = cy + (radius - 30) * math.sin(score_angle)
        
        # 等级文字
        grade = self._get_grade(score)
        
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
    <rect width="100%" height="100%" fill="white"/>
    <text x="{cx}" y="30" text-anchor="middle" font-size="16" font-weight="bold" fill="#333">综合评分</text>
    
    {"".join(color_arcs)}
    <path d="{score_path}" fill="none" stroke="{score_color}" stroke-width="20" stroke-linecap="round"/>
    
    <circle cx="{cx}" cy="{cy}" r="8" fill="#333"/>
    <line x1="{cx}" y1="{cy}" x2="{pointer_x}" y2="{pointer_y}" stroke="#333" stroke-width="3" stroke-linecap="round"/>
    
    <text x="{cx}" y="{cy - 40}" text-anchor="middle" font-size="36" font-weight="bold" fill="{score_color}">{score:.1f}</text>
    <text x="{cx}" y="{cy - 10}" text-anchor="middle" font-size="14" fill="#666">{grade}</text>
    
    <text x="{cx - radius - 10}" y="{cy + 20}" text-anchor="middle" font-size="10" fill="#666">0</text>
    <text x="{cx + radius + 10}" y="{cy + 20}" text-anchor="middle" font-size="10" fill="#666">100</text>
</svg>'''
    
    def _empty_svg(self, message: str) -> str:
        """生成空白 SVG"""
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="400" height="300" xmlns="http://www.w3.org/2000/svg">
    <rect width="100%" height="100%" fill="#f5f5f5"/>
    <text x="200" y="150" text-anchor="middle" font-size="14" fill="#999">{message}</text>
</svg>'''
    
    # ==================== 报告海报生成 ====================
    
    def generate_poster_svg(self) -> str:
        """生成专业的报告海报 SVG"""
        width, height = 800, 1200
        score = self.result.overall_score
        dim_scores = self.result.get_dimension_scores()
        
        # 颜色主题
        primary_color = "#2196F3"
        success_color = "#4CAF50"
        warning_color = "#FF9800"
        danger_color = "#F44336"
        
        score_color = danger_color if score < 60 else warning_color if score < 75 else success_color
        grade = self._get_grade(score)
        
        # 生成维度卡片
        dim_cards = []
        card_y = 480
        card_height = 100
        card_gap = 20
        
        for i, (dim_key, dim_score) in enumerate(dim_scores.items()):
            info = self.DIMENSION_INFO.get(dim_key, {})
            y = card_y + i * (card_height + card_gap)
            color = info.get("color", primary_color)
            
            # 进度条
            bar_width = 300
            bar_x = 420
            filled_width = (dim_score / 100) * bar_width
            
            dim_cards.append(f'''
            <g transform="translate(50, {y})">
                <rect width="700" height="{card_height}" rx="10" fill="white" filter="url(#shadow)"/>
                <text x="20" y="35" font-size="24">{info.get("icon", "📊")}</text>
                <text x="60" y="38" font-size="16" font-weight="bold" fill="#333">{info.get("name_zh", dim_key)}</text>
                <text x="60" y="60" font-size="12" fill="#666">{info.get("description_zh", "")[:30]}</text>
                <rect x="{bar_x}" y="30" width="{bar_width}" height="16" rx="8" fill="#e0e0e0"/>
                <rect x="{bar_x}" y="30" width="{filled_width}" height="16" rx="8" fill="{color}"/>
                <text x="{bar_x + bar_width + 20}" y="44" font-size="18" font-weight="bold" fill="{color}">{dim_score:.1f}</text>
                <text x="{bar_x + bar_width + 60}" y="44" font-size="12" fill="#999">/100</text>
            </g>''')
        
        # 生成建议列表
        recommendations = self.result.recommendations[:3] if self.result.recommendations else ["综述质量良好"]
        rec_items = []
        rec_y = 1050
        for i, rec in enumerate(recommendations):
            rec_text = rec[:40] + "..." if len(rec) > 40 else rec
            rec_items.append(f'<text x="70" y="{rec_y + i * 25}" font-size="12" fill="#333">• {rec_text}</text>')
        
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <linearGradient id="headerGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style="stop-color:{primary_color};stop-opacity:1" />
            <stop offset="100%" style="stop-color:#1976D2;stop-opacity:1" />
        </linearGradient>
        <filter id="shadow" x="-10%" y="-10%" width="120%" height="120%">
            <feDropShadow dx="0" dy="2" stdDeviation="4" flood-opacity="0.1"/>
        </filter>
    </defs>
    
    <!-- 背景 -->
    <rect width="100%" height="100%" fill="#f5f7fa"/>
    
    <!-- 头部 -->
    <rect width="100%" height="200" fill="url(#headerGradient)"/>
    <text x="50" y="60" font-size="28" font-weight="bold" fill="white">📊 综述质量评测报告</text>
    <text x="50" y="90" font-size="14" fill="rgba(255,255,255,0.8)">Survey Quality Evaluation Report</text>
    <text x="50" y="130" font-size="12" fill="rgba(255,255,255,0.7)">生成时间: {self.result.timestamp[:10]}</text>
    <text x="50" y="155" font-size="12" fill="rgba(255,255,255,0.7)">评测系统: MEKG Survey Evaluation System v2.0</text>
    
    <!-- 综合评分卡片 -->
    <g transform="translate(50, 230)">
        <rect width="700" height="200" rx="15" fill="white" filter="url(#shadow)"/>
        <text x="30" y="40" font-size="18" font-weight="bold" fill="#333">🎯 综合评分</text>
        
        <!-- 大分数 -->
        <text x="350" y="130" text-anchor="middle" font-size="72" font-weight="bold" fill="{score_color}">{score:.1f}</text>
        <text x="350" y="160" text-anchor="middle" font-size="16" fill="#666">/100 分</text>
        <text x="350" y="185" text-anchor="middle" font-size="14" fill="{score_color}">{grade}</text>
        
        <!-- 评分说明 -->
        <g transform="translate(550, 60)">
            <rect width="120" height="30" rx="15" fill="{score_color}" opacity="0.1"/>
            <text x="60" y="20" text-anchor="middle" font-size="12" fill="{score_color}">{grade}</text>
        </g>
    </g>
    
    <!-- 维度评分 -->
    <text x="50" y="460" font-size="18" font-weight="bold" fill="#333">📋 维度评分详情</text>
    {"".join(dim_cards)}
    
    <!-- 改进建议 -->
    <g transform="translate(50, 1000)">
        <rect width="700" height="150" rx="15" fill="white" filter="url(#shadow)"/>
        <text x="20" y="35" font-size="16" font-weight="bold" fill="#333">💡 改进建议</text>
        {"".join(rec_items)}
    </g>
    
    <!-- 底部 -->
    <text x="{width/2}" y="{height - 20}" text-anchor="middle" font-size="10" fill="#999">Powered by MEKG Survey Evaluation System</text>
</svg>'''
    
    # ==================== 辅助方法 ====================
    
    def _get_grade(self, score: float) -> str:
        """获取评级"""
        if score >= 90:
            return "🏆 优秀 (Excellent)"
        elif score >= 75:
            return "✅ 良好 (Good)"
        elif score >= 60:
            return "⚠️ 中等 (Fair)"
        else:
            return "❌ 待改进 (Needs Improvement)"
    
    def _get_grade_color(self, score: float) -> str:
        """获取评级颜色"""
        if score >= 90:
            return "#4CAF50"
        elif score >= 75:
            return "#8BC34A"
        elif score >= 60:
            return "#FF9800"
        else:
            return "#F44336"
    
    def _get_status_emoji(self, score: float) -> str:
        """获取状态表情"""
        if score >= 90:
            return "🏆"
        elif score >= 75:
            return "✅"
        elif score >= 60:
            return "⚠️"
        else:
            return "❌"
    
    def _get_dimension_weight(self, dim_key: str) -> float:
        """获取维度权重"""
        weights = {
            "reference_quality": 0.25,
            "structural_soundness": 0.20,
            "content_integrity": 0.25,
            "ethics_integrity": 0.15,
            "rich_media_quality": 0.15
        }
        return weights.get(dim_key, 0.0)


# ==================== 便捷函数 ====================

def generate_enhanced_report(
    result: EvaluationResult,
    output_dir: Path,
    config: Optional[ReportConfig] = None
) -> Dict[str, Path]:
    """
    生成增强版评测报告的便捷函数
    
    Args:
        result: 评测结果
        output_dir: 输出目录
        config: 报告配置
        
    Returns:
        生成的文件路径字典
    """
    generator = EnhancedReportGenerator(result, config)
    return generator.generate_all(output_dir)