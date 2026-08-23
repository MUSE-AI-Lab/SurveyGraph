# -*- coding: utf-8 -*-
"""
Dynamic Visual Generator - 动态视觉元素生成器

让LLM自主决定在综述的各个章节中生成什么类型的视觉元素，
包括：表格、流程图、架构图、时间线、文字框等。

主要功能:
1. 分析综述内容，决定需要什么类型的视觉元素
2. 从参考文献中提取和引用相关图片
3. 使用固定模板生成表格和图表（避免编译错误）
4. LLM只负责填充数据，不生成TikZ代码

重要：使用固定模板确保LaTeX编译不会出错
"""

import json
import os
import re
import shutil
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum
from datetime import datetime

import requests

from src.configs.logger import get_logger
from src.configs.constants import OUTPUT_DIR, RESOURCE_DIR, BASE_DIR

logger = get_logger("src.modules.multimodal.DynamicVisualGenerator")


class VisualElementType(Enum):
    """视觉元素类型"""
    REFERENCE_FIGURE = "reference_figure"      # 引用参考文献中的图片
    COMPARISON_TABLE = "comparison_table"      # 对比表格
    SUMMARY_TABLE = "summary_table"            # 总结表格
    TIMELINE = "timeline"                      # 时间线图
    TAXONOMY_TREE = "taxonomy_tree"            # 分类树图
    FLOWCHART = "flowchart"                    # 流程图
    ARCHITECTURE_DIAGRAM = "architecture"      # 架构图
    STATISTICS_CHART = "statistics_chart"      # 统计图表
    CONCEPT_MAP = "concept_map"                # 概念图
    CALLOUT_BOX = "callout_box"                # 信息框/文本框 (Key Insights, Example, Evidence等)
    DATAFLOW = "dataflow"                      # 数据流图
    PIPELINE = "pipeline"                      # 管道/流水线图
    PERFORMANCE_CHART = "performance_chart"    # 性能对比图
    STRUCTURE = "structure"                    # Survey结构图 (使用Forest包，多层级彩色分类树)
    TREE = "tree"                              # 通用树形图
    MINDMAP = "mindmap"                        # 思维导图 (使用mindmap库)
    TINY_TREE = "tiny_tree"                    # 紧凑树形图 (适用于小型层次结构)
    CONCEPTUAL_COMPARISON = "conceptual_comparison" # 概念对比图
    
    # 表格类型
    ICON_DESCRIPTION_TABLE = "icon_description_table"   # 带图标的描述表格
    GROUPED_CATEGORY_TABLE = "grouped_category_table"   # 带彩色分组标题的表格
    TAXONOMY_MATRIX_TABLE = "taxonomy_matrix_table"     # 矩阵式分类表格
    NESTED_MULTIROW_TABLE = "nested_multirow_table"     # 嵌套多行表格
    COLORED_HEADER_TABLE = "colored_header_table"       # 带彩色标题栏的表格
    BENCHMARK_RESULTS_TABLE = "benchmark_results_table" # 基准测试结果表格
    LABELED_BADGE_TABLE = "labeled_badge_table"         # 带彩色标签徽章的表格

    NONE = "none"                                       # 不需要视觉元素


@dataclass
class VisualElementDecision:
    """视觉元素决策结果"""
    element_type: VisualElementType
    target_section: str                        # 目标章节
    section_title: str                         # 章节标题
    description: str                           # 元素描述
    data_requirements: Dict[str, Any]          # 数据需求
    style_preference: str                      # 样式偏好
    reference_images: List[str]                # 相关参考文献图片路径
    priority: int                              # 优先级 (1-10)
    reason: str                                # 决策理由
    latex_code: str = ""                       # 生成的LaTeX代码
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["element_type"] = self.element_type.value
        return d


@dataclass
class ExistingVisualElement:
    """已存在的视觉元素信息（用于避免重复生成）"""
    element_type: str                          # 元素类型（table, tikz, ai_image等）
    title: str                                 # 标题/caption
    description: str                           # 描述
    target_section: str                        # 目标章节
    topics: List[str] = field(default_factory=list)  # 涉及的主题/关键词
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_table_info(cls, table_info: Dict) -> "ExistingVisualElement":
        """从表格信息创建"""
        return cls(
            element_type="table",
            title=table_info.get("caption", table_info.get("title", "")),
            description=table_info.get("description", ""),
            target_section=table_info.get("section", ""),
            topics=table_info.get("topics", [])
        )


@dataclass
class ReferenceImage:
    """参考文献图片信息"""
    image_path: Path
    source_paper: str                          # 来源论文标题
    original_caption: str                      # 原始标题
    page_number: int                           # 页码
    context: str                               # 上下文
    relevance_score: float                     # 相关性评分
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["image_path"] = str(self.image_path)
        return d


class DynamicVisualGenerator:
    """
    动态视觉元素生成器
    
    根据综述内容自动决定并生成多样化的视觉元素
    使用固定模板确保LaTeX编译成功
    """
    
    # 模板目录
    TEMPLATE_DIR = Path(RESOURCE_DIR) / "latex" / "figure_template"
    
    # 视觉元素样式模板
    STYLE_TEMPLATES = {
        "comparison_table": [
            "horizontal_comparison",    # 横向对比
            "vertical_comparison",      # 纵向对比
            "matrix_comparison",        # 矩阵对比
            "feature_checklist",        # 特性清单
        ],
        "summary_table": [
            "categorized_summary",      # 分类总结
            "chronological_summary",    # 时间顺序总结
            "hierarchical_summary",     # 层级总结
        ],
        "timeline": [
            "horizontal_timeline",      # 水平时间线
            "vertical_timeline",        # 垂直时间线
            "milestone_timeline",       # 里程碑时间线
        ],
        "taxonomy_tree": [
            "top_down_tree",            # 自上而下树
            "left_right_tree",          # 左右树
            "radial_tree",              # 放射状树
            "mindmap_style",            # 思维导图风格
        ],
        "flowchart": [
            "linear_flow",              # 线性流程
            "branching_flow",           # 分支流程
            "circular_flow",            # 循环流程
        ],
        "architecture": [
            "layered_architecture",     # 分层架构
            "component_diagram",        # 组件图
            "pipeline_diagram",         # 管道图
        ],
        "callout_box": [
            "key_insights",             # 关键洞察框
            "example",                  # 示例框
            "evidence",                 # 证据/引用框
            "definition",               # 定义框
            "warning",                  # 警告/注意框
            "numbered_list",            # 带编号圆圈的列表框
            "key_questions",            # 关键问题框
            "concept_list",             # 概念列表框（带子项说明）
            "summary",                  # 总结框
            "note",                     # 注释/补充说明框
            "tip",                      # 提示/最佳实践框
        ],
        "conceptual_comparison": [
            "venn_style",               # 韦恩图风格
            "overlap_style",            # 重叠圆圈风格
        ],
        # 新增精美表格样式
        "icon_description_table": ["default"],
        "grouped_category_table": ["default"],
        "taxonomy_matrix_table": ["default"],
        "nested_multirow_table": ["default"],
        "colored_header_table": ["default"],
        "benchmark_results_table": ["default"],
        "labeled_badge_table": ["default"],
    }
    
    # 全局限制配置 - 动态视觉元素配置
    # 要求：1个structure图 + 至少3个其他类型的TikZ图 = 至少4个
    MAX_TOTAL_TIKZ_FIGURES = 6      # 最多生成6个TikZ图
    MAX_TOTAL_TABLES = 0            # 不生成表格（由 LatexListTableBuilder 负责）
    MAX_TOTAL_REFERENCE_FIGURES = 0 # 不引用参考文献图片（由 EnhancedMultimodalRefiner 负责）
    MAX_ELEMENTS_PER_SECTION = 1    # 每个章节最多1个动态视觉元素
    MAX_TOTAL_ELEMENTS = 6          # 总共最多6个动态视觉元素
    MIN_TOTAL_ELEMENTS = 4          # 最少生成4个视觉元素
    
    def __init__(
        self,
        api_url: str = None,
        api_key: str = None,
        model: str = "glm-4.6",
        task_id: str = None
    ):
        """
        初始化动态视觉生成器
        
        Args:
            api_url: LLM API地址
            api_key: API密钥
            model: 模型名称
            task_id: 任务ID
        """
        self.api_url = api_url or os.getenv("AI_IMAGE_API_URL", "")
        self.api_key = api_key or os.getenv("AI_IMAGE_API_KEY", "")
        self.model = model
        self.task_id = task_id
        
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # 设置路径
        if task_id:
            self.output_dir = Path(OUTPUT_DIR) / task_id
            self.figs_dir = self.output_dir / "latex" / "figs"
            self.extracted_images_dir = self.output_dir / "extracted_images"
            self.mineru_output_dir = self.output_dir / "mineru_output"
        else:
            self.output_dir = Path(OUTPUT_DIR) / "temp"
            self.figs_dir = self.output_dir / "figs"
            self.extracted_images_dir = self.output_dir / "extracted_images"
            self.mineru_output_dir = self.output_dir / "mineru_output"
        
        self.figs_dir.mkdir(parents=True, exist_ok=True)
        
        # 已生成的视觉元素计数
        self.element_count = {t: 0 for t in VisualElementType}
        
        # 全局计数器
        self.total_tikz_count = 0
        self.total_table_count = 0
        self.total_reference_fig_count = 0
        
        # 每个章节的视觉元素限制
        self.max_elements_per_section = self.MAX_ELEMENTS_PER_SECTION
        self.section_element_count = {}
        
        # 收集的参考文献图片
        self.reference_images: List[ReferenceImage] = []
        
        # 已存在的视觉元素（用于避免重复）
        self.existing_visual_elements: List[ExistingVisualElement] = []
        
        # 章节对应的方法列表 (section_no -> [method_names])
        self.section_methods: Dict[str, List[str]] = {}
        
        # 加载模板
        self._load_templates()
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名，移除或替换非法字符 (与 MEKG pipeline 保持一致)"""
        import re
        return re.sub(r'[\\/:*?"<>|]', '_', filename)

    def load_paper_methods(self):
        """
        从 papers 目录加载论文方法名，并映射到章节
        
        策略优先级：
        1. 读取 papers/*.json 中的 mount_outline 字段（最准确，由 SurveyX 生成）
        2. 读取 outline.json 中的 paper_ids 字段（MEKG 生成，可能为空）
        3. 读取 outlines.json 并使用模糊匹配（最后的兜底方案）
        """
        if not self.output_dir:
            return
            
        papers_dir = self.output_dir / "papers"
        if not papers_dir.exists():
            return
            
        # 1. 尝试从 papers/*.json 中的 mount_outline 加载
        loaded_from_mount = self._load_methods_from_mount_outline(papers_dir)
        if loaded_from_mount:
            logger.info(f"Loaded methods from mount_outline for {len(self.section_methods)} sections")
            return

        # 2. 尝试读取 outline.json (MEKG格式，包含 paper_ids)
        outline_path = self.output_dir / "outline.json"
        loaded_from_outline = False
        
        if outline_path.exists():
            try:
                outline_data = json.loads(outline_path.read_text(encoding="utf-8"))
                # 检查是否真的加载到了方法（即 outline.json 中是否有 paper_ids）
                if self._process_mekg_outline(outline_data, papers_dir):
                    logger.info(f"Loaded methods from outline.json for {len(self.section_methods)} sections")
                    loaded_from_outline = True
                else:
                    logger.warning("outline.json found but contained no paper_ids")
            except Exception as e:
                logger.warning(f"Failed to process outline.json: {e}")
        
        # 3. 回退方案：读取 outlines.json 并使用模糊匹配
        if not loaded_from_outline:
            logger.info("Falling back to fuzzy matching using outlines.json")
            self._load_methods_fallback(papers_dir)

    def _load_methods_from_mount_outline(self, papers_dir: Path) -> bool:
        """
        从 papers/*.json 的 mount_outline 字段加载方法映射
        
        包含去重逻辑：
        1. 同一章节内不重复
        2. 父子章节去重：如果论文同时挂载在父章节和子章节，只保留子章节（更具体）
        """
        methods_loaded = False
        
        # 临时存储：method_unique_id -> {sec_num, ...}
        # 用于处理父子章节去重
        method_mounts = {}
        
        for paper_file in papers_dir.glob("*.json"):
            try:
                content = paper_file.read_text(encoding="utf-8")
                paper = json.loads(content)
                
                mount_outline = paper.get("mount_outline", [])
                if not mount_outline:
                    continue
                
                # 提取方法名
                method_name = ""
                attri = paper.get("attri", {})
                if isinstance(attri, dict):
                    method_info = attri.get("method", {})
                    if isinstance(method_info, dict):
                        method_name = method_info.get("method name", "")
                
                if not method_name:
                    title = paper.get("title", "")
                    if len(title) < 50:
                        method_name = title
                
                if not method_name:
                    continue
                    
                # 格式化方法名
                bib_name = paper.get("bib_name", "")
                if len(method_name) > 30:
                    method_name = method_name[:27] + "..."
                if bib_name:
                    method_name += f"~\\cite{{{bib_name}}}"
                
                # 收集该方法的所有挂载点
                unique_id = f"{method_name}_{bib_name}"
                if unique_id not in method_mounts:
                    method_mounts[unique_id] = {
                        "name": method_name,
                        "sections": set()
                    }
                
                for mount in mount_outline:
                    sec_num = mount.get("section number", "")
                    if sec_num:
                        method_mounts[unique_id]["sections"].add(sec_num)
                            
            except Exception as e:
                logger.warning(f"Failed to process paper {paper_file.name}: {e}")
        
        # 处理去重并填充 self.section_methods
        for m_data in method_mounts.values():
            method_name = m_data["name"]
            sections = sorted(list(m_data["sections"]))
            
            # 过滤父章节：如果存在子章节，移除父章节
            # 例如：如果同时存在 "2" 和 "2.1"，移除 "2"
            final_sections = []
            for s1 in sections:
                is_parent = False
                for s2 in sections:
                    if s1 != s2 and s2.startswith(s1 + "."):
                        is_parent = True
                        break
                if not is_parent:
                    final_sections.append(s1)
            
            # 添加到 section_methods
            for sec_num in final_sections:
                if sec_num not in self.section_methods:
                    self.section_methods[sec_num] = []
                self.section_methods[sec_num].append(method_name)
                methods_loaded = True
                
        return methods_loaded

    def _process_mekg_outline(self, outline_data: Dict, papers_dir: Path) -> bool:
        """
        处理 MEKG 格式的大纲，直接使用 paper_ids
        
        Returns:
            bool: 是否成功加载了至少一个章节的方法
        """
        methods_loaded = False
        
        def get_method_name_from_paper(paper_id: str) -> str:
            # 清理文件名
            safe_id = self._sanitize_filename(paper_id)
            paper_path = papers_dir / f"{safe_id}.json"
            
            if not paper_path.exists():
                return ""
                
            try:
                content = paper_path.read_text(encoding="utf-8")
                paper = json.loads(content)
                
                # 提取方法名
                method_name = ""
                attri = paper.get("attri", {})
                if isinstance(attri, dict):
                    method_info = attri.get("method", {})
                    if isinstance(method_info, dict):
                        method_name = method_info.get("method name", "")
                
                if not method_name:
                    # 尝试从标题提取（如果标题很短）
                    title = paper.get("title", "")
                    if len(title) < 50:
                        method_name = title
                
                # 格式化
                if method_name:
                    bib_name = paper.get("bib_name", "")
                    if len(method_name) > 30:
                        method_name = method_name[:27] + "..."
                    if bib_name:
                        method_name += f"~\\cite{{{bib_name}}}"
                    return method_name
            except:
                pass
            return ""

        def process_sections(sections):
            nonlocal methods_loaded
            for section in sections:
                sec_num = section.get("number", "")
                paper_ids = section.get("paper_ids", [])
                
                if sec_num and paper_ids:
                    methods = []
                    for pid in paper_ids:
                        m_name = get_method_name_from_paper(pid)
                        if m_name:
                            methods.append(m_name)
                    
                    if methods:
                        self.section_methods[sec_num] = list(set(methods))
                        methods_loaded = True
                
                # 递归处理子章节
                if "subsections" in section:
                    process_sections(section["subsections"])
        
        process_sections(outline_data.get("sections", []))
        return methods_loaded

    def _load_methods_fallback(self, papers_dir: Path):
        """回退方案：读取所有论文并模糊匹配"""
        # 1. 读取所有论文的方法名和分类
        paper_methods = []
        for paper_file in papers_dir.glob("*.json"):
            try:
                content = paper_file.read_text(encoding="utf-8")
                paper = json.loads(content)
                
                # 提取方法名
                method_name = ""
                attri = paper.get("attri", {})
                if isinstance(attri, dict):
                    method_info = attri.get("method", {})
                    if isinstance(method_info, dict):
                        method_name = method_info.get("method name", "")
                
                if not method_name:
                    title = paper.get("title", "")
                    if len(title) < 50:
                        method_name = title
                
                if method_name:
                    paper_methods.append({
                        "method_name": method_name,
                        "category": paper.get("category", "").lower(),
                        "subcategory": paper.get("subcategory", "").lower(),
                        "bib_name": paper.get("bib_name", "")
                    })
            except Exception as e:
                logger.warning(f"Failed to load paper {paper_file.name}: {e}")
        
        # 2. 读取大纲，建立章节映射
        outlines_path = self.output_dir / "outlines.json"
        if not outlines_path.exists():
            return
            
        try:
            outlines = json.loads(outlines_path.read_text(encoding="utf-8"))
            
            # 递归遍历大纲，匹配方法
            def process_sections(sections, parent_num=""):
                for i, section in enumerate(sections, 1):
                    current_num = f"{parent_num}.{i}" if parent_num else str(i)
                    title = section.get("title", "").lower()
                    
                    # 查找匹配的方法
                    matched_methods = []
                    for pm in paper_methods:
                        # 简单的匹配逻辑：如果分类或子分类包含在章节标题中
                        if (pm["category"] and pm["category"] in title) or \
                           (pm["subcategory"] and pm["subcategory"] in title):
                            # 格式化为 "MethodName [Citation]"
                            display_name = pm["method_name"]
                            if len(display_name) > 30: # 截断过长的方法名
                                display_name = display_name[:27] + "..."
                                
                            if pm["bib_name"]:
                                display_name += f"~\\cite{{{pm['bib_name']}}}"
                            
                            matched_methods.append(display_name)
                    
                    if matched_methods:
                        self.section_methods[current_num] = list(set(matched_methods)) # 去重
                    
                    # 递归处理子章节
                    if "subsections" in section:
                        process_sections(section["subsections"], current_num)
            
            process_sections(outlines.get("sections", []))
            logger.info(f"Loaded methods (fallback) for {len(self.section_methods)} sections")
            
        except Exception as e:
            logger.warning(f"Failed to process outlines: {e}")

    def _load_templates(self):
        """动态加载所有LaTeX模板
        
        自动扫描模板目录中所有以 '_template.tex' 结尾的文件，
        并根据文件名推断模板名称（去掉 '_template.tex' 后缀）。
        
        例如：
        - flowchart_template.tex -> templates["flowchart"]
        - comparison_table_template.tex -> templates["comparison_table"]
        
        重要：会自动去除模板中的注释和 \\begin{figure} 之前的内容，
        避免占位符被错误替换到注释中。
        """
        self.templates = {}
        
        # 检查模板目录是否存在
        if not self.TEMPLATE_DIR.exists():
            logger.warning(f"Template directory not found: {self.TEMPLATE_DIR}")
            return
        
        # 动态扫描目录中所有以 '_template.tex' 结尾的文件
        template_suffix = "_template.tex"
        template_files = list(self.TEMPLATE_DIR.glob(f"*{template_suffix}"))
        
        if not template_files:
            logger.warning(f"No template files found in {self.TEMPLATE_DIR}")
            return
        
        for template_path in template_files:
            # 从文件名推断模板名称（去掉 '_template.tex' 后缀）
            filename = template_path.name
            template_name = filename[:-len(template_suffix)]  # 去掉后缀
            
            try:
                content = template_path.read_text(encoding="utf-8")
                
                # 清理模板内容
                content = self._clean_template_content(content)
                
                self.templates[template_name] = content
                logger.debug(f"Loaded template: {template_name}")
            except Exception as e:
                logger.warning(f"Failed to load template {template_name}: {e}")
                self.templates[template_name] = None
        
        logger.info(f"Dynamically loaded {len(self.templates)} templates: {list(self.templates.keys())}")
    
    def _clean_template_content(self, content: str) -> str:
        """清理模板内容，移除注释和不必要的部分
        
        处理逻辑：
        1. 去除 \\begin{figure} 或 \\begin{figure*} 之前的所有内容（包括注释）
        2. 去除 \\end{figure} 或 \\end{figure*} 之后的所有内容
        3. 移除模板内部的纯注释行（以 % 开头且不包含占位符的行）
        
        Args:
            content: 原始模板内容
            
        Returns:
            清理后的模板内容
        """
        # 1. 找到 \begin{figure} 或 \begin{figure*} 的位置
        begin_markers = ["\\begin{figure*}", "\\begin{figure}"]
        begin_pos = -1
        used_begin_marker = None
        
        for marker in begin_markers:
            pos = content.find(marker)
            if pos != -1 and (begin_pos == -1 or pos < begin_pos):
                begin_pos = pos
                used_begin_marker = marker
        
        # 如果找到了 \begin{figure}，去除之前的内容
        if begin_pos != -1:
            content = content[begin_pos:]
        
        # 2. 找到对应的 \end{figure} 或 \end{figure*} 的位置
        if used_begin_marker == "\\begin{figure*}":
            end_marker = "\\end{figure*}"
        else:
            end_marker = "\\end{figure}"
        
        end_pos = content.find(end_marker)
        if end_pos != -1:
            content = content[:end_pos + len(end_marker)]
        
        # 3. 移除模板内部的纯注释行（不包含占位符的注释）
        # 保留包含占位符 <...> 的行，因为这些可能是有意义的
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            stripped = line.strip()
            # 如果是纯注释行（以 % 开头）且不包含占位符
            if stripped.startswith('%') and '<' not in stripped:
                # 跳过这行注释
                continue
            cleaned_lines.append(line)
        
        content = '\n'.join(cleaned_lines)
        
        return content
    
    def _call_llm(self, prompt: str, temperature: float = 0.7) -> str:
        """调用LLM"""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=120
            )
            
            if response.status_code != 200:
                logger.error(f"LLM API error: {response.status_code}")
                return ""
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"LLM call error: {e}")
            return ""
    
    def collect_reference_images(self) -> List[ReferenceImage]:
        """
        收集参考文献中的所有图片
        
        从MinerU解析输出中收集图片及其上下文信息
        """
        images = []
        
        # 从MinerU输出目录收集
        if self.mineru_output_dir.exists():
            for paper_dir in self.mineru_output_dir.iterdir():
                if paper_dir.is_dir():
                    images.extend(self._collect_images_from_paper(paper_dir))
        
        # 从extracted_images目录收集
        if self.extracted_images_dir.exists():
            for img_path in self.extracted_images_dir.glob("**/*"):
                if img_path.suffix.lower() in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
                    images.append(ReferenceImage(
                        image_path=img_path,
                        source_paper=img_path.parent.name,
                        original_caption="",
                        page_number=0,
                        context=self._get_image_context(img_path),
                        relevance_score=0.5
                    ))
        
        self.reference_images = images
        logger.info(f"Collected {len(images)} reference images")
        return images
    
    def _collect_images_from_paper(self, paper_dir: Path) -> List[ReferenceImage]:
        """从单篇论文目录收集图片"""
        images = []
        
        # 查找图片目录
        for images_dir in paper_dir.glob("**/images"):
            if images_dir.is_dir():
                # 尝试加载对应的markdown文件获取上下文
                md_files = list(paper_dir.glob("**/*.md"))
                md_content = ""
                if md_files:
                    try:
                        md_content = md_files[0].read_text(encoding="utf-8")
                    except:
                        pass
                
                for img_path in images_dir.glob("*"):
                    if img_path.suffix.lower() in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
                        # 从markdown中提取图片上下文
                        context = self._extract_image_context_from_md(
                            img_path.name, md_content
                        )
                        
                        images.append(ReferenceImage(
                            image_path=img_path,
                            source_paper=paper_dir.name,
                            original_caption=self._extract_caption(img_path.name, md_content),
                            page_number=0,
                            context=context,
                            relevance_score=0.5
                        ))
        
        return images
    
    def _extract_image_context_from_md(self, image_name: str, md_content: str) -> str:
        """从markdown内容中提取图片上下文"""
        if not md_content or image_name not in md_content:
            return ""
        
        # 查找图片引用位置
        idx = md_content.find(image_name)
        if idx == -1:
            return ""
        
        # 提取前后各300个字符作为上下文
        start = max(0, idx - 300)
        end = min(len(md_content), idx + 300)
        return md_content[start:end]
    
    def _extract_caption(self, image_name: str, md_content: str) -> str:
        """从markdown中提取图片标题"""
        if not md_content:
            return ""
        
        # 尝试匹配 ![caption](image_name) 格式
        pattern = rf'!\[([^\]]*)\]\([^)]*{re.escape(image_name)}[^)]*\)'
        match = re.search(pattern, md_content)
        if match:
            return match.group(1)
        
        return ""
    
    def _get_image_context(self, img_path: Path) -> str:
        """获取图片上下文"""
        # 尝试从同目录的markdown文件获取上下文
        md_files = list(img_path.parent.glob("*.md"))
        if not md_files:
            md_files = list(img_path.parent.parent.glob("*.md"))
        
        if md_files:
            try:
                md_content = md_files[0].read_text(encoding="utf-8")
                return self._extract_image_context_from_md(img_path.name, md_content)
            except:
                pass
        
        return ""
    
    def analyze_section_for_visuals(
        self,
        section_content: str,
        section_title: str,
        section_no: str,
        survey_topic: str,
        existing_visuals: List[str] = None
    ) -> List[VisualElementDecision]:
        """
        分析章节内容，决定需要什么视觉元素
        
        Args:
            section_content: 章节内容
            section_title: 章节标题
            section_no: 章节编号
            survey_topic: 综述主题
            existing_visuals: 已有的视觉元素类型
            
        Returns:
            视觉元素决策列表
        """
        # 构建分析prompt
        prompt = self._build_analysis_prompt(
            section_content,
            section_title,
            section_no,
            survey_topic,
            existing_visuals or []
        )
        
        # 调用LLM进行分析
        response = self._call_llm(prompt, temperature=0.7)
        
        if not response:
            logger.warning(f"Failed to analyze section {section_no}")
            return []
        
        # 解析决策结果
        decisions = self._parse_analysis_response(response, section_no, section_title)
        
        return decisions
    
    def _build_analysis_prompt(
        self,
        section_content: str,
        section_title: str,
        section_no: str,
        survey_topic: str,
        existing_visuals: List[str]
    ) -> str:
        """构建分析prompt"""
        
        # 获取可用的参考文献图片信息
        ref_images_info = self._format_reference_images_info()
        
        prompt = f"""You are an academic survey writing expert, specializing in designing visual elements for survey papers.

## Task
Analyze the following survey section content and decide what type of visual elements should be added to enhance readability and academic value.
**IMPORTANT: All output content (descriptions, captions, reasons, table headers, etc.) MUST be in ENGLISH.**

## Survey Topic
{survey_topic}

## Current Section
- Section Number: {section_no}
- Section Title: {section_title}

## Section Content
{section_content[:3000]}...

## Existing Visual Element Types
{', '.join(existing_visuals) if existing_visuals else 'None'}

## Available Reference Images
{ref_images_info}

## Optional Visual Element Types

1. **reference_figure** - Cite an image from references
   - Scenario: When references contain high-quality architecture diagrams, experimental results, etc.
   - Requires: Image path, new caption (in English), citation note

2. **comparison_table** - Comparison Table
   - Scenario: Comparing features of multiple methods, models, or technologies
   - **IMPORTANT**: Provide actual data for the table, not just column/row names

3. **summary_table** - Summary Table
   - Scenario: Summarizing key information of a class of methods
   - **IMPORTANT**: Provide actual data for the table, not just column/row names

4. **timeline** - Timeline Chart
   - Scenario: Showing technology development history, key milestones
   - **IMPORTANT**: Provide specific years and events (max 8 items)

5. **taxonomy_tree** - Taxonomy Tree
   - Scenario: Showing method classification, technology hierarchy
   - **IMPORTANT**: Provide tree structure with max 3 levels, max 4 children per node

6. **flowchart** - Flowchart
   - Scenario: Showing method flow, workflow
   - **IMPORTANT**: Provide steps with max 6 nodes

7. **architecture** - Architecture Diagram
- Scenario: Showing system architecture, model structure
- **IMPORTANT**: Provide layers with max 4 layers, max 4 components per layer

8. **conceptual_comparison** - Conceptual Comparison Diagram
- Scenario: Comparing overlapping concepts, showing relationships between 3-4 key entities (like Venn diagram)
- **IMPORTANT**: Provide 4 main entities (1 center, 3 surrounding) and their relationships

9. **callout_box** - Information Box / Text Box
- Scenario: Highlighting key insights, examples, evidence, or definitions
- Subtypes: key_insights, example, evidence, definition, warning
- **IMPORTANT**: Provide actual content items for the box

10. **none** - No visual element needed
- Scenario: Section content is not suitable for visual elements

## Decision Principles

1. **Diversity**: Try to choose types different from existing visual elements
2. **Relevance**: Visual elements must be highly relevant to the section content
3. **Academic Value**: Prioritize elements that enhance academic expression
4. **Moderation**: Suggest at most 1-2 visual elements per section
5. **Citation Priority**: If there are suitable images in references, prioritize citing them
6. **Language**: All generated text MUST be in ENGLISH.
7. **Simplicity**: Keep visual elements simple to avoid LaTeX compilation errors

## Output Format

Please output your decision in JSON format (can be one or more):
```json
[
    {{
        "element_type": "comparison_table",
        "description": "Comparison of key features of different LLM models",
        "data_requirements": {{
            "caption": "Comparison of Large Language Models",
            "headers": ["Model", "Parameters", "Training Data", "Key Features"],
            "rows": [
                ["GPT-4", "1.76T", "Web + Books", "Multimodal, RLHF"],
                ["Claude-3", "Unknown", "Web + Books", "Constitutional AI"],
                ["LLaMA-2", "70B", "Web", "Open Source"],
                ["PaLM-2", "340B", "Web + Code", "Multilingual"]
            ]
        }},
        "priority": 8,
        "reason": "The section discusses the comparison of multiple models, a table can clearly show the differences"
    }},
    {{
        "element_type": "timeline",
        "description": "Development history of LLMs",
        "data_requirements": {{
            "caption": "Timeline of Large Language Model Development",
            "items": [
                {{"year": "2017", "event": "Transformer architecture introduced"}},
                {{"year": "2018", "event": "BERT released by Google"}},
                {{"year": "2019", "event": "GPT-2 released by OpenAI"}},
                {{"year": "2020", "event": "GPT-3 with 175B parameters"}},
                {{"year": "2022", "event": "ChatGPT launched"}},
                {{"year": "2023", "event": "GPT-4 and Claude released"}}
            ]
        }},
        "priority": 7,
        "reason": "The section mentions the historical development of LLMs"
    }},
    {{
        "element_type": "flowchart",
        "description": "LLM training pipeline",
        "data_requirements": {{
            "caption": "Training Pipeline of Large Language Models",
            "nodes": [
                {{"id": "1", "type": "start", "text": "Data Collection"}},
                {{"id": "2", "type": "process", "text": "Preprocessing"}},
                {{"id": "3", "type": "process", "text": "Pre-training"}},
                {{"id": "4", "type": "process", "text": "Fine-tuning"}},
                {{"id": "5", "type": "end", "text": "Deployment"}}
            ],
            "edges": [
                {{"from": "1", "to": "2"}},
                {{"from": "2", "to": "3"}},
                {{"from": "3", "to": "4"}},
                {{"from": "4", "to": "5"}}
            ]
        }},
        "priority": 6,
        "reason": "The section describes the training process"
    }},
    {{
        "element_type": "architecture",
        "description": "Transformer architecture layers",
        "data_requirements": {{
            "caption": "Transformer Model Architecture",
            "layers": [
                {{"name": "Output Layer", "components": ["Softmax", "Linear"], "color": "red!20"}},
                {{"name": "Decoder Stack", "components": ["Self-Attention", "Cross-Attention", "FFN"], "color": "blue!20"}},
                {{"name": "Encoder Stack", "components": ["Self-Attention", "FFN"], "color": "green!20"}},
                {{"name": "Input Layer", "components": ["Embedding", "Positional Encoding"], "color": "yellow!20"}}
            ]
        }},
        "priority": 7,
        "reason": "The section discusses model architecture"
    }},
    {{
        "element_type": "taxonomy_tree",
        "description": "Classification of LLM techniques",
        "data_requirements": {{
            "caption": "Taxonomy of Large Language Model Techniques",
            "root": "LLM Techniques",
            "children": [
                {{
                    "name": "Pre-training",
                    "children": ["Masked LM", "Causal LM", "Seq2Seq"]
                }},
                {{
                    "name": "Fine-tuning",
                    "children": ["Full FT", "LoRA", "Prompt Tuning"]
                }},
                {{
                    "name": "Inference",
                    "children": ["Greedy", "Beam Search", "Sampling"]
                }}
            ]
        }},
        "priority": 7,
        "reason": "The section categorizes different techniques"
    }},
    {{
        "element_type": "conceptual_comparison",
        "description": "Comparison of Agent Memory with other concepts",
        "data_requirements": {{
            "caption": "Conceptual Comparison of Agent Memory",
            "center_label": "Agent Memory",
            "left_label": "RAG",
            "right_label": "LLM Memory",
            "bottom_label": "Context Eng.",
            "center_left_text": "Graph Retrieval",
            "center_right_text": "KV Reuse",
            "center_bottom_text": "Prompting",
            "annotations": {{
                "center": {{
                    "title": "Agent Memory",
                    "items": ["Self-evolving", "Persistent state", "Integrates facts & exp"]
                }},
                "left": {{
                    "title": "RAG",
                    "items": ["Static knowledge", "Modular retrieval", "Graph RAG"]
                }},
                "right": {{
                    "title": "LLM Memory",
                    "items": ["KV compression", "Long context", "Attention mgmt"]
                }},
                "bottom": {{
                    "title": "Context Eng.",
                    "items": ["Tool selection", "Few-shot prompting", "Transient resource"]
                }}
            }}
        }},
        "priority": 8,
        "reason": "Visualizes the relationship between the core concept and related fields"
    }},
    {{
        "element_type": "callout_box",
        "description": "Key insights about LLM capabilities",
        "data_requirements": {{
            "box_type": "key_insights",
            "title": "Key Insights",
            "items": [
                "LLMs demonstrate emergent abilities at scale",
                "In-context learning enables few-shot adaptation",
                "Chain-of-thought prompting improves reasoning"
            ]
        }},
        "priority": 6,
        "reason": "The section contains important findings that should be highlighted"
    }},
    {{
        "element_type": "callout_box",
        "description": "Three major types of memory",
        "data_requirements": {{
            "box_type": "numbered_list",
            "title": "Three Types of Experiential Memory",
            "items": [
                "Case-based Memory stores minimally processed records of historical episodes",
                "Strategy-based Memory distills transferable reasoning patterns and workflows",
                "Skill-based Memory encapsulates executable procedural capacities"
            ]
        }},
        "priority": 7,
        "reason": "The section categorizes memory types that should be clearly listed"
    }},
    {{
        "element_type": "callout_box",
        "description": "Key research questions",
        "data_requirements": {{
            "box_type": "key_questions",
            "title": "Key Questions",
            "items": [
                "How is agent memory defined and how does it relate to RAG?",
                "What architectural forms can agent memory take?",
                "Why is agent memory needed and what purposes does it serve?",
                "How does agent memory operate, adapt, and evolve over time?"
            ]
        }},
        "priority": 7,
        "reason": "The section poses important research questions that should be highlighted"
    }},
    {{
        "element_type": "callout_box",
        "description": "Definition of a key concept",
        "data_requirements": {{
            "box_type": "definition",
            "title": "Definition of Token-level Memory",
            "term": "Token-level Memory",
            "definition": "Memory organized as explicit and discrete units that can be individually accessed, modified, and reconstructed. These units remain externally visible and can be stored in a structured form over time."
        }},
        "priority": 6,
        "reason": "The section introduces a key concept that needs formal definition"
    }},
    {{
        "element_type": "callout_box",
        "description": "Concept list with explanations",
        "data_requirements": {{
            "box_type": "concept_list",
            "title": "Three Major Memory Forms",
            "concepts": [
                {{
                    "name": "Token-level Memory",
                    "section_ref": "Section 3.1",
                    "description": "Memory organized as explicit and discrete units that can be individually accessed."
                }},
                {{
                    "name": "Parametric Memory",
                    "section_ref": "Section 3.2",
                    "description": "Memory stored within the model parameters, accessed implicitly during forward computation."
                }},
                {{
                    "name": "Latent Memory",
                    "section_ref": "Section 3.3",
                    "description": "Memory represented in the model's internal hidden states or evolving latent structures."
                }}
            ]
        }},
        "priority": 7,
        "reason": "The section presents multiple related concepts that need structured presentation"
    }}
]
```

If no visual element is needed, output:
```json
[
    {{
        "element_type": "none",
        "description": "",
        "data_requirements": {{}},
        "priority": 0,
        "reason": "This section is mainly textual description, not suitable for visual elements"
    }}
]
```

Please output ONLY JSON, no other content.
"""
        return prompt
    
    def _format_reference_images_info(self) -> str:
        """格式化参考文献图片信息"""
        if not self.reference_images:
            return "No reference images available"
        
        info_lines = []
        for i, img in enumerate(self.reference_images[:20]):  # 最多显示20张
            info_lines.append(
                f"{i+1}. Path: {img.image_path}\n"
                f"   Source: {img.source_paper}\n"
                f"   Caption: {img.original_caption or 'None'}\n"
                f"   Context: {img.context[:100]}..." if img.context else ""
            )
        
        return "\n".join(info_lines)
    
    def _extract_and_parse_json(self, response: str) -> Any:
        """提取并解析JSON，支持从Markdown代码块中提取"""
        import re
        
        # 1. 尝试提取 Markdown 代码块
        json_str = response
        if "```json" in response:
            pattern = r"```json\s*(.*?)\s*```"
            match = re.search(pattern, response, re.DOTALL)
            if match:
                json_str = match.group(1)
        elif "```" in response:
            pattern = r"```\s*(.*?)\s*```"
            match = re.search(pattern, response, re.DOTALL)
            if match:
                json_str = match.group(1)
        
        # 2. 清理可能的注释和非法字符
        json_str = json_str.strip()
        
        # 3. 尝试解析
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # 4. 如果失败，尝试更激进的提取（查找最外层的 {} 或 []）
            try:
                # 查找第一个 { 或 [
                start_idx = -1
                for i, char in enumerate(json_str):
                    if char in ['{', '[']:
                        start_idx = i
                        break
                
                if start_idx != -1:
                    # 查找最后一个 } 或 ]
                    end_idx = -1
                    for i in range(len(json_str) - 1, -1, -1):
                        if json_str[i] in ['}', ']']:
                            end_idx = i
                            break
                    
                    if end_idx != -1 and end_idx > start_idx:
                        potential_json = json_str[start_idx:end_idx+1]
                        return json.loads(potential_json)
            except:
                pass
            
            # 5. 如果还是失败，尝试修复常见的未转义引号问题（简单尝试）
            try:
                # 这是一个非常简单的修复，可能不完美
                # 替换未转义的换行符
                fixed_str = json_str.replace('\n', '\\n')
                return json.loads(fixed_str)
            except:
                pass
                
            raise

    def _parse_analysis_response(
        self,
        response: str,
        section_no: str,
        section_title: str
    ) -> List[VisualElementDecision]:
        """解析LLM分析响应"""
        decisions = []
        
        try:
            data_list = self._extract_and_parse_json(response)
            
            if not isinstance(data_list, list):
                data_list = [data_list]
            
            for data in data_list:
                element_type_str = data.get("element_type", "none")
                try:
                    element_type = VisualElementType(element_type_str)
                except ValueError:
                    element_type = VisualElementType.NONE
                
                decision = VisualElementDecision(
                    element_type=element_type,
                    target_section=section_no,
                    section_title=section_title,
                    description=data.get("description", ""),
                    data_requirements=data.get("data_requirements", {}),
                    style_preference=data.get("style_preference", ""),
                    reference_images=data.get("reference_images", []),
                    priority=data.get("priority", 5),
                    reason=data.get("reason", "")
                )
                decisions.append(decision)
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.debug(f"Response: {response[:500]}")
        except Exception as e:
            logger.error(f"Parse error: {e}")
        
        return decisions
    
    def _is_tikz_type(self, element_type: VisualElementType) -> bool:
        """判断是否是TikZ类型的图"""
        return element_type in [
            VisualElementType.TIMELINE,
            VisualElementType.TAXONOMY_TREE,
            VisualElementType.FLOWCHART,
            VisualElementType.ARCHITECTURE_DIAGRAM,
            VisualElementType.CONCEPT_MAP,
            VisualElementType.STATISTICS_CHART,
            VisualElementType.DATAFLOW,
            VisualElementType.PIPELINE,
            VisualElementType.PERFORMANCE_CHART,
            VisualElementType.STRUCTURE,
            VisualElementType.TREE,
            VisualElementType.MINDMAP,
            VisualElementType.TINY_TREE,
            VisualElementType.CONCEPTUAL_COMPARISON
        ]
    
    def _is_table_type(self, element_type: VisualElementType) -> bool:
        """判断是否是表格类型"""
        return element_type in [
            VisualElementType.COMPARISON_TABLE,
            VisualElementType.SUMMARY_TABLE,
            # 新增精美表格类型
            VisualElementType.ICON_DESCRIPTION_TABLE,
            VisualElementType.GROUPED_CATEGORY_TABLE,
            VisualElementType.TAXONOMY_MATRIX_TABLE,
            VisualElementType.NESTED_MULTIROW_TABLE,
            VisualElementType.COLORED_HEADER_TABLE,
            VisualElementType.BENCHMARK_RESULTS_TABLE,
            VisualElementType.LABELED_BADGE_TABLE,
        ]
    
    def _can_generate_element(self, element_type: VisualElementType, section_no: str) -> bool:
        """
        检查是否可以生成该类型的元素（基于全局限制）
        
        Args:
            element_type: 元素类型
            section_no: 章节编号
            
        Returns:
            是否可以生成
        """
        # 检查章节限制
        section_count = self.section_element_count.get(section_no, 0)
        if section_count >= self.max_elements_per_section:
            logger.info(f"Section {section_no} already has {section_count} elements, skipping")
            return False
        
        # 检查全局限制
        if self._is_tikz_type(element_type):
            if self.total_tikz_count >= self.MAX_TOTAL_TIKZ_FIGURES:
                logger.info(f"Reached max TikZ figures limit ({self.MAX_TOTAL_TIKZ_FIGURES}), skipping {element_type.value}")
                return False
        elif self._is_table_type(element_type):
            if self.total_table_count >= self.MAX_TOTAL_TABLES:
                logger.info(f"Reached max tables limit ({self.MAX_TOTAL_TABLES}), skipping {element_type.value}")
                return False
        elif element_type == VisualElementType.REFERENCE_FIGURE:
            if self.total_reference_fig_count >= self.MAX_TOTAL_REFERENCE_FIGURES:
                logger.info(f"Reached max reference figures limit ({self.MAX_TOTAL_REFERENCE_FIGURES}), skipping")
                return False
        
        return True
    
    def _update_counters(self, element_type: VisualElementType, section_no: str):
        """更新计数器"""
        # 更新章节计数
        self.section_element_count[section_no] = self.section_element_count.get(section_no, 0) + 1
        
        # 更新全局计数
        if self._is_tikz_type(element_type):
            self.total_tikz_count += 1
        elif self._is_table_type(element_type):
            self.total_table_count += 1
        elif element_type == VisualElementType.REFERENCE_FIGURE:
            self.total_reference_fig_count += 1
        
        # 更新类型计数
        self.element_count[element_type] += 1

    def generate_visual_element(
        self,
        decision: VisualElementDecision,
        section_content: str
    ) -> VisualElementDecision:
        """
        根据决策生成视觉元素
        
        Args:
            decision: 视觉元素决策
            section_content: 章节内容
            
        Returns:
            更新后的决策（包含生成的LaTeX代码）
        """
        if decision.element_type == VisualElementType.NONE:
            return decision
        
        # 检查是否可以生成
        if not self._can_generate_element(decision.element_type, decision.target_section):
            logger.info(f"Skipping {decision.element_type.value} for section {decision.target_section} due to limits")
            return decision
        
        try:
            result = decision
            if decision.element_type == VisualElementType.REFERENCE_FIGURE:
                result = self._generate_reference_figure(decision)
            elif decision.element_type == VisualElementType.COMPARISON_TABLE:
                result = self._generate_comparison_table_from_template(decision)
            elif decision.element_type == VisualElementType.SUMMARY_TABLE:
                result = self._generate_summary_table_from_template(decision)
            elif decision.element_type == VisualElementType.TIMELINE:
                result = self._generate_timeline_from_template(decision)
            elif decision.element_type == VisualElementType.TAXONOMY_TREE:
                result = self._generate_taxonomy_from_template(decision)
            elif decision.element_type == VisualElementType.FLOWCHART:
                result = self._generate_flowchart_from_template(decision)
            elif decision.element_type == VisualElementType.ARCHITECTURE_DIAGRAM:
                result = self._generate_architecture_from_template(decision)
            elif decision.element_type == VisualElementType.CALLOUT_BOX:
                result = self._generate_callout_box(decision)
            elif decision.element_type == VisualElementType.DATAFLOW:
                result = self._generate_dataflow_from_template(decision)
            elif decision.element_type == VisualElementType.PIPELINE:
                result = self._generate_pipeline_from_template(decision)
            elif decision.element_type == VisualElementType.PERFORMANCE_CHART:
                result = self._generate_performance_chart_from_template(decision)
            elif decision.element_type == VisualElementType.STRUCTURE:
                result = self._generate_structure_from_template(decision)
            elif decision.element_type == VisualElementType.TREE:
                result = self._generate_tree_from_template(decision)
            elif decision.element_type == VisualElementType.MINDMAP:
                result = self._generate_mindmap_from_template(decision)
            elif decision.element_type == VisualElementType.TINY_TREE:
                result = self._generate_tiny_tree_from_template(decision)
            elif decision.element_type == VisualElementType.CONCEPTUAL_COMPARISON:
                result = self._generate_conceptual_comparison_from_template(decision)
            # 新增精美表格类型
            elif decision.element_type == VisualElementType.ICON_DESCRIPTION_TABLE:
                result = self._generate_icon_description_table(decision)
            elif decision.element_type == VisualElementType.GROUPED_CATEGORY_TABLE:
                result = self._generate_grouped_category_table(decision)
            elif decision.element_type == VisualElementType.TAXONOMY_MATRIX_TABLE:
                result = self._generate_taxonomy_matrix_table(decision)
            elif decision.element_type == VisualElementType.NESTED_MULTIROW_TABLE:
                result = self._generate_nested_multirow_table(decision)
            elif decision.element_type == VisualElementType.COLORED_HEADER_TABLE:
                result = self._generate_colored_header_table(decision)
            elif decision.element_type == VisualElementType.BENCHMARK_RESULTS_TABLE:
                result = self._generate_benchmark_results_table(decision)
            elif decision.element_type == VisualElementType.LABELED_BADGE_TABLE:
                result = self._generate_labeled_badge_table(decision)
            else:
                logger.warning(f"Unknown element type: {decision.element_type}")
                return decision
            
            # 如果成功生成了LaTeX代码，更新计数器
            if result.latex_code:
                self._update_counters(decision.element_type, decision.target_section)
            
            return result
        except Exception as e:
            logger.error(f"Error generating {decision.element_type.value}: {e}")
            return decision
    
    def _generate_reference_figure(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """生成引用参考文献图片的LaTeX代码"""
        data = decision.data_requirements
        image_path = data.get("image_path", "")
        
        if not image_path:
            # 尝试从reference_images中获取
            if decision.reference_images:
                image_path = decision.reference_images[0]
        
        if not image_path:
            logger.warning("No image path specified for reference figure")
            return decision
        
        # 复制图片到输出目录
        src_path = Path(image_path)
        if src_path.exists():
            self.element_count[VisualElementType.REFERENCE_FIGURE] += 1
            fig_num = self.element_count[VisualElementType.REFERENCE_FIGURE]
            new_name = f"ref_fig_{fig_num}{src_path.suffix}"
            dst_path = self.figs_dir / new_name
            
            try:
                shutil.copy2(src_path, dst_path)
                logger.info(f"Copied reference image to {dst_path}")
            except Exception as e:
                logger.error(f"Failed to copy image: {e}")
                return decision
            
            # 生成LaTeX代码
            caption = data.get("new_caption", decision.description)
            citation = data.get("citation", "")
            label = f"fig:ref_{fig_num}"
            
            latex_code = f"""
\\begin{{figure}}[H]
    \\centering
    \\includegraphics[width=0.85\\textwidth]{{figs/{new_name}}}
    \\caption{{{self._escape_latex(caption)}{' (' + self._escape_latex(citation) + ')' if citation else ''}}}
    \\label{{{label}}}
\\end{{figure}}
"""
            decision.latex_code = latex_code.strip()
        
        return decision
    
    def _generate_comparison_table_from_template(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """使用模板生成对比表格"""
        # 尝试加载模板
        template = self.templates.get("comparison_table")
        if not template:
            logger.warning("Comparison table template not found")
            return decision
            
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        headers = data.get("headers", [])
        rows = data.get("rows", [])
        
        if not headers or not rows:
            logger.warning("No headers or rows provided for comparison table")
            return decision
        
        self.element_count[VisualElementType.COMPARISON_TABLE] += 1
        label = f"comparison_{self.element_count[VisualElementType.COMPARISON_TABLE]}"
        
        # 生成列规格
        num_cols = len(headers)
        col_width = f"{0.85/num_cols:.2f}\\textwidth"
        column_spec = "l" + "".join([f"p{{{col_width}}}" for _ in range(num_cols - 1)])
        
        # 生成表头
        header_row = " & ".join([self._escape_latex(h) for h in headers]) + " \\\\"
        
        # 生成数据行
        data_rows = []
        for row in rows[:10]:  # 限制最多10行
            row_str = " & ".join([self._escape_latex(str(cell)) for cell in row]) + " \\\\"
            data_rows.append(row_str)
        rows_content = "\n".join(data_rows)
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<column_spec>", column_spec)
        latex_code = latex_code.replace("<headers>", header_row)
        latex_code = latex_code.replace("<rows>", rows_content)
        
        decision.latex_code = latex_code
        return decision
    
    def _escape_latex(self, text: str) -> str:
        """转义LaTeX特殊字符并转换Markdown格式为LaTeX格式"""
        if not text:
            return ""
        text = str(text)
        
        # 先处理Markdown格式转换（在转义特殊字符之前）
        # 转换 **text** 为 \textbf{text}
        import re
        text = re.sub(r'\*\*([^*]+)\*\*', r'\\textbf{\1}', text)
        # 转换 *text* 为 \textit{text}
        text = re.sub(r'\*([^*]+)\*', r'\\textit{\1}', text)
        # 转换 `text` 为 \texttt{text}
        text = re.sub(r'`([^`]+)`', r'\\texttt{\1}', text)
        
        # 转义特殊字符（注意：不转义已经是LaTeX命令的部分）
        # 先保护已有的LaTeX命令
        protected_patterns = []
        def protect_latex(match):
            protected_patterns.append(match.group(0))
            # 使用不包含特殊字符（如下划线）的占位符
            return f"PROTECTEDLATEXCOMMAND{len(protected_patterns)-1}END"
        
        # 保护 \textbf{}, \textit{}, \texttt{} 等命令
        text = re.sub(r'\\text[a-z]+\{[^}]*\}', protect_latex, text)
        # 保护 \cite{}, \ref{}, \autoref{} 等引用命令 (包括前面的波浪号)
        text = re.sub(r'~?\\(cite|ref|autoref)\{[^}]*\}', protect_latex, text)
        
        # 转义特殊字符
        special_chars = {
            '&': r'\&',
            '%': r'\%',
            '$': r'\$',
            '#': r'\#',
            '_': r'\_',
            '{': r'\{',
            '}': r'\}',
            '~': r'\textasciitilde{}',
            '^': r'\textasciicircum{}',
        }
        for char, escaped in special_chars.items():
            text = text.replace(char, escaped)
        
        # 恢复被保护的LaTeX命令
        for i, pattern in enumerate(protected_patterns):
            text = text.replace(f"PROTECTEDLATEXCOMMAND{i}END", pattern)
        
        return text
    
    def _generate_summary_table_from_template(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """使用模板生成总结表格"""
        # 尝试加载模板
        template = self.templates.get("summary_table")
        if not template:
            # 如果没有专门的总结表格模板，使用对比表格模板
            return self._generate_comparison_table_from_template(decision)
            
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        headers = data.get("headers", [])
        rows = data.get("rows", [])
        
        if not headers or not rows:
            logger.warning("No headers or rows provided for summary table")
            return decision
        
        self.element_count[VisualElementType.SUMMARY_TABLE] += 1
        label = f"summary_{self.element_count[VisualElementType.SUMMARY_TABLE]}"
        
        # 生成列规格
        num_cols = len(headers)
        col_width = f"{0.85/num_cols:.2f}\\textwidth"
        column_spec = "l" + "".join([f"p{{{col_width}}}" for _ in range(num_cols - 1)])
        
        # 生成表头
        header_row = " & ".join([self._escape_latex(h) for h in headers]) + " \\\\"
        
        # 生成数据行
        data_rows = []
        for row in rows[:10]:
            row_str = " & ".join([self._escape_latex(str(cell)) for cell in row]) + " \\\\"
            data_rows.append(row_str)
        rows_content = "\n".join(data_rows)
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<column_spec>", column_spec)
        latex_code = latex_code.replace("<headers>", header_row)
        latex_code = latex_code.replace("<rows>", rows_content)
        
        decision.latex_code = latex_code
        return decision
    
    def _generate_timeline_from_template(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """
        使用相对定位生成时间线，确保节点不会重叠
        
        关键改进：使用TikZ的 below=of 相对定位，让节点自动一个接一个排列，
        而不是手动计算间距。这样TikZ会自动处理节点之间的间距。
        """
        from datetime import datetime
        
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        items = data.get("items", [])
        
        if not items:
            logger.warning("No items provided for timeline")
            return decision
        
        self.element_count[VisualElementType.TIMELINE] += 1
        label = f"timeline_{self.element_count[VisualElementType.TIMELINE]}"
        
        # 获取当前年份
        current_year = datetime.now().year
        
        # 过滤掉超出当前年份的事件
        filtered_items = []
        for item in items:
            year_str = str(item.get("year", ""))
            try:
                year_int = int(year_str)
                if year_int <= current_year:
                    filtered_items.append(item)
            except ValueError:
                filtered_items.append(item)
        
        if not filtered_items:
            return decision
        
        # 按年份分组合并事件
        year_events = {}
        for item in filtered_items:
            year = str(item.get("year", ""))
            event = str(item.get("event", ""))
            if year not in year_events:
                year_events[year] = []
            year_events[year].append(event)
        
        # 按年份排序
        try:
            sorted_years = sorted(year_events.keys(), key=lambda x: int(x))
        except ValueError:
            sorted_years = sorted(year_events.keys())
        
        # 限制最多8个年份节点
        sorted_years = sorted_years[:8]
        MAX_EVENTS_PER_YEAR = 3
        
        # 使用相对定位生成节点代码
        nodes_code = []
        
        for i, year in enumerate(sorted_years):
            events = year_events[year]
            year_escaped = self._escape_latex(year)
            
            if len(events) > MAX_EVENTS_PER_YEAR:
                events = events[:MAX_EVENTS_PER_YEAR]
            
            # 构建事件文本
            if len(events) > 1:
                events_lines = ["\\textbullet\\ " + self._escape_latex(e) for e in events]
                events_text = " \\\\ ".join(events_lines)
            else:
                events_text = self._escape_latex(events[0])
            
            event_node_name = f"event{i}"
            
            if i == 0:
                # 第一个节点：使用绝对定位
                nodes_code.append(f"% Year {year}")
                nodes_code.append(f"\\node[event] ({event_node_name}) at (0.3, 0) {{{events_text}}};")
                nodes_code.append(f"\\node[year, left=0.8cm of {event_node_name}.north west, anchor=east] {{{year_escaped}}};")
                nodes_code.append(f"\\node[milestone, left=0.3cm of {event_node_name}.north west, anchor=center] {{}};")
            else:
                # 后续节点：使用相对定位，自动排列在上一个节点下方
                prev_node = f"event{i-1}"
                nodes_code.append(f"% Year {year}")
                nodes_code.append(f"\\node[event, below=0.5cm of {prev_node}.south west, anchor=north west] ({event_node_name}) {{{events_text}}};")
                nodes_code.append(f"\\node[year, left=0.8cm of {event_node_name}.north west, anchor=east] {{{year_escaped}}};")
                nodes_code.append(f"\\node[milestone, left=0.3cm of {event_node_name}.north west, anchor=center] {{}};")
        
        nodes_content = "\n".join(nodes_code)
        
        # 动态生成caption中的年份范围
        actual_min_year = sorted_years[0] if sorted_years else ""
        actual_max_year = sorted_years[-1] if sorted_years else ""
        
        # 尝试替换caption中的年份范围
        import re
        year_range_pattern = r'\(?\d{4}\s*[-–]\s*\d{4}\)?'
        if actual_min_year and actual_max_year and actual_min_year != actual_max_year:
            actual_range = f"({actual_min_year}-{actual_max_year})"
            caption = re.sub(year_range_pattern, actual_range, caption)
        elif actual_min_year and actual_max_year and actual_min_year == actual_max_year:
            caption = re.sub(year_range_pattern, f"({actual_min_year})", caption)
        
        # 生成完整的LaTeX代码（不使用模板，直接生成以确保正确性）
        latex_code = f"""\\begin{{figure}}[H]
\\centering
\\begin{{tikzpicture}}[
    node distance=0.5cm,
    year/.style={{font=\\small\\bfseries, text=blue!70!black, text width=1.2cm, align=right}},
    event/.style={{rectangle, rounded corners=3pt, draw=gray!40, fill=gray!8,
                  text width=10.5cm, font=\\small,
                  align=left, inner sep=8pt}},
    milestone/.style={{circle, fill=blue!60, minimum size=8pt, inner sep=0pt}}
]

{nodes_content}

% 绘制时间线轴（连接所有里程碑点）
\\coordinate (timeline_start) at ([yshift=0.5cm]event0.north west);
\\coordinate (timeline_end) at ([xshift=-0.3cm, yshift=-0.5cm]event{len(sorted_years)-1}.south west);
\\draw[thick, gray!50] ([xshift=-0.3cm]timeline_start) -- ([xshift=-0.3cm]timeline_end);

\\end{{tikzpicture}}
\\caption{{{self._escape_latex(caption)}}}
\\label{{fig:{label}}}
\\end{{figure}}"""
        
        decision.latex_code = latex_code
        logger.info(f"Generated timeline with relative positioning, {len(sorted_years)} year nodes")
        return decision
    
    def _generate_taxonomy_from_template(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """使用固定模板生成分类树"""
        # 尝试加载模板
        template = self.templates.get("taxonomy")
        if not template:
            logger.warning("Taxonomy template not found")
            return decision
            
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        root = data.get("root", "Root")
        children = data.get("children", [])
        
        if not children:
            logger.warning("No children provided for taxonomy tree")
            return decision
        
        self.element_count[VisualElementType.TAXONOMY_TREE] += 1
        label = f"taxonomy_{self.element_count[VisualElementType.TAXONOMY_TREE]}"
        
        # 构建forest树结构
        def build_tree_node(node, depth=0):
            max_children_per_level = 4 if depth < 2 else 3
            
            if isinstance(node, str):
                return f"[{self._escape_latex(node)}]"
            elif isinstance(node, dict):
                name = str(node.get("name", ""))
                name_escaped = self._escape_latex(name)
                node_children = node.get("children", [])
                if node_children:
                    limited_children = node_children[:max_children_per_level]
                    children_str = " ".join([build_tree_node(c, depth + 1) for c in limited_children])
                    return f"[{name_escaped} {children_str}]"
                else:
                    return f"[{name_escaped}]"
            return ""
        
        # 限制一级子节点数量
        limited_children = children[:4]
        children_content = " ".join([build_tree_node(c, 0) for c in limited_children])
        
        tree_content = f"[{self._escape_latex(root)} {children_content}]"
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<tree_content>", tree_content)
        
        decision.latex_code = latex_code
        return decision
    
    def _generate_flowchart_from_template(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """使用固定模板生成流程图"""
        # 尝试加载模板
        template = self.templates.get("flowchart")
        if not template:
            logger.warning("Flowchart template not found")
            return decision
            
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        
        if not nodes:
            logger.warning("No nodes provided for flowchart")
            return decision
        
        self.element_count[VisualElementType.FLOWCHART] += 1
        label = f"flow_{self.element_count[VisualElementType.FLOWCHART]}"
        
        # 限制最多6个节点
        nodes = nodes[:6]
        
        # 生成节点代码
        nodes_code = []
        node_ids = {}
        for i, node in enumerate(nodes):
            node_id = str(node.get("id", str(i+1)))
            node_type = node.get("type", "process")
            node_text = self._escape_latex(str(node.get("text", f"Step {i+1}")))
            node_ids[node_id] = f"node{i+1}"
            
            # 根据类型选择样式
            if node_type == "start":
                style = "startstop"
            elif node_type == "end":
                style = "startstop"
            elif node_type == "decision":
                style = "decision"
            elif node_type == "io":
                style = "io"
            else:
                style = "process"
            
            if i == 0:
                nodes_code.append(f"\\node[{style}] ({node_ids[node_id]}) {{{node_text}}};")
            else:
                prev_node = f"node{i}"
                nodes_code.append(f"\\node[{style}, below=of {prev_node}] ({node_ids[node_id]}) {{{node_text}}};")
        
        # 生成边代码
        edges_code = []
        for edge in edges:
            from_id = str(edge.get("from", ""))
            to_id = str(edge.get("to", ""))
            label_text = self._escape_latex(str(edge.get("label", "")))
            
            if from_id in node_ids and to_id in node_ids:
                if label_text:
                    edges_code.append(f"\\draw[arrow] ({node_ids[from_id]}) -- node[midway, right, font=\\footnotesize] {{{label_text}}} ({node_ids[to_id]});")
                else:
                    edges_code.append(f"\\draw[arrow] ({node_ids[from_id]}) -- ({node_ids[to_id]});")
        
        content = "\n".join(nodes_code) + "\n" + "\n".join(edges_code)
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<nodes>", content)
        # 替换可能存在的 <title> 占位符（如果模板中有）
        latex_code = latex_code.replace("<title>", self._escape_latex(caption))
        
        decision.latex_code = latex_code
        return decision
    
    def _generate_architecture_from_template(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """使用固定模板生成架构图
        
        重构版本：垂直堆叠布局，解决宽度限制下的重叠问题
        - 每层包含：层标题 + 垂直排列的组件
        - 组件垂直堆叠，不会水平重叠
        - 适合窄宽度的文档
        """
        # 尝试加载模板
        template = self.templates.get("architecture")
        if not template:
            logger.warning("Architecture template not found")
            return decision
            
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        layers = data.get("layers", [])
        
        if not layers:
            logger.warning("No layers provided for architecture diagram")
            return decision
        
        self.element_count[VisualElementType.ARCHITECTURE_DIAGRAM] += 1
        label = f"arch_{self.element_count[VisualElementType.ARCHITECTURE_DIAGRAM]}"
        
        # 限制最多5层
        layers = layers[:5]
        
        # 生成层代码 - 使用垂直堆叠布局
        layers_code = []
        
        # 定义层颜色映射 (arch-layer1 to arch-layer5)
        layer_colors = ["arch-layer1", "arch-layer2", "arch-layer3", "arch-layer4", "arch-layer5"]
        # 定义组件颜色映射 (arch-comp1 to arch-comp4)
        comp_colors = ["arch-comp1", "arch-comp2", "arch-comp3", "arch-comp4"]
        
        # 计算总高度：每层 = 标题(0.7) + 组件数*0.8 + 间距(0.5)
        current_y = 0
        layer_positions = []
        
        # 先计算每层的起始位置（从上到下）
        for i, layer in enumerate(layers):
            components = layer.get("components", [])[:4]  # 限制每层最多4个组件
            layer_height = 0.7 + len(components) * 0.8 + 0.3  # 标题 + 组件 + 底部间距
            layer_positions.append({
                'start_y': current_y,
                'height': layer_height,
                'components': components
            })
            current_y -= layer_height + 0.5  # 层间距
        
        # 生成每层的代码
        for i, layer in enumerate(layers):
            layer_name = self._escape_latex(str(layer.get("name", f"Layer {i+1}")))
            components = layer.get("components", [])[:4]
            layer_color = layer_colors[i % len(layer_colors)]
            
            pos = layer_positions[i]
            title_y = pos['start_y']
            
            # 绘制层标题
            layers_code.append(
                f"\\node[layer-title={layer_color}] (title{i}) at (0, {title_y}) "
                f"{{\\textcolor{{white}}{{{layer_name}}}}};"
            )
            
            # 绘制组件（垂直堆叠）
            comp_y = title_y - 0.8  # 第一个组件在标题下方
            for j, comp in enumerate(components):
                comp_text = self._escape_latex(str(comp))
                comp_color = comp_colors[j % len(comp_colors)]
                
                layers_code.append(
                    f"\\node[comp={comp_color}] (c{i}{j}) at (0, {comp_y}) {{{comp_text}}};"
                )
                comp_y -= 0.8  # 下一个组件
            
            # 绘制层之间的连接箭头
            if i < len(layers) - 1:
                arrow_start_y = comp_y + 0.3  # 最后一个组件下方
                next_title_y = layer_positions[i + 1]['start_y']
                arrow_end_y = next_title_y + 0.4  # 下一层标题上方
                layers_code.append(f"\\draw[arrow] (0, {arrow_start_y}) -- (0, {arrow_end_y});")
        
        layers_content = "\n".join(layers_code)
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<layers>", layers_content)
        
        decision.latex_code = latex_code
        logger.info(f"Generated architecture diagram (vertical layout) with {len(layers)} layers")
        return decision
    
    def _generate_dataflow_from_template(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """使用固定模板生成数据流图
        
        重构版本：
        1. 根据节点数量动态计算间距
        2. 支持多行布局（当节点过多时）
        3. 使用相对定位确保节点不重叠
        """
        # 尝试加载模板
        template = self.templates.get("dataflow")
        if not template:
            logger.warning("Dataflow template not found")
            return decision
            
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        nodes = data.get("nodes", [])
        flows = data.get("flows", [])
        
        if not nodes:
            logger.warning("No nodes provided for dataflow diagram")
            return decision
        
        self.element_count[VisualElementType.DATAFLOW] += 1
        label = f"dataflow_{self.element_count[VisualElementType.DATAFLOW]}"
        
        # 限制最多8个节点
        nodes = nodes[:8]
        num_nodes = len(nodes)
        
        # 生成节点代码
        nodes_code = []
        node_positions = {}
        
        # 根据节点数量决定布局策略
        # 单行最多放5个节点，超过则使用多行布局
        MAX_NODES_PER_ROW = 5
        
        if num_nodes <= MAX_NODES_PER_ROW:
            # 单行布局：根据节点数量计算间距
            # 参考模板注释：
            # - 6 nodes: x = 0, 3.5, 7.0, 10.5, 14.0, 17.5 (间距 3.5)
            # - 5 nodes: x = 0, 4.0, 8.0, 12.0, 16.0 (间距 4.0)
            # - 4 nodes: x = 0, 4.5, 9.0, 13.5 (间距 4.5)
            spacing_map = {
                1: 0,
                2: 5.0,
                3: 4.5,
                4: 4.5,
                5: 4.0,
                6: 3.5,
                7: 3.5,
                8: 3.5,
            }
            x_spacing = spacing_map.get(num_nodes, 4.0)
            
            for i, node in enumerate(nodes):
                node_id = str(node.get("id", str(i+1)))
                node_type = node.get("type", "process")
                node_text = self._escape_latex(str(node.get("text", f"Node {i+1}")))
                
                # 计算位置
                x_pos = i * x_spacing
                y_pos = 0
                
                # 根据类型选择样式
                if node_type == "input":
                    style = "external"
                elif node_type == "output":
                    style = "external"
                elif node_type == "storage":
                    style = "datastore"
                else:
                    style = "process"
                
                node_positions[node_id] = f"node{i+1}"
                nodes_code.append(f"\\node[{style}] ({node_positions[node_id]}) at ({x_pos:.1f}, {y_pos}) {{{node_text}}};")
        else:
            # 多行布局：将节点分成两行
            row1_count = (num_nodes + 1) // 2  # 第一行节点数（向上取整）
            row2_count = num_nodes - row1_count
            
            x_spacing = 4.5  # 固定间距
            row_spacing = 3.0  # 行间距
            
            for i, node in enumerate(nodes):
                node_id = str(node.get("id", str(i+1)))
                node_type = node.get("type", "process")
                node_text = self._escape_latex(str(node.get("text", f"Node {i+1}")))
                
                # 计算位置
                if i < row1_count:
                    # 第一行
                    x_pos = i * x_spacing
                    y_pos = 0
                else:
                    # 第二行
                    x_pos = (i - row1_count) * x_spacing
                    y_pos = -row_spacing
                
                # 根据类型选择样式
                if node_type == "input":
                    style = "external"
                elif node_type == "output":
                    style = "external"
                elif node_type == "storage":
                    style = "datastore"
                else:
                    style = "process"
                
                node_positions[node_id] = f"node{i+1}"
                nodes_code.append(f"\\node[{style}] ({node_positions[node_id]}) at ({x_pos:.1f}, {y_pos:.1f}) {{{node_text}}};")
        
        # 生成数据流箭头
        for flow in flows:
            from_id = str(flow.get("from", ""))
            to_id = str(flow.get("to", ""))
            flow_label = self._escape_latex(str(flow.get("label", "")))
            
            if from_id in node_positions and to_id in node_positions:
                if flow_label:
                    # 使用 midway 和 above 来定位标签，避免重叠
                    nodes_code.append(f"\\draw[dataflow] ({node_positions[from_id]}) -- node[flowlabel, midway, above] {{{flow_label}}} ({node_positions[to_id]});")
                else:
                    nodes_code.append(f"\\draw[dataflow] ({node_positions[from_id]}) -- ({node_positions[to_id]});")
        
        nodes_content = "\n".join(nodes_code)
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<nodes>", nodes_content)
        
        decision.latex_code = latex_code
        logger.info(f"Generated dataflow diagram using template with {len(nodes)} nodes (spacing: {x_spacing if num_nodes <= MAX_NODES_PER_ROW else 'multi-row'})")
        return decision
    
    def _generate_pipeline_from_template(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """使用固定模板生成管道/流水线图"""
        # 尝试加载模板
        template = self.templates.get("pipeline")
        if not template:
            logger.warning("Pipeline template not found")
            return decision
            
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        stages = data.get("stages", [])
        
        if not stages:
            logger.warning("No stages provided for pipeline diagram")
            return decision
        
        self.element_count[VisualElementType.PIPELINE] += 1
        label = f"pipeline_{self.element_count[VisualElementType.PIPELINE]}"
        
        # 限制最多6个阶段
        stages = stages[:6]
        
        # 定义颜色列表 (pipe-stage1 to pipe-stage6)
        colors = ["pipe-stage1", "pipe-stage2", "pipe-stage3", "pipe-stage4", "pipe-stage5", "pipe-stage6"]
        
        # 生成阶段代码
        stages_code = []
        for i, stage in enumerate(stages):
            stage_name = self._escape_latex(str(stage.get("name", f"Stage {i+1}")))
            stage_desc = self._escape_latex(str(stage.get("description", "")))
            color = colors[i % len(colors)]
            x_pos = i * 3.5
            
            # 绘制箭头形状的阶段
            stages_code.append(f"\\node[stage={color}] (stage{i+1}) at ({x_pos}, 0) {{{stage_name}}};")
            stages_code.append(f"\\node[desc] at ({x_pos}, -1.2) {{{stage_desc}}};")
            
            # 添加连接箭头（除了最后一个）
            if i < len(stages) - 1:
                stages_code.append(f"\\draw[arrow] (stage{i+1}.east) -- ++(0.7, 0);")
        
        stages_content = "\n".join(stages_code)
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<stages>", stages_content)
        
        decision.latex_code = latex_code
        return decision
    
    def _generate_performance_chart_from_template(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """使用固定模板生成性能对比图（柱状图）
        
        重要改进：
        - 跳过值为0或缺失的数据，不显示对应的柱子
        - 只显示有效数据（值 > 0）
        - 这样可以避免显示大量无意义的0值
        """
        # 尝试加载模板
        template = self.templates.get("performance_chart")
        if not template:
            logger.warning("Performance chart template not found")
            return decision
            
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        methods = data.get("methods", [])
        metrics = data.get("metrics", [])
        values = data.get("values", [])  # 2D array: values[method_idx][metric_idx]
        
        if not methods or not metrics or not values:
            logger.warning("Incomplete data for performance chart")
            return decision
        
        self.element_count[VisualElementType.PERFORMANCE_CHART] += 1
        label = f"perf_{self.element_count[VisualElementType.PERFORMANCE_CHART]}"
        
        # 限制最多5个方法和4个指标
        methods = methods[:5]
        metrics = metrics[:4]
        values = [row[:4] for row in values[:5]]
        
        # 定义颜色 (perf-bar1 to perf-bar4)
        bar_colors = ["perf-bar1", "perf-bar2", "perf-bar3", "perf-bar4"]
        
        # 计算柱状图参数
        num_methods = len(methods)
        num_metrics = len(metrics)
        bar_width = 0.6 / num_metrics
        group_width = 1.0
        
        # 统计有效数据（用于判断是否需要生成图表）
        valid_data_count = 0
        
        # 生成柱状图代码
        bars_code = []
        for m_idx, method in enumerate(methods):
            for metric_idx in range(min(num_metrics, len(values[m_idx]) if m_idx < len(values) else 0)):
                if m_idx < len(values) and metric_idx < len(values[m_idx]):
                    # 获取值，处理各种可能的格式
                    raw_value = values[m_idx][metric_idx]
                    try:
                        value = float(raw_value) if raw_value else 0
                    except (ValueError, TypeError):
                        value = 0
                    
                    # 跳过值为0或无效的数据
                    if value <= 0:
                        continue
                    
                    valid_data_count += 1
                    x_pos = m_idx * group_width + metric_idx * bar_width - (num_metrics - 1) * bar_width / 2
                    color = bar_colors[metric_idx % len(bar_colors)]
                    # 缩放高度（假设值在0-100范围内）
                    height = value / 100 * 4  # 最大高度4cm
                    bars_code.append(f"\\fill[{color}] ({x_pos - bar_width/2}, 0) rectangle ({x_pos + bar_width/2}, {height:.2f});")
                    # 添加数值标签
                    bars_code.append(f"\\node[font=\\tiny] at ({x_pos}, {height + 0.2}) {{{value:.1f}}};")
        
        # 如果没有有效数据，记录警告并返回
        if valid_data_count == 0:
            logger.warning(f"No valid data (all values are 0 or missing) for performance chart in section {decision.target_section}")
            return decision
        
        # 生成X轴标签
        x_labels = []
        for m_idx, method in enumerate(methods):
            x_pos = m_idx * group_width
            x_labels.append(f"\\node[font=\\small, rotate=30, anchor=east] at ({x_pos}, -0.3) {{{self._escape_latex(method)}}};")
        
        # 生成图例
        legend_items = []
        for metric_idx, metric in enumerate(metrics):
            color = bar_colors[metric_idx % len(bar_colors)]
            y_pos = 4.5 - metric_idx * 0.4
            legend_items.append(f"\\fill[{color}] (5, {y_pos}) rectangle (5.3, {y_pos + 0.25});")
            legend_items.append(f"\\node[font=\\scriptsize, anchor=west] at (5.4, {y_pos + 0.125}) {{{self._escape_latex(metric)}}};")
        
        bars_content = "\n".join(bars_code)
        x_labels_content = "\n".join(x_labels)
        legend_content = "\n".join(legend_items)
        
        # 计算X轴范围
        x_max = (num_methods - 1) * group_width + 0.5
        
        # 生成坐标轴
        y_axis = f"""\\draw[->] (-0.5, 0) -- (-0.5, 4.5) node[above, font=\\small] {{Score}};
\\foreach \\y in {{0, 1, 2, 3, 4}}
    \\draw (-0.6, \\y) -- (-0.5, \\y) node[left, font=\\tiny] {{\\pgfmathparse{{\\y*25}}\\pgfmathprintnumber{{\\pgfmathresult}}}};"""
        
        x_axis = f"\\draw[->] (-0.5, 0) -- ({x_max + 0.5}, 0);"
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<bars>", bars_content)
        latex_code = latex_code.replace("<x_labels>", x_labels_content)
        latex_code = latex_code.replace("<legend>", legend_content)
        latex_code = latex_code.replace("<y_axis>", y_axis)
        latex_code = latex_code.replace("<x_axis>", x_axis)
        
        decision.latex_code = latex_code
        return decision
    
    def _generate_structure_from_template(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """
        使用 Forest 包生成 Survey 结构图
        
        重构版本：
        1. 添加章节编号支持（§1, §2, 1.1, 1.2等）
        2. 正确处理引用，生成\cite{}格式
        3. 更好的文字宽度控制，避免超出布局
        4. 学习图2的布局风格
        5. **重要修复**: 将 structure 图保存为单独文件，通过 \input 引入，
           确保颜色定义和样式定义在正确的位置
        """
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        root = data.get("root", "Survey Topic")
        children = data.get("children", [])
        
        if not children:
            logger.warning("No children provided for structure diagram")
            return decision
        
        self.element_count[VisualElementType.STRUCTURE] += 1
        label = f"structure_{self.element_count[VisualElementType.STRUCTURE]}"
        
        # 定义调色板 (保持原有配色方案)
        palette = [
            "a44c34", "bc966f", "b9ac99", "96a25f", "f3e6f1", "fdcee4",
            "c77fa1", "c1c8cd", "727b83", "9C7C7C", "D3E0EA", "b8a9a9"
        ]
        
        # 生成颜色定义
        import random
        sampled_colors = random.sample(palette, len(palette))
        color_defs = []
        for i, color in enumerate(sampled_colors):
            color_defs.append(f"\\definecolor{{c{i}}}{{HTML}}{{{color}}}")
        # 添加 hidden-draw 颜色定义
        color_defs.append("\\definecolor{hidden-draw}{RGB}{255, 255, 255}")
        
        define_color_tex = "\n".join(color_defs)
        
        def format_refs_as_cite(refs_str: str) -> str:
            """
            将引用字符串转换为LaTeX cite格式
            例如: "arXiv_2505.04072, Smith2024" -> "\\cite{arXiv_2505.04072,Smith2024}"
            """
            if not refs_str:
                return ""
            # 清理引用字符串
            refs_str = refs_str.strip()
            # 如果已经是cite格式，直接返回
            if refs_str.startswith("\\cite{"):
                return refs_str
            # 分割多个引用
            refs_list = [r.strip() for r in refs_str.replace(";", ",").split(",") if r.strip()]
            if not refs_list:
                return ""
            # 生成cite命令
            return f"~\\cite{{{','.join(refs_list)}}}"
        
        def build_forest_node(node, depth: int = 0, color_idx: int = 0,
                             section_num: str = "", subsection_counter: list = None):
            """
            递归构建 Forest 节点
            
            Args:
                node: 节点数据（字符串或字典）
                depth: 当前深度（0=root, 1=section, 2=subsection, 3=leaf）
                color_idx: 颜色索引
                section_num: 章节编号（如 "1", "2"）
                subsection_counter: 子节点计数器列表 [用于生成1.1, 1.2等编号]
            """
            color = f"c{color_idx}"
            
            if subsection_counter is None:
                subsection_counter = [0]
            
            if isinstance(node, str):
                # 叶子节点（纯字符串）
                name_escaped = self._escape_latex(node)
                
                # 根据深度确定样式和编号
                if depth == 1:
                    # 一级节点：§1. Title
                    style = "ot1"
                    display_text = f"\\S {section_num}.\\ {name_escaped}"
                elif depth == 2:
                    # 二级节点：1.1 Title
                    style = "ot2"
                    subsection_counter[0] += 1
                    sub_num = f"{section_num}.{subsection_counter[0]}"
                    display_text = f"{sub_num}\\ {name_escaped}"
                else:
                    # 三级节点
                    style = "ot3"
                    display_text = name_escaped
                
                return f"[{display_text}, {style}, draw={color}, fill={color}, fill opacity=0.3]"
            
            elif isinstance(node, dict):
                name = str(node.get("name", ""))
                name_escaped = self._escape_latex(name)
                node_children = node.get("children", [])
                refs = node.get("refs", "")
                
                # 处理引用
                refs_latex = format_refs_as_cite(refs)
                
                # 根据深度确定样式和编号
                if depth == 1:
                    # 一级节点：§1. Title
                    style = "ot1"
                    display_text = f"\\S {section_num}.\\ {name_escaped}"
                elif depth == 2:
                    # 二级节点：1.1 Title
                    style = "ot2"
                    subsection_counter[0] += 1
                    sub_num = f"{section_num}.{subsection_counter[0]}"
                    display_text = f"{sub_num}\\ {name_escaped}"
                else:
                    # 三级节点
                    style = "ot3"
                    display_text = name_escaped
                
                # 如果有引用，添加到显示文本后面
                if refs_latex:
                    display_text = f"{display_text}{refs_latex}"
                
                node_opts = f"{style}, draw={color}, fill={color}, fill opacity=0.3"
                
                if node_children:
                    # 有子节点
                    max_children = 6 if depth < 2 else 4
                    limited_children = node_children[:max_children]
                    
                    # 为子节点创建新的计数器
                    child_counter = [0]
                    children_str = " ".join([
                        build_forest_node(
                            c,
                            depth + 1,
                            color_idx,
                            section_num,
                            child_counter
                        )
                        for c in limited_children
                    ])
                    return f"[{display_text}, {node_opts} {children_str}]"
                else:
                    # 叶子节点
                    return f"[{display_text}, {node_opts}]"
            
            return ""
        
        # 构建子节点（每个一级子节点使用不同颜色和编号）
        children_content_list = []
        for i, c in enumerate(children[:8]):  # 限制最多8个主分支
            color_idx = i % len(sampled_colors)
            section_num = str(i + 1)  # 章节编号从1开始
            children_content_list.append(
                build_forest_node(c, 1, color_idx, section_num, [0])
            )
        
        children_content = " ".join(children_content_list)
        
        root_escaped = self._escape_latex(root)
        tree_content = f"[\\textbf{{{root_escaped}}}, root, ver {children_content}]"
        
        # 生成完整的 structure_fig.tex 文件内容
        # 包含颜色定义、样式定义和 figure 环境
        structure_file_content = f"""{define_color_tex}

% 大纲总样式
\\tikzstyle{{ot}}=[
    rectangle,
    draw=hidden-draw,
    rounded corners,
    align=left,
    text opacity=1,
    text=black,
    minimum height=2.5em,
    minimum width=5em,
    inner xsep=4pt,
    inner ysep=4pt,
    line width=0.8pt,
    font=\\small,
]

% 大纲主样式-root
\\tikzstyle{{root}}=[
    ot,
    draw=gray!80,
    fill=gray!35,
    font=\\small\\bfseries,
]

% 大纲主样式-1级 (Section)
\\tikzstyle{{ot1}}=[
    ot,
    minimum height=2em,
    font=\\small,
]

% 大纲主样式-2级 (Subsection)
\\tikzstyle{{ot2}}=[
    ot,
    minimum height=1.8em,
    font=\\footnotesize,
]

% 大纲主样式-3级 (Subsubsection/Leaf with refs)
\\tikzstyle{{ot3}}=[
    ot,
    minimum height=1.5em,
    font=\\footnotesize,
]

\\begin{{figure*}}[!th]
    \\centering
    \\resizebox{{0.98\\textwidth}}{{!}}
    {{
        \\begin{{forest}}
            for tree={{
                grow=east,
                reversed=true,
                anchor=base west,
                parent anchor=east,
                child anchor=west,
                base=left,
                font=\\small,
                rectangle,
                draw=hidden-draw,
                rounded corners,
                align=left,
                minimum width=2em,
                edge+={{darkgray, line width=1pt}},
                s sep=7pt,
                inner xsep=4pt,
                inner ysep=3pt,
                line width=0.8pt,
                ver/.style={{rotate=90, child anchor=north, parent anchor=south, anchor=center}},
            }},
            {tree_content}
        \\end{{forest}}
    }}
    \\caption{{{self._escape_latex(caption)}}}
    \\label{{fig:{label}}}
\\vspace{{-0.3cm}}
\\end{{figure*}}
"""
        
        # 保存到 figs 目录
        structure_file_path = self.figs_dir / f"{label}.tex"
        try:
            with open(structure_file_path, "w", encoding="utf-8") as f:
                f.write(structure_file_content)
            logger.info(f"Saved structure diagram to {structure_file_path}")
        except Exception as e:
            logger.error(f"Failed to save structure diagram: {e}")
            return decision
        
        # 返回 \input 命令而不是内联代码
        # 这样颜色定义和样式定义会在正确的位置
        decision.latex_code = f"\\input{{figs/{label}}}"
        logger.info(f"Generated structure diagram with {len(children)} sections and section numbering")
        return decision
    
    def _generate_tree_from_template(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """
        使用模板生成通用树形图
        
        这是一个灵活的树形图模板，支持自定义节点样式和布局。
        """
        # 尝试加载模板
        template = self.templates.get("tree")
        if not template:
            logger.warning("Tree template not found")
            return decision
            
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        root = data.get("root", "Root")
        children = data.get("children", [])
        
        if not children:
            logger.warning("No children provided for tree diagram")
            return decision
        
        self.element_count[VisualElementType.TREE] += 1
        label = f"tree_{self.element_count[VisualElementType.TREE]}"
        
        # 构建树节点代码
        def build_tree_nodes(nodes, parent_id="root", depth=0, x_offset=0):
            """递归构建 TikZ 树节点"""
            code_lines = []
            y_spacing = 1.5
            x_spacing = 4.0
            
            for i, node in enumerate(nodes):
                if isinstance(node, str):
                    node_name = node
                    node_children = []
                elif isinstance(node, dict):
                    node_name = node.get("name", f"Node {i}")
                    node_children = node.get("children", [])
                else:
                    continue
                
                node_id = f"{parent_id}_{i}"
                node_text = self._escape_latex(node_name)
                
                # 确定节点样式（使用模板中定义的样式名称）
                if depth == 0:
                    style = "nodeRoot"
                elif node_children:
                    style = "node"
                else:
                    style = "nodeB"
                
                # 计算位置
                y_pos = -i * y_spacing
                x_pos = depth * x_spacing + x_offset
                
                if parent_id == "root":
                    code_lines.append(f"\\node[{style}] ({node_id}) at ({x_pos}, {y_pos}) {{{node_text}}};")
                else:
                    code_lines.append(f"\\node[{style}] ({node_id}) at ({x_pos}, {y_pos}) {{{node_text}}};")
                    code_lines.append(f"\\draw[edge] ({parent_id}) -- ({node_id});")
                
                # 递归处理子节点
                if node_children:
                    child_code = build_tree_nodes(
                        node_children[:4],  # 限制子节点数量
                        node_id,
                        depth + 1,
                        x_offset
                    )
                    code_lines.extend(child_code)
            
            return code_lines
        
        # 生成根节点
        root_escaped = self._escape_latex(root)
        tree_code = [f"\\node[nodeRoot] (root) at (0, 0) {{{root_escaped}}};"]
        
        # 生成子节点
        tree_code.extend(build_tree_nodes(children[:5], "root", 1))
        
        tree_content = "\n".join(tree_code)
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<tree_code>", tree_content)
        
        decision.latex_code = latex_code
        logger.info(f"Generated tree diagram using template with {len(children)} main branches")
        return decision
    
    def _generate_mindmap_from_template(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """
        使用模板生成思维导图
        
        这是一个放射状的概念关系图，适用于展示概念之间的关系。
        """
        # 尝试加载模板
        template = self.templates.get("mindmap")
        if not template:
            logger.warning("Mindmap template not found")
            return decision
            
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        root = data.get("root", "Central Concept")
        children = data.get("children", [])
        
        if not children:
            logger.warning("No children provided for mindmap")
            return decision
        
        self.element_count[VisualElementType.MINDMAP] += 1
        label = f"mindmap_{self.element_count[VisualElementType.MINDMAP]}"
        
        # 定义颜色（使用模板中定义的颜色名称）
        colors = ["mind-l1-1", "mind-l1-2", "mind-l1-3", "mind-l1-4", "mind-l1-5", "mind-l1-6"]
        
        def build_mindmap_node(node, depth=1, color_idx=0):
            """递归构建 mindmap 节点"""
            color = colors[color_idx % len(colors)]
            
            if isinstance(node, str):
                return f"child[concept color={color}] {{ node {{{self._escape_latex(node)}}} }}"
            elif isinstance(node, dict):
                name = str(node.get("name", ""))
                name_escaped = self._escape_latex(name)
                node_children = node.get("children", [])
                
                if node_children and depth < 3:  # 限制最多3层
                    children_str = "\n".join([
                        build_mindmap_node(c, depth + 1, color_idx)
                        for c in node_children[:4]  # 限制子节点数量
                    ])
                    return f"child[concept color={color}] {{ node {{{name_escaped}}} {children_str} }}"
                else:
                    return f"child[concept color={color}] {{ node {{{name_escaped}}} }}"
            return ""
        
        # 构建子节点
        children_content = "\n".join([
            build_mindmap_node(c, 1, i)
            for i, c in enumerate(children[:6])  # 限制最多6个一级分支
        ])
        
        # 构建完整的树代码（根节点 + 子节点）
        tree_content = f"node[root] {{{self._escape_latex(root)}}}\n    {children_content};"
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<tree_code>", tree_content)
        
        decision.latex_code = latex_code
        logger.info(f"Generated mindmap using template with {len(children)} main branches")
        return decision
    
    def _generate_tiny_tree_from_template(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """
        使用模板生成紧凑树形图
        
        适用于小型层次结构，使用更紧凑的布局。
        """
        # 尝试加载模板
        template = self.templates.get("tiny_tree")
        if not template:
            logger.warning("Tiny tree template not found")
            return decision
            
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        root = data.get("root", "Root")
        children = data.get("children", [])
        
        if not children:
            logger.warning("No children provided for tiny tree")
            return decision
        
        self.element_count[VisualElementType.TINY_TREE] += 1
        label = f"tiny_tree_{self.element_count[VisualElementType.TINY_TREE]}"
        
        # 构建树节点代码
        def build_tiny_nodes(nodes, parent_id="root", depth=0, parent_y=0):
            """递归构建紧凑树节点"""
            code_lines = []
            y_spacing = 1.2
            x_spacing = 3.5
            
            for i, node in enumerate(nodes):
                if isinstance(node, str):
                    node_name = node
                    node_children = []
                elif isinstance(node, dict):
                    node_name = node.get("name", f"Node {i}")
                    node_children = node.get("children", [])
                else:
                    continue
                
                node_id = f"{parent_id}_{i}"
                node_text = self._escape_latex(node_name)
                
                # 确定节点样式（使用模板中定义的样式名称）
                if node_children:
                    style = "nodeB"
                else:
                    style = "nodeL"
                
                # 计算位置
                y_pos = parent_y - (i + 1) * y_spacing
                x_pos = depth * x_spacing
                
                code_lines.append(f"\\node[{style}] ({node_id}) at ({x_pos}, {y_pos}) {{{node_text}}};")
                code_lines.append(f"\\draw[edge from parent] ({parent_id}) -- ({node_id});")
                
                # 递归处理子节点
                if node_children:
                    child_code = build_tiny_nodes(
                        node_children[:4],  # 限制子节点数量
                        node_id,
                        depth + 1,
                        y_pos
                    )
                    code_lines.extend(child_code)
            
            return code_lines
        
        # 生成根节点
        root_escaped = self._escape_latex(root)
        tree_code = [f"\\node[root] (root) at (0, 0) {{{root_escaped}}};"]
        
        # 生成子节点
        tree_code.extend(build_tiny_nodes(children[:5], "root", 1, 0))
        
        tree_content = "\n".join(tree_code)
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<tree_code>", tree_content)
        
        decision.latex_code = latex_code
        logger.info(f"Generated tiny tree using template with {len(children)} main branches")
        return decision
    
    def _generate_conceptual_comparison_from_template(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """
        使用模板生成概念对比图 (Venn-like)
        """
        # 尝试加载模板
        template = self.templates.get("conceptual_comparison")
        if not template:
            logger.warning("Conceptual comparison template not found")
            return decision
            
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        
        self.element_count[VisualElementType.CONCEPTUAL_COMPARISON] += 1
        label = f"concept_{self.element_count[VisualElementType.CONCEPTUAL_COMPARISON]}"
        
        # 提取标签和文本
        center_label = self._escape_latex(data.get("center_label", "Center"))
        left_label = self._escape_latex(data.get("left_label", "Left"))
        right_label = self._escape_latex(data.get("right_label", "Right"))
        bottom_label = self._escape_latex(data.get("bottom_label", "Bottom"))
        
        center_left_text = self._escape_latex(data.get("center_left_text", ""))
        center_right_text = self._escape_latex(data.get("center_right_text", ""))
        center_bottom_text = self._escape_latex(data.get("center_bottom_text", ""))
        
        # 处理注释
        annotations = data.get("annotations", {})
        
        def format_annotation(key):
            anno = annotations.get(key, {})
            title = self._escape_latex(anno.get("title", ""))
            items = anno.get("items", [])
            if items:
                items_str = "\\\\ ".join(["- " + self._escape_latex(item) for item in items[:3]])
            else:
                items_str = ""
            return title, items_str
            
        center_title, center_items = format_annotation("center")
        left_title, left_items = format_annotation("left")
        right_title, right_items = format_annotation("right")
        bottom_title, bottom_items = format_annotation("bottom")
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        
        latex_code = latex_code.replace("<center_label>", center_label)
        latex_code = latex_code.replace("<left_label>", left_label)
        latex_code = latex_code.replace("<right_label>", right_label)
        latex_code = latex_code.replace("<bottom_label>", bottom_label)
        
        latex_code = latex_code.replace("<center_left_text>", center_left_text)
        latex_code = latex_code.replace("<center_right_text>", center_right_text)
        latex_code = latex_code.replace("<center_bottom_text>", center_bottom_text)
        
        latex_code = latex_code.replace("<center_annotation_title>", center_title)
        latex_code = latex_code.replace("<center_annotation_items>", center_items)
        
        latex_code = latex_code.replace("<left_annotation_title>", left_title)
        latex_code = latex_code.replace("<left_annotation_items>", left_items)
        
        latex_code = latex_code.replace("<right_annotation_title>", right_title)
        latex_code = latex_code.replace("<right_annotation_items>", right_items)
        
        latex_code = latex_code.replace("<bottom_annotation_title>", bottom_title)
        latex_code = latex_code.replace("<bottom_annotation_items>", bottom_items)
        
        decision.latex_code = latex_code
        logger.info(f"Generated conceptual comparison diagram")
        return decision

    def _generate_callout_box(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """
        生成信息框/文本框 (Key Insights, Example, Evidence等)
        
        支持的box_type:
        - key_insights: 关键洞察框（灰色标题栏 + 蓝色边框）
        - example: 示例框（圆角边框，展示具体例子）
        - evidence: 证据/引用框（左侧竖线装饰）
        - definition: 定义框
        - warning: 警告/注意框
        """
        data = decision.data_requirements
        box_type = data.get("box_type", "key_insights")
        title = data.get("title", "")
        content_items = data.get("items", [])
        
        if not content_items:
            logger.warning("No items provided for callout box")
            return decision
        
        self.element_count[VisualElementType.CALLOUT_BOX] += 1
        
        if box_type == "key_insights":
            latex_code = self._generate_key_insights_box(title, content_items)
        elif box_type == "example":
            latex_code = self._generate_example_box(title, data)
        elif box_type == "evidence":
            latex_code = self._generate_evidence_box(data)
        elif box_type == "definition":
            latex_code = self._generate_definition_box(data)
        elif box_type == "warning":
            latex_code = self._generate_warning_box(title, content_items)
        elif box_type == "numbered_list":
            latex_code = self._generate_numbered_list_box(title, content_items)
        elif box_type == "key_questions":
            latex_code = self._generate_key_questions_box(title, content_items)
        elif box_type == "concept_list":
            latex_code = self._generate_concept_list_box(title, data)
        elif box_type == "summary":
            latex_code = self._generate_summary_box(title, content_items)
        elif box_type == "note":
            latex_code = self._generate_note_box(title, content_items)
        elif box_type == "tip":
            latex_code = self._generate_tip_box(title, content_items)
        else:
            # 默认使用 key_insights 样式
            latex_code = self._generate_key_insights_box(title or "Key Insights", content_items)
        
        decision.latex_code = latex_code
        return decision
    
    def _generate_key_insights_box(self, title: str, items: List[str]) -> str:
        """
        生成关键洞察框
        
        改进版本：
        1. 支持带引用的洞见（格式：洞见内容 [citation_key]）
        2. 自动检测并转换引用格式
        3. 确保内容专业且有依据
        """
        title = title or "Key Insights"
        
        # 生成列表项，处理引用格式
        items_latex = []
        for item in items[:5]:  # 限制最多5条
            # 处理引用格式：将 [citation_key] 转换为 \cite{citation_key}
            # 支持多种格式：[Author2024], [arXiv_2024.xxxxx], [1,2,3]
            import re
            
            # 检测并转换引用格式
            # 格式1: [Author2024] 或 [arXiv_2024.xxxxx]
            processed_item = re.sub(
                r'\[([a-zA-Z0-9_\-\.]+(?:,\s*[a-zA-Z0-9_\-\.]+)*)\]',
                lambda m: f"~\\cite{{{m.group(1).replace(' ', '')}}}",
                item
            )
            
            # 转义 LaTeX 特殊字符（但保护已有的 \cite 命令）
            processed_item = self._escape_latex(processed_item)
            
            items_latex.append(f"    \\item {processed_item}")
        
        items_content = "\n".join(items_latex)
        
        latex_code = f"""\\begin{{tcolorbox}}[
    enhanced,
    colback=blue!3,
    colframe=blue!40!gray,
    coltitle=white,
    fonttitle=\\bfseries,
    title={self._escape_latex(title)},
    attach boxed title to top left={{yshift=-2mm, xshift=2mm}},
    boxed title style={{colback=gray!60, sharp corners}},
    sharp corners=south,
    rounded corners=north,
    left=3mm,
    right=3mm,
    top=4mm,
    bottom=3mm,
    boxrule=0.5pt,
    leftrule=3pt
]
\\begin{{itemize}}[leftmargin=*, itemsep=2pt]
{items_content}
\\end{{itemize}}
\\end{{tcolorbox}}"""
        
        return latex_code
    
    def _generate_example_box(self, title: str, data: Dict) -> str:
        """生成示例框"""
        title = title or data.get("title", "Example")
        sections = data.get("sections", [])
        
        # 构建内容
        content_parts = []
        for section in sections[:6]:  # 限制最多6个部分
            label = self._escape_latex(section.get("label", ""))
            text = self._escape_latex(section.get("text", ""))
            style = section.get("style", "normal")  # normal, italic, code, highlight
            
            if style == "italic":
                content_parts.append(f"\\textbf{{{label}}} \\textit{{{text}}}")
            elif style == "code":
                content_parts.append(f"\\textbf{{{label}}} \\texttt{{{text}}}")
            elif style == "highlight":
                content_parts.append(f"\\textbf{{{label}}} \\textcolor{{red}}{{{text}}}")
            else:
                content_parts.append(f"\\textbf{{{label}}} {text}")
        
        content = "\n\n".join(content_parts)
        
        latex_code = f"""\\begin{{tcolorbox}}[
    enhanced,
    colback=gray!5,
    colframe=gray!50,
    coltitle=black,
    fonttitle=\\bfseries,
    title={self._escape_latex(title)},
    attach boxed title to top left={{yshift=-2mm, xshift=2mm}},
    boxed title style={{colback=white, colframe=gray!50}},
    rounded corners,
    left=3mm,
    right=3mm,
    top=4mm,
    bottom=3mm,
    boxrule=0.5pt
]
{content}
\\end{{tcolorbox}}"""
        
        return latex_code
    
    def _generate_evidence_box(self, data: Dict) -> str:
        """生成证据/引用框"""
        quote = self._escape_latex(data.get("quote", ""))
        citation = self._escape_latex(data.get("citation", ""))
        keyphrases = data.get("keyphrases", [])
        
        # 构建关键短语
        keyphrases_latex = ""
        if keyphrases:
            phrases = ["\\textcolor{purple}{``" + self._escape_latex(kp) + "''}" for kp in keyphrases[:5]]
            keyphrases_latex = "\n\n\\textbf{Generated Keyphrases:} " + ", ".join(phrases)
        
        # 构建引用部分（避免在f-string表达式中使用反斜杠）
        citation_latex = "~\\cite{" + citation + "}" if citation else ""
        
        latex_code = """\\begin{tcolorbox}[
    enhanced,
    colback=white,
    colframe=white,
    leftrule=3pt,
    left=4mm,
    right=3mm,
    top=2mm,
    bottom=2mm,
    borderline west={3pt}{0pt}{purple!60}
]
\\textbf{Evidence:} ``""" + quote + "''" + citation_latex + keyphrases_latex + """
\\end{tcolorbox}"""
        
        return latex_code
    
    def _generate_definition_box(self, data: Dict) -> str:
        """生成定义框"""
        term = self._escape_latex(data.get("term", "Term"))
        definition = self._escape_latex(data.get("definition", ""))
        
        latex_code = f"""\\begin{{tcolorbox}}[
    enhanced,
    colback=blue!5,
    colframe=blue!40!gray,
    rounded corners,
    left=3mm,
    right=3mm,
    top=3mm,
    bottom=3mm,
    boxrule=0.5pt
]
\\textbf{{Definition ({term}):}} {definition}
\\end{{tcolorbox}}"""
        
        return latex_code
    
    def _generate_warning_box(self, title: str, items: List[str]) -> str:
        """生成警告/注意框"""
        title = title or "Important Note"
        
        # 生成内容
        if len(items) == 1:
            content = self._escape_latex(items[0])
        else:
            items_latex = "\n".join([
                f"    \\item {self._escape_latex(item)}"
                for item in items[:4]
            ])
            content = f"""\\begin{{itemize}}[leftmargin=*, itemsep=2pt]
{items_latex}
\\end{{itemize}}"""
        
        latex_code = f"""\\begin{{tcolorbox}}[
    enhanced,
    colback=orange!10,
    colframe=orange!60,
    coltitle=black,
    fonttitle=\\bfseries,
    title={self._escape_latex(title)},
    rounded corners,
    left=3mm,
    right=3mm,
    top=3mm,
    bottom=3mm,
    boxrule=0.5pt
]
{content}
\\end{{tcolorbox}}"""
        
        return latex_code
    
    def _generate_numbered_list_box(self, title: str, items: List[str]) -> str:
        """
        生成带编号圆圈的列表框
        
        样式：浅绿色背景，深绿色边框，带编号圆圈的列表项
        适用于：展示"Three Types of..."、"Major Categories"等内容
        """
        title = title or "Key Points"
        
        # 生成带编号圆圈的列表项
        items_latex = []
        for i, item in enumerate(items[:6], 1):  # 限制最多6条
            escaped_item = self._escape_latex(item)
            # 使用 tikz 绘制编号圆圈
            items_latex.append(
                f"    \\item[\\tikz{{\\node[circle, fill=teal!70, text=white, inner sep=1.5pt, font=\\footnotesize\\bfseries] {{{i}}}}}] {escaped_item}"
            )
        
        items_content = "\n".join(items_latex)
        
        latex_code = f"""\\begin{{tcolorbox}}[
    enhanced,
    colback=teal!5,
    colframe=teal!60,
    coltitle=white,
    fonttitle=\\bfseries,
    title={self._escape_latex(title)},
    attach boxed title to top left={{yshift=-2mm, xshift=2mm}},
    boxed title style={{colback=teal!70, sharp corners}},
    rounded corners,
    left=4mm,
    right=3mm,
    top=4mm,
    bottom=3mm,
    boxrule=0.5pt
]
\\begin{{itemize}}[leftmargin=6mm, itemsep=4pt, labelsep=3mm]
{items_content}
\\end{{itemize}}
\\end{{tcolorbox}}"""
        
        return latex_code
    
    def _generate_key_questions_box(self, title: str, items: List[str]) -> str:
        """
        生成关键问题框
        
        样式：浅蓝色背景，带编号圆圈的问题列表
        适用于：展示研究问题、关键问题等
        """
        title = title or "Key Questions"
        
        # 生成带编号圆圈的问题列表
        items_latex = []
        for i, item in enumerate(items[:6], 1):  # 限制最多6个问题
            escaped_item = self._escape_latex(item)
            # 使用带圆圈的数字符号
            items_latex.append(
                f"    \\item[\\textcolor{{red!70}}{{\\ding{{\\numexpr181+{i}\\relax}}}}] {escaped_item}"
            )
        
        items_content = "\n".join(items_latex)
        
        latex_code = f"""\\begin{{tcolorbox}}[
    enhanced,
    colback=cyan!5,
    colframe=cyan!50!blue!50,
    coltitle=white,
    fonttitle=\\bfseries,
    title={self._escape_latex(title)},
    attach boxed title to top left={{yshift=-2mm, xshift=2mm}},
    boxed title style={{colback=cyan!60!blue!60, sharp corners}},
    rounded corners,
    left=4mm,
    right=3mm,
    top=4mm,
    bottom=3mm,
    boxrule=0.5pt
]
\\begin{{itemize}}[leftmargin=6mm, itemsep=4pt, labelsep=3mm]
{items_content}
\\end{{itemize}}
\\end{{tcolorbox}}"""
        
        return latex_code
    
    def _generate_concept_list_box(self, title: str, data: Dict) -> str:
        """
        生成概念列表框（带子项说明）
        
        样式：浅绿色背景，每个概念带有详细说明
        适用于：展示多个相关概念及其解释，如"Three Major Memory Forms"
        
        data格式：
        {
            "title": "Three Major Memory Forms",
            "concepts": [
                {
                    "name": "Token-level Memory",
                    "section_ref": "Section 3.1",  # 可选
                    "description": "Memory organized as explicit and discrete units..."
                },
                ...
            ]
        }
        """
        title = title or data.get("title", "Key Concepts")
        concepts = data.get("concepts", data.get("items", []))
        
        # 如果 concepts 是简单字符串列表，转换为概念格式
        if concepts and isinstance(concepts[0], str):
            concepts = [{"name": "", "description": item} for item in concepts]
        
        # 生成概念列表
        concepts_latex = []
        for i, concept in enumerate(concepts[:5], 1):  # 限制最多5个概念
            if isinstance(concept, dict):
                name = concept.get("name", "")
                section_ref = concept.get("section_ref", "")
                description = concept.get("description", "")
                
                name_escaped = self._escape_latex(name)
                desc_escaped = self._escape_latex(description)
                
                if name and section_ref:
                    # 带章节引用的格式
                    concepts_latex.append(
                        f"    \\item \\textbf{{{name_escaped}}} (\\textcolor{{red}}{{{self._escape_latex(section_ref)}}}): {desc_escaped}"
                    )
                elif name:
                    concepts_latex.append(
                        f"    \\item \\textbf{{{name_escaped}}}: {desc_escaped}"
                    )
                else:
                    concepts_latex.append(f"    \\item {desc_escaped}")
            else:
                concepts_latex.append(f"    \\item {self._escape_latex(str(concept))}")
        
        concepts_content = "\n".join(concepts_latex)
        
        latex_code = f"""\\begin{{tcolorbox}}[
    enhanced,
    colback=green!5,
    colframe=green!50!black!50,
    coltitle=white,
    fonttitle=\\bfseries,
    title={self._escape_latex(title)},
    attach boxed title to top left={{yshift=-2mm, xshift=2mm}},
    boxed title style={{colback=green!60!black!60, sharp corners}},
    rounded corners,
    left=3mm,
    right=3mm,
    top=4mm,
    bottom=3mm,
    boxrule=0.5pt
]
\\begin{{enumerate}}[leftmargin=*, itemsep=6pt, label=\\arabic*.]
{concepts_content}
\\end{{enumerate}}
\\end{{tcolorbox}}"""
        
        return latex_code
    
    def _generate_summary_box(self, title: str, items: List[str]) -> str:
        """
        生成总结框
        
        样式：浅紫色背景，用于章节总结或要点回顾
        适用于：章节末尾的总结、关键要点回顾
        """
        title = title or "Summary"
        
        # 生成列表项
        items_latex = "\n".join([
            f"    \\item {self._escape_latex(item)}"
            for item in items[:5]  # 限制最多5条
        ])
        
        latex_code = f"""\\begin{{tcolorbox}}[
    enhanced,
    colback=violet!5,
    colframe=violet!50,
    coltitle=white,
    fonttitle=\\bfseries,
    title={self._escape_latex(title)},
    attach boxed title to top left={{yshift=-2mm, xshift=2mm}},
    boxed title style={{colback=violet!60, sharp corners}},
    rounded corners,
    left=3mm,
    right=3mm,
    top=4mm,
    bottom=3mm,
    boxrule=0.5pt,
    shadow={{2mm}}{{-2mm}}{{0mm}}{{black!20}}
]
\\begin{{itemize}}[leftmargin=*, itemsep=2pt]
{items_latex}
\\end{{itemize}}
\\end{{tcolorbox}}"""
        
        return latex_code
    
    def _generate_note_box(self, title: str, items: List[str]) -> str:
        """
        生成注释/补充说明框
        
        样式：浅黄色背景，左侧带竖线装饰
        适用于：补充说明、注释、旁注
        """
        title = title or "Note"
        
        # 生成内容
        if len(items) == 1:
            content = self._escape_latex(items[0])
        else:
            items_latex = "\n".join([
                f"    \\item {self._escape_latex(item)}"
                for item in items[:4]
            ])
            content = f"""\\begin{{itemize}}[leftmargin=*, itemsep=2pt]
{items_latex}
\\end{{itemize}}"""
        
        latex_code = f"""\\begin{{tcolorbox}}[
    enhanced,
    colback=yellow!10,
    colframe=yellow!10,
    coltitle=black,
    fonttitle=\\bfseries\\itshape,
    title={self._escape_latex(title)},
    attach boxed title to top left={{yshift=-2mm, xshift=2mm}},
    boxed title style={{colback=yellow!30, colframe=yellow!50}},
    rounded corners,
    left=4mm,
    right=3mm,
    top=4mm,
    bottom=3mm,
    boxrule=0pt,
    borderline west={{3pt}}{{0pt}}{{yellow!70!orange}}
]
{content}
\\end{{tcolorbox}}"""
        
        return latex_code
    
    def _generate_tip_box(self, title: str, items: List[str]) -> str:
        """
        生成提示/最佳实践框
        
        样式：浅蓝绿色背景，带灯泡图标
        适用于：最佳实践、建议、提示
        """
        title = title or "Tip"
        
        # 生成内容
        if len(items) == 1:
            content = self._escape_latex(items[0])
        else:
            items_latex = "\n".join([
                f"    \\item {self._escape_latex(item)}"
                for item in items[:4]
            ])
            content = f"""\\begin{{itemize}}[leftmargin=*, itemsep=2pt]
{items_latex}
\\end{{itemize}}"""
        
        latex_code = f"""\\begin{{tcolorbox}}[
    enhanced,
    colback=teal!10,
    colframe=teal!50,
    coltitle=white,
    fonttitle=\\bfseries,
    title={{\\faLightbulbO\\ {self._escape_latex(title)}}},
    attach boxed title to top left={{yshift=-2mm, xshift=2mm}},
    boxed title style={{colback=teal!60, sharp corners}},
    rounded corners,
    left=3mm,
    right=3mm,
    top=4mm,
    bottom=3mm,
    boxrule=0.5pt
]
{content}
\\end{{tcolorbox}}"""
        
        return latex_code
    
    # ==================== 新增精美表格生成方法 ====================
    
    def _generate_icon_description_table(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """
        生成带图标的描述表格
        
        类似 Table 2 (Natural language prompts) 的样式
        特点：左侧图标+标题，右侧详细描述
        
        data_requirements 格式:
        {
            "caption": "表格标题",
            "header_left": "Prompt Type",
            "header_right": "Explanations",
            "rows": [
                {"icon": "📝", "title": "System Prompt", "description": "Text templates..."},
                {"icon": "💡", "title": "Instructions", "description": "Commands or instructions..."}
            ]
        }
        """
        template = self.templates.get("icon_description_table")
        if not template:
            logger.warning("Icon description table template not found")
            return decision
        
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        header_left = data.get("header_left", "Type")
        header_right = data.get("header_right", "Description")
        rows = data.get("rows", [])
        
        if not rows:
            logger.warning("No rows provided for icon description table")
            return decision
        
        self.element_count[VisualElementType.ICON_DESCRIPTION_TABLE] += 1
        label = f"icon_desc_{self.element_count[VisualElementType.ICON_DESCRIPTION_TABLE]}"
        
        # 生成行内容
        rows_latex = []
        for row in rows[:8]:  # 限制最多8行
            icon = row.get("icon", "")
            title = self._escape_latex(row.get("title", ""))
            description = self._escape_latex(row.get("description", ""))
            
            # 格式化为：图标 + 粗体标题 & 描述
            if icon:
                left_cell = f"{icon} \\textbf{{{title}}}"
            else:
                left_cell = f"\\textbf{{{title}}}"
            
            rows_latex.append(f"{left_cell} & {description} \\\\")
        
        rows_content = "\n".join(rows_latex)
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<header_left>", self._escape_latex(header_left))
        latex_code = latex_code.replace("<header_right>", self._escape_latex(header_right))
        latex_code = latex_code.replace("<rows>", rows_content)
        
        decision.latex_code = latex_code
        logger.info(f"Generated icon description table with {len(rows)} rows")
        return decision
    
    def _generate_grouped_category_table(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """
        生成带彩色分组标题的表格
        
        类似 Table 4, 5 (Datasets & Benchmarks) 的样式
        特点：彩色圆点分组标题，多级表头
        
        data_requirements 格式:
        {
            "caption": "表格标题",
            "headers": ["Dataset", "Year", "Type", "Scale", "Description"],
            "groups": [
                {
                    "name": "Vision-Action Datasets",
                    "color": "teal",
                    "rows": [
                        ["BDD100K", "2020", "Real", "120M", "Trajectory prediction"],
                        ["nuScenes", "2020", "Real", "1.4M", "Perception"]
                    ]
                },
                {
                    "name": "Vision-Language Datasets",
                    "color": "cyan",
                    "rows": [...]
                }
            ]
        }
        """
        template = self.templates.get("grouped_category_table")
        if not template:
            logger.warning("Grouped category table template not found")
            return decision
        
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        headers = data.get("headers", [])
        groups = data.get("groups", [])
        
        if not headers or not groups:
            logger.warning("No headers or groups provided for grouped category table")
            return decision
        
        self.element_count[VisualElementType.GROUPED_CATEGORY_TABLE] += 1
        label = f"grouped_{self.element_count[VisualElementType.GROUPED_CATEGORY_TABLE]}"
        
        # 生成列规格
        num_cols = len(headers)
        column_spec = "l" * num_cols
        
        # 生成表头
        header_row = " & ".join([f"\\textbf{{{self._escape_latex(h)}}}" for h in headers]) + " \\\\"
        
        # 生成分组行
        rows_latex = []
        for group in groups[:5]:  # 限制最多5个分组
            group_name = self._escape_latex(group.get("name", ""))
            group_color = group.get("color", "teal")
            group_rows = group.get("rows", [])
            
            # 添加分组标题行
            rows_latex.append(f"\\multicolumn{{{num_cols}}}{{l}}{{\\textcolor{{{group_color}}}{{\\textbullet\\ \\textbf{{{group_name}}}}}}} \\\\")
            
            # 添加数据行
            for row in group_rows[:6]:  # 每组最多6行
                row_str = " & ".join([self._escape_latex(str(cell)) for cell in row])
                rows_latex.append(f"{row_str} \\\\")
        
        rows_content = "\n".join(rows_latex)
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<column_spec>", column_spec)
        latex_code = latex_code.replace("<headers>", header_row)
        latex_code = latex_code.replace("<rows>", rows_content)
        
        decision.latex_code = latex_code
        logger.info(f"Generated grouped category table with {len(groups)} groups")
        return decision
    
    def _generate_taxonomy_matrix_table(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """
        生成矩阵式分类表格
        
        类似 Table 1 (Taxonomy Matrix for MM-RAG Studies) 的样式
        特点：斜线表头，勾选标记，分组行
        
        data_requirements 格式:
        {
            "caption": "表格标题",
            "row_header": "Input",
            "col_headers": ["Text", "Code", "Image", "Video"],
            "row_groups": [
                {
                    "name": "Uni-Modal",
                    "rows": [
                        {"name": "Text", "ref": "§3.1.1", "checks": [true, true, false, true]},
                        {"name": "Image", "ref": "§3.1.2", "checks": [true, false, false, false]}
                    ]
                }
            ],
            "footnote": "* Video may be considered..."
        }
        """
        template = self.templates.get("taxonomy_matrix_table")
        if not template:
            logger.warning("Taxonomy matrix table template not found")
            return decision
        
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        row_header = data.get("row_header", "Input")
        col_headers = data.get("col_headers", [])
        row_groups = data.get("row_groups", [])
        footnote = data.get("footnote", "")
        
        if not col_headers or not row_groups:
            logger.warning("No headers or row groups provided for taxonomy matrix table")
            return decision
        
        self.element_count[VisualElementType.TAXONOMY_MATRIX_TABLE] += 1
        label = f"matrix_{self.element_count[VisualElementType.TAXONOMY_MATRIX_TABLE]}"
        
        # 生成列规格
        num_cols = len(col_headers) + 2  # row_header + name + ref + checks
        column_spec = "ll" + "c" * len(col_headers)
        
        # 生成表头（使用斜线分隔）
        col_headers_str = " & ".join([f"\\textbf{{{self._escape_latex(h)}}}" for h in col_headers])
        header_row = f"\\diagbox{{\\textbf{{{self._escape_latex(row_header)}}}}}{{\\textbf{{Output}}}} & & {col_headers_str} \\\\"
        
        # 生成分组行
        rows_latex = []
        for group in row_groups[:4]:  # 限制最多4个分组
            group_name = self._escape_latex(group.get("name", ""))
            group_rows = group.get("rows", [])
            
            # 添加分组标题
            first_row = True
            for row in group_rows[:6]:  # 每组最多6行
                row_name = self._escape_latex(row.get("name", ""))
                row_ref = self._escape_latex(row.get("ref", ""))
                checks = row.get("checks", [])
                
                # 生成勾选标记
                check_cells = []
                for check in checks[:len(col_headers)]:
                    if check:
                        check_cells.append("\\checkmark")
                    else:
                        check_cells.append("")
                
                checks_str = " & ".join(check_cells)
                
                if first_row:
                    rows_latex.append(f"\\multirow{{{len(group_rows)}}}{{*}}{{\\rotatebox{{90}}{{\\textbf{{{group_name}}}}}}} & {row_name} ({row_ref}) & {checks_str} \\\\")
                    first_row = False
                else:
                    rows_latex.append(f" & {row_name} ({row_ref}) & {checks_str} \\\\")
            
            rows_latex.append("\\midrule")
        
        # 移除最后一个 \midrule
        if rows_latex and rows_latex[-1] == "\\midrule":
            rows_latex.pop()
        
        rows_content = "\n".join(rows_latex)
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<column_spec>", column_spec)
        latex_code = latex_code.replace("<headers>", header_row)
        latex_code = latex_code.replace("<rows>", rows_content)
        latex_code = latex_code.replace("<footnote>", self._escape_latex(footnote) if footnote else "")
        
        decision.latex_code = latex_code
        logger.info(f"Generated taxonomy matrix table with {len(row_groups)} groups")
        return decision
    
    def _generate_nested_multirow_table(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """
        生成嵌套多行表格
        
        类似 Table 2 (Core Components, Tasks, and Applications) 的样式
        特点：多级嵌套行，multirow合并单元格
        
        data_requirements 格式:
        {
            "caption": "表格标题",
            "headers": ["Modality", "Backbone", "", "Task", "Examples"],
            "sub_headers": ["", "Retriever", "Generator", "", ""],
            "rows": [
                {
                    "modality": "T+I→T",
                    "sub_rows": [
                        {"retriever": "CLIP", "generator": "GPT", "task": "Visual QA", "examples": "MuRAG, RA-VQA"},
                        {"retriever": "", "generator": "LLaVA", "task": "Image Caption", "examples": "Re-ViLM"}
                    ]
                }
            ]
        }
        """
        template = self.templates.get("nested_multirow_table")
        if not template:
            logger.warning("Nested multirow table template not found")
            return decision
        
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        headers = data.get("headers", [])
        sub_headers = data.get("sub_headers", [])
        rows = data.get("rows", [])
        
        if not headers or not rows:
            logger.warning("No headers or rows provided for nested multirow table")
            return decision
        
        self.element_count[VisualElementType.NESTED_MULTIROW_TABLE] += 1
        label = f"nested_{self.element_count[VisualElementType.NESTED_MULTIROW_TABLE]}"
        
        # 生成列规格
        num_cols = len(headers)
        column_spec = "l" * num_cols
        
        # 生成表头
        header_row = " & ".join([f"\\textbf{{{self._escape_latex(h)}}}" for h in headers]) + " \\\\"
        
        # 生成子表头（如果有）
        sub_header_row = ""
        if sub_headers and any(sub_headers):
            sub_header_row = " & ".join([self._escape_latex(h) for h in sub_headers]) + " \\\\ \\midrule"
        
        # 生成数据行
        rows_latex = []
        for row_group in rows[:8]:  # 限制最多8个主行
            modality = self._escape_latex(row_group.get("modality", ""))
            sub_rows = row_group.get("sub_rows", [])
            
            if not sub_rows:
                continue
            
            num_sub_rows = len(sub_rows)
            
            for i, sub_row in enumerate(sub_rows[:4]):  # 每组最多4个子行
                cells = []
                
                # 第一列使用 multirow
                if i == 0:
                    cells.append(f"\\multirow{{{num_sub_rows}}}{{*}}{{{modality}}}")
                else:
                    cells.append("")
                
                # 其他列
                for key in ["retriever", "generator", "task", "examples"]:
                    if key in sub_row:
                        cells.append(self._escape_latex(str(sub_row[key])))
                
                rows_latex.append(" & ".join(cells) + " \\\\")
            
            rows_latex.append("\\midrule")
        
        # 移除最后一个 \midrule
        if rows_latex and rows_latex[-1] == "\\midrule":
            rows_latex.pop()
        
        rows_content = "\n".join(rows_latex)
        
        # 组合表头
        full_headers = header_row
        if sub_header_row:
            full_headers += "\n" + sub_header_row
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<column_spec>", column_spec)
        latex_code = latex_code.replace("<headers>", full_headers)
        latex_code = latex_code.replace("<rows>", rows_content)
        
        decision.latex_code = latex_code
        logger.info(f"Generated nested multirow table with {len(rows)} row groups")
        return decision
    
    def _generate_colored_header_table(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """
        生成带彩色标题栏的表格
        
        类似 Table 3, 4 (Training Strategies) 的样式
        特点：顶部彩色标题栏，嵌套行结构
        
        data_requirements 格式:
        {
            "caption": "表格标题",
            "header_color": "blue",
            "headers": ["Training Strategy", "Methods"],
            "rows": [
                {"strategy": "Parameter-Frozen", "methods": "PICa, TIGeR, RAR..."},
                {
                    "strategy": "Parameter-Trainable",
                    "sub_rows": [
                        {"sub_strategy": "Modular Training", "methods": "VisRAG, DocPrompt..."},
                        {"sub_strategy": "End-to-End", "methods": "MuRAG, RA-VQA..."}
                    ]
                }
            ]
        }
        """
        template = self.templates.get("colored_header_table")
        if not template:
            logger.warning("Colored header table template not found")
            return decision
        
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        header_color = data.get("header_color", "blue")
        headers = data.get("headers", [])
        rows = data.get("rows", [])
        
        if not headers or not rows:
            logger.warning("No headers or rows provided for colored header table")
            return decision
        
        self.element_count[VisualElementType.COLORED_HEADER_TABLE] += 1
        label = f"colored_{self.element_count[VisualElementType.COLORED_HEADER_TABLE]}"
        
        # 生成列规格
        num_cols = len(headers)
        column_spec = "l" + "p{0.6\\textwidth}" * (num_cols - 1)
        
        # 生成表头
        header_row = " & ".join([f"\\textbf{{{self._escape_latex(h)}}}" for h in headers]) + " \\\\"
        
        # 生成数据行
        rows_latex = []
        for row in rows[:10]:  # 限制最多10行
            strategy = self._escape_latex(row.get("strategy", ""))
            methods = row.get("methods", "")
            sub_rows = row.get("sub_rows", [])
            
            if sub_rows:
                # 有子行的情况
                num_sub = len(sub_rows)
                for i, sub_row in enumerate(sub_rows[:4]):
                    sub_strategy = self._escape_latex(sub_row.get("sub_strategy", ""))
                    sub_methods = self._escape_latex(sub_row.get("methods", ""))
                    
                    if i == 0:
                        rows_latex.append(f"\\multirow{{{num_sub}}}{{*}}{{{strategy}}} & {sub_strategy} & {sub_methods} \\\\")
                    else:
                        rows_latex.append(f" & {sub_strategy} & {sub_methods} \\\\")
            else:
                # 简单行
                rows_latex.append(f"{strategy} & {self._escape_latex(methods)} \\\\")
        
        rows_content = "\n".join(rows_latex)
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<header_color>", header_color)
        latex_code = latex_code.replace("<column_spec>", column_spec)
        latex_code = latex_code.replace("<headers>", header_row)
        latex_code = latex_code.replace("<rows>", rows_content)
        
        decision.latex_code = latex_code
        logger.info(f"Generated colored header table with {len(rows)} rows")
        return decision
    
    def _generate_benchmark_results_table(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """
        生成基准测试结果表格
        
        类似 Table 5 (Open-Loop Planning comparisons) 的样式
        特点：多级表头，数值精确对齐，分组行
        
        data_requirements 格式:
        {
            "caption": "表格标题",
            "headers_level1": ["Model", "Year", "Input", "Vision", "Language", "Action", "L2↓", "", "", "", "CR↓", "", "", ""],
            "headers_level2": ["", "", "", "", "", "", "1s", "2s", "3s", "Avg.", "1s", "2s", "3s", "Avg."],
            "groups": [
                {
                    "name": "Vision-Action Models",
                    "color": "green",
                    "rows": [
                        ["ST-P3", "2022", "📷", "EfficientNet", "-", "REG", "1.33", "2.11", "2.90", "2.11", "0.23", "0.62", "1.27", "0.71"]
                    ]
                }
            ]
        }
        """
        template = self.templates.get("benchmark_results_table")
        if not template:
            logger.warning("Benchmark results table template not found")
            return decision
        
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        headers_level1 = data.get("headers_level1", [])
        headers_level2 = data.get("headers_level2", [])
        groups = data.get("groups", [])
        
        if not headers_level1 or not groups:
            logger.warning("No headers or groups provided for benchmark results table")
            return decision
        
        self.element_count[VisualElementType.BENCHMARK_RESULTS_TABLE] += 1
        label = f"benchmark_{self.element_count[VisualElementType.BENCHMARK_RESULTS_TABLE]}"
        
        # 生成列规格
        num_cols = len(headers_level1)
        column_spec = "l" * min(6, num_cols) + "c" * max(0, num_cols - 6)
        
        # 生成第一级表头
        header1_cells = []
        for h in headers_level1:
            if h:
                header1_cells.append(f"\\textbf{{{self._escape_latex(h)}}}")
            else:
                header1_cells.append("")
        headers_level1_row = " & ".join(header1_cells) + " \\\\"
        
        # 生成第二级表头
        headers_level2_row = ""
        if headers_level2 and any(headers_level2):
            header2_cells = [self._escape_latex(h) for h in headers_level2]
            headers_level2_row = " & ".join(header2_cells) + " \\\\"
        
        # 生成分组行
        rows_latex = []
        for group in groups[:4]:  # 限制最多4个分组
            group_name = self._escape_latex(group.get("name", ""))
            group_color = group.get("color", "green")
            group_rows = group.get("rows", [])
            
            # 添加分组标题行
            rows_latex.append(f"\\multicolumn{{{num_cols}}}{{l}}{{\\textcolor{{{group_color}}}{{\\textbullet\\ {group_name}}}}} \\\\")
            
            # 添加数据行
            for row in group_rows[:10]:  # 每组最多10行
                row_str = " & ".join([self._escape_latex(str(cell)) for cell in row[:num_cols]])
                rows_latex.append(f"{row_str} \\\\")
        
        rows_content = "\n".join(rows_latex)
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<column_spec>", column_spec)
        latex_code = latex_code.replace("<headers_level1>", headers_level1_row)
        latex_code = latex_code.replace("<headers_level2>", headers_level2_row)
        latex_code = latex_code.replace("<rows>", rows_content)
        
        decision.latex_code = latex_code
        logger.info(f"Generated benchmark results table with {len(groups)} groups")
        return decision
    
    def _generate_labeled_badge_table(
        self,
        decision: VisualElementDecision
    ) -> VisualElementDecision:
        """
        生成带彩色标签徽章的表格
        
        类似 Table 3, 4 (带 B, N, W 等彩色圆形标签) 的样式
        特点：彩色圆形字母标签，分组标题，多列数据
        
        data_requirements 格式:
        {
            "caption": "表格标题",
            "headers": ["Dataset", "Year", "Sensor", "Type", "Scale", "Tasks"],
            "badge_colors": {
                "B": "blue", "N": "orange", "W": "green", "A": "red"
            },
            "groups": [
                {
                    "name": "Vision-Action Datasets",
                    "color": "teal",
                    "rows": [
                        {"badge": "B", "data": ["BDD100K", "2020", "📷", "Real", "120M", "Percept."]},
                        {"badge": "N", "data": ["nuScenes", "2020", "📷🔊", "Real", "1.4M", "Percept."]}
                    ]
                }
            ]
        }
        """
        template = self.templates.get("labeled_badge_table")
        if not template:
            logger.warning("Labeled badge table template not found")
            return decision
        
        data = decision.data_requirements
        caption = data.get("caption", decision.description)
        headers = data.get("headers", [])
        badge_colors = data.get("badge_colors", {"B": "blue", "N": "orange", "W": "green", "A": "red"})
        groups = data.get("groups", [])
        
        if not headers or not groups:
            logger.warning("No headers or groups provided for labeled badge table")
            return decision
        
        self.element_count[VisualElementType.LABELED_BADGE_TABLE] += 1
        label = f"badge_{self.element_count[VisualElementType.LABELED_BADGE_TABLE]}"
        
        # 生成列规格
        num_cols = len(headers)
        column_spec = "l" * num_cols
        
        # 生成表头
        header_row = " & ".join([f"\\textbf{{{self._escape_latex(h)}}}" for h in headers]) + " \\\\"
        
        # 生成分组行
        rows_latex = []
        for group in groups[:5]:  # 限制最多5个分组
            group_name = self._escape_latex(group.get("name", ""))
            group_color = group.get("color", "teal")
            group_rows = group.get("rows", [])
            
            # 添加分组标题行
            rows_latex.append(f"\\multicolumn{{{num_cols}}}{{l}}{{\\textcolor{{{group_color}}}{{\\textbullet\\ \\textbf{{{group_name}}}}}}} \\\\")
            
            # 添加数据行
            for row in group_rows[:8]:  # 每组最多8行
                badge = row.get("badge", "")
                row_data = row.get("data", [])
                
                # 生成徽章
                badge_color = badge_colors.get(badge, "gray")
                badge_latex = f"\\tikz{{\\node[circle, fill={badge_color}!70, text=white, inner sep=1pt, font=\\tiny\\bfseries] {{{badge}}};}}"
                
                # 第一列加上徽章
                cells = []
                for i, cell in enumerate(row_data[:num_cols]):
                    if i == 0:
                        cells.append(f"{badge_latex} {self._escape_latex(str(cell))}")
                    else:
                        cells.append(self._escape_latex(str(cell)))
                
                rows_latex.append(" & ".join(cells) + " \\\\")
        
        rows_content = "\n".join(rows_latex)
        
        # 使用模板替换
        latex_code = template.replace("<caption>", self._escape_latex(caption))
        latex_code = latex_code.replace("<label>", label)
        latex_code = latex_code.replace("<column_spec>", column_spec)
        latex_code = latex_code.replace("<headers>", header_row)
        latex_code = latex_code.replace("<rows>", rows_content)
        
        decision.latex_code = latex_code
        logger.info(f"Generated labeled badge table with {len(groups)} groups")
        return decision

    def insert_visual_elements(
        self,
        mainbody_content: str,
        decisions: List[VisualElementDecision]
    ) -> str:
        """
        将视觉元素插入到综述内容中
        
        Args:
            mainbody_content: 原始综述内容
            decisions: 视觉元素决策列表
            
        Returns:
            插入视觉元素后的内容
        """
        # 过滤出有LaTeX代码的决策
        valid_decisions = [d for d in decisions if d.latex_code]
        
        if not valid_decisions:
            return mainbody_content
        
        # 按章节分组
        by_section = {}
        for decision in valid_decisions:
            section = decision.target_section
            if section not in by_section:
                by_section[section] = []
            by_section[section].append(decision)
        
        # 逐章节插入
        modified_content = mainbody_content
        
        for section_no, section_decisions in by_section.items():
            # 按优先级排序
            section_decisions.sort(key=lambda x: x.priority, reverse=True)
            
            for decision in section_decisions[:self.max_elements_per_section]:
                modified_content = self._insert_single_element(
                    modified_content,
                    decision
                )
        
        return modified_content
    
    def _insert_single_element(
        self,
        content: str,
        decision: VisualElementDecision
    ) -> str:
        """插入单个视觉元素"""
        # 找到目标章节的位置
        insert_pos = self._find_section_position(content, decision.target_section)
        
        if insert_pos == -1:
            logger.warning(f"Section {decision.target_section} not found")
            return content
        
        # 跳过空行，找到第一段结束的位置
        remaining = content[insert_pos:]
        para_end = remaining.find("\n\n")
        if para_end != -1:
            insert_pos += para_end
        
        # 构建插入内容
        insert_content = f"\n\n{decision.latex_code}\n"
        
        # 插入内容
        modified = content[:insert_pos] + insert_content + content[insert_pos:]
        
        logger.info(f"Inserted {decision.element_type.value} into section {decision.target_section}")
        return modified
    
    def _find_section_position(self, content: str, section_no: str) -> int:
        """找到指定章节编号的位置
        
        Args:
            content: LaTeX内容
            section_no: 章节编号（如 "1", "2.1", "3.2" 等）
            
        Returns:
            章节标题结束的位置，如果未找到返回-1
        """
        parts = section_no.split('.')
        
        # 解析所有章节
        section_pattern = r'\\section\{([^}]+)\}'
        subsection_pattern = r'\\subsection\{([^}]+)\}'
        
        section_matches = list(re.finditer(section_pattern, content))
        subsection_matches = list(re.finditer(subsection_pattern, content))
        
        try:
            if len(parts) == 1:
                # 一级章节
                section_idx = int(parts[0]) - 1
                if 0 <= section_idx < len(section_matches):
                    return section_matches[section_idx].end()
            else:
                # 二级章节（如 "2.1"）
                target_section = int(parts[0])
                target_subsection = int(parts[1])
                
                # 找到目标section的范围
                if target_section <= 0 or target_section > len(section_matches):
                    return -1
                
                section_start = section_matches[target_section - 1].start()
                section_end = section_matches[target_section].start() if target_section < len(section_matches) else len(content)
                
                # 在该section范围内找到对应的subsection
                subsection_count = 0
                for match in subsection_matches:
                    if section_start < match.start() < section_end:
                        subsection_count += 1
                        if subsection_count == target_subsection:
                            return match.end()
        except (ValueError, IndexError) as e:
            logger.warning(f"Error parsing section number {section_no}: {e}")
        
        return -1
    
    def generate_visual_summary(
        self,
        decisions: List[VisualElementDecision]
    ) -> str:
        """
        生成视觉元素摘要报告
        
        Args:
            decisions: 决策列表
            
        Returns:
            摘要文本
        """
        generated = [d for d in decisions if d.latex_code]
        skipped = [d for d in decisions if not d.latex_code and d.element_type != VisualElementType.NONE]
        
        summary = f"""
# Dynamic Visual Elements Summary

## Generated Elements: {len(generated)}
"""
        
        # 按类型统计
        type_counts = {}
        for d in generated:
            t = d.element_type.value
            type_counts[t] = type_counts.get(t, 0) + 1
        
        summary += "\n### By Type:\n"
        for t, count in type_counts.items():
            summary += f"- {t}: {count}\n"
        
        summary += "\n### Details:\n"
        for d in generated:
            summary += f"""
**{d.element_type.value}** in Section {d.target_section}
- Description: {d.description}
- Priority: {d.priority}
- Reason: {d.reason}
"""
        
        if skipped:
            summary += f"\n## Skipped Elements: {len(skipped)}\n"
            for d in skipped[:5]:
                summary += f"- {d.element_type.value} in {d.target_section}: {d.reason}\n"
        
        return summary
    
    def _has_reached_global_limits(self) -> bool:
        """检查是否已达到全局限制"""
        total_generated = self.total_tikz_count + self.total_table_count + self.total_reference_fig_count
        return total_generated >= self.MAX_TOTAL_ELEMENTS

    def _format_existing_elements_info(self) -> str:
        """格式化已存在的视觉元素信息，用于提示LLM避免重复"""
        if not self.existing_visual_elements:
            return "No existing visual elements."
        
        info_lines = ["The following visual elements have already been generated. AVOID generating similar content:"]
        for i, elem in enumerate(self.existing_visual_elements, 1):
            topics_str = ", ".join(elem.topics) if elem.topics else "N/A"
            info_lines.append(
                f"{i}. [{elem.element_type.upper()}] \"{elem.title}\"\n"
                f"   - Section: {elem.target_section}\n"
                f"   - Topics: {topics_str}\n"
                f"   - Description: {elem.description[:200]}..." if len(elem.description) > 200 else f"   - Description: {elem.description}"
            )
        
        return "\n".join(info_lines)
    
    def _global_planning(
        self,
        mainbody_content: str,
        sections: List[Tuple[str, str, str]],
        survey_topic: str
    ) -> Dict[str, Any]:
        """
        全局规划阶段：分析整个综述，决定需要什么类型的视觉元素以及在哪里生成
        
        Args:
            mainbody_content: 综述主体内容
            sections: 解析后的章节列表 [(section_no, section_title, section_content), ...]
            survey_topic: 综述主题
            
        Returns:
            规划结果，包含每种类型的视觉元素应该生成的位置和数量
        """
        # 构建章节摘要
        sections_summary = []
        for section_no, section_title, section_content in sections:
            # 提取章节的关键特征
            has_comparison = any(word in section_content.lower() for word in ['compare', 'comparison', 'versus', 'vs', 'differ'])
            has_timeline = any(word in section_content.lower() for word in ['history', 'evolution', 'development', 'timeline', 'year', '2017', '2018', '2019', '2020', '2021', '2022', '2023', '2024'])
            has_taxonomy = any(word in section_content.lower() for word in ['category', 'classification', 'taxonomy', 'type', 'class'])
            has_process = any(word in section_content.lower() for word in ['process', 'pipeline', 'workflow', 'step', 'procedure', 'flow'])
            has_architecture = any(word in section_content.lower() for word in ['architecture', 'structure', 'framework', 'model', 'layer'])
            has_methods = any(word in section_content.lower() for word in ['method', 'approach', 'technique', 'algorithm'])
            
            sections_summary.append({
                'section_no': section_no,
                'title': section_title,
                'length': len(section_content),
                'has_comparison': has_comparison,
                'has_timeline': has_timeline,
                'has_taxonomy': has_taxonomy,
                'has_process': has_process,
                'has_architecture': has_architecture,
                'has_methods': has_methods,
                'content_preview': section_content[:500]
            })
        
        # 构建全局规划prompt
        # 获取已存在的视觉元素信息
        existing_elements_info = self._format_existing_elements_info()
        
        prompt = f"""You are an academic survey writing expert. Analyze the following survey structure and decide what visual elements should be added.

## Survey Topic
{survey_topic}

## IMPORTANT: Existing Visual Elements (AVOID DUPLICATES)
{existing_elements_info}

## Survey Sections
{json.dumps(sections_summary, indent=2, ensure_ascii=False)}

## Available Visual Element Types

### TikZ Figures (for technical illustrations):
1. **timeline** - For showing historical development and evolution of the field
2. **taxonomy_tree** - For showing classification hierarchy and categorization
3. **flowchart** - For showing processes, workflows, or decision flows
4. **architecture** - For showing system architecture with layered components
5. **dataflow** - For showing data flow between components (input → process → output)
6. **pipeline** - For showing sequential processing stages (e.g., training pipeline)
7. **performance_chart** - For comparing performance metrics across methods (bar chart)
8. **structure** - For showing survey structure with multi-level colored taxonomy (Forest package)
9. **tree** - For showing general tree diagrams with TikZ
10. **mindmap** - For showing radial concept maps (TikZ mindmap library)
11. **tiny_tree** - For showing compact hierarchical structures
12. **conceptual_comparison** - For showing overlapping concepts (Venn-like)

### Advanced Tables (for high-quality academic presentation):
13. **icon_description_table** - Table with icons and bold titles (like Table 2 in example)
14. **grouped_category_table** - Table with colored group headers and multi-level structure (like Table 4/5)
15. **taxonomy_matrix_table** - Matrix table with checkmarks and diagonal header (like Table 1)
16. **nested_multirow_table** - Complex table with nested rows and multirow cells (like Table 2)
17. **colored_header_table** - Table with colored header bar and nested structure (like Table 3)
18. **benchmark_results_table** - Benchmark table with multi-level headers and precise alignment (like Table 5)
19. **labeled_badge_table** - Table with colored letter badges (B, N, W) for datasets (like Table 3/4)

### Text Boxes (Callout Boxes) - HIGHLY RECOMMENDED:
13. **callout_box** - For highlighting key information in visually appealing boxes
   - **IMPORTANT**: This is one of the most versatile and useful visual elements!
   - Subtypes (choose based on content):
     * **numbered_list**: For "Three Types of...", "Major Categories", numbered items with explanations
     * **key_questions**: For research questions, key questions to address
     * **concept_list**: For multiple related concepts with descriptions (like "Three Major Memory Forms")
     * **definition**: For formal definitions of key terms
     * **key_insights**: For main findings, takeaways, important observations
     * **summary**: For chapter/section summaries
     * **example**: For concrete examples with input/output
     * **evidence**: For important quotes from literature
     * **note**: For clarifications or additional information
     * **tip**: For best practices or recommendations
     * **warning**: For important caveats or warnings

## Visual Element Selection Guide

| Element Type | Best For | Example Use Case |
|--------------|----------|------------------|
| timeline | Historical evolution | "Development of LLMs from 2017-2024" |
| taxonomy_tree | Classification | "Taxonomy of tool-use methods" |
| flowchart | Process/workflow | "Training pipeline steps" |
| architecture | System structure | "Model architecture layers" |
| dataflow | Data transformation | "Data flow in RAG system" |
| pipeline | Sequential stages | "Function calling pipeline" |
| performance_chart | Metric comparison | "Accuracy comparison across models" |
| structure | Survey overview | "Survey structure with colored categories" |
| tree | Hierarchical concepts | "Method classification tree" |
| mindmap | Concept relationships | "Research topic mindmap" |
| tiny_tree | Small hierarchies | "Compact method taxonomy" |
| conceptual_comparison | Overlapping concepts | "Comparison of Agent Memory vs RAG vs LLM" |
| icon_description_table | Categorized descriptions | "Prompt types with icons and explanations" |
| grouped_category_table | Grouped datasets/methods | "Datasets grouped by task type" |
| taxonomy_matrix_table | Feature matrix | "Input-Output modality matrix" |
| nested_multirow_table | Complex relationships | "Core components and tasks mapping" |
| colored_header_table | Hierarchical strategies | "Training strategies and methods" |
| benchmark_results_table | Performance results | "Model performance on multiple metrics" |
| labeled_badge_table | Labeled datasets | "Datasets with sensor type badges" |
| **callout_box** | **VERSATILE - Many uses** | See detailed guide below |

## IMPORTANT: When to use callout_box (HIGHLY RECOMMENDED)

**callout_box is extremely versatile and should be used frequently!** Choose the appropriate subtype:

| Subtype | Best For | Example |
|---------|----------|---------|
| numbered_list | Categorized items (2-6 items) | "Three Types of Memory", "Four Key Challenges" |
| key_questions | Research questions | "Key Questions This Survey Addresses" |
| concept_list | Related concepts with descriptions | "Three Major Memory Forms" with explanations |
| definition | Formal definitions | "Definition of Token-level Memory" |
| key_insights | Main findings/takeaways | "Key Insights from This Section" |
| summary | Section summaries | "Summary of Methodology" |
| example | Concrete examples | "Example: Chain-of-Thought Prompting" |
| evidence | Literature quotes | Important findings from cited papers |
| note | Additional information | Clarifications, side notes |
| tip | Best practices | Recommendations for practitioners |
| warning | Caveats/warnings | Important limitations to note |

**Recommended usage:**
- Use callout_box in ANY section that has important categorizations, definitions, or key points
- Especially good for sections that introduce "Three types of...", "Major categories...", "Key concepts..."
- Also excellent for highlighting research questions, definitions, and important findings

## Planning Principles
1. **MANDATORY Structure Diagram**: You MUST include exactly ONE "structure" element to show the survey's overall organization
2. **Minimum Requirement**: You MUST plan at least 4 visual elements total (1 structure + 3 others)
3. **NO Duplicates**: Each element type can only be used ONCE - all types must be different
4. **AVOID TOPIC OVERLAP**: Do NOT generate visual elements that cover the same topics as existing tables or figures listed above
5. **Quality over Quantity**: Only suggest visual elements that truly enhance understanding
6. **Strategic Placement**: Place visual elements where they add the most value
7. **One per Section**: At most one visual element per section
8. **Prefer Technical Diagrams**: For methodology sections, prefer dataflow/pipeline/architecture over simple flowcharts
9. **Performance Charts**: Use for evaluation/benchmark sections to show comparative results
10. **Use Advanced Tables**: For complex data, prefer advanced table types (grouped_category_table, benchmark_results_table, etc.) over simple comparison_table
11. **HIGHLY RECOMMEND Callout Boxes**: Use callout_box for ANY section with:
    - Categorizations ("Three types of...", "Major categories...")
    - Key definitions or concepts
    - Research questions
    - Important findings or insights
    - Section summaries
    Choose the appropriate subtype: numbered_list, key_questions, concept_list, definition, key_insights, summary, etc.
12. **Complementary Content**: Choose topics that COMPLEMENT (not duplicate) existing visual elements

## Output Format
Output a JSON object with your planning decisions (MINIMUM 4 elements, MAXIMUM 5 elements):
```json
{{
    "total_elements": 4,
    "reasoning": "Brief explanation of the overall strategy",
    "planned_elements": [
        {{
            "section_no": "1",
            "element_type": "structure",
            "reason": "MANDATORY: Survey structure overview showing the organization of topics",
            "priority": 10
        }},
        {{
            "section_no": "2",
            "element_type": "pipeline",
            "reason": "This section describes the function calling pipeline stages",
            "priority": 9
        }},
        {{
            "section_no": "3",
            "element_type": "taxonomy_tree",
            "reason": "This section categorizes different methods",
            "priority": 8
        }},
        {{
            "section_no": "3.1",
            "element_type": "callout_box",
            "reason": "This section introduces 'Three Types of Memory' - perfect for numbered_list callout box",
            "priority": 8
        }}
    ]
}}
```

**CRITICAL REQUIREMENTS**:
- You MUST include exactly ONE "structure" element (usually in section 1 or 2) - this is MANDATORY
- You MUST select at least 4 elements total (1 structure + 3 others), maximum 5 elements
- Each element_type can only appear ONCE - NO DUPLICATES allowed
- Prioritize DIVERSE element types from: structure, pipeline, taxonomy_tree, flowchart, architecture, dataflow, timeline, performance_chart, callout_box, tree, mindmap
- For methodology sections, consider dataflow/pipeline/architecture diagrams
- For evaluation sections, consider performance_chart
- **STRONGLY RECOMMEND callout_box** for sections that:
  * Introduce categorizations ("Three types of...", "Major categories...")
  * Define key concepts or terms
  * Present research questions
  * Summarize important findings
  * List key insights or takeaways
  Choose appropriate subtype: numbered_list, key_questions, concept_list, definition, key_insights, summary, etc.

Please output ONLY JSON, no other content.
"""
        
        # 尝试多次调用LLM，增加成功率
        max_retries = 5
        last_error = None
        last_response = None
        
        for attempt in range(max_retries):
            # 第一次尝试使用原始prompt，后续尝试使用简化版本
            if attempt == 0:
                current_prompt = prompt
                temp = 0.3
            elif attempt == 1:
                current_prompt = prompt
                temp = 0.5
            elif attempt == 2:
                # 使用简化的prompt
                current_prompt = self._build_simplified_planning_prompt(sections_summary, survey_topic)
                temp = 0.3
            else:
                # 如果有上次的响应，尝试让LLM修复它
                if last_response:
                    current_prompt = self._build_json_repair_prompt(last_response, last_error)
                    temp = 0.2
                else:
                    current_prompt = self._build_simplified_planning_prompt(sections_summary, survey_topic)
                    temp = 0.4
            
            response = self._call_llm(current_prompt, temperature=temp)
            
            if not response:
                logger.warning(f"Attempt {attempt + 1}/{max_retries}: Failed to get global planning response (empty response)")
                last_error = "Empty response from LLM"
                continue
            
            last_response = response
            
            try:
                plan = self._extract_and_parse_json(response)
                planned_elements = plan.get("planned_elements", [])
                
                # 验证并补充规划结果
                plan = self._validate_and_enhance_plan(plan, sections)
                
                logger.info(f"Global planning result: {plan.get('total_elements', 0)} elements planned")
                logger.info(f"Planning reasoning: {plan.get('reasoning', 'N/A')}")
                
                return plan
                
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries}: Failed to parse planning response: {e}")
                logger.debug(f"Response content (first 500 chars): {response[:500] if response else 'None'}")
                last_error = str(e)
                continue
        
        # 所有重试都失败，最后一次尝试使用超简化的直接生成方式
        logger.error(f"All {max_retries} attempts failed. Last error: {last_error}")
        logger.info("Attempting final fallback with direct JSON generation...")
        
        return self._generate_plan_with_direct_llm(sections, survey_topic)
    
    def _build_simplified_planning_prompt(self, sections_summary: List[Dict], survey_topic: str) -> str:
        """构建简化版的规划提示词，更强调JSON格式"""
        # 只保留必要的章节信息
        simple_sections = []
        for s in sections_summary[:10]:  # 限制章节数量
            simple_sections.append({
                "section_no": s["section_no"],
                "title": s["title"][:50]  # 限制标题长度
            })
        
        return f"""You are a JSON generator. Your task is to output a valid JSON object for visual element planning.

## Survey Topic
{survey_topic}

## Available Sections
{json.dumps(simple_sections, indent=2)}

## Available Element Types
- structure (MANDATORY - must include exactly one)
- pipeline
- taxonomy_tree
- flowchart
- architecture
- timeline
- conceptual_comparison
- callout_box

## STRICT REQUIREMENTS
1. Output ONLY valid JSON - no explanations, no markdown formatting
2. Must include exactly ONE "structure" element
3. Must include 4-5 elements total
4. Each element_type can only appear ONCE

## EXACT OUTPUT FORMAT (copy this structure):
{{"total_elements": 4, "reasoning": "Brief strategy", "planned_elements": [{{"section_no": "1", "element_type": "structure", "reason": "Survey overview", "priority": 10}}, {{"section_no": "2", "element_type": "pipeline", "reason": "Process description", "priority": 9}}, {{"section_no": "3", "element_type": "taxonomy_tree", "reason": "Classification", "priority": 8}}, {{"section_no": "4", "element_type": "callout_box", "reason": "Key insights", "priority": 7}}]}}

Output your JSON now (no other text):"""

    def _build_json_repair_prompt(self, invalid_response: str, error_msg: str) -> str:
        """构建JSON修复提示词"""
        # 截取响应的前1000个字符
        truncated_response = invalid_response[:1000] if len(invalid_response) > 1000 else invalid_response
        
        return f"""The following JSON is invalid and needs to be fixed.

## Error Message
{error_msg}

## Invalid JSON (may be truncated)
{truncated_response}

## Required Format
The output must be a valid JSON object with this exact structure:
{{"total_elements": 4, "reasoning": "string", "planned_elements": [{{"section_no": "1", "element_type": "structure", "reason": "string", "priority": 10}}, {{"section_no": "2", "element_type": "pipeline", "reason": "string", "priority": 9}}, {{"section_no": "3", "element_type": "taxonomy_tree", "reason": "string", "priority": 8}}, {{"section_no": "4", "element_type": "callout_box", "reason": "string", "priority": 7}}]}}

## Rules
1. Output ONLY the fixed JSON - no explanations
2. Must have "structure" as one element_type
3. Must have 4-5 planned_elements
4. All strings must be properly escaped
5. No trailing commas

Output the fixed JSON now:"""

    def _generate_plan_with_direct_llm(
        self,
        sections: List[Tuple[str, str, str]],
        survey_topic: str
    ) -> Dict[str, Any]:
        """
        使用更直接的方式让LLM生成规划（最后的后备方案）
        
        这个方法使用分步生成的方式，先让LLM选择章节，再生成完整JSON。
        如果LLM调用也失败，则使用基于关键词分析的默认规划。
        """
        logger.info("Using direct LLM generation as final fallback...")
        
        # 获取可用的章节编号
        section_numbers = [s[0] for s in sections[:10]]
        
        # 第一步：让LLM选择4个章节
        step1_prompt = f"""Select 4 section numbers for visual elements from this list: {section_numbers}

Rules:
- First selection MUST be for "structure" diagram
- Output ONLY 4 numbers separated by commas
- Example output: 1,2,3,5

Your selection:"""
        
        step1_response = self._call_llm(step1_prompt, temperature=0.2)
        
        # 解析选择的章节
        selected_sections = []
        if step1_response:
            # 提取数字
            import re
            numbers = re.findall(r'\d+(?:\.\d+)?', step1_response)
            for num in numbers[:4]:
                if num in section_numbers or num.split('.')[0] in [s.split('.')[0] for s in section_numbers]:
                    selected_sections.append(num)
        
        # 如果解析失败，使用基于关键词分析的默认规划
        if len(selected_sections) < 4:
            logger.info("LLM selection failed, using keyword-based default planning...")
            return self._generate_default_plan(sections)
        
        # 第二步：为每个选择的章节分配元素类型
        element_types = ["structure", "pipeline", "taxonomy_tree", "conceptual_comparison", "callout_box"]
        
        planned_elements = []
        for i, section_no in enumerate(selected_sections[:4]):
            elem_type = element_types[i] if i < len(element_types) else "flowchart"
            planned_elements.append({
                "section_no": section_no,
                "element_type": elem_type,
                "reason": f"Auto-assigned for section {section_no}",
                "priority": 10 - i
            })
        
        plan = {
            "total_elements": len(planned_elements),
            "reasoning": "Generated using direct LLM selection fallback",
            "planned_elements": planned_elements
        }
        
        # 验证并增强
        plan = self._validate_and_enhance_plan(plan, sections)
        
        logger.info(f"Direct LLM plan created with {len(plan.get('planned_elements', []))} elements")
        
        return plan
    
    def _generate_default_plan(
        self,
        sections: List[Tuple[str, str, str]]
    ) -> Dict[str, Any]:
        """
        基于关键词分析生成默认的视觉元素规划（完全不依赖LLM的兜底方案）
        
        这是最后的兜底方案，当所有LLM调用都失败时使用。
        通过分析章节内容中的关键词来决定最合适的视觉元素类型。
        
        Args:
            sections: 章节列表 [(section_no, section_title, section_content), ...]
            
        Returns:
            规划结果
        """
        logger.info("Generating default plan based on keyword analysis...")
        
        # 定义元素类型和对应的关键词
        element_keywords = {
            "pipeline": ["pipeline", "process", "workflow", "step", "stage", "procedure", "training", "inference"],
            "taxonomy_tree": ["category", "classification", "taxonomy", "type", "class", "hierarchy", "categorize"],
            "architecture": ["architecture", "structure", "framework", "model", "layer", "component", "module"],
            "flowchart": ["flow", "decision", "branch", "condition", "if", "then", "else"],
            "timeline": ["history", "evolution", "development", "year", "2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024", "milestone"],
            "dataflow": ["data", "input", "output", "transform", "processing", "stream"],
            "performance_chart": ["performance", "benchmark", "evaluation", "result", "accuracy", "score", "comparison"],
            "benchmark_results_table": ["benchmark", "result", "performance", "metric", "score", "accuracy", "evaluation"],
            "grouped_category_table": ["dataset", "benchmark", "collection", "group", "category"],
            "taxonomy_matrix_table": ["matrix", "feature", "capability", "support", "check", "cross"],
            "nested_multirow_table": ["component", "module", "part", "sub-task", "hierarchical"],
            "colored_header_table": ["strategy", "approach", "method", "technique", "training"],
            "labeled_badge_table": ["dataset", "source", "type", "scale", "sensor", "modality"],
            "icon_description_table": ["prompt", "instruction", "command", "template", "type", "category"],
            "callout_box": [
                "conclusion", "summary", "insight", "finding", "key", "important", "note", "observation",
                "definition", "define", "term", "concept", "question", "challenge", "issue", "problem",
                "example", "instance", "case", "illustration", "tip", "recommendation", "practice",
                "three types", "major types", "categories", "forms", "warning", "caveat", "limitation"
            ],
        }
        
        planned_elements = []
        used_types = set()
        used_sections = set()
        
        # 1. 首先添加必须的 structure 图（选择第一个主章节）
        structure_section = None
        for section_no, section_title, _ in sections:
            if "." not in section_no:  # 主章节
                structure_section = section_no
                break
        
        if structure_section is None and sections:
            structure_section = sections[0][0]
        
        if structure_section:
            planned_elements.append({
                "section_no": structure_section,
                "element_type": "structure",
                "reason": "MANDATORY: Survey structure overview (default planning)",
                "priority": 10
            })
            used_types.add("structure")
            used_sections.add(structure_section)
        
        # 2. 为其他章节分配最合适的元素类型
        for section_no, section_title, section_content in sections:
            if section_no in used_sections:
                continue
            
            if len(planned_elements) >= 5:  # 最多5个元素
                break
            
            # 计算每种元素类型的匹配分数
            best_type = None
            best_score = 0
            
            content_lower = (section_content + " " + section_title).lower()
            
            for elem_type, keywords in element_keywords.items():
                if elem_type in used_types:
                    continue
                
                score = sum(1 for kw in keywords if kw in content_lower)
                if score > best_score:
                    best_score = score
                    best_type = elem_type
            
            # 如果找到匹配的类型且分数大于0
            if best_type and best_score > 0:
                planned_elements.append({
                    "section_no": section_no,
                    "element_type": best_type,
                    "reason": f"Auto-selected based on keyword analysis (score: {best_score})",
                    "priority": 9 - len(planned_elements)
                })
                used_types.add(best_type)
                used_sections.add(section_no)
        
        # 3. 如果元素数量不足4个，补充更多
        fallback_types = ["pipeline", "taxonomy_tree", "flowchart", "callout_box", "architecture"]
        
        for section_no, section_title, _ in sections:
            if section_no in used_sections:
                continue
            
            if len(planned_elements) >= 4:
                break
            
            # 选择一个未使用的类型
            for elem_type in fallback_types:
                if elem_type not in used_types:
                    planned_elements.append({
                        "section_no": section_no,
                        "element_type": elem_type,
                        "reason": "Auto-added to meet minimum requirement (default planning)",
                        "priority": 7 - len(planned_elements)
                    })
                    used_types.add(elem_type)
                    used_sections.add(section_no)
                    break
        
        plan = {
            "total_elements": len(planned_elements),
            "reasoning": "Generated using keyword-based default planning (LLM fallback)",
            "planned_elements": planned_elements
        }
        
        logger.info(f"Default plan created with {len(planned_elements)} elements: {[e['element_type'] for e in planned_elements]}")
        
        return plan
    
    def _validate_and_enhance_plan(
        self,
        plan: Dict[str, Any],
        sections: List[Tuple[str, str, str]]
    ) -> Dict[str, Any]:
        """
        验证并增强规划结果，确保满足最低要求
        
        要求：
        1. 必须包含一个 structure 图
        2. 至少 4 个视觉元素（1 structure + 3 其他）
        3. 类型不重复
        
        Args:
            plan: 原始规划结果
            sections: 章节列表
            
        Returns:
            增强后的规划结果
        """
        planned_elements = plan.get("planned_elements", [])
        
        # 获取已使用的类型和章节
        used_types = set()
        used_sections = set()
        for elem in planned_elements:
            used_types.add(elem.get("element_type", ""))
            used_sections.add(elem.get("section_no", ""))
        
        # 检查是否有 structure
        has_structure = "structure" in used_types
        
        # 如果没有 structure，添加一个
        if not has_structure:
            # 找一个合适的章节（优先选择第一个主章节）
            structure_section = None
            for section_no, section_title, _ in sections:
                if section_no not in used_sections and "." not in section_no:
                    structure_section = section_no
                    break
            
            if structure_section is None and sections:
                # 如果所有主章节都被占用，选择第一个可用的
                for section_no, _, _ in sections:
                    if section_no not in used_sections:
                        structure_section = section_no
                        break
            
            if structure_section:
                planned_elements.insert(0, {
                    "section_no": structure_section,
                    "element_type": "structure",
                    "reason": "MANDATORY: Survey structure overview showing the organization of topics",
                    "priority": 10
                })
                used_types.add("structure")
                used_sections.add(structure_section)
                logger.info(f"Added mandatory structure element to section {structure_section}")
        
        # 检查是否满足最低数量要求（至少4个）
        min_elements = getattr(self, 'MIN_TOTAL_ELEMENTS', 4)
        
        # 可用的元素类型（按优先级排序）
        available_types = [
            ("pipeline", ["pipeline", "process", "workflow", "step"]),
            ("taxonomy_tree", ["category", "classification", "taxonomy", "type"]),
            ("architecture", ["architecture", "structure", "framework", "model", "layer"]),
            ("flowchart", ["flow", "process", "procedure"]),
            ("timeline", ["history", "evolution", "development", "year"]),
            ("dataflow", ["data", "input", "output", "transform"]),
            ("performance_chart", ["performance", "benchmark", "evaluation", "result"]),
            ("benchmark_results_table", ["benchmark", "result", "performance", "metric"]),
            ("grouped_category_table", ["dataset", "benchmark", "collection"]),
            ("taxonomy_matrix_table", ["matrix", "feature", "capability"]),
            ("conceptual_comparison", ["comparison", "overlap", "intersection", "relationship", "versus", "vs"]),
            ("callout_box", ["conclusion", "summary", "insight", "finding"]),
        ]
        
        # 如果元素数量不足，补充更多
        while len(planned_elements) < min_elements:
            added = False
            
            for elem_type, keywords in available_types:
                if elem_type in used_types:
                    continue
                
                # 找一个合适的章节
                best_section = None
                best_score = 0
                
                for section_no, section_title, section_content in sections:
                    if section_no in used_sections:
                        continue
                    
                    # 计算匹配分数
                    score = sum(1 for kw in keywords if kw in section_content.lower() or kw in section_title.lower())
                    if score > best_score:
                        best_score = score
                        best_section = section_no
                
                if best_section:
                    planned_elements.append({
                        "section_no": best_section,
                        "element_type": elem_type,
                        "reason": f"Auto-added to meet minimum requirement of {min_elements} elements",
                        "priority": 7 - len(planned_elements)  # 递减优先级
                    })
                    used_types.add(elem_type)
                    used_sections.add(best_section)
                    logger.info(f"Auto-added {elem_type} element to section {best_section}")
                    added = True
                    break
            
            if not added:
                # 如果没有更多可用的类型或章节，退出循环
                logger.warning(f"Could not add more elements, current count: {len(planned_elements)}")
                break
        
        # 去除重复类型（保留优先级最高的）
        seen_types = {}
        unique_elements = []
        for elem in sorted(planned_elements, key=lambda x: x.get("priority", 0), reverse=True):
            elem_type = elem.get("element_type", "")
            if elem_type not in seen_types:
                seen_types[elem_type] = True
                unique_elements.append(elem)
        
        plan["planned_elements"] = unique_elements
        plan["total_elements"] = len(unique_elements)
        
        return plan

    def _generate_element_for_section(
        self,
        section_no: str,
        section_title: str,
        section_content: str,
        element_type: str,
        survey_topic: str,
        year_range: tuple = None
    ) -> VisualElementDecision:
        """
        为指定章节生成指定类型的视觉元素
        
        Args:
            section_no: 章节编号
            section_title: 章节标题
            section_content: 章节内容
            element_type: 元素类型
            survey_topic: 综述主题
            year_range: 年份范围 (start_year, end_year)，用于时间线生成
            
        Returns:
            视觉元素决策
        """
        # 构建年份范围提示（用于时间线）
        year_hint = ""
        if element_type == "timeline" and year_range:
            start_year, end_year = year_range
            current_year = datetime.now().year   # 当前年份
            if end_year and end_year >= current_year:
                year_hint = f"""
## IMPORTANT: Year Range
The survey covers research from {start_year} to {end_year}.
**CRITICAL: You must extract the LATEST available events.**
If the text mentions events in {current_year} or {current_year - 1}, they MUST be included.
Do not arbitrarily cut off the timeline early.
"""
        
        prompt = f"""You are an academic survey writing expert. Generate the data for a {element_type} based on the following section content.

## Survey Topic
{survey_topic}
{year_hint}
## Section
- Number: {section_no}
- Title: {section_title}

## Section Content
{section_content[:3000]}

## Task
Generate the data for a **{element_type}** that best represents the key information in this section.
**IMPORTANT: All content MUST be in ENGLISH.**
**IMPORTANT: For timelines, include the most recent developments mentioned in the content, up to the current year.**

## Output Format
"""
        
        # 根据元素类型添加具体的输出格式要求
        if element_type == "comparison_table":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Table caption in English",
    "headers": ["Column1", "Column2", "Column3", "Column4"],
    "rows": [
        ["Row1Col1", "Row1Col2", "Row1Col3", "Row1Col4"],
        ["Row2Col1", "Row2Col2", "Row2Col3", "Row2Col4"]
    ]
}
```
Provide 4-8 rows of actual data extracted from the content.
"""
        elif element_type == "summary_table":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Table caption in English",
    "headers": ["Method", "Key Features", "Advantages", "Limitations"],
    "rows": [
        ["Method1", "Features", "Pros", "Cons"],
        ["Method2", "Features", "Pros", "Cons"]
    ]
}
```
Provide 4-6 rows of actual data extracted from the content.
"""
        elif element_type == "timeline":
            # 1. 获取当前年份
            current_year = datetime.now().year
            
            # 2. 准备动态变量
            year_example_hint = ""
            
            # 为了让 JSON 示例更有说服力，我们动态生成示例中的“近几年”
            # 比如今年是2025，示例里就会显示 2024 和 2025
            ex_year_recent = current_year
            ex_year_prev = current_year - 1
            if year_range:
                start_year, end_year = year_range
                
                # 动态生成 "2023, 2024, and 2025"
                # 取最近3年 (包含今年)
                recent_years_list = [str(y) for y in range(current_year - 2, current_year + 1)]
                recent_years_str = ", ".join(recent_years_list[:-1]) + " and " + recent_years_list[-1]
                
                # 动态计算 "不要停在 2022" -> current_year - 3
                cutoff_year = current_year - 3
                year_example_hint = f"""
**CRITICAL**: The timeline should cover developments from {start_year} to {end_year}.
Include recent events from {recent_years_str} if mentioned in the content.
Do NOT stop at {cutoff_year} - the field has continued to evolve!
"""
            # 3. 组装 Prompt
            # 注意：在 f-string 中，原本 JSON 的大括号 { } 需要写成双大括号 {{ }} 来转义
            # 只有我们要插入变量的地方才用单大括号 {ex_year_prev}
            prompt += f"""
Output a JSON object:
```json
{{
    "caption": "Timeline caption in English",
    "items": [
        {{"year": "2017", "event": "Historical context (example)"}},
        {{"year": "2018", "event": "Key milestone (example)"}},
        {{"year": "{ex_year_prev}", "event": "Recent development"}},
        {{"year": "{ex_year_recent}", "event": "Latest advancement"}}
    ]
}}
```
{year_example_hint}
"""
            
        elif element_type == "taxonomy_tree":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Taxonomy caption in English",
    "root": "Root Category",
    "children": [
        {"name": "Category1", "children": ["Sub1", "Sub2"]},
        {"name": "Category2", "children": ["Sub3", "Sub4"]}
    ]
}
```
Provide a taxonomy with 2-4 main categories and 2-3 subcategories each.
"""
        elif element_type == "flowchart":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Flowchart caption in English",
    "nodes": [
        {"id": "1", "type": "start", "text": "Start"},
        {"id": "2", "type": "process", "text": "Step 1"},
        {"id": "3", "type": "process", "text": "Step 2"},
        {"id": "4", "type": "end", "text": "End"}
    ],
    "edges": [
        {"from": "1", "to": "2"},
        {"from": "2", "to": "3"},
        {"from": "3", "to": "4"}
    ]
}
```
Provide 4-6 nodes representing the main steps in the process.
"""
        elif element_type == "architecture":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Architecture caption in English",
    "layers": [
        {"name": "Layer1", "components": ["Comp1", "Comp2"], "color": "red!20"},
        {"name": "Layer2", "components": ["Comp3", "Comp4"], "color": "blue!20"}
    ]
}
```
Provide 2-4 layers with 2-4 components each.
"""
        elif element_type == "dataflow":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Data Flow Diagram caption in English",
    "nodes": [
        {"id": "1", "type": "input", "text": "User Query"},
        {"id": "2", "type": "process", "text": "Query Processing"},
        {"id": "3", "type": "storage", "text": "Knowledge Base"},
        {"id": "4", "type": "process", "text": "Response Generation"},
        {"id": "5", "type": "output", "text": "Final Response"}
    ],
    "flows": [
        {"from": "1", "to": "2", "label": "raw input"},
        {"from": "2", "to": "3", "label": "retrieve"},
        {"from": "3", "to": "4", "label": "context"},
        {"from": "4", "to": "5", "label": "output"}
    ]
}
```
Node types: input (green trapezoid), output (red trapezoid), process (blue rectangle), storage (orange cylinder).
Provide 4-8 nodes showing the data flow in the system.
"""
        elif element_type == "pipeline":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Pipeline Diagram caption in English",
    "stages": [
        {"name": "Stage 1", "description": "Brief description"},
        {"name": "Stage 2", "description": "Brief description"},
        {"name": "Stage 3", "description": "Brief description"},
        {"name": "Stage 4", "description": "Brief description"}
    ]
}
```
Provide 4-6 sequential stages representing the pipeline process.
Each stage should have a short name and a brief description.
"""
        elif element_type == "performance_chart":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Performance Comparison caption in English",
    "methods": ["Method1", "Method2", "Method3", "Method4"],
    "metrics": ["Accuracy", "F1-Score", "Latency"],
    "values": [
        [85.2, 82.1, 45.3],
        [87.5, 84.2, 52.1],
        [82.3, 80.5, 38.2],
        [89.1, 86.3, 61.5]
    ]
}
```
- methods: List of method/model names being compared (max 5)
- metrics: List of evaluation metrics (max 4)
- values: 2D array where values[i][j] is the score of method i on metric j
- All values should be in 0-100 range for proper visualization
Provide actual performance data extracted from the content.
"""
        elif element_type == "structure":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Survey Structure caption in English",
    "root": "Survey Topic",
    "children": [
        {
            "name": "Category 1",
            "children": ["Subcat 1.1", "Subcat 1.2"]
        },
        {
            "name": "Category 2",
            "children": [
                {
                    "name": "Subcat 2.1",
                    "methods": ["Method A [1]", "Method B [2]", "Method C [3]"]
                },
                {
                    "name": "Subcat 2.2",
                    "refs": "Ref1, Ref2"
                }
            ]
        }
    ]
}
```
Provide a hierarchical structure with 3-6 main categories.
**IMPORTANT**: For leaf nodes, use the "methods" field to list specific methods or papers (e.g., ["GPT-4 [1]", "Claude [2]"]). This will be displayed as a list next to the node.
"""
        elif element_type == "tree":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Tree Diagram caption in English",
    "root": "Root Node",
    "children": [
        {
            "name": "Branch 1",
            "children": ["Leaf 1", "Leaf 2"]
        },
        "Branch 2"
    ]
}
```
Provide a tree structure with 2-4 main branches.
"""
        elif element_type == "mindmap":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Mindmap caption in English",
    "root": "Central Concept",
    "children": [
        {
            "name": "Concept 1",
            "children": ["Detail 1", "Detail 2"]
        },
        "Concept 2"
    ]
}
```
Provide a radial structure with 4-6 main concepts.
"""
        elif element_type == "tiny_tree":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Compact Tree caption in English",
    "root": "Root",
    "children": [
        {
            "name": "Node A",
            "children": ["A1", "A2"]
        },
        "Node B"
    ]
}
```
Provide a small hierarchy with 2-3 branches.
"""
        elif element_type == "conceptual_comparison":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Conceptual Comparison caption in English",
    "center_label": "Main Concept",
    "left_label": "Concept A",
    "right_label": "Concept B",
    "bottom_label": "Concept C",
    "center_left_text": "Overlap A-Main",
    "center_right_text": "Overlap B-Main",
    "center_bottom_text": "Overlap C-Main",
    "annotations": {
        "center": {"title": "Main Concept", "items": ["Feature 1", "Feature 2"]},
        "left": {"title": "Concept A", "items": ["Feature 3", "Feature 4"]},
        "right": {"title": "Concept B", "items": ["Feature 5", "Feature 6"]},
        "bottom": {"title": "Concept C", "items": ["Feature 7", "Feature 8"]}
    }
}
```
Provide data for a Venn-like diagram comparing the main concept with 3 other related concepts.
"""
        elif element_type == "icon_description_table":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Table caption in English",
    "header_left": "Prompt Type",
    "header_right": "Explanations",
    "rows": [
        {"icon": "📝", "title": "System Prompt", "description": "Text templates designed to interact with LLMs..."},
        {"icon": "💡", "title": "Instructions", "description": "Commands provided by humans..."}
    ]
}
```
Provide 4-8 rows. Use appropriate emoji icons for each item.
"""
        elif element_type == "grouped_category_table":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Table caption in English",
    "headers": ["Dataset", "Year", "Type", "Scale", "Description"],
    "groups": [
        {
            "name": "Vision-Action Datasets",
            "color": "teal",
            "rows": [
                ["BDD100K", "2020", "Real", "120M", "Trajectory prediction"],
                ["nuScenes", "2020", "Real", "1.4M", "Perception"]
            ]
        },
        {
            "name": "Vision-Language Datasets",
            "color": "cyan",
            "rows": [
                ["BDD-X", "2018", "Real", "8.4M", "Captioning"]
            ]
        }
    ]
}
```
Provide 2-4 groups with 2-6 rows each. Available colors: teal, cyan, blue, orange, purple, red.
"""
        elif element_type == "taxonomy_matrix_table":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Table caption in English",
    "row_header": "Input",
    "col_headers": ["Text", "Code", "Image", "Video"],
    "row_groups": [
        {
            "name": "Uni-Modal",
            "rows": [
                {"name": "Text", "ref": "§3.1.1", "checks": [true, true, false, true]},
                {"name": "Image", "ref": "§3.1.2", "checks": [true, false, false, false]}
            ]
        }
    ],
    "footnote": "* Video may be considered a composite of audio and image frames."
}
```
Provide a matrix showing relationships/capabilities. checks array length must match col_headers length.
"""
        elif element_type == "nested_multirow_table":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Table caption in English",
    "headers": ["Modality", "Backbone", "", "Task", "Examples"],
    "sub_headers": ["", "Retriever", "Generator", "", ""],
    "rows": [
        {
            "modality": "T+I→T",
            "sub_rows": [
                {"retriever": "CLIP", "generator": "GPT", "task": "Visual QA", "examples": "MuRAG, RA-VQA"},
                {"retriever": "", "generator": "LLaVA", "task": "Image Caption", "examples": "Re-ViLM"}
            ]
        }
    ]
}
```
Provide nested data structure. sub_headers is optional (leave empty strings for merged columns).
"""
        elif element_type == "colored_header_table":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Table caption in English",
    "header_color": "blue",
    "headers": ["Training Strategy", "Methods"],
    "rows": [
        {"strategy": "Parameter-Frozen", "methods": "PICa, TIGeR, RAR..."},
        {
            "strategy": "Parameter-Trainable",
            "sub_rows": [
                {"sub_strategy": "Modular Training", "methods": "VisRAG, DocPrompt..."},
                {"sub_strategy": "End-to-End", "methods": "MuRAG, RA-VQA..."}
            ]
        }
    ]
}
```
Provide hierarchical data. Available colors: blue, teal, cyan, orange, purple.
"""
        elif element_type == "benchmark_results_table":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Table caption in English",
    "headers_level1": ["Model", "Year", "Input", "Vision", "Language", "Action", "L2↓", "", "", "", "CR↓", "", "", ""],
    "headers_level2": ["", "", "", "", "", "", "1s", "2s", "3s", "Avg.", "1s", "2s", "3s", "Avg."],
    "groups": [
        {
            "name": "Vision-Action Models",
            "color": "green",
            "rows": [
                ["ST-P3", "2022", "📷", "EfficientNet", "-", "REG", "1.33", "2.11", "2.90", "2.11", "0.23", "0.62", "1.27", "0.71"]
            ]
        }
    ]
}
```
Provide benchmark data. Use empty strings in headers_level1 for columns spanned by headers_level2 (or vice versa).
"""
        elif element_type == "labeled_badge_table":
            prompt += """
Output a JSON object:
```json
{
    "caption": "Table caption in English",
    "headers": ["Dataset", "Year", "Sensor", "Type", "Scale", "Tasks"],
    "badge_colors": {"B": "blue", "N": "orange", "W": "green", "A": "red"},
    "groups": [
        {
            "name": "Vision-Action Datasets",
            "color": "teal",
            "rows": [
                {"badge": "B", "data": ["BDD100K", "2020", "📷", "Real", "120M", "Percept."]},
                {"badge": "N", "data": ["nuScenes", "2020", "📷🔊", "Real", "1.4M", "Percept."]}
            ]
        }
    ]
}
```
Provide data with badges (single letter like B, N, W). badge_colors maps letters to colors.
"""
        elif element_type == "callout_box":
            prompt += """
Output a JSON object for a callout box. Choose the most appropriate box_type based on the content.

## CRITICAL REQUIREMENTS FOR KEY INSIGHTS:
**Every insight MUST be grounded in the actual content and include citations where possible.**
- Do NOT generate vague or generic statements
- Each insight should be specific, measurable, and verifiable
- Include citation keys in square brackets when referencing specific findings, e.g., "LLMs achieve 95% accuracy on benchmark X [Author2024]"
- If no specific citation is available, ensure the insight is directly derived from the section content

## Available Box Types:

### 1. **key_insights** - Highlighting main findings (bullet list with citations)
**IMPORTANT: Each insight MUST be evidence-based and include citations when possible**
```json
{
    "box_type": "key_insights",
    "title": "Key Insights",
    "items": [
        "Transformer-based models achieve state-of-the-art performance on document understanding tasks, with accuracy improvements of 15-20% over CNN-based approaches [Author2023, Author2024]",
        "Multi-modal pre-training significantly improves cross-modal alignment, as demonstrated by LayoutLM achieving 94.1% F1 on FUNSD benchmark [Xu2020]",
        "Visual features contribute 30% of the performance gain in document VQA tasks, highlighting the importance of image encoders [Li2022]"
    ]
}
```

### 2. **numbered_list** - Categorized items with numbered circles (like "Three Types of...")
```json
{
    "box_type": "numbered_list",
    "title": "Three Types of Experiential Memory",
    "items": [
        "Case-based Memory stores minimally processed records of historical episodes, enabling retrieval of similar past experiences [Park2023]",
        "Strategy-based Memory distills transferable reasoning patterns and workflows from successful problem-solving instances [Shinn2023]",
        "Skill-based Memory encapsulates executable procedural capacities that can be invoked for specific tasks [Wang2024]"
    ]
}
```

### 3. **key_questions** - Research questions with numbered circles
```json
{
    "box_type": "key_questions",
    "title": "Key Questions",
    "items": [
        "How is agent memory defined and how does it relate to RAG?",
        "What architectural forms can agent memory take?",
        "Why is agent memory needed and what purposes does it serve?",
        "How does agent memory operate and evolve over time?"
    ]
}
```

### 4. **concept_list** - Multiple concepts with descriptions and optional section references
```json
{
    "box_type": "concept_list",
    "title": "Three Major Memory Forms",
    "concepts": [
        {
            "name": "Token-level Memory",
            "section_ref": "Section 3.1",
            "description": "Memory organized as explicit and discrete units that can be individually accessed and modified."
        },
        {
            "name": "Parametric Memory",
            "section_ref": "Section 3.2",
            "description": "Memory stored within the model parameters, accessed implicitly during forward computation."
        }
    ]
}
```

### 5. **definition** - Formal definition of a key term
```json
{
    "box_type": "definition",
    "title": "Definition of Token-level Memory",
    "term": "Token-level Memory",
    "definition": "Token-level memory stores information as persistent, discrete units that are externally accessible and inspectable, enabling explicit manipulation and retrieval of stored knowledge."
}
```

### 6. **example** - Concrete examples with labeled sections
```json
{
    "box_type": "example",
    "title": "Example: Chain-of-Thought Prompting",
    "sections": [
        {"label": "Input:", "text": "Q: Roger has 5 tennis balls...", "style": "normal"},
        {"label": "CoT:", "text": "Let's think step by step...", "style": "italic"},
        {"label": "Output:", "text": "The answer is 11.", "style": "highlight"}
    ]
}
```

### 7. **evidence** - Quoting important findings from literature
```json
{
    "box_type": "evidence",
    "quote": "Important quote from the literature",
    "citation": "Author2024",
    "keyphrases": ["keyphrase1", "keyphrase2"]
}
```

### 8. **summary** - Chapter or section summary
```json
{
    "box_type": "summary",
    "title": "Summary",
    "items": ["First summary point with specific findings", "Second summary point with quantitative results", "Third summary point with implications"]
}
```

### 9. **note** - Additional notes or clarifications
```json
{
    "box_type": "note",
    "title": "Note",
    "items": ["Important clarification or additional information"]
}
```

### 10. **tip** - Best practices or recommendations
```json
{
    "box_type": "tip",
    "title": "Best Practice",
    "items": ["Recommended approach or tip for practitioners"]
}
```

### 11. **warning** - Important warnings or caveats
```json
{
    "box_type": "warning",
    "title": "Important Note",
    "items": ["Critical warning or caveat to be aware of"]
}
```

## Selection Guide:
- Use **numbered_list** for "Three Types of...", "Major Categories", etc.
- Use **key_questions** for research questions or key questions to address
- Use **concept_list** for multiple related concepts with descriptions
- Use **definition** for formal definitions of key terms
- Use **key_insights** for main findings or takeaways (MUST include citations)
- Use **summary** for chapter/section summaries
- Use **example** for concrete examples with input/output
- Use **evidence** for important quotes from literature
- Use **note** for clarifications or additional information
- Use **tip** for best practices or recommendations
- Use **warning** for important caveats or warnings

## QUALITY REQUIREMENTS:
1. **Be Specific**: Avoid vague statements like "LLMs are powerful" - instead say "GPT-4 achieves 86.4% accuracy on MMLU benchmark [OpenAI2023]"
2. **Include Evidence**: Every key insight should reference specific findings from the section content
3. **Use Citations**: Include citation keys in [brackets] when referencing specific papers or findings
4. **Be Professional**: Use academic language and precise terminology
5. **Be Insightful**: Provide genuine insights that synthesize information, not just restate facts

Choose the box_type that best fits the section content and provide 2-5 items.
"""
        
        prompt += "\nPlease output ONLY JSON, no other content."
        
        response = self._call_llm(prompt, temperature=0.5)
        
        if not response:
            return VisualElementDecision(
                element_type=VisualElementType.NONE,
                target_section=section_no,
                section_title=section_title,
                description="",
                data_requirements={},
                style_preference="",
                reference_images=[],
                priority=0,
                reason="Failed to generate"
            )
        
        try:
            data = self._extract_and_parse_json(response)
            
            return VisualElementDecision(
                element_type=VisualElementType(element_type),
                target_section=section_no,
                section_title=section_title,
                description=data.get("caption", ""),
                data_requirements=data,
                style_preference="",
                reference_images=[],
                priority=8,
                reason=f"Generated based on global planning"
            )
            
        except Exception as e:
            logger.error(f"Failed to parse element data: {e}")
            return VisualElementDecision(
                element_type=VisualElementType.NONE,
                target_section=section_no,
                section_title=section_title,
                description="",
                data_requirements={},
                style_preference="",
                reference_images=[],
                priority=0,
                reason=f"Parse error: {e}"
            )

    def set_existing_visual_elements(self, elements: List[ExistingVisualElement]):
        """
        设置已存在的视觉元素信息，用于避免重复生成
        
        Args:
            elements: 已存在的视觉元素列表
        """
        self.existing_visual_elements = elements
        logger.info(f"Set {len(elements)} existing visual elements for deduplication")
    
    def add_existing_table(self, table_info: Dict):
        """
        添加已存在的表格信息
        
        Args:
            table_info: 表格信息字典，包含 caption, description, section, topics 等
        """
        elem = ExistingVisualElement.from_table_info(table_info)
        self.existing_visual_elements.append(elem)
        logger.debug(f"Added existing table: {elem.title}")
    
    def get_generated_elements_info(self) -> List[Dict]:
        """
        获取本次生成的视觉元素信息，供后续生成器使用
        
        Returns:
            生成的视觉元素信息列表
        """
        # 这个方法会在 run() 完成后被调用，返回生成的元素信息
        return [
            {
                "element_type": "tikz",
                "title": d.description,
                "description": d.reason,
                "section": d.target_section,
                "topics": self._extract_topics_from_decision(d)
            }
            for d in getattr(self, '_last_decisions', [])
            if d.latex_code
        ]
    
    def _extract_topics_from_decision(self, decision: VisualElementDecision) -> List[str]:
        """从决策中提取主题关键词"""
        topics = []
        # 从描述中提取关键词
        desc = decision.description.lower()
        # 常见的主题关键词
        keywords = [
            "taxonomy", "classification", "pipeline", "architecture", "workflow",
            "comparison", "performance", "benchmark", "timeline", "evolution",
            "framework", "method", "approach", "technique", "model", "system",
            "training", "inference", "data", "evaluation"
        ]
        for kw in keywords:
            if kw in desc:
                topics.append(kw)
        return topics
    
    def run(
        self,
        mainbody_content: str,
        outlines: Dict,
        survey_topic: str = "",
        year_range: tuple = None,
        existing_tables: List[Dict] = None
    ) -> Tuple[str, List[VisualElementDecision]]:
        """
        运行动态视觉元素生成流程（智能全局规划版本）
        
        优化策略：
        1. 全局规划：先分析整个综述，决定需要什么类型的视觉元素
        2. 聚焦生成：根据规划结果，为每个选定的章节生成具体内容
        3. 质量优先：确保生成的视觉元素质量高、相关性强
        4. 避免重复：考虑已有的表格和视觉元素，避免主题重复
        
        Args:
            mainbody_content: 综述主体内容
            outlines: 大纲
            survey_topic: 综述主题
            year_range: 年份范围 (start_year, end_year)，用于时间线生成
            existing_tables: 已生成的表格信息列表，用于避免重复
            
        Returns:
            (修改后的内容, 决策列表)
        """
        logger.info("Starting intelligent dynamic visual generation...")
        
        # 重置计数器
        self.total_tikz_count = 0
        self.total_table_count = 0
        self.total_reference_fig_count = 0
        self.section_element_count = {}
        self.element_count = {t: 0 for t in VisualElementType}
        
        # 0. 设置已存在的表格信息（用于避免重复）
        if existing_tables:
            for table_info in existing_tables:
                self.add_existing_table(table_info)
            logger.info(f"Loaded {len(existing_tables)} existing tables for deduplication")
        
        # 0.5 加载论文方法名
        self.load_paper_methods()
        
        # 1. 收集参考文献图片
        self.collect_reference_images()
        
        # 2. 解析章节
        sections = self._parse_sections(mainbody_content)
        
        # 3. 全局规划
        logger.info("Phase 1: Global planning...")
        plan = self._global_planning(mainbody_content, sections, survey_topic)
        
        planned_elements = plan.get("planned_elements", [])
        if not planned_elements:
            logger.info("No visual elements planned, returning original content")
            return mainbody_content, []
        
        # 4. 构建章节内容映射
        section_map = {s[0]: (s[1], s[2]) for s in sections}
        
        # 5. 聚焦生成
        logger.info(f"Phase 2: Focused generation for {len(planned_elements)} planned elements...")
        all_decisions = []
        
        for planned in planned_elements:
            section_no = planned.get("section_no", "")
            element_type = planned.get("element_type", "")
            
            if section_no not in section_map:
                logger.warning(f"Section {section_no} not found, skipping")
                continue
            
            section_title, section_content = section_map[section_no]
            
            logger.info(f"Generating {element_type} for section {section_no}: {section_title}")
            
            # 生成元素数据（传递年份范围用于时间线）
            decision = self._generate_element_for_section(
                section_no,
                section_title,
                section_content,
                element_type,
                survey_topic,
                year_range=year_range
            )
            
            if decision.element_type != VisualElementType.NONE:
                # 生成LaTeX代码
                decision = self.generate_visual_element(decision, section_content)
                
                if decision.latex_code:
                    logger.info(f"Successfully generated {element_type} for section {section_no}")
            
            all_decisions.append(decision)
        
        # 保存决策供后续使用
        self._last_decisions = all_decisions
        
        # 6. 插入视觉元素
        modified_content = self.insert_visual_elements(mainbody_content, all_decisions)
        
        # 7. 生成摘要
        summary = self.generate_visual_summary(all_decisions)
        summary_path = self.output_dir / "tmp" / "visual_elements_summary.md"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary)
        
        generated_count = len([d for d in all_decisions if d.latex_code])
        logger.info(f"Generated {generated_count} visual elements (TikZ: {self.total_tikz_count}, Tables: {self.total_table_count}, RefFigs: {self.total_reference_fig_count})")
        
        return modified_content, all_decisions
    
    def _parse_sections(
        self,
        content: str
    ) -> List[Tuple[str, str, str]]:
        """
        解析内容中的章节
        
        Returns:
            [(section_no, section_title, section_content), ...]
        """
        sections = []
        
        # 匹配 \section{title} 和 \subsection{title}
        pattern = r'\\(sub)?section\{([^}]+)\}'
        matches = list(re.finditer(pattern, content))
        
        for i, match in enumerate(matches):
            is_subsection = match.group(1) is not None
            title = match.group(2)
            
            # 确定章节编号
            section_count = sum(1 for m in matches[:i+1] if m.group(1) is None)
            if is_subsection:
                subsection_count = sum(
                    1 for m in matches[:i+1]
                    if m.group(1) is not None and
                    sum(1 for mm in matches[:matches.index(m)+1] if mm.group(1) is None) == section_count
                )
                section_no = f"{section_count}.{subsection_count}"
            else:
                section_no = str(section_count)
            
            # 获取章节内容
            start = match.end()
            if i + 1 < len(matches):
                end = matches[i + 1].start()
            else:
                end = len(content)
            
            section_content = content[start:end].strip()
            
            # 跳过太短的章节
            if len(section_content) > 200:
                sections.append((section_no, title, section_content))
        
        return sections


# 测试代码
if __name__ == "__main__":
    generator = DynamicVisualGenerator(task_id="test")
    
    # 测试收集图片
    images = generator.collect_reference_images()
    print(f"Collected {len(images)} images")
    
    # 测试分析
    test_content = """
    Large Language Models (LLMs) have revolutionized natural language processing.
    Models like GPT-4, Claude, and LLaMA have shown remarkable capabilities.
    The development of LLMs can be traced back to the introduction of Transformers in 2017.
    """
    
    decisions = generator.analyze_section_for_visuals(
        test_content,
        "Introduction",
        "1",
        "Large Language Models Survey",
        []
    )
    
    for d in decisions:
        print(f"Type: {d.element_type.value}")
        print(f"Description: {d.description}")
        print(f"Priority: {d.priority}")
