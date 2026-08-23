"""
富媒体质量评测器
================

评估综述的富媒体质量，包括:
- Figure Quality: 图片质量
- Table Quality: 表格质量
- Visual-Content Alignment: 视觉-内容对齐
- Resource Accessibility: 资源可访问性

注意：此评测器涉及可视化内容评估，需要多模态能力。
因此，此评测器始终使用 advanced_model（多模态模型），
不参与多模型 T2T 评测融合。
"""

import logging
import re
import requests
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from evaluation.core.base_evaluator import BaseEvaluator
from evaluation.config import EvaluationConfig, RICH_MEDIA_QUALITY_WEIGHTS
from evaluation.utils.latex_parser import (
    extract_figures_and_tables,
    extract_urls,
    extract_text_from_latex
)
from evaluation.utils.metrics import aggregate_scores
from evaluation.utils.llm_client import (
    call_llm,
    call_llm_json,
    parse_json_response,
    MEDIA_QUALITY_PROMPT
)


logger = logging.getLogger(__name__)


class MediaEvaluator(BaseEvaluator):
    """富媒体质量评测器"""
    
    @property
    def name(self) -> str:
        return "Rich Media Quality"
    
    @property
    def weight(self) -> float:
        return self.config.dimension_weights.get("rich_media_quality", 0.15)
    
    def evaluate(
        self,
        survey_content: str,
        survey_outline: Optional[Dict] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行富媒体质量评测
        
        Args:
            survey_content: 综述内容
            survey_outline: 综述大纲（可选）
            
        Returns:
            评测结果
        """
        self._log_start()
        
        # 提取图表
        media = extract_figures_and_tables(survey_content)
        figures = media.get("figures", [])
        tables = media.get("tables", [])
        
        logger.info(f"提取到 {len(figures)} 个图片, {len(tables)} 个表格")
        
        metrics = {}
        details = {}
        
        # 1. Figure Quality - 图片质量
        if figures:
            if self.config.use_llm:
                fq, fq_details = self._calculate_figure_quality(figures)
            else:
                fq, fq_details = self._calculate_figure_quality_basic(figures)
            metrics["figure_quality"] = fq
            details["figure_quality"] = fq_details
        else:
            metrics["figure_quality"] = 0.0
            details["figure_quality"] = {"message": "No figures found"}
        
        # 2. Table Quality - 表格质量
        if tables:
            if self.config.use_llm:
                tq, tq_details = self._calculate_table_quality(tables)
            else:
                tq, tq_details = self._calculate_table_quality_basic(tables)
            metrics["table_quality"] = tq
            details["table_quality"] = tq_details
        else:
            metrics["table_quality"] = 0.0
            details["table_quality"] = {"message": "No tables found"}
        
        # 3. Visual-Content Alignment - 视觉-内容对齐
        if (figures or tables) and self.config.use_llm:
            vca, vca_details = self._calculate_visual_content_alignment(
                survey_content, figures, tables
            )
            metrics["visual_content_alignment"] = vca
            details["visual_content_alignment"] = vca_details
        else:
            metrics["visual_content_alignment"] = 0.5
            details["visual_content_alignment"] = {"message": "Skipped"}
        
        # 4. Resource Accessibility - 资源可访问性
        ra, ra_details = self._calculate_resource_accessibility(survey_content)
        metrics["resource_accessibility"] = ra
        details["resource_accessibility"] = ra_details
        
        # 计算综合分数
        score = aggregate_scores(metrics, RICH_MEDIA_QUALITY_WEIGHTS)
        
        self._log_end(score)
        
        return {
            "score": score,
            "metrics": metrics,
            "details": details,
            "statistics": {
                "figure_count": len(figures),
                "table_count": len(tables)
            }
        }
    
    def _calculate_figure_quality(
        self,
        figures: List[Dict]
    ) -> Tuple[float, Dict]:
        """
        使用LLM评估图片质量
        """
        if not figures:
            return 0.0, {"message": "No figures to evaluate"}
        
        # 评估前几个图片
        sample_figures = figures[:3]
        scores = []
        figure_details = []
        
        for fig in sample_figures:
            caption = fig.get("caption", "")
            
            if not caption:
                scores.append(0.3)
                figure_details.append({
                    "caption": "(no caption)",
                    "score": 0.3,
                    "issue": "Missing caption"
                })
                continue
            
            try:
                prompt = MEDIA_QUALITY_PROMPT.format(
                    media_type="Figure",
                    caption=caption[:200],  # 限制caption长度
                    context="Academic survey paper"
                )
                
                result = call_llm_json(prompt, max_json_retries=2)
                
                score = result.get("overall_quality_score", 0.5)
                scores.append(score)
                
                figure_details.append({
                    "caption": caption[:100],
                    "score": score,
                    "analysis": result.get("analysis", "")
                })
                
            except Exception as e:
                logger.warning(f"图片质量评估失败: {e}")
                scores.append(0.5)
        
        avg_score = sum(scores) / len(scores) if scores else 0.0
        
        return avg_score, {
            "figures_evaluated": len(sample_figures),
            "figure_details": figure_details
        }
    
    def _calculate_figure_quality_basic(
        self,
        figures: List[Dict]
    ) -> Tuple[float, Dict]:
        """
        基础图片质量评估（不使用LLM）
        """
        if not figures:
            return 0.0, {"message": "No figures to evaluate"}
        
        scores = []
        issues = []
        
        for fig in figures:
            score = 0.5  # 基础分
            
            # 有caption加分
            if fig.get("caption"):
                score += 0.3
            else:
                issues.append("Figure without caption")
            
            # 有label加分
            if fig.get("label"):
                score += 0.1
            
            # 有图片路径加分
            if fig.get("path"):
                score += 0.1
            
            scores.append(min(1.0, score))
        
        avg_score = sum(scores) / len(scores) if scores else 0.0
        
        return avg_score, {
            "figures_evaluated": len(figures),
            "figures_with_caption": sum(1 for f in figures if f.get("caption")),
            "issues": issues[:5]
        }
    
    def _calculate_table_quality(
        self,
        tables: List[Dict]
    ) -> Tuple[float, Dict]:
        """
        使用LLM评估表格质量
        """
        if not tables:
            return 0.0, {"message": "No tables to evaluate"}
        
        sample_tables = tables[:3]
        scores = []
        table_details = []
        
        for tbl in sample_tables:
            caption = tbl.get("caption", "")
            
            if not caption:
                scores.append(0.3)
                table_details.append({
                    "caption": "(no caption)",
                    "score": 0.3,
                    "issue": "Missing caption"
                })
                continue
            
            try:
                prompt = MEDIA_QUALITY_PROMPT.format(
                    media_type="Table",
                    caption=caption[:200],  # 限制caption长度
                    context="Academic survey paper"
                )
                
                result = call_llm_json(prompt, max_json_retries=2)
                
                score = result.get("overall_quality_score", 0.5)
                scores.append(score)
                
                table_details.append({
                    "caption": caption[:100],
                    "score": score,
                    "analysis": result.get("analysis", "")
                })
                
            except Exception as e:
                logger.warning(f"表格质量评估失败: {e}")
                scores.append(0.5)
        
        avg_score = sum(scores) / len(scores) if scores else 0.0
        
        return avg_score, {
            "tables_evaluated": len(sample_tables),
            "table_details": table_details
        }
    
    def _calculate_table_quality_basic(
        self,
        tables: List[Dict]
    ) -> Tuple[float, Dict]:
        """
        基础表格质量评估（不使用LLM）
        """
        if not tables:
            return 0.0, {"message": "No tables to evaluate"}
        
        scores = []
        issues = []
        
        for tbl in tables:
            score = 0.5
            
            if tbl.get("caption"):
                score += 0.3
            else:
                issues.append("Table without caption")
            
            if tbl.get("label"):
                score += 0.1
            
            # 检查表格内容复杂度
            content = tbl.get("content", "")
            if "\\hline" in content or "\\toprule" in content:
                score += 0.1
            
            scores.append(min(1.0, score))
        
        avg_score = sum(scores) / len(scores) if scores else 0.0
        
        return avg_score, {
            "tables_evaluated": len(tables),
            "tables_with_caption": sum(1 for t in tables if t.get("caption")),
            "issues": issues[:5]
        }
    
    def _calculate_visual_content_alignment(
        self,
        survey_content: str,
        figures: List[Dict],
        tables: List[Dict]
    ) -> Tuple[float, Dict]:
        """
        评估视觉-内容对齐度
        """
        all_media = figures[:2] + tables[:2]
        
        if not all_media:
            return 0.5, {"message": "No media to evaluate"}
        
        scores = []
        alignment_details = []
        
        for media in all_media:
            caption = media.get("caption", "")
            label = media.get("label", "")
            media_type = media.get("type", "figure")
            
            if not caption:
                scores.append(0.3)
                continue
            
            # 查找引用该图表的上下文
            context = self._find_media_context(survey_content, label, caption)
            
            if not context:
                scores.append(0.5)
                alignment_details.append({
                    "caption": caption[:50],
                    "score": 0.5,
                    "issue": "No reference found in text"
                })
                continue
            
            try:
                prompt = f"""Evaluate {media_type} alignment with content.

Caption: {caption[:150]}
Text: {context[:300]}

Output ONLY valid JSON (no markdown):
{{"alignment_score":0.8,"is_referenced":true,"is_relevant":true,"analysis":"Brief reason"}}
"""
                
                result = call_llm_json(prompt, max_json_retries=2)
                
                score = result.get("alignment_score", 0.5)
                scores.append(score)
                
                alignment_details.append({
                    "caption": caption[:50],
                    "score": score,
                    "is_referenced": result.get("is_referenced", False),
                    "is_relevant": result.get("is_relevant", False)
                })
                
            except Exception as e:
                logger.warning(f"对齐度评估失败: {e}")
                scores.append(0.5)
        
        avg_score = sum(scores) / len(scores) if scores else 0.5
        
        return avg_score, {
            "media_evaluated": len(all_media),
            "alignment_details": alignment_details
        }
    
    def _find_media_context(
        self,
        content: str,
        label: str,
        caption: str
    ) -> str:
        """查找图表的上下文"""
        # 尝试通过label查找引用
        if label:
            ref_pattern = rf'\\ref\{{{re.escape(label)}\}}'
            match = re.search(ref_pattern, content)
            if match:
                # 提取周围的文本
                start = max(0, match.start() - 300)
                end = min(len(content), match.end() + 300)
                return content[start:end]
        
        # 尝试通过caption关键词查找
        if caption:
            keywords = caption.split()[:3]
            for keyword in keywords:
                if len(keyword) > 4:
                    idx = content.lower().find(keyword.lower())
                    if idx != -1:
                        start = max(0, idx - 200)
                        end = min(len(content), idx + 200)
                        return content[start:end]
        
        return ""
    
    def _calculate_resource_accessibility(
        self,
        survey_content: str
    ) -> Tuple[float, Dict]:
        """
        评估资源可访问性
        
        检查URL链接的有效性
        """
        urls = extract_urls(survey_content)
        
        if not urls:
            return 1.0, {"message": "No URLs found", "total_urls": 0}
        
        # 检查URL有效性
        valid_count = 0
        invalid_urls = []
        
        def check_url(url: str) -> Tuple[str, bool]:
            try:
                response = requests.head(url, allow_redirects=True, timeout=5)
                return url, 200 <= response.status_code < 400
            except:
                return url, False
        
        # 并发检查URL
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(check_url, url): url for url in urls[:20]}
            
            for future in as_completed(futures):
                url, is_valid = future.result()
                if is_valid:
                    valid_count += 1
                else:
                    invalid_urls.append(url)
        
        checked_count = min(len(urls), 20)
        accessibility_score = valid_count / checked_count if checked_count > 0 else 1.0
        
        return accessibility_score, {
            "total_urls": len(urls),
            "checked_urls": checked_count,
            "valid_urls": valid_count,
            "invalid_urls": invalid_urls[:5]
        }