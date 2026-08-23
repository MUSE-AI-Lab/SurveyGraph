"""
AI Image Generator - AI生图模块

使用Transformer Diffusion模型生成专业的学术插图。

主要功能:
1. 根据综述内容生成详细的生图prompt
2. 调用AI生图模型生成图片
3. 使用多模态模型评估生成的图片质量
4. 迭代优化，最多2轮（每轮重新生成prompt），选择最佳图片
5. 支持每篇综述最多生成5张AI图片
6. 支持并行生成多张图片，提高效率
"""

import base64
import io
import json
import re
import time
import requests
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, asdict
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from src.configs.logger import get_logger
from src.configs.constants import OUTPUT_DIR, BASE_DIR
from src.configs.config import (
    # AI Image Generation API
    AI_IMAGE_API_URL,
    AI_IMAGE_API_KEY,
    AI_IMAGE_MODEL,
    # AI Image Generation settings
    AI_IMAGE_MAX_PER_SURVEY,
    AI_IMAGE_MAX_ITERATIONS,
    AI_IMAGE_MIN_QUALITY_SCORE,
    AI_IMAGE_PREFER_SURVEY_STYLE,
    # Multimodal API (for evaluation)
    MULTIMODAL_API_URL,
    MULTIMODAL_API_KEY,
    MULTIMODAL_MODEL,
    # LLM API (for prompt generation)
    REMOTE_URL,
    TOKEN,
    DEFAULT_CHATAGENT_MODEL,
)
from src.modules.utils import load_prompt

from src.modules.multimodal.dynamic_visual_generator import ExistingVisualElement

logger = get_logger("src.modules.multimodal.AIImageGenerator")


@dataclass
class GeneratedImage:
    """生成的图片信息"""
    image_url: str                    # 图片URL
    local_path: Path                  # 本地保存路径
    prompt: str                       # 生成prompt
    description: str                  # 图片描述
    target_section: str               # 目标章节
    quality_score: float              # 质量评分 (1-10)
    iteration: int                    # 迭代次数
    evaluation_feedback: str          # 评估反馈
    is_selected: bool                 # 是否被选中
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["local_path"] = str(self.local_path)
        return d


@dataclass
class ImageGenerationDecision:
    """图片生成决策"""
    should_generate: bool             # 是否应该生成
    target_section: str               # 目标章节
    section_title: str                # 章节标题
    image_type: str                   # 图片类型（pipeline, architecture, concept, etc.）
    description: str                  # 图片描述
    key_elements: List[str]           # 关键元素
    style_requirements: str           # 样式要求
    priority: int                     # 优先级 (1-10)
    reason: str                       # 决策理由
    
    def to_dict(self) -> Dict:
        return asdict(self)


class AIImageGenerator:
    """
    AI图片生成器
    
    使用Gemini 3 Pro Image Preview生成专业学术插图
    """
    
    # 支持的图片类型
    IMAGE_TYPES = [
        "pipeline",           # 流程/管道图
        "architecture",       # 架构图
        "concept",            # 概念图
        "comparison",         # 对比图
        "workflow",           # 工作流程图
        "framework",          # 框架图
        "illustration",       # 说明图
        "diagram",            # 图表
    ]
    
    def __init__(
        self,
        image_api_url: str = None,
        image_api_key: str = None,
        image_model: str = None,
        eval_api_url: str = None,
        eval_api_key: str = None,
        eval_model: str = None,
        llm_api_url: str = None,
        llm_api_key: str = None,
        llm_model: str = None,
        task_id: str = None
    ):
        """
        初始化AI图片生成器
        
        Args:
            image_api_url: 生图API地址
            image_api_key: 生图API密钥
            image_model: 生图模型名称
            eval_api_url: 评估API地址（多模态）
            eval_api_key: 评估API密钥
            eval_model: 评估模型名称
            llm_api_url: LLM API地址（用于生成prompt）
            llm_api_key: LLM API密钥
            llm_model: LLM模型名称
            task_id: 任务ID
        """
        # 生图API配置 (使用传入值或config默认值)
        self.image_api_url = image_api_url or AI_IMAGE_API_URL
        self.image_api_key = image_api_key or AI_IMAGE_API_KEY
        self.image_model = image_model or AI_IMAGE_MODEL
        
        # 评估API配置（多模态）(使用传入值或config默认值)
        self.eval_api_url = eval_api_url or MULTIMODAL_API_URL
        self.eval_api_key = eval_api_key or MULTIMODAL_API_KEY
        self.eval_model = eval_model or MULTIMODAL_MODEL
        
        # LLM API配置（用于生成prompt）(使用传入值或config默认值)
        self.llm_api_url = llm_api_url or REMOTE_URL
        self.llm_api_key = llm_api_key or TOKEN
        self.llm_model = llm_model or DEFAULT_CHATAGENT_MODEL
        
        self.task_id = task_id
        
        # 设置路径
        if task_id:
            self.output_dir = Path(OUTPUT_DIR) / task_id
            self.figs_dir = self.output_dir / "latex" / "figs"
            self.ai_images_dir = self.output_dir / "ai_generated_images"
        else:
            self.output_dir = Path(OUTPUT_DIR) / "temp"
            self.figs_dir = self.output_dir / "figs"
            self.ai_images_dir = self.output_dir / "ai_generated_images"
        
        self.figs_dir.mkdir(parents=True, exist_ok=True)
        self.ai_images_dir.mkdir(parents=True, exist_ok=True)
        
        # Prompt 路径
        self.prompt_dir = Path(BASE_DIR) / "resources" / "LLM" / "prompts" / "multimodal"
        self.decide_prompt_path = self.prompt_dir / "decide_image_generation.md"
        self.architect_prompt_path = self.prompt_dir / "architect_schema.md"
        self.renderer_prompt_path = self.prompt_dir / "renderer_instruction.md"
        self.default_prompt_path = self.prompt_dir / "default_image_prompt.md"
        self.evaluate_prompt_path = self.prompt_dir / "evaluate_image.md"
        self.caption_prompt_path = self.prompt_dir / "generate_caption.md"
        
        # Survey风格模板路径 (新增的学术综述风格)
        self.style_templates_dir = self.prompt_dir / "styles"
        self.style_templates_dir.mkdir(parents=True, exist_ok=True)
        
        # 定义风格模板映射
        self.style_templates = {
            "modular_layout": self.style_templates_dir / "style_modular_layout.md",
            "parallel_flow": self.style_templates_dir / "style_parallel_flow.md",
            "timeline_trajectory": self.style_templates_dir / "style_timeline_trajectory.md",
            "stage_workflow": self.style_templates_dir / "style_stage_workflow.md",
            "mechanism_zoom": self.style_templates_dir / "style_mechanism_zoom.md",
            "visual_taxonomy": self.style_templates_dir / "style_visual_taxonomy.md",
            "3d_layered": self.style_templates_dir / "style_3d_layered.md",
            "roadmap_flow": self.style_templates_dir / "style_roadmap_flow.md",
            "evolution_path": self.style_templates_dir / "style_evolution_path.md",
            "circular_cycle": self.style_templates_dir / "style_circular_cycle.md",
            "radial_mindmap": self.style_templates_dir / "style_radial_mindmap.md",
            "card_comparison": self.style_templates_dir / "style_card_comparison.md",
        }
        
        # 定义内容类型到风格的映射
        # 注意：所有风格都应该是2D扁平化学术风格，避免3D效果
        # "3d_layered" 已被重命名为2D分层架构风格，但保留名称以兼容
        self.type_to_style_mapping = {
            "architecture": ["modular_layout", "mechanism_zoom", "parallel_flow", "3d_layered"],
            "framework": ["modular_layout", "mechanism_zoom", "stage_workflow"],
            "pipeline": ["stage_workflow", "roadmap_flow", "parallel_flow", "circular_cycle"],
            "workflow": ["stage_workflow", "roadmap_flow", "circular_cycle"],
            "taxonomy": ["visual_taxonomy", "card_comparison", "radial_mindmap", "evolution_path"],
            "concept": ["visual_taxonomy", "mechanism_zoom", "radial_mindmap"],
            "timeline": ["timeline_trajectory", "evolution_path", "roadmap_flow"],
            "comparison": ["parallel_flow", "card_comparison", "modular_layout"],
            "overview": ["modular_layout", "roadmap_flow", "radial_mindmap"],
            "diagram": ["modular_layout", "stage_workflow", "mechanism_zoom"],
            "illustration": ["modular_layout", "mechanism_zoom", "stage_workflow"]
        }
        
        # 记录已使用的风格，避免重复
        self.used_styles = set()
        
        # 是否优先使用survey风格（可配置）
        self.prefer_survey_style = AI_IMAGE_PREFER_SURVEY_STYLE
        
        # 配置 (使用config默认值)
        self.max_images_per_survey = AI_IMAGE_MAX_PER_SURVEY      # 每篇综述最多生成5张AI图片
        self.max_iterations = AI_IMAGE_MAX_ITERATIONS              # 每张图片最多迭代3次
        self.min_quality_score = AI_IMAGE_MIN_QUALITY_SCORE        # 最低质量分数
        
        # 已生成的图片计数
        self.generated_count = 0
        
        # 已存在的视觉元素（用于避免重复）
        self.existing_visual_elements: List[ExistingVisualElement] = []
    
    def _compress_image_for_latex(
        self,
        input_path: Path,
        output_path: Path,
        max_width: int = 1200,
        max_height: int = 900,
        quality: int = 85
    ) -> bool:
        """
        压缩图片用于 LaTeX 插入，避免 4K 图片导致 PDF 过大
        
        Args:
            input_path: 输入图片路径（原始高清图片）
            output_path: 输出图片路径（压缩后的图片）
            max_width: 最大宽度（像素），默认1200（适合单栏论文）
            max_height: 最大高度（像素），默认900
            quality: PNG/JPEG质量（1-100），默认85
            
        Returns:
            是否压缩成功
        """
        if not HAS_PIL:
            logger.warning("PIL not installed, copying original image without compression")
            import shutil
            shutil.copy2(input_path, output_path)
            return True
        
        try:
            # 打开原始图片
            img = Image.open(input_path)
            original_size = input_path.stat().st_size
            original_dimensions = img.size
            
            logger.info(f"Original image for LaTeX: {original_dimensions[0]}x{original_dimensions[1]}, {original_size / 1024 / 1024:.2f}MB")
            
            # 计算缩放比例（保持宽高比）
            width, height = img.size
            scale_ratio = 1.0
            
            if width > max_width or height > max_height:
                width_ratio = max_width / width
                height_ratio = max_height / height
                scale_ratio = min(width_ratio, height_ratio)
                
                new_width = int(width * scale_ratio)
                new_height = int(height * scale_ratio)
                
                # 使用 LANCZOS 重采样保持清晰度
                img = img.resize((new_width, new_height), Image.LANCZOS)
                logger.info(f"Resized for LaTeX: {new_width}x{new_height} (scale: {scale_ratio:.2f})")
            
            # 保存压缩后的图片
            # 根据输出格式选择保存方式
            output_ext = output_path.suffix.lower()
            
            if output_ext in ['.jpg', '.jpeg']:
                # JPEG 格式
                if img.mode in ('RGBA', 'LA', 'P'):
                    # 转换为 RGB（JPEG 不支持透明通道）
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    if img.mode == 'RGBA':
                        background.paste(img, mask=img.split()[-1])
                    else:
                        background.paste(img)
                    img = background
                img.save(output_path, format='JPEG', quality=quality, optimize=True)
            else:
                # PNG 格式（保持透明通道）
                img.save(output_path, format='PNG', optimize=True)
            
            compressed_size = output_path.stat().st_size
            compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
            
            logger.info(f"LaTeX image compressed: {original_size / 1024 / 1024:.2f}MB -> {compressed_size / 1024 / 1024:.2f}MB ({compression_ratio:.1f}% reduction)")
            
            return True
            
        except Exception as e:
            logger.error(f"LaTeX image compression failed: {e}")
            # 回退：直接复制原始图片
            import shutil
            shutil.copy2(input_path, output_path)
            return False
    
    def _compress_image_for_evaluation(
        self,
        image_data: bytes,
        max_size: int = 2048,
        quality: int = 85,
        max_file_size_mb: float = 4.0
    ) -> str:
        """
        压缩图片用于评测，保持清晰度
        
        Args:
            image_data: 原始图片字节数据
            max_size: 最大边长（像素），默认2048
            quality: JPEG质量（1-100），默认85保持高清晰度
            max_file_size_mb: 最大文件大小（MB），默认4MB
            
        Returns:
            压缩后的Base64编码字符串
        """
        if not HAS_PIL:
            logger.warning("PIL not installed, returning original image")
            return base64.b64encode(image_data).decode("utf-8")
        
        try:
            # 打开图片
            img = Image.open(io.BytesIO(image_data))
            original_size = len(image_data)
            original_dimensions = img.size
            
            logger.debug(f"Original image: {original_dimensions[0]}x{original_dimensions[1]}, {original_size / 1024 / 1024:.2f}MB")
            
            # 转换为RGB（如果是RGBA或其他模式）
            if img.mode in ('RGBA', 'LA', 'P'):
                # 创建白色背景
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 计算缩放比例（保持宽高比）
            width, height = img.size
            if width > max_size or height > max_size:
                ratio = min(max_size / width, max_size / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                # 使用LANCZOS重采样保持清晰度
                img = img.resize((new_width, new_height), Image.LANCZOS)
                logger.debug(f"Resized to: {new_width}x{new_height}")
            
            # 压缩为JPEG，使用高质量设置
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=quality, optimize=True)
            compressed_data = buffer.getvalue()
            compressed_size = len(compressed_data)
            
            # 如果仍然太大，逐步降低质量
            current_quality = quality
            while compressed_size > max_file_size_mb * 1024 * 1024 and current_quality > 50:
                current_quality -= 10
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=current_quality, optimize=True)
                compressed_data = buffer.getvalue()
                compressed_size = len(compressed_data)
                logger.debug(f"Reduced quality to {current_quality}, size: {compressed_size / 1024 / 1024:.2f}MB")
            
            compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
            logger.info(f"Image compressed: {original_size / 1024 / 1024:.2f}MB -> {compressed_size / 1024 / 1024:.2f}MB ({compression_ratio:.1f}% reduction)")
            
            return base64.b64encode(compressed_data).decode("utf-8")
            
        except Exception as e:
            logger.error(f"Image compression failed: {e}")
            # 回退：返回原始图片的Base64
            return base64.b64encode(image_data).decode("utf-8")
    
    def _get_image_as_base64(self, image_url: str, compress: bool = True) -> Optional[str]:
        """
        获取图片并转换为Base64（可选压缩）
        
        Args:
            image_url: 图片URL或Base64数据URL
            compress: 是否压缩图片
            
        Returns:
            Base64编码的图片数据，或None（失败时）
        """
        try:
            # 处理Base64图片
            if image_url.startswith("data:image"):
                # 提取base64数据
                header, encoded = image_url.split(",", 1)
                image_data = base64.b64decode(encoded)
            else:
                # 下载图片
                response = requests.get(image_url, timeout=60)
                if response.status_code != 200:
                    logger.error(f"Failed to download image: {response.status_code}")
                    return None
                image_data = response.content
            
            # 检查图片大小
            size_mb = len(image_data) / 1024 / 1024
            logger.debug(f"Downloaded image size: {size_mb:.2f}MB")
            
            if compress and size_mb > 1.0:  # 大于1MB时压缩
                return self._compress_image_for_evaluation(image_data)
            else:
                return base64.b64encode(image_data).decode("utf-8")
                
        except Exception as e:
            logger.error(f"Failed to get image as base64: {e}")
            return None
    
    def _call_llm(self, prompt: str, temperature: float = 0.7) -> str:
        """调用LLM生成prompt"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.llm_api_key}"
        }
        
        payload = {
            "model": self.llm_model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": 4000
        }
        
        try:
            response = requests.post(
                self.llm_api_url,
                headers=headers,
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
    
    def _is_jimeng_model(self) -> bool:
        """检查是否是即梦（jimeng）模型"""
        return "jimeng" in self.image_model.lower()
    
    def _call_image_generator(self, prompt: str, max_retries: int = 50, timeout: int = 180) -> Optional[str]:
        """
        调用生图API
        
        Args:
            prompt: 生图prompt
            max_retries: 最大重试次数（默认50次，因为上游API可能饱和）
            timeout: 单次请求超时时间（秒），默认180秒（生图需要较长时间）
            
        Returns:
            图片URL或None
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.image_api_key}"
        }
        
        # 检查是否是即梦模型，使用特殊格式
        if self._is_jimeng_model():
            # 即梦模型使用 OpenAI 聊天格式，content 为数组，必须设置 n=1
            payload = {
                "model": self.image_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ],
                "n": 1,  # 即梦模型必须设置 n=1
            }
            logger.debug(f"Using Jimeng model format with n=1")
        else:
            # 其他模型使用标准格式
            payload = {
                "model": self.image_model,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
        
        for attempt in range(max_retries):
            try:
                if attempt > 0 and attempt % 10 == 0:
                    logger.info(f"Generating image (attempt {attempt + 1}/{max_retries})...")
                
                response = requests.post(
                    self.image_api_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout  # 使用可配置的超时时间，默认90秒
                )
                
                if response.status_code != 200:
                    # 检查是否是API密钥或上游饱和问题
                    error_msg = response.text
                    if "API key" in error_msg or "upstream" in error_msg:
                        # 上游饱和，等待后重试
                        time.sleep(1)
                        continue
                    logger.error(f"Image API error: {response.status_code}")
                    logger.error(f"Response content: {error_msg}")
                    time.sleep(1)
                    continue
                
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                
                # 提取URL
                image_url = self._extract_image_url(content)
                
                if image_url:
                    return image_url
                else:
                    logger.warning(f"No image URL found in response (attempt {attempt + 1}), retrying...")
                    time.sleep(2)  # 稍微增加重试间隔
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Image generation timeout (attempt {attempt + 1}/{max_retries}), retrying...")
                time.sleep(3)  # 超时后稍等一下再重试
            except Exception as e:
                logger.error(f"Image generation error (attempt {attempt + 1}): {e}")
                time.sleep(2)
        
        return None
    
    def _extract_image_url(self, content: str) -> Optional[str]:
        """从响应内容中提取图片URL或Base64数据"""
        # 1. 检查Base64图片
        base64_pattern = r'data:image/[a-zA-Z]+;base64,([^\s\)\]\"\'\>]+)'
        base64_matches = re.findall(base64_pattern, content)
        if base64_matches:
            return f"data:image/png;base64,{base64_matches[0]}"
            
        # 2. 查找https开头的URL
        url_pattern = r'https://[^\s\)\]\"\'\>]+'
        matches = re.findall(url_pattern, content)
        
        for url in matches:
            # 验证是否是图片URL
            parsed = urlparse(url)
            if any(ext in parsed.path.lower() for ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif']):
                return url
            # 有些生图服务返回的URL没有扩展名
            if 'image' in url.lower() or 'img' in url.lower() or 'cdn' in url.lower():
                return url
        
        # 如果没有找到明确的图片URL，返回第一个https URL
        if matches:
            return matches[0]
        
        return None
    
    def _download_image(self, url: str, save_path: Path) -> bool:
        """下载图片到本地（支持URL和Base64）"""
        try:
            # 处理Base64图片
            if url.startswith("data:image"):
                import base64
                # 提取base64数据
                header, encoded = url.split(",", 1)
                data = base64.b64decode(encoded)
                
                with open(save_path, 'wb') as f:
                    f.write(data)
                logger.info(f"Base64 image saved to {save_path}")
                return True
                
            # 处理普通URL
            response = requests.get(url, timeout=60)
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                logger.info(f"Image downloaded to {save_path}")
                return True
            else:
                logger.error(f"Failed to download image: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Download/Save error: {e}")
            return False
    
    def _evaluate_image(self, image_url: str, expected_description: str) -> Tuple[float, str]:
        """
        Evaluate generated image using multimodal model
        
        Args:
            image_url: Image URL
            expected_description: Expected image description
            
        Returns:
            (Quality score, Evaluation feedback)
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.eval_api_key}"
        }
        
        eval_prompt = load_prompt(
            self.evaluate_prompt_path,
            expected_description=expected_description
        )
        
        # 获取并压缩图片用于评测
        image_base64 = self._get_image_as_base64(image_url, compress=True)
        
        if image_base64:
            # 使用压缩后的Base64图片
            image_content = {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
            }
            logger.debug("Using compressed base64 image for evaluation")
        else:
            # 回退：直接使用原始URL
            image_content = {
                "type": "image_url",
                "image_url": {"url": image_url}
            }
            logger.warning("Using original image URL for evaluation (compression failed)")
        
        payload = {
            "model": self.eval_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": eval_prompt},
                        image_content
                    ]
                }
            ],
            "temperature": 0.3,
            "max_tokens": 2000
        }
        
        try:
            response = requests.post(
                self.eval_api_url,
                headers=headers,
                json=payload,
                timeout=120
            )
            
            if response.status_code != 200:
                logger.error(f"Evaluation API error: {response.status_code}")
                logger.error(f"Response content: {response.text[:500]}")
                return 5.0, f"评估API错误: HTTP {response.status_code}"
            
            result = response.json()
            
            # 检查响应格式，支持多种API响应格式
            content = None
            
            # 标准 OpenAI 格式
            if "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    content = choice["message"]["content"]
                elif "text" in choice:
                    content = choice["text"]
            # 某些API直接返回 content 字段
            elif "content" in result:
                content = result["content"]
            # 某些API返回 response 字段
            elif "response" in result:
                content = result["response"]
            # 某些API返回 output 字段
            elif "output" in result:
                content = result["output"]
            # 错误响应
            elif "error" in result:
                error_msg = result["error"]
                if isinstance(error_msg, dict):
                    error_msg = error_msg.get("message", str(error_msg))
                logger.error(f"Evaluation API returned error: {error_msg}")
                return 5.0, f"评估API错误: {error_msg}"
            
            if content is None:
                logger.error(f"Unexpected API response format: {str(result)[:500]}")
                return 5.0, f"评估API响应格式异常"
            
            # 解析评估结果
            return self._parse_evaluation(content)
            
        except requests.exceptions.Timeout:
            logger.error("Evaluation API timeout")
            return 5.0, "评估API超时"
        except requests.exceptions.RequestException as e:
            logger.error(f"Evaluation request error: {e}")
            return 5.0, f"评估请求错误: {e}"
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse evaluation response as JSON: {e}")
            return 5.0, f"评估响应解析错误"
        except Exception as e:
            logger.error(f"Evaluation error: {e}")
            return 5.0, f"评估出错: {e}"
    
    def _parse_evaluation(self, response: str) -> Tuple[float, str]:
        """Parse evaluation response with enhanced metrics"""
        try:
            # Extract JSON
            json_str = response
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                json_str = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                json_str = response[start:end].strip()
            
            data = json.loads(json_str)
            
            # Get overall score or calculate from individual scores
            overall_score = data.get("overall_score", None)
            
            if overall_score is None:
                # Calculate from individual metrics (new evaluation format)
                scores = []
                # New metrics including background_quality (formerly background_transparency) and detail_precision
                for key in ["background_quality", "background_transparency",  # Support both old and new field names
                           "content_accuracy", "visual_design_quality",
                           "academic_appropriateness", "clarity_readability", "text_quality",
                           "detail_precision", "icon_element_quality",
                           "simplicity", "clarity"]:  # Include old format keys for compatibility
                    if key in data:
                        scores.append(data[key])
                
                if scores:
                    overall_score = sum(scores) / len(scores)
                else:
                    overall_score = 5.0
            
            # Build detailed feedback string
            strengths = data.get("strengths", [])
            weaknesses = data.get("weaknesses", [])
            suggestions = data.get("improvement_suggestions", "")
            
            # Include individual scores in feedback for better iteration
            score_details = []
            # Include new metrics in feedback (support both old and new field names)
            for key in ["background_quality", "background_transparency",
                       "content_accuracy", "visual_design_quality",
                       "academic_appropriateness", "clarity_readability", "text_quality",
                       "detail_precision"]:
                if key in data:
                    score_details.append(f"{key}: {data[key]}")
            
            feedback_parts = []
            if score_details:
                feedback_parts.append(f"Scores: {', '.join(score_details)}")
            if strengths:
                feedback_parts.append(f"Strengths: {', '.join(strengths)}")
            if weaknesses:
                feedback_parts.append(f"Weaknesses: {', '.join(weaknesses)}")
            if suggestions:
                feedback_parts.append(f"Suggestions: {suggestions}")
            
            feedback = "; ".join(feedback_parts) if feedback_parts else "No detailed feedback"
            
            return float(overall_score), feedback
            
        except Exception as e:
            logger.error(f"Parse evaluation error: {e}")
            return 5.0, "Failed to parse evaluation result"
    
    def set_existing_visual_elements(self, elements: List[ExistingVisualElement]):
        """
        设置已存在的视觉元素信息，用于避免重复生成
        
        Args:
            elements: 已存在的视觉元素列表
        """
        self.existing_visual_elements = elements
        logger.info(f"Set {len(elements)} existing visual elements for AI image deduplication")
    
    def add_existing_element(self, element: ExistingVisualElement):
        """
        添加已存在的视觉元素
        
        Args:
            element: 视觉元素信息
        """
        self.existing_visual_elements.append(element)
        logger.debug(f"Added existing element: {element.title}")
    
    def _format_existing_elements_for_prompt(self) -> str:
        """格式化已存在的视觉元素信息，用于提示LLM避免重复"""
        if not self.existing_visual_elements:
            return "No existing visual elements."
        
        info_lines = ["The following visual elements already exist. AVOID generating images with similar topics:"]
        for i, elem in enumerate(self.existing_visual_elements, 1):
            topics_str = ", ".join(elem.topics) if elem.topics else "N/A"
            info_lines.append(
                f"{i}. [{elem.element_type.upper()}] \"{elem.title}\"\n"
                f"   - Section: {elem.target_section}\n"
                f"   - Topics: {topics_str}"
            )
        
        return "\n".join(info_lines)
    
    def analyze_section_for_ai_image(
        self,
        section_content: str,
        section_title: str,
        section_no: str,
        survey_topic: str,
        existing_images: int = 0
    ) -> Optional[ImageGenerationDecision]:
        """
        Analyze section content to decide if an AI image should be generated
        
        Args:
            section_content: Section content
            section_title: Section title
            section_no: Section number
            survey_topic: Survey topic
            existing_images: Number of existing AI images
            
        Returns:
            Image generation decision or None
        """
        if existing_images >= self.max_images_per_survey:
            return None
        
        # 获取已存在的视觉元素信息
        existing_elements_info = self._format_existing_elements_for_prompt()
        
        # 构建增强的prompt，包含已存在元素信息
        enhanced_prompt = f"""You are an expert at deciding whether to generate AI images for academic survey papers.

## Survey Topic
{survey_topic}

## IMPORTANT: Existing Visual Elements (AVOID DUPLICATES)
{existing_elements_info}

## Current Section
- Section Number: {section_no}
- Section Title: {section_title}

## Section Content
{section_content}

## Current Status
- Existing AI images: {existing_images}
- Maximum allowed: {self.max_images_per_survey}

## Task
Decide whether this section needs an AI-generated image. Consider:
1. Does the section describe concepts that would benefit from visual illustration?
2. Is the topic DIFFERENT from existing visual elements listed above?
3. Would an image add academic value?

## CRITICAL: Avoid Topic Overlap
- Do NOT suggest images that cover the same topics as existing tables or TikZ figures
- If a taxonomy/classification table already exists, do NOT generate a taxonomy image
- If a pipeline/workflow diagram already exists, do NOT generate a similar pipeline image
- Choose COMPLEMENTARY topics that enhance the survey without redundancy

## Output Format
Output a JSON object:
```json
{{
    "should_generate": true/false,
    "image_type": "pipeline/architecture/taxonomy/concept/comparison/workflow/framework/illustration/diagram",
    "description": "Brief description of what the image should show",
    "key_elements": ["element1", "element2", "element3"],
    "style_requirements": "Style requirements for the image",
    "priority": 1-10,
    "reason": "Why this image should/should not be generated"
}}
```

If should_generate is false, only include should_generate and reason fields.
Output ONLY JSON, no other content.
"""
        
        response = self._call_llm(enhanced_prompt, temperature=0.5)
        
        if not response:
            return None
        
        try:
            # 提取JSON
            json_str = response
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                json_str = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                json_str = response[start:end].strip()
            
            data = json.loads(json_str)
            
            if not data.get("should_generate", False):
                return None
            
            return ImageGenerationDecision(
                should_generate=True,
                target_section=section_no,
                section_title=section_title,
                image_type=data.get("image_type", "diagram"),
                description=data.get("description", ""),
                key_elements=data.get("key_elements", []),
                style_requirements=data.get("style_requirements", ""),
                priority=data.get("priority", 5),
                reason=data.get("reason", "")
            )
            
        except Exception as e:
            logger.error(f"Parse decision error: {e}")
            return None
    
    def _select_visual_style(self, image_type: str) -> str:
        """
        智能选择视觉风格，确保多样性
        
        Args:
            image_type: 图片内容类型 (architecture, pipeline, etc.)
            
        Returns:
            选定的风格ID (e.g., "modular_layout")
        """
        import random
        
        # 获取该类型支持的所有风格
        candidates = self.type_to_style_mapping.get(image_type, ["modular_layout"])
        
        # 过滤掉已使用的风格
        available = [s for s in candidates if s not in self.used_styles]
        
        if available:
            # 如果有未使用的风格，随机选择一个
            selected = random.choice(available)
        else:
            # 如果所有适合的风格都用过了，从所有候选中随机选择一个（允许复用）
            # 优先选择使用次数最少的（这里简化为随机）
            selected = random.choice(candidates)
            logger.info(f"All styles for {image_type} used, reusing {selected}")
        
        # 记录使用
        self.used_styles.add(selected)
        logger.info(f"Selected style '{selected}' for image type '{image_type}'")
        
        return selected

    def generate_image_prompt(
        self,
        decision: ImageGenerationDecision,
        section_content: str,
        survey_topic: str,
        previous_feedback: str = ""
    ) -> str:
        """
        Generate detailed image generation prompt
        
        支持两种模式：
        1. Survey Style Mode (prefer_survey_style=True): 使用智能路由选择多样化风格模板
        2. Architect+Renderer Mode: 使用LLM生成schema再渲染
        
        Args:
            decision: Image generation decision
            section_content: Section content
            survey_topic: Survey topic
            previous_feedback: Feedback from previous iteration (for improvement)
            
        Returns:
            Detailed image generation prompt
        """
        # 模式1: 使用智能样式路由 (Survey Style Mode)
        if self.prefer_survey_style:
            # 选择最佳视觉风格
            style_id = self._select_visual_style(decision.image_type)
            style_template_path = self.style_templates.get(style_id)
            
            if style_template_path and style_template_path.exists():
                logger.info(f"Using style template '{style_id}' for {decision.image_type}")
                
                # 构建改进指令（如果有之前的反馈）
                improvement_note = ""
                if previous_feedback:
                    improvement_note = f"\n\n## Improvement Notes from Previous Iteration\n{previous_feedback}\n\nPlease address the above feedback in this iteration."
                
                base_prompt = load_prompt(
                    style_template_path,
                    section_title=decision.section_title,
                    description=decision.description + improvement_note,
                    key_elements=', '.join(decision.key_elements)
                )
                
                return base_prompt
            else:
                logger.warning(f"Style template {style_id} not found, falling back to default")
        
        # 模式2: Architect + Renderer 流程 (Fallback)
        improvement_instruction = ""
        if previous_feedback:
            improvement_instruction = f"""
## Feedback from Previous Iteration
{previous_feedback}

Please improve the Visual Schema based on the above feedback.
"""
        
        # Step 1: The Architect - Generate Visual Schema
        architect_prompt = load_prompt(
            self.architect_prompt_path,
            survey_topic=survey_topic,
            section_title=decision.section_title,
            description=decision.description,
            key_elements=', '.join(decision.key_elements),
            section_content=section_content[:2000],
            improvement_instruction=improvement_instruction
        )
        
        schema_response = self._call_llm(architect_prompt, temperature=0.7)
        
        if not schema_response:
            # Fallback to default prompt if LLM fails
            return self._generate_default_prompt(decision)
        
        # Extract Schema content
        schema_content = schema_response
        if "---BEGIN PROMPT---" in schema_response:
            start = schema_response.find("---BEGIN PROMPT---")
            end = schema_response.find("---END PROMPT---")
            if end != -1:
                schema_content = schema_response[start:end+16] # Include markers
            else:
                schema_content = schema_response[start:]
        
        # Step 2: The Renderer - Build Final Image Generation Prompt
        renderer_prompt = load_prompt(
            self.renderer_prompt_path,
            schema_content=schema_content
        )
        
        return renderer_prompt
    
    def _generate_default_prompt(self, decision: ImageGenerationDecision) -> str:
        """
        生成默认的生图prompt
        
        根据image_type选择合适的模板：
        - 如果prefer_survey_style为True，使用智能样式路由
        - 否则使用默认模板
        """
        # 检查是否应该使用survey风格模板
        if self.prefer_survey_style:
            style_id = self._select_visual_style(decision.image_type)
            style_template_path = self.style_templates.get(style_id)
            
            if style_template_path and style_template_path.exists():
                logger.info(f"Using style template '{style_id}' for {decision.image_type}")
                return load_prompt(
                    style_template_path,
                    section_title=decision.section_title,
                    description=decision.description,
                    key_elements=', '.join(decision.key_elements)
                )
        
        # 回退到默认模板
        return load_prompt(
            self.default_prompt_path,
            section_title=decision.section_title,
            description=decision.description,
            key_elements=', '.join(decision.key_elements)
        )
    
    def generate_image_with_iteration(
        self,
        decision: ImageGenerationDecision,
        section_content: str,
        survey_topic: str,
        image_index: int = 0
    ) -> Optional[GeneratedImage]:
        """
        生成图片并迭代优化（最多2轮，每轮重新生成prompt）
        
        Args:
            decision: 图片生成决策
            section_content: 章节内容
            survey_topic: 综述主题
            image_index: 图片索引（用于并行生成时区分）
            
        Returns:
            最佳生成图片或None
        """
        best_image = None
        best_score = 0.0
        previous_feedback = ""
        
        # 最多2轮迭代，每轮重新生成prompt
        max_prompt_iterations = 2
        
        for iteration in range(max_prompt_iterations):
            logger.info(f"Image generation iteration {iteration + 1}/{max_prompt_iterations} for section {decision.target_section}")
            
            # 生成prompt（每轮都重新生成，基于之前的反馈）
            image_prompt = self.generate_image_prompt(
                decision,
                section_content,
                survey_topic,
                previous_feedback
            )
            
            # 调用生图API（内部有50次重试）
            image_url = self._call_image_generator(image_prompt)
            
            if not image_url:
                logger.warning(f"Failed to generate image in iteration {iteration + 1}")
                continue
            
            # 评估图片
            score, feedback = self._evaluate_image(image_url, decision.description)
            
            logger.info(f"Image evaluation: score={score}, feedback={feedback[:100]}...")
            
            # 保存图片信息
            local_filename = f"ai_fig_{image_index + 1}_iter{iteration + 1}.png"
            local_path = self.ai_images_dir / local_filename
            
            # 下载图片
            if self._download_image(image_url, local_path):
                current_image = GeneratedImage(
                    image_url=image_url,
                    local_path=local_path,
                    prompt=image_prompt,
                    description=decision.description,
                    target_section=decision.target_section,
                    quality_score=score,
                    iteration=iteration + 1,
                    evaluation_feedback=feedback,
                    is_selected=False
                )
                
                # 更新最佳图片
                if score > best_score:
                    best_score = score
                    best_image = current_image
                
                # 如果质量足够好，提前结束
                if score >= self.min_quality_score:
                    logger.info(f"Image quality meets threshold ({score} >= {self.min_quality_score}), stopping iteration")
                    break
                
                # 更新反馈用于下一次迭代
                previous_feedback = feedback
            else:
                logger.warning(f"Failed to download image in iteration {iteration + 1}")
        
        if best_image:
            best_image.is_selected = True
            
            # 1. 保存原始高清版本到 ai_generated_images 文件夹
            original_filename = f"ai_fig_{image_index + 1}_original.png"
            original_path = self.ai_images_dir / original_filename
            
            try:
                import shutil
                # 复制原始高清版本
                shutil.copy2(best_image.local_path, original_path)
                logger.info(f"Original high-res image saved to {original_path}")
            except Exception as e:
                logger.warning(f"Failed to save original image: {e}")
            
            # 2. 压缩图片并复制到 figs 目录（用于 LaTeX）
            final_filename = f"ai_fig_{image_index + 1}.png"
            final_path = self.figs_dir / final_filename
            
            try:
                # 使用压缩功能，避免 4K 图片导致 PDF 过大
                # 默认压缩到 1200x900 以内，适合单栏论文
                compression_success = self._compress_image_for_latex(
                    input_path=best_image.local_path,
                    output_path=final_path,
                    max_width=1200,
                    max_height=900,
                    quality=85
                )
                
                if compression_success:
                    logger.info(f"Best image (score={best_score}) compressed and saved to {final_path}")
                else:
                    logger.warning(f"Compression failed, original image copied to {final_path}")
                
                # 更新路径指向最终文件（压缩后的版本）
                best_image.local_path = final_path
                
                # 清理临时迭代文件，防止用户困惑或误用
                # 删除该图片索引下的所有迭代版本（但保留 _original 版本）
                for i in range(max_prompt_iterations):
                    iter_file = self.ai_images_dir / f"ai_fig_{image_index + 1}_iter{i + 1}.png"
                    if iter_file.exists():
                        try:
                            iter_file.unlink()
                            logger.debug(f"Removed temporary file: {iter_file}")
                        except Exception as e:
                            logger.warning(f"Failed to remove temporary file {iter_file}: {e}")
                            
            except Exception as e:
                logger.error(f"Failed to process best image: {e}")
                # 回退：直接复制原始图片
                try:
                    import shutil
                    shutil.copy2(best_image.local_path, final_path)
                    best_image.local_path = final_path
                    logger.info(f"Fallback: copied original image to {final_path}")
                except Exception as e2:
                    logger.error(f"Fallback copy also failed: {e2}")
        
        return best_image
    
    def generate_latex_code(self, image: GeneratedImage) -> str:
        """生成LaTeX图片代码
        
        Use [H] from float package to force figure placement at this exact position.
        """
        fig_num = self.generated_count
        label = f"fig:ai_generated_{fig_num}"
        
        # 生成caption
        caption = self._generate_caption(image)
        
        latex_code = f"""
\\begin{{figure}}[H]
    \\centering
    \\includegraphics[width=0.9\\textwidth]{{figs/{image.local_path.name}}}
    \\caption{{{caption}}}
    \\label{{{label}}}
\\end{{figure}}
"""
        return latex_code.strip()
    
    def _generate_caption(self, image: GeneratedImage) -> str:
        """Generate image caption"""
        # Use LLM to generate a concise caption
        prompt = load_prompt(
            self.caption_prompt_path,
            description=image.description
        )
        
        response = self._call_llm(prompt, temperature=0.3)
        
        if response:
            # 清理响应
            caption = response.strip()
            if caption.startswith('"') and caption.endswith('"'):
                caption = caption[1:-1]
            return caption
        
        # 默认caption
        return f"Illustration of {image.description[:50]}..."
    
    def run(
        self,
        mainbody_content: str,
        outlines: Dict,
        survey_topic: str = "",
        existing_tables: List[Dict] = None,
        existing_tikz_elements: List[Dict] = None
    ) -> Tuple[str, List[GeneratedImage]]:
        """
        运行AI图片生成流程（支持并行生成）
        
        Args:
            mainbody_content: 综述主体内容
            outlines: 大纲
            survey_topic: 综述主题
            existing_tables: 已生成的表格信息列表，用于避免重复
            existing_tikz_elements: 已生成的TikZ图信息列表，用于避免重复
            
        Returns:
            (修改后的内容, 生成的图片列表)
        """
        logger.info("Starting AI image generation...")
        
        # 设置已存在的视觉元素（用于避免重复）
        if existing_tables:
            for table_info in existing_tables:
                elem = ExistingVisualElement.from_table_info(table_info)
                self.add_existing_element(elem)
            logger.info(f"Loaded {len(existing_tables)} existing tables for AI image deduplication")
        
        if existing_tikz_elements:
            for tikz_info in existing_tikz_elements:
                elem = ExistingVisualElement(
                    element_type="tikz",
                    title=tikz_info.get("title", ""),
                    description=tikz_info.get("description", ""),
                    target_section=tikz_info.get("section", ""),
                    topics=tikz_info.get("topics", [])
                )
                self.add_existing_element(elem)
            logger.info(f"Loaded {len(existing_tikz_elements)} existing TikZ elements for AI image deduplication")
        
        # 解析章节
        sections = self._parse_sections(mainbody_content)
        
        generated_images = []
        modified_content = mainbody_content
        
        decisions = []
        
        def analyze_section(section_info):
            section_no, section_title, section_content = section_info
            logger.info(f"Analyzing section {section_no}: {section_title}")
            
            # 这里的 existing_images 只是一个估计值，因为是并行执行
            return self.analyze_section_for_ai_image(
                section_content,
                section_title,
                section_no,
                survey_topic,
                0  # 暂时传0，后面再过滤
            )

        # 1. 并行分析所有章节，确定要生成的图片类型和位置
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_section = {
                executor.submit(analyze_section, section): section
                for section in sections
            }
            
            for future in as_completed(future_to_section):
                try:
                    decision = future.result()
                    if decision:
                        # 找到对应的章节内容
                        section_content = next(s[2] for s in sections if s[0] == decision.target_section)
                        decisions.append((decision, section_content))
                except Exception as e:
                    logger.error(f"Error analyzing section: {e}")

        # 按优先级排序决策
        decisions.sort(key=lambda x: x[0].priority, reverse=True)
        
        # 限制总图片数量
        decisions = decisions[:self.max_images_per_survey]
        
        logger.info(f"Will generate {len(decisions)} AI images in parallel")
        
        # 2. 并行生成图片（每个图片独立生成，互不影响）
        def generate_single_image(args):
            idx, (decision, section_content) = args
            logger.info(f"Decided to generate {decision.image_type} image for section {decision.target_section}")
            
            image = self.generate_image_with_iteration(
                decision,
                section_content,
                survey_topic,
                image_index=idx
            )
            
            return idx, decision, image
        
        # 使用线程池并行生成所有图片
        image_results = []
        with ThreadPoolExecutor(max_workers=min(len(decisions), 5)) as executor:
            futures = {
                executor.submit(generate_single_image, (idx, item)): idx
                for idx, item in enumerate(decisions)
            }
            
            for future in as_completed(futures):
                try:
                    idx, decision, image = future.result()
                    if image:
                        image_results.append((idx, decision, image))
                        logger.info(f"Successfully generated image for section {decision.target_section}")
                except Exception as e:
                    logger.error(f"Error generating image: {e}")
        
        # 按原始顺序排序结果
        image_results.sort(key=lambda x: x[0])
        
        # 3. 按顺序插入图片到文档中
        inserted_sections = set()
        for idx, decision, image in image_results:
            if decision.target_section in inserted_sections:
                logger.warning(f"Skipping duplicate image insertion for section {decision.target_section}")
                continue
                
            generated_images.append(image)
            self.generated_count = idx + 1  # 更新计数器
            
            # 生成LaTeX代码并插入
            latex_code = self.generate_latex_code(image)
            modified_content = self._insert_image(
                modified_content,
                decision.target_section,
                latex_code
            )
            inserted_sections.add(decision.target_section)
        
        logger.info(f"Generated {len(generated_images)} AI images")
        
        # 保存生成报告
        self._save_generation_report(generated_images)
        
        return modified_content, generated_images
    
    def _parse_sections(self, content: str) -> List[Tuple[str, str, str]]:
        """解析章节"""
        sections = []
        
        pattern = r'\\(sub)?section\{([^}]+)\}'
        matches = list(re.finditer(pattern, content))
        
        for i, match in enumerate(matches):
            is_subsection = match.group(1) is not None
            title = match.group(2)
            
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
            if len(section_content) > 300:
                sections.append((section_no, title, section_content))
        
        return sections
    
    def _insert_image(
        self,
        content: str,
        section_no: str,
        latex_code: str
    ) -> str:
        """将图片插入到指定章节
        
        Args:
            content: LaTeX内容
            section_no: 目标章节编号（如 "1", "2.1", "3.2" 等）
            latex_code: 要插入的LaTeX代码
            
        Returns:
            修改后的内容
        """
        # 找到目标章节的位置
        insert_pos = self._find_section_position(content, section_no)
        
        if insert_pos == -1:
            logger.warning(f"Section {section_no} not found, trying fallback")
            # 回退：尝试在文档末尾插入
            return content
        
        # 跳过空行，找到第一段结束的位置
        remaining = content[insert_pos:]
        para_end = remaining.find("\n\n")
        if para_end != -1:
            insert_pos += para_end
        
        # 插入内容
        insert_content = f"\n\n{latex_code}\n"
        modified = content[:insert_pos] + insert_content + content[insert_pos:]
        
        logger.info(f"Inserted AI image into section {section_no}")
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
        
        return -1
    
    def _save_generation_report(self, images: List[GeneratedImage]):
        """保存生成报告"""
        report = """# AI Image Generation Report

## Summary
"""
        report += f"- Total images generated: {len(images)}\n"
        report += f"- Maximum allowed: {self.max_images_per_survey}\n"
        report += f"- Maximum iterations per image: {self.max_iterations}\n\n"
        
        report += "## Generated Images\n\n"
        
        for i, img in enumerate(images, 1):
            report += f"""### Image {i}
- **Section**: {img.target_section}
- **Description**: {img.description}
- **Quality Score**: {img.quality_score}/10
- **Iterations**: {img.iteration}
- **Local Path**: {img.local_path}
- **Evaluation**: {img.evaluation_feedback}
- **Selected**: {'Yes' if img.is_selected else 'No'}

**Prompt Used**:
```
{img.prompt[:500]}...
```

---
"""
        
        report_path = self.output_dir / "tmp" / "ai_image_generation_report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        
        logger.info(f"Saved AI image generation report to {report_path}")


# 测试代码
if __name__ == "__main__":
    generator = AIImageGenerator(task_id="test")
    
    print("Testing Style Routing...")
    
    # 测试不同类型的样式分配
    test_types = ["architecture", "pipeline", "taxonomy", "timeline"]
    
    for img_type in test_types:
        print(f"\n--- Testing {img_type} ---")
        decision = ImageGenerationDecision(
            should_generate=True,
            target_section="2.1",
            section_title=f"Test {img_type}",
            image_type=img_type,
            description=f"A test diagram for {img_type}",
            key_elements=["element1", "element2"],
            style_requirements="academic style",
            priority=8,
            reason="Testing"
        )
        
        # 生成多次以观察样式变化（虽然在单次运行中会尽量不重复）
        prompt = generator.generate_image_prompt(
            decision,
            "Content...",
            "Survey Topic"
        )
        
        # 从 prompt 中提取样式名称（如果模板中有标识）或者打印前几行
        print(f"Generated prompt start: {prompt[:100]}...")
        
    print("\nUsed styles:", generator.used_styles)
