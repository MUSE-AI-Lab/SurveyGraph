"""
HTML 报告生成器
===============

生成精美的 HTML 评测报告，支持中英文双语，可导出为 PNG/JPG 图片。
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass

from evaluation.core.result import EvaluationResult, DimensionResult


@dataclass
class HTMLReportConfig:
    """HTML 报告配置"""
    language: str = "en"  # "en" or "zh"
    width: int = 800  # 报告宽度（像素）
    include_all_metrics: bool = True  # 是否包含所有指标表格
    include_recommendations: bool = True  # 是否包含建议
    show_multi_model_details: bool = True  # 是否展示多模型评测详情


class HTMLReportGenerator:
    """HTML 报告生成器"""
    
    # 多语言文本配置
    TEXTS = {
        "en": {
            "title": "Survey Quality Evaluation Report",
            "subtitle": "Comprehensive Analysis of Academic Survey Quality",
            "overall_score": "Overall Score",
            "key_metrics": "Key Metrics Overview",
            "dimension_analysis": "Dimension Analysis",
            "strengths_weaknesses": "Strengths & Weaknesses",
            "strengths": "Strengths",
            "weaknesses": "Areas for Improvement",
            "recommendations": "Recommendations",
            "all_metrics": "Complete Metrics Summary",
            "generated": "Generated",
            "system_name": "MEKG Evaluation System v2.0",
            "powered_by": "Powered by Knowledge Graph & Multi-Model LLM Ensemble",
            "weight": "Weight",
            "score": "Score",
            "status": "Status",
            "category": "Category",
            "metric": "Metric",
            "excellent": "Excellent",
            "good": "Good", 
            "fair": "Fair",
            "poor": "Needs Improvement",
            "reference_quality": "Reference Quality",
            "structural_soundness": "Structural Soundness",
            "content_integrity": "Content Integrity",
            "ethics_integrity": "Ethics & Integrity",
            "rich_media_quality": "Rich Media Quality",
            "reference_quality_desc": "Coverage of core literature and citation accuracy",
            "structural_soundness_desc": "Organization structure and logical coherence",
            "content_integrity_desc": "Content accuracy, depth and writing quality",
            "ethics_integrity_desc": "Originality, societal impact and fairness",
            "rich_media_quality_desc": "Figure/table quality and visual effectiveness",
            "wcr": "WCR",
            "cc": "Community Coverage",
            "bibliographic_integrity": "Bibliographic Integrity",
            "citation_faithfulness": "Citation Faithfulness",
            "sc": "Structural Coherence",
            "structural_completeness": "Structural Completeness",
            "content_structure_fidelity": "Content-Structure Fidelity",
            "general_factualness": "General Factualness",
            "writing_quality": "Writing Quality",
            "scholarly_depth": "Scholarly Depth",
            "tc": "Temporal Coverage",
            "rubric_score": "Rubric Score",
            "originality": "Originality",
            "societal_impact": "Societal Impact",
            "fairness": "Fairness",
            "figure_quality": "Figure Quality",
            "table_quality": "Table Quality",
            "visual_content_alignment": "Visual-Content Alignment",
            "resource_accessibility": "Resource Accessibility",
            # 多模型评测相关
            "multi_model_evaluation": "Multi-Model Evaluation Details",
            "model_responses": "Model Responses",
            "fusion_result": "Fused Result",
            "fusion_strategy": "Fusion Strategy",
            "models_used": "Models Used",
            "view_llm_details": "View LLM Evaluation Details",
            "model_score": "Score",
            "model_analysis": "Analysis",
            "evaluations_count": "evaluations",
        },
        "zh": {
            "title": "综述质量评测报告",
            "subtitle": "学术综述质量综合分析",
            "overall_score": "综合评分",
            "key_metrics": "核心指标概览",
            "dimension_analysis": "维度分析",
            "strengths_weaknesses": "优势与不足",
            "strengths": "优势亮点",
            "weaknesses": "改进空间",
            "recommendations": "改进建议",
            "all_metrics": "完整指标汇总",
            "generated": "生成时间",
            "system_name": "MEKG 评测系统 v2.0",
            "powered_by": "基于知识图谱与多模型 LLM 集成评测",
            "weight": "权重",
            "score": "得分",
            "status": "状态",
            "category": "类别",
            "metric": "指标",
            "excellent": "优秀",
            "good": "良好",
            "fair": "中等",
            "poor": "待改进",
            "reference_quality": "引用质量",
            "structural_soundness": "结构完整性",
            "content_integrity": "内容质量",
            "ethics_integrity": "伦理与完整性",
            "rich_media_quality": "富媒体质量",
            "reference_quality_desc": "核心文献覆盖率与引用准确性",
            "structural_soundness_desc": "组织结构与逻辑连贯性",
            "content_integrity_desc": "内容准确性、深度与写作质量",
            "ethics_integrity_desc": "原创性、社会影响与公平性",
            "rich_media_quality_desc": "图表质量与视觉效果",
            "wcr": "加权中心性召回率",
            "cc": "社区覆盖率",
            "bibliographic_integrity": "文献完整性",
            "citation_faithfulness": "引用忠实度",
            "sc": "结构一致性",
            "structural_completeness": "结构完整性",
            "content_structure_fidelity": "内容-结构一致性",
            "general_factualness": "通用事实性",
            "writing_quality": "写作质量",
            "scholarly_depth": "学术深度",
            "tc": "时间覆盖率",
            "rubric_score": "评分细则得分",
            "originality": "原创性",
            "societal_impact": "社会影响讨论",
            "fairness": "公平性",
            "figure_quality": "图片质量",
            "table_quality": "表格质量",
            "visual_content_alignment": "视觉-内容对齐",
            "resource_accessibility": "资源可访问性",
            # 多模型评测相关
            "multi_model_evaluation": "多模型评测详情",
            "model_responses": "各模型响应",
            "fusion_result": "融合结果",
            "fusion_strategy": "融合策略",
            "models_used": "使用的模型",
            "view_llm_details": "查看 LLM 评测详情",
            "model_score": "评分",
            "model_analysis": "分析",
            "evaluations_count": "次评测",
        }
    }
    
    DIMENSION_CONFIG = {
        "reference_quality": {"icon": "fa-book-open", "icon_class": "reference", "weight": 0.25,
            "metrics": ["wcr", "cc", "bibliographic_integrity", "citation_faithfulness"]},
        "structural_soundness": {"icon": "fa-project-diagram", "icon_class": "structure", "weight": 0.20,
            "metrics": ["sc", "structural_completeness", "content_structure_fidelity"]},
        "content_integrity": {"icon": "fa-file-alt", "icon_class": "content", "weight": 0.25,
            "metrics": ["general_factualness", "writing_quality", "scholarly_depth", "tc", "rubric_score"]},
        "ethics_integrity": {"icon": "fa-balance-scale", "icon_class": "ethics", "weight": 0.15,
            "metrics": ["originality", "societal_impact", "fairness"]},
        "rich_media_quality": {"icon": "fa-images", "icon_class": "media", "weight": 0.15,
            "metrics": ["figure_quality", "table_quality", "visual_content_alignment", "resource_accessibility"]}
    }
    
    def __init__(self, result: EvaluationResult, config: Optional[HTMLReportConfig] = None, mekg_data: Optional[Dict] = None):
        self.result = result
        self.config = config or HTMLReportConfig()
        self.texts = self.TEXTS[self.config.language]
        self.mekg_data = mekg_data
    
    def generate(self) -> str:
        """生成 HTML 报告"""
        return self._build_html()
    
    def generate_both_languages(self, output_dir: Path) -> Dict[str, Path]:
        """生成中英文两个版本的报告"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        files = {}
        
        self.config.language = "en"
        self.texts = self.TEXTS["en"]
        en_path = output_dir / "evaluation_report_en.html"
        en_path.write_text(self.generate(), encoding='utf-8')
        files["en"] = en_path
        
        self.config.language = "zh"
        self.texts = self.TEXTS["zh"]
        zh_path = output_dir / "evaluation_report_zh.html"
        zh_path.write_text(self.generate(), encoding='utf-8')
        files["zh"] = zh_path
        
        return files
    
    def _get_grade_class(self, score: float) -> str:
        if score >= 90: return "excellent"
        elif score >= 75: return "good"
        elif score >= 60: return "fair"
        return "poor"
    
    def _get_grade_text(self, score: float) -> str:
        if score >= 90: return self.texts["excellent"]
        elif score >= 75: return self.texts["good"]
        elif score >= 60: return self.texts["fair"]
        return self.texts["poor"]
    
    def _format_percent(self, value: float) -> str:
        if value <= 1: return f"{value * 100:.1f}%"
        return f"{value:.1f}%"
    
    def _get_dimension_result(self, dim_key: str) -> Optional[DimensionResult]:
        """获取维度结果"""
        return getattr(self.result, dim_key, None)
    
    def _build_html(self) -> str:
        lang = "zh-CN" if self.config.language == "zh" else "en"
        return f'''<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.texts["title"]}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Noto+Sans+SC:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    {self._get_styles()}
</head>
<body>
    <div class="report-container" id="report">
        {self._build_header()}
        <main class="report-body">
            {self._build_score_section()}
            {self._build_key_metrics()}
            {self._build_dimensions()}
            {self._build_mekg_section() if self.mekg_data else ""}
            {self._build_analysis()}
            {self._build_recommendations() if self.config.include_recommendations else ""}
            {self._build_all_metrics() if self.config.include_all_metrics else ""}
        </main>
        {self._build_footer()}
    </div>
    {self._get_script()}
</body>
</html>'''

    def _build_header(self) -> str:
        survey_name = Path(self.result.survey_path).stem if self.result.survey_path else "Survey"
        survey_name = survey_name.replace("_", " ").title()
        timestamp = self.result.timestamp[:10] if self.result.timestamp else datetime.now().strftime("%Y-%m-%d")
        
        return f'''<header class="report-header">
            <div class="header-content">
                <div class="header-icon"><i class="fas fa-chart-line"></i></div>
                <h1 class="header-title">{self.texts["title"]}</h1>
                <p class="header-subtitle">{self.texts["subtitle"]}</p>
                <div class="header-meta">
                    <div class="header-meta-item"><i class="far fa-calendar"></i><span>{timestamp}</span></div>
                    <div class="header-meta-item"><i class="far fa-file-alt"></i><span>{survey_name}</span></div>
                    <div class="header-meta-item"><i class="fas fa-cog"></i><span>{self.texts["system_name"]}</span></div>
                </div>
            </div>
        </header>'''

    def _build_score_section(self) -> str:
        score = self.result.overall_score
        grade_class = self._get_grade_class(score)
        grade_text = self._get_grade_text(score)
        
        return f'''<section class="score-section">
            <div class="score-label"><i class="fas fa-star"></i> {self.texts["overall_score"]}</div>
            <div class="score-grade {grade_class}">
                <i class="fas fa-trophy"></i>
                <span>{grade_text}</span>
            </div>
            <div class="score-value {grade_class}">{score:.1f}</div>
            <span class="score-max">/ 100</span>
        </section>'''

    def _build_key_metrics(self) -> str:
        metrics = self.result.all_metrics
        wcr = self._format_percent(metrics.get("wcr", 0))
        cc = self._format_percent(metrics.get("cc", 0))
        sc = self._format_percent(metrics.get("sc", 0))
        wq = self._format_percent(metrics.get("writing_quality", 0))
        
        return f'''<section class="key-metrics">
            <h2 class="section-title"><i class="fas fa-chart-bar"></i>{self.texts["key_metrics"]}</h2>
            <div class="key-metrics-grid">
                <div class="key-metric-card">
                    <div class="key-metric-icon green"><i class="fas fa-book"></i></div>
                    <div class="key-metric-value">{wcr}</div>
                    <div class="key-metric-name">{self.texts["wcr"]}</div>
                </div>
                <div class="key-metric-card">
                    <div class="key-metric-icon blue"><i class="fas fa-sitemap"></i></div>
                    <div class="key-metric-value">{cc}</div>
                    <div class="key-metric-name">{self.texts["cc"]}</div>
                </div>
                <div class="key-metric-card">
                    <div class="key-metric-icon orange"><i class="fas fa-align-left"></i></div>
                    <div class="key-metric-value">{sc}</div>
                    <div class="key-metric-name">{self.texts["sc"]}</div>
                </div>
                <div class="key-metric-card">
                    <div class="key-metric-icon purple"><i class="fas fa-pen-fancy"></i></div>
                    <div class="key-metric-value">{wq}</div>
                    <div class="key-metric-name">{self.texts["writing_quality"]}</div>
                </div>
            </div>
        </section>'''

    def _build_dimensions(self) -> str:
        cards = []
        dim_order = ["reference_quality", "structural_soundness", "content_integrity", "ethics_integrity", "rich_media_quality"]
        
        for dim_key in dim_order:
            dim_result = self._get_dimension_result(dim_key)
            if dim_result:
                cards.append(self._build_dimension_card(dim_key, dim_result))
        
        return f'''<section class="dimensions-section">
            <h2 class="section-title"><i class="fas fa-layer-group"></i>{self.texts["dimension_analysis"]}</h2>
            <div class="dimensions-grid">{"".join(cards)}</div>
        </section>'''

    def _build_dimension_card(self, dim_key: str, dim_result: DimensionResult) -> str:
        config = self.DIMENSION_CONFIG[dim_key]
        score = dim_result.score * 100
        grade_class = self._get_grade_class(score)
        weight_pct = int(config["weight"] * 100)
        
        metrics_html = []
        for metric_key in config["metrics"]:
            if metric_key in dim_result.metrics:
                value = self._format_percent(dim_result.metrics[metric_key])
                name = self.texts.get(metric_key, metric_key)
                metrics_html.append(f'''<div class="metric-item">
                    <span class="metric-name"><i class="fas fa-circle"></i> {name}</span>
                    <span class="metric-value">{value}</span>
                </div>''')
        
        # 多模型评测详情
        multi_model_html = ""
        if self.config.show_multi_model_details and dim_result.details:
            multi_model_html = self._build_multi_model_details(dim_result.details)
        
        # 决策路径内容
        decision_path_html = ""
        if dim_result.details and "decision_path" in dim_result.details:
            path_data = dim_result.details["decision_path"]
            if isinstance(path_data, list):
                steps = "".join([f'<li>{step}</li>' for step in path_data])
                decision_path_html = f'''<div class="decision-path-container">
                    <div class="collapsible-trigger" onclick="toggleCollapsible(this)">
                        <i class="fas fa-chevron-right"></i> {self.texts.get("view_llm_details", "查看 LLM 决策路径与依据")}
                    </div>
                    <div class="collapsible-content">
                        <ul class="decision-steps">{steps}</ul>
                        {f'<div class="evidence-box"><strong>决策依据:</strong> {dim_result.details.get("evidence", "见上述步骤")}</div>' if "evidence" in dim_result.details else ""}
                    </div>
                </div>'''
        elif dim_result.details and "reasoning" in dim_result.details:
             decision_path_html = f'''<div class="decision-path-container">
                    <div class="collapsible-trigger" onclick="toggleCollapsible(this)">
                        <i class="fas fa-chevron-right"></i> {self.texts.get("view_llm_details", "查看 LLM 决策路径与依据")}
                    </div>
                    <div class="collapsible-content">
                        <div class="reasoning-text">{dim_result.details["reasoning"]}</div>
                    </div>
                </div>'''

        return f'''<div class="dimension-card">
            <div class="dimension-header">
                <div class="dimension-info">
                    <div class="dimension-icon {config["icon_class"]}"><i class="fas {config["icon"]}"></i></div>
                    <div>
                        <div class="dimension-name">{self.texts[dim_key]}</div>
                        <div class="dimension-desc">{self.texts[dim_key + "_desc"]}</div>
                    </div>
                </div>
                <div class="dimension-score">
                    <div class="dimension-score-value {grade_class}">{score:.1f}</div>
                    <div class="dimension-weight">{self.texts["weight"]}: {weight_pct}%</div>
                </div>
            </div>
            <div class="dimension-progress">
                <div class="dimension-progress-bar {grade_class}" style="width: {score}%"></div>
            </div>
            <div class="metrics-grid">{"".join(metrics_html)}</div>
            {multi_model_html}
            {decision_path_html}
        </div>'''
    
    def _build_multi_model_details(self, details: Dict) -> str:
        """构建多模型评测详情的 HTML"""
        # 查找多模型评测信息
        multi_model_data = None
        
        # 遍历 details 查找多模型评测数据
        for key, value in details.items():
            if isinstance(value, dict):
                if value.get("multi_model_evaluation"):
                    multi_model_data = value.get("multi_model_evaluation")
                    break
                elif key == "multi_model_evaluation":
                    multi_model_data = value
                    break
        
        # 也检查顶层的 multi_model_evaluation
        if not multi_model_data and "multi_model_evaluation" in details:
            multi_model_data = details["multi_model_evaluation"]
        
        if not multi_model_data or not multi_model_data.get("enabled"):
            return ""
        
        # 构建模型结果展示
        model_results_html = ""
        sample_results = multi_model_data.get("sample_model_results", [])
        
        if sample_results:
            # 取第一个样本的详细结果展示
            first_sample = sample_results[0] if sample_results else {}
            model_results = first_sample.get("model_results", {})
            
            if model_results:
                model_cards = []
                for model_name, result in model_results.items():
                    # 提取评分和分析
                    score_keys = [k for k in result.keys() if 'score' in k.lower()]
                    analysis = result.get("analysis", result.get("verification_summary", result.get("explanation", "")))
                    
                    # 构建评分展示
                    scores_html = ""
                    for sk in score_keys[:3]:  # 最多显示3个评分
                        score_val = result.get(sk, 0)
                        if isinstance(score_val, (int, float)):
                            score_display = f"{score_val * 100:.1f}%" if score_val <= 1 else f"{score_val:.1f}"
                            score_name = sk.replace("_score", "").replace("_", " ").title()
                            scores_html += f'<div class="model-score-item"><span>{score_name}:</span><strong>{score_display}</strong></div>'
                    
                    # 截断分析文本
                    analysis_str = str(analysis) if analysis else ""
                    analysis_display = analysis_str[:200] + "..." if len(analysis_str) > 200 else analysis_str
                    
                    model_cards.append(f'''
                        <div class="model-result-card">
                            <div class="model-name">
                                <i class="fas fa-robot"></i>
                                <span>{model_name}</span>
                            </div>
                            <div class="model-scores">{scores_html}</div>
                            <div class="model-analysis">{analysis_display}</div>
                        </div>
                    ''')
                
                model_results_html = f'''
                    <div class="model-results-grid">
                        {"".join(model_cards)}
                    </div>
                '''
        
        # 融合策略说明
        fusion_strategy = ""
        if sample_results:
            fusion_strategy = sample_results[0].get("fusion_strategy", "average")
        
        fusion_strategy_display = {
            "average": "简单平均" if self.config.language == "zh" else "Average",
            "weighted_average": "加权平均" if self.config.language == "zh" else "Weighted Average",
            "majority_vote": "多数投票" if self.config.language == "zh" else "Majority Vote",
            "median": "中位数" if self.config.language == "zh" else "Median",
            "max_confidence": "最高置信度" if self.config.language == "zh" else "Max Confidence"
        }.get(fusion_strategy, fusion_strategy.replace("_", " ").title() if fusion_strategy else "N/A")
        
        total_evals = multi_model_data.get("total_evaluations", 0)
        
        return f'''
        <div class="multi-model-container">
            <div class="collapsible-trigger multi-model-trigger" onclick="toggleCollapsible(this)">
                <i class="fas fa-chevron-right"></i>
                <i class="fas fa-layer-group"></i>
                <span>{self.texts.get("multi_model_evaluation", "多模型评测详情")}</span>
                <span class="multi-model-badge">{total_evals} {self.texts.get("evaluations_count", "次评测")}</span>
            </div>
            <div class="collapsible-content multi-model-content">
                <div class="fusion-info">
                    <div class="fusion-item">
                        <i class="fas fa-cogs"></i>
                        <span>{self.texts.get("fusion_strategy", "融合策略")}:</span>
                        <strong>{fusion_strategy_display}</strong>
                    </div>
                </div>
                <div class="model-responses-section">
                    <h4><i class="fas fa-comments"></i> {self.texts.get("model_responses", "各模型响应")}</h4>
                    {model_results_html if model_results_html else '<p style="color: var(--gray-500); font-style: italic;">暂无详细模型响应数据</p>'}
                </div>
            </div>
        </div>
        '''

    def _build_mekg_section(self) -> str:
        return f'''<section class="mekg-section">
            <h2 class="section-title"><i class="fas fa-share-alt"></i>MEKG 知识图谱概览</h2>
            <div class="mekg-container">
                <div id="mekg-viz" style="width: 100%; height: 400px; background: #f9fafb; border-radius: 12px; border: 1px solid var(--gray-200); position: relative; overflow: hidden;">
                    <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: var(--gray-400); text-align: center;">
                        <i class="fas fa-project-diagram" style="font-size: 48px; margin-bottom: 16px; opacity: 0.5;"></i>
                        <p>正在加载知识图谱可视化...</p>
                    </div>
                </div>
                <div class="mekg-stats" style="display: flex; gap: 24px; margin-top: 16px; font-size: 13px; color: var(--gray-600);">
                    <span><i class="fas fa-file-alt"></i> 论文节点: {self.mekg_data.get('papers_count', 'N/A')}</span>
                    <span><i class="fas fa-link"></i> 关系数量: {self.mekg_data.get('relations_count', 'N/A')}</span>
                    <span><i class="fas fa-tags"></i> 实体类型: {len(self.mekg_data.get('relation_stats', {}).get('by_type', {}))}</span>
                </div>
            </div>
        </section>'''

    def _build_analysis(self) -> str:
        strengths = []
        weaknesses = []
        
        for metric, value in self.result.all_metrics.items():
            score = value * 100 if value <= 1 else value
            name = self.texts.get(metric, metric)
            if score >= 85:
                strengths.append(f"{name} ({score:.1f}%)")
            elif score < 70:
                weaknesses.append(f"{name} ({score:.1f}%)")
        
        strengths_html = "".join([f'<li><i class="fas fa-check"></i><span>{s}</span></li>' for s in strengths[:4]])
        weaknesses_html = "".join([f'<li><i class="fas fa-times"></i><span>{w}</span></li>' for w in weaknesses[:4]])
        
        if not strengths_html:
            strengths_html = f'<li><i class="fas fa-check"></i><span>{self.texts["good"]}</span></li>'
        if not weaknesses_html:
            weaknesses_html = f'<li><i class="fas fa-check"></i><span>{self.texts["good"]}</span></li>'
        
        return f'''<section class="analysis-section">
            <h2 class="section-title"><i class="fas fa-search-plus"></i>{self.texts["strengths_weaknesses"]}</h2>
            <div class="analysis-grid">
                <div class="analysis-card strengths">
                    <div class="analysis-title"><i class="fas fa-check-circle"></i>{self.texts["strengths"]}</div>
                    <ul class="analysis-list">{strengths_html}</ul>
                </div>
                <div class="analysis-card weaknesses">
                    <div class="analysis-title"><i class="fas fa-exclamation-circle"></i>{self.texts["weaknesses"]}</div>
                    <ul class="analysis-list">{weaknesses_html}</ul>
                </div>
            </div>
        </section>'''

    def _build_recommendations(self) -> str:
        if not self.result.recommendations:
            return ""
        
        items = []
        lang = self.config.language
        
        for i, rec in enumerate(self.result.recommendations[:5], 1):
            # 支持双语建议格式: {"en": "...", "zh": "..."} 或纯字符串
            if isinstance(rec, dict):
                rec_text = rec.get(lang, rec.get("en", str(rec)))
            else:
                rec_text = rec
            
            items.append(f'''<li class="recommendation-item">
                <div class="recommendation-number">{i}</div>
                <div class="recommendation-text">{rec_text}</div>
            </li>''')
        
        return f'''<section class="recommendations">
            <h2 class="section-title"><i class="fas fa-lightbulb"></i>{self.texts["recommendations"]}</h2>
            <ul class="recommendation-list">{"".join(items)}</ul>
        </section>'''

    def _build_all_metrics(self) -> str:
        categories = {
            "reference_quality": ["wcr", "cc", "bibliographic_integrity", "citation_faithfulness"],
            "structural_soundness": ["sc", "structural_completeness", "content_structure_fidelity"],
            "content_integrity": ["general_factualness", "writing_quality", "scholarly_depth", "tc", "rubric_score"],
            "ethics_integrity": ["originality", "societal_impact", "fairness"],
            "rich_media_quality": ["figure_quality", "table_quality", "visual_content_alignment", "resource_accessibility"]
        }
        
        rows = []
        for cat_key, metrics in categories.items():
            config = self.DIMENSION_CONFIG[cat_key]
            rows.append(f'''<tr class="category-header">
                <td colspan="4"><i class="fas {config["icon"]}"></i> {self.texts[cat_key]}</td>
            </tr>''')
            
            for metric in metrics:
                if metric in self.result.all_metrics:
                    value = self.result.all_metrics[metric]
                    score = value * 100 if value <= 1 else value
                    grade_class = self._get_grade_class(score)
                    grade_text = self._get_grade_text(score)
                    rows.append(f'''<tr>
                        <td></td>
                        <td>{self.texts.get(metric, metric)}</td>
                        <td>{self._format_percent(value)}</td>
                        <td><span class="status-badge {grade_class}">{grade_text}</span></td>
                    </tr>''')
        
        return f'''<section class="all-metrics-section">
            <h2 class="section-title"><i class="fas fa-table"></i>{self.texts["all_metrics"]}</h2>
            <div class="metrics-table-container">
                <table class="metrics-table">
                    <thead><tr>
                        <th>{self.texts["category"]}</th>
                        <th>{self.texts["metric"]}</th>
                        <th>{self.texts["score"]}</th>
                        <th>{self.texts["status"]}</th>
                    </tr></thead>
                    <tbody>{"".join(rows)}</tbody>
                </table>
            </div>
        </section>'''

    def _build_footer(self) -> str:
        timestamp = self.result.timestamp if self.result.timestamp else datetime.now().isoformat()
        return f'''<footer class="report-footer">
            <div class="footer-logo"><i class="fas fa-chart-line"></i>{self.texts["system_name"]}</div>
            <p class="footer-desc">{self.texts["powered_by"]}</p>
            <p class="footer-meta">{self.texts["generated"]}: {timestamp}</p>
        </footer>'''

    def _get_styles(self) -> str:
        return '''<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--primary:#3b82f6;--primary-dark:#2563eb;--success:#10b981;--warning:#f59e0b;--danger:#ef4444;--gray-50:#f9fafb;--gray-100:#f3f4f6;--gray-200:#e5e7eb;--gray-300:#d1d5db;--gray-400:#9ca3af;--gray-500:#6b7280;--gray-600:#4b5563;--gray-700:#374151;--gray-800:#1f2937;--gray-900:#111827;--shadow-md:0 4px 6px -1px rgb(0 0 0/0.1),0 2px 4px -2px rgb(0 0 0/0.1)}
body{font-family:'Inter','Noto Sans SC',-apple-system,BlinkMacSystemFont,sans-serif;background:var(--gray-100);color:var(--gray-800);line-height:1.6}
.report-container{width:''' + str(self.config.width) + '''px;margin:0 auto;background:white;min-height:100vh;position:relative;}
.report-header{background:linear-gradient(135deg,var(--primary) 0%,var(--primary-dark) 100%);color:white;padding:48px 40px;position:relative;overflow:hidden}
.report-header::before{content:'';position:absolute;top:-50%;right:-20%;width:400px;height:400px;background:rgba(255,255,255,0.1);border-radius:50%}
.report-header::after{content:'';position:absolute;bottom:-30%;left:-10%;width:300px;height:300px;background:rgba(255,255,255,0.05);border-radius:50%}
.header-content{position:relative;z-index:1}
.header-icon{font-size:48px;margin-bottom:16px;opacity:0.9}
.header-title{font-size:32px;font-weight:700;margin-bottom:8px;letter-spacing:-0.5px}
.header-subtitle{font-size:16px;opacity:0.85;font-weight:400}
.header-meta{margin-top:24px;display:flex;gap:32px;font-size:13px;opacity:0.8;flex-wrap:wrap}
.header-meta-item{display:flex;align-items:center;gap:8px}
.report-body{padding:40px}
.score-section{background:var(--gray-50);border-radius:16px;padding:40px;margin-bottom:32px;text-align:center;border:1px solid var(--gray-200)}
.score-label{font-size:14px;color:var(--gray-500);text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;font-weight:600}
.score-value{font-size:80px;font-weight:700;line-height:1;margin-bottom:8px;margin-top:16px}
.score-value.excellent{color:var(--success)}.score-value.good{color:#22c55e}.score-value.fair{color:var(--warning)}.score-value.poor{color:var(--danger)}
.score-max{font-size:24px;color:var(--gray-400);font-weight:400}
.score-grade{display:inline-block;padding:8px 20px;border-radius:24px;font-size:14px;font-weight:600;margin-top:16px;vertical-align:middle}
.score-grade i{display:inline-block;margin-right:8px;vertical-align:middle}
.score-grade span{display:inline-block;vertical-align:middle}
.score-grade.excellent{background:#dcfce7;color:#166534}.score-grade.good{background:#dcfce7;color:#166534}.score-grade.fair{background:#fef3c7;color:#92400e}.score-grade.poor{background:#fee2e2;color:#991b1b}
.section-title{display:flex;align-items:center;gap:12px;font-size:20px;font-weight:600;color:var(--gray-800);margin-bottom:24px;padding-bottom:12px;border-bottom:2px solid var(--gray-200)}
.section-title i{color:var(--primary);font-size:22px}
.key-metrics{background:var(--gray-50);border-radius:16px;padding:32px;margin-bottom:40px;border:1px solid var(--gray-200)}
.key-metrics-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:20px}
.key-metric-card{background:white;border-radius:12px;padding:20px;text-align:center;border:1px solid var(--gray-200)}
.key-metric-icon{width:48px;height:48px;border-radius:12px;display:flex;align-items:center;justify-content:center;margin:0 auto 12px;font-size:20px}
.key-metric-icon.green{background:#dcfce7;color:#166534}.key-metric-icon.blue{background:#dbeafe;color:#1e40af}.key-metric-icon.orange{background:#fef3c7;color:#92400e}.key-metric-icon.purple{background:#f3e8ff;color:#6b21a8}
.key-metric-value{font-size:24px;font-weight:700;color:var(--gray-800);margin-bottom:4px}
.key-metric-name{font-size:12px;color:var(--gray-500);text-transform:uppercase;letter-spacing:0.5px}
.dimensions-grid{display:flex;flex-direction:column;gap:16px;margin-bottom:40px}
.dimension-card{background:white;border:1px solid var(--gray-200);border-radius:12px;padding:24px;transition:all 0.2s ease}
.dimension-card:hover{box-shadow:var(--shadow-md);border-color:var(--gray-300)}
.dimension-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.dimension-info{display:flex;align-items:center;gap:12px}
.dimension-icon{width:44px;height:44px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px;color:white}
.dimension-icon.reference{background:linear-gradient(135deg,#10b981,#059669)}.dimension-icon.structure{background:linear-gradient(135deg,#3b82f6,#2563eb)}.dimension-icon.content{background:linear-gradient(135deg,#f59e0b,#d97706)}.dimension-icon.ethics{background:linear-gradient(135deg,#8b5cf6,#7c3aed)}.dimension-icon.media{background:linear-gradient(135deg,#ec4899,#db2777)}
.dimension-name{font-size:16px;font-weight:600;color:var(--gray-800)}
.dimension-desc{font-size:13px;color:var(--gray-500);margin-top:2px}
.dimension-score{text-align:right}
.dimension-score-value{font-size:28px;font-weight:700}
.dimension-score-value.excellent{color:var(--success)}.dimension-score-value.good{color:#22c55e}.dimension-score-value.fair{color:var(--warning)}.dimension-score-value.poor{color:var(--danger)}
.dimension-weight{font-size:12px;color:var(--gray-400)}
.dimension-progress{height:8px;background:var(--gray-200);border-radius:4px;overflow:hidden;margin-bottom:16px}
.dimension-progress-bar{height:100%;border-radius:4px;transition:width 0.5s ease}
.dimension-progress-bar.excellent{background:linear-gradient(90deg,#10b981,#34d399)}.dimension-progress-bar.good{background:linear-gradient(90deg,#22c55e,#4ade80)}.dimension-progress-bar.fair{background:linear-gradient(90deg,#f59e0b,#fbbf24)}.dimension-progress-bar.poor{background:linear-gradient(90deg,#ef4444,#f87171)}
.metrics-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-bottom:16px}
.decision-path-container{margin-top:16px;border-top:1px solid var(--gray-100);padding-top:12px}
.collapsible-trigger{font-size:13px;color:var(--primary);cursor:pointer;display:flex;align-items:center;gap:8px;font-weight:500;user-select:none}
.collapsible-trigger i{transition:transform 0.2s ease;font-size:10px}
.collapsible-trigger.active i{transform:rotate(90deg)}
.collapsible-content{display:none;margin-top:12px;padding:12px;background:var(--gray-50);border-radius:8px;font-size:13px;color:var(--gray-700)}
.report-container.screenshot-mode .collapsible-content{display:block !important}
.report-container.screenshot-mode .collapsible-trigger i{transform:rotate(90deg)}
.decision-steps{padding-left:20px;margin-bottom:12px}
.decision-steps li{margin-bottom:6px}
.evidence-box{padding:10px;background:white;border-left:3px solid var(--primary);font-style:italic}
.metric-item{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:var(--gray-50);border-radius:8px;font-size:13px}
.metric-name{color:var(--gray-600);display:flex;align-items:center;gap:6px}
.metric-name i{font-size:8px;color:var(--gray-400)}
.metric-value{font-weight:600;color:var(--gray-800)}
.analysis-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:24px;margin-bottom:40px}
.analysis-card{border-radius:12px;padding:24px;border:1px solid}
.analysis-card.strengths{background:#f0fdf4;border-color:#bbf7d0}
.analysis-card.weaknesses{background:#fef2f2;border-color:#fecaca}
.analysis-title{display:flex;align-items:center;gap:8px;font-size:16px;font-weight:600;margin-bottom:16px}
.analysis-card.strengths .analysis-title{color:#166534}
.analysis-card.weaknesses .analysis-title{color:#991b1b}
.analysis-list{list-style:none}
.analysis-list li{display:flex;align-items:flex-start;gap:10px;padding:8px 0;font-size:14px;color:var(--gray-700)}
.analysis-list li i{margin-top:3px;font-size:12px}
.analysis-card.strengths .analysis-list li i{color:var(--success)}
.analysis-card.weaknesses .analysis-list li i{color:var(--danger)}
.recommendations{background:linear-gradient(135deg,#eff6ff 0%,#dbeafe 100%);border-radius:16px;padding:32px;margin-bottom:40px;border:1px solid #bfdbfe}
.recommendations .section-title{border-bottom-color:#93c5fd}
.recommendations .section-title i{color:#2563eb}
.recommendation-list{list-style:none}
.recommendation-item{display:flex;align-items:flex-start;gap:16px;padding:16px;background:white;border-radius:10px;margin-bottom:12px;border:1px solid #bfdbfe}
.recommendation-item:last-child{margin-bottom:0}
.recommendation-number{width:28px;height:28px;border-radius:8px;background:var(--primary);color:white;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:600;flex-shrink:0}
.recommendation-text{font-size:14px;color:var(--gray-700);line-height:1.6}
.metrics-table-container{overflow-x:auto;border-radius:12px;border:1px solid var(--gray-200);margin-bottom:40px}
.metrics-table{width:100%;border-collapse:collapse;font-size:14px}
.metrics-table thead{background:var(--gray-100)}
.metrics-table th{padding:14px 16px;text-align:left;font-weight:600;color:var(--gray-700);border-bottom:2px solid var(--gray-200)}
.metrics-table td{padding:12px 16px;border-bottom:1px solid var(--gray-100);color:var(--gray-700)}
.metrics-table tbody tr:hover{background:var(--gray-50)}
.metrics-table .category-header{background:var(--gray-50)}
.metrics-table .category-header td{font-weight:600;color:var(--gray-800);padding:10px 16px}
.metrics-table .category-header i{margin-right:8px;color:var(--primary)}
.status-badge{display:inline-block;padding:4px 10px;border-radius:12px;font-size:12px;font-weight:500}
.status-badge.excellent{background:#dcfce7;color:#166534}.status-badge.good{background:#dbeafe;color:#1e40af}.status-badge.fair{background:#fef3c7;color:#92400e}.status-badge.poor{background:#fee2e2;color:#991b1b}

/* 多模型评测样式 */
.multi-model-container{margin-top:16px;border-top:1px solid var(--gray-100);padding-top:12px}
.multi-model-trigger{background:linear-gradient(135deg,#f0f9ff 0%,#e0f2fe 100%);padding:12px 16px;border-radius:8px;border:1px solid #bae6fd}
.multi-model-trigger i.fa-layer-group{color:#0284c7;margin-left:4px}
.multi-model-badge{background:#0284c7;color:white;padding:2px 8px;border-radius:12px;font-size:11px;margin-left:auto}
.multi-model-content{background:white;border:1px solid var(--gray-200);border-radius:8px;padding:16px;margin-top:8px}
.fusion-info{display:flex;gap:24px;padding:12px 16px;background:linear-gradient(135deg,#fef3c7 0%,#fde68a 100%);border-radius:8px;margin-bottom:16px;flex-wrap:wrap}
.fusion-item{display:flex;align-items:center;gap:8px;font-size:13px;color:#92400e}
.fusion-item i{color:#d97706}
.fusion-item strong{color:#78350f}
.model-responses-section h4{font-size:14px;color:var(--gray-700);margin-bottom:12px;display:flex;align-items:center;gap:8px}
.model-responses-section h4 i{color:var(--primary)}
.model-results-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.model-result-card{background:var(--gray-50);border:1px solid var(--gray-200);border-radius:8px;padding:12px;transition:all 0.2s ease}
.model-result-card:hover{border-color:var(--primary);box-shadow:0 2px 8px rgba(59,130,246,0.1)}
.model-name{display:flex;align-items:center;gap:8px;font-weight:600;color:var(--gray-800);margin-bottom:8px;font-size:13px}
.model-name i{color:var(--primary)}
.model-scores{display:flex;flex-direction:column;gap:4px;margin-bottom:8px}
.model-score-item{display:flex;justify-content:space-between;font-size:12px;color:var(--gray-600)}
.model-score-item strong{color:var(--gray-800)}
.model-analysis{font-size:12px;color:var(--gray-500);line-height:1.5;padding-top:8px;border-top:1px solid var(--gray-200)}

.report-footer{background:var(--gray-800);color:white;padding:32px 40px;text-align:center}
.footer-logo{font-size:18px;font-weight:600;margin-bottom:8px;display:flex;align-items:center;justify-content:center;gap:10px}
.footer-logo i{color:var(--primary)}
.footer-desc{font-size:13px;color:var(--gray-400);margin-bottom:16px}
.footer-meta{font-size:12px;color:var(--gray-500)}
@media print{.report-container{width:100%}}
</style>'''

    def _get_script(self) -> str:
        mekg_json = json.dumps(self.mekg_data) if self.mekg_data else "null"
        return f'''<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<script>
function toggleCollapsible(el) {{
    el.classList.toggle('active');
    const content = el.nextElementSibling;
    if (content.style.display === 'block') {{
        content.style.display = 'none';
    }} else {{
        content.style.display = 'block';
    }}
}}

// 保存为图片功能 (需要 html2canvas 库)
async function saveAsImage(format) {{
    if (typeof html2canvas === 'undefined') {{
        const script = document.createElement('script');
        script.src = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
        script.onload = () => captureAndSave(format);
        document.head.appendChild(script);
    }} else {{
        captureAndSave(format);
    }}
}}

async function captureAndSave(format) {{
    const element = document.getElementById('report');
    
    // 截图前进入截图模式，展开所有折叠内容
    element.classList.add('screenshot-mode');
    
    // 等待渲染
    await new Promise(resolve => setTimeout(resolve, 500));
    
    const canvas = await html2canvas(element, {{
        scale: 2,
        useCORS: true,
        logging: false,
        backgroundColor: '#ffffff'
    }});
    
    // 截图后退出截图模式
    element.classList.remove('screenshot-mode');
    
    const link = document.createElement('a');
    link.download = 'evaluation_report.' + (format || 'png');
    link.href = canvas.toDataURL('image/' + (format || 'png'), 0.95);
    link.click();
}}

// MEKG 可视化逻辑
const mekgData = {mekg_json};
if (mekgData && document.getElementById('mekg-viz')) {{
    renderMEKG(mekgData);
}}

function renderMEKG(data) {{
    const width = document.getElementById('mekg-viz').clientWidth;
    const height = 400;
    
    const svg = d3.select("#mekg-viz")
        .html("")
        .append("svg")
        .attr("width", width)
        .attr("height", height);

    // 简单的力导向图实现
    const nodes = data.papers ? data.papers.slice(0, 50).map(p => ({{id: p.id, title: p.title, group: p.category}})) : [];
    const links = data.relations ? data.relations.filter(r =>
        nodes.find(n => n.id === r.source) && nodes.find(n => n.id === r.target)
    ).slice(0, 100) : [];

    const simulation = d3.forceSimulation(nodes)
        .force("link", d3.forceLink(links).id(d => d.id).distance(50))
        .force("charge", d3.forceManyBody().strength(-100))
        .force("center", d3.forceCenter(width / 2, height / 2));

    const link = svg.append("g")
        .attr("stroke", "#999")
        .attr("stroke-opacity", 0.6)
        .selectAll("line")
        .data(links)
        .join("line")
        .attr("stroke-width", 1);

    const node = svg.append("g")
        .attr("stroke", "#fff")
        .attr("stroke-width", 1.5)
        .selectAll("circle")
        .data(nodes)
        .join("circle")
        .attr("r", 5)
        .attr("fill", (d) => {{
            const colors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"];
            return colors[Math.abs(d.group?.length || 0) % colors.length];
        }})
        .call(d3.drag()
            .on("start", dragstarted)
            .on("drag", dragged)
            .on("end", dragended));

    node.append("title").text(d => d.title);

    simulation.on("tick", () => {{
        link
            .attr("x1", d => d.source.x)
            .attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x)
            .attr("y2", d => d.target.y);

        node
            .attr("cx", d => d.x)
            .attr("cy", d => d.y);
    }});

    function dragstarted(event) {{
        if (!event.active) simulation.alphaTarget(0.3).restart();
        event.subject.fx = event.subject.x;
        event.subject.fy = event.subject.y;
    }}

    function dragged(event) {{
        event.subject.fx = event.x;
        event.subject.fy = event.y;
    }}

    function dragended(event) {{
        if (!event.active) simulation.alphaTarget(0);
        event.subject.fx = null;
        event.subject.fy = null;
    }}
}}
</script>'''


def generate_html_report(
    result: EvaluationResult,
    output_dir: Path,
    config: Optional[HTMLReportConfig] = None,
    mekg_data: Optional[Dict] = None
) -> Dict[str, Path]:
    """
    生成 HTML 评测报告的便捷函数
    
    Args:
        result: 评测结果
        output_dir: 输出目录
        config: 报告配置
        mekg_data: MEKG 知识图谱数据
        
    Returns:
        生成的文件路径字典
    """
    generator = HTMLReportGenerator(result, config, mekg_data)
    return generator.generate_both_languages(output_dir)