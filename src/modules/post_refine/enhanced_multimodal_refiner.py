"""
Enhanced Multimodal Refiner - 增强版多模态内容优化器

在综述生成后，动态决定并生成多样化的视觉元素，包括：
1. 从参考文献中提取和引用图片
2. LLM自主选择生成表格、图表、流程图等
3. 多样化的视觉样式
4. AI生成专业学术插图（使用Gemini 3 Pro Image Preview）

主要功能:
1. 收集所有参考文献中的图片
2. 分析综述内容，决定需要什么视觉元素
3. 动态生成多样化的表格和图表
4. AI生成专业插图（带迭代优化）
5. 将视觉元素插入到综述内容中
"""

import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from src.configs.logger import get_logger
from src.configs.constants import OUTPUT_DIR, RESOURCE_DIR
from src.configs.config import (
    REMOTE_URL,
    TOKEN,
    DEFAULT_CHATAGENT_MODEL,
    MULTIMODAL_API_URL,
    MULTIMODAL_API_KEY,
    MULTIMODAL_MODEL,
    AI_IMAGE_API_URL,
    AI_IMAGE_API_KEY,
    AI_IMAGE_MODEL,
)
from src.configs.utils import load_latest_task_id
from src.modules.utils import load_file_as_string, save_result
from src.modules.post_refine.base_refiner import BaseRefiner
from src.modules.multimodal.image_analyzer import ImageAnalyzer, ImageAnalysisResult
from src.modules.multimodal.image_insertion import ImageInsertion, InsertionDecision
from src.modules.multimodal.dynamic_visual_generator import (
    DynamicVisualGenerator,
    VisualElementDecision,
    VisualElementType,
    ReferenceImage,
    ExistingVisualElement
)
from src.modules.multimodal.ai_image_generator import (
    AIImageGenerator,
    GeneratedImage,
    ImageGenerationDecision
)

logger = get_logger("src.modules.post_refine.EnhancedMultimodalRefiner")


class EnhancedMultimodalRefiner(BaseRefiner):
    """
    增强版多模态内容优化器
    
    结合原有的图片插入功能和新的动态视觉元素生成功能
    """
    
    def __init__(
        self,
        task_id: str = None,
        multimodal_api_url: str = MULTIMODAL_API_URL,
        multimodal_api_key: str = MULTIMODAL_API_KEY,
        multimodal_model: str = MULTIMODAL_MODEL,
        llm_api_url: str = REMOTE_URL,
        llm_api_key: str = TOKEN,
        llm_model: str = DEFAULT_CHATAGENT_MODEL,
        image_gen_api_url: str = AI_IMAGE_API_URL,
        image_gen_api_key: str = AI_IMAGE_API_KEY,
        image_gen_model: str = AI_IMAGE_MODEL,
        enable_dynamic_visuals: bool = True,
        enable_reference_images: bool = True,
        enable_ai_images: bool = True,
        year_start: int = None,
        year_end: int = None,
        **kwargs
    ):
        """
        初始化增强版多模态优化器
        
        Args:
            task_id: 任务ID
            multimodal_api_url: 多模态API地址
            multimodal_api_key: 多模态API密钥
            multimodal_model: 多模态模型名称
            llm_api_url: LLM API地址
            llm_api_key: LLM API密钥
            llm_model: LLM模型名称
            image_gen_api_url: AI生图API地址
            image_gen_api_key: AI生图API密钥
            image_gen_model: AI生图模型名称
            enable_dynamic_visuals: 是否启用动态视觉元素生成
            enable_reference_images: 是否启用参考文献图片引用
            enable_ai_images: 是否启用AI生图功能
        """
        super().__init__(task_id=task_id, **kwargs)
        
        # 设置路径
        self.refined_mainbody_path = Path(
            f"{OUTPUT_DIR}/{self.task_id}/tmp/mainbody_enhanced_multimodal.tex"
        )
        self.images_dir = self.task_dir / "extracted_images"
        self.figs_dir = self.task_dir / "latex" / "figs"
        
        # 功能开关
        self.enable_dynamic_visuals = enable_dynamic_visuals
        self.enable_reference_images = enable_reference_images
        self.enable_ai_images = enable_ai_images
        
        # 初始化图片分析器（用于参考文献图片）
        self.image_analyzer = ImageAnalyzer(
            api_url=multimodal_api_url,
            api_key=multimodal_api_key,
            model=multimodal_model
        )
        
        # 初始化图片插入器
        self.image_inserter = ImageInsertion(
            api_url=llm_api_url,
            api_key=llm_api_key,
            model=llm_model,
            task_id=task_id
        )
        
        # 初始化动态视觉生成器
        self.visual_generator = DynamicVisualGenerator(
            api_url=llm_api_url,
            api_key=llm_api_key,
            model=llm_model,
            task_id=task_id
        )
        
        # 初始化AI图片生成器
        self.ai_image_generator = AIImageGenerator(
            image_api_url=image_gen_api_url,
            image_api_key=image_gen_api_key,
            image_model=image_gen_model,
            eval_api_url=multimodal_api_url,
            eval_api_key=multimodal_api_key,
            eval_model=multimodal_model,
            llm_api_url=llm_api_url,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            task_id=task_id
        )
        
        # 配置 - 优化后的限制，确保生成的视觉元素数量适中
        self.max_reference_images = 2       # 最大参考文献图片数
        self.max_generated_visuals = 2      # 最大生成的动态视觉元素数（TikZ图）
        self.max_ai_images = 3              # 最大AI生成图片数
        self.min_relevance_score = 7.0      # 最低相关性分数（提高）
        self.min_quality_score = 6.0        # 最低质量分数（提高）
        self.min_academic_value = 7.0       # 最低学术价值分数（提高）
        
        # 年份范围（用于时间线生成）
        self.year_start = year_start
        self.year_end = year_end
        
        # 已存在的视觉元素信息（用于避免重复）
        self.existing_tables: List[Dict] = []
        self.existing_tikz_elements: List[Dict] = []
        
        # 加载大纲
        self.outlines = self._load_outlines()
        
        # 尝试从任务配置中加载年份范围
        self._load_year_range_from_config()
        
    def _load_outlines(self) -> Optional[Dict]:
        """加载综述大纲"""
        outlines_path = self.task_dir / "outlines.json"
        
        if outlines_path.exists():
            try:
                with open(outlines_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load outlines: {e}")
        
        return None
    
    def _load_year_range_from_config(self):
        """从任务配置文件中加载年份范围"""
        if self.year_start is not None and self.year_end is not None:
            return  # 已经设置了年份范围
        
        # 尝试从 task_config.json 加载
        task_config_path = self.task_dir / "task_config.json"
        if task_config_path.exists():
            try:
                with open(task_config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    if self.year_start is None:
                        self.year_start = config.get("year_start", 2020)
                    if self.year_end is None:
                        self.year_end = config.get("year_end", 2026)
                    logger.info(f"Loaded year range from task_config: {self.year_start}-{self.year_end}")
                    return
            except Exception as e:
                logger.debug(f"Failed to load task_config.json: {e}")
        
        # 尝试从 tmp_config.json 加载
        tmp_config_path = self.task_dir / "tmp_config.json"
        if tmp_config_path.exists():
            try:
                with open(tmp_config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    if self.year_start is None:
                        self.year_start = config.get("year_start", 2020)
                    if self.year_end is None:
                        self.year_end = config.get("year_end", 2026)
                    logger.info(f"Loaded year range from tmp_config: {self.year_start}-{self.year_end}")
                    return
            except Exception as e:
                logger.debug(f"Failed to load tmp_config.json: {e}")
        
        # 默认值
        if self.year_start is None:
            self.year_start = 2020
        if self.year_end is None:
            self.year_end = 2026
        logger.info(f"Using default year range: {self.year_start}-{self.year_end}")
    
    def collect_and_analyze_reference_images(
        self,
        survey_topic: str = ""
    ) -> List[InsertionDecision]:
        """
        收集并分析参考文献中的图片
        
        Returns:
            图片插入决策列表
        """
        if not self.enable_reference_images:
            return []
        
        logger.info("Collecting reference images...")
        
        # 收集图片
        images = []
        
        # 从MinerU输出目录收集
        mineru_dir = self.task_dir / "mineru_output"
        if mineru_dir.exists():
            for paper_dir in mineru_dir.iterdir():
                if paper_dir.is_dir():
                    for img_path in paper_dir.glob("**/images/*"):
                        if img_path.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                            images.append({
                                "path": img_path,
                                "source": "mineru",
                                "context": self._get_image_context(img_path)
                            })
        
        # 从extracted_images目录收集
        if self.images_dir.exists():
            for img_path in self.images_dir.glob("**/*"):
                if img_path.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                    images.append({
                        "path": img_path,
                        "source": "extracted",
                        "context": self._get_image_context(img_path)
                    })
        
        if not images:
            logger.info("No reference images found")
            return []
        
        logger.info(f"Found {len(images)} reference images")
        
        # 分析图片
        local_images = [
            img for img in images 
            if isinstance(img.get("path"), Path) or 
               (isinstance(img.get("path"), str) and not img["path"].startswith("http"))
        ]
        
        if not local_images:
            return []
        
        # 限制分析数量
        local_images = local_images[:20]
        
        logger.info(f"Analyzing {len(local_images)} images...")
        
        analysis_results = self.image_analyzer.batch_analyze(
            images=local_images,
            paper_title=survey_topic,
            max_workers=2
        )
        
        # 筛选适合的图片
        filtered = self.image_analyzer.filter_suitable_images(
            results=analysis_results,
            min_relevance=self.min_relevance_score,
            min_quality=self.min_quality_score,
            min_academic_value=self.min_academic_value
        )
        
        # 限制数量
        filtered = filtered[:self.max_reference_images]
        
        if not filtered:
            logger.info("No suitable reference images after filtering")
            return []
        
        logger.info(f"Selected {len(filtered)} reference images")
        
        # 决定插入位置
        if not self.outlines:
            logger.warning("No outlines available for image insertion")
            return []
        
        decisions = self.image_inserter.batch_decide(
            image_analyses=filtered,
            survey_outline=self.outlines,
            survey_topic=survey_topic,
            max_total_images=self.max_reference_images
        )
        
        return decisions
    
    def _get_image_context(self, img_path: Path) -> str:
        """获取图片上下文"""
        # 尝试从同目录的markdown文件获取上下文
        md_files = list(img_path.parent.glob("*.md"))
        if not md_files:
            md_files = list(img_path.parent.parent.glob("*.md"))
        
        if md_files:
            try:
                md_content = md_files[0].read_text(encoding="utf-8")
                img_name = img_path.name
                if img_name in md_content:
                    idx = md_content.find(img_name)
                    start = max(0, idx - 200)
                    end = min(len(md_content), idx + 200)
                    return md_content[start:end]
            except:
                pass
        
        return ""
    
    def set_existing_tables(self, tables: List[Dict]):
        """
        设置已存在的表格信息，用于避免重复生成
        
        Args:
            tables: 表格信息列表，每个字典包含:
                - caption: 表格标题
                - description: 表格描述
                - section: 目标章节
                - topics: 涉及的主题关键词列表
        """
        self.existing_tables = tables
        logger.info(f"Set {len(tables)} existing tables for visual element deduplication")
    
    def generate_dynamic_visuals(
        self,
        mainbody_content: str,
        survey_topic: str = ""
    ) -> tuple:
        """
        生成动态视觉元素
        
        Args:
            mainbody_content: 综述主体内容
            survey_topic: 综述主题
            
        Returns:
            (修改后的内容, 决策列表)
        """
        if not self.enable_dynamic_visuals:
            return mainbody_content, []
        
        logger.info("Generating dynamic visual elements...")
        logger.info(f"Using year range for timeline: {self.year_start}-{self.year_end}")
        
        # 运行动态视觉生成（传递年份范围和已有表格信息）
        modified_content, decisions = self.visual_generator.run(
            mainbody_content=mainbody_content,
            outlines=self.outlines or {},
            survey_topic=survey_topic,
            year_range=(self.year_start, self.year_end),
            existing_tables=self.existing_tables
        )
        
        # 收集生成的TikZ元素信息，供AI图片生成器使用
        self.existing_tikz_elements = self.visual_generator.get_generated_elements_info()
        logger.info(f"Collected {len(self.existing_tikz_elements)} TikZ elements for AI image deduplication")
        
        return modified_content, decisions
    
    def generate_ai_images(
        self,
        mainbody_content: str,
        survey_topic: str = ""
    ) -> tuple:
        """
        使用AI生成专业学术插图
        
        Args:
            mainbody_content: 综述主体内容
            survey_topic: 综述主题
            
        Returns:
            (修改后的内容, 生成的图片列表)
        """
        if not self.enable_ai_images:
            logger.info("AI image generation disabled; skipping generate_ai_images step")
            return mainbody_content, []
        
        logger.info("Generating AI images...")
        logger.info(f"Passing {len(self.existing_tables)} tables and {len(self.existing_tikz_elements)} TikZ elements for deduplication")
        
        # 运行AI图片生成（传递已有表格和TikZ元素信息）
        modified_content, generated_images = self.ai_image_generator.run(
            mainbody_content=mainbody_content,
            outlines=self.outlines or {},
            survey_topic=survey_topic,
            existing_tables=self.existing_tables,
            existing_tikz_elements=self.existing_tikz_elements
        )
        
        return modified_content, generated_images

    def run(self, mainbody_path: Path = None) -> str:
        """
        运行增强版多模态优化流程
        
        Args:
            mainbody_path: 主体内容文件路径
            
        Returns:
            优化后的内容
        """
        if mainbody_path is None:
            mainbody_path = self.mainbody_path
        
        logger.info("Starting enhanced multimodal refinement...")
        
        # 1. 加载原始内容
        mainbody_content = load_file_as_string(mainbody_path)
        
        # 2. 获取综述主题
        survey_topic = ""
        if self.outlines:
            survey_topic = self.outlines.get("title", "")
        
        # 3. 处理参考文献图片
        ref_image_decisions = []
        if self.enable_reference_images:
            ref_image_decisions = self.collect_and_analyze_reference_images(survey_topic)
            
            # 插入参考文献图片
            if ref_image_decisions:
                mainbody_content = self.image_inserter.insert_images_to_survey(
                    survey_content=mainbody_content,
                    decisions=ref_image_decisions
                )
                logger.info(f"Inserted {len([d for d in ref_image_decisions if d.should_insert])} reference images")
        
        # 4. 生成动态视觉元素（表格、TikZ图等）
        visual_decisions = []
        if self.enable_dynamic_visuals:
            mainbody_content, visual_decisions = self.generate_dynamic_visuals(
                mainbody_content,
                survey_topic
            )
            logger.info(f"Generated {len([d for d in visual_decisions if d.latex_code])} dynamic visual elements")
        
        # 5. 生成AI图片（使用Gemini 3 Pro Image Preview）
        ai_generated_images = []
        if self.enable_ai_images:
            mainbody_content, ai_generated_images = self.generate_ai_images(
                mainbody_content,
                survey_topic
            )
            logger.info(f"Generated {len(ai_generated_images)} AI images")
        else:
            logger.info("AI image stage disabled; skipping AI image generation")
        
        # 6. 保存结果
        # 保存到增强后的文件
        save_result(mainbody_content, self.refined_mainbody_path)
        logger.info(f"Saved enhanced multimodal content to {self.refined_mainbody_path}")
        
        # 同时更新 mainbody_post_refined.tex，确保后续流程使用增强后的内容
        post_refined_path = self.task_dir / "tmp" / "mainbody_post_refined.tex"
        if post_refined_path.exists():
            save_result(mainbody_content, post_refined_path)
            logger.info(f"Also updated {post_refined_path}")
        
        # 7. 生成综合报告
        self._generate_summary_report(ref_image_decisions, visual_decisions, ai_generated_images)
        
        return mainbody_content
    
    def _generate_summary_report(
        self,
        ref_image_decisions: List[InsertionDecision],
        visual_decisions: List[VisualElementDecision],
        ai_generated_images: List[GeneratedImage] = None
    ):
        """生成综合报告"""
        report = """# Enhanced Multimodal Refinement Report

## Overview
"""
        
        # 参考文献图片统计
        if ref_image_decisions:
            inserted_images = [d for d in ref_image_decisions if d.should_insert]
            report += f"""
## Reference Images
- Total analyzed: {len(ref_image_decisions)}
- Inserted: {len(inserted_images)}

### Inserted Images:
"""
            for d in inserted_images:
                report += f"- **{d.generated_caption}** in Section {d.target_section}\n"
        
        # 动态视觉元素统计
        if visual_decisions:
            generated = [d for d in visual_decisions if d.latex_code]
            report += f"""
## Dynamic Visual Elements
- Total decisions: {len(visual_decisions)}
- Generated: {len(generated)}

### By Type:
"""
            type_counts = {}
            for d in generated:
                t = d.element_type.value
                type_counts[t] = type_counts.get(t, 0) + 1
            
            for t, count in type_counts.items():
                report += f"- {t}: {count}\n"
            
            report += "\n### Details:\n"
            for d in generated:
                report += f"""
**{d.element_type.value}** in Section {d.target_section}
- Description: {d.description}
- Style: {d.style_preference}
- Priority: {d.priority}
"""
        
        # AI生成图片统计
        if ai_generated_images:
            report += f"""
## AI Generated Images
- Total generated: {len(ai_generated_images)}
- Max iterations per image: {self.ai_image_generator.max_iterations}

### Generated Images:
"""
            for i, img in enumerate(ai_generated_images, 1):
                report += f"""
### Image {i}
- **Section**: {img.target_section}
- **Description**: {img.description}
- **Quality Score**: {img.quality_score}/10
- **Iterations Used**: {img.iteration}
- **Evaluation**: {img.evaluation_feedback[:200]}...
"""
        
        # 保存报告
        report_path = self.task_dir / "tmp" / "enhanced_multimodal_report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        
        logger.info(f"Saved summary report to {report_path}")


# 测试代码
if __name__ == "__main__":
    task_id = load_latest_task_id()
    
    if task_id:
        print(f"Task ID: {task_id}")
        refiner = EnhancedMultimodalRefiner(task_id=task_id)
        refiner.run()
    else:
        print("No task ID found")
