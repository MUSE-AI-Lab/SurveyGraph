"""
伦理与完整性评测器
==================

评估综述的伦理与完整性，包括:
- Originality: 原创性
- Societal Impact: 社会影响讨论
- Fairness: 公平性与偏见

支持多模型评测：
- 当配置启用多模型时，使用多个 T2T 模型进行评测并融合结果
- 提高评测的可靠性和稳定性
"""

import logging
import re
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

from evaluation.core.base_evaluator import BaseEvaluator
from evaluation.config import EvaluationConfig, ETHICS_INTEGRITY_WEIGHTS
from evaluation.utils.latex_parser import (
    extract_text_from_latex,
    extract_content_samples
)
from evaluation.utils.metrics import aggregate_scores
from evaluation.utils.llm_client import (
    call_llm,
    parse_json_response,
    call_multi_model_json,
    ETHICS_EVALUATION_PROMPT
)


logger = logging.getLogger(__name__)


# 伦理相关关键词
ETHICS_KEYWORDS = {
    "societal_impact": [
        "societal impact", "social impact", "ethical", "ethics",
        "responsible", "responsibility", "harm", "harmful",
        "misuse", "abuse", "risk", "danger", "concern"
    ],
    "fairness": [
        "bias", "biased", "fairness", "fair", "unfair",
        "discrimination", "discriminatory", "equity", "equitable",
        "inclusive", "inclusion", "diversity", "diverse"
    ],
    "limitation": [
        "limitation", "limited", "constraint", "challenge",
        "drawback", "weakness", "shortcoming", "caveat"
    ]
}


class EthicsEvaluator(BaseEvaluator):
    """伦理与完整性评测器"""
    
    @property
    def name(self) -> str:
        return "Ethics & Integrity"
    
    @property
    def weight(self) -> float:
        return self.config.dimension_weights.get("ethics_integrity", 0.15)
    
    def evaluate(
        self,
        survey_content: str,
        survey_outline: Optional[Dict] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行伦理与完整性评测
        
        Args:
            survey_content: 综述内容
            survey_outline: 综述大纲（可选）
            
        Returns:
            评测结果
        """
        self._log_start()
        
        metrics = {}
        details = {}
        
        # 1. Originality - 原创性
        originality, originality_details = self._calculate_originality(survey_content)
        metrics["originality"] = originality
        details["originality"] = originality_details
        
        # 2. Societal Impact - 社会影响讨论
        if self.config.use_llm:
            impact, impact_details = self._calculate_societal_impact(survey_content)
            metrics["societal_impact"] = impact
            details["societal_impact"] = impact_details
        else:
            # 使用关键词检测
            impact, impact_details = self._calculate_societal_impact_keywords(survey_content)
            metrics["societal_impact"] = impact
            details["societal_impact"] = impact_details
        
        # 3. Fairness - 公平性与偏见
        if self.config.use_llm:
            fairness, fairness_details = self._calculate_fairness(survey_content)
            metrics["fairness"] = fairness
            details["fairness"] = fairness_details
        else:
            fairness, fairness_details = self._calculate_fairness_keywords(survey_content)
            metrics["fairness"] = fairness
            details["fairness"] = fairness_details
        
        # 计算综合分数
        score = aggregate_scores(metrics, ETHICS_INTEGRITY_WEIGHTS)
        
        self._log_end(score)
        
        return {
            "score": score,
            "metrics": metrics,
            "details": details
        }
    
    def _calculate_originality(
        self,
        survey_content: str
    ) -> Tuple[float, Dict]:
        """
        计算原创性
        
        检测过度引用、重复内容等
        """
        text = extract_text_from_latex(survey_content)
        
        # 统计引用密度
        citation_count = len(re.findall(r'\[[^\]]+\]', text))
        word_count = len(text.split())
        
        if word_count == 0:
            return 0.5, {"message": "No content to analyze"}
        
        citation_density = citation_count / word_count
        
        # 检测重复段落
        paragraphs = [p.strip() for p in text.split('\n\n') if len(p.strip()) > 100]
        unique_paragraphs = set()
        duplicate_count = 0
        
        for para in paragraphs:
            # 简化段落用于比较
            simplified = ' '.join(para.lower().split()[:20])
            if simplified in unique_paragraphs:
                duplicate_count += 1
            else:
                unique_paragraphs.add(simplified)
        
        duplicate_ratio = duplicate_count / len(paragraphs) if paragraphs else 0
        
        # 计算原创性分数
        # 引用密度过高或过低都不好
        if citation_density > 0.1:  # 过度引用
            citation_score = max(0, 1 - (citation_density - 0.1) * 5)
        elif citation_density < 0.02:  # 引用太少
            citation_score = max(0, citation_density / 0.02)
        else:
            citation_score = 1.0
        
        # 重复内容惩罚
        duplicate_penalty = duplicate_ratio * 0.5
        
        originality_score = max(0, citation_score - duplicate_penalty)
        
        return originality_score, {
            "citation_count": citation_count,
            "word_count": word_count,
            "citation_density": round(citation_density, 4),
            "paragraph_count": len(paragraphs),
            "duplicate_paragraphs": duplicate_count,
            "duplicate_ratio": round(duplicate_ratio, 4)
        }
    
    def _calculate_societal_impact(
        self,
        survey_content: str
    ) -> Tuple[float, Dict]:
        """
        使用LLM评估社会影响讨论（支持多模型评测）
        """
        samples = extract_content_samples(survey_content, num_samples=5, sample_length=800)
        
        if not samples:
            return 0.0, {"message": "No content to analyze"}
        
        content_excerpt = "\n\n---\n\n".join(samples)
        
        try:
            prompt = ETHICS_EVALUATION_PROMPT.format(content_excerpts=content_excerpt)
            
            multi_model_details = {}
            
            # 检查是否启用多模型评测
            if self.config.should_use_multi_model():
                multi_result = call_multi_model_json(
                    prompt=prompt,
                    models=self.config.t2t_models,
                    fusion_strategy=self.config.fusion_strategy
                )
                result = multi_result.get("fused_result", {})
                logger.debug(f"多模型社会影响评估: 使用 {len(multi_result.get('models_used', []))} 个模型")
                
                multi_model_details = {
                    "enabled": True,
                    "models_used": multi_result.get("models_used", []),
                    "fusion_strategy": multi_result.get("fusion_strategy", ""),
                    "model_results": multi_result.get("model_results", {})
                }
            else:
                response = call_llm(prompt, response_format="json_object", max_retries=10)
                result = parse_json_response(response)
                multi_model_details = {"enabled": False}
            
            impact_score = result.get("societal_impact_score", 0.0)
            
            details = {
                "analysis": result.get("analysis", ""),
                "responsible_scholarship_score": result.get("responsible_scholarship_score", 0.0)
            }
            
            # 添加多模型评测详情
            if multi_model_details.get("enabled"):
                details["multi_model_evaluation"] = multi_model_details
            
            return impact_score, details
            
        except Exception as e:
            logger.warning(f"社会影响评估失败: {e}")
            return self._calculate_societal_impact_keywords(survey_content)
    
    def _calculate_societal_impact_keywords(
        self,
        survey_content: str
    ) -> Tuple[float, Dict]:
        """
        使用关键词检测社会影响讨论
        
        注意：对于技术综述，我们采用宽松的评分标准。
        只要综述讨论了技术局限性或挑战，就认为具有一定的社会影响意识。
        """
        text = extract_text_from_latex(survey_content).lower()
        
        found_keywords = []
        for keyword in ETHICS_KEYWORDS["societal_impact"]:
            if keyword in text:
                found_keywords.append(keyword)
        
        # 检查是否有专门的伦理/影响章节
        has_ethics_section = any(
            section in text for section in
            ["ethical consideration", "societal impact", "broader impact", "limitation"]
        )
        
        # 检查是否讨论了技术局限性（对技术综述来说这也是一种负责任的态度）
        has_limitation_discussion = any(
            keyword in text for keyword in ETHICS_KEYWORDS["limitation"]
        )
        
        # 计算分数 - 放宽标准
        # 基础分：技术综述默认给0.5的基础分（因为技术综述不强制要求伦理讨论）
        base_score = 0.5
        
        # 关键词加分
        keyword_bonus = min(len(found_keywords) / 8, 0.3)  # 最多加0.3
        
        # 伦理章节加分
        section_bonus = 0.15 if has_ethics_section else 0.0
        
        # 局限性讨论加分（技术综述讨论局限性也是负责任的表现）
        limitation_bonus = 0.1 if has_limitation_discussion else 0.0
        
        impact_score = min(1.0, base_score + keyword_bonus + section_bonus + limitation_bonus)
        
        return impact_score, {
            "found_keywords": found_keywords,
            "has_ethics_section": has_ethics_section,
            "has_limitation_discussion": has_limitation_discussion,
            "keyword_count": len(found_keywords),
            "note": "技术综述采用宽松评分标准"
        }
    
    def _calculate_fairness(
        self,
        survey_content: str
    ) -> Tuple[float, Dict]:
        """
        使用LLM评估公平性与偏见讨论（支持多模型评测）
        """
        samples = extract_content_samples(survey_content, num_samples=5, sample_length=800)
        
        if not samples:
            return 0.0, {"message": "No content to analyze"}
        
        content_excerpt = "\n\n---\n\n".join(samples)
        
        try:
            prompt = f"""You are an expert in research ethics. Evaluate the fairness and bias considerations in this survey.

**Survey Excerpts**:
---
{content_excerpt}
---

**Evaluation Criteria**:
1. Does the survey discuss potential biases in the research area?
2. Does it address fairness concerns in methods or applications?
3. Does it consider diverse perspectives and inclusive approaches?

**Output Format (JSON)**:
{{
    "fairness_score": 0.0-1.0,
    "bias_discussion_present": true/false,
    "diversity_consideration": true/false,
    "analysis": "Brief analysis of fairness considerations."
}}
"""
            
            multi_model_details = {}
            
            # 检查是否启用多模型评测
            if self.config.should_use_multi_model():
                multi_result = call_multi_model_json(
                    prompt=prompt,
                    models=self.config.t2t_models,
                    fusion_strategy=self.config.fusion_strategy
                )
                result = multi_result.get("fused_result", {})
                logger.debug(f"多模型公平性评估: 使用 {len(multi_result.get('models_used', []))} 个模型")
                
                multi_model_details = {
                    "enabled": True,
                    "models_used": multi_result.get("models_used", []),
                    "fusion_strategy": multi_result.get("fusion_strategy", ""),
                    "model_results": multi_result.get("model_results", {})
                }
            else:
                response = call_llm(prompt, response_format="json_object", max_retries=10)
                result = parse_json_response(response)
                multi_model_details = {"enabled": False}
            
            fairness_score = result.get("fairness_score", 0.0)
            
            details = {
                "bias_discussion_present": result.get("bias_discussion_present", False),
                "diversity_consideration": result.get("diversity_consideration", False),
                "analysis": result.get("analysis", "")
            }
            
            # 添加多模型评测详情
            if multi_model_details.get("enabled"):
                details["multi_model_evaluation"] = multi_model_details
            
            return fairness_score, details
            
        except Exception as e:
            logger.warning(f"公平性评估失败: {e}")
            return self._calculate_fairness_keywords(survey_content)
    
    def _calculate_fairness_keywords(
        self,
        survey_content: str
    ) -> Tuple[float, Dict]:
        """
        使用关键词检测公平性讨论
        
        注意：对于技术综述，我们采用宽松的评分标准。
        技术综述的主要目标是总结技术进展，不强制要求公平性讨论。
        """
        text = extract_text_from_latex(survey_content).lower()
        
        found_keywords = []
        for keyword in ETHICS_KEYWORDS["fairness"]:
            if keyword in text:
                found_keywords.append(keyword)
        
        # 计算分数 - 放宽标准
        # 基础分：技术综述默认给0.5的基础分
        base_score = 0.5
        
        # 关键词加分
        keyword_bonus = min(len(found_keywords) / 6, 0.5)  # 最多加0.5
        
        fairness_score = min(1.0, base_score + keyword_bonus)
        
        return fairness_score, {
            "found_keywords": found_keywords,
            "keyword_count": len(found_keywords),
            "note": "技术综述采用宽松评分标准"
        }