"""
全局反思器 - GlobalReflector

实现论文级别的全局一致性检查和优化，参考 SciSage 的设计。

核心功能:
1. 全局一致性检查: 检查章节间的逻辑连贯性
2. 术语一致性: 确保术语使用统一
3. 引用覆盖检查: 确保核心论文被充分引用
4. 结构平衡检查: 检查章节长度和深度的平衡

Reference:
- SciSage: refer/SciSage-main/core/paper_global_reflection_opt.py
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import Counter

from src.configs.config import BASE_DIR, ADVANCED_CHATAGENT_MODEL
from src.configs.logger import get_logger
from src.models.LLM import ChatAgent

logger = get_logger("src.modules.post_refine.GlobalReflector")


@dataclass
class ConsistencyIssue:
    """一致性问题"""
    issue_type: str  # terminology, logic, citation, structure, style
    severity: str  # high, medium, low
    location: str  # 问题位置 (章节名)
    description: str
    suggestion: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_type": self.issue_type,
            "severity": self.severity,
            "location": self.location,
            "description": self.description,
            "suggestion": self.suggestion
        }


@dataclass
class GlobalReflectionResult:
    """全局反思结果"""
    meets_requirements: bool
    overall_score: float  # 1-5 分
    feedback: str
    issues: List[ConsistencyIssue] = field(default_factory=list)
    improvement_actions: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "meets_requirements": self.meets_requirements,
            "overall_score": self.overall_score,
            "feedback": self.feedback,
            "issues": [i.to_dict() for i in self.issues],
            "improvement_actions": self.improvement_actions,
            "metrics": self.metrics
        }


class GlobalReflector:
    """
    全局反思器
    
    对整篇综述进行全局一致性检查和优化建议。
    
    检查维度:
    1. 逻辑一致性: 章节间的逻辑流程是否连贯
    2. 术语一致性: 专业术语是否统一使用
    3. 引用覆盖: 核心论文是否被充分引用
    4. 结构平衡: 章节长度和深度是否平衡
    5. 风格一致性: 写作风格是否统一
    """
    
    # 全局评估 Prompt
    GLOBAL_EVALUATION_PROMPT = """You are an expert academic reviewer evaluating a survey paper on "{topic}".

Survey Title: {title}

Survey Content (by sections):
{sections_content}

Evaluate this survey on the following dimensions:

1. **Logical Coherence** (1-5): Do sections flow logically? Are transitions smooth?
2. **Terminology Consistency** (1-5): Are technical terms used consistently throughout?
3. **Citation Coverage** (1-5): Are key works in the field adequately cited?
4. **Structural Balance** (1-5): Are sections appropriately balanced in length and depth?
5. **Writing Style** (1-5): Is the writing style consistent and academic?

For each issue found, provide:
- Issue type (logic, terminology, citation, structure, style)
- Severity (high, medium, low)
- Location (section name)
- Description of the issue
- Suggestion for improvement

Output format (JSON):
{{
    "meets_requirements": true/false,
    "overall_score": 4.2,
    "feedback": "Overall assessment...",
    "dimension_scores": {{
        "logical_coherence": 4,
        "terminology_consistency": 5,
        "citation_coverage": 3,
        "structural_balance": 4,
        "writing_style": 4
    }},
    "issues": [
        {{
            "issue_type": "citation",
            "severity": "medium",
            "location": "Section 3",
            "description": "Missing citation for key work X",
            "suggestion": "Add citation to [Author et al., 2023]"
        }}
    ],
    "improvement_actions": [
        {{
            "section": "Section 3",
            "action": "Add more citations",
            "priority": "high"
        }}
    ]
}}

Evaluate the survey:"""

    # 术语一致性检查 Prompt
    TERMINOLOGY_CHECK_PROMPT = """Analyze the following survey content for terminology consistency.

Topic: {topic}

Content:
{content}

Identify any inconsistent use of technical terms. For example:
- Same concept referred to by different names
- Abbreviations used inconsistently
- Capitalization inconsistencies

Output format (JSON):
{{
    "inconsistencies": [
        {{
            "term_variants": ["LLM", "large language model", "Large Language Model"],
            "recommended": "large language model (LLM)",
            "locations": ["Section 1", "Section 3"]
        }}
    ],
    "recommendations": ["Use 'LLM' consistently after first definition"]
}}

Analyze:"""

    # 结构平衡检查 Prompt
    STRUCTURE_CHECK_PROMPT = """Analyze the structure of this survey for balance and completeness.

Topic: {topic}

Section Statistics:
{section_stats}

Evaluate:
1. Are sections balanced in length?
2. Is the depth of coverage appropriate for each topic?
3. Are there any missing important sections?
4. Are there any sections that are too long or too short?

Output format (JSON):
{{
    "balance_score": 4,
    "issues": [
        {{
            "section": "Section 3",
            "issue": "Too short compared to other sections",
            "suggestion": "Expand with more detailed analysis"
        }}
    ],
    "missing_topics": ["Topic X could be added"],
    "recommendations": ["Consider splitting Section 2 into subsections"]
}}

Analyze:"""

    def __init__(
        self,
        chat_agent: Optional[ChatAgent] = None,
        quality_threshold: float = 3.5,
        enable_terminology_check: bool = True,
        enable_structure_check: bool = True
    ):
        """
        初始化全局反思器
        
        Args:
            chat_agent: ChatAgent 实例
            quality_threshold: 质量阈值 (1-5)
            enable_terminology_check: 是否启用术语一致性检查
            enable_structure_check: 是否启用结构平衡检查
        """
        self.chat_agent = chat_agent or ChatAgent()
        self.quality_threshold = quality_threshold
        self.enable_terminology_check = enable_terminology_check
        self.enable_structure_check = enable_structure_check
    
    def reflect(
        self,
        title: str,
        topic: str,
        sections_content: Dict[str, str],
        outline: Optional[Dict[str, Any]] = None
    ) -> GlobalReflectionResult:
        """
        执行全局反思
        
        Args:
            title: 综述标题
            topic: 综述主题
            sections_content: 章节内容 {section_name: content}
            outline: 大纲结构 (可选)
            
        Returns:
            GlobalReflectionResult 对象
        """
        logger.info(f"开始全局反思: {title}")
        
        # Step 1: 全局评估
        logger.info("Step 1: 执行全局评估...")
        global_result = self._evaluate_global(title, topic, sections_content)
        
        # Step 2: 术语一致性检查 (如果启用)
        if self.enable_terminology_check:
            logger.info("Step 2: 检查术语一致性...")
            terminology_issues = self._check_terminology(topic, sections_content)
            global_result.issues.extend(terminology_issues)
        
        # Step 3: 结构平衡检查 (如果启用)
        if self.enable_structure_check:
            logger.info("Step 3: 检查结构平衡...")
            structure_issues = self._check_structure(topic, sections_content)
            global_result.issues.extend(structure_issues)
        
        # Step 4: 计算最终评分
        global_result.meets_requirements = global_result.overall_score >= self.quality_threshold
        
        logger.info(
            f"全局反思完成: 评分={global_result.overall_score:.2f}, "
            f"满足要求={global_result.meets_requirements}, "
            f"问题数={len(global_result.issues)}"
        )
        
        return global_result
    
    async def reflect_async(
        self,
        title: str,
        topic: str,
        sections_content: Dict[str, str],
        outline: Optional[Dict[str, Any]] = None
    ) -> GlobalReflectionResult:
        """异步执行全局反思"""
        # 使用线程池执行同步方法
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.reflect,
            title, topic, sections_content, outline
        )
    
    def _evaluate_global(
        self,
        title: str,
        topic: str,
        sections_content: Dict[str, str]
    ) -> GlobalReflectionResult:
        """执行全局评估"""
        # 准备章节内容文本
        sections_text = ""
        for section_name, content in sections_content.items():
            # 截断过长的内容
            truncated_content = content[:2000] if len(content) > 2000 else content
            sections_text += f"\n## {section_name}\n{truncated_content}\n"
        
        prompt = self.GLOBAL_EVALUATION_PROMPT.format(
            topic=topic,
            title=title,
            sections_content=sections_text
        )
        
        response = self.chat_agent.remote_chat(prompt, model=ADVANCED_CHATAGENT_MODEL)
        
        # 解析响应
        try:
            result_data = self._parse_json_response(response)
            
            issues = []
            for issue_data in result_data.get("issues", []):
                issue = ConsistencyIssue(
                    issue_type=issue_data.get("issue_type", "unknown"),
                    severity=issue_data.get("severity", "medium"),
                    location=issue_data.get("location", ""),
                    description=issue_data.get("description", ""),
                    suggestion=issue_data.get("suggestion", "")
                )
                issues.append(issue)
            
            return GlobalReflectionResult(
                meets_requirements=result_data.get("meets_requirements", False),
                overall_score=result_data.get("overall_score", 3.0),
                feedback=result_data.get("feedback", ""),
                issues=issues,
                improvement_actions=result_data.get("improvement_actions", []),
                metrics=result_data.get("dimension_scores", {})
            )
        except Exception as e:
            logger.error(f"解析全局评估结果失败: {e}")
            return GlobalReflectionResult(
                meets_requirements=False,
                overall_score=3.0,
                feedback=f"评估解析失败: {str(e)}",
                issues=[],
                improvement_actions=[],
                metrics={}
            )
    
    def _check_terminology(
        self,
        topic: str,
        sections_content: Dict[str, str]
    ) -> List[ConsistencyIssue]:
        """检查术语一致性"""
        # 合并所有内容
        full_content = "\n\n".join(sections_content.values())
        
        # 截断过长的内容
        if len(full_content) > 10000:
            full_content = full_content[:10000]
        
        prompt = self.TERMINOLOGY_CHECK_PROMPT.format(
            topic=topic,
            content=full_content
        )
        
        response = self.chat_agent.remote_chat(prompt, model=ADVANCED_CHATAGENT_MODEL)
        
        issues = []
        try:
            result_data = self._parse_json_response(response)
            
            for inconsistency in result_data.get("inconsistencies", []):
                variants = inconsistency.get("term_variants", [])
                recommended = inconsistency.get("recommended", "")
                locations = inconsistency.get("locations", [])
                
                issue = ConsistencyIssue(
                    issue_type="terminology",
                    severity="medium",
                    location=", ".join(locations),
                    description=f"术语不一致: {', '.join(variants)}",
                    suggestion=f"建议统一使用: {recommended}"
                )
                issues.append(issue)
        except Exception as e:
            logger.warning(f"术语一致性检查失败: {e}")
        
        return issues
    
    def _check_structure(
        self,
        topic: str,
        sections_content: Dict[str, str]
    ) -> List[ConsistencyIssue]:
        """检查结构平衡"""
        # 计算章节统计
        section_stats = []
        total_length = sum(len(c) for c in sections_content.values())
        
        for section_name, content in sections_content.items():
            length = len(content)
            percentage = (length / total_length * 100) if total_length > 0 else 0
            word_count = len(content.split())
            section_stats.append({
                "section": section_name,
                "length": length,
                "percentage": f"{percentage:.1f}%",
                "word_count": word_count
            })
        
        stats_text = json.dumps(section_stats, indent=2)
        
        prompt = self.STRUCTURE_CHECK_PROMPT.format(
            topic=topic,
            section_stats=stats_text
        )
        
        response = self.chat_agent.remote_chat(prompt, model=ADVANCED_CHATAGENT_MODEL)
        
        issues = []
        try:
            result_data = self._parse_json_response(response)
            
            for issue_data in result_data.get("issues", []):
                issue = ConsistencyIssue(
                    issue_type="structure",
                    severity="medium",
                    location=issue_data.get("section", ""),
                    description=issue_data.get("issue", ""),
                    suggestion=issue_data.get("suggestion", "")
                )
                issues.append(issue)
            
            # 添加缺失主题作为问题
            for missing in result_data.get("missing_topics", []):
                issue = ConsistencyIssue(
                    issue_type="structure",
                    severity="low",
                    location="Overall",
                    description=f"可能缺失的主题: {missing}",
                    suggestion=f"考虑添加关于 {missing} 的内容"
                )
                issues.append(issue)
        except Exception as e:
            logger.warning(f"结构平衡检查失败: {e}")
        
        return issues
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """解析 JSON 响应"""
        # 尝试提取 JSON
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response
        
        return json.loads(json_str)
    
    def get_improvement_suggestions(
        self,
        result: GlobalReflectionResult
    ) -> List[Dict[str, Any]]:
        """
        根据反思结果生成改进建议
        
        Args:
            result: 全局反思结果
            
        Returns:
            改进建议列表
        """
        suggestions = []
        
        # 按严重程度排序问题
        high_issues = [i for i in result.issues if i.severity == "high"]
        medium_issues = [i for i in result.issues if i.severity == "medium"]
        low_issues = [i for i in result.issues if i.severity == "low"]
        
        # 高优先级建议
        for issue in high_issues:
            suggestions.append({
                "priority": "high",
                "type": issue.issue_type,
                "location": issue.location,
                "action": issue.suggestion,
                "reason": issue.description
            })
        
        # 中优先级建议
        for issue in medium_issues:
            suggestions.append({
                "priority": "medium",
                "type": issue.issue_type,
                "location": issue.location,
                "action": issue.suggestion,
                "reason": issue.description
            })
        
        # 低优先级建议
        for issue in low_issues:
            suggestions.append({
                "priority": "low",
                "type": issue.issue_type,
                "location": issue.location,
                "action": issue.suggestion,
                "reason": issue.description
            })
        
        return suggestions


# 便捷函数
def reflect_survey_global(
    title: str,
    topic: str,
    sections_content: Dict[str, str],
    chat_agent: Optional[ChatAgent] = None,
    quality_threshold: float = 3.5
) -> GlobalReflectionResult:
    """
    执行全局反思的便捷函数
    
    Args:
        title: 综述标题
        topic: 综述主题
        sections_content: 章节内容
        chat_agent: ChatAgent 实例
        quality_threshold: 质量阈值
        
    Returns:
        GlobalReflectionResult 对象
    """
    reflector = GlobalReflector(
        chat_agent=chat_agent,
        quality_threshold=quality_threshold
    )
    return reflector.reflect(title, topic, sections_content)


async def reflect_survey_global_async(
    title: str,
    topic: str,
    sections_content: Dict[str, str],
    chat_agent: Optional[ChatAgent] = None,
    quality_threshold: float = 3.5
) -> GlobalReflectionResult:
    """异步执行全局反思的便捷函数"""
    reflector = GlobalReflector(
        chat_agent=chat_agent,
        quality_threshold=quality_threshold
    )
    return await reflector.reflect_async(title, topic, sections_content)


if __name__ == "__main__":
    # 测试代码
    title = "A Survey on Large Language Model Agents"
    topic = "Large Language Model Agents"
    sections_content = {
        "Introduction": "Large language models have revolutionized...",
        "Background": "The development of LLMs began with...",
        "Methods": "Various approaches have been proposed..."
    }
    
    reflector = GlobalReflector()
    result = reflector.reflect(title, topic, sections_content)
    
    print(f"评分: {result.overall_score}")
    print(f"满足要求: {result.meets_requirements}")
    print(f"问题数: {len(result.issues)}")