"""
MinerU Parser - PDF文档解析器

使用MinerU库解析PDF文档，提取文本、图片和表格。
MinerU文档: https://github.com/opendatalab/MinerU

主要功能:
1. 解析PDF为Markdown格式
2. 提取文档中的图片
3. 提取文档中的表格
4. 保留图片与文本的位置关系
"""

import os
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
import re

from src.configs.logger import get_logger
from src.configs.constants import OUTPUT_DIR, CACHE_DIR
from src.modules.utils import save_result, sanitize_filename

logger = get_logger("src.modules.multimodal.MinerUParser")


@dataclass
class ExtractedImage:
    """提取的图片信息"""
    path: Path                    # 图片本地路径
    page: int                     # 所在页码
    index: int                    # 在页面中的索引
    bbox: Tuple[float, ...]       # 边界框 (x0, y0, x1, y1)
    caption: str                  # 原始caption（如果有）
    context_before: str           # 图片前的文本上下文
    context_after: str            # 图片后的文本上下文
    image_type: str               # 图片类型推测
    width: int                    # 图片宽度
    height: int                   # 图片高度
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["path"] = str(self.path)
        return d


@dataclass
class ExtractedTable:
    """提取的表格信息"""
    page: int
    index: int
    html: str                     # 表格HTML
    markdown: str                 # 表格Markdown
    caption: str
    context_before: str
    context_after: str
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ParseResult:
    """解析结果"""
    markdown: str                 # 完整markdown文本
    images: List[ExtractedImage]  # 提取的图片列表
    tables: List[ExtractedTable]  # 提取的表格列表
    metadata: Dict[str, Any]      # 文档元数据
    source_pdf: Path              # 源PDF路径
    output_dir: Path              # 输出目录
    
    def to_dict(self) -> Dict:
        return {
            "markdown": self.markdown,
            "images": [img.to_dict() for img in self.images],
            "tables": [tbl.to_dict() for tbl in self.tables],
            "metadata": self.metadata,
            "source_pdf": str(self.source_pdf),
            "output_dir": str(self.output_dir)
        }


class MinerUParser:
    """
    MinerU PDF解析器
    
    封装MinerU进行PDF解析，支持:
    - 文本提取（保留格式）
    - 图片提取（保留位置信息）
    - 表格提取（转换为HTML/Markdown）
    - 公式识别
    """
    
    # MinerU支持的后端
    BACKENDS = ["pipeline", "vlm"]
    
    def __init__(
        self,
        backend: str = "pipeline",
        device: str = "auto",
        output_base_dir: Path = None
    ):
        """
        初始化MinerU解析器
        
        Args:
            backend: 解析后端 ("pipeline" 或 "vlm")
            device: 设备 ("auto", "cpu", "cuda", "mps")
            output_base_dir: 输出基础目录
        """
        self.backend = backend
        self.device = device
        self.output_base_dir = output_base_dir or Path(OUTPUT_DIR) / "mineru_output"
        self.output_base_dir.mkdir(parents=True, exist_ok=True)
        
        # 检查MinerU是否安装
        self._check_mineru_installed()
        
    def _check_mineru_installed(self):
        """检查MinerU是否已安装"""
        try:
            # 尝试导入 MinerU 的核心模块
            from mineru.cli.common import read_fn
            import mineru
            logger.info(f"MinerU version: {getattr(mineru, '__version__', 'No version')}")
            self._mineru_available = True
        except ImportError:
            logger.warning(
                "MinerU not installed or incomplete. Please install with: "
                "pip install mineru[core]"
            )
            self._mineru_available = False
    
    def parse_pdf(
        self,
        pdf_path: Path,
        output_dir: Path = None,
        extract_images: bool = True,
        extract_tables: bool = True,
        ocr_lang: str = "auto"
    ) -> ParseResult:
        """
        解析PDF文档
        
        Args:
            pdf_path: PDF文件路径
            output_dir: 输出目录（默认自动生成）
            extract_images: 是否提取图片
            extract_tables: 是否提取表格
            ocr_lang: OCR语言
            
        Returns:
            ParseResult对象，包含解析结果
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        # 设置输出目录
        if output_dir is None:
            safe_name = sanitize_filename(pdf_path.stem)[:50].strip()
            # 确保目录名不为空
            if not safe_name:
                safe_name = "unnamed_pdf"
            output_dir = self.output_base_dir / safe_name
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Parsing PDF: {pdf_path}")
        logger.info(f"Output directory: {output_dir}")
        
        # 调用MinerU进行解析
        try:
            result = self._run_mineru(
                pdf_path=pdf_path,
                output_dir=output_dir,
                ocr_lang=ocr_lang
            )
        except Exception as e:
            logger.error(f"MinerU parsing failed: {e}")
            # 返回空结果
            return ParseResult(
                markdown="",
                images=[],
                tables=[],
                metadata={"error": str(e)},
                source_pdf=pdf_path,
                output_dir=output_dir
            )
        
        # 读取解析结果
        markdown = self._read_markdown(output_dir)
        
        # 提取图片信息
        images = []
        if extract_images:
            images = self._extract_images(output_dir, markdown)
        
        # 提取表格信息
        tables = []
        if extract_tables:
            tables = self._extract_tables(output_dir, markdown)
        
        # 读取元数据
        metadata = self._read_metadata(output_dir)
        metadata["source_pdf"] = str(pdf_path)
        metadata["backend"] = self.backend
        
        return ParseResult(
            markdown=markdown,
            images=images,
            tables=tables,
            metadata=metadata,
            source_pdf=pdf_path,
            output_dir=output_dir
        )
    
    def _run_mineru(
        self,
        pdf_path: Path,
        output_dir: Path,
        ocr_lang: str = "auto"
    ) -> Dict:
        """运行MinerU命令行工具"""
        try:
            # 尝试使用Python API
            return self._run_mineru_api(pdf_path, output_dir, ocr_lang)
        except Exception as e:
            logger.warning(f"MinerU API failed, trying CLI: {e}")
            # 回退到命令行
            return self._run_mineru_cli(pdf_path, output_dir, ocr_lang)
    
    def _run_mineru_api(
        self,
        pdf_path: Path,
        output_dir: Path,
        ocr_lang: str = "auto"
    ) -> Dict:
        """使用MinerU Python API"""
        try:
            from mineru.cli.common import do_parse, read_fn
            
            logger.info("MinerU API: importing successful, starting parse...")
            
            # 读取 PDF 字节
            pdf_bytes = read_fn(str(pdf_path))
            pdf_file_name = pdf_path.stem
            
            logger.info(f"MinerU API: PDF loaded, size={len(pdf_bytes)} bytes, name={pdf_file_name}")
            
            # 设置语言参数
            lang = "ch" if ocr_lang == "auto" else ocr_lang
            
            # 调用 do_parse 函数
            do_parse(
                output_dir=str(output_dir),
                pdf_file_names=[pdf_file_name],
                pdf_bytes_list=[pdf_bytes],
                p_lang_list=[lang],
                backend=self.backend,
                parse_method="auto",
                formula_enable=True,
                table_enable=True,
                f_draw_layout_bbox=False,  # 不需要绘制布局框
                f_draw_span_bbox=False,    # 不需要绘制span框
                f_dump_md=True,            # 输出markdown
                f_dump_middle_json=True,   # 输出中间json
                f_dump_model_output=False, # 不需要模型输出
                f_dump_orig_pdf=False,     # 不需要原始pdf
                f_dump_content_list=True,  # 输出内容列表
            )
            
            logger.info("MinerU API: parse completed successfully")
            return {"status": "success", "method": "api"}
            
        except ImportError as e:
            logger.error(f"MinerU API ImportError: {e}")
            raise ImportError(f"MinerU not installed: {e}")
        except Exception as e:
            logger.error(f"MinerU API Exception: {type(e).__name__}: {e}")
            raise RuntimeError(f"MinerU API error: {e}")
    
    def _run_mineru_cli(
        self,
        pdf_path: Path,
        output_dir: Path,
        ocr_lang: str = "auto"
    ) -> Dict:
        """使用MinerU命令行工具"""
        cmd = [
            "mineru",
            "-p", str(pdf_path),
            "-o", str(output_dir),
            "--backend", self.backend
        ]
        
        if ocr_lang != "auto":
            cmd.extend(["--lang", ocr_lang])
        
        # 打印带引号的命令，方便用户复制和检查
        display_cmd = []
        for part in cmd:
            if " " in part:
                display_cmd.append(f'"{part}"')
            else:
                display_cmd.append(part)
        logger.info(f"Running: {' '.join(display_cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10分钟超时
            )
            
            if result.returncode != 0:
                logger.error(f"MinerU CLI error: {result.stderr}")
                raise RuntimeError(f"MinerU CLI failed: {result.stderr}")
            
            return {"status": "success", "output": result.stdout}
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("MinerU CLI timeout")
        except FileNotFoundError:
            raise RuntimeError("MinerU CLI not found. Please install MinerU.")
    
    def _read_markdown(self, output_dir: Path) -> str:
        """读取生成的Markdown文件"""
        # MinerU 会在 output_dir 下创建子目录结构: {pdf_name}/{parse_method}/
        # 所以需要递归搜索所有子目录
        
        # 递归查找所有 .md 文件
        md_files = list(output_dir.glob("**/*.md"))
        
        if md_files:
            # 优先选择最大的 .md 文件（通常是主要内容）
            md_files.sort(key=lambda x: x.stat().st_size, reverse=True)
            md_path = md_files[0]
            logger.info(f"Found markdown: {md_path}")
            return md_path.read_text(encoding="utf-8")
        
        logger.warning(f"No markdown file found in {output_dir}")
        return ""
    
    def _extract_images(
        self,
        output_dir: Path,
        markdown: str
    ) -> List[ExtractedImage]:
        """提取图片信息"""
        images = []
        
        # MinerU 会在 output_dir 下创建子目录结构，需要递归搜索
        # 查找所有图片文件
        image_extensions = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]
        image_files = []
        
        for ext in image_extensions:
            image_files.extend(output_dir.glob(f"**/*{ext}"))
            image_files.extend(output_dir.glob(f"**/*{ext.upper()}"))
        
        # 确定图片目录（用于日志）
        if image_files:
            image_dir = image_files[0].parent
        else:
            image_dir = output_dir
        
        logger.info(f"Found {len(image_files)} images in {image_dir}")
        
        # 解析Markdown中的图片引用，获取上下文
        image_contexts = self._parse_image_contexts(markdown)
        
        for idx, img_path in enumerate(sorted(image_files)):
            # 尝试从文件名解析页码
            page = self._extract_page_from_filename(img_path.name)
            
            # 获取图片尺寸
            width, height = self._get_image_size(img_path)
            
            # 查找对应的上下文
            context = image_contexts.get(img_path.name, {})
            
            # 推测图片类型
            image_type = self._guess_image_type(img_path.name, context)
            
            image = ExtractedImage(
                path=img_path,
                page=page,
                index=idx,
                bbox=(0, 0, width, height),  # 简化的bbox
                caption=context.get("caption", ""),
                context_before=context.get("before", ""),
                context_after=context.get("after", ""),
                image_type=image_type,
                width=width,
                height=height
            )
            images.append(image)
        
        return images
    
    def _parse_image_contexts(self, markdown: str) -> Dict[str, Dict]:
        """从Markdown中解析图片上下文"""
        contexts = {}
        
        # 匹配Markdown图片语法: ![alt](path)
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        
        lines = markdown.split('\n')
        
        for i, line in enumerate(lines):
            matches = re.finditer(pattern, line)
            for match in matches:
                alt_text = match.group(1)
                img_path = match.group(2)
                img_name = Path(img_path).name
                
                # 获取前后上下文
                context_before = ""
                context_after = ""
                
                # 向前查找非空行
                for j in range(i - 1, max(0, i - 5), -1):
                    if lines[j].strip() and not lines[j].strip().startswith('!'):
                        context_before = lines[j].strip()
                        break
                
                # 向后查找非空行
                for j in range(i + 1, min(len(lines), i + 5)):
                    if lines[j].strip() and not lines[j].strip().startswith('!'):
                        context_after = lines[j].strip()
                        break
                
                contexts[img_name] = {
                    "caption": alt_text,
                    "before": context_before,
                    "after": context_after
                }
        
        return contexts
    
    def _extract_page_from_filename(self, filename: str) -> int:
        """从文件名提取页码"""
        # 常见模式: page_1.png, p1.png, 1.png, img_page1.png
        patterns = [
            r'page[_-]?(\d+)',
            r'p(\d+)',
            r'^(\d+)\.',
            r'_(\d+)\.'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        return 0
    
    def _get_image_size(self, img_path: Path) -> Tuple[int, int]:
        """获取图片尺寸"""
        try:
            from PIL import Image
            with Image.open(img_path) as img:
                return img.size
        except Exception:
            return (0, 0)
    
    def _guess_image_type(self, filename: str, context: Dict) -> str:
        """推测图片类型"""
        filename_lower = filename.lower()
        context_text = (
            context.get("caption", "") + " " +
            context.get("before", "") + " " +
            context.get("after", "")
        ).lower()
        
        # 基于文件名和上下文推测
        type_keywords = {
            "architecture": ["architecture", "framework", "model", "structure", "system"],
            "flowchart": ["flow", "process", "pipeline", "workflow", "step"],
            "experiment": ["result", "experiment", "performance", "accuracy", "loss", "curve", "plot"],
            "comparison": ["comparison", "compare", "vs", "versus", "benchmark"],
            "illustration": ["illustration", "example", "demo", "sample", "case"],
            "table": ["table", "tab"],
            "equation": ["equation", "formula", "eq"]
        }
        
        for img_type, keywords in type_keywords.items():
            for keyword in keywords:
                if keyword in filename_lower or keyword in context_text:
                    return img_type
        
        return "figure"
    
    def _extract_tables(
        self,
        output_dir: Path,
        markdown: str
    ) -> List[ExtractedTable]:
        """提取表格信息"""
        tables = []
        
        # 从Markdown中提取表格
        # Markdown表格格式:
        # | Header1 | Header2 |
        # |---------|---------|
        # | Cell1   | Cell2   |
        
        lines = markdown.split('\n')
        table_start = None
        table_lines = []
        
        for i, line in enumerate(lines):
            # 检测表格行
            if '|' in line and line.strip().startswith('|'):
                if table_start is None:
                    table_start = i
                table_lines.append(line)
            else:
                if table_lines:
                    # 表格结束
                    table_md = '\n'.join(table_lines)
                    
                    # 获取上下文
                    context_before = ""
                    context_after = ""
                    
                    if table_start > 0:
                        context_before = lines[table_start - 1].strip()
                    if i < len(lines):
                        context_after = line.strip()
                    
                    table = ExtractedTable(
                        page=0,
                        index=len(tables),
                        html=self._markdown_table_to_html(table_md),
                        markdown=table_md,
                        caption=context_before if "table" in context_before.lower() else "",
                        context_before=context_before,
                        context_after=context_after
                    )
                    tables.append(table)
                    
                    table_start = None
                    table_lines = []
        
        # 处理最后一个表格
        if table_lines:
            table_md = '\n'.join(table_lines)
            table = ExtractedTable(
                page=0,
                index=len(tables),
                html=self._markdown_table_to_html(table_md),
                markdown=table_md,
                caption="",
                context_before="",
                context_after=""
            )
            tables.append(table)
        
        logger.info(f"Extracted {len(tables)} tables")
        return tables
    
    def _markdown_table_to_html(self, md_table: str) -> str:
        """将Markdown表格转换为HTML"""
        lines = md_table.strip().split('\n')
        if len(lines) < 2:
            return ""
        
        html_parts = ["<table>"]
        
        for i, line in enumerate(lines):
            cells = [c.strip() for c in line.split('|')[1:-1]]
            
            if i == 0:
                # 表头
                html_parts.append("<thead><tr>")
                for cell in cells:
                    html_parts.append(f"<th>{cell}</th>")
                html_parts.append("</tr></thead>")
            elif i == 1:
                # 分隔行，跳过
                html_parts.append("<tbody>")
            else:
                # 数据行
                html_parts.append("<tr>")
                for cell in cells:
                    html_parts.append(f"<td>{cell}</td>")
                html_parts.append("</tr>")
        
        html_parts.append("</tbody></table>")
        return '\n'.join(html_parts)
    
    def _read_metadata(self, output_dir: Path) -> Dict:
        """读取解析元数据"""
        metadata = {}
        
        # 查找元数据文件
        metadata_files = [
            "metadata.json",
            "info.json",
            "middle.json",
            "content_list.json"
        ]
        
        for name in metadata_files:
            meta_path = output_dir / name
            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                    logger.info(f"Loaded metadata from {meta_path}")
                    break
                except Exception as e:
                    logger.warning(f"Failed to load {meta_path}: {e}")
        
        return metadata
    
    def batch_parse(
        self,
        pdf_paths: List[Path],
        output_base_dir: Path = None,
        max_workers: int = 2
    ) -> List[ParseResult]:
        """
        批量解析PDF
        
        Args:
            pdf_paths: PDF文件路径列表
            output_base_dir: 输出基础目录
            max_workers: 并发数（MinerU较重，建议不要太高）
            
        Returns:
            解析结果列表
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from tqdm import tqdm
        
        if output_base_dir:
            self.output_base_dir = Path(output_base_dir)
        
        results = []
        
        # 由于MinerU资源消耗较大，使用顺序处理更稳定
        for pdf_path in tqdm(pdf_paths, desc="Parsing PDFs"):
            try:
                result = self.parse_pdf(pdf_path)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to parse {pdf_path}: {e}")
                # 添加空结果
                results.append(ParseResult(
                    markdown="",
                    images=[],
                    tables=[],
                    metadata={"error": str(e)},
                    source_pdf=pdf_path,
                    output_dir=self.output_base_dir / sanitize_filename(pdf_path.stem)
                ))
        
        return results
    
    def save_result(self, result: ParseResult, output_path: Path = None):
        """保存解析结果"""
        if output_path is None:
            output_path = result.output_dir / "parse_result.json"
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved parse result to {output_path}")


# 测试代码
if __name__ == "__main__":
    parser = MinerUParser(backend="pipeline")
    
    # 测试解析
    test_pdf = Path("test.pdf")
    if test_pdf.exists():
        result = parser.parse_pdf(test_pdf)
        print(f"Markdown length: {len(result.markdown)}")
        print(f"Images: {len(result.images)}")
        print(f"Tables: {len(result.tables)}")
    else:
        print("No test PDF found")