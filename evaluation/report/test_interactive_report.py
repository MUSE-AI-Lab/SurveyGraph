import sys
from pathlib import Path
import json

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent.parent))

from evaluation.core.result import EvaluationResult, DimensionResult
from evaluation.report.html_generator import generate_html_report

def test_interactive_report():
    # 1. 模拟评测结果
    result = EvaluationResult(
        survey_path="d:/SurveyGraph/paper/main.tex",
        overall_score=88.5,
        timestamp="2025-12-21T18:15:00"
    )
    
    # 模拟引用质量维度，包含决策路径
    result.reference_quality = DimensionResult(
        name="引用质量",
        score=0.92,
        weight=0.25,
        metrics={"wcr": 0.85, "cc": 0.88, "bibliographic_integrity": 0.95, "citation_faithfulness": 0.98},
        details={
            "decision_path": [
                "识别综述中的 45 个引用标记",
                "从 MEKG 中检索对应的 42 篇核心论文",
                "计算加权中心性召回率 (WCR): 0.85",
                "分析社区覆盖率: 发现覆盖了 5 个主要研究社区中的 4 个",
                "验证引用忠实度: 随机抽取 10 处引用，LLM 判定 9 处完全准确"
            ],
            "evidence": "基于 MEKG 2024-12 版数据，对比了 OpenAlex 的引用拓扑结构。"
        }
    )
    
    # 模拟内容质量维度，包含推理过程
    result.content_integrity = DimensionResult(
        name="内容质量",
        score=0.85,
        weight=0.25,
        metrics={"general_factualness": 0.88, "writing_quality": 0.92, "scholarly_depth": 0.82, "tc": 0.78},
        details={
            "reasoning": "LLM 分析认为：该综述在‘方法论’章节表现出色，逻辑严密。但在‘未来挑战’章节深度略显不足，仅列举了已知问题，缺乏前瞻性洞察。时间覆盖率受限于 2023 年后的论文较少。"
        }
    )
    
    # 模拟其他维度
    result.structural_soundness = DimensionResult(name="结构完整性", score=0.90, weight=0.20, metrics={"sc": 0.92})
    result.ethics_integrity = DimensionResult(name="伦理与完整性", score=0.80, weight=0.15, metrics={"originality": 0.85})
    result.rich_media_quality = DimensionResult(name="富媒体质量", score=0.75, weight=0.15, metrics={"figure_quality": 0.70})
    
    result.collect_all_metrics()
    result.recommendations = [
        "增加对 2024 年最新进展的引用以提升时间覆盖率。",
        "在‘未来方向’章节增加关于多模态融合的深度讨论。",
        "优化图 3 的分辨率，目前在缩放时存在模糊。"
    ]

    # 2. 模拟 MEKG 数据
    mekg_data = {
        "papers_count": 120,
        "relations_count": 450,
        "papers": [
            {"id": "P1", "title": "Attention is All You Need", "category": "Architecture"},
            {"id": "P2", "title": "BERT: Pre-training of Deep Bidirectional Transformers", "category": "Language Model"},
            {"id": "P3", "title": "GPT-3: Language Models are Few-Shot Learners", "category": "Language Model"},
            {"id": "P4", "title": "Llama: Open and Efficient Foundation Language Models", "category": "Language Model"}
        ],
        "relations": [
            {"source": "P2", "target": "P1", "type": "cites"},
            {"source": "P3", "target": "P1", "type": "cites"},
            {"source": "P4", "target": "P1", "type": "cites"},
            {"source": "P3", "target": "P2", "type": "extends"}
        ]
    }

    # 3. 生成报告
    output_dir = Path(__file__).parent / "test_output_interactive"
    files = generate_html_report(result, output_dir, mekg_data=mekg_data)
    
    print(f"✅ 交互式报告已生成:")
    for lang, path in files.items():
        print(f"  - {lang}: {path}")

if __name__ == "__main__":
    test_interactive_report()