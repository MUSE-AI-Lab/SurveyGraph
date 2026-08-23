"""
基于评分细则的评估器 - 参考 ARISE 实现

该模块实现了基于学术评审标准的综述质量评估，通过结构化的评分细则
对综述进行多维度评估，并生成定向优化建议。

核心功能:
1. 基于评分细则的多维度评估
2. 与现有 evaluation 框架的整合
3. 生成定向优化提示
4. 支持章节级和全文级评估

Reference:
- ARISE: refer/ARISE-main/full_detailed_review_rubric.json
- 现有评估框架: evaluation/
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field

from src.configs.logger import get_logger
from src.models.LLM import ChatAgent

logger = get_logger("src.modules.post_refine.RubricEvaluator")


@dataclass
class SubcriterionResult:
    """子标准评估结果"""
    name: str
    score: float  # 1-5 分
    weight: float
    feedback: str
    level_description: str  # 对应分数的描述
    
    @property
    def weighted_score(self) -> float:
        return self.score * self.weight
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "score": self.score,
            "weight": self.weight,
            "weighted_score": round(self.weighted_score, 4),
            "feedback": self.feedback,
            "level_description": self.level_description
        }


@dataclass
class CategoryResult:
    """类别评估结果"""
    name: str
    display_name: str
    weight: float
    subcriteria: List[SubcriterionResult] = field(default_factory=list)
    
    @property
    def score(self) -> float:
        """计算类别得分 (加权平均)"""
        if not self.subcriteria:
            return 0.0
        total_weight = sum(s.weight for s in self.subcriteria)
        if total_weight == 0:
            return 0.0
        return sum(s.weighted_score for s in self.subcriteria) / total_weight
    
    @property
    def weighted_score(self) -> float:
        return self.score * self.weight
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "score": round(self.score, 4),
            "weight": self.weight,
            "weighted_score": round(self.weighted_score, 4),
            "subcriteria": [s.to_dict() for s in self.subcriteria]
        }


@dataclass
class RubricEvaluationResult:
    """评分细则评估结果"""
    total_score: float = 0.0  # 1-5 分制
    normalized_score: float = 0.0  # 0-100 分制
    categories: Dict[str, CategoryResult] = field(default_factory=dict)
    feedback: List[str] = field(default_factory=list)
    improvement_suggestions: List[Dict[str, Any]] = field(default_factory=list)
    quality_level: str = ""  # excellent, good, acceptable, needs_improvement, poor
    
    def to_dict(self) -> Dict:
        return {
            "total_score": round(self.total_score, 4),
            "normalized_score": round(self.normalized_score, 2),
            "quality_level": self.quality_level,
            "categories": {k: v.to_dict() for k, v in self.categories.items()},
            "feedback": self.feedback,
            "improvement_suggestions": self.improvement_suggestions
        }


class RubricEvaluator:
    """
    基于评分细则的综述评估器
    
    该评估器使用结构化的评分细则对综述进行多维度评估，
    并生成定向优化建议。
    
    Attributes:
        rubric: 评分细则配置
        chat_agent: LLM 对话代理
        use_llm: 是否使用 LLM 进行评估
    """
    
    DEFAULT_RUBRIC_PATH = Path(__file__).parent.parent.parent.parent / "resources/rubrics/survey_review_rubric.json"
    
    def __init__(
        self,
        chat_agent: Optional[ChatAgent] = None,
        rubric_path: Optional[str] = None,
        use_llm: bool = True
    ):
        """
        初始化评估器
        
        Args:
            chat_agent: LLM 对话代理
            rubric_path: 评分细则配置文件路径
            use_llm: 是否使用 LLM 进行评估
        """
        self.chat_agent = chat_agent
        self.use_llm = use_llm and chat_agent is not None
        
        # 加载评分细则
        if rubric_path is None:
            rubric_path = self.DEFAULT_RUBRIC_PATH
        
        self.rubric = self._load_rubric(rubric_path)
        self.quality_thresholds = self.rubric.get("quality_thresholds", {
            "excellent": 4.5,
            "good": 4.0,
            "acceptable": 3.5,
            "needs_improvement": 3.0,
            "poor": 2.0
        })
        
    def _load_rubric(self, rubric_path) -> Dict[str, Any]:
        """加载评分细则配置"""
        rubric_path = Path(rubric_path)
        
        if not rubric_path.exists():
            logger.warning(f"评分细则文件不存在: {rubric_path}，使用默认配置")
            return self._get_default_rubric()
        
        try:
            with open(rubric_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载评分细则失败: {e}")
            return self._get_default_rubric()
    
    def _get_default_rubric(self) -> Dict[str, Any]:
        """获取默认评分细则"""
        return {
            "version": "1.0",
            "categories": {
                "Scope": {
                    "name": "范围与目标",
                    "weight": 0.15,
                    "subcriteria": {
                        "Objectives": {"name": "研究目标", "weight": 0.4},
                        "Relevance": {"name": "主题相关性", "weight": 0.3},
                        "Coverage": {"name": "覆盖范围", "weight": 0.3}
                    }
                },
                "Literature": {
                    "name": "文献综述",
                    "weight": 0.20,
                    "subcriteria": {
                        "Comprehensiveness": {"name": "全面性", "weight": 0.4},
                        "Balance": {"name": "平衡性", "weight": 0.3},
                        "Currency": {"name": "时效性", "weight": 0.3}
                    }
                },
                "Analysis": {
                    "name": "分析深度",
                    "weight": 0.20,
                    "subcriteria": {
                        "Depth": {"name": "分析深度", "weight": 0.4},
                        "Integration": {"name": "整合性", "weight": 0.3},
                        "Critical_Thinking": {"name": "批判性思维", "weight": 0.3}
                    }
                },
                "Organization": {
                    "name": "组织结构",
                    "weight": 0.15,
                    "subcriteria": {
                        "Logical_Flow": {"name": "逻辑流程", "weight": 0.4},
                        "Section_Clarity": {"name": "章节清晰度", "weight": 0.3},
                        "Taxonomy": {"name": "分类体系", "weight": 0.3}
                    }
                },
                "Presentation": {
                    "name": "表达呈现",
                    "weight": 0.15,
                    "subcriteria": {
                        "Language": {"name": "语言质量", "weight": 0.4},
                        "Visuals": {"name": "视觉元素", "weight": 0.3},
                        "Tables": {"name": "表格质量", "weight": 0.3}
                    }
                },
                "References": {
                    "name": "参考文献",
                    "weight": 0.15,
                    "subcriteria": {
                        "Accuracy": {"name": "引用准确性", "weight": 0.5},
                        "Appropriateness": {"name": "引用适当性", "weight": 0.5}
                    }
                }
            },
            "quality_thresholds": {
                "excellent": 4.5,
                "good": 4.0,
                "acceptable": 3.5,
                "needs_improvement": 3.0,
                "poor": 2.0
            }
        }
    
    def evaluate(
        self,
        survey_content: str,
        detailed: bool = True,
        topic: str = "",
        outline: Optional[Dict] = None
    ) -> RubricEvaluationResult:
        """
        评估综述质量
        
        Args:
            survey_content: 综述内容 (LaTeX 或纯文本)
            detailed: 是否返回详细评分
            topic: 综述主题
            outline: 大纲结构
            
        Returns:
            评估结果
        """
        logger.info("开始基于评分细则的综述评估")
        
        result = RubricEvaluationResult()
        categories = self.rubric.get("categories", {})
        
        for category_key, category_info in categories.items():
            category_result = self._evaluate_category(
                survey_content=survey_content,
                category_key=category_key,
                category_info=category_info,
                topic=topic,
                outline=outline
            )
            result.categories[category_key] = category_result
        
        # 计算总分
        result.total_score = self._calculate_total_score(result.categories)
        result.normalized_score = (result.total_score / 5.0) * 100
        
        # 确定质量等级
        result.quality_level = self._determine_quality_level(result.total_score)
        
        # 生成反馈
        result.feedback = self._generate_overall_feedback(result)
        
        # 生成改进建议
        result.improvement_suggestions = self._generate_improvement_suggestions(result)
        
        logger.info(f"评估完成: 总分={result.total_score:.2f}/5.0, 质量等级={result.quality_level}")
        
        return result
    
    def _evaluate_category(
        self,
        survey_content: str,
        category_key: str,
        category_info: Dict[str, Any],
        topic: str,
        outline: Optional[Dict]
    ) -> CategoryResult:
        """评估单个类别"""
        category_result = CategoryResult(
            name=category_key,
            display_name=category_info.get("name", category_key),
            weight=category_info.get("weight", 0.15)
        )
        
        subcriteria = category_info.get("subcriteria", {})
        
        for sub_key, sub_info in subcriteria.items():
            sub_result = self._evaluate_subcriterion(
                survey_content=survey_content,
                category_key=category_key,
                category_name=category_info.get("name", category_key),
                subcriterion_key=sub_key,
                subcriterion_info=sub_info,
                topic=topic
            )
            category_result.subcriteria.append(sub_result)
        
        return category_result
    
    def _evaluate_subcriterion(
        self,
        survey_content: str,
        category_key: str,
        category_name: str,
        subcriterion_key: str,
        subcriterion_info: Dict[str, Any],
        topic: str
    ) -> SubcriterionResult:
        """评估单个子标准"""
        sub_name = subcriterion_info.get("name", subcriterion_key)
        sub_weight = subcriterion_info.get("weight", 0.33)
        levels = subcriterion_info.get("levels", {})
        
        if self.use_llm:
            score, feedback = self._llm_evaluate_subcriterion(
                survey_content=survey_content,
                category_name=category_name,
                subcriterion_name=sub_name,
                levels=levels,
                topic=topic
            )
        else:
            # 不使用 LLM 时，使用启发式评估
            score, feedback = self._heuristic_evaluate_subcriterion(
                survey_content=survey_content,
                category_key=category_key,
                subcriterion_key=subcriterion_key
            )
        
        # 获取对应分数的描述
        level_description = levels.get(str(int(score)), levels.get(str(round(score)), ""))
        
        return SubcriterionResult(
            name=sub_name,
            score=score,
            weight=sub_weight,
            feedback=feedback,
            level_description=level_description
        )
    
    def _llm_evaluate_subcriterion(
        self,
        survey_content: str,
        category_name: str,
        subcriterion_name: str,
        levels: Dict[str, str],
        topic: str
    ) -> Tuple[float, str]:
        """使用 LLM 评估子标准"""
        # 构建评分标准描述
        levels_desc = "\n".join([
            f"{score}分: {desc}" for score, desc in sorted(levels.items(), reverse=True)
        ])
        
        # 限制内容长度
        content_excerpt = survey_content[:8000] if len(survey_content) > 8000 else survey_content
        
        prompt = f"""请评估以下综述在 "{category_name} - {subcriterion_name}" 维度的质量。

## 综述主题
{topic or "学术综述"}

## 评分标准
{levels_desc}

## 综述内容
{content_excerpt}

## 评估要求
1. 仔细阅读综述内容
2. 根据评分标准进行评估
3. 给出 1-5 分的整数评分
4. 提供具体的反馈说明

## 输出格式
请严格按照以下 JSON 格式输出:
```json
{{
    "score": <1-5的整数>,
    "feedback": "<具体反馈，说明为什么给这个分数>"
}}
```

请输出评估结果:
"""
        
        try:
            chat_once = getattr(self.chat_agent, "remote_chat_no_retry", None)
            if not callable(chat_once):
                logger.warning("RubricEvaluator requires remote_chat_no_retry; using fallback score")
                return 3.0, "评估失败: remote_chat_no_retry unavailable"

            response = chat_once(prompt, temperature=0.3, timeout=120)
            if not response or str(response).strip().lower().startswith(("error", "timeout")):
                raise RuntimeError(str(response)[:200])
            result = self._parse_llm_response(response)
            score = max(1, min(5, int(result.get("score", 3))))
            feedback = result.get("feedback", "评估完成")
            return float(score), feedback
        except Exception as e:
            logger.warning(f"LLM 评估失败: {e}")
            return 3.0, f"评估失败: {str(e)}"
    
    def _heuristic_evaluate_subcriterion(
        self,
        survey_content: str,
        category_key: str,
        subcriterion_key: str
    ) -> Tuple[float, str]:
        """启发式评估子标准 (不使用 LLM)"""
        # 基于简单的启发式规则进行评估
        content_length = len(survey_content)
        
        # 基础分数
        base_score = 3.0
        
        # 根据内容长度调整
        if content_length > 50000:
            base_score += 0.5
        elif content_length > 30000:
            base_score += 0.3
        elif content_length < 10000:
            base_score -= 0.5
        
        # 根据类别进行特定检查
        if category_key == "References":
            # 检查引用数量
            cite_count = survey_content.count("\\cite{")
            if cite_count > 50:
                base_score += 0.5
            elif cite_count > 30:
                base_score += 0.3
            elif cite_count < 10:
                base_score -= 0.5
        
        elif category_key == "Organization":
            # 检查章节结构
            section_count = survey_content.count("\\section{")
            subsection_count = survey_content.count("\\subsection{")
            if section_count >= 5 and subsection_count >= 10:
                base_score += 0.3
        
        elif category_key == "Presentation":
            # 检查表格和图片
            table_count = survey_content.count("\\begin{table")
            figure_count = survey_content.count("\\begin{figure")
            if table_count >= 3 and figure_count >= 3:
                base_score += 0.3
        
        # 确保分数在 1-5 范围内
        score = max(1.0, min(5.0, base_score))
        
        return score, "基于启发式规则评估"
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 响应"""
        try:
            # 尝试提取 JSON
            json_str = response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            
            return json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            # 尝试直接解析
            try:
                return json.loads(response.strip())
            except:
                return {"score": 3, "feedback": "响应解析失败"}
    
    def _calculate_total_score(self, categories: Dict[str, CategoryResult]) -> float:
        """计算总分"""
        if not categories:
            return 0.0
        
        total_weighted_score = sum(cat.weighted_score for cat in categories.values())
        total_weight = sum(cat.weight for cat in categories.values())
        
        if total_weight == 0:
            return 0.0
        
        return total_weighted_score / total_weight
    
    def _determine_quality_level(self, score: float) -> str:
        """确定质量等级"""
        if score >= self.quality_thresholds.get("excellent", 4.5):
            return "excellent"
        elif score >= self.quality_thresholds.get("good", 4.0):
            return "good"
        elif score >= self.quality_thresholds.get("acceptable", 3.5):
            return "acceptable"
        elif score >= self.quality_thresholds.get("needs_improvement", 3.0):
            return "needs_improvement"
        else:
            return "poor"
    
    def _generate_overall_feedback(self, result: RubricEvaluationResult) -> List[str]:
        """生成总体反馈"""
        feedback = []
        
        # 质量等级反馈
        level_feedback = self.rubric.get("feedback_templates", {}).get(
            result.quality_level,
            f"综述质量等级: {result.quality_level}"
        )
        feedback.append(level_feedback)
        
        # 找出最强和最弱的维度
        if result.categories:
            sorted_categories = sorted(
                result.categories.items(),
                key=lambda x: x[1].score,
                reverse=True
            )
            
            strongest = sorted_categories[0]
            weakest = sorted_categories[-1]
            
            feedback.append(f"最强维度: {strongest[1].display_name} (得分: {strongest[1].score:.2f})")
            feedback.append(f"最需改进: {weakest[1].display_name} (得分: {weakest[1].score:.2f})")
        
        return feedback
    
    def _generate_improvement_suggestions(
        self,
        result: RubricEvaluationResult,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """生成改进建议"""
        suggestions = []
        
        # 收集所有低分项
        for category_key, category in result.categories.items():
            for sub in category.subcriteria:
                if sub.score < 4:  # 低于 4 分的都需要改进
                    suggestions.append({
                        "category": category.display_name,
                        "subcriterion": sub.name,
                        "current_score": sub.score,
                        "feedback": sub.feedback,
                        "target_level": sub.level_description if sub.score < 5 else "",
                        "priority": 5 - sub.score  # 分数越低优先级越高
                    })
        
        # 按优先级排序
        suggestions.sort(key=lambda x: x["priority"], reverse=True)
        
        return suggestions[:top_k]
    
    def get_targeted_refinement_prompt(
        self,
        result: RubricEvaluationResult,
        top_k: int = 3
    ) -> str:
        """
        基于评估结果生成定向优化提示
        
        Args:
            result: 评估结果
            top_k: 返回前 k 个最需要改进的维度
            
        Returns:
            优化提示字符串
        """
        suggestions = result.improvement_suggestions[:top_k]
        
        if not suggestions:
            return "综述质量良好，无需特别改进。"
        
        prompt_parts = ["请针对以下维度进行定向优化：\n"]
        
        for i, suggestion in enumerate(suggestions, 1):
            prompt_parts.append(f"""
{i}. **{suggestion['category']} - {suggestion['subcriterion']}**
   - 当前得分: {suggestion['current_score']}/5
   - 问题: {suggestion['feedback']}
   - 目标: 达到 4-5 分水平
""")
        
        prompt_parts.append("\n请根据以上反馈进行针对性改进。")
        
        return "\n".join(prompt_parts)
    
    def evaluate_section(
        self,
        section_content: str,
        section_name: str,
        topic: str = ""
    ) -> Dict[str, Any]:
        """
        评估单个章节
        
        Args:
            section_content: 章节内容
            section_name: 章节名称
            topic: 综述主题
            
        Returns:
            章节评估结果
        """
        # 对章节进行简化评估，只评估相关维度
        relevant_categories = ["Analysis", "Presentation", "Organization"]
        
        result = {
            "section_name": section_name,
            "scores": {},
            "feedback": [],
            "overall_score": 0.0
        }
        
        categories = self.rubric.get("categories", {})
        total_score = 0.0
        count = 0
        
        for category_key in relevant_categories:
            if category_key not in categories:
                continue
            
            category_info = categories[category_key]
            category_result = self._evaluate_category(
                survey_content=section_content,
                category_key=category_key,
                category_info=category_info,
                topic=topic,
                outline=None
            )
            
            result["scores"][category_key] = {
                "score": category_result.score,
                "display_name": category_result.display_name
            }
            
            total_score += category_result.score
            count += 1
            
            # 收集低分反馈
            for sub in category_result.subcriteria:
                if sub.score < 4:
                    result["feedback"].append(f"{sub.name}: {sub.feedback}")
        
        if count > 0:
            result["overall_score"] = total_score / count
        
        return result


# 便捷函数
def evaluate_survey_with_rubric(
    survey_content: str,
    chat_agent: Optional[ChatAgent] = None,
    rubric_path: Optional[str] = None,
    topic: str = "",
    use_llm: bool = True
) -> RubricEvaluationResult:
    """
    使用评分细则评估综述
    
    Args:
        survey_content: 综述内容
        chat_agent: LLM 对话代理
        rubric_path: 评分细则配置文件路径
        topic: 综述主题
        use_llm: 是否使用 LLM
        
    Returns:
        评估结果
    """
    evaluator = RubricEvaluator(
        chat_agent=chat_agent,
        rubric_path=rubric_path,
        use_llm=use_llm
    )
    
    return evaluator.evaluate(
        survey_content=survey_content,
        topic=topic
    )


if __name__ == "__main__":
    # 测试代码
    from src.models.monitor.token_monitor import TokenMonitor
    
    # 创建测试用的 ChatAgent
    token_monitor = TokenMonitor("test", "rubric_evaluation_test")
    chat_agent = ChatAgent(token_monitor)
    
    # 测试内容
    test_content = """
\\section{Introduction}
Large Language Models (LLMs) have revolutionized natural language processing in recent years.
This survey provides a comprehensive overview of the field.

\\section{Background}
The development of LLMs can be traced back to the transformer architecture.

\\section{Methods}
\\subsection{Pre-training}
Pre-training involves training on large corpora.

\\subsection{Fine-tuning}
Fine-tuning adapts models to specific tasks.

\\section{Applications}
LLMs have been applied to various domains.

\\section{Challenges}
Several challenges remain in the field.

\\section{Conclusion}
This survey has provided an overview of LLMs.
"""
    
    # 不使用 LLM 的快速测试
    result = evaluate_survey_with_rubric(
        survey_content=test_content,
        chat_agent=None,
        topic="Large Language Models",
        use_llm=False
    )
    
    print("评估结果:")
    print(f"总分: {result.total_score:.2f}/5.0")
    print(f"质量等级: {result.quality_level}")
    print(f"反馈: {result.feedback}")
