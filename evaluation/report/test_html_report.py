#!/usr/bin/env python
"""
测试 HTML 报告生成器
==================

生成示例 HTML 报告用于预览效果。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from evaluation.core.result import EvaluationResult, DimensionResult
from evaluation.report.html_generator import HTMLReportGenerator, HTMLReportConfig, generate_html_report


def create_sample_result() -> EvaluationResult:
    """创建示例评测结果"""
    result = EvaluationResult(
        survey_path="outputs/Large_Language_Model_Survey/survey.pdf",
        timestamp="2024-12-20T15:30:00",
        overall_score=85.6
    )
    
    # 引用质量
    result.reference_quality = DimensionResult(
        name="Reference Quality",
        score=0.872,
        weight=0.25,
        metrics={
            "wcr": 0.785,
            "cc": 0.823,
            "bibliographic_integrity": 0.951,
            "citation_faithfulness": 0.928
        },
        details={"total_references": 156, "core_papers_covered": 89}
    )
    
    # 结构完整性
    result.structural_soundness = DimensionResult(
        name="Structural Soundness",
        score=0.915,
        weight=0.20,
        metrics={
            "sc": 0.912,
            "structural_completeness": 0.886,
            "content_structure_fidelity": 0.947
        },
        details={"sections": 8, "subsections": 24}
    )
    
    # 内容质量
    result.content_integrity = DimensionResult(
        name="Content Integrity",
        score=0.828,
        weight=0.25,
        metrics={
            "general_factualness": 0.853,
            "writing_quality": 0.887,
            "scholarly_depth": 0.792,
            "tc": 0.781
        },
        details={"word_count": 15000, "figures": 12, "tables": 5}
    )
    
    # 伦理与完整性
    result.ethics_integrity = DimensionResult(
        name="Ethics & Integrity",
        score=0.794,
        weight=0.15,
        metrics={
            "originality": 0.825,
            "societal_impact": 0.758,
            "fairness": 0.800
        },
        details={}
    )
    
    # 富媒体质量
    result.rich_media_quality = DimensionResult(
        name="Rich Media Quality",
        score=0.726,
        weight=0.15,
        metrics={
            "figure_quality": 0.752,
            "table_quality": 0.789,
            "visual_content_alignment": 0.684,
            "resource_accessibility": 0.680
        },
        details={"figures": 12, "tables": 5}
    )
    
    # 收集所有指标
    result.collect_all_metrics()
    
    # 添加双语建议 (支持 {"en": "...", "zh": "..."} 格式)
    result.recommendations = [
        {
            "en": "Improve visual-content alignment by ensuring all figures and tables are directly referenced and explained in the text.",
            "zh": "改进视觉-内容对齐，确保所有图表都在正文中被直接引用和解释。"
        },
        {
            "en": "Enhance resource accessibility by providing working links to code repositories and datasets mentioned in the survey.",
            "zh": "增强资源可访问性，提供综述中提到的代码仓库和数据集的有效链接。"
        },
        {
            "en": "Expand the discussion on societal impact and ethical considerations of the surveyed technologies.",
            "zh": "扩展对所调研技术的社会影响和伦理考量的讨论。"
        },
        {
            "en": "Consider adding more recent publications to improve temporal coverage of the literature.",
            "zh": "考虑添加更多近期发表的文献，以提高文献的时间覆盖率。"
        },
        {
            "en": "Add more comparative analysis tables to help readers understand the differences between approaches.",
            "zh": "添加更多对比分析表格，帮助读者理解不同方法之间的差异。"
        }
    ]
    
    return result


def main():
    """主函数"""
    print("=" * 60)
    print("HTML 报告生成器测试")
    print("=" * 60)
    
    # 创建示例结果
    result = create_sample_result()
    print(f"\n综合评分: {result.overall_score:.1f}/100")
    
    # 输出目录
    output_dir = Path(__file__).parent / "test_output"
    output_dir.mkdir(exist_ok=True)
    
    # 生成中英文报告
    print(f"\n正在生成报告到: {output_dir}")
    files = generate_html_report(result, output_dir)
    
    print("\n生成的文件:")
    for lang, path in files.items():
        print(f"  - {lang}: {path}")
    
    print("\n" + "=" * 60)
    print("测试完成！请在浏览器中打开生成的 HTML 文件查看效果。")
    print("=" * 60)
    
    # 提示如何保存为图片
    print("\n提示: 要将报告保存为 PNG/JPG 图片，可以：")
    print("  1. 在浏览器中打开 HTML 文件")
    print("  2. 打开浏览器开发者工具 (F12)")
    print("  3. 在控制台中运行: saveAsImage('png') 或 saveAsImage('jpg')")
    print("  4. 或者使用浏览器的截图功能/扩展")


if __name__ == "__main__":
    main()