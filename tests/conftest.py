"""
Pytest 配置文件

提供测试所需的 fixtures 和配置。
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

# 添加项目根目录到路径
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))


@pytest.fixture
def mock_chat_agent():
    """
    创建模拟的 ChatAgent
    
    返回一个 Mock 对象，可以用于测试不需要实际 LLM 调用的功能。
    """
    agent = Mock()
    agent.remote_chat = Mock(return_value='{"score": 4, "feedback": "Good quality"}')
    agent.batch_remote_chat = Mock(return_value=['{"score": 4}'] * 10)
    return agent


@pytest.fixture
def sample_survey_content():
    """
    提供示例综述内容
    """
    return """
\\title{A Survey on Large Language Models}

\\begin{abstract}
This survey provides a comprehensive overview of Large Language Models (LLMs).
\\end{abstract}

\\section{Introduction}
Large Language Models have revolutionized natural language processing.
This survey aims to provide a comprehensive overview of the field.

\\section{Background}
\\subsection{Transformer Architecture}
The transformer architecture \\cite{vaswani2017attention} introduced self-attention.

\\subsection{Pre-training Paradigms}
Pre-training on large corpora has become the standard approach.

\\section{Methods}
\\subsection{Pre-training}
Pre-training involves training on massive text corpora.

\\subsection{Fine-tuning}
Fine-tuning adapts pre-trained models to specific tasks.

\\section{Applications}
LLMs have been applied to various domains including:
\\begin{itemize}
\\item Text generation
\\item Question answering
\\item Code generation
\\end{itemize}

\\section{Challenges and Future Directions}
Several challenges remain in the field:
\\begin{enumerate}
\\item Computational costs
\\item Hallucination
\\item Bias and fairness
\\end{enumerate}

\\section{Conclusion}
This survey has provided an overview of LLMs and their applications.
"""


@pytest.fixture
def sample_outline():
    """
    提供示例大纲
    """
    return {
        "title": "A Survey on Large Language Models",
        "sections": [
            {
                "title": "Introduction",
                "desc": "Overview of LLMs",
                "sub": []
            },
            {
                "title": "Background",
                "desc": "Historical context",
                "sub": [
                    {"title": "Transformer Architecture", "desc": "Self-attention mechanism", "sub": []},
                    {"title": "Pre-training Paradigms", "desc": "Pre-training approaches", "sub": []}
                ]
            },
            {
                "title": "Methods",
                "desc": "Key techniques",
                "sub": [
                    {"title": "Pre-training", "desc": "Pre-training methods", "sub": []},
                    {"title": "Fine-tuning", "desc": "Fine-tuning approaches", "sub": []}
                ]
            },
            {
                "title": "Applications",
                "desc": "Application domains",
                "sub": []
            },
            {
                "title": "Challenges and Future Directions",
                "desc": "Open problems",
                "sub": []
            },
            {
                "title": "Conclusion",
                "desc": "Summary",
                "sub": []
            }
        ]
    }


@pytest.fixture
def sample_papers_data():
    """
    提供示例论文数据
    """
    return [
        {
            "bib_name": "vaswani2017attention",
            "title": "Attention Is All You Need",
            "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
            "year": 2017
        },
        {
            "bib_name": "devlin2019bert",
            "title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "abstract": "We introduce a new language representation model called BERT.",
            "year": 2019
        },
        {
            "bib_name": "brown2020gpt3",
            "title": "Language Models are Few-Shot Learners",
            "abstract": "Recent work has demonstrated substantial gains on many NLP tasks.",
            "year": 2020
        }
    ]


@pytest.fixture
def sample_section_content():
    """
    提供示例章节内容
    """
    return """
Large Language Models (LLMs) have emerged as a transformative technology in natural language processing.
These models, characterized by their massive scale and extensive pre-training, have demonstrated remarkable
capabilities across a wide range of tasks \\cite{brown2020gpt3}.

The development of LLMs can be traced back to the introduction of the transformer architecture
\\cite{vaswani2017attention}, which replaced recurrent neural networks with self-attention mechanisms.
This architectural innovation enabled more efficient parallel processing and better capture of long-range
dependencies in text.

Subsequent work on pre-training paradigms, such as BERT \\cite{devlin2019bert} and GPT, established
the foundation for modern LLMs. These models are first pre-trained on large text corpora using
self-supervised objectives, then fine-tuned for specific downstream tasks.
"""


# 配置 pytest
def pytest_configure(config):
    """
    Pytest 配置钩子
    """
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "requires_llm: marks tests that require actual LLM connection"
    )