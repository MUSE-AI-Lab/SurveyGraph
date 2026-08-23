"""
MEKG Content Generator
======================

基于MEKG知识图谱生成综述内容，利用图谱关系组织叙述逻辑。

核心思路:
1. 基于图谱关系组织论文引用顺序
2. 利用关系类型丰富叙述（如"A extends B", "C improves D"）
3. 基于论文属性生成原子事实
4. 迭代式内容生成，每次处理一批论文
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger

import sys
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from mekg.src.survey.outline_generator import SurveyOutline, OutlineSection
from src.configs.config import CONTENT_GEN_WORKERS

try:
    from src.models.LLM.ChatAgent import ChatAgent
    HAS_CHAT_AGENT = True
except ImportError:
    HAS_CHAT_AGENT = False


@dataclass
class PaperInfo:
    """论文信息，用于内容生成"""
    paper_id: str
    title: str
    abstract: str = ""
    year: Optional[int] = None
    citations: int = 0
    authors: List[str] = field(default_factory=list)
    venue: str = ""
    bib_name: str = ""  # 用于LaTeX引用
    category: str = ""
    subcategory: str = ""
    # 从MEKG提取的属性
    method_entities: List[str] = field(default_factory=list)
    task_entities: List[str] = field(default_factory=list)
    dataset_entities: List[str] = field(default_factory=list)
    innovation_points: List[str] = field(default_factory=list)
    # 关系信息
    relations: List[Dict] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PaperInfo':
        return cls(
            paper_id=data.get("id", data.get("paper_id", "")),
            title=data.get("title", ""),
            abstract=data.get("abstract", "")[:500] if data.get("abstract") else "",
            year=data.get("year"),
            citations=data.get("citations", 0),
            authors=data.get("authors", [])[:5],
            venue=data.get("venue", ""),
            bib_name=data.get("bib_name", data.get("id", data.get("paper_id", ""))),
            category=data.get("category", ""),
            subcategory=data.get("subcategory", ""),
            method_entities=data.get("method_entities", []),
            task_entities=data.get("task_entities", []),
            dataset_entities=data.get("dataset_entities", []),
            innovation_points=data.get("innovation_points", []),
            relations=data.get("relations", [])
        )
    
    def to_context_string(self) -> str:
        """生成用于LLM的上下文字符串"""
        parts = [f"Title: {self.title}"]
        if self.year:
            parts.append(f"Year: {self.year}")
        if self.citations:
            parts.append(f"Citations: {self.citations}")
        if self.abstract:
            parts.append(f"Abstract: {self.abstract[:300]}...")
        if self.method_entities:
            parts.append(f"Methods: {', '.join(self.method_entities[:5])}")
        if self.innovation_points:
            parts.append(f"Innovations: {', '.join(self.innovation_points[:3])}")
        return "\n".join(parts)


class MEKGContentGenerator:
    """
    基于MEKG知识图谱的内容生成器
    
    核心策略:
    1. 关系驱动叙述: 利用论文间关系组织叙述逻辑
    2. 原子事实写作: 基于论文属性而非全文
    3. 迭代式生成: 每次处理一批论文，保持上下文连贯
    4. 引用准确性: 确保每个引用都有对应的论文
    """
    
    # 内容生成Prompt (Evidence-Based with Deep Technical Analysis)
    CONTENT_GENERATION_PROMPT = """你是一位学术综述写作专家，擅长**深度技术分析**、**定量比较**和**批判性评价**。请基于以下信息，为综述的一个章节撰写**高质量学术内容**。

## 综述主题
{topic}

## 当前章节
标题: {section_title}
描述: {section_description}

## 已写内容
{written_content}

## 本次需要整合的论文 (Evidence)
{papers_info}

## 论文间的关系 (Logic) - 重要！请利用这些关系构建叙述逻辑
{relations_info}

## 核心写作原则 (CRITICAL - 必须严格遵守)

### 1. 禁止引用堆砌 (NO Citation Stuffing)
- **错误示例**: "许多研究探索了这个问题 \\cite{{a}}\\cite{{b}}\\cite{{c}}\\cite{{d}}。"
- **正确示例**: "Smith等人 \\cite{{a}} 首创了这一方法，随后Jones \\cite{{b}} 通过引入X机制对其进行了改进。"
- **规则**: 每个引用必须有**具体的引用理由**。除非明确进行对比，否则单句引用不超过2-3篇。

### 2. 深度技术分析优于罗列 (Deep Technical Analysis Over Listing)
- **错误示例**: "方法A使用技术X。方法B使用技术Y。方法C使用技术Z。"
- **正确示例**: "方法A采用技术X解决了可扩展性问题，但引入了延迟开销。方法B通过采用技术Y缓解了这一问题，以准确性换取速度。这一权衡后来被方法C通过技术Z解决。"
- **规则**: 始终解释方法**为什么有效**、**解决了什么问题**、以及**与替代方案的比较**。
- **技术机制**: 对于每个方法，解释其底层机制："关键洞察是[机制]通过[工作原理]实现了[能力]。"

### 3. 定量证据 (Quantitative Evidence) - 重要！
- **错误示例**: "方法A显著优于方法B。"
- **正确示例**: "方法A在BFCL v3上达到85.3\\%的准确率，比方法B（82.1\\%）高出3.2个百分点 \\cite{{paper_a}}。"
- **规则**: 比较方法时，尽可能包含论文中的具体数字。
- 如果没有确切数字，请说明："由于评估设置不同，直接比较具有挑战性，[方法A]在[基准]上报告了[指标]，而[方法B]在[不同基准]上进行了评估。"

### 4. 利用关系信息构建演进脉络
- 如果存在 `A extends B` 关系，描述A如何在B的基础上扩展
- 如果存在 `A improves B` 关系，详细说明改进点和改进幅度
- 如果存在 `A compares B` 关系，进行系统性对比分析
- 追溯思想演进: "早期方法依赖X，但在[论文]证明Z之后，领域转向Y。"
- **提供证据**: 用具体例子或统计数据支持趋势判断。

### 5. 批判性评价与具体细节
- **错误示例**: "该方法有一些局限性。"
- **正确示例**: "该方法表现出三种主要失败模式：(1) 当工具描述超过500个token时出现schema幻觉；(2) 字符串和整数参数之间的类型混淆；(3) 多步骤计划中的级联错误，早期错误会传播到后续调用。"
- 讨论具体局限性: "虽然[方法]取得了最先进的结果，但它需要[具体资源]，限制了其在[具体场景]中的适用性。"
- 明确比较权衡: "[方法A]优先考虑准确性，而[方法B]优化效率，使它们适用于不同的部署场景。"

### 6. 失败模式分析 (Failure Mode Analysis) - 新增重要！
- 识别常见失败模式: "一个反复出现的失败模式是[模式]，当[条件]时会发生。"
- 讨论边缘情况: "该方法在[边缘情况]上表现不佳，因为[原因]。"
- 建议缓解措施（如论文中提到）: "这一局限性可以通过[缓解措施]部分解决。"

### 7. 权衡分析 (Trade-off Analysis) - 新增
- 比较方法时，明确讨论权衡:
- "[方法A]和[方法B]之间的选择涉及一个基本权衡：[A]以[劣势A]为代价提供[优势A]，而[B]优先考虑[优势B]但牺牲了[劣势B]。这使得[A]更适合[场景A]，[B]更适合[场景B]。"

### 8. 对比表格 (Comparison Tables) - 适当时使用
当讨论3个或更多解决同一问题的方法时，考虑生成对比表格：
\\begin{{table}}[h]
\\centering
\\caption{{[主题]方法对比}}
\\small
\\begin{{tabularx}}{{\\textwidth}}{{p{{2.5cm}}XXX}}
\\toprule
\\textbf{{方法}} & \\textbf{{核心技术}} & \\textbf{{优势}} & \\textbf{{局限}} \\\\
\\midrule
方法A \\cite{{a}} & 技术X & 优势1 & 局限1 \\\\
方法B \\cite{{b}} & 技术Y & 优势2 & 局限2 \\\\
方法C \\cite{{c}} & 技术Z & 优势3 & 局限3 \\\\
\\bottomrule
\\end{{tabularx}}
\\end{{table}}

## 格式要求
- 输出纯LaTeX格式
- 引用格式: \\cite{{bib_name}}
- 关键术语使用 \\textit{{}}
- 不要输出章节标题
- 每段应包含分析，而非仅仅描述
- 包含定量数据（如有）
- 讨论局限性和失败模式

## LaTeX特殊字符处理 (IMPORTANT)
当提到代码、标签、变量名等包含特殊字符时，请使用以下格式：
- **XML/HTML标签**: 使用 \\texttt{{<tag>}} 格式，如 \\texttt{{<think>}}, \\texttt{{<tool\\_code>}}
- **带下划线的名称**: 转义下划线，如 tool\\_code, self\\_attention
- **尖括号**: 在非标签场景使用 $\\langle$ 和 $\\rangle$，如 $\\langle$input, output$\\rangle$
- **代码片段**: 使用 \\texttt{{...}} 包裹

## 输出示例 (请遵循此风格)
工具调用机制的发展可以追溯到三个不同的阶段，每个阶段都解决了前一阶段的特定局限性。早期方法以ReAct \\cite{{react}}为代表，依赖于交错的推理和行动步骤。关键洞察是显式推理轨迹可以指导工具选择，在HotpotQA上达到34\\%的准确率，而纯思维链方法仅为29\\%。然而，这种方法在多步骤任务中存在错误传播问题，单个错误的推理步骤可能级联到后续失败。

Toolformer \\cite{{toolformer}}通过自监督学习训练模型自主决定何时以及如何调用工具来解决这一局限性。该方法在数学推理基准上实现了15\\%的任务完成率提升。然而，其对基于困惑度过滤的依赖限制了其在工具API难以模拟的场景中的适用性——这对于API响应通常是非确定性的实际部署是一个重大限制。

随后函数调用API的引入将范式转向基于schema的方法。这一转变涉及一个基本权衡：基于schema的方法牺牲了学习型工具使用的灵活性，以换取生产部署所需的可靠性。具体而言，虽然学习型方法可以在不重新训练的情况下适应新工具，但基于schema的方法需要显式工具定义，但提供确定性解析和类型安全。

当前方法已识别出三种主要失败模式：(1) schema幻觉，模型生成看似合理但不存在的函数签名；(2) 参数类型混淆，特别是字符串和整数参数之间；(3) 多工具场景中的上下文溢出，累积的工具描述超过模型的有效上下文窗口。

## 输出
直接输出LaTeX内容，不要任何其他说明。"""

    # 对比分析 Prompt (Enhanced)
    COMPARATIVE_ANALYSIS_PROMPT = """请基于以下论文信息，撰写一段**深度批判性**的对比分析。

## 待对比论文
{papers_info}

## 论文间的关系
{relations_info}

## 写作要求

### 1. 多维度对比分析
从以下维度进行系统性对比：
- **核心思想 (Core Idea)**: 每个方法的核心创新点是什么？
- **技术路线 (Technical Approach)**: 采用了什么技术？为什么选择这种技术？
- **适用场景 (Applicability)**: 在什么场景下表现最好？有什么限制？
- **性能表现 (Performance)**: 在哪些指标上有优势？代价是什么？

### 2. 演进脉络分析
- 识别方法之间的继承和改进关系
- 解释为什么后续方法要做出这些改变
- 指出领域发展的关键转折点

### 3. 批判性评价
- 每个方法的主要优点和局限性
- 不同方法之间的权衡 (trade-offs)
- 哪些问题仍未解决？

### 4. 输出格式
- 先输出文字分析（2-3段）
- 然后生成一个LaTeX表格总结关键对比维度
- 表格应包含：方法名称、核心技术、主要优点、主要局限、适用场景

直接输出LaTeX内容（包含表格）。"""

    SECTION_INTRO_PROMPT = """请为以下综述章节撰写一段简短的导言（2-3句话），介绍该章节的主要内容和组织结构。

章节标题: {section_title}
章节描述: {section_description}
包含的子章节: {subsections}

要求:
- 使用学术论文风格
- 输出纯LaTeX格式
- 不要章节标题
- 2-3句话即可

直接输出内容:"""

    ABSTRACT_GENERATION_PROMPT = """请基于以下综述内容，撰写一份学术摘要。

## 综述标题
{title}

## 综述主题
{topic}

## 主要章节
{sections}

## 内容摘要
{content_summary}

## 要求
- 200-300词
- 包含：研究背景、主要内容、关键发现、结论
- 学术论文风格
- 输出格式：直接输出摘要文本，不要任何标记

直接输出摘要:"""

    def __init__(
        self,
        chat_agent: Optional[ChatAgent] = None,
        iter_span: int = 10,
        max_workers: int = None
    ):
        """
        初始化内容生成器
        
        Args:
            chat_agent: LLM对话代理
            iter_span: 每次迭代处理的论文数
            max_workers: 并发工作线程数（默认从 config.CONTENT_GEN_WORKERS 读取）
        """
        self.chat_agent = chat_agent
        self.iter_span = iter_span
        self.max_workers = max_workers if max_workers is not None else CONTENT_GEN_WORKERS
        
        if self.chat_agent is None and HAS_CHAT_AGENT:
            try:
                self.chat_agent = ChatAgent()
            except Exception as e:
                logger.warning(f"无法创建ChatAgent: {e}")
    
    def generate_content(
        self,
        outline: SurveyOutline,
        mekg_data: Dict[str, Any],
        output_dir: Path
    ) -> Dict[str, str]:
        """
        生成综述内容
        
        Args:
            outline: 综述大纲
            mekg_data: MEKG数据
            output_dir: 输出目录
            
        Returns:
            包含各部分内容的字典
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. 准备论文信息
        papers_map = self._prepare_papers_map(mekg_data)
        relations_map = self._prepare_relations_map(mekg_data)
        
        # 2. 为每个章节生成内容
        mainbody_parts = []
        
        for section in outline.sections:
            section_content = self._generate_section_content(
                section=section,
                outline=outline,
                papers_map=papers_map,
                relations_map=relations_map
            )
            mainbody_parts.append(section_content)
        
        # 3. 合并主体内容
        mainbody = "\n\n".join(mainbody_parts)
        
        # 4. 生成摘要
        abstract = self._generate_abstract(outline, mainbody)
        
        # 5. 保存结果
        results = {
            "mainbody": mainbody,
            "abstract": abstract,
            "outline": str(outline)
        }
        
        # 保存到文件
        (output_dir / "mainbody.tex").write_text(mainbody, encoding='utf-8')
        (output_dir / "abstract.tex").write_text(abstract, encoding='utf-8')
        
        logger.info(f"内容已生成并保存到: {output_dir}")
        
        return results
    
    def _prepare_papers_map(self, mekg_data: Dict) -> Dict[str, PaperInfo]:
        """准备论文ID到论文信息的映射"""
        papers_map = {}
        for paper in mekg_data.get("papers", []):
            paper_id = paper.get("id", paper.get("paper_id", ""))
            if paper_id:
                papers_map[paper_id] = PaperInfo.from_dict(paper)
        return papers_map
    
    def _prepare_relations_map(self, mekg_data: Dict) -> Dict[str, List[Dict]]:
        """准备论文ID到关系的映射"""
        relations_map = defaultdict(list)
        for rel in mekg_data.get("relations", []):
            source = rel.get("source", "")
            target = rel.get("target", "")
            if source:
                relations_map[source].append(rel)
            if target:
                relations_map[target].append(rel)
        return dict(relations_map)
    
    def _generate_section_content(
        self,
        section: OutlineSection,
        outline: SurveyOutline,
        papers_map: Dict[str, PaperInfo],
        relations_map: Dict[str, List[Dict]]
    ) -> str:
        """生成单个章节的内容"""
        content_parts = []
        
        # 章节标题
        content_parts.append(f"\\section{{{section.title}}}")
        logger.info(f"正在生成章节: {section.number}. {section.title}")
        
        # 如果有子章节，先生成章节导言
        if section.subsections:
            intro = self._generate_section_intro(section)
            content_parts.append(intro)
            
            # 生成每个子章节
            for subsection in section.subsections:
                sub_content = self._generate_subsection_content(
                    subsection=subsection,
                    section=section,
                    outline=outline,
                    papers_map=papers_map,
                    relations_map=relations_map
                )
                content_parts.append(sub_content)
        else:
            # 没有子章节，直接生成内容
            papers = self._get_section_papers(section, papers_map)
            if papers:
                logger.info(f"  章节 {section.number} 有 {len(papers)} 篇论文")
                content = self._generate_content_for_papers(
                    papers=papers,
                    section_title=f"{section.number} {section.title}",
                    section_desc=section.description,
                    topic=outline.topic,
                    relations_map=relations_map
                )
                content_parts.append(content)
            else:
                # 没有论文，使用LLM动态生成内容
                logger.info(f"  章节 {section.number} 没有挂载论文，使用LLM生成")
                content_parts.append(self._generate_generic_content(section, outline, papers_map))
        
        return "\n\n".join(content_parts)
    
    def _generate_subsection_content(
        self,
        subsection: OutlineSection,
        section: OutlineSection,
        outline: SurveyOutline,
        papers_map: Dict[str, PaperInfo],
        relations_map: Dict[str, List[Dict]]
    ) -> str:
        """生成子章节内容 - 支持三级结构"""
        content_parts = []
        
        # 子章节标题
        content_parts.append(f"\\subsection{{{subsection.title}}}")
        
        # 检查是否有三级结构 (subsubsections)
        if subsection.subsections:
            logger.info(f"  子章节 {subsection.number} 有 {len(subsection.subsections)} 个子子节")
            
            # 先生成子章节的导言（如果有多个子子节）
            if len(subsection.subsections) > 1:
                intro = self._generate_subsection_intro(subsection)
                content_parts.append(intro)
            
            # 生成每个子子节的内容
            for subsubsection in subsection.subsections:
                subsub_content = self._generate_subsubsection_content(
                    subsubsection=subsubsection,
                    subsection=subsection,
                    section=section,
                    outline=outline,
                    papers_map=papers_map,
                    relations_map=relations_map
                )
                content_parts.append(subsub_content)
        else:
            # 没有三级结构，直接生成二级内容
            # 获取该子章节的论文
            papers = self._get_section_papers(subsection, papers_map)
            
            # 如果子章节没有论文，尝试从父章节继承
            if not papers and section.paper_ids:
                # 按子章节标题关键词过滤父章节的论文
                papers = self._filter_papers_by_keywords(
                    [papers_map[pid] for pid in section.paper_ids if pid in papers_map],
                    subsection.title
                )
                if papers:
                    logger.info(f"  子章节 {subsection.number} 从父章节继承了 {len(papers)} 篇论文")
            
            if papers:
                content = self._generate_content_for_papers(
                    papers=papers,
                    section_title=f"{subsection.number} {subsection.title}",
                    section_desc=subsection.description,
                    topic=outline.topic,
                    relations_map=relations_map
                )
                content_parts.append(content)
            else:
                logger.info(f"  子章节 {subsection.number} 没有论文，使用LLM生成")
                content_parts.append(self._generate_generic_content(subsection, outline, papers_map))
        
        return "\n\n".join(content_parts)
    
    def _generate_subsubsection_content(
        self,
        subsubsection: OutlineSection,
        subsection: OutlineSection,
        section: OutlineSection,
        outline: SurveyOutline,
        papers_map: Dict[str, PaperInfo],
        relations_map: Dict[str, List[Dict]]
    ) -> str:
        """生成子子节内容（三级结构）"""
        content_parts = []
        
        # 子子节标题
        content_parts.append(f"\\subsubsection{{{subsubsection.title}}}")
        logger.info(f"    正在生成子子节: {subsubsection.number}. {subsubsection.title}")
        
        # 获取该子子节的论文
        papers = self._get_section_papers(subsubsection, papers_map)
        
        # 如果子子节没有论文，尝试从父章节继承
        if not papers and subsection.paper_ids:
            papers = self._filter_papers_by_keywords(
                [papers_map[pid] for pid in subsection.paper_ids if pid in papers_map],
                subsubsection.title
            )
            if papers:
                logger.info(f"    子子节 {subsubsection.number} 从父章节继承了 {len(papers)} 篇论文")
        
        # 如果还是没有论文，尝试从祖父章节继承
        if not papers and section.paper_ids:
            papers = self._filter_papers_by_keywords(
                [papers_map[pid] for pid in section.paper_ids if pid in papers_map],
                subsubsection.title
            )
            if papers:
                logger.info(f"    子子节 {subsubsection.number} 从祖父章节继承了 {len(papers)} 篇论文")
        
        if papers:
            logger.info(f"    子子节 {subsubsection.number} 有 {len(papers)} 篇论文")
            content = self._generate_content_for_papers(
                papers=papers,
                section_title=f"{subsubsection.number} {subsubsection.title}",
                section_desc=subsubsection.description,
                topic=outline.topic,
                relations_map=relations_map
            )
            content_parts.append(content)
        else:
            logger.info(f"    子子节 {subsubsection.number} 没有论文，使用LLM生成")
            content_parts.append(self._generate_generic_content(subsubsection, outline, papers_map))
        
        return "\n\n".join(content_parts)
    
    def _generate_subsection_intro(self, subsection: OutlineSection) -> str:
        """生成子章节导言（当有多个子子节时）"""
        if not self.chat_agent:
            return f"This subsection discusses {subsection.title}."
        
        subsubsections_str = ", ".join([s.title for s in subsection.subsections])
        
        prompt = f"""请为以下综述子章节撰写一段简短的导言（1-2句话），介绍该子章节的主要内容和组织结构。

子章节标题: {subsection.title}
子章节描述: {subsection.description}
包含的子子节: {subsubsections_str}

要求:
- 使用学术论文风格
- 输出纯LaTeX格式
- 不要章节标题
- 1-2句话即可

直接输出内容:"""
        
        try:
            intro = self.chat_agent.remote_chat(prompt, temperature=0.3)
            return self._clean_content(intro)
        except Exception as e:
            logger.warning(f"子章节导言生成失败: {e}")
            return f"This subsection discusses {subsection.title}."
    
    def _filter_papers_by_keywords(
        self,
        papers: List[PaperInfo],
        title: str
    ) -> List[PaperInfo]:
        """根据标题关键词过滤论文"""
        if not papers:
            return []
        
        # 提取标题中的关键词
        keywords = set(title.lower().split())
        # 移除常见停用词
        stopwords = {'and', 'or', 'the', 'a', 'an', 'of', 'for', 'in', 'on', 'to', 'with'}
        keywords = keywords - stopwords
        
        if not keywords:
            return papers[:5]  # 如果没有有效关键词，返回前5篇
        
        # 计算每篇论文的匹配分数
        scored_papers = []
        for paper in papers:
            paper_text = f"{paper.title} {paper.abstract} {' '.join(paper.method_entities)}".lower()
            score = sum(1 for kw in keywords if kw in paper_text)
            if score > 0:
                scored_papers.append((paper, score))
        
        # 按分数排序
        scored_papers.sort(key=lambda x: x[1], reverse=True)
        
        return [p for p, s in scored_papers[:10]]  # 返回前10篇
    
    def _get_section_papers(
        self,
        section: OutlineSection,
        papers_map: Dict[str, PaperInfo]
    ) -> List[PaperInfo]:
        """获取章节对应的论文"""
        papers = []
        
        # 从paper_ids获取
        for paper_id in section.paper_ids:
            if paper_id in papers_map:
                papers.append(papers_map[paper_id])
        
        # 从key_papers获取（如果paper_ids为空）
        if not papers:
            for paper_id in section.key_papers:
                if paper_id in papers_map:
                    papers.append(papers_map[paper_id])
        
        # 按引用数排序
        papers.sort(key=lambda x: x.citations, reverse=True)
        
        return papers
    
    def _generate_content_for_papers(
        self,
        papers: List[PaperInfo],
        section_title: str,
        section_desc: str,
        topic: str,
        relations_map: Dict[str, List[Dict]],
        written_content: str = ""
    ) -> str:
        """为一组论文生成内容"""
        if not self.chat_agent:
            return self._generate_content_without_llm(papers, section_title)
        
        all_content = []
        
        # 1. 如果论文数量较多（>5），先生成一个对比分析表格
        if len(papers) >= 5:
            try:
                logger.info(f"为 {section_title} 生成对比分析 (基于 {min(len(papers), 8)} 篇核心论文)...")
                top_papers = papers[:8] # 取前8篇做对比
                papers_info = "\n\n".join([
                    f"[{i+1}] bib_name: {p.bib_name}\n{p.to_context_string()}"
                    for i, p in enumerate(top_papers)
                ])
                # 获取这些论文之间的关系信息
                relations_info = self._format_relations_for_papers(top_papers, relations_map)
                comp_prompt = self.COMPARATIVE_ANALYSIS_PROMPT.format(
                    papers_info=papers_info,
                    relations_info=relations_info
                )
                comp_content = self.chat_agent.remote_chat(comp_prompt, temperature=0.3)
                all_content.append(self._clean_content(comp_content))
            except Exception as e:
                logger.warning(f"对比分析生成失败: {e}")

        # 2. 迭代式生成正文
        total_batches = (len(papers) + self.iter_span - 1) // self.iter_span
        for i in range(0, len(papers), self.iter_span):
            batch_idx = i // self.iter_span + 1
            batch_papers = papers[i:i + self.iter_span]
            
            logger.info(f"正在撰写 {section_title} (批次 {batch_idx}/{total_batches}, {len(batch_papers)} 篇论文)...")
            
            # 准备论文信息
            papers_info = "\n\n---\n\n".join([
                f"[{j+1}] bib_name: {p.bib_name}\n{p.to_context_string()}"
                for j, p in enumerate(batch_papers)
            ])
            
            # 准备关系信息
            relations_info = self._format_relations_for_papers(batch_papers, relations_map)
            
            # 构建prompt
            prompt = self.CONTENT_GENERATION_PROMPT.format(
                topic=topic,
                section_title=section_title,
                section_description=section_desc,
                written_content=written_content[-2000:] if written_content else "(这是章节开头)",
                papers_info=papers_info,
                relations_info=relations_info
            )
            
            # 调用LLM
            try:
                content = self.chat_agent.remote_chat(prompt, temperature=0.5)
                content = self._clean_content(content)
                all_content.append(content)
                written_content += "\n\n" + content
            except Exception as e:
                logger.error(f"内容生成失败: {e}")
                all_content.append(self._generate_content_without_llm(batch_papers, section_title))
        
        return "\n\n".join(all_content)
    
    def _format_relations_for_papers(
        self,
        papers: List[PaperInfo],
        relations_map: Dict[str, List[Dict]]
    ) -> str:
        """格式化论文间的关系信息"""
        paper_ids = {p.paper_id for p in papers}
        relevant_relations = []
        
        for paper in papers:
            for rel in relations_map.get(paper.paper_id, []):
                source = rel.get("source", "")
                target = rel.get("target", "")
                rel_type = rel.get("type", "")
                
                # 只保留两端都在当前论文集中的关系
                if source in paper_ids and target in paper_ids:
                    relevant_relations.append(
                        f"- {source} --[{rel_type}]--> {target}"
                    )
        
        if relevant_relations:
            return "\n".join(relevant_relations[:20])  # 限制数量
        return "无明显关系"
    
    def _generate_content_without_llm(
        self,
        papers: List[PaperInfo],
        section_title: str
    ) -> str:
        """无LLM时的内容生成（简单模板）"""
        if not papers:
            return f"This section discusses {section_title}."
        
        content_parts = []
        for paper in papers[:10]:
            content_parts.append(
                f"{paper.title} \\cite{{{paper.bib_name}}} "
                f"{'proposes ' + paper.method_entities[0] if paper.method_entities else 'addresses this problem'}."
            )
        
        return " ".join(content_parts)
    
    def _generate_section_intro(self, section: OutlineSection) -> str:
        """生成章节导言"""
        if not self.chat_agent:
            return f"This section presents an overview of {section.title}."
        
        subsections_str = ", ".join([s.title for s in section.subsections])
        
        prompt = self.SECTION_INTRO_PROMPT.format(
            section_title=section.title,
            section_description=section.description,
            subsections=subsections_str
        )
        
        try:
            intro = self.chat_agent.remote_chat(prompt, temperature=0.3)
            return self._clean_content(intro)
        except Exception as e:
            logger.warning(f"导言生成失败: {e}")
            return f"This section presents an overview of {section.title}."
    
    def _generate_generic_content(
        self,
        section: OutlineSection,
        outline: Optional['SurveyOutline'] = None,
        papers_map: Optional[Dict[str, PaperInfo]] = None
    ) -> str:
        """生成通用内容（无论文时）- 使用LLM动态生成"""
        if not self.chat_agent:
            # 无LLM时使用简单模板
            if section.title.lower() == "introduction":
                return self._generate_introduction_fallback()
            elif section.title.lower() in ["conclusion", "conclusion and future directions"]:
                return self._generate_conclusion_fallback()
            else:
                return f"This section discusses {section.title}. {section.description}"
        
        # 使用LLM动态生成
        if section.title.lower() == "introduction":
            return self._generate_introduction_with_llm(section, outline, papers_map)
        elif section.title.lower() in ["conclusion", "conclusion and future directions"]:
            return self._generate_conclusion_with_llm(section, outline, papers_map)
        else:
            return self._generate_section_with_llm(section, outline)
    
    def _generate_introduction_with_llm(
        self,
        section: OutlineSection,
        outline: Optional['SurveyOutline'] = None,
        papers_map: Optional[Dict[str, PaperInfo]] = None
    ) -> str:
        """使用LLM生成Introduction内容"""
        topic = outline.topic if outline else "this research area"
        
        # 获取一些代表性论文作为背景
        sample_papers = []
        if papers_map:
            # 按引用数排序，取前10篇作为背景
            sorted_papers = sorted(papers_map.values(), key=lambda x: x.citations, reverse=True)[:10]
            sample_papers = [f"- {p.title} ({p.year})" for p in sorted_papers if p.title]
        
        # 获取章节结构
        sections_overview = ""
        if outline:
            sections_overview = "\n".join([
                f"- Section {s.number}: {s.title}"
                for s in outline.sections if s.number != section.number
            ])
        
        prompt = f"""你是一位学术综述写作专家。请为以下综述撰写Introduction章节。

## 综述主题
{topic}

## 综述结构
{sections_overview}

## 领域代表性论文（供参考）
{chr(10).join(sample_papers) if sample_papers else "暂无"}

## 写作要求
1. **背景介绍**: 介绍该研究领域的背景和重要性
2. **问题动机**: 说明为什么需要这篇综述
3. **主要贡献**: 列出本综述的主要贡献（3-4点）
4. **结构概述**: 简要介绍综述的组织结构

## 格式要求
- 输出纯LaTeX格式
- 使用 \\textit{{}} 标记关键术语
- 贡献列表使用 itemize 环境
- 不要输出章节标题（\\section）
- 长度：300-500词

直接输出LaTeX内容:"""

        try:
            content = self.chat_agent.remote_chat(prompt, temperature=0.5)
            return self._clean_content(content)
        except Exception as e:
            logger.warning(f"Introduction LLM生成失败: {e}")
            return self._generate_introduction_fallback()
    
    def _generate_conclusion_with_llm(
        self,
        section: OutlineSection,
        outline: Optional['SurveyOutline'] = None,
        papers_map: Optional[Dict[str, PaperInfo]] = None
    ) -> str:
        """使用LLM生成Conclusion内容"""
        topic = outline.topic if outline else "this research area"
        
        # 获取章节摘要
        sections_summary = ""
        if outline:
            sections_summary = "\n".join([
                f"- {s.title}: {s.description[:100]}..."
                for s in outline.sections
                if s.title.lower() not in ["introduction", "conclusion", "conclusion and future directions"]
            ])
        
        prompt = f"""你是一位学术综述写作专家。请为以下综述撰写Conclusion章节。

## 综述主题
{topic}

## 已覆盖的章节
{sections_summary}

## 写作要求
1. **总结回顾**: 总结综述的主要内容和发现
2. **关键洞察**: 提炼出该领域的关键洞察和趋势
3. **挑战与局限**: 讨论当前方法的主要挑战和局限性
4. **未来方向**: 提出3-5个有前景的未来研究方向

## 格式要求
- 输出纯LaTeX格式
- 使用 \\textit{{}} 标记关键术语
- 未来方向使用 itemize 环境
- 不要输出章节标题（\\section）
- 长度：300-500词

直接输出LaTeX内容:"""

        try:
            content = self.chat_agent.remote_chat(prompt, temperature=0.5)
            return self._clean_content(content)
        except Exception as e:
            logger.warning(f"Conclusion LLM生成失败: {e}")
            return self._generate_conclusion_fallback()
    
    def _generate_section_with_llm(
        self,
        section: OutlineSection,
        outline: Optional['SurveyOutline'] = None
    ) -> str:
        """使用LLM生成普通章节内容（无论文时）"""
        topic = outline.topic if outline else "this research area"
        
        prompt = f"""你是一位学术综述写作专家。请为以下综述章节撰写内容。

## 综述主题
{topic}

## 章节信息
标题: {section.title}
描述: {section.description}

## 写作要求
1. 基于章节标题和描述，撰写该章节的内容
2. 内容应该是概述性的，介绍该主题的关键概念和方法
3. 由于没有具体论文引用，请使用通用性描述

## 格式要求
- 输出纯LaTeX格式
- 使用 \\textit{{}} 标记关键术语
- 不要输出章节标题（\\section 或 \\subsection）
- 长度：150-300词

直接输出LaTeX内容:"""

        try:
            content = self.chat_agent.remote_chat(prompt, temperature=0.5)
            return self._clean_content(content)
        except Exception as e:
            logger.warning(f"章节 {section.title} LLM生成失败: {e}")
            return f"This section discusses {section.title}. {section.description}"
    
    def _generate_introduction_fallback(self) -> str:
        """Introduction的回退模板"""
        return """The rapid advancement of artificial intelligence and machine learning has led to significant developments in this research area. This survey aims to provide a comprehensive overview of the current state-of-the-art methods, challenges, and future directions.

The main contributions of this survey are as follows:
\\begin{itemize}
\\item We provide a systematic review of existing approaches and methods.
\\item We analyze the relationships and evolution of different techniques.
\\item We identify key challenges and promising future research directions.
\\end{itemize}"""
    
    def _generate_conclusion_fallback(self) -> str:
        """Conclusion的回退模板"""
        return """In this survey, we have provided a comprehensive overview of the research landscape in this field. We have reviewed the major approaches, analyzed their relationships, and discussed the key challenges.

Looking forward, several promising research directions emerge:
\\begin{itemize}
\\item Developing more efficient and scalable methods.
\\item Improving the interpretability and reliability of existing approaches.
\\item Exploring novel applications in emerging domains.
\\end{itemize}

We hope this survey serves as a valuable resource for researchers and practitioners in this field."""
    
    def _generate_abstract(self, outline: SurveyOutline, mainbody: str) -> str:
        """生成摘要"""
        if not self.chat_agent:
            return f"This survey provides a comprehensive overview of {outline.topic}."
        
        # 提取章节标题
        sections_str = "\n".join([
            f"- {s.title}: {s.description[:50]}..."
            for s in outline.sections
        ])
        
        # 提取内容摘要（取前2000字符）
        content_summary = mainbody[:2000] + "..."
        
        prompt = self.ABSTRACT_GENERATION_PROMPT.format(
            title=outline.title,
            topic=outline.topic,
            sections=sections_str,
            content_summary=content_summary
        )
        
        try:
            abstract = self.chat_agent.remote_chat(prompt, temperature=0.3)
            return f"\\begin{{abstract}}\n{abstract.strip()}\n\\end{{abstract}}"
        except Exception as e:
            logger.warning(f"摘要生成失败: {e}")
            return f"\\begin{{abstract}}\nThis survey provides a comprehensive overview of {outline.topic}.\\end{{abstract}}"
    
    def _clean_content(self, content: str) -> str:
        """清理生成的内容并转义LaTeX特殊字符"""
        # 移除可能的Markdown标记
        content = re.sub(r'^```\w*\n?', '', content)
        content = re.sub(r'\n?```$', '', content)
        
        # 移除多余的空行
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        # 转义LaTeX特殊字符（保留原汁原味但确保能正确渲染）
        content = self._escape_latex_special_chars(content)
        
        return content.strip()
    
    def _escape_latex_special_chars(self, content: str) -> str:
        """
        智能转义LaTeX特殊字符
        
        处理以下情况：
        1. XML/HTML标签如 <think>, <tool_code> 等
        2. 下划线 _ 在非数学模式下
        3. 尖括号 < > 在普通文本中
        
        保留以下情况不转义：
        1. 已有的LaTeX命令（如 \cite{}, \textit{} 等）
        2. 数学模式中的内容（$...$）
        3. 已经转义的字符
        """
        # 1. 保护已有的LaTeX结构（临时替换）
        protected_patterns = []
        
        # 保护LaTeX命令 \command{...} 和 \command[...]{...}
        def protect_latex_cmd(match):
            idx = len(protected_patterns)
            protected_patterns.append(match.group(0))
            return f"__PROTECTED_{idx}__"
        
        # 保护 \cite{}, \textit{}, \textbf{}, \ref{}, \label{} 等
        content = re.sub(r'\\[a-zA-Z]+(?:\[[^\]]*\])?\{[^}]*\}', protect_latex_cmd, content)
        
        # 保护数学模式 $...$ 和 $$...$$
        content = re.sub(r'\$\$[^$]+\$\$', protect_latex_cmd, content)
        content = re.sub(r'\$[^$]+\$', protect_latex_cmd, content)
        
        # 保护 \begin{...}...\end{...} 环境
        content = re.sub(r'\\begin\{[^}]+\}.*?\\end\{[^}]+\}', protect_latex_cmd, content, flags=re.DOTALL)
        
        # 保护已转义的字符
        content = re.sub(r'\\[_&%#${}]', protect_latex_cmd, content)
        
        # 2. 转义XML/HTML标签模式 <tag_name> 或 <tag-name>
        # 使用 \texttt{} 包裹以保持代码风格
        def escape_xml_tag(match):
            tag = match.group(0)
            # 转义内部的特殊字符
            inner = tag[1:-1]  # 去掉 < >
            inner = inner.replace('_', r'\_')
            return r'\texttt{<' + inner + r'>}'
        
        content = re.sub(r'<[a-zA-Z_][a-zA-Z0-9_-]*>', escape_xml_tag, content)
        content = re.sub(r'</[a-zA-Z_][a-zA-Z0-9_-]*>', escape_xml_tag, content)
        
        # 3. 转义剩余的尖括号（非标签形式）
        # 使用数学模式的 \langle 和 \rangle 或直接用 \textless \textgreater
        content = re.sub(r'(?<!\\)<(?![a-zA-Z_/])', r'\\textless{}', content)
        content = re.sub(r'(?<![a-zA-Z0-9_-])>(?!})', r'\\textgreater{}', content)
        
        # 4. 转义普通文本中的下划线（不在命令参数中的）
        # 查找不在 {} 内的下划线
        def escape_underscore(match):
            text = match.group(0)
            # 如果是在单词中间的下划线（如 tool_code），转义它
            return text.replace('_', r'\_')
        
        # 匹配包含下划线的"单词"（字母数字下划线组合）
        content = re.sub(r'\b[a-zA-Z0-9]*_[a-zA-Z0-9_]*\b', escape_underscore, content)
        
        # 5. 恢复被保护的LaTeX结构
        for idx, original in enumerate(protected_patterns):
            content = content.replace(f"__PROTECTED_{idx}__", original)
        
        return content


def generate_content_from_mekg(
    mekg_json_path: Path,
    outline_path: Path,
    output_dir: Path
) -> Dict[str, str]:
    """
    从MEKG数据和大纲生成内容
    
    Args:
        mekg_json_path: MEKG数据JSON文件路径
        outline_path: 大纲JSON文件路径
        output_dir: 输出目录
        
    Returns:
        包含各部分内容的字典
    """
    # 加载数据
    with open(mekg_json_path, 'r', encoding='utf-8') as f:
        mekg_data = json.load(f)
    
    outline = SurveyOutline.load(outline_path)
    
    # 生成内容
    generator = MEKGContentGenerator()
    return generator.generate_content(outline, mekg_data, output_dir)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) >= 4:
        mekg_path = Path(sys.argv[1])
        outline_path = Path(sys.argv[2])
        output_dir = Path(sys.argv[3])
        
        results = generate_content_from_mekg(mekg_path, outline_path, output_dir)
        print(f"生成完成！主体内容长度: {len(results['mainbody'])} 字符")
    else:
        print("Usage: python content_generator.py <mekg_json> <outline_json> <output_dir>")