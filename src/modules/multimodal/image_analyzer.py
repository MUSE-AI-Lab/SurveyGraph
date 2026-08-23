"""
Image Analyzer - 多模态LLM图片分析器

使用多模态大语言模型分析学术论文中的图片，提取关键信息。

主要功能:
1. 分析图片内容和类型
2. 评估图片质量和相关性
3. 生成图片描述
4. 推荐适合的综述章节
"""

import json
import base64
import os
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm

from src.configs.logger import get_logger
from src.modules.utils import load_file_as_string

logger = get_logger("src.modules.multimodal.ImageAnalyzer")


@dataclass
class ImageAnalysisResult:
    """图片分析结果"""
    image_path: Path
    description: str              # 图片详细描述
    image_type: str               # 图片类型
    key_concepts: List[str]       # 关键概念
    relevance_score: float        # 相关性评分 (1-10)
    quality_score: float          # 质量评分 (1-10)
    academic_value: float         # 学术价值评分 (1-10)
    suggested_sections: List[str] # 建议插入的章节类型
    is_suitable: bool             # 是否适合插入综述
    reason: str                   # 判断理由
    raw_response: str             # 原始响应
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["image_path"] = str(self.image_path)
        return d


class ImageAnalyzer:
    """
    多模态LLM图片分析器
    
    使用多模态大语言模型（如Qwen-VL）分析学术论文图片
    """
    
    # 图片类型定义
    IMAGE_TYPES = [
        "architecture",    # 系统/模型架构图
        "flowchart",       # 流程图
        "experiment",      # 实验结果图
        "comparison",      # 对比图/表
        "illustration",    # 概念示意图
        "screenshot",      # 截图
        "photo",           # 照片
        "diagram",         # 图表
        "other"            # 其他
    ]
    
    # 章节类型定义
    SECTION_TYPES = [
        "introduction",
        "background",
        "methodology",
        "architecture",
        "experiment",
        "analysis",
        "discussion",
        "application"
    ]
    
    def __init__(
        self,
        api_url: str = "https://apis.iflow.cn/v1/chat/completions",
        api_key: str = None,
        model: str = "Qwen3-VL-Plus",
        timeout: int = 60
    ):
        """
        初始化图片分析器
        
        Args:
            api_url: 多模态API地址
            api_key: API密钥
            model: 模型名称
            timeout: 请求超时时间
        """
        self.api_url = api_url
        self.api_key = api_key or os.getenv("MULTIMODAL_API_KEY", "")
        self.model = model
        self.timeout = timeout
        
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def _encode_image(self, image_path: Path) -> str:
        """将图片编码为base64"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    
    def _get_image_mime_type(self, image_path: Path) -> str:
        """获取图片MIME类型"""
        suffix = image_path.suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp"
        }
        return mime_types.get(suffix, "image/png")
    
    def _build_analysis_prompt(self, context: str = "") -> str:
        """构建图片分析prompt"""
        prompt = """你是一个学术论文图片分析专家。请仔细分析这张来自学术论文的图片。

## 分析任务

请提供以下信息：

1. **图片描述** (description): 详细描述图片内容，包括展示的内容、结构、关键元素等。

2. **图片类型** (image_type): 从以下类型中选择一个最匹配的：
   - architecture: 系统/模型架构图
   - flowchart: 流程图、工作流程
   - experiment: 实验结果图（曲线图、柱状图、散点图等）
   - comparison: 对比图或对比表格
   - illustration: 概念示意图、说明图
   - screenshot: 界面截图
   - diagram: 其他图表
   - other: 其他类型

3. **关键概念** (key_concepts): 列出图片中涉及的3-5个关键技术概念或术语。

4. **相关性评分** (relevance_score): 1-10分，评估图片对理解论文核心内容的重要性。
   - 10分：核心架构图或关键实验结果
   - 7-9分：重要的方法说明或对比分析
   - 4-6分：辅助说明图
   - 1-3分：装饰性或不太相关的图片

5. **质量评分** (quality_score): 1-10分，评估图片的清晰度、专业性和可读性。
   - 10分：非常清晰、专业、易读
   - 7-9分：清晰、较专业
   - 4-6分：一般
   - 1-3分：模糊或难以理解

6. **学术价值** (academic_value): 1-10分，评估图片在学术综述中的价值。
   - 考虑：是否能帮助读者理解概念？是否具有代表性？是否适合引用？

7. **建议章节** (suggested_sections): 这张图片适合放在综述的哪类章节？可多选：
   - introduction: 引言
   - background: 背景知识
   - methodology: 方法论
   - architecture: 架构设计
   - experiment: 实验分析
   - analysis: 深入分析
   - discussion: 讨论
   - application: 应用场景

8. **是否适合** (is_suitable): 这张图片是否适合插入到学术综述中？(true/false)

9. **判断理由** (reason): 简要说明为什么适合或不适合插入综述。

"""
        
        if context:
            prompt += f"""
## 图片上下文信息
{context}

"""
        
        prompt += """
## 输出格式
请以JSON格式输出，确保可以被正确解析：
```json
{
    "description": "图片描述",
    "image_type": "类型",
    "key_concepts": ["概念1", "概念2", "概念3"],
    "relevance_score": 8,
    "quality_score": 7,
    "academic_value": 8,
    "suggested_sections": ["methodology", "architecture"],
    "is_suitable": true,
    "reason": "判断理由"
}
```

请只输出JSON，不要有其他内容。
"""
        return prompt
    
    def analyze_image(
        self,
        image_path: Path,
        context: str = "",
        paper_title: str = "",
        paper_abstract: str = ""
    ) -> ImageAnalysisResult:
        """
        分析单张图片
        
        Args:
            image_path: 图片路径
            context: 图片上下文（如caption、周围文本）
            paper_title: 论文标题
            paper_abstract: 论文摘要
            
        Returns:
            ImageAnalysisResult对象
        """
        image_path = Path(image_path)
        
        if not image_path.exists():
            logger.error(f"Image not found: {image_path}")
            return self._create_error_result(image_path, "Image not found")
        
        # 构建上下文
        full_context = ""
        if paper_title:
            full_context += f"论文标题: {paper_title}\n"
        if paper_abstract:
            full_context += f"论文摘要: {paper_abstract[:500]}...\n"
        if context:
            full_context += f"图片上下文: {context}\n"
        
        # 构建prompt
        prompt = self._build_analysis_prompt(full_context)
        
        # 编码图片
        try:
            image_base64 = self._encode_image(image_path)
            mime_type = self._get_image_mime_type(image_path)
        except Exception as e:
            logger.error(f"Failed to encode image: {e}")
            return self._create_error_result(image_path, f"Failed to encode: {e}")
        
        # 构建请求
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.3,
            "max_tokens": 2000
        }
        
        # 发送请求
        try:
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.error(f"API error: {response.status_code} - {response.text[:200]}")
                return self._create_error_result(
                    image_path, 
                    f"API error: {response.status_code}"
                )
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # 解析响应
            return self._parse_response(image_path, content)
            
        except requests.RequestException as e:
            logger.error(f"Request error: {e}")
            return self._create_error_result(image_path, f"Request error: {e}")
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            return self._create_error_result(image_path, f"Analysis error: {e}")
    
    def _parse_response(
        self,
        image_path: Path,
        response: str
    ) -> ImageAnalysisResult:
        """解析LLM响应"""
        try:
            # 尝试提取JSON
            json_str = response
            
            # 如果响应包含markdown代码块，提取其中的JSON
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                json_str = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                json_str = response[start:end].strip()
            
            data = json.loads(json_str)
            
            return ImageAnalysisResult(
                image_path=image_path,
                description=data.get("description", ""),
                image_type=data.get("image_type", "other"),
                key_concepts=data.get("key_concepts", []),
                relevance_score=float(data.get("relevance_score", 5)),
                quality_score=float(data.get("quality_score", 5)),
                academic_value=float(data.get("academic_value", 5)),
                suggested_sections=data.get("suggested_sections", []),
                is_suitable=data.get("is_suitable", False),
                reason=data.get("reason", ""),
                raw_response=response
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.debug(f"Response: {response[:500]}")
            
            # 尝试从文本中提取信息
            return self._extract_from_text(image_path, response)
    
    def _extract_from_text(
        self,
        image_path: Path,
        response: str
    ) -> ImageAnalysisResult:
        """从非JSON响应中提取信息"""
        # 简单的文本解析
        description = response[:500] if response else "Unable to analyze"
        
        # 尝试识别图片类型
        image_type = "other"
        for t in self.IMAGE_TYPES:
            if t.lower() in response.lower():
                image_type = t
                break
        
        return ImageAnalysisResult(
            image_path=image_path,
            description=description,
            image_type=image_type,
            key_concepts=[],
            relevance_score=5.0,
            quality_score=5.0,
            academic_value=5.0,
            suggested_sections=["methodology"],
            is_suitable=False,
            reason="Unable to parse response properly",
            raw_response=response
        )
    
    def _create_error_result(
        self,
        image_path: Path,
        error_message: str
    ) -> ImageAnalysisResult:
        """创建错误结果"""
        return ImageAnalysisResult(
            image_path=image_path,
            description=f"Error: {error_message}",
            image_type="other",
            key_concepts=[],
            relevance_score=0.0,
            quality_score=0.0,
            academic_value=0.0,
            suggested_sections=[],
            is_suitable=False,
            reason=error_message,
            raw_response=""
        )
    
    def batch_analyze(
        self,
        images: List[Dict],
        paper_title: str = "",
        paper_abstract: str = "",
        max_workers: int = 3
    ) -> List[ImageAnalysisResult]:
        """
        批量分析图片
        
        Args:
            images: 图片信息列表，每个包含 path 和可选的 context
            paper_title: 论文标题
            paper_abstract: 论文摘要
            max_workers: 并发数
            
        Returns:
            分析结果列表
        """
        results = []
        
        logger.info(f"Analyzing {len(images)} images...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            
            for img_info in images:
                if isinstance(img_info, dict):
                    path = Path(img_info.get("path", img_info.get("image_path", "")))
                    context = img_info.get("context", img_info.get("caption", ""))
                else:
                    path = Path(img_info)
                    context = ""
                
                future = executor.submit(
                    self.analyze_image,
                    path,
                    context,
                    paper_title,
                    paper_abstract
                )
                futures[future] = path
            
            for future in tqdm(
                as_completed(futures),
                total=len(futures),
                desc="Analyzing images"
            ):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    path = futures[future]
                    logger.error(f"Failed to analyze {path}: {e}")
                    results.append(self._create_error_result(path, str(e)))
        
        return results
    
    def filter_suitable_images(
        self,
        results: List[ImageAnalysisResult],
        min_relevance: float = 6.0,
        min_quality: float = 5.0,
        min_academic_value: float = 6.0
    ) -> List[ImageAnalysisResult]:
        """
        筛选适合插入综述的图片
        
        Args:
            results: 分析结果列表
            min_relevance: 最低相关性分数
            min_quality: 最低质量分数
            min_academic_value: 最低学术价值分数
            
        Returns:
            筛选后的结果列表
        """
        filtered = []
        
        for result in results:
            if not result.is_suitable:
                continue
            if result.relevance_score < min_relevance:
                continue
            if result.quality_score < min_quality:
                continue
            if result.academic_value < min_academic_value:
                continue
            
            filtered.append(result)
        
        # 按学术价值排序
        filtered.sort(key=lambda x: x.academic_value, reverse=True)
        
        logger.info(f"Filtered {len(filtered)} suitable images from {len(results)}")
        return filtered
    
    def group_by_section(
        self,
        results: List[ImageAnalysisResult]
    ) -> Dict[str, List[ImageAnalysisResult]]:
        """
        按建议章节分组
        
        Args:
            results: 分析结果列表
            
        Returns:
            按章节分组的字典
        """
        grouped = {section: [] for section in self.SECTION_TYPES}
        grouped["other"] = []
        
        for result in results:
            if not result.suggested_sections:
                grouped["other"].append(result)
            else:
                for section in result.suggested_sections:
                    if section in grouped:
                        grouped[section].append(result)
                    else:
                        grouped["other"].append(result)
        
        # 移除空组
        return {k: v for k, v in grouped.items() if v}


# 测试代码
if __name__ == "__main__":
    analyzer = ImageAnalyzer()
    
    # 测试分析
    test_image = Path("test_image.png")
    if test_image.exists():
        result = analyzer.analyze_image(
            test_image,
            context="Figure 1: Model architecture",
            paper_title="A Survey on Large Language Models"
        )
        print(f"Type: {result.image_type}")
        print(f"Suitable: {result.is_suitable}")
        print(f"Scores: R={result.relevance_score}, Q={result.quality_score}, A={result.academic_value}")
        print(f"Description: {result.description[:200]}...")
    else:
        print("No test image found")
