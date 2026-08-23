"""
Multimodal Refiner - 多模态内容优化器

在综述生成后，将从参考文献中提取的图片插入到适当位置。

主要功能:
1. 收集所有参考文献中的图片
2. 分析图片并筛选适合的图片
3. 决定图片插入位置
4. 将图片插入到综述内容中
"""

import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from src.configs.logger import get_logger
from src.configs.constants import OUTPUT_DIR, RESOURCE_DIR
from src.configs.utils import load_latest_task_id
from src.modules.utils import load_file_as_string, save_result
from src.modules.post_refine.base_refiner import BaseRefiner
from src.modules.multimodal.image_analyzer import ImageAnalyzer, ImageAnalysisResult
from src.modules.multimodal.image_insertion import ImageInsertion, InsertionDecision
from src.schemas.outlines import Outlines

logger = get_logger("src.modules.post_refine.MultimodalRefiner")


class MultimodalRefiner(BaseRefiner):
    """
    多模态内容优化器
    
    在综述生成后，分析参考文献中的图片并将适合的图片插入到综述中
    """
    
    def __init__(
        self,
        task_id: str = None,
        multimodal_api_url: str = None,
        multimodal_api_key: str = None,
        multimodal_model: str = "Qwen3-VL-Plus",
        llm_api_url: str = None,
        llm_api_key: str = None,
        llm_model: str = "glm-4.6",
        **kwargs
    ):
        """
        初始化多模态优化器
        
        Args:
            task_id: 任务ID
            multimodal_api_url: 多模态API地址
            multimodal_api_key: 多模态API密钥
            multimodal_model: 多模态模型名称
            llm_api_url: LLM API地址
            llm_api_key: LLM API密钥
            llm_model: LLM模型名称
        """
        super().__init__(task_id=task_id, **kwargs)
        
        multimodal_api_url = multimodal_api_url or os.getenv("MULTIMODAL_API_URL", "")
        llm_api_url = llm_api_url or os.getenv("REMOTE_URL", "")

        # 设置路径
        self.refined_mainbody_path = Path(
            f"{OUTPUT_DIR}/{self.task_id}/tmp/mainbody_multimodal_refined.tex"
        )
        self.images_dir = self.task_dir / "extracted_images"
        self.figs_dir = self.task_dir / "latex" / "figs"
        
        # 初始化图片分析器
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
        
        # 配置
        self.max_images_total = 8          # 最大总图片数
        self.max_images_per_section = 2    # 每章节最大图片数
        self.min_relevance_score = 6.0     # 最低相关性分数
        self.min_quality_score = 5.0       # 最低质量分数
        self.min_academic_value = 6.0      # 最低学术价值分数
        
        # 加载大纲
        self.outlines = self._load_outlines()
        
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
    
    def collect_images(self) -> List[Dict]:
        """
        收集所有可用的图片
        
        从以下来源收集:
        1. MinerU解析输出的图片
        2. 论文元数据中的图片链接
        """
        images = []
        
        # 1. 从MinerU解析输出收集
        if self.images_dir.exists():
            for img_path in self.images_dir.glob("**/*"):
                if img_path.suffix.lower() in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
                    images.append({
                        "path": img_path,
                        "source": "mineru",
                        "context": self._get_image_context(img_path)
                    })
        
        # 2. 从论文目录收集
        papers_dir = self.task_dir / "papers"
        if papers_dir.exists():
            for paper_file in papers_dir.glob("*.json"):
                try:
                    with open(paper_file, "r", encoding="utf-8") as f:
                        paper = json.load(f)
                    
                    # 检查是否有图片字段
                    paper_images = paper.get("image", [])
                    if paper_images:
                        for img_url in paper_images[:3]:  # 每篇论文最多3张
                            images.append({
                                "path": img_url,
                                "source": "paper_metadata",
                                "context": paper.get("title", ""),
                                "paper_title": paper.get("title", ""),
                                "paper_abstract": paper.get("abstract", "")[:500]
                            })
                except Exception as e:
                    logger.warning(f"Failed to load paper {paper_file}: {e}")
        
        logger.info(f"Collected {len(images)} images")
        return images
    
    def _get_image_context(self, img_path: Path) -> str:
        """获取图片上下文"""
        # 尝试从同目录的markdown文件获取上下文
        md_files = list(img_path.parent.glob("*.md"))
        
        if md_files:
            try:
                md_content = md_files[0].read_text(encoding="utf-8")
                # 查找图片引用
                img_name = img_path.name
                if img_name in md_content:
                    # 提取周围文本
                    idx = md_content.find(img_name)
                    start = max(0, idx - 200)
                    end = min(len(md_content), idx + 200)
                    return md_content[start:end]
            except Exception:
                pass
        
        return ""
    
    def analyze_images(
        self,
        images: List[Dict],
        survey_topic: str = ""
    ) -> List[ImageAnalysisResult]:
        """
        分析所有图片
        
        Args:
            images: 图片信息列表
            survey_topic: 综述主题
            
        Returns:
            分析结果列表
        """
        # 过滤出本地图片（URL图片暂不支持直接分析）
        local_images = [
            img for img in images 
            if isinstance(img.get("path"), Path) or 
               (isinstance(img.get("path"), str) and not img["path"].startswith("http"))
        ]
        
        if not local_images:
            logger.warning("No local images to analyze")
            return []
        
        logger.info(f"Analyzing {len(local_images)} local images...")
        
        # 批量分析
        results = self.image_analyzer.batch_analyze(
            images=local_images,
            paper_title=survey_topic,
            max_workers=2
        )
        
        return results
    
    def filter_images(
        self,
        analysis_results: List[ImageAnalysisResult]
    ) -> List[ImageAnalysisResult]:
        """
        筛选适合插入的图片
        
        Args:
            analysis_results: 分析结果列表
            
        Returns:
            筛选后的结果列表
        """
        filtered = self.image_analyzer.filter_suitable_images(
            results=analysis_results,
            min_relevance=self.min_relevance_score,
            min_quality=self.min_quality_score,
            min_academic_value=self.min_academic_value
        )
        
        # 限制总数
        return filtered[:self.max_images_total]
    
    def decide_insertions(
        self,
        filtered_results: List[ImageAnalysisResult],
        survey_topic: str = ""
    ) -> List[InsertionDecision]:
        """
        决定图片插入位置
        
        Args:
            filtered_results: 筛选后的分析结果
            survey_topic: 综述主题
            
        Returns:
            插入决策列表
        """
        if not self.outlines:
            logger.warning("No outlines available, skipping insertion decisions")
            return []
        
        decisions = self.image_inserter.batch_decide(
            image_analyses=filtered_results,
            survey_outline=self.outlines,
            survey_topic=survey_topic,
            max_total_images=self.max_images_total
        )
        
        return decisions
    
    def insert_images(
        self,
        mainbody_content: str,
        decisions: List[InsertionDecision]
    ) -> str:
        """
        将图片插入到综述内容中
        
        Args:
            mainbody_content: 原始综述内容
            decisions: 插入决策列表
            
        Returns:
            插入图片后的内容
        """
        return self.image_inserter.insert_images_to_survey(
            survey_content=mainbody_content,
            decisions=decisions
        )
    
    def run(self, mainbody_path: Path = None) -> str:
        """
        运行多模态优化流程
        
        Args:
            mainbody_path: 主体内容文件路径
            
        Returns:
            优化后的内容
        """
        if mainbody_path is None:
            mainbody_path = self.mainbody_path
        
        logger.info("Starting multimodal refinement...")
        
        # 1. 加载原始内容
        mainbody_content = load_file_as_string(mainbody_path)
        
        # 2. 收集图片
        images = self.collect_images()
        
        if not images:
            logger.info("No images found, skipping multimodal refinement")
            save_result(mainbody_content, self.refined_mainbody_path)
            return mainbody_content
        
        # 3. 获取综述主题
        survey_topic = ""
        if self.outlines:
            survey_topic = self.outlines.get("title", "")
        
        # 4. 分析图片
        analysis_results = self.analyze_images(images, survey_topic)
        
        if not analysis_results:
            logger.info("No images analyzed successfully")
            save_result(mainbody_content, self.refined_mainbody_path)
            return mainbody_content
        
        # 5. 筛选图片
        filtered_results = self.filter_images(analysis_results)
        
        if not filtered_results:
            logger.info("No suitable images after filtering")
            save_result(mainbody_content, self.refined_mainbody_path)
            return mainbody_content
        
        logger.info(f"Selected {len(filtered_results)} images for potential insertion")
        
        # 6. 决定插入位置
        decisions = self.decide_insertions(filtered_results, survey_topic)
        
        # 7. 插入图片
        refined_content = self.insert_images(mainbody_content, decisions)
        
        # 8. 保存结果
        save_result(refined_content, self.refined_mainbody_path)
        logger.info(f"Saved multimodal refined content to {self.refined_mainbody_path}")
        
        # 9. 生成摘要报告
        summary = self.image_inserter.generate_image_summary(decisions)
        summary_path = self.task_dir / "tmp" / "image_insertion_summary.md"
        save_result(summary, summary_path)
        logger.info(f"Saved insertion summary to {summary_path}")
        
        return refined_content


# 测试代码
if __name__ == "__main__":
    task_id = load_latest_task_id()
    
    if task_id:
        print(f"Task ID: {task_id}")
        refiner = MultimodalRefiner(task_id=task_id)
        refiner.run()
    else:
        print("No task ID found")
