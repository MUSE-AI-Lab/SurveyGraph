"""
Protocol Interfaces
===================

定义 Pipeline 各组件的协议接口，用于：
- 模块解耦
- 依赖注入
- 单元测试 Mock
- 组件替换

使用 Python 的 Protocol 类型提示，支持结构化子类型（鸭子类型）。
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    AsyncIterator,
    Dict,
    List,
    Optional,
    Protocol,
    TypeVar,
    runtime_checkable,
)


# ============================================================================
# 数据类型定义
# ============================================================================

@dataclass
class PaperData:
    """论文数据结构"""
    paper_id: str
    title: str
    abstract: str = ""
    authors: List[str] = None
    year: Optional[int] = None
    venue: str = ""
    citations: int = 0
    pdf_url: Optional[str] = None
    arxiv_id: Optional[str] = None
    source: str = "unknown"
    is_survey: bool = False
    relevance_score: float = 0.0
    md_text: str = ""
    
    def __post_init__(self):
        if self.authors is None:
            self.authors = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "year": self.year,
            "venue": self.venue,
            "citations": self.citations,
            "pdf_url": self.pdf_url,
            "arxiv_id": self.arxiv_id,
            "source": self.source,
            "is_survey": self.is_survey,
            "relevance_score": self.relevance_score,
            "md_text": self.md_text,
        }


@dataclass
class OutlineSection:
    """大纲章节"""
    number: str
    title: str
    description: str = ""
    level: int = 1
    paper_ids: List[str] = None
    subsections: List["OutlineSection"] = None
    
    def __post_init__(self):
        if self.paper_ids is None:
            self.paper_ids = []
        if self.subsections is None:
            self.subsections = []


@dataclass
class SurveyOutline:
    """综述大纲"""
    title: str
    topic: str
    sections: List[OutlineSection] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.sections is None:
            self.sections = []
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ContentResult:
    """内容生成结果"""
    mainbody: str
    abstract: str
    outline_str: str = ""
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class EvaluationResult:
    """评估结果"""
    overall_score: float
    wcr: float  # 核心论文覆盖率
    details: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "wcr": self.wcr,
            "details": self.details,
        }


# ============================================================================
# 协议接口定义
# ============================================================================

@runtime_checkable
class PaperCollectorProtocol(Protocol):
    """
    论文收集器协议
    
    负责从各种数据源收集论文，支持：
    - 关键词搜索
    - Survey 优先策略
    - 相关性筛选
    - PDF 下载和解析
    """
    
    async def collect_papers(
        self,
        topic: str,
        target_count: int = 100,
        year_start: int = 2020,
        year_end: Optional[int] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        收集论文
        
        Args:
            topic: 研究主题
            target_count: 目标论文数
            year_start: 起始年份
            year_end: 结束年份
            **kwargs: 其他配置参数
            
        Returns:
            论文列表（字典格式）
        """
        ...
    
    async def collect_papers_stream(
        self,
        topic: str,
        target_count: int = 100,
        **kwargs
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """
        流式收集论文（边收集边返回）
        
        Args:
            topic: 研究主题
            target_count: 目标论文数
            **kwargs: 其他配置参数
            
        Yields:
            论文批次
        """
        ...


@runtime_checkable
class OutlineGeneratorProtocol(Protocol):
    """
    大纲生成器协议
    
    负责基于 MEKG 数据生成综述大纲，支持：
    - 图谱结构分析
    - LLM 大纲生成
    - Critic-Refine 循环
    - 论文挂载
    """
    
    def generate_from_mekg_data(
        self,
        mekg_data: Dict[str, Any],
        topic: str,
        target_sections: int = 5
    ) -> Any:  # SurveyOutline
        """
        从 MEKG 数据生成大纲
        
        Args:
            mekg_data: MEKG 数据
            topic: 综述主题
            target_sections: 目标章节数
            
        Returns:
            SurveyOutline 对象
        """
        ...


@runtime_checkable
class ContentGeneratorProtocol(Protocol):
    """
    内容生成器协议
    
    负责基于大纲和论文数据生成综述内容，支持：
    - 迭代式内容生成
    - 关系驱动叙述
    - 对比分析
    - 摘要生成
    """
    
    def generate_content(
        self,
        outline: Any,  # SurveyOutline
        mekg_data: Dict[str, Any],
        output_dir: Path
    ) -> Dict[str, str]:
        """
        生成综述内容
        
        Args:
            outline: 综述大纲
            mekg_data: MEKG 数据
            output_dir: 输出目录
            
        Returns:
            包含 mainbody, abstract 等的字典
        """
        ...
    
    async def generate_content_async(
        self,
        outline: Any,
        mekg_data: Dict[str, Any],
        output_dir: Path
    ) -> Dict[str, str]:
        """
        异步生成综述内容
        """
        ...


@runtime_checkable
class EvaluatorProtocol(Protocol):
    """
    评估器协议
    
    负责评估综述质量，支持：
    - 核心论文覆盖率
    - 内容质量评分
    - 全局一致性检查
    """
    
    def evaluate(
        self,
        survey_content: str,
        survey_outline: Dict[str, Any]
    ) -> Any:  # EvaluationResult
        """
        评估综述质量
        
        Args:
            survey_content: 综述内容
            survey_outline: 综述大纲
            
        Returns:
            EvaluationResult 对象
        """
        ...
    
    def generate_report(
        self,
        evaluation: Any,  # EvaluationResult
        output_path: Path
    ) -> None:
        """
        生成评估报告
        
        Args:
            evaluation: 评估结果
            output_path: 输出路径
        """
        ...


@runtime_checkable
class LatexGeneratorProtocol(Protocol):
    """
    LaTeX 生成器协议
    
    负责生成 LaTeX 文档和编译 PDF
    """
    
    def generate_full_survey(self) -> None:
        """生成完整的 survey.tex"""
        ...
    
    def compile_single_survey(self) -> bool:
        """编译 PDF"""
        ...


@runtime_checkable
class PostRefinerProtocol(Protocol):
    """
    后处理器协议
    
    负责内容优化、表格生成、视觉元素生成
    """
    
    def refine_text(self) -> None:
        """文本优化"""
        ...
    
    def generate_tables(self) -> None:
        """生成表格"""
        ...
    
    def generate_dynamic_visuals(self, mainbody_path: Path) -> None:
        """生成动态视觉元素"""
        ...
    
    def run(self) -> None:
        """运行完整的后处理流程"""
        ...


@runtime_checkable
class GlobalReflectorProtocol(Protocol):
    """
    全局反思器协议
    
    负责全局一致性检查
    """
    
    def reflect(
        self,
        title: str,
        topic: str,
        sections_content: Dict[str, str],
        outline: Dict[str, Any]
    ) -> Any:
        """
        执行全局反思
        
        Args:
            title: 综述标题
            topic: 综述主题
            sections_content: 章节内容
            outline: 大纲
            
        Returns:
            反思结果
        """
        ...


@runtime_checkable
class EvolutionaryAnalyzerProtocol(Protocol):
    """
    演化分析器协议
    
    负责分析研究领域的演化趋势
    """
    
    def analyze(
        self,
        topic: str,
        papers: List[Dict[str, Any]]
    ) -> Any:
        """
        分析演化趋势
        
        Args:
            topic: 研究主题
            papers: 论文列表
            
        Returns:
            演化分析结果
        """
        ...
    
    def generate_timeline_latex(self, result: Any) -> str:
        """
        生成时间线 LaTeX
        
        Args:
            result: 演化分析结果
            
        Returns:
            LaTeX 代码
        """
        ...


@runtime_checkable
class CriticalAnalyzerProtocol(Protocol):
    """
    批判性分析器协议
    
    负责检测和增强内容中的薄弱环节
    """
    
    def analyze(self, content: str) -> Dict[str, List[Any]]:
        """
        分析内容质量
        
        Args:
            content: 内容文本
            
        Returns:
            分析结果
        """
        ...
    
    def enhance(
        self,
        content: str,
        analysis_result: Dict[str, List[Any]]
    ) -> tuple[str, int]:
        """
        增强内容
        
        Args:
            content: 原始内容
            analysis_result: 分析结果
            
        Returns:
            (增强后的内容, 增强的段落数)
        """
        ...
    
    def generate_report(self, analysis_result: Dict[str, List[Any]]) -> str:
        """
        生成分析报告
        
        Args:
            analysis_result: 分析结果
            
        Returns:
            报告文本
        """
        ...


# ============================================================================
# LLM 服务协议
# ============================================================================

@runtime_checkable
class LLMServiceProtocol(Protocol):
    """
    LLM 服务协议
    
    统一的 LLM 调用接口
    """
    
    async def call(
        self,
        prompt: str,
        *,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """单次调用"""
        ...
    
    async def batch_call(
        self,
        prompts: List[str],
        *,
        max_concurrency: Optional[int] = None,
        **kwargs
    ) -> List[str]:
        """批量调用"""
        ...
    
    def call_sync(
        self,
        prompt: str,
        **kwargs
    ) -> str:
        """同步调用"""
        ...


# ============================================================================
# 任务队列协议
# ============================================================================

@runtime_checkable
class TaskQueueProtocol(Protocol):
    """
    任务队列协议
    
    支持异步任务调度和执行
    """
    
    async def submit(
        self,
        task_name: str,
        task_func: Any,
        *args,
        priority: int = 0,
        **kwargs
    ) -> str:
        """
        提交任务
        
        Args:
            task_name: 任务名称
            task_func: 任务函数
            *args: 位置参数
            priority: 优先级（越大越优先）
            **kwargs: 关键字参数
            
        Returns:
            任务 ID
        """
        ...
    
    async def wait(self, task_id: str, timeout: Optional[float] = None) -> Any:
        """
        等待任务完成
        
        Args:
            task_id: 任务 ID
            timeout: 超时时间
            
        Returns:
            任务结果
        """
        ...
    
    async def cancel(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否成功取消
        """
        ...
    
    def get_status(self, task_id: str) -> str:
        """
        获取任务状态
        
        Args:
            task_id: 任务 ID
            
        Returns:
            任务状态
        """
        ...


# ============================================================================
# 状态存储协议
# ============================================================================

@runtime_checkable
class StateStoreProtocol(Protocol):
    """
    状态存储协议
    
    用于增量处理的状态持久化
    """
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取状态"""
        ...
    
    def set(self, key: str, value: Any) -> None:
        """设置状态"""
        ...
    
    def delete(self, key: str) -> bool:
        """删除状态"""
        ...
    
    def exists(self, key: str) -> bool:
        """检查状态是否存在"""
        ...
    
    def clear(self) -> None:
        """清空所有状态"""
        ...