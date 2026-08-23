"""
@Reference:
1. How to create llama index templates: https://blog.csdn.net/lovechris00/article/details/137782020

Enhanced with dynamic visual element generation for diverse survey outputs.
"""

import json
from pathlib import Path
from typing import List, Dict
import traceback

from src.configs.constants import OUTPUT_DIR, RESOURCE_DIR
from src.configs.config import ENABLE_AI_IMAGES
from src.configs.logger import get_logger
from src.configs.utils import load_latest_task_id
from src.models.monitor.token_monitor import TokenMonitor
from src.models.LLM import ChatAgent
from src.models.monitor.time_monitor import TimeMonitor
from src.modules.latex_handler.latex_comparison_table_builder import (
    LatexComparisonTableBuilder,
)
from src.modules.latex_handler.latex_figure_builder import LatexFigureBuilder
from src.modules.latex_handler.latex_list_table_builder import LatexListTableBuilder
from src.modules.latex_handler.latex_summary_table_builder import (
    LatexSummaryTableBuilder,
)
from src.modules.latex_handler.latex_survey_table_builder import (
    LatexSurveyTableBuilder,
    SurveyTableType,
)
from src.modules.post_refine import (
    FigRetrieveRefiner,
    RagRefiner,
    RuleBasedRefiner,
    SectionRewriter,
    EnhancedMultimodalRefiner,
)
from src.modules.post_refine.base_refiner import BaseRefiner
from src.modules.utils import save_result, load_file_as_string

logger = get_logger("src.models.post_refine.PostRefiner")


class PostRefiner(BaseRefiner):
    def __init__(self, task_id: str = None, **kwargs) -> None:
        llamaindex_topk = (
            50 if "llamaindex_topk" not in kwargs else kwargs["llamaindex_topk"]
        )
        task_id = load_latest_task_id() if task_id is None else task_id
        assert task_id is not None
        super().__init__(task_id, **kwargs)
        self.paper_dir = Path(f"{OUTPUT_DIR}/{self.task_id}/papers")
        self.mainbody_path = Path(f"{OUTPUT_DIR}/{self.task_id}/tmp/mainbody.tex")
        self.refined_mainbody_path = Path(
            f"{OUTPUT_DIR}/{self.task_id}/tmp/mainbody_post_refined.tex"
        )

        self.max_retry_times = 2
        self.max_words = 10000
        
        # 动态视觉元素生成开关
        self.enable_dynamic_visuals = kwargs.get("enable_dynamic_visuals", True)
        self.enable_reference_images = kwargs.get("enable_reference_images", True)
        self.enable_ai_images = kwargs.get("enable_ai_images", ENABLE_AI_IMAGES)
        
        # 专业综述表格生成开关（新增）
        self.enable_survey_tables = kwargs.get("enable_survey_tables", True)
        
        # 存储已生成的表格信息（用于避免后续生成重复的视觉元素）
        self.generated_table_info: List[Dict] = []
        self.table_info_path = Path(f"{OUTPUT_DIR}/{self.task_id}/tmp/generated_tables.json")
        
        # 尝试加载已保存的表格信息（支持断点续传）
        self._load_generated_table_info()

        # refine settings
        if "papers" not in kwargs:
            self.papers = self.load_papers(self.paper_dir)
        else:
            self.papers = kwargs["papers"]
        logger.info(f"PostRefiner load {len(self.papers)} papers")
        self.llamaindex_topk = llamaindex_topk

        # refining modules
        self.llamaindex_store_local = False
        if "llamaindex_wrapper" in kwargs:
            self.llamaindex_wrapper = kwargs["llamaindex_wrapper"]
            self.rag_refiner = RagRefiner(
                task_id,
                llamaindex_store_local=self.llamaindex_store_local,
                papers=self.papers,
                llamaindex_wrapper=self.llamaindex_wrapper,
            )
        else:
            self.rag_refiner = RagRefiner(
                task_id,
                llamaindex_store_local=self.llamaindex_store_local,
                papers=self.papers,
            )
            self.llamaindex_wrapper = self.rag_refiner.llamaindex_wrapper
        self.sec_rewriter = SectionRewriter(task_id, papers=self.papers)
        self.fig_builder = LatexFigureBuilder(task_id=task_id)

        self.rule_based_refiner = RuleBasedRefiner(task_id=task_id, papers=self.papers)
        self.fig_retrieve_refiner = FigRetrieveRefiner(
            task_id=task_id,
            llamaindex_topk=llamaindex_topk,
            papers=self.papers,
            llamaindex_wrapper=self.llamaindex_wrapper,
        )
        
        # 增强版多模态优化器 - 用于动态生成多样化视觉元素
        self.enhanced_multimodal_refiner = EnhancedMultimodalRefiner(
            task_id=task_id,
            enable_dynamic_visuals=self.enable_dynamic_visuals,
            enable_reference_images=self.enable_reference_images,
            enable_ai_images=self.enable_ai_images,
        )

        # -- tables
        chat_agent = ChatAgent(TokenMonitor(task_id, "generate table"))
        self.paper_dir = Path(f"{OUTPUT_DIR}/{str(self.task_id)}/papers")
        self.tmp_path = Path(f"{OUTPUT_DIR}/{str(self.task_id)}/tmp/table_gen")
        self.latex_path = Path(f"{OUTPUT_DIR}/{str(self.task_id)}/latex")
        self.prompt_dir = Path(f"{RESOURCE_DIR}/LLM/prompts/latex_table_builder")
        self.mainbody_tex_path = Path(
            f"{OUTPUT_DIR}/{str(self.task_id)}/tmp/mainbody_post_refined.tex"
        )
        self.outlines_path = Path(f"{OUTPUT_DIR}/{str(self.task_id)}/outlines.json")

        self.summary_table_builder = LatexSummaryTableBuilder(
            main_body_path=self.mainbody_tex_path,
            tmp_path=self.tmp_path,
            outline_path=self.outlines_path,
            latex_path=self.latex_path,
            paper_dir=self.paper_dir,
            prompt_dir=self.prompt_dir,
            chat_agent=chat_agent,
        )
        self.list_table_builder = LatexListTableBuilder(
            main_body_path=self.mainbody_tex_path,
            tmp_path=self.tmp_path,
            outline_path=self.outlines_path,
            latex_path=self.latex_path,
            paper_dir=self.paper_dir,
            prompt_dir=self.prompt_dir,
            chat_agent=chat_agent,
        )
        self.comparison_table_builder = LatexComparisonTableBuilder(
            main_body_path=self.mainbody_tex_path,
            tmp_path=self.tmp_path,
            outline_path=self.outlines_path,
            latex_path=self.latex_path,
            paper_dir=self.paper_dir,
            prompt_dir=self.prompt_dir,
            chat_agent=chat_agent,
        )
        
        # 专业综述表格生成器（新增）- 生成像顶会论文那样系统化的表格
        self.survey_table_builder = LatexSurveyTableBuilder(
            main_body_path=self.mainbody_tex_path,
            tmp_path=self.tmp_path,
            outline_path=self.outlines_path,
            latex_path=self.latex_path,
            paper_dir=self.paper_dir,
            prompt_dir=self.prompt_dir,
            chat_agent=chat_agent,
        )

    def _load_generated_table_info(self):
        """从文件加载已生成的表格信息"""
        if self.table_info_path.exists():
            try:
                with open(self.table_info_path, "r", encoding="utf-8") as f:
                    self.generated_table_info = json.load(f)
                logger.info(f"Loaded {len(self.generated_table_info)} generated tables info from {self.table_info_path}")
            except Exception as e:
                logger.warning(f"Failed to load generated tables info: {e}")

    def _save_generated_table_info(self):
        """保存已生成的表格信息到文件"""
        try:
            self.table_info_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.table_info_path, "w", encoding="utf-8") as f:
                json.dump(self.generated_table_info, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved generated tables info to {self.table_info_path}")
        except Exception as e:
            logger.warning(f"Failed to save generated tables info: {e}")

    def generate_tables(self, mainbody_path: Path = None, use_survey_tables: bool = None) -> List[Dict]:
        """
        生成表格（summary table, list table, comparison table, survey table）
        
        Args:
            mainbody_path: 主体内容文件路径。如果为 None，则自动检测：
                          优先使用 mainbody_post_refined.tex，如果不存在则使用 mainbody.tex
            use_survey_tables: 是否使用专业综述表格生成器。如果为 None，则使用实例属性 enable_survey_tables
            
        Returns:
            生成的表格信息列表，用于后续避免重复生成视觉元素
        """
        time_monitor = TimeMonitor(self.task_id)
        time_monitor.start("generate tabel")

        # 确定要使用的 mainbody 文件路径
        if mainbody_path is None:
            if self.refined_mainbody_path.exists():
                mainbody_path = self.refined_mainbody_path
                logger.info(f"Using refined mainbody: {mainbody_path}")
            elif self.mainbody_path.exists():
                mainbody_path = self.mainbody_path
                logger.warning(f"mainbody_post_refined.tex not found, falling back to mainbody.tex")
                # 复制 mainbody.tex 到 mainbody_post_refined.tex，以便表格构建器可以在其上修改
                import shutil
                shutil.copy(self.mainbody_path, self.refined_mainbody_path)
                mainbody_path = self.refined_mainbody_path
            else:
                logger.error("No mainbody file found, skipping table generation")
                time_monitor.end("generate tabel")
                return
        
        # 更新表格构建器的路径（如果与初始化时不同）
        if mainbody_path != self.mainbody_tex_path:
            logger.info(f"Updating table builders to use: {mainbody_path}")
            self.summary_table_builder.main_body_path = mainbody_path
            self.list_table_builder.main_body_path = mainbody_path
            self.comparison_table_builder.main_body_path = mainbody_path
            self.survey_table_builder.main_body_path = mainbody_path

        # 确定是否使用专业综述表格
        if use_survey_tables is None:
            use_survey_tables = self.enable_survey_tables

        # -- 专业综述表格生成（新增）
        # 如果启用，优先使用专业综述表格生成器，它会生成更系统化、更专业的表格
        # 使用 run_all() 方法通过 router 机制生成多个不同类型的精品表格
        if use_survey_tables:
            logger.info("Using professional survey table builder with router for diverse tables")
            try:
                # 使用 run_all() 来生成多个不同类型的表格
                generated_tables = self.survey_table_builder.run_all()
                logger.info(f"Professional survey tables generated successfully: {len(generated_tables)} tables")
                
                # 收集生成的表格信息，用于后续避免重复生成视觉元素
                self.generated_table_info = self.survey_table_builder.get_generated_table_info()
                self._save_generated_table_info()  # 保存到文件
                logger.info(f"Collected {len(self.generated_table_info)} table info for visual element deduplication")
            except Exception as e:
                tb_str = traceback.format_exc()
                logger.error(f"Error generating survey tables: {e}; Traceback: {tb_str}")
                # 如果专业表格生成失败，回退到传统表格生成
                logger.info("Falling back to traditional table generation")
                use_survey_tables = False

        # -- 传统表格生成（作为补充或回退）
        if not use_survey_tables:
            try:
                self.summary_table_builder.run()
            except Exception as e:
                tb_str = traceback.format_exc()
                logger.error(f"An error occurred: {e}; The traceback: {tb_str}")

            try:
                self.list_table_builder.run()
            except Exception as e:
                tb_str = traceback.format_exc()
                logger.error(f"An error occurred: {e}; The traceback: {tb_str}")

            try:
                self.comparison_table_builder.run()
            except Exception as e:
                tb_str = traceback.format_exc()
                logger.error(f"An error occurred: {e}; The traceback: {tb_str}")

        time_monitor.end("generate tabel")
        return self.generated_table_info
    
    def generate_survey_tables(self, mainbody_path: Path = None, table_type: SurveyTableType = None):
        """
        专门生成专业综述表格的方法
        
        这个方法使用 router 机制智能选择表格类型，生成像顶会论文那样系统化的表格。
        
        支持的表格类型包括：
        - benchmark_comparison: 基准数据集对比表
        - method_comparison: 方法对比表
        - performance_comparison_table: 性能对比表（带最佳结果高亮）
        - evidence_table: 证据引用表
        - trend_analysis_table: 趋势分析表（带箭头符号）
        - statistics_table: 统计数据表
        - distribution_matrix_table: 分布矩阵表
        - formula_comparison_table: 公式对比表
        - application_overview_table: 应用概览表
        
        特点：
        - Router 机制自动选择 2-4 种不同类型的表格
        - 确保不重复生成同类型表格
        - 每个表格针对不同章节生成
        
        Args:
            mainbody_path: 主体内容文件路径
            table_type: 指定表格类型，如果为 None 则使用 router 自动选择多种类型
        """
        time_monitor = TimeMonitor(self.task_id)
        time_monitor.start("generate survey tables")

        # 确定要使用的 mainbody 文件路径
        if mainbody_path is None:
            if self.refined_mainbody_path.exists():
                mainbody_path = self.refined_mainbody_path
            elif self.mainbody_path.exists():
                import shutil
                shutil.copy(self.mainbody_path, self.refined_mainbody_path)
                mainbody_path = self.refined_mainbody_path
            else:
                logger.error("No mainbody file found, skipping survey table generation")
                time_monitor.end("generate survey tables")
                return
        
        # 更新表格构建器的路径
        self.survey_table_builder.main_body_path = mainbody_path

        try:
            if table_type:
                # 生成指定类型的表格
                self.survey_table_builder.run(table_type=table_type)
            else:
                # 自动检测并生成多个表格
                self.survey_table_builder.run_all()
            logger.info("Professional survey tables generated successfully")
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(f"Error generating survey tables: {e}; Traceback: {tb_str}")

        time_monitor.end("generate survey tables")

    def generate_dynamic_visuals(self, mainbody_path: Path, existing_tables: List[Dict] = None):
        """
        生成动态视觉元素（表格、图表、参考文献图片等）
        
        LLM会自主决定在每个章节中生成什么类型的视觉元素
        
        Args:
            mainbody_path: 主体内容文件路径
            existing_tables: 已生成的表格信息列表，用于避免重复生成视觉元素
        """
        time_monitor = TimeMonitor(self.task_id)
        time_monitor.start("generate dynamic visuals")
        
        # 如果没有传入已有表格信息，使用实例变量
        if existing_tables is None:
            existing_tables = self.generated_table_info
        
        # 将已有表格信息传递给 enhanced_multimodal_refiner
        if existing_tables:
            self.enhanced_multimodal_refiner.set_existing_tables(existing_tables)
            logger.info(f"Passed {len(existing_tables)} existing tables to multimodal refiner for deduplication")
        
        try:
            self.enhanced_multimodal_refiner.run(mainbody_path=mainbody_path)
            logger.info("Dynamic visual elements generated successfully")
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(f"Error generating dynamic visuals: {e}; Traceback: {tb_str}")
        
        time_monitor.end("generate dynamic visuals")

    def refine_text(self, mainbody_path=None):
        """
        只执行文本优化部分，不执行表格和动态视觉元素生成
        
        这是为了支持 pipeline 的细粒度拆分：
        - Step 4: 文本优化 (refine_text)
        - Step 5: 表格生成 (generate_tables)
        - Step 6: 动态视觉元素生成 (generate_dynamic_visuals)
        
        Args:
            mainbody_path: 输入的 mainbody.tex 文件路径，如果为 None 则使用默认路径
            
        Returns:
            优化后的内容字符串
        """
        time_monitor = TimeMonitor(self.task_id)
        time_monitor.start("refine text")

        if mainbody_path is None:
            mainbody_path = self.mainbody_path

        try_times = 0
        final_refined_content = ""
        
        while try_times < self.max_retry_times:
            # rag_refiner
            self.rag_refiner.run(mainbody_path=mainbody_path)
            # sec_rewriter
            self.sec_rewriter.run(mainbody_path=self.rag_refiner.refined_mainbody_path)
            # fig_builder
            self.fig_builder.run(mainbody_path=self.sec_rewriter.refined_mainbody_path)
            # rule_based_refiner
            final_refined_content = self.rule_based_refiner.run(
                mainbody_path=self.fig_builder.fig_mainbody_path
            )
            # save the final refined content
            save_result(final_refined_content, self.refined_mainbody_path)
            
            words_count = len(final_refined_content.strip().split())
            if words_count < self.max_words:
                logger.debug(f"核验通过，refine_text后的main body总字数为{words_count}")
                break
            else:
                try_times += 1
                logger.debug(
                    f"核验不通过，refine_text后的main body总字数为{words_count}；重新生成，trying times {try_times}, max trying: {self.max_retry_times}"
                )

        logger.info(f"Refine text and save content to {self.refined_mainbody_path}")
        time_monitor.end("refine text")
        return final_refined_content

    def run(self, mainbody_path=None):
        time_monitor = TimeMonitor(self.task_id)
        time_monitor.start("post refine")

        if mainbody_path is None:
            mainbody_path = self.mainbody_path

        try_times = 0
        while try_times < self.max_retry_times:
            # rag_refiner
            self.rag_refiner.run(mainbody_path=mainbody_path)
            # fig_retrieve_refiner
            # self.fig_retrieve_refiner.run(mainbody_path=self.rag_refiner.refined_mainbody_path)
            # sec_rewriter
            self.sec_rewriter.run(mainbody_path=self.rag_refiner.refined_mainbody_path)
            # fig_builder
            self.fig_builder.run(mainbody_path=self.sec_rewriter.refined_mainbody_path)
            # rule_based_refiner
            final_refined_content = self.rule_based_refiner.run(
                mainbody_path=self.fig_builder.fig_mainbody_path
            )
            # save the final refined content
            save_result(final_refined_content, self.refined_mainbody_path)
            # generate tables (原有的固定模板表格)
            generated_table_info = self.generate_tables()
            
            # 生成动态视觉元素（LLM自主选择的多样化图表和参考文献图片）
            # 传递已生成的表格信息，避免生成重复主题的视觉元素
            if self.enable_dynamic_visuals or self.enable_reference_images:
                self.generate_dynamic_visuals(self.refined_mainbody_path, generated_table_info)
                # 重新加载内容（因为动态视觉生成可能修改了文件）
                final_refined_content = load_file_as_string(self.refined_mainbody_path)
            
            words_count = len(final_refined_content.strip().split())
            if words_count < self.max_words:
                logger.debug(f"核验通过，postrefine后的main body总字数为{words_count}")
                break
            else:
                try_times += 1
                logger.debug(
                    f"核验不通过，postrefine后的main body总字数为{words_count}；postrefine后的main重新生成，trying times {try_times}, max trying: {self.max_retry_times}"
                )

        logger.info(f"Post refine and save content to {self.refined_mainbody_path}")
        time_monitor.end("post refine")
        return final_refined_content


# python -m src.models.post_refine.post_refiner
if __name__ == "__main__":
    task_id = load_latest_task_id()
    post_refiner = PostRefiner(task_id)
    # mainbody_path = Path(f"{OUTPUT_DIR}/{task_id}/tmp/mainbody_sec_rewritten.tex")
    mainbody_path = None
    post_refiner.run(mainbody_path=mainbody_path)
