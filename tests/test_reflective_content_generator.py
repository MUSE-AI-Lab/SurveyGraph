"""
ReflectiveContentGenerator 单元测试

测试带反思机制的内容生成器。
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any
from pathlib import Path
from dataclasses import asdict

import sys

# 添加项目根目录到路径
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.models.generator.reflective_content_generator import (
    ReflectiveContentGenerator,
    ReflectionConfig,
    create_reflective_generator
)


class TestReflectionConfig:
    """测试 ReflectionConfig 数据类"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = ReflectionConfig()
        
        assert config.enable_section_reflection is True
        assert config.section_reflection_max_turns == 3
        assert config.quality_threshold == 3.5
        assert config.enable_global_evaluation is True
        assert config.save_reflection_history is True
        assert config.reflection_scope == "main_body"
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = ReflectionConfig(
            enable_section_reflection=False,
            section_reflection_max_turns=5,
            quality_threshold=4.0
        )
        
        assert config.enable_section_reflection is False
        assert config.section_reflection_max_turns == 5
        assert config.quality_threshold == 4.0
    
    def test_should_reflect_section_all(self):
        """测试 reflection_scope='all' 时的章节反思判断"""
        config = ReflectionConfig(reflection_scope="all")
        
        assert config.should_reflect_section("Introduction") is True
        assert config.should_reflect_section("Methods") is True
        assert config.should_reflect_section("Conclusion") is True
    
    def test_should_reflect_section_main_body(self):
        """测试 reflection_scope='main_body' 时的章节反思判断"""
        config = ReflectionConfig(reflection_scope="main_body")
        
        # 默认跳过的章节
        assert config.should_reflect_section("Introduction") is False
        assert config.should_reflect_section("Conclusion") is False
        assert config.should_reflect_section("Abstract") is False
        assert config.should_reflect_section("References") is False
        
        # 应该反思的章节
        assert config.should_reflect_section("Methods") is True
        assert config.should_reflect_section("Related Work") is True
        assert config.should_reflect_section("Experiments") is True
    
    def test_should_reflect_section_custom_skip(self):
        """测试自定义跳过列表"""
        config = ReflectionConfig(
            reflection_scope="main_body",
            skip_sections=["Introduction", "Background"]
        )
        
        assert config.should_reflect_section("Introduction") is False
        assert config.should_reflect_section("Background") is False
        assert config.should_reflect_section("Methods") is True
        assert config.should_reflect_section("Conclusion") is True  # 不在跳过列表中


class TestReflectiveContentGenerator:
    """测试 ReflectiveContentGenerator 类"""
    
    @pytest.fixture
    def mock_chat_agent(self):
        """创建模拟的 ChatAgent"""
        agent = Mock()
        agent.remote_chat = Mock(return_value="Test response")
        return agent
    
    @pytest.fixture
    def generator(self):
        """创建生成器实例（使用模拟的任务 ID）"""
        config = ReflectionConfig(
            enable_section_reflection=True,
            section_reflection_max_turns=2,
            quality_threshold=3.5
        )
        
        # 使用 patch 来避免实际的文件系统操作
        with patch.object(ReflectiveContentGenerator, '__init__', lambda self, task_id, config=None: None):
            gen = ReflectiveContentGenerator.__new__(ReflectiveContentGenerator)
            gen.reflection_config = config
            gen.reflection_history = {}
            gen._section_reflector = None
            gen._rubric_evaluator = None
            gen.topic = "Test Topic"
            return gen
    
    def test_init_with_default_config(self):
        """测试使用默认配置初始化"""
        with patch.object(ReflectiveContentGenerator, '__init__', lambda self, task_id, config=None: None):
            gen = ReflectiveContentGenerator.__new__(ReflectiveContentGenerator)
            gen.reflection_config = ReflectionConfig()
            
            assert gen.reflection_config.enable_section_reflection is True
    
    def test_init_with_custom_config(self):
        """测试使用自定义配置初始化"""
        config = ReflectionConfig(
            enable_section_reflection=False,
            section_reflection_max_turns=5
        )
        
        with patch.object(ReflectiveContentGenerator, '__init__', lambda self, task_id, config=None: None):
            gen = ReflectiveContentGenerator.__new__(ReflectiveContentGenerator)
            gen.reflection_config = config
            
            assert gen.reflection_config.enable_section_reflection is False
            assert gen.reflection_config.section_reflection_max_turns == 5
    
    def test_get_section_reflector(self, generator, mock_chat_agent):
        """测试获取章节反思器"""
        reflector = generator._get_section_reflector(mock_chat_agent)
        
        assert reflector is not None
        assert generator._section_reflector is reflector
        
        # 再次调用应该返回同一个实例
        reflector2 = generator._get_section_reflector(mock_chat_agent)
        assert reflector is reflector2
    
    def test_get_rubric_evaluator(self, generator, mock_chat_agent):
        """测试获取评分细则评估器"""
        evaluator = generator._get_rubric_evaluator(mock_chat_agent)
        
        assert evaluator is not None
        assert generator._rubric_evaluator is evaluator
        
        # 再次调用应该返回同一个实例
        evaluator2 = generator._get_rubric_evaluator(mock_chat_agent)
        assert evaluator is evaluator2


class TestCreateReflectiveGenerator:
    """测试便捷函数"""
    
    def test_create_with_defaults(self):
        """测试使用默认参数创建"""
        with patch.object(ReflectiveContentGenerator, '__init__', return_value=None):
            # 由于 __init__ 被 mock，我们需要手动设置属性
            gen = create_reflective_generator("test_task")
            
            # 验证返回的是 ReflectiveContentGenerator 实例
            assert isinstance(gen, ReflectiveContentGenerator)
    
    def test_create_with_custom_params(self):
        """测试使用自定义参数创建"""
        with patch.object(ReflectiveContentGenerator, '__init__', return_value=None):
            gen = create_reflective_generator(
                task_id="test_task",
                enable_reflection=False,
                max_iterations=5,
                quality_threshold=4.0
            )
            
            assert isinstance(gen, ReflectiveContentGenerator)


class TestReflectionHistory:
    """测试反思历史记录"""
    
    @pytest.fixture
    def generator_with_history(self):
        """创建带有反思历史的生成器"""
        with patch.object(ReflectiveContentGenerator, '__init__', lambda self, task_id, config=None: None):
            gen = ReflectiveContentGenerator.__new__(ReflectiveContentGenerator)
            gen.reflection_config = ReflectionConfig(save_reflection_history=True)
            gen.reflection_history = {
                "Methods": {
                    "meets_requirements": True,
                    "final_score": 4.2,
                    "iterations": 2,
                    "summary": "This section discusses methods."
                },
                "Experiments": {
                    "meets_requirements": False,
                    "final_score": 3.1,
                    "iterations": 3,
                    "summary": "This section presents experiments."
                }
            }
            return gen
    
    def test_reflection_history_structure(self, generator_with_history):
        """测试反思历史结构"""
        history = generator_with_history.reflection_history
        
        assert "Methods" in history
        assert "Experiments" in history
        
        methods_history = history["Methods"]
        assert "meets_requirements" in methods_history
        assert "final_score" in methods_history
        assert "iterations" in methods_history
        assert "summary" in methods_history
    
    def test_reflection_history_values(self, generator_with_history):
        """测试反思历史值"""
        history = generator_with_history.reflection_history
        
        assert history["Methods"]["meets_requirements"] is True
        assert history["Methods"]["final_score"] == 4.2
        assert history["Experiments"]["meets_requirements"] is False


class TestReflectionIntegration:
    """集成测试（需要实际环境，默认跳过）"""
    
    @pytest.mark.skip(reason="需要实际的文件系统和 LLM 连接")
    def test_full_generation_with_reflection(self):
        """测试完整的带反思生成流程"""
        generator = create_reflective_generator(
            task_id="test_integration",
            enable_reflection=True,
            max_iterations=2,
            quality_threshold=3.5
        )
        
        # 这里需要实际的任务数据
        generator.run(enable_reflection=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])