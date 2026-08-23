"""
带反思机制的内容生成器

该模块扩展了 ContentGenerator，集成了章节级反思机制和评分细则评估，
实现"写-评-改"的迭代优化循环。

核心功能:
1. 继承 ContentGenerator 的所有功能
2. 在内容生成后进行章节级反思
3. 基于评分细则进行质量评估
4. 支持可配置的反思策略
5. 支持并行反思模式（先串行生成所有内容，再并行反思）

Reference:
- SciSage: refer/SciSage-main/core/section_reflection_opt.py
- ARISE: refer/ARISE-main/full_detailed_review_rubric.json
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from tqdm import tqdm

from src.configs.config import ADVANCED_CHATAGENT_MODEL, BASE_DIR, CHAT_AGENT_WORKERS, SECTION_REFLECTION_WORKERS
from src.configs.constants import OUTPUT_DIR
from src.configs.logger import get_logger
from src.models.LLM import ChatAgent
from src.models.LLM.utils import load_prompt
from src.models.monitor.time_monitor import TimeMonitor
from src.models.monitor.token_monitor import TokenMonitor
from src.modules.utils import clean_chat_agent_format, load_file_as_string, save_result
from src.schemas.base import Base
from src.schemas.outlines import Outlines, SingleOutline

# 导入反思模块
from src.modules.post_refine.section_reflector import SectionReflector, reflect_section_sync
from src.modules.post_refine.rubric_evaluator import RubricEvaluator, evaluate_survey_with_rubric

# 导入基类
from src.models.generator.content_generator import ContentGenerator

logger = get_logger("src.modules.generator.ReflectiveContentGenerator")


@dataclass
class ReflectionConfig:
    """反思配置"""
    
    # 是否启用章节级反思
    enable_section_reflection: bool = True
    
    # 章节反思最大迭代次数
    section_reflection_max_turns: int = 3
    
    # 质量阈值 (1-5 分制)
    quality_threshold: float = 3.5
    
    # 是否启用全局评估（默认禁用，建议使用 evaluation 模块单独评估）
    enable_global_evaluation: bool = False
    
    # 是否保存反思历史
    save_reflection_history: bool = True
    
    # 需要反思的章节类型 (可选: all, main_body, specific)
    reflection_scope: str = "main_body"
    
    # 跳过反思的章节名称模式
    skip_sections: List[str] = field(default_factory=lambda: [
        "Introduction",
        "Conclusion",
        "Abstract",
        "References"
    ])
    
    # 并行反思配置
    enable_parallel_reflection: bool = True  # 是否启用并行反思
    parallel_reflection_workers: int = SECTION_REFLECTION_WORKERS  # 并行反思的工作线程数
    
    def should_reflect_section(self, section_name: str) -> bool:
        """判断是否应该对该章节进行反思"""
        if self.reflection_scope == "all":
            return True
        
        # 检查是否在跳过列表中
        for skip_pattern in self.skip_sections:
            if skip_pattern.lower() in section_name.lower():
                return False
        
        return True


class ReflectiveContentGenerator(ContentGenerator):
    """
    带反思机制的内容生成器
    
    继承自 ContentGenerator，增加了章节级反思和质量评估功能。
    
    Attributes:
        reflection_config: 反思配置
        section_reflector: 章节反思器
        rubric_evaluator: 评分细则评估器
        reflection_history: 反思历史记录
    """
    
    def __init__(
        self,
        task_id: str,
        reflection_config: Optional[ReflectionConfig] = None
    ):
        """
        初始化带反思机制的内容生成器
        
        Args:
            task_id: 任务 ID
            reflection_config: 反思配置
        """
        super().__init__(task_id)
        
        self.reflection_config = reflection_config or ReflectionConfig()
        self.reflection_history = {}
        
        # 反思器和评估器将在需要时初始化
        self._section_reflector = None
        self._rubric_evaluator = None
    
    def _get_section_reflector(self, chat_agent: ChatAgent) -> SectionReflector:
        """获取或创建章节反思器"""
        if self._section_reflector is None:
            self._section_reflector = SectionReflector(
                chat_agent=chat_agent,
                quality_threshold=self.reflection_config.quality_threshold,
                max_iterations=self.reflection_config.section_reflection_max_turns
            )
        return self._section_reflector
    
    def _get_rubric_evaluator(self, chat_agent: ChatAgent) -> RubricEvaluator:
        """获取或创建评分细则评估器"""
        if self._rubric_evaluator is None:
            self._rubric_evaluator = RubricEvaluator(
                chat_agent=chat_agent,
                use_llm=True
            )
        return self._rubric_evaluator
    
    def write_content_with_reflection(
        self,
        papers: List[str],
        outlines: Outlines,
        written_content: str,
        last_written: str,
        section_title: str,
        section_desc: str,
        chat: ChatAgent,
        related_papers: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        带反思的内容写作
        
        Args:
            papers: 相关论文信息列表
            outlines: 大纲
            written_content: 已写内容
            last_written: 上次写的内容
            section_title: 章节标题
            section_desc: 章节描述
            chat: ChatAgent
            related_papers: 相关论文详细信息
            
        Returns:
            优化后的章节内容
        """
        # 1. 首先生成初始内容
        initial_content = self.write_content_iteratively(
            papers=papers,
            outlines=outlines,
            written_content=written_content,
            last_written=last_written,
            subsection_title=section_title,
            subsection_desc=section_desc,
            chat=chat
        )
        
        # 2. 检查是否需要反思
        if not self.reflection_config.enable_section_reflection:
            return initial_content
        
        if not self.reflection_config.should_reflect_section(section_title):
            logger.info(f"跳过章节 [{section_title}] 的反思")
            return initial_content
        
        # 3. 进行章节级反思
        logger.info(f"开始对章节 [{section_title}] 进行反思优化")
        
        try:
            reflection_result = reflect_section_sync(
                chat_agent=chat,
                section_name=section_title,
                section_content=initial_content,
                paper_title=outlines.title,
                user_query=self.topic,
                outline={"title": outlines.title, "sections": [s.to_dict() for s in outlines.sections]},
                related_papers=related_papers,
                max_iterations=self.reflection_config.section_reflection_max_turns,
                quality_threshold=self.reflection_config.quality_threshold
            )
            
            # 保存反思历史
            if self.reflection_config.save_reflection_history:
                self.reflection_history[section_title] = {
                    "initial_content": initial_content,
                    "final_content": reflection_result["final_content"],
                    "meets_requirements": reflection_result["meets_requirements"],
                    "final_score": reflection_result["final_score"],
                    "iterations": reflection_result["iterations"],
                    "summary": reflection_result["summary"]
                }
            
            logger.info(
                f"章节 [{section_title}] 反思完成: "
                f"满足要求={reflection_result['meets_requirements']}, "
                f"评分={reflection_result['final_score']:.2f}"
            )
            
            return reflection_result["final_content"]
            
        except Exception as e:
            logger.error(f"章节 [{section_title}] 反思失败: {e}")
            # 反思失败时返回初始内容
            return initial_content
    
    def content_fulfill_iter_with_reflection(
        self,
        paper_dir: str,
        outlines: Outlines,
        chat: ChatAgent,
        mainbody_save_path: str,
    ) -> None:
        """
        带反思的迭代内容生成
        
        这是 content_fulfill_iter 的增强版本，支持两种模式：
        1. 串行模式（默认）：在每个章节生成后立即进行反思优化
        2. 并行模式：先串行生成所有内容，然后并行反思所有章节
        
        并行模式可以显著提升效率，因为反思是独立的，不依赖其他章节的反思结果。
        
        支持检查点功能，可以从上次中断的位置恢复。
        """
        # 根据配置选择模式
        if self.reflection_config.enable_parallel_reflection:
            logger.info("使用并行反思模式")
            self._content_fulfill_with_parallel_reflection(
                paper_dir, outlines, chat, mainbody_save_path
            )
        else:
            logger.info("使用串行反思模式")
            self._content_fulfill_with_serial_reflection(
                paper_dir, outlines, chat, mainbody_save_path
            )
    
    def _content_fulfill_with_serial_reflection(
        self,
        paper_dir: str,
        outlines: Outlines,
        chat: ChatAgent,
        mainbody_save_path: str,
    ) -> None:
        """
        串行反思模式：在每个章节生成后立即进行反思优化
        
        这是原始的实现方式。
        """
        sec2info = self.map_section_to_papers(outlines, paper_dir)
        
        # 加载论文详细信息用于反思
        papers_data = self._load_papers_data(paper_dir)
        
        # 检查点文件路径
        checkpoint_path = Path(mainbody_save_path).parent / "content_checkpoint.json"
        
        # 尝试从检查点恢复
        checkpoint_data = self._load_checkpoint(checkpoint_path)
        start_section_idx = 0
        start_subsection_idx = 0
        start_subsubsection_idx = 0
        
        if checkpoint_data:
            start_section_idx = checkpoint_data.get("section_idx", 0)
            start_subsection_idx = checkpoint_data.get("subsection_idx", 0)
            start_subsubsection_idx = checkpoint_data.get("subsubsection_idx", 0)
            mainbody = checkpoint_data.get("mainbody", [])
            written_content = checkpoint_data.get("written_content", f"\\title{{{outlines.title}}}\n")
            self.reflection_history = checkpoint_data.get("reflection_history", {})
            logger.info(f"从检查点恢复: section={start_section_idx}, subsection={start_subsection_idx}, subsubsection={start_subsubsection_idx}")
        else:
            mainbody = []
            written_content = f"\\title{{{outlines.title}}}\n"
        
        # Calculate total units for progress bar
        total_units = self._count_total_content_units(outlines)
        completed_units = self._count_completed_units(outlines, start_section_idx, start_subsection_idx, start_subsubsection_idx)
        tqdm_bar = tqdm(
            total=total_units,
            initial=completed_units,
            desc="writing content with reflection...",
            position=0,
        )

        for i, section in enumerate(outlines.sections):
            # 跳过已完成的章节
            if i < start_section_idx:
                continue
            
            out1_title = section.title
            
            # 如果是恢复的第一个章节，不需要重新添加标题
            if i > start_section_idx or not checkpoint_data:
                written_content += f"\n\\section{{{out1_title}}}\n"
                mainbody.append(f"\\section{{{out1_title}}}")
            
            # Handle sections without subsections
            if section.sub == []:
                if out1_title not in sec2info:
                    papers = []
                else:
                    papers = sec2info[out1_title]

                last_written = ""
                with tqdm(
                    total=max(len(papers), 1),
                    desc=f"{i + 1} {section.title[:15]}",
                    position=1,
                    leave=False,
                ) as bar_1:
                    for k in range(0, max(len(papers), 1), self.ITER_SPAN):
                        tmp_papers = papers[k : k + self.ITER_SPAN]
                        res = self.write_content_iteratively(
                            papers=tmp_papers,
                            outlines=outlines,
                            written_content=written_content,
                            last_written=last_written,
                            subsection_title=section.title,
                            subsection_desc=section.desc,
                            chat=chat,
                        )
                        last_written = res
                        bar_1.update(10)

                # 对章节进行反思
                if self.reflection_config.enable_section_reflection:
                    last_written = self._reflect_content(
                        content=last_written,
                        section_title=section.title,
                        outlines=outlines,
                        chat=chat,
                        papers_data=papers_data,
                        section_paper_hints=sec2info.get(section.title, []),
                    )

                mainbody.append(last_written)
                written_content = "\n\n".join(mainbody)
                tqdm_bar.update()
                
                # 保存检查点
                self._save_checkpoint(checkpoint_path, i + 1, 0, 0, mainbody, written_content)
                continue

            # 确定子章节的起始索引
            subsection_start = start_subsection_idx if i == start_section_idx else 0
            
            for j, subsection in enumerate(section.sub):
                # 跳过已完成的子章节
                if i == start_section_idx and j < subsection_start:
                    continue
                
                out2_title = subsection.title
                
                # 如果是恢复的第一个子章节，不需要重新添加标题
                if j > subsection_start or i > start_section_idx or not checkpoint_data:
                    written_content += f"\n\\subsection{{{out2_title}}}\n"
                    mainbody.append(f"\\subsection{{{out2_title}}}")
                
                if subsection.sub:
                    # 3-level structure
                    # 确定子子章节的起始索引
                    subsubsection_start = start_subsubsection_idx if (i == start_section_idx and j == start_subsection_idx) else 0
                    
                    for k, subsubsection in enumerate(subsection.sub):
                        # 跳过已完成的子子章节
                        if i == start_section_idx and j == start_subsection_idx and k < subsubsection_start:
                            continue
                        
                        out3_title = subsubsection.title
                        
                        # 如果是恢复的第一个子子章节，不需要重新添加标题
                        if k > subsubsection_start or j > subsection_start or i > start_section_idx or not checkpoint_data:
                            written_content += f"\n\\subsubsection{{{out3_title}}}\n"
                            mainbody.append(f"\\subsubsection{{{out3_title}}}")
                        
                        if out3_title not in sec2info:
                            papers = []
                        else:
                            papers = sec2info[out3_title]
                        
                        last_written = ""
                        with tqdm(
                            total=max(len(papers), 1),
                            desc=f"{i + 1}.{j + 1}.{k + 1} {subsubsection.title[:10]}",
                            position=1,
                            leave=False,
                        ) as bar_3:
                            for m in range(0, max(len(papers), 1), self.ITER_SPAN):
                                tmp_papers = papers[m : m + self.ITER_SPAN]
                                res = self.write_content_iteratively(
                                    papers=tmp_papers,
                                    outlines=outlines,
                                    written_content=written_content,
                                    last_written=last_written,
                                    subsection_title=subsubsection.title,
                                    subsection_desc=subsubsection.desc,
                                    chat=chat,
                                )
                                last_written = res
                                bar_3.update(10)
                        
                        # 对子章节进行反思
                        if self.reflection_config.enable_section_reflection:
                            last_written = self._reflect_content(
                                content=last_written,
                                section_title=subsubsection.title,
                                outlines=outlines,
                                chat=chat,
                                papers_data=papers_data,
                                section_paper_hints=sec2info.get(subsubsection.title, []),
                            )
                        
                        mainbody.append(last_written)
                        written_content = "\n\n".join(mainbody)
                        tqdm_bar.update()
                        
                        # 保存检查点
                        self._save_checkpoint(checkpoint_path, i, j, k + 1, mainbody, written_content)
                else:
                    # 2-level structure
                    if out2_title not in sec2info:
                        papers = []
                    else:
                        papers = sec2info[out2_title]

                    last_written = ""
                    with tqdm(
                        total=max(len(papers), 1),
                        desc=f"{i + 1}.{j + 1} {subsection.title[:10]}",
                        position=1,
                        leave=False,
                    ) as bar_2:
                        for k in range(0, max(len(papers), 1), self.ITER_SPAN):
                            tmp_papers = papers[k : k + self.ITER_SPAN]
                            res = self.write_content_iteratively(
                                papers=tmp_papers,
                                outlines=outlines,
                                written_content=written_content,
                                last_written=last_written,
                                subsection_title=subsection.title,
                                subsection_desc=subsection.desc,
                                chat=chat,
                            )
                            last_written = res
                            bar_2.update(10)

                    # 对子章节进行反思
                    if self.reflection_config.enable_section_reflection:
                        last_written = self._reflect_content(
                            content=last_written,
                            section_title=subsection.title,
                            outlines=outlines,
                            chat=chat,
                            papers_data=papers_data,
                            section_paper_hints=sec2info.get(subsection.title, []),
                        )

                    mainbody.append(last_written)
                    written_content = "\n\n".join(mainbody)
                    tqdm_bar.update()
                    
                    # 保存检查点
                    self._save_checkpoint(checkpoint_path, i, j + 1, 0, mainbody, written_content)

        tqdm_bar.close()
        mainbody = "\n\n".join(mainbody)
        
        # Generate section words
        mainbody = self.gen_section_words(mainbody, chat)
        
        # Save result
        save_result(mainbody, mainbody_save_path)
        
        # Save reflection history
        if self.reflection_config.save_reflection_history and self.reflection_history:
            history_path = Path(mainbody_save_path).parent / "reflection_history.json"
            with open(history_path, 'w', encoding='utf-8') as f:
                json.dump(self.reflection_history, f, ensure_ascii=False, indent=2)
            logger.info(f"反思历史已保存到: {history_path}")
        
        # 删除检查点文件（任务完成）
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            logger.info("内容生成完成，已删除检查点文件")
        
        logger.info("content fulfill with reflection done.")
    
    def _content_fulfill_with_parallel_reflection(
        self,
        paper_dir: str,
        outlines: Outlines,
        chat: ChatAgent,
        mainbody_save_path: str,
    ) -> None:
        """
        并行反思模式：先串行生成所有内容，然后并行反思所有章节
        
        这种模式可以显著提升效率，因为：
        1. 内容生成必须串行（需要上下文）
        2. 反思可以并行（每个章节独立）
        
        流程：
        1. 串行生成所有章节内容（不进行反思）
        2. 收集所有需要反思的章节
        3. 并行执行所有章节的反思
        4. 将反思后的内容替换回原位置
        """
        sec2info = self.map_section_to_papers(outlines, paper_dir)
        
        # 加载论文详细信息用于反思
        papers_data = self._load_papers_data(paper_dir)
        
        # 检查点文件路径
        checkpoint_path = Path(mainbody_save_path).parent / "content_checkpoint.json"
        
        # 尝试从检查点恢复
        checkpoint_data = self._load_checkpoint(checkpoint_path)
        start_section_idx = 0
        start_subsection_idx = 0
        start_subsubsection_idx = 0
        
        if checkpoint_data:
            start_section_idx = checkpoint_data.get("section_idx", 0)
            start_subsection_idx = checkpoint_data.get("subsection_idx", 0)
            start_subsubsection_idx = checkpoint_data.get("subsubsection_idx", 0)
            mainbody = checkpoint_data.get("mainbody", [])
            written_content = checkpoint_data.get("written_content", f"\\title{{{outlines.title}}}\n")
            self.reflection_history = checkpoint_data.get("reflection_history", {})
            logger.info(f"从检查点恢复: section={start_section_idx}, subsection={start_subsection_idx}, subsubsection={start_subsubsection_idx}")
        else:
            mainbody = []
            written_content = f"\\title{{{outlines.title}}}\n"
        
        # 用于收集需要反思的章节信息
        # 格式: [(section_title, content_index, section_paper_hints), ...]
        sections_to_reflect: List[Tuple[str, int, List[str]]] = []
        
        # Calculate total units for progress bar
        total_units = self._count_total_content_units(outlines)
        completed_units = self._count_completed_units(outlines, start_section_idx, start_subsection_idx, start_subsubsection_idx)
        tqdm_bar = tqdm(
            total=total_units,
            initial=completed_units,
            desc="Phase 1: generating content...",
            position=0,
        )

        # ========== Phase 1: 串行生成所有内容（不进行反思）==========
        for i, section in enumerate(outlines.sections):
            # 跳过已完成的章节
            if i < start_section_idx:
                continue
            
            out1_title = section.title
            
            # 如果是恢复的第一个章节，不需要重新添加标题
            if i > start_section_idx or not checkpoint_data:
                written_content += f"\n\\section{{{out1_title}}}\n"
                mainbody.append(f"\\section{{{out1_title}}}")
            
            # Handle sections without subsections
            if section.sub == []:
                if out1_title not in sec2info:
                    papers = []
                else:
                    papers = sec2info[out1_title]

                last_written = ""
                with tqdm(
                    total=max(len(papers), 1),
                    desc=f"{i + 1} {section.title[:15]}",
                    position=1,
                    leave=False,
                ) as bar_1:
                    for k in range(0, max(len(papers), 1), self.ITER_SPAN):
                        tmp_papers = papers[k : k + self.ITER_SPAN]
                        res = self.write_content_iteratively(
                            papers=tmp_papers,
                            outlines=outlines,
                            written_content=written_content,
                            last_written=last_written,
                            subsection_title=section.title,
                            subsection_desc=section.desc,
                            chat=chat,
                        )
                        last_written = res
                        bar_1.update(10)

                # 记录需要反思的章节（不立即反思）
                content_index = len(mainbody)
                mainbody.append(last_written)
                
                if self.reflection_config.enable_section_reflection and \
                   self.reflection_config.should_reflect_section(section.title):
                    sections_to_reflect.append((
                        section.title,
                        content_index,
                        sec2info.get(section.title, [])
                    ))
                
                written_content = "\n\n".join(mainbody)
                tqdm_bar.update()
                
                # 保存检查点
                self._save_checkpoint(checkpoint_path, i + 1, 0, 0, mainbody, written_content)
                continue

            # 确定子章节的起始索引
            subsection_start = start_subsection_idx if i == start_section_idx else 0
            
            for j, subsection in enumerate(section.sub):
                # 跳过已完成的子章节
                if i == start_section_idx and j < subsection_start:
                    continue
                
                out2_title = subsection.title
                
                # 如果是恢复的第一个子章节，不需要重新添加标题
                if j > subsection_start or i > start_section_idx or not checkpoint_data:
                    written_content += f"\n\\subsection{{{out2_title}}}\n"
                    mainbody.append(f"\\subsection{{{out2_title}}}")
                
                if subsection.sub:
                    # 3-level structure
                    # 确定子子章节的起始索引
                    subsubsection_start = start_subsubsection_idx if (i == start_section_idx and j == start_subsection_idx) else 0
                    
                    for k, subsubsection in enumerate(subsection.sub):
                        # 跳过已完成的子子章节
                        if i == start_section_idx and j == start_subsection_idx and k < subsubsection_start:
                            continue
                        
                        out3_title = subsubsection.title
                        
                        # 如果是恢复的第一个子子章节，不需要重新添加标题
                        if k > subsubsection_start or j > subsection_start or i > start_section_idx or not checkpoint_data:
                            written_content += f"\n\\subsubsection{{{out3_title}}}\n"
                            mainbody.append(f"\\subsubsection{{{out3_title}}}")
                        
                        if out3_title not in sec2info:
                            papers = []
                        else:
                            papers = sec2info[out3_title]
                        
                        last_written = ""
                        with tqdm(
                            total=max(len(papers), 1),
                            desc=f"{i + 1}.{j + 1}.{k + 1} {subsubsection.title[:10]}",
                            position=1,
                            leave=False,
                        ) as bar_3:
                            for m in range(0, max(len(papers), 1), self.ITER_SPAN):
                                tmp_papers = papers[m : m + self.ITER_SPAN]
                                res = self.write_content_iteratively(
                                    papers=tmp_papers,
                                    outlines=outlines,
                                    written_content=written_content,
                                    last_written=last_written,
                                    subsection_title=subsubsection.title,
                                    subsection_desc=subsubsection.desc,
                                    chat=chat,
                                )
                                last_written = res
                                bar_3.update(10)
                        
                        # 记录需要反思的章节（不立即反思）
                        content_index = len(mainbody)
                        mainbody.append(last_written)
                        
                        if self.reflection_config.enable_section_reflection and \
                           self.reflection_config.should_reflect_section(subsubsection.title):
                            sections_to_reflect.append((
                                subsubsection.title,
                                content_index,
                                sec2info.get(subsubsection.title, [])
                            ))
                        
                        written_content = "\n\n".join(mainbody)
                        tqdm_bar.update()
                        
                        # 保存检查点
                        self._save_checkpoint(checkpoint_path, i, j, k + 1, mainbody, written_content)
                else:
                    # 2-level structure
                    if out2_title not in sec2info:
                        papers = []
                    else:
                        papers = sec2info[out2_title]

                    last_written = ""
                    with tqdm(
                        total=max(len(papers), 1),
                        desc=f"{i + 1}.{j + 1} {subsection.title[:10]}",
                        position=1,
                        leave=False,
                    ) as bar_2:
                        for k in range(0, max(len(papers), 1), self.ITER_SPAN):
                            tmp_papers = papers[k : k + self.ITER_SPAN]
                            res = self.write_content_iteratively(
                                papers=tmp_papers,
                                outlines=outlines,
                                written_content=written_content,
                                last_written=last_written,
                                subsection_title=subsection.title,
                                subsection_desc=subsection.desc,
                                chat=chat,
                            )
                            last_written = res
                            bar_2.update(10)

                    # 记录需要反思的章节（不立即反思）
                    content_index = len(mainbody)
                    mainbody.append(last_written)
                    
                    if self.reflection_config.enable_section_reflection and \
                       self.reflection_config.should_reflect_section(subsection.title):
                        sections_to_reflect.append((
                            subsection.title,
                            content_index,
                            sec2info.get(subsection.title, [])
                        ))
                    
                    written_content = "\n\n".join(mainbody)
                    tqdm_bar.update()
                    
                    # 保存检查点
                    self._save_checkpoint(checkpoint_path, i, j + 1, 0, mainbody, written_content)

        tqdm_bar.close()
        
        # ========== Phase 2: 并行反思所有章节 ==========
        if sections_to_reflect and self.reflection_config.enable_section_reflection:
            logger.info(f"Phase 2: 开始并行反思 {len(sections_to_reflect)} 个章节 (workers={self.reflection_config.parallel_reflection_workers})")
            
            # 准备反思任务
            def reflect_task(task_info: Tuple[str, int, List[str]]) -> Tuple[int, str, Dict[str, Any]]:
                """单个反思任务"""
                section_title, content_index, section_paper_hints = task_info
                original_content = mainbody[content_index]
                
                try:
                    reflected_content = self._reflect_content(
                        content=original_content,
                        section_title=section_title,
                        outlines=outlines,
                        chat=chat,
                        papers_data=papers_data,
                        section_paper_hints=section_paper_hints,
                    )
                    
                    # 返回反思历史
                    history = self.reflection_history.get(section_title, {})
                    return (content_index, reflected_content, history)
                except Exception as e:
                    logger.warning(f"章节 [{section_title}] 并行反思失败: {e}")
                    return (content_index, original_content, {})
            
            # 使用线程池并行执行反思
            with ThreadPoolExecutor(max_workers=self.reflection_config.parallel_reflection_workers) as executor:
                futures = {
                    executor.submit(reflect_task, task_info): task_info
                    for task_info in sections_to_reflect
                }
                
                # 使用 tqdm 显示进度
                with tqdm(
                    total=len(sections_to_reflect),
                    desc="Phase 2: parallel reflection...",
                    position=0,
                ) as pbar:
                    for future in as_completed(futures):
                        task_info = futures[future]
                        section_title = task_info[0]
                        try:
                            content_index, reflected_content, history = future.result()
                            # 更新 mainbody 中的内容
                            mainbody[content_index] = reflected_content
                            # 更新反思历史
                            if history:
                                self.reflection_history[section_title] = history
                        except Exception as e:
                            logger.error(f"章节 [{section_title}] 反思任务异常: {e}")
                        pbar.update(1)
            
            logger.info(f"并行反思完成，共处理 {len(sections_to_reflect)} 个章节")
        
        # ========== Phase 3: 后处理 ==========
        mainbody_str = "\n\n".join(mainbody)
        
        # Generate section words
        mainbody_str = self.gen_section_words(mainbody_str, chat)
        
        # Save result
        save_result(mainbody_str, mainbody_save_path)
        
        # Save reflection history
        if self.reflection_config.save_reflection_history and self.reflection_history:
            history_path = Path(mainbody_save_path).parent / "reflection_history.json"
            with open(history_path, 'w', encoding='utf-8') as f:
                json.dump(self.reflection_history, f, ensure_ascii=False, indent=2)
            logger.info(f"反思历史已保存到: {history_path}")
        
        # 删除检查点文件（任务完成）
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            logger.info("内容生成完成，已删除检查点文件")
        
        logger.info("content fulfill with reflection done.")
    
    def _load_checkpoint(self, checkpoint_path: Path) -> Optional[Dict[str, Any]]:
        """加载检查点数据"""
        if not checkpoint_path.exists():
            return None
        
        try:
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"成功加载检查点: {checkpoint_path}")
            return data
        except Exception as e:
            logger.warning(f"加载检查点失败: {e}")
            return None
    
    def _save_checkpoint(
        self,
        checkpoint_path: Path,
        section_idx: int,
        subsection_idx: int,
        subsubsection_idx: int,
        mainbody: List[str],
        written_content: str
    ) -> None:
        """保存检查点数据"""
        try:
            checkpoint_data = {
                "section_idx": section_idx,
                "subsection_idx": subsection_idx,
                "subsubsection_idx": subsubsection_idx,
                "mainbody": mainbody,
                "written_content": written_content,
                "reflection_history": self.reflection_history,
                "timestamp": time.time()
            }
            with open(checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
            logger.debug(f"检查点已保存: section={section_idx}, subsection={subsection_idx}, subsubsection={subsubsection_idx}")
        except Exception as e:
            logger.warning(f"保存检查点失败: {e}")
    
    def _count_completed_units(
        self,
        outlines: Outlines,
        section_idx: int,
        subsection_idx: int,
        subsubsection_idx: int
    ) -> int:
        """计算已完成的内容单元数量"""
        completed = 0
        
        for i, section in enumerate(outlines.sections):
            if i < section_idx:
                # 整个章节已完成
                if not section.sub:
                    completed += 1
                else:
                    for subsection in section.sub:
                        if not subsection.sub:
                            completed += 1
                        else:
                            completed += len(subsection.sub)
            elif i == section_idx:
                # 当前章节部分完成
                if not section.sub:
                    # 如果没有子章节，且 section_idx 指向下一个，说明已完成
                    pass
                else:
                    for j, subsection in enumerate(section.sub):
                        if j < subsection_idx:
                            if not subsection.sub:
                                completed += 1
                            else:
                                completed += len(subsection.sub)
                        elif j == subsection_idx:
                            if subsection.sub:
                                completed += subsubsection_idx
        
        return completed
    
    def _reflect_content(
        self,
        content: str,
        section_title: str,
        outlines: Outlines,
        chat: ChatAgent,
        papers_data: List[Dict[str, Any]],
        section_paper_hints: Optional[List[str]] = None,
    ) -> str:
        """对内容进行反思优化"""
        if not self.reflection_config.should_reflect_section(section_title):
            logger.debug(f"跳过章节 [{section_title}] 的反思")
            return content
        
        try:
            # 构造“章节相关论文”以提升反思的 grounding：
            # 1) 优先使用正文中实际出现的 citation key
            # 2) 不足时，用该章节挂载的 bib_name 补齐（来自 mount_tree_on_outlines 的 sec2info）
            papers_by_bib = {}
            for paper in papers_data:
                bib = paper.get("bib_name")
                if not bib:
                    continue
                papers_by_bib[str(bib)] = {
                    "bib_name": str(bib),
                    "title": paper.get("title", ""),
                    "abstract": paper.get("abstract", ""),
                }

            # 匹配 \cite{...} 或 \Cite{...} 等引用格式
            cite_pattern = re.compile(r'\\[cC]ite\w*(?:\[[^\]]*\])*\{([^}]+)\}')
            cited_keys: List[str] = []
            for match in cite_pattern.findall(content or ""):
                for key in match.split(","):
                    key = key.strip()
                    if key:
                        cited_keys.append(key)

            related_bibs: List[str] = []
            for key in cited_keys:
                if key in papers_by_bib and key not in related_bibs:
                    related_bibs.append(key)

            if section_paper_hints:
                for hint in section_paper_hints:
                    m = re.search(r"bib_name:\s*(\S+)", hint)
                    if not m:
                        continue
                    bib = m.group(1).strip()
                    if bib in papers_by_bib and bib not in related_bibs:
                        related_bibs.append(bib)

            related_papers = [papers_by_bib[b] for b in related_bibs[:10]]

            reflection_result = reflect_section_sync(
                chat_agent=chat,
                section_name=section_title,
                section_content=content,
                paper_title=outlines.title,
                user_query=self.topic,
                outline={
                    "title": outlines.title,
                    "sections": [s.to_dict() for s in outlines.sections],
                },
                related_papers=related_papers,
                max_iterations=self.reflection_config.section_reflection_max_turns,
                quality_threshold=self.reflection_config.quality_threshold
            )
            
            # 保存反思历史
            if self.reflection_config.save_reflection_history:
                self.reflection_history[section_title] = {
                    "meets_requirements": reflection_result["meets_requirements"],
                    "final_score": reflection_result["final_score"],
                    "iterations": reflection_result["iterations"],
                    "summary": reflection_result["summary"]
                }
            
            logger.info(
                f"章节 [{section_title}] 反思: "
                f"评分={reflection_result['final_score']:.2f}, "
                f"迭代={reflection_result['iterations']}"
            )
            
            return reflection_result["final_content"]
            
        except Exception as e:
            logger.warning(f"章节 [{section_title}] 反思失败: {e}")
            return content
    
    def _load_papers_data(self, paper_dir: str) -> List[Dict[str, Any]]:
        """加载论文数据"""
        papers_data = []
        paper_dir = Path(paper_dir)
        
        for file in os.listdir(paper_dir):
            if not file.endswith(".json"):
                continue
            
            file_path = paper_dir / file
            if not file_path.is_file():
                continue
            
            try:
                paper_data = json.loads(load_file_as_string(file_path))
                papers_data.append(paper_data)
            except Exception as e:
                logger.warning(f"加载论文文件 {file} 失败: {e}")
        
        return papers_data
    
    def evaluate_survey(
        self,
        survey_content: str,
        chat: ChatAgent
    ) -> Dict[str, Any]:
        """
        使用评分细则评估综述质量
        
        Args:
            survey_content: 综述内容
            chat: ChatAgent
            
        Returns:
            评估结果
        """
        evaluator = self._get_rubric_evaluator(chat)
        result = evaluator.evaluate(
            survey_content=survey_content,
            topic=self.topic
        )
        return result.to_dict()
    
    def run(self, enable_reflection: bool = True):
        """
        运行带反思的内容生成流程
        
        Args:
            enable_reflection: 是否启用反思机制
        """
        # 临时设置反思配置
        original_enable = self.reflection_config.enable_section_reflection
        self.reflection_config.enable_section_reflection = enable_reflection
        
        chat_agent = ChatAgent(TokenMonitor(self.task_id, "generate content with reflection"))
        time_monitor = TimeMonitor(self.task_id)
        time_monitor.start("generate content with reflection")

        # 1. Mount trees on outlines
        outlines = Outlines.from_saved(self.outlines_path)
        self.mount_trees_on_outlines(self.paper_dir, outlines, chat_agent)

        tmp_dir = self.work_dir / "tmp"
        if not tmp_dir.exists():
            tmp_dir.mkdir(exist_ok=True, parents=True)

        # 2. Overview the mount details
        mount_detail_fig_path = tmp_dir / "mount_details.jpg"
        self.draw_mount_details(self.paper_dir, mount_detail_fig_path)

        # 3. Content fulfill with reflection
        main_body_raw_path = tmp_dir / "mainbody.raw.tex"
        
        if enable_reflection:
            self.content_fulfill_iter_with_reflection(
                self.paper_dir, outlines, chat_agent, main_body_raw_path
            )
        else:
            self.content_fulfill_iter(
                self.paper_dir, outlines, chat_agent, main_body_raw_path
            )

        # 4. Generate abstract
        abstract_save_path = tmp_dir / "abstract.tex"
        self.gen_abstract(main_body_raw_path, abstract_save_path, chat_agent)

        # 5. Post revise
        main_body_save_path = tmp_dir / "mainbody.tex"
        self.post_revise(main_body_raw_path, main_body_save_path, self.paper_dir)

        # 6. Global evaluation (optional)
        if self.reflection_config.enable_global_evaluation:
            try:
                survey_content = load_file_as_string(main_body_save_path)
                evaluation_result = self.evaluate_survey(survey_content, chat_agent)
                
                # 保存评估结果
                eval_path = tmp_dir / "rubric_evaluation.json"
                with open(eval_path, 'w', encoding='utf-8') as f:
                    json.dump(evaluation_result, f, ensure_ascii=False, indent=2)
                logger.info(f"评分细则评估结果已保存到: {eval_path}")
                logger.info(f"综述总评分: {evaluation_result['total_score']:.2f}/5.0")
            except Exception as e:
                logger.warning(f"全局评估失败: {e}")

        time_monitor.end("generate content with reflection")
        
        # 恢复原始配置
        self.reflection_config.enable_section_reflection = original_enable


# 便捷函数
def create_reflective_generator(
    task_id: str,
    enable_reflection: bool = True,
    max_iterations: int = 3,
    quality_threshold: float = 3.5
) -> ReflectiveContentGenerator:
    """
    创建带反思机制的内容生成器
    
    Args:
        task_id: 任务 ID
        enable_reflection: 是否启用反思
        max_iterations: 最大迭代次数
        quality_threshold: 质量阈值
        
    Returns:
        ReflectiveContentGenerator 实例
    """
    config = ReflectionConfig(
        enable_section_reflection=enable_reflection,
        section_reflection_max_turns=max_iterations,
        quality_threshold=quality_threshold
    )
    
    return ReflectiveContentGenerator(task_id, config)


if __name__ == "__main__":
    # 测试代码
    task_id = "test_reflective"
    
    # 创建带反思的生成器
    generator = create_reflective_generator(
        task_id=task_id,
        enable_reflection=True,
        max_iterations=2,
        quality_threshold=3.5
    )
    
    print(f"ReflectiveContentGenerator 创建成功")
    print(f"反思配置: {generator.reflection_config}")
