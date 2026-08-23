"""
结构完整性评测器
================

评估综述的结构完整性，包括:
- SC (Structural Coherence): 结构一致性
- Structural Completeness: 结构完整性
- Content-Structure Fidelity: 内容-结构一致性

支持多模型评测：
- 当配置启用多模型时，使用多个 T2T 模型进行评测并融合结果
- 提高评测的可靠性和稳定性
"""

import logging
from typing import Dict, Any, Optional, List, Tuple, Set
from pathlib import Path

from evaluation.core.base_evaluator import BaseEvaluator
from evaluation.config import EvaluationConfig, STRUCTURAL_SOUNDNESS_WEIGHTS
from evaluation.utils.latex_parser import (
    extract_outline_from_latex,
    extract_text_from_latex,
    extract_content_samples
)
from evaluation.utils.metrics import (
    calculate_structure_match_score,
    aggregate_scores
)
from evaluation.utils.llm_client import (
    call_llm,
    parse_json_response,
    call_multi_model_json,
    STRUCTURE_EVALUATION_PROMPT
)


logger = logging.getLogger(__name__)


# 标准综述章节
STANDARD_SECTIONS = {
    "introduction": ["introduction", "intro", "overview"],
    "background": ["background", "preliminary", "preliminaries", "related work"],
    "main_content": ["method", "approach", "technique", "model", "framework", "analysis"],
    "experiment": ["experiment", "evaluation", "result", "empirical"],
    "discussion": ["discussion", "limitation", "future work", "challenge"],
    "conclusion": ["conclusion", "summary", "concluding"]
}


class StructureEvaluator(BaseEvaluator):
    """结构完整性评测器"""
    
    @property
    def name(self) -> str:
        return "Structural Soundness"
    
    @property
    def weight(self) -> float:
        return self.config.dimension_weights.get("structural_soundness", 0.20)
    
    def evaluate(
        self,
        survey_content: str,
        survey_outline: Optional[Dict] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行结构完整性评测
        
        Args:
            survey_content: 综述内容
            survey_outline: 综述大纲（可选）
            
        Returns:
            评测结果
        """
        self._log_start()
        
        # 提取大纲
        if survey_outline:
            outline = self._parse_outline(survey_outline)
        else:
            outline = extract_outline_from_latex(survey_content)
        
        logger.info(f"提取到 {len(outline)} 个章节")
        
        metrics = {}
        details = {}
        
        # 1. SC (Structural Coherence) - 与MEKG社区的对应
        sc, sc_details = self._calculate_sc(outline)
        metrics["sc"] = sc
        details["sc"] = sc_details
        
        # 2. Structural Completeness - 结构完整性
        completeness, completeness_details = self._calculate_structural_completeness(outline)
        metrics["structural_completeness"] = completeness
        details["structural_completeness"] = completeness_details
        
        # 3. Content-Structure Fidelity - 内容与标题一致性
        if self.config.use_llm:
            fidelity, fidelity_details = self._calculate_content_structure_fidelity(
                survey_content, outline
            )
            metrics["content_structure_fidelity"] = fidelity
            details["content_structure_fidelity"] = fidelity_details
        else:
            metrics["content_structure_fidelity"] = 0.75
            details["content_structure_fidelity"] = {"message": "Skipped (LLM disabled)"}
        
        # 计算综合分数
        score = aggregate_scores(metrics, STRUCTURAL_SOUNDNESS_WEIGHTS)
        
        self._log_end(score)
        
        return {
            "score": score,
            "metrics": metrics,
            "details": details,
            "statistics": {
                "total_sections": len([o for o in outline if o.get("level") == 1]),
                "total_subsections": len([o for o in outline if o.get("level") == 2]),
                "max_depth": max([o.get("level", 1) for o in outline]) if outline else 0
            }
        }
    
    def _parse_outline(self, survey_outline: Dict) -> List[Dict]:
        """解析大纲格式"""
        outline = []
        
        sections = survey_outline.get("sections", [])
        for i, section in enumerate(sections, 1):
            # 兼容多种格式
            title = section.get("section title") or section.get("title") or ""
            outline.append({
                "level": 1,
                "title": title,
                "index": str(i)
            })
            
            # 处理子章节
            subsections = section.get("subsections", [])
            for j, subsection in enumerate(subsections, 1):
                sub_title = subsection.get("subsection title") or subsection.get("title") or ""
                outline.append({
                    "level": 2,
                    "title": sub_title,
                    "index": f"{i}.{j}"
                })
        
        return outline
    
    def _calculate_sc(self, outline: List[Dict]) -> Tuple[float, Dict]:
        """
        计算结构一致性 (Structural Coherence)
        
        衡量综述结构与MEKG社区结构的一致性
        """
        if not self.all_communities:
            return 0.5, {"message": "No communities in MEKG data"}
        
        # 提取章节标题
        section_titles = [
            o["title"] for o in outline 
            if o.get("level") == 1 and o.get("title")
        ]
        
        if not section_titles:
            return 0.5, {"message": "No sections found"}
        
        # 计算匹配分数
        communities = list(self.all_communities)
        score, match_details = calculate_structure_match_score(section_titles, communities)
        
        return score, match_details
    
    def _calculate_structural_completeness(
        self,
        outline: List[Dict]
    ) -> Tuple[float, Dict]:
        """
        计算结构完整性
        
        检查是否包含标准综述章节
        """
        section_titles = [
            o["title"].lower() for o in outline 
            if o.get("level") == 1 and o.get("title")
        ]
        
        if not section_titles:
            return 0.0, {"message": "No sections found"}
        
        # 检查每个标准章节是否存在
        found_sections = {}
        missing_sections = []
        
        for section_type, keywords in STANDARD_SECTIONS.items():
            found = False
            for title in section_titles:
                if any(kw in title for kw in keywords):
                    found = True
                    found_sections[section_type] = title
                    break
            
            if not found:
                missing_sections.append(section_type)
        
        # 计算完整性分数
        completeness = len(found_sections) / len(STANDARD_SECTIONS)
        
        # 检查层次结构
        has_subsections = any(o.get("level", 1) > 1 for o in outline)
        hierarchy_bonus = 0.1 if has_subsections else 0.0
        
        final_score = min(1.0, completeness + hierarchy_bonus)
        
        return final_score, {
            "found_sections": found_sections,
            "missing_sections": missing_sections,
            "has_subsections": has_subsections,
            "total_sections": len(section_titles)
        }
    
    def _calculate_content_structure_fidelity(
        self,
        survey_content: str,
        outline: List[Dict]
    ) -> Tuple[float, Dict]:
        """
        计算内容-结构一致性
        
        检查每个章节的内容是否与标题一致
        """
        # 提取主要章节
        main_sections = [o for o in outline if o.get("level") == 1][:5]
        
        if not main_sections:
            return 0.5, {"message": "No sections to evaluate"}
        
        scores = []
        section_details = []
        multi_model_info = []
        
        for section in main_sections:
            title = section.get("title", "")
            if not title:
                continue
            
            # 提取该章节的内容样本
            content_sample = self._extract_section_content(survey_content, title)
            
            if not content_sample:
                continue
            
            # 使用LLM评估一致性
            try:
                score, analysis, multi_details = self._evaluate_section_fidelity(title, content_sample)
                scores.append(score)
                
                section_item = {
                    "section": title,
                    "score": score,
                    "analysis": analysis
                }
                
                # 保存多模型详情
                if multi_details.get("enabled"):
                    section_item["multi_model"] = multi_details
                    multi_model_info.append(multi_details)
                
                section_details.append(section_item)
            except Exception as e:
                logger.warning(f"评估章节 '{title}' 失败: {e}")
        
        if not scores:
            return 0.5, {"message": "No sections evaluated"}
        
        avg_score = sum(scores) / len(scores)
        
        details = {
            "sections_evaluated": len(scores),
            "section_details": section_details
        }
        
        # 添加多模型评测汇总信息
        if multi_model_info:
            details["multi_model_evaluation"] = {
                "enabled": True,
                "total_evaluations": len(multi_model_info),
                "sample_model_results": multi_model_info[:2]  # 保存前2个样本的详细结果
            }
        
        return avg_score, details
    
    def _extract_section_content(self, content: str, section_title: str) -> str:
        """提取指定章节的内容"""
        import re
        
        # 尝试匹配章节
        pattern = rf'\\section\{{{re.escape(section_title)}\}}(.*?)(?=\\section|\\bibliography|\\end\{{document\}})'
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        
        if match:
            section_content = match.group(1)
            # 清理并截取
            clean_content = extract_text_from_latex(section_content)
            return clean_content[:2000]
        
        return ""
    
    def _evaluate_section_fidelity(
        self,
        section_title: str,
        section_content: str
    ) -> Tuple[float, str, Dict]:
        """使用LLM评估章节一致性（支持多模型评测）
        
        Returns:
            Tuple[score, analysis, multi_model_details]
        """
        prompt = f"""You are an expert academic editor. Evaluate if the content of a section matches its title.

**Section Title**: {section_title}

**Section Content (Excerpt)**:
---
{section_content[:1500]}
---

**Instructions**:
1. Does the content directly address the topic promised by the title?
2. Is there any off-topic or misplaced content?

**Output Format (JSON)**:
{{
    "fidelity_score": 0.0-1.0,
    "analysis": "Brief analysis of the alignment between title and content."
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
            logger.debug(f"多模型章节一致性评估: 使用 {len(multi_result.get('models_used', []))} 个模型")
            
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
        
        score = result.get("fidelity_score", 0.5)
        analysis = result.get("analysis", "")
        
        return score, analysis, multi_model_details
    
    @property
    def all_communities(self) -> Set[str]:
        """获取所有社区"""
        communities = set()
        
        # 从categories获取
        for cat_name in self.categories.keys():
            communities.add(cat_name)
        
        # 从papers获取
        for paper in self.papers.values():
            community = paper.get("community", paper.get("category", ""))
            if community:
                communities.add(str(community))
        
        return communities