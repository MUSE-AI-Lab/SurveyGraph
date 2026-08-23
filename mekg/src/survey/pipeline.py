"""
MEKG Survey Pipeline
====================

完整的MEKG驱动综述生成流水线，整合图谱构建、大纲生成、内容撰写和质量评估。

核心设计：
- 大纲生成：使用 MEKG 自己的 MEKGOutlineGenerator（基于图谱结构）
- 内容生成：复用 SurveyX 的 ContentGenerator（保持一致性）
- 后处理：复用 SurveyX 的 PostRefiner
- LaTeX生成：复用 SurveyX 的 LatexGenerator

断点续传功能：
- 每个步骤完成后自动保存检查点
- 支持从任意检查点恢复执行
- 72小时内的检查点有效

使用方法:
    pipeline = MEKGSurveyPipeline(topic="LLM Tool Use")
    result = await pipeline.run()
    
    # 从断点恢复
    result = await pipeline.run(resume=True)
"""

from __future__ import annotations

import asyncio
import glob
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from mekg.src.survey.outline_generator import MEKGOutlineGenerator, SurveyOutline, OutlineSection
from src.configs.config import RELEVANCE_FILTER_MODEL, RELEVANCE_FILTER_WORKERS


class PipelineStep(Enum):
    """
    流水线步骤枚举
    
    细粒度拆分，方便调试和回溯：
    - Step 1: MEKG 数据构建
    - Step 2: 大纲生成
    - Step 2.5: 论文重分类（基于大纲结构优化分类体系）
    - Step 3: Survey 主体内容生成 (ContentGenerator)
    - Step 4: PostRefiner 文本优化
    - Step 5: 表格生成
    - Step 6: 动态视觉元素生成（图表、流程图等）
    - Step 7: 质量评估
    - Step 7.5: 批判性分析增强（新增）
    - Step 8: LaTeX 生成
    - Step 9: 可视化数据导出
    """
    NOT_STARTED = 0
    MEKG_BUILT = 1              # Step 1: MEKG数据构建完成
    OUTLINE_GENERATED = 2       # Step 2: 大纲生成完成
    PAPERS_RECLASSIFIED = 3     # Step 2.5: 论文重分类完成（基于大纲结构优化分类体系）
    CONTENT_GENERATED = 4       # Step 3: Survey主体内容生成完成 (ContentGenerator)
    POST_REFINED = 5            # Step 4: PostRefiner文本优化完成
    TABLES_GENERATED = 6        # Step 5: 表格生成完成
    VISUALS_GENERATED = 7       # Step 6: 动态视觉元素生成完成（图表、流程图等）
    EVALUATED = 8               # Step 7: 评估完成
    CRITICAL_ANALYZED = 9       # Step 7.5: 批判性分析增强完成（新增）
    LATEX_GENERATED = 10        # Step 8: LaTeX生成完成
    VISUALIZATION_DONE = 11     # Step 9: 可视化数据导出完成
    COMPLETED = 12              # 全部完成


# 步骤与生成文件的映射关系
# 用于在恢复执行时清理后续步骤的文件，避免编译冲突
STEP_FILE_MAPPING = {
    # Step 1: MEKG_BUILT - 不清理，这是基础数据
    # Step 2: OUTLINE_GENERATED - 不清理，这是基础数据
    
    # Step 3: CONTENT_GENERATED
    PipelineStep.CONTENT_GENERATED: {
        "files": [
            "tmp/mainbody.tex",
            "tmp/mainbody.raw.tex",
            "tmp/abstract.tex",
            "tmp/mount_details.jpg",
            "tmp/reflection_history.json",
            "tmp/rubric_evaluation.json",
        ],
        "patterns": []
    },
    
    # Step 4: POST_REFINED
    PipelineStep.POST_REFINED: {
        "files": [
            "tmp/mainbody_post_refined.tex",
            "tmp/mainbody_rag_refined.tex",
        ],
        "patterns": []
    },
    
    # Step 5: TABLES_GENERATED
    PipelineStep.TABLES_GENERATED: {
        "files": [
            "latex/benchmark_table.tex",
            "latex/comparison_table.tex",
        ],
        "patterns": [
            "latex/survey_table_*.tex",
            "latex/Arbitrary_table_*.tex",
        ]
    },
    
    # Step 6: VISUALS_GENERATED
    PipelineStep.VISUALS_GENERATED: {
        "files": [
            "tmp/mainbody_enhanced_multimodal.tex",
            "tmp/ai_image_generation_report.md",
            "tmp/enhanced_multimodal_report.md",
            "tmp/visual_elements_summary.md",
        ],
        "patterns": [
            "latex/figs/ai_fig_*.png",
            "ai_generated_images/*",
        ],
        "dirs": [
            "ai_generated_images",
        ]
    },
    
    # Step 7: EVALUATED
    PipelineStep.EVALUATED: {
        "files": [
            "evaluation_report.md",
            "global_reflection.json",
            "evolution_analysis.json",
            "latex/timeline.tex",
        ],
        "patterns": []
    },
    
    # Step 7.5: CRITICAL_ANALYZED
    PipelineStep.CRITICAL_ANALYZED: {
        "files": [
            "tmp/mainbody_critical_enhanced.tex",
            "critical_analysis_report.md",
        ],
        "patterns": []
    },
    
    # Step 8: LATEX_GENERATED
    PipelineStep.LATEX_GENERATED: {
        "files": [
            "latex/survey.tex",
            "latex/survey.synctex.gz",
            "latex/compile.log",
        ],
        "patterns": [
            "latex/*.aux",
            "latex/*.log",
            "latex/*.out",
            "latex/*.toc",
            "latex/*.bbl",
            "latex/*.blg",
            "latex/*.fls",
            "latex/*.fdb_latexmk",
        ]
    },
    
    # Step 9: VISUALIZATION_DONE
    PipelineStep.VISUALIZATION_DONE: {
        "files": [
            "visualization_data.json",
        ],
        "patterns": [
            "visualization/*.png",
            "visualization/*.svg",
        ],
        "dirs": [
            "visualization",
        ]
    },
    
    # Step 10: COMPLETED
    PipelineStep.COMPLETED: {
        "files": [
            "pipeline_result.json",
            "survey.pdf",
            "survey_wtmk.pdf",
        ],
        "patterns": [
            "evaluation/*",
        ],
        "dirs": [
            "evaluation",
        ]
    },
}


# 检查点有效期（72小时）
CHECKPOINT_VALIDITY_HOURS = 72
from mekg.src.survey.content_generator import MEKGContentGenerator
from mekg.src.survey.evaluator import MEKGEvaluator, EvaluationResult

try:
    from mekg.src.processing.relevance_filter import RelevanceFilter
    HAS_RELEVANCE_FILTER = True
except ImportError:
    HAS_RELEVANCE_FILTER = False

try:
    from mekg.src.processing.enhanced_paper_collector import EnhancedPaperCollector
    HAS_ENHANCED_COLLECTOR = True
except ImportError:
    HAS_ENHANCED_COLLECTOR = False

try:
    from src.models.LLM.ChatAgent import ChatAgent
    HAS_CHAT_AGENT = True
except ImportError:
    HAS_CHAT_AGENT = False

try:
    from src.models.generator import LatexGenerator
    HAS_LATEX_GENERATOR = True
except ImportError:
    HAS_LATEX_GENERATOR = False

# 尝试导入 SurveyX 的内容生成器和后处理器
try:
    from src.models.generator.content_generator import ContentGenerator as SurveyXContentGenerator
    from src.schemas.outlines import Outlines as SurveyXOutlines
    HAS_SURVEYX_CONTENT = True
except ImportError:
    HAS_SURVEYX_CONTENT = False

# 尝试导入带反思机制的内容生成器
try:
    from src.models.generator.reflective_content_generator import (
        ReflectiveContentGenerator,
        ReflectionConfig,
        create_reflective_generator
    )
    HAS_REFLECTIVE_GENERATOR = True
except ImportError:
    HAS_REFLECTIVE_GENERATOR = False

# 尝试导入 SurveyX 的数据清洗器（用于论文属性提取）
try:
    from src.modules.preprocessor.data_cleaner import DataCleaner
    HAS_DATA_CLEANER = True
except ImportError:
    HAS_DATA_CLEANER = False

try:
    from src.models.post_refine import PostRefiner
    HAS_POST_REFINER = True
except ImportError:
    HAS_POST_REFINER = False

# 尝试导入新模块 (P1/P2 优化功能)
try:
    from src.modules.outline.hybrid_outline_generator import HybridOutlineGenerator, generate_hybrid_outline
    HAS_HYBRID_OUTLINE = True
except ImportError:
    HAS_HYBRID_OUTLINE = False

try:
    from src.modules.post_refine.global_reflector import GlobalReflector, reflect_survey_global
    HAS_GLOBAL_REFLECTOR = True
except ImportError:
    HAS_GLOBAL_REFLECTOR = False

try:
    from src.modules.analysis.evolutionary_analyzer import EvolutionaryAnalyzer, analyze_evolution
    HAS_EVOLUTIONARY_ANALYZER = True
except ImportError:
    HAS_EVOLUTIONARY_ANALYZER = False

# 尝试导入批判性分析模块 (深度优化功能)
try:
    from src.modules.post_refine.critical_analysis_refiner import CriticalAnalysisRefiner
    HAS_CRITICAL_ANALYZER = True
except ImportError:
    HAS_CRITICAL_ANALYZER = False

# 尝试导入论文重分类模块
try:
    from mekg.src.processing.paper_reclassifier import PaperReclassifier, reclassify_papers
    HAS_PAPER_RECLASSIFIER = True
except ImportError:
    HAS_PAPER_RECLASSIFIER = False


@dataclass
class PipelineConfig:
    """流水线配置"""
    # 基本配置
    topic: str
    output_dir: Path
    task_id: str = ""
    
    # 论文采集配置
    max_papers: int = 100
    year_start: int = 2020
    year_end: int = 2024
    
    # 自定义上传文件配置
    uploaded_files: List[str] = None  # 用户上传的 PDF 文件路径列表
    enable_arxiv: bool = True  # 是否启用 arXiv 搜索（当上传文件数 >= max_papers 时可自动禁用）
    
    # 关键词拆分配置
    use_keyword_split: bool = True        # 是否使用LLM拆分关键词（推荐开启）
    
    # 增强论文收集配置（新增）
    use_enhanced_collector: bool = True   # 是否使用增强版论文收集器（arXiv优先）
    use_survey_strategy: bool = False     # 是否使用 Survey 优先策略（默认关闭，因为参考文献获取不稳定）
    survey_count: int = 10                # 搜索的 survey 数量
    max_refs_per_survey: int = 50         # 每篇 survey 最多获取的参考文献数
    use_embedding_filter: bool = True     # 是否使用 Embedding 筛选
    embedding_threshold: float = 0.3      # Embedding 相似度阈值
    use_openalex: bool = False            # 是否使用 OpenAlex（默认关闭，搜索结果相关性差且PDF难以下载）
    download_pdf: bool = True             # 是否下载 PDF 并解析为 md_text（推荐开启）
    extract_paper_attri: bool = True      # 是否使用 LLM 提取论文属性（idea、method等，推荐开启）
    
    # 图谱构建配置
    use_llm_relations: bool = True
    max_relation_pairs: int = 500
    use_memgraph: bool = False  # 是否使用 Memgraph
    
    # 相关性过滤配置（用于传统收集器）
    enable_relevance_filter: bool = True  # 是否启用相关性过滤
    relevance_threshold: float = 0.2      # 关键词相关性阈值（降低以保留更多论文）
    use_llm_relevance: bool = True        # 是否使用LLM进行相关性判断（推荐开启）
    llm_relevance_model: str = RELEVANCE_FILTER_MODEL  # LLM过滤使用的模型
    llm_relevance_workers: int = RELEVANCE_FILTER_WORKERS
    llm_relevance_threshold: float = 0.5  # LLM相关性阈值
    crawl_multiplier: float = 2.0         # 爬取倍数（爬取 max_papers * multiplier 篇，然后过滤到 max_papers）
    
    # 内容生成配置
    iter_span: int = 10
    max_workers: int = 50                 # 关系发现等 LLM 并发数（从 config.RELATION_DISCOVERY_WORKERS 读取）
    
    # 高级配置 (Agentic Workflow)
    enable_critic_loop: bool = True      # 启用大纲批判循环
    enable_auto_refine: bool = True      # 启用内容自动优化
    min_wcr_threshold: float = 0.7       # 最低核心论文覆盖率阈值
    
    # 内容生成配置
    use_surveyx_content: bool = True     # 使用 SurveyX 的内容生成器（推荐）
    use_surveyx_postrefine: bool = True  # 使用 SurveyX 的后处理器
    
    # 反思机制配置 (P0 优化功能)
    enable_reflection: bool = True       # 启用章节级反思机制
    reflection_max_iterations: int = 3   # 反思最大迭代次数
    reflection_quality_threshold: float = 3.5  # 质量阈值 (1-5 分制)
    enable_global_evaluation: bool = True  # 启用全局评分细则评估
    
    # 新模块配置 (P1/P2 优化功能)
    use_hybrid_outline: bool = True      # 启用混合大纲生成
    use_global_reflector: bool = True    # 启用全局一致性检查
    use_evolutionary_analyzer: bool = True # 启用演化叙事分析
    
    # 批判性分析配置 (深度优化功能 - 默认开启)
    enable_critical_analysis: bool = True  # 启用批判性分析增强
    critical_analysis_auto_enhance: bool = True  # 自动增强问题段落
    
    # 输出配置
    generate_latex: bool = True
    generate_pdf: bool = False
    generate_visualization: bool = True
    
    def __post_init__(self):
        if not self.task_id:
            timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
            topic_slug = self.topic.replace(" ", "_")[:20]
            self.task_id = f"{timestamp}_{topic_slug}"
        
        self.output_dir = Path(self.output_dir)
        
        # 初始化 uploaded_files 为空列表
        if self.uploaded_files is None:
            self.uploaded_files = []


@dataclass
class CheckpointData:
    """检查点数据"""
    step: PipelineStep
    timestamp: str
    task_id: str
    topic: str
    
    # 各步骤的中间结果
    mekg_data: Optional[Dict] = None
    outline_data: Optional[Dict] = None
    content_result: Optional[Dict] = None
    evaluation_data: Optional[Dict] = None
    
    # 统计信息
    papers_count: int = 0
    relations_count: int = 0
    sections_count: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "step": self.step.value,
            "step_name": self.step.name,
            "timestamp": self.timestamp,
            "task_id": self.task_id,
            "topic": self.topic,
            "papers_count": self.papers_count,
            "relations_count": self.relations_count,
            "sections_count": self.sections_count,
            # 注意：大型数据（mekg_data, outline_data等）单独保存，这里只保存元信息
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'CheckpointData':
        return cls(
            step=PipelineStep(data.get("step", 0)),
            timestamp=data.get("timestamp", ""),
            task_id=data.get("task_id", ""),
            topic=data.get("topic", ""),
            papers_count=data.get("papers_count", 0),
            relations_count=data.get("relations_count", 0),
            sections_count=data.get("sections_count", 0)
        )
    
    def is_valid(self) -> bool:
        """检查检查点是否在有效期内（72小时）"""
        if not self.timestamp:
            return False
        try:
            checkpoint_time = datetime.fromisoformat(self.timestamp)
            now = datetime.now()
            hours_diff = (now - checkpoint_time).total_seconds() / 3600
            return hours_diff <= CHECKPOINT_VALIDITY_HOURS
        except:
            return False


@dataclass
class PipelineResult:
    """流水线结果"""
    task_id: str
    topic: str
    success: bool
    
    # 输出路径
    output_dir: Path = None
    mekg_data_path: Path = None
    outline_path: Path = None
    mainbody_path: Path = None
    abstract_path: Path = None
    latex_path: Path = None
    pdf_path: Path = None
    visualization_path: Path = None
    evaluation_report_path: Path = None
    
    # 统计信息
    papers_count: int = 0
    relations_count: int = 0
    sections_count: int = 0
    
    # 评估结果
    evaluation: Optional[EvaluationResult] = None
    
    # 错误信息
    error: str = ""
    
    # 断点续传信息
    resumed_from_step: Optional[PipelineStep] = None
    
    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "topic": self.topic,
            "success": self.success,
            "output_dir": str(self.output_dir) if self.output_dir else None,
            "papers_count": self.papers_count,
            "relations_count": self.relations_count,
            "sections_count": self.sections_count,
            "evaluation": self.evaluation.to_dict() if self.evaluation else None,
            "error": self.error,
            "resumed_from_step": self.resumed_from_step.name if self.resumed_from_step else None
        }


class MEKGSurveyPipeline:
    """
    MEKG驱动的综述生成流水线
    
    完整流程:
    1. 论文采集 (OpenAlex API)
    2. 图谱构建 (关系发现)
    3. 大纲生成 (基于图谱结构)
    4. 内容撰写 (基于图谱关系)
    5. 质量评估 (基于图谱指标)
    6. LaTeX生成 (可选)
    """
    
    def __init__(self, config: PipelineConfig):
        """
        初始化流水线
        
        Args:
            config: 流水线配置
        """
        self.config = config
        self.chat_agent = None
        
        if HAS_CHAT_AGENT:
            try:
                self.chat_agent = ChatAgent()
            except Exception as e:
                print(f"⚠️ 无法创建ChatAgent: {e}")
        
        # 创建输出目录
        self.output_dir = config.output_dir / config.task_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 子目录
        self.mekg_dir = self.output_dir / "mekg"
        self.papers_dir = self.output_dir / "papers"
        self.latex_dir = self.output_dir / "latex"
        self.tmp_dir = self.output_dir / "tmp"
        
        for d in [self.mekg_dir, self.papers_dir, self.latex_dir, self.tmp_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        # 检查点文件路径
        self.checkpoint_path = self.output_dir / "checkpoint.json"
    
    def _clean_tex_content(self, file_path: Path, patterns: List[str]):
        """从 TeX 文件中移除匹配的内容"""
        if not file_path.exists():
            return
        
        try:
            import re
            content = file_path.read_text(encoding='utf-8')
            original_len = len(content)
            
            for pattern in patterns:
                content = re.sub(pattern, "", content, flags=re.MULTILINE)
                
            if len(content) != original_len:
                print(f"      - 清理文件内容: {file_path.name} (移除 {original_len - len(content)} 字符)")
                file_path.write_text(content, encoding='utf-8')
        except Exception as e:
            print(f"   ⚠️ 清理文件内容失败 {file_path.name}: {e}")

    def _clean_subsequent_step_files(self, start_step: PipelineStep):
        """
        清理指定步骤之后所有步骤生成的文件，并恢复对应版本的文件
        
        当从某个检查点恢复执行时：
        1. 删除该步骤之后所有步骤生成的文件，避免后续编译时的冲突
        2. 从备份中恢复 survey.tex 和 mainbody 文件到对应步骤的版本
        3. 清理 mainbody 文件中的无效引用
        
        Args:
            start_step: 恢复执行的起始步骤（该步骤之后的所有文件都会被删除）
        """
        print(f"\n🧹 清理 {start_step.name} (Step {start_step.value}) 之后步骤生成的文件...")
        
        total_deleted_files = 0
        total_deleted_dirs = 0
        
        # 需要清理内容的 tex 文件列表
        tex_files_to_clean = [
            self.tmp_dir / "mainbody_post_refined.tex",
            self.tmp_dir / "mainbody_enhanced_multimodal.tex"
        ]
        
        # 遍历所有步骤，找出需要清理的步骤
        for step in PipelineStep:
            # 只清理 start_step 之后的步骤
            if step.value <= start_step.value:
                continue
            
            # 获取该步骤的文件映射
            step_mapping = STEP_FILE_MAPPING.get(step)
            if not step_mapping:
                continue
            
            step_deleted = 0
            
            # 1. 删除具体文件
            for file_path in step_mapping.get("files", []):
                try:
                    full_path = self.output_dir / file_path
                    if full_path.exists():
                        full_path.unlink()
                        step_deleted += 1
                        total_deleted_files += 1
                        print(f"      - 删除文件: {file_path}")
                except Exception as e:
                    print(f"   ⚠️ 无法删除文件 {file_path}: {e}")
            
            # 2. 删除匹配模式的文件
            for pattern in step_mapping.get("patterns", []):
                try:
                    # 使用 os.path.join 确保路径拼接正确，避免 Path 对象处理通配符的问题
                    import os
                    full_pattern = os.path.join(str(self.output_dir), pattern)
                    matched_files = glob.glob(full_pattern)
                    
                    for matched_file in matched_files:
                        try:
                            matched_path = Path(matched_file)
                            if matched_path.is_file():
                                matched_path.unlink()
                                step_deleted += 1
                                total_deleted_files += 1
                                print(f"      - 删除文件: {matched_path.name}")
                            elif matched_path.is_dir():
                                shutil.rmtree(matched_path)
                                step_deleted += 1
                                total_deleted_dirs += 1
                                print(f"      - 删除目录: {matched_path.name}")
                        except Exception as e:
                            print(f"   ⚠️ 无法删除 {matched_file}: {e}")
                except Exception as e:
                    print(f"   ⚠️ 处理模式 {pattern} 失败: {e}")
            
            # 3. 删除目录（如果指定了）
            for dir_path in step_mapping.get("dirs", []):
                try:
                    full_dir = self.output_dir / dir_path
                    if full_dir.exists() and full_dir.is_dir():
                        shutil.rmtree(full_dir)
                        total_deleted_dirs += 1
                        step_deleted += 1
                        print(f"      - 删除目录: {dir_path}")
                except Exception as e:
                    print(f"   ⚠️ 无法删除目录 {dir_path}: {e}")
            
            # 4. 特殊处理：清理所有 tex 文件中的引用
            # 如果清理了表格生成步骤，移除表格引用
            if step == PipelineStep.TABLES_GENERATED:
                for tex_file in tex_files_to_clean:
                    self._clean_tex_content(tex_file, [
                        r"\\input\{.*?survey_table_.*?\}",
                        r"\\input\{.*?benchmark_table.*?\}",
                        r"\\input\{.*?comparison_table.*?\}",
                        r"\\input\{.*?Arbitrary_table_.*?\}"
                    ])
            
            # 如果清理了视觉生成步骤，移除图片引用
            if step == PipelineStep.VISUALS_GENERATED:
                for tex_file in tex_files_to_clean:
                    self._clean_tex_content(tex_file, [
                        r"\\includegraphics.*?\{.*?ai_fig_.*?\}",
                        r"\\input\{.*?ai_fig_.*?\}",
                        # 清理可能插入的 figure 环境（使用 DOTALL 模式匹配多行）
                        r"\\begin\{figure\}[\s\S]*?ai_fig_[\s\S]*?\\end\{figure\}"
                    ])

            if step_deleted > 0:
                print(f"   ✓ {step.name}: 删除了 {step_deleted} 个文件/目录")
        
        if total_deleted_files > 0 or total_deleted_dirs > 0:
            print(f"   📊 总计: 删除了 {total_deleted_files} 个文件, {total_deleted_dirs} 个目录")
        else:
            print(f"   ✓ 没有需要清理的文件 (所有后续步骤文件已清除或不存在)")
        
        # 5. 从备份恢复 survey.tex 和 mainbody 文件到对应步骤的版本
        print(f"\n🔄 恢复文件到 {start_step.name} 版本...")
        self._restore_survey_tex(start_step)
        self._restore_mainbody_files(start_step)
            
        # 6. 额外检查：修复可能存在的损坏引用
        # 即使从 COMPLETED 恢复，如果表格文件丢失但引用还在，会导致编译失败
        self._fix_broken_references()

    def _fix_broken_references(self):
        """
        检查并修复 mainbody 中的损坏引用
        
        如果 mainbody 引用了不存在的文件（表格、图片等），
        会导致后续 LaTeX 编译失败。此方法会自动移除这些无效引用。
        
        检查的引用类型：
        1. 表格引用: \\input{survey_table_X}, \\input{benchmark_table}, \\input{comparison_table}
        2. 图片引用: \\includegraphics{...ai_fig_...}
        3. 其他 input 引用: \\input{Arbitrary_table_X}
        """
        tex_files = [
            self.tmp_dir / "mainbody_post_refined.tex",
            self.tmp_dir / "mainbody_enhanced_multimodal.tex",
            self.latex_dir / "survey.tex"
        ]
        
        import re
        
        for tex_file in tex_files:
            if not tex_file.exists():
                continue
                
            try:
                content = tex_file.read_text(encoding='utf-8')
                original_content = content
                fixes_made = []
                
                # 1. 检查表格引用 \input{survey_table_X}
                table_refs = set(re.findall(r"\\input\{(survey_table_\d+)\}", content))
                for table_ref in table_refs:
                    table_path = self.latex_dir / f"{table_ref}.tex"
                    if not table_path.exists():
                        fixes_made.append(f"\\input{{{table_ref}}}")
                        content = content.replace(f"\\input{{{table_ref}}}", "")
                
                # 2. 检查 benchmark_table 引用
                if "\\input{benchmark_table}" in content:
                    benchmark_path = self.latex_dir / "benchmark_table.tex"
                    if not benchmark_path.exists():
                        fixes_made.append("\\input{benchmark_table}")
                        content = content.replace("\\input{benchmark_table}", "")
                
                # 3. 检查 comparison_table 引用
                if "\\input{comparison_table}" in content:
                    comparison_path = self.latex_dir / "comparison_table.tex"
                    if not comparison_path.exists():
                        fixes_made.append("\\input{comparison_table}")
                        content = content.replace("\\input{comparison_table}", "")
                
                # 4. 检查 Arbitrary_table 引用
                arbitrary_refs = set(re.findall(r"\\input\{(Arbitrary_table_\d+)\}", content))
                for arb_ref in arbitrary_refs:
                    arb_path = self.latex_dir / f"{arb_ref}.tex"
                    if not arb_path.exists():
                        fixes_made.append(f"\\input{{{arb_ref}}}")
                        content = content.replace(f"\\input{{{arb_ref}}}", "")
                
                # 5. 检查 AI 图片引用 \includegraphics{...ai_fig_...}
                # 匹配 \includegraphics[...]{path/to/ai_fig_X.png} 格式
                ai_fig_pattern = r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*ai_fig_[^}]*)\}"
                ai_fig_refs = set(re.findall(ai_fig_pattern, content))
                for fig_ref in ai_fig_refs:
                    # 尝试多个可能的路径
                    fig_found = False
                    possible_paths = [
                        self.latex_dir / fig_ref,
                        self.latex_dir / "figs" / Path(fig_ref).name,
                        self.output_dir / fig_ref,
                        self.output_dir / "ai_generated_images" / Path(fig_ref).name
                    ]
                    for fig_path in possible_paths:
                        if fig_path.exists():
                            fig_found = True
                            break
                    
                    if not fig_found:
                        # 移除整个 figure 环境（如果存在）
                        # 使用更精确的模式匹配包含该图片的 figure 环境
                        figure_pattern = rf"\\begin\{{figure\}}[\s\S]*?{re.escape(fig_ref)}[\s\S]*?\\end\{{figure\}}"
                        if re.search(figure_pattern, content):
                            fixes_made.append(f"figure containing {fig_ref}")
                            content = re.sub(figure_pattern, "", content)
                        else:
                            # 只移除 includegraphics 命令
                            fixes_made.append(f"\\includegraphics{{...{Path(fig_ref).name}}}")
                            content = re.sub(
                                rf"\\includegraphics(?:\[[^\]]*\])?\{{{re.escape(fig_ref)}\}}",
                                "",
                                content
                            )
                
                # 6. 清理可能残留的空 figure 环境
                empty_figure_pattern = r"\\begin\{figure\}\s*\\centering\s*\\caption\{[^}]*\}\s*\\label\{[^}]*\}\s*\\end\{figure\}"
                if re.search(empty_figure_pattern, content):
                    fixes_made.append("empty figure environments")
                    content = re.sub(empty_figure_pattern, "", content)
                
                # 7. 清理多余的空行（连续3个以上的空行合并为2个）
                content = re.sub(r'\n{4,}', '\n\n\n', content)
                
                if content != original_content:
                    tex_file.write_text(content, encoding='utf-8')
                    if fixes_made:
                        print(f"   🔧 修复 {tex_file.name}: 移除了 {len(fixes_made)} 个无效引用")
                        for fix in fixes_made[:5]:  # 只显示前5个
                            print(f"      - {fix}")
                        if len(fixes_made) > 5:
                            print(f"      - ... 还有 {len(fixes_made) - 5} 个")
                    else:
                        print(f"   ✓ 已清理 {tex_file.name}")
            except Exception as e:
                print(f"   ⚠️ 修复引用失败 {tex_file.name}: {e}")
    
    def _backup_survey_tex(self, step: PipelineStep):
        """
        备份 survey.tex 文件
        
        在每个关键步骤完成后备份当前的 survey.tex，
        以便在恢复检查点时可以恢复到对应版本。
        
        备份文件命名格式: survey.tex.step_{step_value}_{step_name}
        例如: survey.tex.step_5_TABLES_GENERATED
        
        Args:
            step: 当前完成的步骤
        """
        survey_tex_path = self.latex_dir / "survey.tex"
        
        if not survey_tex_path.exists():
            return
        
        # 创建备份目录
        backup_dir = self.latex_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 备份文件名
        backup_name = f"survey.tex.step_{step.value}_{step.name}"
        backup_path = backup_dir / backup_name
        
        try:
            shutil.copy2(survey_tex_path, backup_path)
            print(f"   📦 survey.tex 已备份: {backup_name}")
        except Exception as e:
            print(f"   ⚠️ survey.tex 备份失败: {e}")
    
    def _backup_mainbody_files(self, step: PipelineStep):
        """
        备份 mainbody 相关文件
        
        备份 mainbody_post_refined.tex 和 mainbody_enhanced_multimodal.tex，
        以便在恢复检查点时可以恢复到对应版本。
        
        Args:
            step: 当前完成的步骤
        """
        mainbody_files = [
            "mainbody_post_refined.tex",
            "mainbody_enhanced_multimodal.tex"
        ]
        
        # 创建备份目录
        backup_dir = self.tmp_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        for filename in mainbody_files:
            file_path = self.tmp_dir / filename
            if not file_path.exists():
                continue
            
            # 备份文件名
            backup_name = f"{filename}.step_{step.value}_{step.name}"
            backup_path = backup_dir / backup_name
            
            try:
                shutil.copy2(file_path, backup_path)
                print(f"   📦 {filename} 已备份: {backup_name}")
            except Exception as e:
                print(f"   ⚠️ {filename} 备份失败: {e}")
    
    def _restore_survey_tex(self, step: PipelineStep):
        """
        从备份恢复 survey.tex 文件
        
        在恢复检查点时，从备份中恢复对应步骤的 survey.tex 版本。
        
        Args:
            step: 要恢复到的步骤
        """
        backup_dir = self.latex_dir / "backups"
        
        if not backup_dir.exists():
            print(f"   ⚠️ 没有找到 survey.tex 备份目录")
            return False
        
        # 查找对应步骤的备份
        backup_name = f"survey.tex.step_{step.value}_{step.name}"
        backup_path = backup_dir / backup_name
        
        if backup_path.exists():
            survey_tex_path = self.latex_dir / "survey.tex"
            try:
                shutil.copy2(backup_path, survey_tex_path)
                print(f"   🔄 survey.tex 已恢复到: {step.name}")
                return True
            except Exception as e:
                print(f"   ⚠️ survey.tex 恢复失败: {e}")
                return False
        else:
            # 尝试查找最近的较早步骤的备份
            print(f"   ⚠️ 没有找到 {step.name} 的 survey.tex 备份，尝试查找较早的备份...")
            
            # 按步骤值从高到低查找
            for earlier_step in reversed(list(PipelineStep)):
                if earlier_step.value >= step.value:
                    continue
                
                earlier_backup_name = f"survey.tex.step_{earlier_step.value}_{earlier_step.name}"
                earlier_backup_path = backup_dir / earlier_backup_name
                
                if earlier_backup_path.exists():
                    survey_tex_path = self.latex_dir / "survey.tex"
                    try:
                        shutil.copy2(earlier_backup_path, survey_tex_path)
                        print(f"   🔄 survey.tex 已恢复到较早版本: {earlier_step.name}")
                        return True
                    except Exception as e:
                        print(f"   ⚠️ survey.tex 恢复失败: {e}")
                        return False
            
            print(f"   ⚠️ 没有找到任何可用的 survey.tex 备份")
            return False
    
    def _restore_mainbody_files(self, step: PipelineStep):
        """
        从备份恢复 mainbody 相关文件
        
        在恢复检查点时，从备份中恢复对应步骤的 mainbody 文件版本。
        
        Args:
            step: 要恢复到的步骤
        """
        backup_dir = self.tmp_dir / "backups"
        
        if not backup_dir.exists():
            print(f"   ⚠️ 没有找到 mainbody 备份目录")
            return
        
        mainbody_files = [
            "mainbody_post_refined.tex",
            "mainbody_enhanced_multimodal.tex"
        ]
        
        for filename in mainbody_files:
            # 查找对应步骤的备份
            backup_name = f"{filename}.step_{step.value}_{step.name}"
            backup_path = backup_dir / backup_name
            
            if backup_path.exists():
                file_path = self.tmp_dir / filename
                try:
                    shutil.copy2(backup_path, file_path)
                    print(f"   🔄 {filename} 已恢复到: {step.name}")
                except Exception as e:
                    print(f"   ⚠️ {filename} 恢复失败: {e}")
            else:
                # 尝试查找最近的较早步骤的备份
                for earlier_step in reversed(list(PipelineStep)):
                    if earlier_step.value >= step.value:
                        continue
                    
                    earlier_backup_name = f"{filename}.step_{earlier_step.value}_{earlier_step.name}"
                    earlier_backup_path = backup_dir / earlier_backup_name
                    
                    if earlier_backup_path.exists():
                        file_path = self.tmp_dir / filename
                        try:
                            shutil.copy2(earlier_backup_path, file_path)
                            print(f"   🔄 {filename} 已恢复到较早版本: {earlier_step.name}")
                            break
                        except Exception as e:
                            print(f"   ⚠️ {filename} 恢复失败: {e}")
                            break

    def _save_checkpoint(self, step: PipelineStep, **kwargs):
        """
        保存检查点
        
        Args:
            step: 当前完成的步骤
            **kwargs: 额外的状态数据
        """
        checkpoint = CheckpointData(
            step=step,
            timestamp=datetime.now().isoformat(),
            task_id=self.config.task_id,
            topic=self.config.topic,
            papers_count=kwargs.get("papers_count", 0),
            relations_count=kwargs.get("relations_count", 0),
            sections_count=kwargs.get("sections_count", 0)
        )
        
        # 保存检查点元信息
        with open(self.checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(checkpoint.to_dict(), f, ensure_ascii=False, indent=2)
        
        # 备份 survey.tex 和 mainbody 文件
        self._backup_survey_tex(step)
        self._backup_mainbody_files(step)
        
        print(f"   💾 检查点已保存: {step.name}")
    
    def _load_checkpoint(self) -> Optional[CheckpointData]:
        """
        加载检查点
        
        Returns:
            CheckpointData 或 None（如果没有有效检查点）
        """
        if not self.checkpoint_path.exists():
            return None
        
        try:
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            checkpoint = CheckpointData.from_dict(data)
            
            # 检查有效期
            if not checkpoint.is_valid():
                print(f"   ⚠️ 检查点已过期（超过{CHECKPOINT_VALIDITY_HOURS}小时）")
                return None
            
            return checkpoint
        except Exception as e:
            print(f"   ⚠️ 加载检查点失败: {e}")
            return None
    
    def _load_mekg_data(self) -> Optional[Dict]:
        """从文件加载MEKG数据"""
        mekg_data_path = self.mekg_dir / "mekg_data.json"
        if mekg_data_path.exists():
            with open(mekg_data_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    
    def _load_outline(self) -> Optional[SurveyOutline]:
        """从文件加载大纲"""
        outline_path = self.output_dir / "outline.json"
        if outline_path.exists():
            return SurveyOutline.load(outline_path)
        return None
    
    def _load_content_result(self) -> Optional[Dict]:
        """从文件加载内容结果"""
        from src.modules.utils import load_file_as_string
        
        mainbody_path = self.tmp_dir / "mainbody.tex"
        if not mainbody_path.exists():
            mainbody_path = self.tmp_dir / "mainbody_post_refined.tex"
        
        abstract_path = self.tmp_dir / "abstract.tex"
        
        if not mainbody_path.exists():
            return None
        
        mainbody = load_file_as_string(mainbody_path) if mainbody_path.exists() else ""
        abstract = load_file_as_string(abstract_path) if abstract_path.exists() else ""
        
        return {
            "mainbody": mainbody,
            "abstract": abstract
        }
    
    async def run(
        self,
        mekg_data: Optional[Dict] = None,
        skip_collection: bool = False,
        resume: bool = False
    ) -> PipelineResult:
        """
        运行完整流水线
        
        Args:
            mekg_data: 预先构建的MEKG数据（可选，跳过采集和构建）
            skip_collection: 是否跳过论文采集
            resume: 是否从断点恢复（72小时内有效）
            
        Returns:
            PipelineResult对象
        """
        result = PipelineResult(
            task_id=self.config.task_id,
            topic=self.config.topic,
            success=False,
            output_dir=self.output_dir
        )
        
        # 检查是否有可恢复的检查点
        checkpoint = None
        start_step = PipelineStep.NOT_STARTED
        outline = None
        content_result = None
        
        if resume:
            checkpoint = self._load_checkpoint()
            if checkpoint:
                start_step = checkpoint.step
                result.resumed_from_step = start_step
                print(f"\n🔄 从检查点恢复: {start_step.name}")
                print(f"   检查点时间: {checkpoint.timestamp}")
                
                # 加载已有数据
                if start_step.value >= PipelineStep.MEKG_BUILT.value:
                    mekg_data = self._load_mekg_data()
                    result.papers_count = checkpoint.papers_count
                    result.relations_count = checkpoint.relations_count
                
                if start_step.value >= PipelineStep.OUTLINE_GENERATED.value:
                    outline = self._load_outline()
                    result.sections_count = checkpoint.sections_count
                
                if start_step.value >= PipelineStep.CONTENT_GENERATED.value:
                    content_result = self._load_content_result()
                
                # 清理后续步骤的文件，避免编译冲突
                self._clean_subsequent_step_files(start_step)
        
        try:
            print("=" * 60)
            print(f"🚀 MEKG Survey Pipeline")
            print(f"   Topic: {self.config.topic}")
            print(f"   Task ID: {self.config.task_id}")
            if resume and checkpoint:
                print(f"   📍 从 {start_step.name} 之后继续")
            print("=" * 60)
            
            # Step 1: 获取或构建MEKG数据
            if start_step.value < PipelineStep.MEKG_BUILT.value:
                if mekg_data is None:
                    if skip_collection:
                        # 尝试从文件加载
                        mekg_data_path = self.mekg_dir / "mekg_data.json"
                        if mekg_data_path.exists():
                            print("\n📂 加载已有MEKG数据...")
                            with open(mekg_data_path, 'r', encoding='utf-8') as f:
                                mekg_data = json.load(f)
                        else:
                            raise FileNotFoundError(f"MEKG数据文件不存在: {mekg_data_path}")
                    else:
                        print("\n📥 Step 1: 论文采集与图谱构建...")
                        mekg_data = await self._build_mekg()
                
                # 保存MEKG数据
                mekg_data_path = self.mekg_dir / "mekg_data.json"
                with open(mekg_data_path, 'w', encoding='utf-8') as f:
                    json.dump(mekg_data, f, ensure_ascii=False, indent=2)
                result.mekg_data_path = mekg_data_path
                result.papers_count = len(mekg_data.get("papers", []))
                result.relations_count = len(mekg_data.get("relations", []))
                
                print(f"   ✓ 论文数: {result.papers_count}")
                print(f"   ✓ 关系数: {result.relations_count}")
                
                # 保存检查点
                self._save_checkpoint(
                    PipelineStep.MEKG_BUILT,
                    papers_count=result.papers_count,
                    relations_count=result.relations_count
                )
            else:
                print("\n✅ Step 1: 已从检查点恢复MEKG数据")
                print(f"   ✓ 论文数: {result.papers_count}")
                print(f"   ✓ 关系数: {result.relations_count}")
            
            # Step 2: 生成大纲
            if start_step.value < PipelineStep.OUTLINE_GENERATED.value:
                print("\n📋 Step 2: 生成大纲...")
                outline = self._generate_outline(mekg_data)
                
                outline_path = self.output_dir / "outline.json"
                outline.save(outline_path)
                result.outline_path = outline_path
                result.sections_count = len(outline.sections)
                
                print(f"   ✓ 章节数: {result.sections_count}")
                
                # 同时保存SurveyX格式的大纲
                surveyx_outline = outline.to_surveyx_format()
                surveyx_outline_path = self.output_dir / "outlines.json"
                with open(surveyx_outline_path, 'w', encoding='utf-8') as f:
                    json.dump(surveyx_outline, f, ensure_ascii=False, indent=2)
                
                # 保存检查点
                self._save_checkpoint(
                    PipelineStep.OUTLINE_GENERATED,
                    papers_count=result.papers_count,
                    relations_count=result.relations_count,
                    sections_count=result.sections_count
                )
            else:
                print("\n✅ Step 2: 已从检查点恢复大纲")
                print(f"   ✓ 章节数: {result.sections_count}")
                result.outline_path = self.output_dir / "outline.json"
            
            # Step 2.5: 论文重分类（基于大纲结构优化分类体系）
            if HAS_PAPER_RECLASSIFIER:
                if start_step.value < PipelineStep.PAPERS_RECLASSIFIED.value:
                    print("\n🔄 Step 2.5: 论文重分类（基于大纲结构优化分类体系）...")
                    
                    try:
                        # 获取大纲数据
                        outline_data = outline.to_dict() if hasattr(outline, 'to_dict') else {
                            "title": outline.title,
                            "topic": outline.topic,
                            "sections": [
                                {
                                    "number": s.number,
                                    "title": s.title,
                                    "description": s.description,
                                    "subsections": [
                                        {
                                            "number": sub.number,
                                            "title": sub.title,
                                            "description": sub.description
                                        }
                                        for sub in (s.subsections or [])
                                    ]
                                }
                                for s in outline.sections
                            ]
                        }
                        
                        # 执行重分类
                        reclassifier = PaperReclassifier(
                            chat_agent=self.chat_agent,
                            max_workers=self.config.max_workers
                        )
                        mekg_data = reclassifier.reclassify(
                            mekg_data=mekg_data,
                            outline_data=outline_data,
                            topic=self.config.topic,
                            verbose=True
                        )
                        
                        # 保存更新后的 MEKG 数据
                        mekg_data_path = self.mekg_dir / "mekg_data.json"
                        with open(mekg_data_path, 'w', encoding='utf-8') as f:
                            json.dump(mekg_data, f, ensure_ascii=False, indent=2)
                        
                        print(f"   ✓ 论文重分类完成，分类体系已更新")
                        
                    except Exception as e:
                        print(f"   ⚠️ 论文重分类失败: {e}（继续使用原分类）")
                        import traceback
                        traceback.print_exc()
                    
                    # 保存检查点
                    self._save_checkpoint(
                        PipelineStep.PAPERS_RECLASSIFIED,
                        papers_count=result.papers_count,
                        relations_count=result.relations_count,
                        sections_count=result.sections_count
                    )
                else:
                    print("\n✅ Step 2.5: 已从检查点恢复论文重分类结果")
            else:
                # 如果重分类模块不可用，直接跳过并保存检查点
                if start_step.value < PipelineStep.PAPERS_RECLASSIFIED.value:
                    print("\n⏭️ Step 2.5: 跳过论文重分类（模块不可用）")
                    self._save_checkpoint(
                        PipelineStep.PAPERS_RECLASSIFIED,
                        papers_count=result.papers_count,
                        relations_count=result.relations_count,
                        sections_count=result.sections_count
                    )
            
            # Step 3: 生成Survey主体内容 (ContentGenerator)
            if start_step.value < PipelineStep.CONTENT_GENERATED.value:
                print("\n✍️ Step 3: 生成Survey主体内容 (ContentGenerator)...")
                content_result = self._generate_content_only(outline, mekg_data)
                
                result.mainbody_path = self.tmp_dir / "mainbody.tex"
                result.abstract_path = self.tmp_dir / "abstract.tex"
                
                print(f"   ✓ 主体内容: {len(content_result.get('mainbody', ''))} 字符")
                
                # 保存检查点
                self._save_checkpoint(
                    PipelineStep.CONTENT_GENERATED,
                    papers_count=result.papers_count,
                    relations_count=result.relations_count,
                    sections_count=result.sections_count
                )
            else:
                print("\n✅ Step 3: 已从检查点恢复Survey主体内容")
                result.mainbody_path = self.tmp_dir / "mainbody.tex"
                result.abstract_path = self.tmp_dir / "abstract.tex"
                if not content_result:
                    content_result = self._load_content_result()
                if content_result:
                    print(f"   ✓ 主体内容: {len(content_result.get('mainbody', ''))} 字符")
            
            # Step 4-6: PostRefiner 相关步骤
            # 为了避免重复 embedding（每次约45秒），在这里统一初始化 PostRefiner
            # 然后在 Step 4、5、6 中复用同一个实例
            #
            # 关键优化：只有当真正需要执行某个步骤时才初始化 PostRefiner
            # - 如果从 TABLES_GENERATED 恢复，只需要执行 Step 6，此时才初始化
            # - 如果从 POST_REFINED 恢复，需要执行 Step 5 和 6，此时才初始化
            # - 如果从 CONTENT_GENERATED 恢复，需要执行 Step 4、5、6，此时才初始化
            post_refiner = None
            
            # 判断是否需要初始化 PostRefiner
            # 🔧 Step 4 已禁用，只有当需要执行 Step 5 或 6 时才初始化
            need_post_refiner = (
                self.config.use_surveyx_postrefine and
                HAS_POST_REFINER and
                (
                    # Step 4（文本优化）已禁用，不再需要为此初始化
                    # start_step.value < PipelineStep.POST_REFINED.value or
                    # 需要执行 Step 5（表格生成）
                    start_step.value < PipelineStep.TABLES_GENERATED.value or
                    # 需要执行 Step 6（动态视觉元素生成）
                    start_step.value < PipelineStep.VISUALS_GENERATED.value
                )
            )
            
            if need_post_refiner:
                # 进一步检查：如果 Step 4 和 Step 5 都已完成，只需要执行 Step 6
                # 此时检查 Step 6 是否真的需要执行（即是否已有结果）
                if start_step.value >= PipelineStep.TABLES_GENERATED.value:
                    # 从 TABLES_GENERATED 恢复，检查 Step 6 是否已完成
                    enhanced_multimodal_path = self.tmp_dir / "mainbody_enhanced_multimodal.tex"
                    if enhanced_multimodal_path.exists() and enhanced_multimodal_path.stat().st_size > 0:
                        need_post_refiner = False
            
            if need_post_refiner:
                print("\n🔧 初始化 PostRefiner（复用于 Step 4-6，避免重复 embedding）...")
                try:
                    post_refiner = PostRefiner(
                        task_id=self.config.task_id,
                        chat_agent=self.chat_agent,
                        enable_dynamic_visuals=True,
                        enable_reference_images=True
                    )
                    print("   ✅ PostRefiner 初始化完成")
                except Exception as e:
                    print(f"   ❌ PostRefiner 初始化失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Step 4: PostRefiner 文本优化
            # 🔧 已禁用：跳过 RagRefiner + SectionRewriter + FigureBuilder + RuleBasedRefiner
            # 这些步骤会进行引用增强和内容压缩，但耗时较长
            # 如需启用，取消下方注释
            #
            # if self.config.use_surveyx_postrefine and HAS_POST_REFINER:
            #     if start_step.value < PipelineStep.POST_REFINED.value:
            #         print("\n🔧 Step 4: PostRefiner 文本优化...")
            #         self._run_post_refine_text(outline, post_refiner)
            #
            #         # 重新加载优化后的内容
            #         content_result = self._load_content_result()
            #
            #         print(f"   ✓ 文本优化完成")
            #
            #         # 保存检查点
            #         self._save_checkpoint(
            #             PipelineStep.POST_REFINED,
            #             papers_count=result.papers_count,
            #             relations_count=result.relations_count,
            #             sections_count=result.sections_count
            #         )
            #     else:
            #         print("\n✅ Step 4: 已从检查点恢复PostRefiner文本优化结果")
            #         if not content_result:
            #             content_result = self._load_content_result()
            # else:
            #     # 如果不使用 PostRefiner，直接跳过并保存检查点
            #     if start_step.value < PipelineStep.POST_REFINED.value:
            #         print("\n⏭️ Step 4: 跳过PostRefiner文本优化（未启用）")
            #         self._save_checkpoint(
            #             PipelineStep.POST_REFINED,
            #             papers_count=result.papers_count,
            #             relations_count=result.relations_count,
            #             sections_count=result.sections_count
            #         )
            
            # 🔧 Step 4 已禁用，直接跳过并保存检查点
            if start_step.value < PipelineStep.POST_REFINED.value:
                print("\n⏭️ Step 4: 跳过PostRefiner文本优化（已禁用，直接使用 mainbody.tex）")
                
                # 将 mainbody.tex 复制为 mainbody_post_refined.tex，供后续步骤使用
                mainbody_path = self.tmp_dir / "mainbody.tex"
                post_refined_path = self.tmp_dir / "mainbody_post_refined.tex"
                if mainbody_path.exists() and not post_refined_path.exists():
                    import shutil
                    shutil.copy(mainbody_path, post_refined_path)
                    print(f"   📋 已复制 mainbody.tex -> mainbody_post_refined.tex")
                
                self._save_checkpoint(
                    PipelineStep.POST_REFINED,
                    papers_count=result.papers_count,
                    relations_count=result.relations_count,
                    sections_count=result.sections_count
                )
            else:
                print("\n✅ Step 4: 已从检查点恢复（文本优化已禁用）")
                if not content_result:
                    content_result = self._load_content_result()
            
            # Step 5: 表格生成
            if self.config.use_surveyx_postrefine and HAS_POST_REFINER:
                if start_step.value < PipelineStep.TABLES_GENERATED.value:
                    print("\n📊 Step 5: 生成表格...")
                    self._run_generate_tables(post_refiner)
                    
                    print(f"   ✓ 表格生成完成")
                    
                    # 保存检查点
                    self._save_checkpoint(
                        PipelineStep.TABLES_GENERATED,
                        papers_count=result.papers_count,
                        relations_count=result.relations_count,
                        sections_count=result.sections_count
                    )
                else:
                    print("\n✅ Step 5: 已从检查点恢复表格生成结果")
            else:
                # 如果不使用 PostRefiner，直接跳过并保存检查点
                if start_step.value < PipelineStep.TABLES_GENERATED.value:
                    print("\n⏭️ Step 5: 跳过表格生成（未启用PostRefiner）")
                    self._save_checkpoint(
                        PipelineStep.TABLES_GENERATED,
                        papers_count=result.papers_count,
                        relations_count=result.relations_count,
                        sections_count=result.sections_count
                    )
            
            # Step 6: 动态视觉元素生成（图表、流程图等）
            if self.config.use_surveyx_postrefine and HAS_POST_REFINER:
                if start_step.value < PipelineStep.VISUALS_GENERATED.value:
                    print("\n🎨 Step 6: 生成动态视觉元素（图表、流程图等）...")
                    self._run_generate_dynamic_visuals(post_refiner)
                    
                    # 重新加载内容（可能包含新插入的图表）
                    content_result = self._load_content_result()
                    
                    print(f"   ✓ 动态视觉元素生成完成")
                    
                    # 保存检查点
                    self._save_checkpoint(
                        PipelineStep.VISUALS_GENERATED,
                        papers_count=result.papers_count,
                        relations_count=result.relations_count,
                        sections_count=result.sections_count
                    )
                else:
                    print("\n✅ Step 6: 已从检查点恢复动态视觉元素")
                    if not content_result:
                        content_result = self._load_content_result()
            else:
                # 如果不使用 PostRefiner，直接跳过并保存检查点
                if start_step.value < PipelineStep.VISUALS_GENERATED.value:
                    print("\n⏭️ Step 6: 跳过动态视觉元素生成（未启用PostRefiner）")
                    self._save_checkpoint(
                        PipelineStep.VISUALS_GENERATED,
                        papers_count=result.papers_count,
                        relations_count=result.relations_count,
                        sections_count=result.sections_count
                    )
            
            # Step 7: 质量评估与全局反思（并行执行）
            if start_step.value < PipelineStep.EVALUATED.value:
                print("\n📊 Step 7: 质量评估与全局反思（并行执行）...")
                if not content_result:
                    content_result = self._load_content_result()
                
                # 并行执行评估任务
                evaluation, global_result, evolution_result = await self._run_evaluation_parallel(
                    mekg_data, content_result, outline
                )
                
                result.evaluation = evaluation
                
                # 保存评估报告
                evaluation_report_path = self.output_dir / "evaluation_report.md"
                evaluator = MEKGEvaluator(mekg_data)
                evaluator.generate_report(evaluation, evaluation_report_path)
                result.evaluation_report_path = evaluation_report_path
                
                print(f"   ✓ 综合得分: {evaluation.overall_score:.4f}")
                
                # 保存全局反思结果（如果有）
                if global_result:
                    global_reflection_path = self.output_dir / "global_reflection.json"
                    with open(global_reflection_path, 'w', encoding='utf-8') as f:
                        json.dump(global_result.to_dict(), f, ensure_ascii=False, indent=2)
                    print(f"   ✓ 全局反思完成: 评分={global_result.overall_score:.2f}")
                
                # 保存演化分析结果（如果有）
                if evolution_result:
                    evolution_path = self.output_dir / "evolution_analysis.json"
                    with open(evolution_path, 'w', encoding='utf-8') as f:
                        json.dump(evolution_result.to_dict(), f, ensure_ascii=False, indent=2)
                    
                    # 生成时间线 LaTeX
                    try:
                        analyzer = EvolutionaryAnalyzer(chat_agent=self.chat_agent)
                        timeline_latex = analyzer.generate_timeline_latex(evolution_result)
                        timeline_path = self.latex_dir / "timeline.tex"
                        with open(timeline_path, 'w', encoding='utf-8') as f:
                            f.write(timeline_latex)
                    except Exception as e:
                        print(f"   ⚠️ 时间线生成失败: {e}")
                    
                    print(f"   ✓ 演化分析完成: {len(evolution_result.timeline)} 个里程碑")
                
                # 保存检查点
                self._save_checkpoint(
                    PipelineStep.EVALUATED,
                    papers_count=result.papers_count,
                    relations_count=result.relations_count,
                    sections_count=result.sections_count
                )
            else:
                print("\n✅ Step 7: 已从检查点恢复评估结果")
                result.evaluation_report_path = self.output_dir / "evaluation_report.md"
            
            # Step 7.5: 批判性分析增强（深度优化功能）
            if self.config.enable_critical_analysis and HAS_CRITICAL_ANALYZER:
                if start_step.value < PipelineStep.CRITICAL_ANALYZED.value:
                    print("\n🔬 Step 7.5: 批判性分析增强...")
                    if not content_result:
                        content_result = self._load_content_result()
                    
                    try:
                        # 执行批判性分析
                        critical_result = self._run_critical_analysis(content_result)
                        
                        # 如果有增强后的内容，更新 content_result
                        if critical_result and critical_result.get("enhanced_content"):
                            # 保存增强后的内容
                            enhanced_path = self.tmp_dir / "mainbody_critical_enhanced.tex"
                            with open(enhanced_path, 'w', encoding='utf-8') as f:
                                f.write(critical_result["enhanced_content"])
                            
                            # 更新 content_result
                            content_result["mainbody"] = critical_result["enhanced_content"]
                            
                            print(f"   ✓ 批判性分析完成: 增强了 {critical_result.get('enhanced_count', 0)} 个段落")
                        else:
                            print(f"   ✓ 批判性分析完成: 内容质量良好，无需增强")
                        
                        # 保存分析报告
                        if critical_result and critical_result.get("report"):
                            report_path = self.output_dir / "critical_analysis_report.md"
                            with open(report_path, 'w', encoding='utf-8') as f:
                                f.write(critical_result["report"])
                            print(f"   ✓ 分析报告已保存: {report_path}")
                        
                    except Exception as e:
                        print(f"   ⚠️ 批判性分析失败: {e}")
                        import traceback
                        traceback.print_exc()
                    
                    # 保存检查点
                    self._save_checkpoint(
                        PipelineStep.CRITICAL_ANALYZED,
                        papers_count=result.papers_count,
                        relations_count=result.relations_count,
                        sections_count=result.sections_count
                    )
                else:
                    print("\n✅ Step 7.5: 已从检查点恢复批判性分析结果")
                    # 尝试加载增强后的内容
                    enhanced_path = self.tmp_dir / "mainbody_critical_enhanced.tex"
                    if enhanced_path.exists():
                        from src.modules.utils import load_file_as_string
                        content_result["mainbody"] = load_file_as_string(enhanced_path)
            else:
                # 如果未启用批判性分析，直接跳过并保存检查点
                if start_step.value < PipelineStep.CRITICAL_ANALYZED.value:
                    if not self.config.enable_critical_analysis:
                        print("\n⏭️ Step 7.5: 跳过批判性分析（未启用）")
                    elif not HAS_CRITICAL_ANALYZER:
                        print("\n⏭️ Step 7.5: 跳过批判性分析（模块不可用）")
                    
                    self._save_checkpoint(
                        PipelineStep.CRITICAL_ANALYZED,
                        papers_count=result.papers_count,
                        relations_count=result.relations_count,
                        sections_count=result.sections_count
                    )
            
            # Step 8: 生成LaTeX（可选）
            if self.config.generate_latex:
                if start_step.value < PipelineStep.LATEX_GENERATED.value:
                    print("\n📄 Step 8: 生成LaTeX...")
                    if not content_result:
                        content_result = self._load_content_result()
                    latex_path = self._generate_latex(outline, content_result)
                    result.latex_path = latex_path
                    print(f"   ✓ LaTeX: {latex_path}")
                    
                    # 保存检查点
                    self._save_checkpoint(
                        PipelineStep.LATEX_GENERATED,
                        papers_count=result.papers_count,
                        relations_count=result.relations_count,
                        sections_count=result.sections_count
                    )
                else:
                    print("\n✅ Step 8: 已从检查点恢复LaTeX")
                    result.latex_path = self.latex_dir / "survey.tex"
            
            # Step 9: 生成可视化数据导出（可选）
            if self.config.generate_visualization:
                if start_step.value < PipelineStep.VISUALIZATION_DONE.value:
                    print("\n📈 Step 9: 生成可视化数据导出...")
                    vis_path = self._generate_visualization(mekg_data, outline)
                    result.visualization_path = vis_path
                    print(f"   ✓ 可视化: {vis_path}")
                    
                    # 保存检查点
                    self._save_checkpoint(
                        PipelineStep.VISUALIZATION_DONE,
                        papers_count=result.papers_count,
                        relations_count=result.relations_count,
                        sections_count=result.sections_count
                    )
                else:
                    print("\n✅ Step 9: 已从检查点恢复可视化数据")
                    result.visualization_path = self.output_dir / "visualization_data.json"
            
            # 保存论文数据（供SurveyX后续流程使用）
            self._save_papers_for_surveyx(mekg_data)
            
            # 最终检查点
            self._save_checkpoint(
                PipelineStep.COMPLETED,
                papers_count=result.papers_count,
                relations_count=result.relations_count,
                sections_count=result.sections_count
            )
            
            result.success = True
            
            print("\n" + "=" * 60)
            print("✅ Pipeline completed successfully!")
            print(f"   Output: {self.output_dir}")
            if result.resumed_from_step:
                print(f"   📍 从 {result.resumed_from_step.name} 恢复执行")
            print("=" * 60)
            
        except Exception as e:
            import traceback
            result.error = str(e)
            print(f"\n❌ Pipeline failed: {e}")
            print(f"   💡 提示: 可以使用 resume=True 从断点恢复")
            traceback.print_exc()
        
        # 保存结果摘要
        summary_path = self.output_dir / "pipeline_result.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        
        return result
    
    async def _build_mekg(self) -> Dict:
        """构建MEKG图谱"""
        # 如果有用户上传的文件，优先处理
        uploaded_papers = []
        if self.config.uploaded_files:
            print(f"   📂 处理用户上传的 {len(self.config.uploaded_files)} 个文件...")
            uploaded_papers = await self._process_uploaded_files(self.config.uploaded_files)
            print(f"   ✓ 成功解析 {len(uploaded_papers)} 篇上传的论文")
        
        # 判断是否需要 arXiv 补充
        # 如果上传的论文数量 >= max_papers，则不需要 arXiv 搜索
        need_arxiv = self.config.enable_arxiv and len(uploaded_papers) < self.config.max_papers
        
        if not need_arxiv:
            if len(uploaded_papers) >= self.config.max_papers:
                print(f"   ℹ️ 上传论文数量 ({len(uploaded_papers)}) >= 目标数量 ({self.config.max_papers})，跳过 arXiv 搜索")
            else:
                print(f"   ℹ️ arXiv 搜索已禁用")
            
            # 只使用上传的论文
            return await self._build_mekg_from_papers(uploaded_papers)
        
        # 需要 arXiv 补充
        remaining_count = self.config.max_papers - len(uploaded_papers)
        print(f"   🔍 需要从 arXiv 补充 {remaining_count} 篇论文...")
        
        # 使用增强版或传统收集器获取额外论文
        if self.config.use_enhanced_collector and HAS_ENHANCED_COLLECTOR:
            arxiv_papers = await self._collect_arxiv_papers(remaining_count)
        else:
            arxiv_papers = await self._collect_legacy_papers(remaining_count)
        
        # 合并上传的论文和 arXiv 论文
        all_papers = uploaded_papers + arxiv_papers
        print(f"   ✓ 总计 {len(all_papers)} 篇论文（上传: {len(uploaded_papers)}, arXiv: {len(arxiv_papers)}）")
        
        return await self._build_mekg_from_papers(all_papers)
    
    async def _process_uploaded_files(self, file_paths: List[str]) -> List[Dict]:
        """
        处理用户上传的 PDF 文件
        
        自定义上传的文件直接解析，不需要粗筛精筛。
        
        Args:
            file_paths: PDF 文件路径列表
            
        Returns:
            解析后的论文列表
        """
        papers = []
        
        try:
            from mekg.src.processing.pdf_parser import PDFParser
            parser = PDFParser()
        except ImportError:
            print("   ⚠️ PDFParser 不可用，尝试使用备用解析器")
            parser = None
        
        for i, file_path in enumerate(file_paths):
            try:
                file_path = Path(file_path)
                if not file_path.exists():
                    print(f"   ⚠️ 文件不存在: {file_path}")
                    continue
                
                print(f"   📄 解析 [{i+1}/{len(file_paths)}]: {file_path.name}")
                
                # 解析 PDF
                if parser:
                    paper_data = parser.parse(str(file_path))
                else:
                    # 备用解析方案
                    paper_data = await self._parse_pdf_fallback(file_path)
                
                if paper_data:
                    # 标记为用户上传的论文
                    paper_data["source"] = "uploaded"
                    paper_data["is_uploaded"] = True
                    paper_data["uploaded_path"] = str(file_path)
                    
                    # 生成唯一 ID
                    if not paper_data.get("id") and not paper_data.get("paper_id"):
                        paper_data["paper_id"] = f"uploaded_{file_path.stem}"
                    
                    papers.append(paper_data)
                    
            except Exception as e:
                print(f"   ⚠️ 解析失败 {file_path}: {e}")
                continue
        
        return papers
    
    async def _parse_pdf_fallback(self, file_path: Path) -> Optional[Dict]:
        """
        备用 PDF 解析方案
        
        当主解析器不可用时使用。
        """
        try:
            import fitz  # PyMuPDF
            
            doc = fitz.open(str(file_path))
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            
            # 尝试从文本中提取标题（通常是第一行非空文本）
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            title = lines[0] if lines else file_path.stem
            
            # 尝试提取摘要
            abstract = ""
            abstract_start = text.lower().find("abstract")
            if abstract_start != -1:
                abstract_end = text.lower().find("introduction", abstract_start)
                if abstract_end == -1:
                    abstract_end = abstract_start + 2000
                abstract = text[abstract_start:abstract_end].strip()
            
            return {
                "paper_id": f"uploaded_{file_path.stem}",
                "title": title[:200],  # 限制标题长度
                "abstract": abstract[:2000],  # 限制摘要长度
                "md_text": text,
                "year": None,
                "authors": [],
                "source": "uploaded"
            }
            
        except ImportError:
            print("   ⚠️ PyMuPDF 不可用，无法解析 PDF")
            return None
        except Exception as e:
            print(f"   ⚠️ 备用解析失败: {e}")
            return None
    
    async def _collect_arxiv_papers(self, target_count: int) -> List[Dict]:
        """
        使用增强版收集器从 arXiv 收集论文
        
        Args:
            target_count: 目标论文数量
            
        Returns:
            收集到的论文列表
        """
        try:
            collector = EnhancedPaperCollector(chat_agent=self.chat_agent)
            
            papers = await collector.collect_papers(
                topic=self.config.topic,
                target_count=target_count,
                year_start=self.config.year_start,
                year_end=self.config.year_end,
                use_survey_strategy=self.config.use_survey_strategy,
                survey_count=self.config.survey_count,
                max_refs_per_survey=self.config.max_refs_per_survey,
                use_embedding_filter=self.config.use_embedding_filter,
                use_llm_filter=self.config.use_llm_relevance,
                embedding_threshold=self.config.embedding_threshold,
                llm_threshold=self.config.llm_relevance_threshold,
                use_openalex=self.config.use_openalex,
                download_pdf=self.config.download_pdf,
                pdf_output_dir=self.papers_dir / "pdfs"
            )
            
            return papers
            
        except Exception as e:
            print(f"   ⚠️ arXiv 收集失败: {e}")
            return []
    
    async def _collect_legacy_papers(self, target_count: int) -> List[Dict]:
        """
        使用传统收集器收集论文
        
        Args:
            target_count: 目标论文数量
            
        Returns:
            收集到的论文列表
        """
        try:
            from mekg.src.builders.paper_collector import OpenAlexCrawler
            
            crawler = OpenAlexCrawler(chat_agent=self.chat_agent)
            papers = await crawler.search_papers(
                query=self.config.topic,
                limit=target_count,
                year_start=self.config.year_start,
                use_keyword_split=self.config.use_keyword_split
            )
            
            return papers
            
        except Exception as e:
            print(f"   ⚠️ 传统收集器失败: {e}")
            return []
    
    async def _build_mekg_from_papers(self, papers: List[Dict]) -> Dict:
        """
        从论文列表构建 MEKG 数据
        
        Args:
            papers: 论文列表
            
        Returns:
            MEKG 数据字典
        """
        try:
            from mekg.src.builders.paper_collector import (
                PaperClassifier,
                RelationDiscoverer
            )
            
            # 分类论文
            classifier = PaperClassifier()
            classified = classifier.classify_papers(papers)
            
            # 发现关系
            if self.config.use_memgraph:
                relations = await self._discover_relations_with_memgraph(papers, classified)
            else:
                discoverer = RelationDiscoverer(
                    use_llm=self.config.use_llm_relations,
                    max_workers=self.config.max_workers
                )
                relations = discoverer.discover_relations(
                    papers, classified,
                    max_pairs=self.config.max_relation_pairs
                )
            
            # 构建 MEKG 数据
            return self._build_mekg_data(papers, relations, classified)
            
        except ImportError as e:
            print(f"   ⚠️ 无法导入 MEKG 构建模块: {e}")
            # 返回基础数据结构
            return {
                "topic": self.config.topic,
                "papers_count": len(papers),
                "relations_count": 0,
                "categories": {},
                "papers": [
                    {
                        "id": p.get("paper_id", p.get("id", "")),
                        "title": p.get("title", ""),
                        "abstract": p.get("abstract", ""),
                        "md_text": p.get("md_text", ""),
                        "year": p.get("year"),
                        "citations": p.get("citations", 0),
                        "authors": p.get("authors", []),
                        "source": p.get("source", "unknown"),
                        "is_uploaded": p.get("is_uploaded", False)
                    }
                    for p in papers
                ],
                "relations": []
            }
    
    async def _build_mekg_with_enhanced_collector(self) -> Dict:
        """使用增强版论文收集器构建MEKG图谱"""
        print("   🚀 使用增强版论文收集器 (arXiv优先 + Survey策略)")
        
        try:
            from mekg.src.builders.paper_collector import (
                PaperClassifier,
                RelationDiscoverer
            )
            
            # 1. 使用增强版收集器收集论文
            collector = EnhancedPaperCollector(chat_agent=self.chat_agent)
            
            print(f"   📥 收集论文 (目标: {self.config.max_papers} 篇)...")
            print(f"      - Survey 策略: {'启用' if self.config.use_survey_strategy else '禁用'}")
            print(f"      - Embedding 筛选: {'启用' if self.config.use_embedding_filter else '禁用'}")
            print(f"      - LLM 精筛: {'启用' if self.config.use_llm_relevance else '禁用'}")
            
            papers = await collector.collect_papers(
                topic=self.config.topic,
                target_count=self.config.max_papers,
                year_start=self.config.year_start,
                year_end=self.config.year_end,
                use_survey_strategy=self.config.use_survey_strategy,
                survey_count=self.config.survey_count,
                max_refs_per_survey=self.config.max_refs_per_survey,
                use_embedding_filter=self.config.use_embedding_filter,
                use_llm_filter=self.config.use_llm_relevance,
                embedding_threshold=self.config.embedding_threshold,
                llm_threshold=self.config.llm_relevance_threshold,
                use_openalex=self.config.use_openalex,
                download_pdf=self.config.download_pdf,
                pdf_output_dir=self.papers_dir / "pdfs"
            )
            
            print(f"   ✓ 收集到 {len(papers)} 篇高质量论文")
            
            # 统计来源
            source_counts = {}
            survey_count = 0
            for p in papers:
                source = p.get("source", "unknown")
                source_counts[source] = source_counts.get(source, 0) + 1
                if p.get("is_survey"):
                    survey_count += 1
            
            print(f"   📊 来源分布: {source_counts}")
            if survey_count > 0:
                print(f"   📚 包含 {survey_count} 篇 Survey 论文")
            
            # 2. 分类论文
            classifier = PaperClassifier()
            classified = classifier.classify_papers(papers)
            
            # 3. 发现关系
            if self.config.use_memgraph:
                relations = await self._discover_relations_with_memgraph(papers, classified)
            else:
                discoverer = RelationDiscoverer(
                    use_llm=self.config.use_llm_relations,
                    max_workers=self.config.max_workers
                )
                relations = discoverer.discover_relations(
                    papers, classified,
                    max_pairs=self.config.max_relation_pairs
                )
            
            # 构建MEKG数据
            mekg_data = self._build_mekg_data(papers, relations, classified)
            
            return mekg_data
            
        except ImportError as e:
            print(f"⚠️ 增强版收集器依赖缺失: {e}，回退到传统收集器")
            return await self._build_mekg_with_legacy_collector()
    
    async def _discover_relations_with_memgraph(self, papers: List[Dict], classified: Dict) -> List:
        """使用 Memgraph 发现关系"""
        try:
            from mekg.src.storage.memgraph_graph_db import MemgraphGraphDB
            from mekg.src.extraction.enhanced_relation_discoverer import EnhancedRelationDiscoverer
            
            print("   🔌 连接 Memgraph...")
            db = MemgraphGraphDB()
            
            # 将论文存入 Memgraph
            print(f"   💾 存储 {len(papers)} 篇论文到 Memgraph...")
            for p in papers:
                db.add_paper(p)
            
            discoverer = EnhancedRelationDiscoverer(
                db=db,
                chat_agent=self.chat_agent,
                use_llm=self.config.use_llm_relations,
                max_workers=self.config.max_workers
            )
            
            # 批量发现关系
            paper_ids = [p.get("paper_id") or p.get("id") for p in papers]
            paper_ids = [pid for pid in paper_ids if pid]
            
            print(f"   🔍 使用 Memgraph 进行增强关系发现...")
            discovery_result = discoverer.batch_discover_concurrent(
                paper_ids,
                max_pairs=self.config.max_relation_pairs
            )
            
            # 转换关系格式
            relations = []
            for r in discovery_result.relations:
                relations.append(type('obj', (object,), {
                    'source_id': r.source_id,
                    'target_id': r.target_id,
                    'relation_type': r.relation_type,
                    'confidence': r.confidence
                }))
            
            return relations
             
        except ImportError as e:
            print(f"⚠️ 无法使用 Memgraph: {e}，回退到默认发现器")
            from mekg.src.builders.paper_collector import RelationDiscoverer
            discoverer = RelationDiscoverer(
                use_llm=self.config.use_llm_relations,
                max_workers=self.config.max_workers
            )
            return discoverer.discover_relations(
                papers, classified,
                max_pairs=self.config.max_relation_pairs
            )
        except Exception as e:
            print(f"⚠️ Memgraph 关系发现失败: {e}，回退到默认发现器")
            from mekg.src.builders.paper_collector import RelationDiscoverer
            discoverer = RelationDiscoverer(
                use_llm=self.config.use_llm_relations,
                max_workers=self.config.max_workers
            )
            return discoverer.discover_relations(
                papers, classified,
                max_pairs=self.config.max_relation_pairs
            )
    
    def _build_mekg_data(self, papers: List[Dict], relations: List, classified: Dict) -> Dict:
        """构建 MEKG 数据结构
        
        注意：这里的 categories 来自 PaperClassifier 的硬编码分类体系，
        主要用于论文的初步分类。可视化时可以选择使用大纲结构替代。
        """
        return {
            "topic": self.config.topic,
            "papers_count": len(papers),
            "relations_count": len(relations),
            "categories": {
                cat: {subcat: len(ps) for subcat, ps in subcats.items()}
                for cat, subcats in classified.items()
            },
            "papers": [
                {
                    "id": p.get("paper_id", p.get("id", "")),
                    "title": p.get("title", ""),
                    "abstract": p.get("abstract", ""),  # 保留完整摘要
                    "md_text": p.get("md_text", ""),    # 论文全文（从 PDF 解析）
                    "year": p.get("year"),
                    "citations": p.get("citations", 0),
                    "authors": p.get("authors", []),
                    "category": p.get("category", ""),
                    "subcategory": p.get("subcategory", ""),
                    "source": p.get("source", "unknown"),
                    "is_survey": p.get("is_survey", False),
                    "relevance_score": p.get("relevance_score", 0.0),
                    "pdf_url": p.get("pdf_url", ""),
                    "arxiv_id": p.get("arxiv_id", "")
                }
                for p in papers
            ],
            "relations": [
                {
                    "source": r.source_id,
                    "target": r.target_id,
                    "type": r.relation_type,
                    "confidence": r.confidence
                }
                for r in relations
            ]
        }
    
    async def _build_mekg_with_legacy_collector(self) -> Dict:
        """使用传统收集器构建MEKG图谱（回退方案）"""
        print("   📥 使用传统收集器 (OpenAlex)")
        
        try:
            # 尝试导入现有的构建器
            from mekg.src.builders.paper_collector import (
                OpenAlexCrawler,
                PaperClassifier,
                RelationDiscoverer
            )
            
            # 1. 爬取论文 - 如果启用过滤，爬取更多论文
            target_papers = self.config.max_papers
            if self.config.enable_relevance_filter and HAS_RELEVANCE_FILTER:
                # 爬取 target * multiplier 篇，然后过滤到 target 篇
                crawl_limit = int(target_papers * self.config.crawl_multiplier)
                print(f"   📥 爬取 {crawl_limit} 篇论文（目标: {target_papers} 篇）...")
            else:
                crawl_limit = target_papers
            
            crawler = OpenAlexCrawler(chat_agent=self.chat_agent)
            
            # 使用LLM拆分关键词搜索
            if self.config.use_keyword_split:
                print(f"   🤖 启用LLM关键词拆分...")
            
            papers = await crawler.search_papers(
                query=self.config.topic,
                limit=crawl_limit,
                year_start=self.config.year_start,
                use_keyword_split=self.config.use_keyword_split
            )
            
            print(f"   ✓ 爬取到 {len(papers)} 篇论文")
            
            # 1.5 相关性过滤 - 过滤后保留目标数量
            if self.config.enable_relevance_filter and HAS_RELEVANCE_FILTER:
                if self.config.use_llm_relevance:
                    print(f"   🔍 使用LLM过滤不相关论文 (模型: {self.config.llm_relevance_model}, 并发: {self.config.llm_relevance_workers})...")
                else:
                    print(f"   🔍 过滤不相关论文 (关键词阈值: {self.config.relevance_threshold})...")
                
                relevance_filter = RelevanceFilter(
                    chat_agent=self.chat_agent,
                    use_llm=self.config.use_llm_relevance,
                    keyword_threshold=self.config.relevance_threshold,
                    llm_threshold=self.config.llm_relevance_threshold,
                    max_workers=self.config.llm_relevance_workers,
                    filter_model=self.config.llm_relevance_model if self.config.use_llm_relevance else None,
                    use_fast_prompt=True  # 使用简洁prompt提高效率
                )
                
                # 如果启用LLM过滤，使用纯LLM过滤模式
                if self.config.use_llm_relevance and self.chat_agent:
                    relevant_papers, filtered_out = relevance_filter.filter_papers_llm_only(
                        papers,
                        self.config.topic
                    )
                else:
                    relevant_papers, filtered_out = relevance_filter.filter_papers(
                        papers,
                        self.config.topic,
                        use_llm_filter=False
                    )
                
                # 如果过滤后论文数量不足，降低阈值重试
                if len(relevant_papers) < target_papers:
                    print(f"   ⚠️ 过滤后只有 {len(relevant_papers)} 篇，尝试降低阈值...")
                    # 按相关性分数排序所有论文，取前 target_papers 篇
                    all_papers_scored = []
                    for p in papers:
                        score = relevance_filter._keyword_relevance(
                            p,
                            relevance_filter._extract_keywords(self.config.topic)
                        )
                        all_papers_scored.append((p, score))
                    
                    # 按分数排序，取前 target_papers 篇
                    all_papers_scored.sort(key=lambda x: x[1], reverse=True)
                    papers = [p for p, s in all_papers_scored[:target_papers]]
                    print(f"   ✓ 按相关性排序后保留 {len(papers)} 篇论文")
                else:
                    # 如果过滤后论文数量超过目标，按引用数排序取前 target_papers 篇
                    if len(relevant_papers) > target_papers:
                        relevant_papers.sort(key=lambda x: x.get("citations", 0), reverse=True)
                        papers = relevant_papers[:target_papers]
                        print(f"   ✓ 保留 {len(papers)} 篇高引用相关论文（过滤 {len(filtered_out)} 篇）")
                    else:
                        papers = relevant_papers
                        print(f"   ✓ 保留 {len(papers)} 篇相关论文（过滤 {len(filtered_out)} 篇）")
            
            # 2. 分类论文
            classifier = PaperClassifier()
            classified = classifier.classify_papers(papers)
            
            # 3. 发现关系
            # 如果启用 Memgraph，使用 EnhancedRelationDiscoverer
            if self.config.use_memgraph:
                try:
                    from mekg.src.storage.memgraph_graph_db import MemgraphGraphDB
                    from mekg.src.extraction.enhanced_relation_discoverer import EnhancedRelationDiscoverer

                    print("   🔌 连接 Memgraph...")
                    db = MemgraphGraphDB()

                    # 将论文存入 Memgraph
                    print(f"   💾 存储 {len(papers)} 篇论文到 Memgraph...")
                    for p in papers:
                        db.add_paper(p)

                    discoverer = EnhancedRelationDiscoverer(
                        db=db,
                        chat_agent=self.chat_agent,
                        use_llm=self.config.use_llm_relations,
                        max_workers=self.config.max_workers
                    )

                    # 批量发现关系
                    paper_ids = [p.get("paper_id") or p.get("id") for p in papers]
                    paper_ids = [pid for pid in paper_ids if pid]

                    print("   🔍 使用 Memgraph 进行增强关系发现...")
                    discovery_result = discoverer.batch_discover_concurrent(
                        paper_ids,
                        max_pairs=self.config.max_relation_pairs
                    )

                    # 转换关系格式
                    relations = []
                    for r in discovery_result.relations:
                        relations.append(type('obj', (object,), {
                            'source_id': r.source_id,
                            'target_id': r.target_id,
                            'relation_type': r.relation_type,
                            'confidence': r.confidence
                        }))

                except ImportError as e:
                    print(f"⚠️ 无法使用 Memgraph: {e}，回退到默认发现器")
                    discoverer = RelationDiscoverer(
                        use_llm=self.config.use_llm_relations,
                        max_workers=self.config.max_workers
                    )
                    relations = discoverer.discover_relations(
                        papers, classified,
                        max_pairs=self.config.max_relation_pairs
                    )
                except Exception as e:
                    print(f"⚠️ Memgraph 关系发现失败: {e}，回退到默认发现器")
                    discoverer = RelationDiscoverer(
                        use_llm=self.config.use_llm_relations,
                        max_workers=self.config.max_workers
                    )
                    relations = discoverer.discover_relations(
                        papers, classified,
                        max_pairs=self.config.max_relation_pairs
                    )
            else:
                discoverer = RelationDiscoverer(
                    use_llm=self.config.use_llm_relations,
                    max_workers=self.config.max_workers
                )
                relations = discoverer.discover_relations(
                    papers, classified,
                    max_pairs=self.config.max_relation_pairs
                )
            
            # 构建MEKG数据
            mekg_data = {
                "topic": self.config.topic,
                "papers_count": len(papers),
                "relations_count": len(relations),
                "categories": {
                    cat: {subcat: len(ps) for subcat, ps in subcats.items()}
                    for cat, subcats in classified.items()
                },
                "papers": [
                    {
                        "id": p.get("paper_id", ""),
                        "title": p.get("title", ""),
                        "abstract": p.get("abstract", "")[:500],
                        "year": p.get("year"),
                        "citations": p.get("citations", 0),
                        "authors": p.get("authors", []),
                        "category": p.get("category", ""),
                        "subcategory": p.get("subcategory", "")
                    }
                    for p in papers
                ],
                "relations": [
                    {
                        "source": r.source_id,
                        "target": r.target_id,
                        "type": r.relation_type,
                        "confidence": r.confidence
                    }
                    for r in relations
                ]
            }
            
            return mekg_data
            
        except ImportError:
            # 如果无法导入，返回空数据
            print("⚠️ 无法导入MEKG构建模块，使用空数据")
            return {
                "topic": self.config.topic,
                "papers_count": 0,
                "relations_count": 0,
                "categories": {},
                "papers": [],
                "relations": []
            }
    
    def _generate_outline(self, mekg_data: Dict) -> SurveyOutline:
        """生成大纲"""
        # 优先使用混合大纲生成器 (P1 优化)
        if self.config.use_hybrid_outline and HAS_HYBRID_OUTLINE:
            print("   📋 使用 HybridOutlineGenerator (Top-down + Bottom-up)...")
            try:
                # 准备论文数据
                papers = mekg_data.get("papers", [])
                
                # 生成混合大纲
                # 注意：max_papers_for_clustering 应该与 max_papers 配置一致
                # 否则聚类只会使用默认的100篇论文
                hybrid_generator = HybridOutlineGenerator(
                    chat_agent=self.chat_agent,
                    enable_bottom_up=True,
                    enable_merge=True,
                    max_papers_for_clustering=len(papers)  # 使用全部论文进行聚类
                )
                hybrid_outline = hybrid_generator.generate(
                    topic=self.config.topic,
                    papers=papers
                )
                
                # 转换为 MEKG 的 SurveyOutline/OutlineSection 格式（支持 3 级结构）
                sections: List[OutlineSection] = []
                for i, h_section in enumerate(hybrid_outline.sections, 1):
                    subsections: List[OutlineSection] = []
                    for j, h_sub in enumerate(getattr(h_section, "subsections", []) or [], 1):
                        subsubsections: List[OutlineSection] = []
                        for k, h_subsub in enumerate(getattr(h_sub, "subsections", []) or [], 1):
                            subsubsections.append(
                                OutlineSection(
                                    number=f"{i}.{j}.{k}",
                                    title=h_subsub.title,
                                    description=h_subsub.description,
                                    level=3,
                                )
                            )

                        subsections.append(
                            OutlineSection(
                                number=f"{i}.{j}",
                                title=h_sub.title,
                                description=h_sub.description,
                                level=2,
                                subsections=subsubsections,
                            )
                        )

                    sections.append(
                        OutlineSection(
                            number=str(i),
                            title=h_section.title,
                            description=h_section.description,
                            level=1,
                            subsections=subsections,
                        )
                    )

                outline = SurveyOutline(
                    title=hybrid_outline.title,
                    topic=self.config.topic,
                    sections=sections,
                    metadata=getattr(hybrid_outline, "metadata", {}) or {},
                )

                # 可选：对混合大纲执行 critic-refine（保持与 enable_critic_loop 语义一致）
                if self.config.enable_critic_loop:
                    try:
                        critic = MEKGOutlineGenerator(
                            chat_agent=self.chat_agent,
                            enable_critic=True,
                            skip_mount=True,
                        )
                        outline = critic._critic_and_refine(outline, self.config.topic)
                    except Exception as e:
                        print(f"   ⚠️ Critic-Refine 失败: {e}（保留混合大纲）")

                return outline
                 
            except Exception as e:
                print(f"   ⚠️ 混合大纲生成失败: {e}，回退到 MEKGOutlineGenerator")
                import traceback
                traceback.print_exc()
        
        # 回退到 MEKGOutlineGenerator
        print("   📋 使用 MEKGOutlineGenerator...")
        # 如果使用 SurveyX 的 ContentGenerator，跳过 MEKG 的论文挂载
        # 让 SurveyX 自己执行挂载，避免重复挂载
        skip_mount = self.config.use_surveyx_content and HAS_SURVEYX_CONTENT
        
        generator = MEKGOutlineGenerator(
            chat_agent=self.chat_agent,
            enable_critic=self.config.enable_critic_loop,
            skip_mount=skip_mount
        )
        return generator.generate_from_mekg_data(
            mekg_data=mekg_data,
            topic=self.config.topic
        )
    
    def _generate_content(
        self,
        outline: SurveyOutline,
        mekg_data: Dict
    ) -> Dict[str, str]:
        """
        生成内容
        
        根据配置选择使用 SurveyX 的 ContentGenerator 或 MEKG 自己的生成器。
        推荐使用 SurveyX 的生成器以保持一致性。
        """
        # 优先使用 SurveyX 的内容生成器
        if self.config.use_surveyx_content and HAS_SURVEYX_CONTENT:
            print("   📝 使用 SurveyX ContentGenerator...")
            return self._generate_content_with_surveyx(outline, mekg_data)
        else:
            print("   📝 使用 MEKG ContentGenerator...")
            generator = MEKGContentGenerator(
                chat_agent=self.chat_agent,
                iter_span=self.config.iter_span,
                max_workers=self.config.max_workers
            )
            return generator.generate_content(
                outline=outline,
                mekg_data=mekg_data,
                output_dir=self.tmp_dir
            )
    
    def _generate_content_with_surveyx(
        self,
        outline: SurveyOutline,
        mekg_data: Dict
    ) -> Dict[str, str]:
        """
        使用 SurveyX 的 ContentGenerator 生成内容
        
        流程：
        1. 将 MEKG 大纲转换为 SurveyX 格式
        2. 将 MEKG 论文数据保存为 SurveyX 格式
        3. 生成 references.bib 文件（PostRefiner 需要）
        4. 调用 SurveyX ContentGenerator
        5. 调用 SurveyX PostRefiner（可选）
        """
        from src.modules.utils import load_file_as_string
        
        # 1. 保存 SurveyX 格式的大纲
        surveyx_outline = outline.to_surveyx_format()
        outlines_path = self.output_dir / "outlines.json"
        with open(outlines_path, 'w', encoding='utf-8') as f:
            json.dump(surveyx_outline, f, ensure_ascii=False, indent=2)
        
        # 2. 保存论文数据（带挂载信息）
        self._save_papers_with_mount_info(mekg_data, outline)
        
        # 3. 生成 references.bib 文件（PostRefiner 的 BibNameReplacer 需要）
        self._generate_references_bib(mekg_data)
        
        # 4. 保存 tmp_config.json（SurveyX 需要）
        # 注意：SurveyX 的 Base 类期望 tmp_config.json 在 OUTPUT_DIR / task_id / "tmp_config.json"
        # 即 outputs/{task_id}/tmp_config.json，而不是 outputs/{task_id}/tmp/tmp_config.json
        tmp_config = {
            "task_id": self.config.task_id,
            "title": self.config.topic,  # SurveyX 需要 title 字段
            "topic": self.config.topic,
            "key_words": self.config.topic
        }
        # 保存到 output_dir（不是 tmp_dir）
        tmp_config_path = self.output_dir / "tmp_config.json"
        with open(tmp_config_path, 'w', encoding='utf-8') as f:
            json.dump(tmp_config, f, ensure_ascii=False, indent=2)
        
        # 5. 调用 SurveyX ContentGenerator
        # 检查是否已存在生成的内容，如果存在则跳过生成（避免重复消耗 Token）
        mainbody_path = self.tmp_dir / "mainbody.tex"
        if mainbody_path.exists() and mainbody_path.stat().st_size > 0:
            print("   📝 检测到已有内容，跳过内容生成步骤...")
        else:
            content_gen = SurveyXContentGenerator(task_id=self.config.task_id)
            content_gen.run()
        
        # 6. 调用 PostRefiner（可选）
        print(f"   DEBUG: use_surveyx_postrefine={self.config.use_surveyx_postrefine}, HAS_POST_REFINER={HAS_POST_REFINER}")
        
        if self.config.use_surveyx_postrefine and HAS_POST_REFINER:
            # 检查是否已存在 PostRefiner 的结果
            post_refined_path = self.tmp_dir / "mainbody_post_refined.tex"
            
            # 无论文件是否存在，我们都尝试初始化 PostRefiner
            try:
                print("   🔧 初始化 PostRefiner...")
                post_refiner = PostRefiner(
                    task_id=self.config.task_id,
                    chat_agent=self.chat_agent,
                    enable_dynamic_visuals=True,  # 强制开启
                    enable_reference_images=True  # 强制开启
                )
                
                if post_refined_path.exists() and post_refined_path.stat().st_size > 0:
                    print("   📝 检测到已有 PostRefiner 结果，跳过文本优化，仅执行图表生成...")
                    
                    # 1. 生成表格
                    print("   📊 开始生成表格 (generate_tables)...")
                    try:
                        post_refiner.generate_tables()
                        print("   ✅ 表格生成完成")
                    except Exception as e:
                        print(f"   ⚠️ 表格生成失败: {e}")
                        import traceback
                        traceback.print_exc()
                    
                    # 2. 生成动态视觉元素
                    print("   🎨 开始生成动态视觉元素 (generate_dynamic_visuals)...")
                    try:
                        post_refiner.generate_dynamic_visuals(post_refined_path)
                        print("   ✅ 动态视觉元素生成完成")
                    except Exception as e:
                        print(f"   ⚠️ 动态视觉元素生成失败: {e}")
                        import traceback
                        traceback.print_exc()
                        
                else:
                    print("   🚀 开始执行完整的 PostRefiner 流程...")
                    post_refiner.run()
                    
            except Exception as e:
                print(f"   ❌ PostRefiner 执行失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 7. 读取生成的内容
        mainbody_path = self.tmp_dir / "mainbody.tex"
        if not mainbody_path.exists():
            mainbody_path = self.tmp_dir / "mainbody_post_refined.tex"
        
        abstract_path = self.tmp_dir / "abstract.tex"
        
        mainbody = ""
        abstract = ""
        
        if mainbody_path.exists():
            mainbody = load_file_as_string(mainbody_path)
        if abstract_path.exists():
            abstract = load_file_as_string(abstract_path)
        
        return {
            "mainbody": mainbody,
            "abstract": abstract,
            "outline": str(outline)
        }
    
    def _generate_content_only(
        self,
        outline: SurveyOutline,
        mekg_data: Dict
    ) -> Dict[str, str]:
        """
        只生成Survey主体内容，不执行PostRefiner
        
        这是细粒度拆分后的 Step 3，只负责：
        1. 保存 SurveyX 格式的大纲
        2. 保存论文数据
        3. 生成 references.bib
        4. 调用 SurveyX ContentGenerator
        
        PostRefiner 的各个步骤会在后续的 Step 4-6 中分别执行。
        """
        from src.modules.utils import load_file_as_string
        
        # 1. 保存 SurveyX 格式的大纲
        surveyx_outline = outline.to_surveyx_format()
        outlines_path = self.output_dir / "outlines.json"
        with open(outlines_path, 'w', encoding='utf-8') as f:
            json.dump(surveyx_outline, f, ensure_ascii=False, indent=2)
        
        # 2. 保存论文数据（带挂载信息）
        self._save_papers_with_mount_info(mekg_data, outline)
        
        # 3. 生成 references.bib 文件（PostRefiner 的 BibNameReplacer 需要）
        self._generate_references_bib(mekg_data)
        
        # 4. 保存 tmp_config.json（SurveyX 需要）
        tmp_config = {
            "task_id": self.config.task_id,
            "title": self.config.topic,
            "topic": self.config.topic,
            "key_words": self.config.topic,
            "year_start": self.config.year_start,
            "year_end": self.config.year_end
        }
        tmp_config_path = self.output_dir / "tmp_config.json"
        with open(tmp_config_path, 'w', encoding='utf-8') as f:
            json.dump(tmp_config, f, ensure_ascii=False, indent=2)
        
        # 同时保存 task_config.json（用于 EnhancedMultimodalRefiner 读取年份范围）
        task_config = {
            "task_id": self.config.task_id,
            "topic": self.config.topic,
            "year_start": self.config.year_start,
            "year_end": self.config.year_end,
            "max_papers": self.config.max_papers
        }
        task_config_path = self.output_dir / "task_config.json"
        with open(task_config_path, 'w', encoding='utf-8') as f:
            json.dump(task_config, f, ensure_ascii=False, indent=2)
        
        # 5. 调用 ContentGenerator (支持反思机制)
        mainbody_path = self.tmp_dir / "mainbody.tex"
        if mainbody_path.exists() and mainbody_path.stat().st_size > 0:
            print("   📝 检测到已有内容，跳过内容生成步骤...")
        else:
            if self.config.use_surveyx_content and HAS_SURVEYX_CONTENT:
                # 优先使用带反思机制的生成器
                if self.config.enable_reflection and HAS_REFLECTIVE_GENERATOR:
                    print("   📝 使用 ReflectiveContentGenerator (带反思机制)...")
                    print(f"      - 反思最大迭代: {self.config.reflection_max_iterations}")
                    print(f"      - 质量阈值: {self.config.reflection_quality_threshold}")
                    
                    reflection_config = ReflectionConfig(
                        enable_section_reflection=True,
                        section_reflection_max_turns=self.config.reflection_max_iterations,
                        quality_threshold=self.config.reflection_quality_threshold,
                        enable_global_evaluation=self.config.enable_global_evaluation,
                        save_reflection_history=True
                    )
                    content_gen = ReflectiveContentGenerator(
                        task_id=self.config.task_id,
                        reflection_config=reflection_config
                    )
                    content_gen.run(enable_reflection=True)
                else:
                    print("   📝 使用 SurveyX ContentGenerator...")
                    content_gen = SurveyXContentGenerator(task_id=self.config.task_id)
                    content_gen.run()
            else:
                print("   📝 使用 MEKG ContentGenerator...")
                generator = MEKGContentGenerator(
                    chat_agent=self.chat_agent,
                    iter_span=self.config.iter_span,
                    max_workers=self.config.max_workers
                )
                generator.generate_content(
                    outline=outline,
                    mekg_data=mekg_data,
                    output_dir=self.tmp_dir
                )
        
        # 6. 读取生成的内容
        abstract_path = self.tmp_dir / "abstract.tex"
        
        mainbody = ""
        abstract = ""
        
        if mainbody_path.exists():
            mainbody = load_file_as_string(mainbody_path)
        if abstract_path.exists():
            abstract = load_file_as_string(abstract_path)
        
        return {
            "mainbody": mainbody,
            "abstract": abstract,
            "outline": str(outline)
        }
    
    def _run_post_refine_text(self, outline: SurveyOutline, post_refiner=None):
        """
        执行 PostRefiner 的文本优化步骤
        
        这是细粒度拆分后的 Step 4，只负责执行文本优化（refine_text）。
        PostRefiner 实例由调用方传入，避免重复初始化和 embedding。
        
        在生成新版本之前，会自动备份当前版本（如果存在）。
        
        Args:
            outline: 大纲对象
            post_refiner: 已初始化的 PostRefiner 实例（可选，如果为 None 则创建新实例）
        """
        if not HAS_POST_REFINER:
            print("   ⚠️ PostRefiner 不可用，跳过文本优化")
            return
        
        post_refined_path = self.tmp_dir / "mainbody_post_refined.tex"
        
        # 如果已存在优化后的文件，跳过
        if post_refined_path.exists() and post_refined_path.stat().st_size > 0:
            print("   📝 检测到已有 PostRefiner 结果，跳过文本优化...")
            return
        
        # 在生成新版本之前，备份当前版本（如果存在）
        self._backup_file_before_update(post_refined_path, "step_4_refine")
        
        try:
            # 如果没有传入 post_refiner，则创建新实例（兼容旧调用方式）
            if post_refiner is None:
                print("   🔧 初始化 PostRefiner...")
                post_refiner = PostRefiner(
                    task_id=self.config.task_id,
                    chat_agent=self.chat_agent,
                    enable_dynamic_visuals=False,
                    enable_reference_images=False
                )
            
            # 只执行文本优化部分
            print("   📝 执行文本优化 (refine_text)...")
            post_refiner.refine_text()
            print("   ✅ 文本优化完成")
            
        except Exception as e:
            print(f"   ❌ PostRefiner 文本优化失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _run_generate_tables(self, post_refiner=None):
        """
        执行表格生成步骤
        
        这是细粒度拆分后的 Step 5，只负责执行表格生成（generate_tables）。
        PostRefiner 实例由调用方传入，避免重复初始化和 embedding。
        
        Args:
            post_refiner: 已初始化的 PostRefiner 实例（可选，如果为 None 则创建新实例）
        """
        if not HAS_POST_REFINER:
            print("   ⚠️ PostRefiner 不可用，跳过表格生成")
            return
        
        try:
            # 如果没有传入 post_refiner，则创建新实例（兼容旧调用方式）
            if post_refiner is None:
                print("   🔧 初始化 PostRefiner...")
                post_refiner = PostRefiner(
                    task_id=self.config.task_id,
                    chat_agent=self.chat_agent,
                    enable_dynamic_visuals=False,
                    enable_reference_images=False
                )
            
            print("   📊 执行表格生成 (generate_tables)...")
            post_refiner.generate_tables()
            print("   ✅ 表格生成完成")
            
        except Exception as e:
            print(f"   ❌ 表格生成失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _run_generate_dynamic_visuals(self, post_refiner=None):
        """
        执行动态视觉元素生成步骤
        
        这是细粒度拆分后的 Step 6，只负责执行动态视觉元素生成（generate_dynamic_visuals）。
        PostRefiner 实例由调用方传入，避免重复初始化和 embedding。
        
        包括：流程图、架构图、AI生成的图片等
        
        在生成新版本之前，会自动备份当前版本（如果存在）。
        
        Args:
            post_refiner: 已初始化的 PostRefiner 实例（可选，如果为 None 则创建新实例）
        """
        if not HAS_POST_REFINER:
            print("   ⚠️ PostRefiner 不可用，跳过动态视觉元素生成")
            return
        
        # 确定要处理的文件路径
        post_refined_path = self.tmp_dir / "mainbody_post_refined.tex"
        if not post_refined_path.exists():
            post_refined_path = self.tmp_dir / "mainbody.tex"
        
        if not post_refined_path.exists():
            print("   ⚠️ 未找到主体内容文件，跳过动态视觉元素生成")
            return
        
        # 在生成新版本之前，备份 mainbody_enhanced_multimodal.tex（如果存在）
        enhanced_multimodal_path = self.tmp_dir / "mainbody_enhanced_multimodal.tex"
        self._backup_file_before_update(enhanced_multimodal_path, "step_6_visuals")
        
        # 同时备份 post_refined 文件（因为 generate_dynamic_visuals 可能会修改它）
        self._backup_file_before_update(post_refined_path, "step_6_visuals")
        
        try:
            # 如果没有传入 post_refiner，则创建新实例（兼容旧调用方式）
            if post_refiner is None:
                print("   🔧 初始化 PostRefiner...")
                post_refiner = PostRefiner(
                    task_id=self.config.task_id,
                    chat_agent=self.chat_agent,
                    enable_dynamic_visuals=True,
                    enable_reference_images=True
                )
            
            print("   🎨 执行动态视觉元素生成 (generate_dynamic_visuals)...")
            post_refiner.generate_dynamic_visuals(post_refined_path)
            print("   ✅ 动态视觉元素生成完成")
            
        except Exception as e:
            print(f"   ❌ 动态视觉元素生成失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _extract_paper_attributes(self, mekg_data: Dict) -> Dict[str, Dict]:
        """
        使用 SurveyX 的 DataCleaner 提取论文属性
        
        这是 SurveyX 原版的论文属性提取流程，会为每篇论文提取：
        - paper_type: method/benchmark/theory/survey
        - attri: 包含 idea、method、discussion 等结构化信息
        
        Returns:
            Dict[str, Dict]: paper_id -> {paper_type, attri} 的映射
        """
        if not HAS_DATA_CLEANER:
            print("   ⚠️ DataCleaner 不可用，跳过论文属性提取")
            return {}
        
        if not self.chat_agent:
            print("   ⚠️ ChatAgent 不可用，跳过论文属性提取")
            return {}
        
        print("   📝 使用 SurveyX DataCleaner 提取论文属性...")
        
        # 准备论文数据（DataCleaner 需要 md_text 字段）
        papers_for_cleaner = []
        paper_id_map = {}  # index -> paper_id
        
        for i, paper in enumerate(mekg_data.get("papers", [])):
            paper_id = paper.get("id", "")
            if not paper_id:
                continue
            
            # 获取 md_text（优先使用 PDF 解析的全文）
            md_text = paper.get("md_text", "")
            if not md_text:
                md_text = paper.get("abstract", "")
            
            if not md_text or len(md_text) < 100:
                # 跳过内容太少的论文
                continue
            
            papers_for_cleaner.append({
                "title": paper.get("title", ""),
                "abstract": paper.get("abstract", ""),
                "md_text": md_text
            })
            paper_id_map[len(papers_for_cleaner) - 1] = paper_id
        
        if not papers_for_cleaner:
            print("   ⚠️ 没有足够内容的论文，跳过属性提取")
            return {}
        
        print(f"   📊 准备提取 {len(papers_for_cleaner)} 篇论文的属性...")
        
        # 使用 DataCleaner 提取属性
        cleaner = DataCleaner(papers=papers_for_cleaner)
        
        # 1. 分类论文类型
        print("   🏷️ 分类论文类型...")
        cleaner.get_paper_type(chat_agent=self.chat_agent)
        
        # 2. 提取论文属性
        print("   🔍 提取论文属性 (idea, method, discussion 等)...")
        cleaner.get_attri(chat_agent=self.chat_agent)
        
        # 构建结果映射
        result = {}
        for i, paper in enumerate(cleaner.papers):
            if i in paper_id_map:
                paper_id = paper_id_map[i]
                result[paper_id] = {
                    "paper_type": paper.get("paper_type", "method"),
                    "attri": paper.get("attri", {})
                }
        
        print(f"   ✓ 成功提取 {len(result)} 篇论文的属性")
        return result
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        清理文件名，移除或替换非法字符
        
        在 Windows 上，以下字符是非法的文件名字符：
        \\ / : * ? " < > |
        
        Args:
            filename: 原始文件名
            
        Returns:
            清理后的合法文件名
        """
        import re
        # 替换非法字符为下划线
        return re.sub(r'[\\/:*?"<>|]', '_', filename)

    def _surveyx_papers_ready(self, expected_count: int) -> bool:
        """Check whether SurveyX paper JSONs already contain reusable attributes."""
        try:
            if expected_count <= 0 or not self.papers_dir.exists():
                return False

            paper_files = list(self.papers_dir.glob("*.json"))
            if len(paper_files) < expected_count:
                return False

            ready_count = 0
            for paper_file in paper_files:
                try:
                    paper = json.loads(paper_file.read_text(encoding="utf-8"))
                except Exception:
                    return False

                if paper.get("attri") and paper.get("bib_name") and paper.get("md_text"):
                    ready_count += 1

            return ready_count >= expected_count
        except Exception as e:
            print(f"   ⚠️ 检查已有 SurveyX 论文数据失败: {e}")
            return False
    
    def _save_papers_with_mount_info(self, mekg_data: Dict, outline: SurveyOutline):
        """
        保存论文数据（供 SurveyX ContentGenerator 使用）
        
        流程：
        1. 如果启用了 extract_paper_attri，先使用 SurveyX DataCleaner 提取论文属性
        2. 保存论文数据，包含提取的 attri 字段
        
        注意：不再预设 mount_outline 字段，让 SurveyX 的 mount_trees_on_outlines 来执行挂载。
        这样可以避免重复挂载，并使用 SurveyX 原版的挂载逻辑。
        """
        expected_papers = len([p for p in mekg_data.get("papers", []) if p.get("id", "")])
        if self._surveyx_papers_ready(expected_papers):
            print(
                f"   ♻️ 检测到已有完整 SurveyX 论文数据 "
                f"({expected_papers} 篇)，跳过属性提取和论文重写"
            )
            return

        # 如果启用了论文属性提取，先提取属性
        extracted_attrs = {}
        if self.config.extract_paper_attri and HAS_DATA_CLEANER:
            extracted_attrs = self._extract_paper_attributes(mekg_data)
        
        # 构建论文关系映射（从 MEKG 的 relations 中提取）
        paper_relations = {}
        for rel in mekg_data.get("relations", []):
            source = rel.get("source", "")
            target = rel.get("target", "")
            rel_type = rel.get("type", "")
            confidence = rel.get("confidence", 0)
            
            if source:
                if source not in paper_relations:
                    paper_relations[source] = []
                paper_relations[source].append({
                    "target": target,
                    "type": rel_type,
                    "confidence": confidence
                })
        
        # 保存每篇论文（不包含挂载信息，由 SurveyX 自己挂载）
        for paper in mekg_data.get("papers", []):
            paper_id = paper.get("id", "")
            if not paper_id:
                continue
            
            # 获取该论文的关系信息
            relations = paper_relations.get(paper_id, [])
            
            # 获取提取的属性（如果有）
            extracted = extracted_attrs.get(paper_id, {})
            extracted_attri = extracted.get("attri", {})
            extracted_paper_type = extracted.get("paper_type", "")
            
            # 构建 attri 字段
            # 如果有 LLM 提取的属性，使用提取的属性；否则使用基础信息
            if extracted_attri:
                # 使用 LLM 提取的结构化属性（包含 idea、method、discussion 等）
                attri = extracted_attri
                # 补充 MEKG 的关系信息
                attri["mekg_relations"] = relations[:10] if relations else []
                attri["mekg_category"] = paper.get("category", "")
                attri["mekg_subcategory"] = paper.get("subcategory", "")
            else:
                # 回退到基础属性
                attri = {
                    # 基本信息（必须包含 title 和 abstract，这是挂载的关键）
                    "title": paper.get("title", ""),
                    "abstract": paper.get("abstract", ""),
                    
                    # 元数据
                    "year": paper.get("year"),
                    "citations": paper.get("citations", 0),
                    "authors": paper.get("authors", []),
                    
                    # MEKG 分类信息
                    "category": paper.get("category", ""),
                    "subcategory": paper.get("subcategory", ""),
                    
                    # MEKG 实体信息
                    "method_entities": paper.get("method_entities", []),
                    "task_entities": paper.get("task_entities", []),
                    
                    # MEKG 关系信息（帮助 LLM 理解论文之间的关系）
                    "relations": relations[:10] if relations else []
                }
            
            # 确定 paper_type
            if extracted_paper_type:
                paper_type = extracted_paper_type
            else:
                # 根据分类判断 paper_type
                category = paper.get("category", "").lower()
                subcategory = paper.get("subcategory", "").lower()
                paper_type = "method"
                if "benchmark" in category or "benchmark" in subcategory or "dataset" in category:
                    paper_type = "benchmark"
            
            # 获取 md_text
            abstract = paper.get("abstract", "")
            md_text = paper.get("md_text", "")
            if not md_text:
                md_text = abstract  # 回退到摘要
            
            # 清理文件名中的非法字符（如 arXiv:2505.20192 中的冒号）
            safe_paper_id = self._sanitize_filename(paper_id)
            
            surveyx_paper = {
                "title": paper.get("title", ""),
                "abstract": abstract,
                "md_text": md_text,  # 优先使用 PDF 解析的全文
                "paper_type": paper_type,
                "bib_name": safe_paper_id,  # 使用清理后的 ID 作为 bib_name
                "attri": attri
                # 注意：不设置 mount_outline，让 SurveyX 的 mount_trees_on_outlines 来填充
            }
            
            paper_path = self.papers_dir / f"{safe_paper_id}.json"
            with open(paper_path, 'w', encoding='utf-8') as f:
                json.dump(surveyx_paper, f, ensure_ascii=False, indent=2)
    
    def _evaluate(
        self,
        mekg_data: Dict,
        content_result: Dict,
        outline: SurveyOutline
    ) -> EvaluationResult:
        """评估质量"""
        evaluator = MEKGEvaluator(mekg_data)
        evaluation = evaluator.evaluate(
            survey_content=content_result.get("mainbody", ""),
            survey_outline=outline.to_surveyx_format()
        )
        
        return evaluation
    
    async def _run_evaluation_parallel(
        self,
        mekg_data: Dict,
        content_result: Dict,
        outline: SurveyOutline
    ) -> tuple:
        """
        并行执行评估任务
        
        将三个独立的评估任务并行执行，显著减少评估阶段的总时间：
        1. 基础评估 (MEKGEvaluator)
        2. 全局一致性检查 (GlobalReflector)
        3. 演化叙事分析 (EvolutionaryAnalyzer)
        
        Args:
            mekg_data: MEKG 数据
            content_result: 内容结果
            outline: 大纲
            
        Returns:
            (evaluation, global_result, evolution_result) 元组
        """
        import concurrent.futures
        from functools import partial
        
        evaluation = None
        global_result = None
        evolution_result = None
        
        # 定义各个评估任务
        def run_basic_evaluation():
            """基础评估任务"""
            try:
                return self._evaluate(mekg_data, content_result, outline)
            except Exception as e:
                print(f"   ⚠️ 基础评估失败: {e}")
                import traceback
                traceback.print_exc()
                return None
        
        def run_global_reflection():
            """全局一致性检查任务"""
            if not (self.config.use_global_reflector and HAS_GLOBAL_REFLECTOR):
                return None
            
            try:
                print("   🔍 执行全局一致性检查 (GlobalReflector)...")
                # 准备章节内容
                sections_content = self._split_mainbody_into_sections(
                    content_result.get("mainbody", ""),
                    max_chars_per_section=6000,
                )
                
                global_reflector = GlobalReflector(
                    chat_agent=self.chat_agent,
                    quality_threshold=self.config.reflection_quality_threshold
                )
                return global_reflector.reflect(
                    title=outline.title,
                    topic=self.config.topic,
                    sections_content=sections_content,
                    outline=outline.to_surveyx_format()
                )
            except Exception as e:
                print(f"   ⚠️ 全局反思失败: {e}")
                import traceback
                traceback.print_exc()
                return None
        
        def run_evolutionary_analysis():
            """演化叙事分析任务"""
            if not (self.config.use_evolutionary_analyzer and HAS_EVOLUTIONARY_ANALYZER):
                return None
            
            try:
                print("   📈 执行演化叙事分析 (EvolutionaryAnalyzer)...")
                papers = mekg_data.get("papers", [])
                analyzer = EvolutionaryAnalyzer(chat_agent=self.chat_agent)
                return analyzer.analyze(self.config.topic, papers)
            except Exception as e:
                print(f"   ⚠️ 演化分析失败: {e}")
                import traceback
                traceback.print_exc()
                return None
        
        # 使用 ThreadPoolExecutor 并行执行（因为这些任务主要是 I/O 密集型的 LLM 调用）
        print("   🚀 并行执行 3 个评估任务...")
        
        loop = asyncio.get_event_loop()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # 提交所有任务
            future_basic = loop.run_in_executor(executor, run_basic_evaluation)
            future_global = loop.run_in_executor(executor, run_global_reflection)
            future_evolution = loop.run_in_executor(executor, run_evolutionary_analysis)
            
            # 等待所有任务完成
            evaluation, global_result, evolution_result = await asyncio.gather(
                future_basic,
                future_global,
                future_evolution,
                return_exceptions=True
            )
            
            # 处理异常结果
            if isinstance(evaluation, Exception):
                print(f"   ⚠️ 基础评估异常: {evaluation}")
                evaluation = None
            if isinstance(global_result, Exception):
                print(f"   ⚠️ 全局反思异常: {global_result}")
                global_result = None
            if isinstance(evolution_result, Exception):
                print(f"   ⚠️ 演化分析异常: {evolution_result}")
                evolution_result = None
        
        # 如果基础评估失败，创建一个默认的评估结果
        if evaluation is None:
            print("   ⚠️ 基础评估失败，使用默认评估结果")
            evaluation = EvaluationResult(
                overall_score=0.0,
                wcr=0.0,
                rdr=0.0,
                scs=0.0,
                details={}
            )
        
        print("   ✓ 并行评估完成")
        return evaluation, global_result, evolution_result

    def _run_critical_analysis(self, content_result: Dict) -> Optional[Dict]:
        """
        执行批判性分析增强
        
        这是深度优化功能，用于检测和增强内容中的薄弱环节：
        1. 检测缺少定量数据的段落
        2. 检测批判性分析不足的段落
        3. 检测缺少失败模式分析的段落
        4. 检测缺少权衡分析的段落
        
        Args:
            content_result: 包含 mainbody 的内容字典
            
        Returns:
            包含增强内容和报告的字典，或 None（如果分析失败）
        """
        if not HAS_CRITICAL_ANALYZER:
            print("   ⚠️ CriticalAnalysisRefiner 不可用")
            return None
        
        mainbody = content_result.get("mainbody", "")
        if not mainbody or len(mainbody) < 1000:
            print("   ⚠️ 主体内容太短，跳过批判性分析")
            return None
        
        try:
            # 创建批判性分析器
            refiner = CriticalAnalysisRefiner(
                chat_agent=self.chat_agent,
                enable_enhancement=self.config.critical_analysis_auto_enhance
            )
            
            # 分析内容并自动增强（如果启用）
            print("   🔍 分析内容质量...")
            refine_result = refiner.analyze_content(mainbody)
            
            # 生成报告
            report = refiner.get_quality_report(refine_result)
            
            # 统计问题
            total_issues = refine_result.statistics.get("total_issues", 0)
            print(f"   📊 发现 {total_issues} 个潜在问题")
            
            # 检查是否有增强
            enhanced_content = refine_result.refined_content
            enhanced_count = len(refine_result.improvements_made)
            
            if enhanced_count > 0:
                print(f"   ✓ 成功增强 {enhanced_count} 个段落")
            
            return {
                "enhanced_content": enhanced_content if enhanced_count > 0 else None,
                "enhanced_count": enhanced_count,
                "report": report,
                "analysis": refine_result.statistics,
                "total_issues": total_issues
            }
            
        except Exception as e:
            print(f"   ❌ 批判性分析执行失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _split_mainbody_into_sections(
        self,
        mainbody_tex: str,
        *,
        max_chars_per_section: int = 6000,
    ) -> Dict[str, str]:
        """
        将 LaTeX 主体内容按 \\section 分割为 {section_name: content}。

        GlobalReflector 需要按章节输入，以便进行跨章节一致性检查。
        为了避免 prompt 过长，默认对每个章节内容做截断。
        """
        import re

        if not mainbody_tex or not mainbody_tex.strip():
            return {"Full Content": ""}

        pattern = re.compile(r"\\section\{([^}]*)\}")
        matches = list(pattern.finditer(mainbody_tex))
        if not matches:
            snippet = mainbody_tex.strip()
            if len(snippet) > max_chars_per_section:
                snippet = snippet[:max_chars_per_section] + "\n% ... (truncated)"
            return {"Full Content": snippet}

        sections: Dict[str, str] = {}
        for idx, m in enumerate(matches):
            raw_title = (m.group(1) or "").strip()
            section_name = f"Section {idx + 1}: {raw_title}" if raw_title else f"Section {idx + 1}"

            start = m.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(mainbody_tex)
            content = mainbody_tex[start:end].strip()
            if len(content) > max_chars_per_section:
                content = content[:max_chars_per_section] + "\n% ... (truncated)"

            # 避免重复键（例如标题重复）
            unique_name = section_name
            suffix = 2
            while unique_name in sections:
                unique_name = f"{section_name} ({suffix})"
                suffix += 1

            sections[unique_name] = content

        return sections
    
    def _backup_file_before_update(self, file_path: Path, backup_type: str = "auto"):
        """
        在更新文件之前自动备份当前版本
        
        备份策略：
        1. 如果文件存在，备份到 backups/ 子目录
        2. 备份文件名格式: {filename}.{backup_type}_{timestamp}
        3. 保留最近 10 个备份，自动清理旧备份
        
        Args:
            file_path: 要备份的文件路径
            backup_type: 备份类型标识（如 "auto", "step_5" 等）
        """
        if not file_path.exists():
            return
        
        # 创建备份目录
        backup_dir = file_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成备份文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.name}.{backup_type}_{timestamp}"
        backup_path = backup_dir / backup_name
        
        try:
            shutil.copy2(file_path, backup_path)
            print(f"   📦 已备份 {file_path.name} -> {backup_name}")
            
            # 清理旧备份，只保留最近 10 个
            self._cleanup_old_backups(backup_dir, file_path.name, max_keep=10)
        except Exception as e:
            print(f"   ⚠️ 备份 {file_path.name} 失败: {e}")
    
    def _cleanup_old_backups(self, backup_dir: Path, filename_prefix: str, max_keep: int = 10):
        """
        清理旧备份，只保留最近的 max_keep 个
        
        Args:
            backup_dir: 备份目录
            filename_prefix: 文件名前缀（用于匹配备份文件）
            max_keep: 最多保留的备份数量
        """
        try:
            # 查找所有匹配的备份文件
            pattern = f"{filename_prefix}.*"
            backups = list(backup_dir.glob(pattern))
            
            if len(backups) <= max_keep:
                return
            
            # 按修改时间排序，删除最旧的
            backups.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            for old_backup in backups[max_keep:]:
                old_backup.unlink()
        except Exception as e:
            print(f"   ⚠️ 清理旧备份失败: {e}")

    def _generate_latex(
        self,
        outline: SurveyOutline,
        content_result: Dict
    ) -> Path:
        """
        生成LaTeX
        
        优先使用 SurveyX 的 LatexTextBuilder 来生成正确格式的 LaTeX 文档，
        这样可以使用 neurips_2024.sty 样式，并保持与 SurveyX 的一致性。
        
        在生成新版本之前，会自动备份当前版本（如果存在）。
        """
        latex_save_path = self.latex_dir / "survey.tex"
        
        # 在生成新版本之前，备份当前版本
        self._backup_file_before_update(latex_save_path, "step_8_latex")
        
        try:
            # 尝试使用 SurveyX 的 LatexTextBuilder
            from src.modules.latex_handler.latex_text_builder import LatexTextBuilder
            from src.configs.constants import RESOURCE_DIR
            
            init_tex_path = Path(RESOURCE_DIR) / "latex" / "survey.ini.tex"
            
            if init_tex_path.exists():
                print("   📄 使用 SurveyX LatexTextBuilder...")
                
                # 确保 outlines.json 存在
                outlines_path = self.output_dir / "outlines.json"
                abstract_path = self.tmp_dir / "abstract.tex"
                
                # 确定 mainbody 路径
                # 优先使用增强后的多模态内容（包含AI生成的图片和表格）
                mainbody_path = self.tmp_dir / "mainbody_enhanced_multimodal.tex"
                if not mainbody_path.exists():
                    mainbody_path = self.tmp_dir / "mainbody_post_refined.tex"
                if not mainbody_path.exists():
                    mainbody_path = self.tmp_dir / "mainbody.tex"
                
                print(f"   📄 使用主体内容文件: {mainbody_path.name}")
                
                # 使用 LatexTextBuilder
                builder = LatexTextBuilder(init_tex_path=str(init_tex_path))
                builder.run(
                    outlines_path=outlines_path,
                    abstract_path=abstract_path,
                    main_body_path=mainbody_path,
                    latex_save_path=latex_save_path
                )
                
                # 修改作者为 SurveyGraph System
                self._update_latex_author(latex_save_path)
                
                return latex_save_path
            else:
                print("   ⚠️ 未找到 survey.ini.tex，使用简化版 LaTeX")
                
        except ImportError as e:
            print(f"   ⚠️ 无法导入 LatexTextBuilder: {e}，使用简化版 LaTeX")
        except Exception as e:
            print(f"   ⚠️ LatexTextBuilder 失败: {e}，使用简化版 LaTeX")
        
        # 回退到简化版 LaTeX
        latex_content = self._build_latex_document(outline, content_result)
        latex_save_path.write_text(latex_content, encoding='utf-8')
        
        return latex_save_path
    
    def _update_latex_author(self, latex_path: Path):
        """更新 LaTeX 文件中的作者信息为 SurveyGraph System"""
        content = latex_path.read_text(encoding='utf-8')
        
        # 替换 SurveyX 的作者链接为 SurveyGraph System
        import re
        # 匹配 \author{...} 中的内容
        content = re.sub(
            r'\\author\{[^}]*surveyx[^}]*\}',
            r'\\author{SurveyGraph System}',
            content,
            flags=re.IGNORECASE
        )
        
        latex_path.write_text(content, encoding='utf-8')
    
    def _build_latex_document(
        self,
        outline: SurveyOutline,
        content_result: Dict
    ) -> str:
        """构建简化版的LaTeX文档（回退方案）"""
        abstract = content_result.get("abstract", "")
        mainbody = content_result.get("mainbody", "")
        
        latex = r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage[numbers]{natbib}
\usepackage{geometry}
\usepackage{booktabs}
\usepackage{multirow}
\usepackage{adjustbox}
\usepackage{tikz}
\usepackage{forest}
\usepackage{xcolor}
\usetikzlibrary{calc, arrows.meta, intersections, patterns, positioning, shapes.misc, fadings, through,decorations.pathreplacing, shadows, chains, mindmap}

\geometry{margin=1in}

\title{""" + outline.title + r"""}
\author{SurveyGraph System}
\date{\today}

\begin{document}

\maketitle

""" + abstract + r"""

\tableofcontents
\newpage

""" + mainbody + r"""

\bibliographystyle{unsrtnat}
\bibliography{references}

\end{document}
"""
        return latex
    
    def _generate_visualization(
        self,
        mekg_data: Dict,
        outline: SurveyOutline
    ) -> Path:
        """生成可视化"""
        from collections import Counter
        from datetime import datetime

        relation_stats = Counter()
        for rel in mekg_data.get("relations", []) or []:
            rel_type = rel.get("type") or rel.get("relation_type") or "unknown"
            relation_stats[str(rel_type)] += 1

        # 保存可视化数据
        vis_data = {
            "topic": self.config.topic,
            "generated_at": datetime.now().isoformat(),
            "papers_count": mekg_data.get("papers_count", 0),
            "nodes_count": len(mekg_data.get("papers", [])),
            "relations_count": len(mekg_data.get("relations", [])),
            "categories": mekg_data.get("categories", {}),
            "papers": mekg_data.get("papers", []),
            "relations": mekg_data.get("relations", []),
            "relation_stats": dict(relation_stats)
        }
        
        vis_path = self.output_dir / "visualization_data.json"
        with open(vis_path, 'w', encoding='utf-8') as f:
            json.dump(vis_data, f, ensure_ascii=False, indent=2)

        # 生成额外的静态可视化图（不影响主流程，失败则跳过）
        try:
            from mekg.src.visualization.graph_visualizer import GraphVisualizer

            vis_dir = self.output_dir / "visualization"
            GraphVisualizer(max_nodes=300).render(mekg_data, vis_dir)
            print(f"   ✓ 可视化图片已生成: {vis_dir}")
        except Exception as e:
            print(f"   ⚠️ 可视化图片生成失败: {e}")
        
        return vis_path
    
    def _save_papers_for_surveyx(self, mekg_data: Dict):
        """
        保存论文数据供SurveyX后续流程使用
        
        注意：这个方法在 _save_papers_with_mount_info 之后调用，
        如果论文文件已存在则跳过，避免覆盖已有的挂载信息。
        """
        # 构建论文关系映射
        paper_relations = {}
        for rel in mekg_data.get("relations", []):
            source = rel.get("source", "")
            target = rel.get("target", "")
            rel_type = rel.get("type", "")
            confidence = rel.get("confidence", 0)
            
            if source:
                if source not in paper_relations:
                    paper_relations[source] = []
                paper_relations[source].append({
                    "target": target,
                    "type": rel_type,
                    "confidence": confidence
                })
        
        for paper in mekg_data.get("papers", []):
            paper_id = paper.get("id", "")
            if not paper_id:
                continue
            
            # 清理文件名中的非法字符
            safe_paper_id = self._sanitize_filename(paper_id)
            
            paper_path = self.papers_dir / f"{safe_paper_id}.json"
            
            # 如果文件已存在，跳过（避免覆盖已有的挂载信息）
            if paper_path.exists():
                continue
            
            # 获取该论文的关系信息
            relations = paper_relations.get(paper_id, [])
            
            # 构建 attri 字段 - 包含足够的信息供 SurveyX 使用
            attri = {
                "title": paper.get("title", ""),
                "abstract": paper.get("abstract", ""),
                "year": paper.get("year"),
                "citations": paper.get("citations", 0),
                "authors": paper.get("authors", []),
                "category": paper.get("category", ""),
                "subcategory": paper.get("subcategory", ""),
                "method_entities": paper.get("method_entities", []),
                "task_entities": paper.get("task_entities", []),
                "relations": relations[:10] if relations else []
            }
            
            # 转换为SurveyX格式
            # 确保包含 md_text 和 paper_type
            abstract = paper.get("abstract", "")
            
            # 优先使用从 PDF 解析的全文，否则使用摘要
            md_text = paper.get("md_text", "")
            if not md_text:
                md_text = abstract  # 回退到摘要
            
            # 根据分类判断 paper_type
            category = paper.get("category", "").lower()
            subcategory = paper.get("subcategory", "").lower()
            paper_type = "method"
            if "benchmark" in category or "benchmark" in subcategory or "dataset" in category:
                paper_type = "benchmark"
            
            surveyx_paper = {
                "title": paper.get("title", ""),
                "abstract": abstract,
                "md_text": md_text,  # 优先使用 PDF 解析的全文
                "paper_type": paper_type,
                "bib_name": safe_paper_id,  # 使用清理后的 ID 作为 bib_name
                "attri": attri
            }
            
            with open(paper_path, 'w', encoding='utf-8') as f:
                json.dump(surveyx_paper, f, ensure_ascii=False, indent=2)
    
    def _generate_references_bib(self, mekg_data: Dict):
        """
        生成 references.bib 文件
        
        PostRefiner 的 BibNameReplacer 需要这个文件来验证和替换引用名称。
        这个方法从 MEKG 论文数据中生成 BibTeX 格式的参考文献。
        """
        bib_entries = []
        
        # 用于去除非 ASCII 字符的函数
        def remove_non_ascii(s: str) -> str:
            return s.replace(",", "").encode("ascii", "ignore").decode("ascii")
        
        for paper in mekg_data.get("papers", []):
            paper_id = paper.get("id", "")
            if not paper_id:
                continue
            
            title = paper.get("title", "")
            abstract = paper.get("abstract", "")
            year = paper.get("year", "")
            authors = paper.get("authors", [])
            
            # 生成 bib_name（与保存论文时使用的清理后的 paper_id 一致）
            bib_name = self._sanitize_filename(paper_id)
            
            # 处理作者列表
            if isinstance(authors, list):
                if len(authors) > 0 and isinstance(authors[0], dict):
                    author_str = " and ".join([a.get("name", "") for a in authors if a.get("name")])
                else:
                    author_str = " and ".join([str(a) for a in authors if a])
            else:
                author_str = str(authors) if authors else ""
            
            # 清理标题中的特殊字符
            clean_title = remove_non_ascii(title) if title else ""
            
            # 生成 BibTeX 条目
            bib_entry = f"""@article{{{bib_name},
  title={{{clean_title}}},
  author={{{author_str}}},
  year={{{year}}},
}}"""
            bib_entries.append(bib_entry)
        
        # 保存到 latex 目录
        bib_path = self.latex_dir / "references.bib"
        with open(bib_path, 'w', encoding='utf-8') as f:
            f.write("\n\n".join(bib_entries))
        
        print(f"   ✓ 生成 references.bib: {len(bib_entries)} 条引用")


def create_pipeline(
    topic: str,
    output_dir: str = "outputs",
    **kwargs
) -> MEKGSurveyPipeline:
    """
    创建流水线的便捷函数
    
    Args:
        topic: 综述主题
        output_dir: 输出目录
        **kwargs: 其他配置参数
        
    Returns:
        MEKGSurveyPipeline实例
    """
    config = PipelineConfig(
        topic=topic,
        output_dir=Path(output_dir),
        **kwargs
    )
    return MEKGSurveyPipeline(config)


async def run_pipeline(
    topic: str,
    output_dir: str = "outputs",
    mekg_data: Optional[Dict] = None,
    **kwargs
) -> PipelineResult:
    """
    运行流水线的便捷函数
    
    Args:
        topic: 综述主题
        output_dir: 输出目录
        mekg_data: 预先构建的MEKG数据（可选）
        **kwargs: 其他配置参数
        
    Returns:
        PipelineResult对象
    """
    pipeline = create_pipeline(topic, output_dir, **kwargs)
    return await pipeline.run(mekg_data=mekg_data)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="MEKG Survey Pipeline")
    parser.add_argument("--topic", type=str, required=True, help="Survey topic")
    parser.add_argument("--output", type=str, default="outputs", help="Output directory")
    parser.add_argument("--mekg-data", type=str, help="Path to existing MEKG data JSON")
    parser.add_argument("--max-papers", type=int, default=100, help="Max papers to collect")
    parser.add_argument("--skip-collection", action="store_true", help="Skip paper collection")
    
    args = parser.parse_args()
    
    # 加载MEKG数据（如果提供）
    mekg_data = None
    if args.mekg_data:
        with open(args.mekg_data, 'r', encoding='utf-8') as f:
            mekg_data = json.load(f)
    
    # 运行流水线
    result = asyncio.run(run_pipeline(
        topic=args.topic,
        output_dir=args.output,
        mekg_data=mekg_data,
        max_papers=args.max_papers
    ))
    
    if result.success:
        print(f"\n✅ Success! Output: {result.output_dir}")
    else:
        print(f"\n❌ Failed: {result.error}")
