"""
内容完整性评测器
================

评估综述的内容完整性，包括:
- General Factualness: 通用事实性
- Writing Quality: 写作质量
- Scholarly Depth: 学术深度
- TC (Temporal Coverage): 时间覆盖率
- Rubric Score: 基于评分细则的综合评估（参考 ARISE）

支持多模型评测：
- 当配置启用多模型时，使用多个 T2T 模型进行评测并融合结果
- 提高评测的可靠性和稳定性
"""

import logging
import random
from typing import Dict, Any, Optional, List, Tuple, Set
from pathlib import Path

from evaluation.core.base_evaluator import BaseEvaluator
from evaluation.config import EvaluationConfig, CONTENT_INTEGRITY_WEIGHTS
from evaluation.utils.latex_parser import (
    extract_citations,
    extract_text_from_latex,
    extract_content_samples,
    extract_sentences_without_citations
)
from evaluation.utils.metrics import (
    calculate_tc,
    aggregate_scores
)
from evaluation.utils.llm_client import (
    call_llm,
    parse_json_response,
    call_multi_model_json,
    CONTENT_QUALITY_PROMPT,
    GENERAL_FACTUALNESS_PROMPT
)

# 导入 RubricEvaluator
try:
    from src.modules.post_refine.rubric_evaluator import RubricEvaluator, RubricEvaluationResult
    RUBRIC_EVALUATOR_AVAILABLE = True
except ImportError:
    RUBRIC_EVALUATOR_AVAILABLE = False
    RubricEvaluator = None
    RubricEvaluationResult = None


logger = logging.getLogger(__name__)


class ContentEvaluator(BaseEvaluator):
    """内容完整性评测器"""
    
    @property
    def name(self) -> str:
        return "Content Integrity"
    
    @property
    def weight(self) -> float:
        return self.config.dimension_weights.get("content_integrity", 0.25)
    
    def evaluate(
        self,
        survey_content: str,
        survey_outline: Optional[Dict] = None,
        topic: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行内容完整性评测
        
        Args:
            survey_content: 综述内容
            survey_outline: 综述大纲（可选）
            topic: 综述主题
            
        Returns:
            评测结果
        """
        self._log_start()
        
        metrics = {}
        details = {}
        
        # 1. General Factualness - 通用事实性
        if self.config.use_llm:
            gf, gf_details = self._calculate_general_factualness(survey_content, topic)
            metrics["general_factualness"] = gf
            details["general_factualness"] = gf_details
        else:
            metrics["general_factualness"] = 1.0
            details["general_factualness"] = {"message": "Skipped (LLM disabled)"}
        
        # 2. Writing Quality - 写作质量
        if self.config.use_llm:
            wq, wq_details = self._calculate_writing_quality(survey_content)
            metrics["writing_quality"] = wq
            details["writing_quality"] = wq_details
        else:
            metrics["writing_quality"] = 0.75
            details["writing_quality"] = {"message": "Skipped (LLM disabled)"}
        
        # 3. Scholarly Depth - 学术深度
        if self.config.use_llm:
            sd, sd_details = self._calculate_scholarly_depth(survey_content)
            metrics["scholarly_depth"] = sd
            details["scholarly_depth"] = sd_details
        else:
            metrics["scholarly_depth"] = 0.75
            details["scholarly_depth"] = {"message": "Skipped (LLM disabled)"}
        
        # 4. TC (Temporal Coverage) - 时间覆盖率
        tc, tc_details = self._calculate_tc(survey_content)
        metrics["tc"] = tc
        details["tc"] = tc_details
        
        # 5. Rubric Score - 基于评分细则的综合评估
        if self.config.use_llm and RUBRIC_EVALUATOR_AVAILABLE:
            rs, rs_details = self._calculate_rubric_score(survey_content, topic, survey_outline)
            metrics["rubric_score"] = rs
            details["rubric_score"] = rs_details
        else:
            if not RUBRIC_EVALUATOR_AVAILABLE:
                metrics["rubric_score"] = 0.7
                details["rubric_score"] = {"message": "Skipped (RubricEvaluator not available)"}
            else:
                metrics["rubric_score"] = 0.7
                details["rubric_score"] = {"message": "Skipped (LLM disabled)"}
        
        # 计算综合分数
        score = aggregate_scores(metrics, CONTENT_INTEGRITY_WEIGHTS)
        
        self._log_end(score)
        
        return {
            "score": score,
            "metrics": metrics,
            "details": details
        }
    
    def _calculate_general_factualness(
        self,
        survey_content: str,
        topic: str
    ) -> Tuple[float, Dict]:
        """
        计算通用事实性
        
        验证无引用声明的事实准确性
        """
        # 提取无引用的句子
        sentences = extract_sentences_without_citations(survey_content)
        
        if not sentences:
            return 1.0, {"message": "No non-cited sentences found"}
        
        # 采样
        sample_size = min(self.config.factual_sample_size, len(sentences))
        if sample_size > 0:
            sampled_sentences = random.sample(sentences, sample_size)
        else:
            sampled_sentences = sentences[:20]
        
        # 验证每个句子
        correct_count = 0
        evaluation_details = []
        
        multi_model_info = []
        
        for sent_data in sampled_sentences:
            sentence = sent_data["sentence"]
            
            try:
                is_correct, summary, multi_details = self._verify_general_fact(sentence, topic)
                if is_correct:
                    correct_count += 1
                
                eval_item = {
                    "sentence": sentence[:100],
                    "is_correct": is_correct,
                    "summary": summary
                }
                
                # 保存多模型详情
                if multi_details.get("enabled"):
                    eval_item["multi_model"] = multi_details
                    multi_model_info.append(multi_details)
                
                evaluation_details.append(eval_item)
            except Exception as e:
                logger.warning(f"事实验证失败: {e}")
                correct_count += 1  # 默认正确
        
        if not sampled_sentences:
            return 1.0, {"message": "No sentences to verify"}
        
        factualness_score = correct_count / len(sampled_sentences)
        
        details = {
            "total_sentences": len(sampled_sentences),
            "correct_sentences": correct_count,
            "sample_details": evaluation_details[:5]
        }
        
        # 添加多模型评测汇总信息
        if multi_model_info:
            details["multi_model_evaluation"] = {
                "enabled": True,
                "total_evaluations": len(multi_model_info),
                "sample_model_results": multi_model_info[:3]  # 保存前3个样本的详细结果
            }
        
        return factualness_score, details
    
    def _verify_general_fact(self, sentence: str, topic: str) -> Tuple[bool, str, Dict]:
        """验证通用事实（支持多模型评测）
        
        Returns:
            Tuple[is_correct, summary, multi_model_details]
        """
        prompt = GENERAL_FACTUALNESS_PROMPT.format(
            claim=sentence,
            topic=topic or "academic research"
        )
        
        multi_model_details = {}
        
        # 检查是否启用多模型评测
        if self.config.should_use_multi_model():
            multi_result = call_multi_model_json(
                prompt=prompt,
                models=self.config.t2t_models,
                fusion_strategy=self.config.fusion_strategy
            )
            result = multi_result.get("fused_result", {})
            logger.debug(f"多模型事实验证: 使用 {len(multi_result.get('models_used', []))} 个模型")
            
            # 保存多模型详情
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
        
        is_correct = result.get("is_factually_correct", True)
        summary = result.get("verification_summary", "")
        
        # null表示无法验证，默认为正确
        if is_correct is None:
            is_correct = True
        
        return is_correct, summary, multi_model_details
    
    def _calculate_writing_quality(
        self,
        survey_content: str
    ) -> Tuple[float, Dict]:
        """
        计算写作质量
        
        评估清晰度、连贯性等
        """
        # 提取内容样本
        samples = extract_content_samples(
            survey_content,
            num_samples=self.config.content_sample_size,
            sample_length=500
        )
        
        if not samples:
            return 0.5, {"message": "No content samples extracted"}
        
        scores = {
            "clarity": [],
            "coherence": [],
            "depth": [],
            "objectivity": []
        }
        
        multi_model_info = []
        
        for sample in samples:
            try:
                result, multi_details = self._evaluate_content_quality(sample)
                scores["clarity"].append(result.get("clarity_score", 0.5))
                scores["coherence"].append(result.get("coherence_score", 0.5))
                scores["depth"].append(result.get("depth_score", 0.5))
                scores["objectivity"].append(result.get("objectivity_score", 0.5))
                
                if multi_details.get("enabled"):
                    multi_model_info.append(multi_details)
            except Exception as e:
                logger.warning(f"内容质量评估失败: {e}")
        
        # 计算平均分
        avg_scores = {}
        for metric, values in scores.items():
            if values:
                avg_scores[metric] = sum(values) / len(values)
            else:
                avg_scores[metric] = 0.5
        
        # 综合写作质量分数
        writing_quality = (
            avg_scores["clarity"] * 0.3 +
            avg_scores["coherence"] * 0.3 +
            avg_scores["depth"] * 0.2 +
            avg_scores["objectivity"] * 0.2
        )
        
        details = {
            "samples_evaluated": len(samples),
            "clarity_score": avg_scores["clarity"],
            "coherence_score": avg_scores["coherence"],
            "depth_score": avg_scores["depth"],
            "objectivity_score": avg_scores["objectivity"]
        }
        
        # 添加多模型评测汇总信息
        if multi_model_info:
            details["multi_model_evaluation"] = {
                "enabled": True,
                "total_evaluations": len(multi_model_info),
                "sample_model_results": multi_model_info[:2]  # 保存前2个样本的详细结果
            }
        
        return writing_quality, details
    
    def _evaluate_content_quality(self, content_sample: str) -> Tuple[Dict, Dict]:
        """使用LLM评估内容质量（支持多模型评测）
        
        Returns:
            Tuple[result, multi_model_details]
        """
        prompt = CONTENT_QUALITY_PROMPT.format(content_sample=content_sample)
        
        multi_model_details = {}
        
        # 检查是否启用多模型评测
        if self.config.should_use_multi_model():
            multi_result = call_multi_model_json(
                prompt=prompt,
                models=self.config.t2t_models,
                fusion_strategy=self.config.fusion_strategy
            )
            result = multi_result.get("fused_result", {})
            logger.debug(f"多模型内容质量评估: 使用 {len(multi_result.get('models_used', []))} 个模型")
            
            multi_model_details = {
                "enabled": True,
                "models_used": multi_result.get("models_used", []),
                "fusion_strategy": multi_result.get("fusion_strategy", ""),
                "model_results": multi_result.get("model_results", {})
            }
            return result, multi_model_details
        else:
            response = call_llm(prompt, response_format="json_object", max_retries=10)
            return parse_json_response(response), {"enabled": False}
    
    def _calculate_scholarly_depth(
        self,
        survey_content: str
    ) -> Tuple[float, Dict]:
        """
        计算学术深度
        
        评估综合分析能力、批判性思维等
        """
        # 提取较长的内容样本
        samples = extract_content_samples(
            survey_content,
            num_samples=3,
            sample_length=1000
        )
        
        if not samples:
            return 0.5, {"message": "No content samples extracted"}
        
        content_excerpt = "\n\n---\n\n".join(samples)
        
        try:
            prompt = f"""You are a senior academic reviewer. Evaluate the scholarly depth of this survey excerpt.

**Survey Excerpts**:
---
{content_excerpt}
---

**Evaluation Criteria**:
1. Synthesis: Does it synthesize multiple studies into coherent themes?
2. Critical Analysis: Does it critically evaluate methodologies and findings?
3. Novel Insights: Does it provide novel perspectives or identify research gaps?
4. Technical Depth: Is the technical discussion sufficiently detailed?

**Output Format (JSON)**:
{{
    "synthesis_score": 0.0-1.0,
    "critical_analysis_score": 0.0-1.0,
    "novel_insights_score": 0.0-1.0,
    "technical_depth_score": 0.0-1.0,
    "overall_depth_score": 0.0-1.0,
    "analysis": "Brief analysis of the scholarly depth."
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
                logger.debug(f"多模型学术深度评估: 使用 {len(multi_result.get('models_used', []))} 个模型")
                
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
            
            depth_score = result.get("overall_depth_score", 0.5)
            
            details = {
                "synthesis_score": result.get("synthesis_score", 0.5),
                "critical_analysis_score": result.get("critical_analysis_score", 0.5),
                "novel_insights_score": result.get("novel_insights_score", 0.5),
                "technical_depth_score": result.get("technical_depth_score", 0.5),
                "analysis": result.get("analysis", "")
            }
            
            # 添加多模型评测详情
            if multi_model_details.get("enabled"):
                details["multi_model_evaluation"] = multi_model_details
            
            return depth_score, details
            
        except Exception as e:
            logger.warning(f"学术深度评估失败: {e}")
            return 0.5, {"error": str(e)}
    
    def _calculate_rubric_score(
        self,
        survey_content: str,
        topic: str,
        outline: Optional[Dict] = None
    ) -> Tuple[float, Dict]:
        """
        基于评分细则的综合评估
        
        使用 RubricEvaluator 对综述进行多维度评估，
        参考 ARISE 的评分细则标准。
        
        评估维度包括:
        - Scope: 范围与目标
        - Literature: 文献综述
        - Analysis: 分析深度
        - Organization: 组织结构
        - Presentation: 表达呈现
        - References: 参考文献
        
        Args:
            survey_content: 综述内容
            topic: 综述主题
            outline: 大纲结构
            
        Returns:
            Tuple[score, details]
        """
        if not RUBRIC_EVALUATOR_AVAILABLE:
            return 0.7, {"message": "RubricEvaluator not available"}
        
        try:
            # 创建 RubricEvaluator（不使用 LLM，使用启发式评估以提高速度）
            # 如果需要更精确的评估，可以传入 chat_agent
            evaluator = RubricEvaluator(
                chat_agent=None,  # 使用启发式评估
                use_llm=False
            )
            
            # 执行评估
            result: RubricEvaluationResult = evaluator.evaluate(
                survey_content=survey_content,
                topic=topic,
                outline=outline
            )
            
            # 将 1-5 分制转换为 0-1 分制
            normalized_score = (result.total_score - 1) / 4.0  # (score - 1) / (5 - 1)
            normalized_score = max(0.0, min(1.0, normalized_score))
            
            # 构建详细信息
            details = {
                "total_score": result.total_score,
                "normalized_score": result.normalized_score,
                "quality_level": result.quality_level,
                "categories": {},
                "feedback": result.feedback,
                "improvement_suggestions": result.improvement_suggestions[:3]  # 只保留前3个建议
            }
            
            # 添加各类别得分
            for cat_key, cat_result in result.categories.items():
                details["categories"][cat_key] = {
                    "name": cat_result.display_name,
                    "score": cat_result.score,
                    "weight": cat_result.weight
                }
            
            logger.info(f"Rubric评估完成: 总分={result.total_score:.2f}/5.0, 质量等级={result.quality_level}")
            
            return normalized_score, details
            
        except Exception as e:
            logger.warning(f"Rubric评估失败: {e}")
            return 0.7, {"error": str(e)}
    
    def _normalize_cite_key(self, cite_key: str) -> str:
        """规范化引用key，处理arXiv_和arXiv:的差异"""
        if cite_key.startswith("arXiv_"):
            return "arXiv:" + cite_key[6:]
        return cite_key
    
    def _calculate_tc(self, survey_content: str) -> Tuple[float, Dict]:
        """
        计算时间覆盖率 (Temporal Coverage)
        """
        # 从MEKG数据获取论文年份
        paper_years = {}
        normalized_id_to_id = {}  # 规范化ID到原始ID的映射
        
        for paper_id, paper in self.papers.items():
            year = paper.get("year")
            if year:
                paper_years[paper_id] = year
            
            # 构建规范化ID映射
            normalized_id_to_id[paper_id] = paper_id
            if paper_id.startswith("arXiv:"):
                underscore_version = "arXiv_" + paper_id[6:]
                normalized_id_to_id[underscore_version] = paper_id
            elif paper_id.startswith("arXiv_"):
                colon_version = "arXiv:" + paper_id[6:]
                normalized_id_to_id[colon_version] = paper_id
        
        if not paper_years:
            return 0.5, {"message": "No year information in MEKG data"}
        
        # 计算期望年份范围
        all_years = list(paper_years.values())
        expected_range = (min(all_years), max(all_years))
        
        # 提取引用
        cited_keys = extract_citations(survey_content)
        
        # 映射到paper_id并获取年份（处理格式差异）
        cited_paper_ids = set()
        for cite_key in cited_keys:
            # 直接匹配
            if cite_key in self.papers:
                cited_paper_ids.add(cite_key)
            # 通过规范化ID匹配
            elif cite_key in normalized_id_to_id:
                cited_paper_ids.add(normalized_id_to_id[cite_key])
        
        return calculate_tc(cited_paper_ids, paper_years, expected_range)