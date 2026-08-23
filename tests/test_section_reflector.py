"""
SectionReflector 单元测试

测试章节级反思模块的核心功能。
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from typing import Dict, Any

import sys
from pathlib import Path

# 添加项目根目录到路径
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.modules.post_refine.section_reflector import (
    SectionReflector,
    SectionReflectionResult,
    EvaluationDetail,
    RegenerationDetail,
    reflect_section_sync
)


class TestSectionReflectionResult:
    """测试 SectionReflectionResult 数据模型"""
    
    def test_create_valid_result(self):
        """测试创建有效的反思结果"""
        result = SectionReflectionResult(
            meets_requirements=True,
            feedback="内容质量良好",
            improvement_queries=["query1", "query2"],
            scores={"coverage": 4.0, "coherence": 4.5}
        )
        
        assert result.meets_requirements is True
        assert result.feedback == "内容质量良好"
        assert len(result.improvement_queries) == 2
        assert result.scores["coverage"] == 4.0
    
    def test_empty_feedback_validation(self):
        """测试空反馈的验证"""
        result = SectionReflectionResult(
            meets_requirements=False,
            feedback="",
            improvement_queries=[]
        )
        
        # 空反馈应该被替换为默认值
        assert result.feedback == "未提供具体反馈。"
    
    def test_whitespace_feedback_validation(self):
        """测试空白反馈的验证"""
        result = SectionReflectionResult(
            meets_requirements=False,
            feedback="   ",
            improvement_queries=[]
        )
        
        assert result.feedback == "未提供具体反馈。"


class TestSectionReflector:
    """测试 SectionReflector 类"""
    
    @pytest.fixture
    def mock_chat_agent(self):
        """创建模拟的 ChatAgent"""
        agent = Mock()
        agent.remote_chat = Mock(return_value='{"scores": {"coverage": 4, "coherence": 4, "citation": 4, "analysis": 4, "writing": 4}, "meets_requirements": true, "feedback": "Good quality", "improvement_queries": []}')
        return agent
    
    @pytest.fixture
    def reflector(self, mock_chat_agent):
        """创建 SectionReflector 实例"""
        return SectionReflector(
            chat_agent=mock_chat_agent,
            quality_threshold=3.5,
            max_iterations=3
        )
    
    def test_init(self, reflector):
        """测试初始化"""
        assert reflector.quality_threshold == 3.5
        assert reflector.max_iterations == 3
        assert len(reflector.EVALUATION_DIMENSIONS) == 5
    
    def test_content_hash(self, reflector):
        """测试内容哈希计算"""
        content1 = "This is test content"
        content2 = "This is test content"
        content3 = "Different content"
        
        hash1 = reflector._content_hash(content1)
        hash2 = reflector._content_hash(content2)
        hash3 = reflector._content_hash(content3)
        
        assert hash1 == hash2  # 相同内容应该有相同哈希
        assert hash1 != hash3  # 不同内容应该有不同哈希
    
    def test_calculate_weighted_score(self, reflector):
        """测试加权分数计算"""
        scores = {
            "coverage": 4.0,
            "coherence": 4.0,
            "citation": 4.0,
            "analysis": 4.0,
            "writing": 4.0
        }
        
        weighted_score = reflector._calculate_weighted_score(scores)
        
        # 所有维度都是 4.0，加权平均也应该是 4.0
        assert abs(weighted_score - 4.0) < 0.01
    
    def test_calculate_weighted_score_partial(self, reflector):
        """测试部分分数的加权计算"""
        scores = {
            "coverage": 5.0,  # weight: 0.25
            "coherence": 3.0,  # weight: 0.20
        }
        
        weighted_score = reflector._calculate_weighted_score(scores)
        
        # (5.0 * 0.25 + 3.0 * 0.20) / (0.25 + 0.20) = 1.85 / 0.45 ≈ 4.11
        expected = (5.0 * 0.25 + 3.0 * 0.20) / (0.25 + 0.20)
        assert abs(weighted_score - expected) < 0.01
    
    def test_parse_evaluation_response_valid_json(self, reflector):
        """测试解析有效的 JSON 响应"""
        response = '''```json
{
    "scores": {"coverage": 4, "coherence": 4, "citation": 4, "analysis": 4, "writing": 4},
    "meets_requirements": true,
    "feedback": "Good quality content",
    "improvement_queries": ["query1"]
}
```'''
        
        result = reflector._parse_evaluation_response(response)
        
        assert result.meets_requirements is True
        assert result.feedback == "Good quality content"
        assert len(result.improvement_queries) == 1
    
    def test_parse_evaluation_response_invalid_json(self, reflector):
        """测试解析无效的 JSON 响应"""
        response = "This is not valid JSON"
        
        result = reflector._parse_evaluation_response(response)
        
        # 应该返回默认结果
        assert result.meets_requirements is False
        assert "解析失败" in result.feedback
    
    def test_extract_improved_content(self, reflector):
        """测试提取改进后的内容"""
        response = '''```latex
This is the improved content.
With multiple lines.
```'''
        
        content = reflector._extract_improved_content(response)
        
        assert "This is the improved content" in content
        assert "```" not in content
    
    def test_build_evaluation_prompt(self, reflector):
        """测试构建评估提示词"""
        prompt = reflector._build_evaluation_prompt(
            section_name="Introduction",
            content="Test content",
            paper_title="Test Paper",
            user_query="Test query",
            outline={"title": "Test"}
        )
        
        assert "Introduction" in prompt
        assert "Test content" in prompt
        assert "Test Paper" in prompt
        assert "coverage" in prompt.lower()


class TestReflectSectionSync:
    """测试同步反思函数"""
    
    def test_reflect_section_sync_basic(self):
        """测试基本的同步反思功能"""
        # 创建模拟的 ChatAgent
        mock_agent = Mock()
        
        # 模拟评估响应
        eval_response = json.dumps({
            "scores": {"coverage": 4, "coherence": 4, "citation": 4, "analysis": 4, "writing": 4},
            "meets_requirements": True,
            "feedback": "Good quality",
            "improvement_queries": []
        })
        
        # 模拟摘要响应
        summary_response = "This section discusses the introduction."
        
        mock_agent.remote_chat = Mock(side_effect=[eval_response, summary_response])
        
        result = reflect_section_sync(
            chat_agent=mock_agent,
            section_name="Introduction",
            section_content="Test content for introduction.",
            paper_title="Test Paper",
            user_query="Test query",
            outline={"title": "Test"},
            max_iterations=1,
            quality_threshold=3.5
        )
        
        assert "section_name" in result
        assert "final_content" in result
        assert "meets_requirements" in result
        assert "iterations" in result


class TestEvaluationDetail:
    """测试 EvaluationDetail 数据模型"""
    
    def test_create_evaluation_detail(self):
        """测试创建评估详情"""
        detail = EvaluationDetail(
            iteration=1,
            timestamp=1234567890.0,
            scores={"coverage": 4.0},
            meets_requirements=True,
            feedback="Good",
            improvement_queries=["query1"],
            content_hash="abc123",
            duration_seconds=1.5
        )
        
        assert detail.iteration == 1
        assert detail.meets_requirements is True
        assert detail.duration_seconds == 1.5


class TestRegenerationDetail:
    """测试 RegenerationDetail 数据模型"""
    
    def test_create_regeneration_detail(self):
        """测试创建重生成详情"""
        detail = RegenerationDetail(
            iteration=1,
            timestamp=1234567890.0,
            feedback_used="Need improvement",
            queries_used=["query1"],
            success=True,
            duration_seconds=2.0
        )
        
        assert detail.iteration == 1
        assert detail.success is True
        assert detail.duration_seconds == 2.0


# 集成测试（需要实际的 LLM 连接，默认跳过）
@pytest.mark.skip(reason="需要实际的 LLM 连接")
class TestSectionReflectorIntegration:
    """集成测试"""
    
    def test_full_reflection_cycle(self):
        """测试完整的反思循环"""
        from src.models.LLM import ChatAgent
        from src.models.monitor.token_monitor import TokenMonitor
        
        token_monitor = TokenMonitor("test", "integration_test")
        chat_agent = ChatAgent(token_monitor)
        
        reflector = SectionReflector(
            chat_agent=chat_agent,
            quality_threshold=3.5,
            max_iterations=2
        )
        
        test_content = """
        Large Language Models (LLMs) have revolutionized NLP.
        This section provides an overview of recent developments.
        """
        
        result = asyncio.run(reflector.reflect_section(
            section_name="Introduction",
            section_content=test_content,
            paper_title="A Survey on LLMs",
            user_query="Large Language Models",
            outline={"title": "A Survey on LLMs"}
        ))
        
        assert "final_content" in result
        assert "meets_requirements" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])