"""
RubricEvaluator 单元测试

测试评分细则评估器的核心功能。
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any
from pathlib import Path

import sys

# 添加项目根目录到路径
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.modules.post_refine.rubric_evaluator import (
    RubricEvaluator,
    RubricEvaluationResult,
    CategoryResult,
    SubcriterionResult,
    evaluate_survey_with_rubric
)


class TestSubcriterionResult:
    """测试 SubcriterionResult 数据模型"""
    
    def test_create_subcriterion_result(self):
        """测试创建子标准结果"""
        result = SubcriterionResult(
            name="研究目标",
            score=4.0,
            weight=0.4,
            feedback="目标清晰明确",
            level_description="研究目标在摘要和引言中清晰明确陈述"
        )
        
        assert result.name == "研究目标"
        assert result.score == 4.0
        assert result.weight == 0.4
    
    def test_weighted_score(self):
        """测试加权分数计算"""
        result = SubcriterionResult(
            name="Test",
            score=4.0,
            weight=0.5,
            feedback="",
            level_description=""
        )
        
        assert result.weighted_score == 2.0  # 4.0 * 0.5
    
    def test_to_dict(self):
        """测试转换为字典"""
        result = SubcriterionResult(
            name="Test",
            score=4.0,
            weight=0.5,
            feedback="Good",
            level_description="Level 4"
        )
        
        d = result.to_dict()
        
        assert d["name"] == "Test"
        assert d["score"] == 4.0
        assert d["weight"] == 0.5
        assert d["weighted_score"] == 2.0
        assert d["feedback"] == "Good"


class TestCategoryResult:
    """测试 CategoryResult 数据模型"""
    
    def test_create_category_result(self):
        """测试创建类别结果"""
        result = CategoryResult(
            name="Scope",
            display_name="范围与目标",
            weight=0.15
        )
        
        assert result.name == "Scope"
        assert result.display_name == "范围与目标"
        assert result.weight == 0.15
    
    def test_score_calculation(self):
        """测试分数计算"""
        result = CategoryResult(
            name="Scope",
            display_name="范围与目标",
            weight=0.15,
            subcriteria=[
                SubcriterionResult("A", 4.0, 0.5, "", ""),
                SubcriterionResult("B", 3.0, 0.5, "", "")
            ]
        )
        
        # (4.0 * 0.5 + 3.0 * 0.5) / (0.5 + 0.5) = 3.5
        assert result.score == 3.5
    
    def test_weighted_score(self):
        """测试加权分数"""
        result = CategoryResult(
            name="Scope",
            display_name="范围与目标",
            weight=0.2,
            subcriteria=[
                SubcriterionResult("A", 4.0, 1.0, "", "")
            ]
        )
        
        # score = 4.0, weighted_score = 4.0 * 0.2 = 0.8
        assert result.weighted_score == 0.8
    
    def test_empty_subcriteria(self):
        """测试空子标准"""
        result = CategoryResult(
            name="Scope",
            display_name="范围与目标",
            weight=0.15
        )
        
        assert result.score == 0.0


class TestRubricEvaluationResult:
    """测试 RubricEvaluationResult 数据模型"""
    
    def test_create_result(self):
        """测试创建评估结果"""
        result = RubricEvaluationResult(
            total_score=4.0,
            normalized_score=80.0,
            quality_level="good"
        )
        
        assert result.total_score == 4.0
        assert result.normalized_score == 80.0
        assert result.quality_level == "good"
    
    def test_to_dict(self):
        """测试转换为字典"""
        result = RubricEvaluationResult(
            total_score=4.0,
            normalized_score=80.0,
            quality_level="good",
            feedback=["Good quality"],
            improvement_suggestions=[{"category": "Test", "score": 3}]
        )
        
        d = result.to_dict()
        
        assert d["total_score"] == 4.0
        assert d["normalized_score"] == 80.0
        assert d["quality_level"] == "good"
        assert len(d["feedback"]) == 1


class TestRubricEvaluator:
    """测试 RubricEvaluator 类"""
    
    @pytest.fixture
    def mock_chat_agent(self):
        """创建模拟的 ChatAgent"""
        agent = Mock()
        agent.remote_chat = Mock(return_value='{"score": 4, "feedback": "Good quality"}')
        return agent
    
    @pytest.fixture
    def evaluator_no_llm(self):
        """创建不使用 LLM 的评估器"""
        return RubricEvaluator(
            chat_agent=None,
            use_llm=False
        )
    
    @pytest.fixture
    def evaluator_with_llm(self, mock_chat_agent):
        """创建使用 LLM 的评估器"""
        return RubricEvaluator(
            chat_agent=mock_chat_agent,
            use_llm=True
        )
    
    def test_init_no_llm(self, evaluator_no_llm):
        """测试不使用 LLM 的初始化"""
        assert evaluator_no_llm.use_llm is False
        assert evaluator_no_llm.rubric is not None
        assert "categories" in evaluator_no_llm.rubric
    
    def test_init_with_llm(self, evaluator_with_llm):
        """测试使用 LLM 的初始化"""
        assert evaluator_with_llm.use_llm is True
    
    def test_load_default_rubric(self, evaluator_no_llm):
        """测试加载默认评分细则"""
        rubric = evaluator_no_llm.rubric
        
        assert "categories" in rubric
        assert "Scope" in rubric["categories"]
        assert "Literature" in rubric["categories"]
        assert "Analysis" in rubric["categories"]
    
    def test_determine_quality_level(self, evaluator_no_llm):
        """测试质量等级判定"""
        assert evaluator_no_llm._determine_quality_level(4.6) == "excellent"
        assert evaluator_no_llm._determine_quality_level(4.2) == "good"
        assert evaluator_no_llm._determine_quality_level(3.7) == "acceptable"
        assert evaluator_no_llm._determine_quality_level(3.2) == "needs_improvement"
        assert evaluator_no_llm._determine_quality_level(2.5) == "poor"
    
    def test_heuristic_evaluate_subcriterion(self, evaluator_no_llm):
        """测试启发式评估"""
        # 测试长内容
        long_content = "x" * 60000
        score, feedback = evaluator_no_llm._heuristic_evaluate_subcriterion(
            long_content, "Scope", "Objectives"
        )
        
        assert 1.0 <= score <= 5.0
        assert feedback == "基于启发式规则评估"
    
    def test_heuristic_evaluate_references(self, evaluator_no_llm):
        """测试引用相关的启发式评估"""
        # 创建包含多个引用的内容
        content = "\\cite{ref1} " * 60
        
        score, feedback = evaluator_no_llm._heuristic_evaluate_subcriterion(
            content, "References", "Accuracy"
        )
        
        # 多引用应该得到较高分数
        assert score >= 3.0
    
    def test_evaluate_no_llm(self, evaluator_no_llm):
        """测试不使用 LLM 的评估"""
        test_content = """
\\section{Introduction}
This is a test survey about Large Language Models.
\\cite{ref1} \\cite{ref2} \\cite{ref3}

\\section{Background}
Background information here.

\\section{Methods}
\\subsection{Pre-training}
Pre-training methods.

\\subsection{Fine-tuning}
Fine-tuning methods.

\\section{Conclusion}
Conclusion here.
"""
        
        result = evaluator_no_llm.evaluate(
            survey_content=test_content,
            topic="Large Language Models"
        )
        
        assert result.total_score > 0
        assert result.quality_level in ["excellent", "good", "acceptable", "needs_improvement", "poor"]
        assert len(result.categories) > 0
    
    def test_parse_llm_response_valid(self, evaluator_no_llm):
        """测试解析有效的 LLM 响应"""
        response = '{"score": 4, "feedback": "Good quality"}'
        
        result = evaluator_no_llm._parse_llm_response(response)
        
        assert result["score"] == 4
        assert result["feedback"] == "Good quality"
    
    def test_parse_llm_response_with_markdown(self, evaluator_no_llm):
        """测试解析带 markdown 的 LLM 响应"""
        response = '''```json
{"score": 4, "feedback": "Good quality"}
```'''
        
        result = evaluator_no_llm._parse_llm_response(response)
        
        assert result["score"] == 4
    
    def test_parse_llm_response_invalid(self, evaluator_no_llm):
        """测试解析无效的 LLM 响应"""
        response = "This is not JSON"
        
        result = evaluator_no_llm._parse_llm_response(response)
        
        assert result["score"] == 3  # 默认分数
    
    def test_generate_improvement_suggestions(self, evaluator_no_llm):
        """测试生成改进建议"""
        # 创建一个有低分项的结果
        result = RubricEvaluationResult()
        result.categories["Scope"] = CategoryResult(
            name="Scope",
            display_name="范围与目标",
            weight=0.15,
            subcriteria=[
                SubcriterionResult("Objectives", 2.0, 0.4, "需要改进", ""),
                SubcriterionResult("Relevance", 4.0, 0.3, "良好", ""),
            ]
        )
        
        suggestions = evaluator_no_llm._generate_improvement_suggestions(result)
        
        # 应该有一个低分项的建议
        assert len(suggestions) >= 1
        assert suggestions[0]["current_score"] == 2.0
    
    def test_get_targeted_refinement_prompt(self, evaluator_no_llm):
        """测试生成定向优化提示"""
        result = RubricEvaluationResult(
            improvement_suggestions=[
                {
                    "category": "范围与目标",
                    "subcriterion": "研究目标",
                    "current_score": 2,
                    "feedback": "目标不清晰"
                }
            ]
        )
        
        prompt = evaluator_no_llm.get_targeted_refinement_prompt(result)
        
        assert "范围与目标" in prompt
        assert "研究目标" in prompt
        assert "2" in prompt
    
    def test_evaluate_section(self, evaluator_no_llm):
        """测试章节评估"""
        section_content = """
This section discusses the methods used in LLM research.
Various approaches have been proposed including pre-training and fine-tuning.
"""
        
        result = evaluator_no_llm.evaluate_section(
            section_content=section_content,
            section_name="Methods",
            topic="Large Language Models"
        )
        
        assert "section_name" in result
        assert "scores" in result
        assert "overall_score" in result


class TestEvaluateSurveyWithRubric:
    """测试便捷函数"""
    
    def test_evaluate_without_llm(self):
        """测试不使用 LLM 的评估"""
        test_content = """
\\section{Introduction}
This is a test survey.

\\section{Methods}
Methods description.

\\section{Conclusion}
Conclusion.
"""
        
        result = evaluate_survey_with_rubric(
            survey_content=test_content,
            chat_agent=None,
            topic="Test Topic",
            use_llm=False
        )
        
        assert isinstance(result, RubricEvaluationResult)
        assert result.total_score > 0


class TestRubricFileLoading:
    """测试评分细则文件加载"""
    
    def test_load_existing_rubric(self):
        """测试加载存在的评分细则文件"""
        rubric_path = BASE_DIR / "resources" / "rubrics" / "survey_review_rubric.json"
        
        if rubric_path.exists():
            evaluator = RubricEvaluator(
                chat_agent=None,
                rubric_path=str(rubric_path),
                use_llm=False
            )
            
            assert evaluator.rubric is not None
            assert "categories" in evaluator.rubric
    
    def test_load_nonexistent_rubric(self):
        """测试加载不存在的评分细则文件"""
        evaluator = RubricEvaluator(
            chat_agent=None,
            rubric_path="/nonexistent/path/rubric.json",
            use_llm=False
        )
        
        # 应该使用默认评分细则
        assert evaluator.rubric is not None
        assert "categories" in evaluator.rubric


if __name__ == "__main__":
    pytest.main([__file__, "-v"])