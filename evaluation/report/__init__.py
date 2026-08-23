"""
报告生成模块
============

生成评测报告，支持多种格式：
- Markdown 详细报告
- JSON 结构化数据
- SVG 可视化图表
- HTML 精美报告（支持中英文，可导出为 PNG/JPG）
"""

from evaluation.report.generator import ReportGenerator
from evaluation.report.enhanced_generator import (
    EnhancedReportGenerator,
    ReportConfig,
    generate_enhanced_report
)
from evaluation.report.html_generator import (
    HTMLReportGenerator,
    HTMLReportConfig,
    generate_html_report
)

__all__ = [
    "ReportGenerator",
    "EnhancedReportGenerator",
    "ReportConfig",
    "generate_enhanced_report",
    "HTMLReportGenerator",
    "HTMLReportConfig",
    "generate_html_report"
]