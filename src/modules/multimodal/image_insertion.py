"""
Image Insertion - 图片插入决策和执行模块

决定图片是否应该插入到综述中，以及插入的位置。

主要功能:
1. 根据图片分析结果和综述大纲决定插入位置
2. 生成图片标题和描述
3. 将图片插入到综述内容中
4. 生成LaTeX图片代码
"""

import json
import os
import re
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, asdict

import requests

from src.configs.logger import get_logger
from src.configs.constants import OUTPUT_DIR, RESOURCE_DIR
from src.modules.utils import save_result, sanitize_filename
from src.modules.multimodal.image_analyzer import ImageAnalysisResult

logger = get_logger("src.modules.multimodal.ImageInsertion")


@dataclass
class InsertionDecision:
    """图片插入决策"""
    image_path: Path
    should_insert: bool           # 是否应该插入
    target_section: str           # 目标章节编号（如 "3.2"）
    target_section_title: str     # 目标章节标题
    position: str                 # 插入位置: "after_title", "before_content", "after_content"
    generated_caption: str        # 生成的图片标题
    generated_description: str    # 生成的图片描述段落
    citation: str                 # 引用格式
    latex_code: str               # LaTeX代码
    confidence: float             # 决策置信度
    reason: str                   # 决策理由
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["image_path"] = str(self.image_path)
        return d


class ImageInsertion:
    """
    图片插入决策和执行器
    
    根据图片分析结果和综述结构，决定图片的插入位置并执行插入
    """
    
    def __init__(
        self,
        api_url: str = None,
        api_key: str = None,
        model: str = "glm-4.6",
        task_id: str = None
    ):
        """
        初始化图片插入器
        
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
        
        # 设置输出目录
        if task_id:
            self.output_dir = Path(OUTPUT_DIR) / task_id
            self.figs_dir = self.output_dir / "latex" / "figs"
        else:
            self.output_dir = Path(OUTPUT_DIR) / "temp"
            self.figs_dir = self.output_dir / "figs"
        
        self.figs_dir.mkdir(parents=True, exist_ok=True)
        
        # 已插入的图片计数（用于生成唯一标签）
        self.inserted_count = 0
        
        # 每个章节最多插入的图片数
        self.max_images_per_section = 2
        
        # 已插入图片的章节记录
        self.section_image_count = {}
    
    def _call_llm(self, prompt: str, temperature: float = 0.3) -> str:
        """调用LLM"""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": 2000
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code != 200:
                logger.error(f"LLM API error: {response.status_code}")
                return ""
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"LLM call error: {e}")
            return ""
    
    def decide_insertion(
        self,
        image_analysis: ImageAnalysisResult,
        survey_outline: Dict,
        survey_topic: str = ""
    ) -> InsertionDecision:
        """
        决定图片是否应该插入以及插入位置
        
        Args:
            image_analysis: 图片分析结果
            survey_outline: 综述大纲
            survey_topic: 综述主题
            
        Returns:
            InsertionDecision对象
        """
        # 首先检查基本条件
        if not image_analysis.is_suitable:
            return self._create_rejection(
                image_analysis.image_path,
                "Image not suitable based on analysis"
            )
        
        if image_analysis.academic_value < 6:
            return self._create_rejection(
                image_analysis.image_path,
                f"Academic value too low: {image_analysis.academic_value}"
            )
        
        # 构建决策prompt
        prompt = self._build_decision_prompt(
            image_analysis,
            survey_outline,
            survey_topic
        )
        
        # 调用LLM进行决策
        response = self._call_llm(prompt)
        
        if not response:
            return self._create_rejection(
                image_analysis.image_path,
                "Failed to get LLM decision"
            )
        
        # 解析决策结果
        return self._parse_decision(image_analysis.image_path, response, survey_outline)
    
    def _build_decision_prompt(
        self,
        image_analysis: ImageAnalysisResult,
        survey_outline: Dict,
        survey_topic: str
    ) -> str:
        """构建决策prompt"""
        # 格式化大纲
        outline_text = self._format_outline(survey_outline)
        
        prompt = f"""你是一个学术综述写作专家。请决定是否应该将以下图片插入到综述中。

## 综述主题
{survey_topic}

## 综述大纲
{outline_text}

## 图片分析结果
- 图片描述: {image_analysis.description}
- 图片类型: {image_analysis.image_type}
- 关键概念: {', '.join(image_analysis.key_concepts)}
- 相关性评分: {image_analysis.relevance_score}/10
- 质量评分: {image_analysis.quality_score}/10
- 学术价值: {image_analysis.academic_value}/10
- 建议章节类型: {', '.join(image_analysis.suggested_sections)}
- 分析理由: {image_analysis.reason}

## 决策任务

请决定：
1. 这张图片是否应该插入到综述中？
2. 如果是，应该插入到哪个具体章节？（给出章节编号，如 "3.2"）
3. 为这张图片生成一个学术风格的英文标题（Figure X: ...）
4. 生成一段英文描述文字（1-2句话），解释这张图片展示的内容及其与综述的关联

## 决策标准
- 图片必须与综述主题高度相关
- 图片应该能够帮助读者理解关键概念
- 优先选择架构图、流程图和关键实验结果图
- 避免在同一章节插入过多图片
- 图片应该放在最相关的章节

## 输出格式
请以JSON格式输出：
```json
{{
    "should_insert": true,
    "target_section": "3.2",
    "caption": "Figure X: Overview of the proposed architecture",
    "description": "This figure illustrates the overall architecture of the model, showing the key components and their interactions.",
    "confidence": 0.85,
    "reason": "This architecture diagram clearly explains the model structure and is highly relevant to the methodology section."
}}
```

如果不应该插入，请输出：
```json
{{
    "should_insert": false,
    "reason": "具体原因"
}}
```

请只输出JSON，不要有其他内容。
"""
        return prompt
    
    def _format_outline(self, outline: Dict) -> str:
        """格式化大纲为文本"""
        if not outline:
            return "No outline available"
        
        lines = []
        
        # 处理标题
        if "title" in outline:
            lines.append(f"Title: {outline['title']}")
            lines.append("")
        
        # 处理章节
        sections = outline.get("sections", outline.get("outlines", []))
        
        for section in sections:
            if isinstance(section, dict):
                no = section.get("no", section.get("section_no", ""))
                title = section.get("title", section.get("section_title", ""))
                desc = section.get("description", "")
                
                lines.append(f"{no}. {title}")
                if desc:
                    lines.append(f"   Description: {desc[:100]}...")
                
                # 处理子章节
                subsections = section.get("subsections", section.get("sub", []))
                for sub in subsections:
                    if isinstance(sub, dict):
                        sub_no = sub.get("no", sub.get("subsection_no", ""))
                        sub_title = sub.get("title", sub.get("subsection_title", ""))
                        lines.append(f"   {sub_no}. {sub_title}")
            else:
                lines.append(str(section))
        
        return "\n".join(lines)
    
    def _parse_decision(
        self,
        image_path: Path,
        response: str,
        outline: Dict
    ) -> InsertionDecision:
        """解析LLM决策响应"""
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
            
            if not data.get("should_insert", False):
                return self._create_rejection(
                    image_path,
                    data.get("reason", "LLM decided not to insert")
                )
            
            # 获取目标章节信息
            target_section = data.get("target_section", "")
            target_title = self._get_section_title(outline, target_section)
            
            # 检查章节图片数量限制
            if self.section_image_count.get(target_section, 0) >= self.max_images_per_section:
                return self._create_rejection(
                    image_path,
                    f"Section {target_section} already has maximum images"
                )
            
            # 生成LaTeX代码
            self.inserted_count += 1
            fig_label = f"fig:inserted_{self.inserted_count}"
            caption = data.get("caption", f"Figure {self.inserted_count}")
            
            # 复制图片到输出目录
            new_image_path = self._copy_image_to_output(image_path)
            
            latex_code = self._generate_latex_code(
                new_image_path,
                caption,
                fig_label
            )
            
            # 更新章节图片计数
            self.section_image_count[target_section] = \
                self.section_image_count.get(target_section, 0) + 1
            
            return InsertionDecision(
                image_path=image_path,
                should_insert=True,
                target_section=target_section,
                target_section_title=target_title,
                position="after_title",
                generated_caption=caption,
                generated_description=data.get("description", ""),
                citation=f"Figure~\\ref{{{fig_label}}}",
                latex_code=latex_code,
                confidence=data.get("confidence", 0.7),
                reason=data.get("reason", "")
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return self._create_rejection(image_path, f"Parse error: {e}")
        except Exception as e:
            logger.error(f"Decision parse error: {e}")
            return self._create_rejection(image_path, f"Error: {e}")
    
    def _get_section_title(self, outline: Dict, section_no: str) -> str:
        """获取章节标题"""
        sections = outline.get("sections", outline.get("outlines", []))
        
        for section in sections:
            if isinstance(section, dict):
                no = section.get("no", section.get("section_no", ""))
                if no == section_no or str(no) == str(section_no):
                    return section.get("title", section.get("section_title", ""))
                
                # 检查子章节
                subsections = section.get("subsections", section.get("sub", []))
                for sub in subsections:
                    if isinstance(sub, dict):
                        sub_no = sub.get("no", sub.get("subsection_no", ""))
                        if sub_no == section_no or str(sub_no) == str(section_no):
                            return sub.get("title", sub.get("subsection_title", ""))
        
        return ""
    
    def _copy_image_to_output(self, image_path: Path) -> Path:
        """复制图片到输出目录"""
        image_path = Path(image_path)
        
        # 生成新文件名
        new_name = f"fig_{self.inserted_count}{image_path.suffix}"
        new_path = self.figs_dir / new_name
        
        try:
            shutil.copy2(image_path, new_path)
            logger.info(f"Copied image to {new_path}")
            return new_path
        except Exception as e:
            logger.error(f"Failed to copy image: {e}")
            return image_path
    
    def _generate_latex_code(
        self,
        image_path: Path,
        caption: str,
        label: str
    ) -> str:
        """生成LaTeX图片代码
        
        Use [H] from float package to force figure placement at this exact position.
        """
        # 使用相对路径
        rel_path = f"figs/{image_path.name}"
        
        latex = f"""
\\begin{{figure}}[H]
    \\centering
    \\includegraphics[width=0.8\\textwidth]{{{rel_path}}}
    \\caption{{{caption}}}
    \\label{{{label}}}
\\end{{figure}}
"""
        return latex.strip()
    
    def _create_rejection(
        self,
        image_path: Path,
        reason: str
    ) -> InsertionDecision:
        """创建拒绝插入的决策"""
        return InsertionDecision(
            image_path=image_path,
            should_insert=False,
            target_section="",
            target_section_title="",
            position="",
            generated_caption="",
            generated_description="",
            citation="",
            latex_code="",
            confidence=0.0,
            reason=reason
        )
    
    def batch_decide(
        self,
        image_analyses: List[ImageAnalysisResult],
        survey_outline: Dict,
        survey_topic: str = "",
        max_total_images: int = 10
    ) -> List[InsertionDecision]:
        """
        批量决策图片插入
        
        Args:
            image_analyses: 图片分析结果列表
            survey_outline: 综述大纲
            survey_topic: 综述主题
            max_total_images: 最大总图片数
            
        Returns:
            插入决策列表
        """
        decisions = []
        inserted_count = 0
        
        # 按学术价值排序
        sorted_analyses = sorted(
            image_analyses,
            key=lambda x: x.academic_value,
            reverse=True
        )
        
        for analysis in sorted_analyses:
            if inserted_count >= max_total_images:
                decisions.append(self._create_rejection(
                    analysis.image_path,
                    "Maximum total images reached"
                ))
                continue
            
            decision = self.decide_insertion(
                analysis,
                survey_outline,
                survey_topic
            )
            decisions.append(decision)
            
            if decision.should_insert:
                inserted_count += 1
        
        logger.info(f"Decided to insert {inserted_count} images out of {len(image_analyses)}")
        return decisions
    
    def insert_images_to_survey(
        self,
        survey_content: str,
        decisions: List[InsertionDecision]
    ) -> str:
        """
        将图片插入到综述内容中
        
        Args:
            survey_content: 原始综述内容（LaTeX格式）
            decisions: 插入决策列表
            
        Returns:
            插入图片后的综述内容
        """
        # 过滤出需要插入的决策
        to_insert = [d for d in decisions if d.should_insert]
        
        if not to_insert:
            return survey_content
        
        # 按章节分组
        by_section = {}
        for decision in to_insert:
            section = decision.target_section
            if section not in by_section:
                by_section[section] = []
            by_section[section].append(decision)
        
        # 逐章节插入
        modified_content = survey_content
        
        for section_no, section_decisions in by_section.items():
            for decision in section_decisions:
                modified_content = self._insert_single_image(
                    modified_content,
                    decision
                )
        
        return modified_content
    
    def _insert_single_image(
        self,
        content: str,
        decision: InsertionDecision
    ) -> str:
        """插入单张图片"""
        # 找到目标章节的位置
        insert_pos = self._find_section_position(content, decision.target_section)
        
        if insert_pos == -1:
            logger.warning(f"Section {decision.target_section} not found")
            return content
        
        # 跳过可能的空行
        while insert_pos < len(content) and content[insert_pos] in '\n\r':
            insert_pos += 1
        
        # 构建插入内容
        insert_content = f"\n\n{decision.latex_code}\n\n{decision.generated_description}\n"
        
        # 插入内容
        modified = content[:insert_pos] + insert_content + content[insert_pos:]
        
        logger.info(f"Inserted image into section {decision.target_section}")
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
            try:
                section_idx = int(parts[0]) - 1
                if 0 <= section_idx < len(section_matches):
                    return section_matches[section_idx].end()
            except ValueError:
                # 如果不是数字，尝试按标题匹配
                for match in section_matches:
                    if parts[0].lower() in match.group(1).lower():
                        return match.end()
        else:
            # 二级章节（如 "2.1"）
            try:
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
            except ValueError:
                pass
        
        return -1
    
    def _build_section_pattern(self, section_no: str) -> str:
        """构建章节匹配模式（保留用于兼容性）"""
        # 处理不同格式的章节编号
        parts = section_no.split('.')
        
        if len(parts) == 1:
            # 一级章节: \section{...}
            return r'\\section\{[^}]+\}'
        else:
            # 二级章节: \subsection{...}
            return r'\\subsection\{[^}]+\}'
    
    def generate_image_summary(
        self,
        decisions: List[InsertionDecision]
    ) -> str:
        """
        生成图片插入摘要
        
        Args:
            decisions: 插入决策列表
            
        Returns:
            摘要文本
        """
        inserted = [d for d in decisions if d.should_insert]
        rejected = [d for d in decisions if not d.should_insert]
        
        summary = f"""
## Image Insertion Summary

### Inserted Images: {len(inserted)}
"""
        
        for d in inserted:
            summary += f"""
- **{d.generated_caption}**
  - Section: {d.target_section} ({d.target_section_title})
  - Confidence: {d.confidence:.2f}
  - Reason: {d.reason}
"""
        
        summary += f"""
### Rejected Images: {len(rejected)}
"""
        
        for d in rejected[:5]:  # 只显示前5个
            summary += f"""
- {Path(d.image_path).name}: {d.reason}
"""
        
        if len(rejected) > 5:
            summary += f"\n... and {len(rejected) - 5} more\n"
        
        return summary


# 测试代码
if __name__ == "__main__":
    from src.modules.multimodal.image_analyzer import ImageAnalysisResult
    
    inserter = ImageInsertion(task_id="test")
    
    # 创建测试分析结果
    test_analysis = ImageAnalysisResult(
        image_path=Path("test.png"),
        description="Model architecture diagram",
        image_type="architecture",
        key_concepts=["transformer", "attention", "encoder"],
        relevance_score=8.0,
        quality_score=7.0,
        academic_value=8.0,
        suggested_sections=["methodology", "architecture"],
        is_suitable=True,
        reason="High quality architecture diagram",
        raw_response=""
    )
    
    # 测试大纲
    test_outline = {
        "title": "A Survey on Large Language Models",
        "sections": [
            {"no": "1", "title": "Introduction"},
            {"no": "2", "title": "Background"},
            {"no": "3", "title": "Methodology", "subsections": [
                {"no": "3.1", "title": "Model Architecture"},
                {"no": "3.2", "title": "Training Techniques"}
            ]},
            {"no": "4", "title": "Experiments"},
            {"no": "5", "title": "Conclusion"}
        ]
    }
    
    # 测试决策
    decision = inserter.decide_insertion(
        test_analysis,
        test_outline,
        "Large Language Models"
    )
    
    print(f"Should insert: {decision.should_insert}")
    print(f"Target section: {decision.target_section}")
    print(f"Caption: {decision.generated_caption}")
