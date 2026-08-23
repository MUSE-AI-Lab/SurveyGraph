import os
import re
import httpx
import fitz  # PyMuPDF
from loguru import logger
import asyncio

class PDFProcessor:
    def __init__(self, download_dir: str = "data/pdfs"):
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)
        
    async def download_pdf(self, url: str, paper_id: str) -> str:
        """下载 PDF 并返回本地路径"""
        if not url:
            return None
            
        # 清理 ID 以作为文件名
        safe_id = paper_id.replace(":", "_").replace("/", "_")
        file_path = os.path.join(self.download_dir, f"{safe_id}.pdf")
        
        if os.path.exists(file_path):
            return file_path
            
        try:
            # arXiv PDF 链接通常需要将 /abs/ 替换为 /pdf/
            if "arxiv.org/abs/" in url:
                url = url.replace("/abs/", "/pdf/")
            if not url.endswith(".pdf"):
                url += ".pdf"
                
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                with open(file_path, "wb") as f:
                    f.write(response.content)
                    
            logger.info(f"Downloaded PDF for {paper_id}")
            return file_path
        except Exception as e:
            logger.error(f"Failed to download PDF for {paper_id}: {e}")
            return None

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """从 PDF 提取全文"""
        if not pdf_path or not os.path.exists(pdf_path):
            return ""
            
        try:
            doc = fitz.open(pdf_path)
            text = ""
            for page in doc:
                text += page.get_text()
            return text
        except Exception as e:
            logger.error(f"Failed to extract text from {pdf_path}: {e}")
            return ""
            
    def extract_sections(self, text: str) -> dict:
        """
        基于规则的章节提取 (Heuristic)
        将全文分割为 Introduction, Method, Experiment, Conclusion 等
        """
        sections = {
            "title": "",
            "abstract": "",
            "introduction": "",
            "related_work": "",
            "method": "",
            "experiment": "",
            "conclusion": "",
            "references": "",
            "full_text": text
        }
        
        if not text:
            return sections

        # 1. 预处理：统一换行符，移除多余空白
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # 2. 定义章节标题的正则模式 (忽略大小写)
        # 匹配如 "1. Introduction", "1 Introduction", "Introduction", "I. Introduction"
        patterns = {
            "abstract": re.compile(r'^(?:abstract|summary)$', re.IGNORECASE),
            "introduction": re.compile(r'^(?:1\.?|i\.?)?\s*introduction$', re.IGNORECASE),
            "related_work": re.compile(r'^(?:2\.?|ii\.?)?\s*(?:related works?|background|literature review)$', re.IGNORECASE),
            "method": re.compile(r'^(?:3\.?|iii\.?)?\s*(?:methods?|methodology|approach|proposed|model architecture)$', re.IGNORECASE),
            "experiment": re.compile(r'^(?:4\.?|iv\.?)?\s*(?:experiments?|evaluations?|results?|performance)$', re.IGNORECASE),
            "conclusion": re.compile(r'^(?:5\.?|6\.?|v\.?|vi\.?)?\s*(?:conclusions?|discussions?|summary)$', re.IGNORECASE),
            "references": re.compile(r'^(?:references|bibliography)$', re.IGNORECASE)
        }
        
        current_section = "title" # 默认第一部分是标题/元数据
        buffer = []
        
        # 简单的状态机
        for line in lines:
            # 检查是否是章节标题
            is_header = False
            
            # 简单的长度过滤，标题通常较短
            if len(line) < 50:
                for section_name, pattern in patterns.items():
                    if pattern.match(line):
                        # 保存当前章节内容
                        if buffer:
                            sections[current_section] = "\n".join(buffer)
                            buffer = []
                        
                        current_section = section_name
                        is_header = True
                        break
            
            if not is_header:
                buffer.append(line)
        
        # 保存最后一个章节
        if buffer:
            sections[current_section] = "\n".join(buffer)
            
        # 后处理：如果某些章节为空，尝试智能回退
        # 例如，如果没有明确的 Method 章节，可能包含在 Introduction 或自定义标题中
        # 这里保持简单，后续可结合 LLM 修正
        
        return sections