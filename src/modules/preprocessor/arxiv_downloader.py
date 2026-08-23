"""
arXiv Downloader - 使用arXiv API搜索和下载论文

arXiv是一个开放的预印本服务器，提供免费的论文访问。
API文档: https://info.arxiv.org/help/api/index.html

主要功能:
1. 根据关键词搜索arXiv论文
2. 下载论文PDF
3. 下载论文源文件（LaTeX）
"""

import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import quote, urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

import requests
from tqdm import tqdm

from src.configs.logger import get_logger
from src.configs.constants import CACHE_DIR, DATASET_DIR
from src.modules.utils import save_result, sanitize_filename

logger = get_logger("src.modules.preprocessor.ArxivDownloader")


class ArxivDownloader:
    """
    使用arXiv API搜索和下载论文
    
    arXiv API特点:
    - 免费使用，无需认证
    - 返回Atom XML格式
    - 支持复杂查询语法
    - 有请求频率限制（建议3秒间隔）
    """
    
    BASE_URL = "http://export.arxiv.org/api/query"
    PDF_BASE_URL = "https://arxiv.org/pdf"
    ABS_BASE_URL = "https://arxiv.org/abs"
    SOURCE_BASE_URL = "https://arxiv.org/e-print"
    
    # arXiv命名空间
    ATOM_NS = "{http://www.w3.org/2005/Atom}"
    ARXIV_NS = "{http://arxiv.org/schemas/atom}"
    
    # 请求间隔（秒），遵守API礼貌规则
    REQUEST_INTERVAL = 3.0
    
    # 每页结果数
    MAX_RESULTS_PER_REQUEST = 100
    
    # 默认最大结果数
    DEFAULT_MAX_RESULTS = 200
    
    def __init__(
        self,
        enable_cache: bool = True,
        cache_dir: Path = None
    ):
        """
        初始化arXiv Downloader
        
        Args:
            enable_cache: 是否启用缓存
            cache_dir: 缓存目录
        """
        self.enable_cache = enable_cache
        self.cache_dir = cache_dir or Path(CACHE_DIR) / "arxiv"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置请求头
        self.headers = {
            "User-Agent": "SurveyX/1.0 (Academic Survey Generator)"
        }
        
        # 上次请求时间
        self._last_request_time = 0
        
    def _rate_limit(self):
        """请求速率限制"""
        current_time = time.time()
        elapsed = current_time - self._last_request_time
        if elapsed < self.REQUEST_INTERVAL:
            time.sleep(self.REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()
    
    def _build_query(
        self,
        query: str = None,
        title: str = None,
        author: str = None,
        abstract: str = None,
        category: str = None,
        id_list: List[str] = None
    ) -> str:
        """
        构建arXiv查询字符串
        
        arXiv支持的查询字段:
        - ti: 标题
        - au: 作者
        - abs: 摘要
        - co: 评论
        - jr: 期刊引用
        - cat: 类别
        - all: 所有字段
        
        支持的操作符: AND, OR, ANDNOT
        """
        parts = []
        
        if query:
            # 通用查询，搜索所有字段
            parts.append(f"all:{query}")
            
        if title:
            parts.append(f"ti:{title}")
            
        if author:
            parts.append(f"au:{author}")
            
        if abstract:
            parts.append(f"abs:{abstract}")
            
        if category:
            parts.append(f"cat:{category}")
            
        if parts:
            return " AND ".join(parts)
        
        return ""
    
    def search(
        self,
        query: str = None,
        title: str = None,
        author: str = None,
        abstract: str = None,
        category: str = None,
        id_list: List[str] = None,
        max_results: int = None,
        sort_by: str = "relevance",
        sort_order: str = "descending"
    ) -> List[Dict]:
        """
        搜索arXiv论文
        
        Args:
            query: 通用搜索词（搜索所有字段）
            title: 标题搜索词
            author: 作者搜索词
            abstract: 摘要搜索词
            category: 类别过滤（如 cs.CL, cs.AI）
            id_list: arXiv ID列表（直接获取指定论文）
            max_results: 最大结果数
            sort_by: 排序方式 (relevance, lastUpdatedDate, submittedDate)
            sort_order: 排序顺序 (ascending, descending)
            
        Returns:
            论文列表
        """
        max_results = max_results or self.DEFAULT_MAX_RESULTS
        
        # 构建查询
        search_query = self._build_query(
            query=query,
            title=title,
            author=author,
            abstract=abstract,
            category=category
        )
        
        # 检查缓存
        cache_key = f"search_{sanitize_filename(search_query or 'ids')}_{max_results}"
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if self.enable_cache and cache_file.exists():
            logger.info(f"Loading cached results for query: {search_query or id_list}")
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        
        papers = []
        start = 0
        
        desc = f"Searching arXiv: {(search_query or str(id_list))[:30]}..."
        with tqdm(total=max_results, desc=desc) as pbar:
            while len(papers) < max_results:
                # 构建请求参数
                params = {
                    "start": start,
                    "max_results": min(
                        self.MAX_RESULTS_PER_REQUEST, 
                        max_results - len(papers)
                    ),
                    "sortBy": sort_by,
                    "sortOrder": sort_order
                }
                
                if search_query:
                    params["search_query"] = search_query
                    
                if id_list:
                    params["id_list"] = ",".join(id_list)
                
                # 发送请求
                self._rate_limit()
                
                try:
                    response = requests.get(
                        self.BASE_URL,
                        params=params,
                        headers=self.headers,
                        timeout=30
                    )
                    
                    if response.status_code != 200:
                        logger.error(f"arXiv API error: {response.status_code}")
                        break
                        
                    # 解析XML响应
                    results = self._parse_response(response.text)
                    
                    if not results:
                        break
                        
                    papers.extend(results)
                    pbar.update(len(results))
                    
                    start += len(results)
                    
                    # 如果返回结果少于请求数，说明没有更多结果
                    if len(results) < params["max_results"]:
                        break
                        
                except Exception as e:
                    logger.error(f"arXiv search error: {e}")
                    break
        
        logger.info(f"Found {len(papers)} papers from arXiv")
        
        # 保存缓存
        if self.enable_cache and papers:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(papers, f, indent=2, ensure_ascii=False)
                
        return papers
    
    def _parse_response(self, xml_text: str) -> List[Dict]:
        """解析arXiv API响应"""
        papers = []
        
        try:
            root = ET.fromstring(xml_text)
            
            for entry in root.findall(f"{self.ATOM_NS}entry"):
                paper = self._parse_entry(entry)
                if paper:
                    papers.append(paper)
                    
        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
            
        return papers
    
    def _parse_entry(self, entry: ET.Element) -> Optional[Dict]:
        """解析单个论文条目"""
        try:
            # 提取arXiv ID
            id_elem = entry.find(f"{self.ATOM_NS}id")
            arxiv_url = id_elem.text if id_elem is not None else ""
            arxiv_id = self._extract_arxiv_id(arxiv_url)
            
            if not arxiv_id:
                return None
            
            # 提取标题
            title_elem = entry.find(f"{self.ATOM_NS}title")
            title = title_elem.text.strip() if title_elem is not None else ""
            # 清理标题中的换行和多余空格
            title = " ".join(title.split())
            
            # 提取摘要
            summary_elem = entry.find(f"{self.ATOM_NS}summary")
            abstract = summary_elem.text.strip() if summary_elem is not None else ""
            abstract = " ".join(abstract.split())
            
            # 提取作者
            authors = []
            for author_elem in entry.findall(f"{self.ATOM_NS}author"):
                name_elem = author_elem.find(f"{self.ATOM_NS}name")
                if name_elem is not None:
                    authors.append({"name": name_elem.text})
            
            # 提取发布日期
            published_elem = entry.find(f"{self.ATOM_NS}published")
            published = published_elem.text if published_elem is not None else ""
            
            # 提取更新日期
            updated_elem = entry.find(f"{self.ATOM_NS}updated")
            updated = updated_elem.text if updated_elem is not None else ""
            
            # 提取类别
            categories = []
            for cat_elem in entry.findall(f"{self.ARXIV_NS}primary_category"):
                term = cat_elem.get("term")
                if term:
                    categories.append(term)
            for cat_elem in entry.findall(f"{self.ATOM_NS}category"):
                term = cat_elem.get("term")
                if term and term not in categories:
                    categories.append(term)
            
            # 提取评论（通常包含页数、会议信息等）
            comment_elem = entry.find(f"{self.ARXIV_NS}comment")
            comment = comment_elem.text if comment_elem is not None else ""
            
            # 提取DOI
            doi_elem = entry.find(f"{self.ARXIV_NS}doi")
            doi = doi_elem.text if doi_elem is not None else ""
            
            # 提取期刊引用
            journal_elem = entry.find(f"{self.ARXIV_NS}journal_ref")
            journal_ref = journal_elem.text if journal_elem is not None else ""
            
            # 构建PDF和源文件URL
            pdf_url = f"{self.PDF_BASE_URL}/{arxiv_id}.pdf"
            abs_url = f"{self.ABS_BASE_URL}/{arxiv_id}"
            source_url = f"{self.SOURCE_BASE_URL}/{arxiv_id}"
            
            return {
                "arxiv_id": arxiv_id,
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "published": published,
                "updated": updated,
                "categories": categories,
                "primary_category": categories[0] if categories else "",
                "comment": comment,
                "doi": doi,
                "journal_ref": journal_ref,
                "pdf_url": pdf_url,
                "abs_url": abs_url,
                "source_url": source_url,
                "from": "arxiv"
            }
            
        except Exception as e:
            logger.error(f"Error parsing entry: {e}")
            return None
    
    def _extract_arxiv_id(self, url: str) -> str:
        """从URL中提取arXiv ID"""
        # URL格式: http://arxiv.org/abs/2301.00001v1
        match = re.search(r"arxiv\.org/abs/(.+?)(?:v\d+)?$", url)
        if match:
            return match.group(1)
        return ""
    
    def get_paper_by_id(self, arxiv_id: str) -> Optional[Dict]:
        """根据arXiv ID获取论文详情"""
        # 清理ID格式
        arxiv_id = arxiv_id.replace("arxiv:", "").replace("arXiv:", "")
        
        results = self.search(id_list=[arxiv_id], max_results=1)
        return results[0] if results else None
    
    def download_pdf(
        self,
        arxiv_id: str = None,
        paper: Dict = None,
        save_dir: Path = None,
        timeout: int = 120
    ) -> Optional[Path]:
        """
        下载论文PDF
        
        Args:
            arxiv_id: arXiv ID
            paper: 论文信息字典（包含pdf_url）
            save_dir: 保存目录
            timeout: 下载超时时间
            
        Returns:
            下载成功返回文件路径，否则返回None
        """
        if paper:
            arxiv_id = paper.get("arxiv_id")
            pdf_url = paper.get("pdf_url")
            title = paper.get("title", arxiv_id)
        elif arxiv_id:
            pdf_url = f"{self.PDF_BASE_URL}/{arxiv_id}.pdf"
            title = arxiv_id
        else:
            logger.error("Must provide either arxiv_id or paper dict")
            return None
            
        if not save_dir:
            save_dir = Path(DATASET_DIR) / "pdfs" / "arxiv"
            
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        safe_title = sanitize_filename(title)[:100]
        filename = f"{safe_title}_{arxiv_id.replace('/', '_')}.pdf"
        filepath = save_dir / filename
        
        # 检查是否已存在
        if filepath.exists():
            logger.info(f"PDF already exists: {filepath}")
            return filepath
        
        try:
            logger.info(f"Downloading PDF: {pdf_url}")
            
            self._rate_limit()
            
            response = requests.get(
                pdf_url,
                headers=self.headers,
                timeout=timeout,
                stream=True
            )
            
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                
                # 检查是否是PDF
                if "pdf" in content_type.lower() or response.content[:4] == b"%PDF":
                    with open(filepath, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    logger.info(f"Downloaded: {filepath}")
                    return filepath
                else:
                    logger.warning(f"Not a PDF file: {content_type}")
            else:
                logger.error(f"Download failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Download error: {e}")
            
        return None
    
    def download_source(
        self,
        arxiv_id: str,
        save_dir: Path = None,
        timeout: int = 120
    ) -> Optional[Path]:
        """
        下载论文源文件（通常是LaTeX）
        
        Args:
            arxiv_id: arXiv ID
            save_dir: 保存目录
            timeout: 下载超时时间
            
        Returns:
            下载成功返回文件路径，否则返回None
        """
        source_url = f"{self.SOURCE_BASE_URL}/{arxiv_id}"
        
        if not save_dir:
            save_dir = Path(DATASET_DIR) / "sources" / "arxiv"
            
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # 源文件通常是tar.gz格式
        filename = f"{arxiv_id.replace('/', '_')}.tar.gz"
        filepath = save_dir / filename
        
        # 检查是否已存在
        if filepath.exists():
            logger.info(f"Source already exists: {filepath}")
            return filepath
        
        try:
            logger.info(f"Downloading source: {source_url}")
            
            self._rate_limit()
            
            response = requests.get(
                source_url,
                headers=self.headers,
                timeout=timeout,
                stream=True
            )
            
            if response.status_code == 200:
                with open(filepath, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                logger.info(f"Downloaded: {filepath}")
                return filepath
            else:
                logger.error(f"Download failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Download error: {e}")
            
        return None
    
    def batch_download_pdfs(
        self,
        papers: List[Dict],
        save_dir: Path = None,
        max_workers: int = 2  # arXiv限制较严，使用较少并发
    ) -> List[Path]:
        """
        批量下载PDF
        
        Args:
            papers: 论文列表
            save_dir: 保存目录
            max_workers: 并发下载数
            
        Returns:
            成功下载的文件路径列表
        """
        downloaded = []
        
        if not papers:
            return downloaded
            
        logger.info(f"Downloading {len(papers)} PDFs from arXiv...")
        
        # 由于arXiv的速率限制，使用顺序下载更安全
        for paper in tqdm(papers, desc="Downloading arXiv PDFs"):
            result = self.download_pdf(paper=paper, save_dir=save_dir)
            if result:
                downloaded.append(result)
            # 额外等待以避免被封
            time.sleep(1)
                    
        logger.info(f"Successfully downloaded {len(downloaded)} PDFs")
        return downloaded
    
    def search_by_keywords(
        self,
        keywords: List[str],
        max_results_per_keyword: int = 50,
        categories: List[str] = None
    ) -> List[Dict]:
        """
        根据多个关键词搜索论文
        
        Args:
            keywords: 关键词列表
            max_results_per_keyword: 每个关键词的最大结果数
            categories: 限制的类别列表
            
        Returns:
            去重后的论文列表
        """
        all_papers = {}
        
        for keyword in keywords:
            query = keyword
            if categories:
                cat_filter = " OR ".join([f"cat:{cat}" for cat in categories])
                query = f"({keyword}) AND ({cat_filter})"
                
            papers = self.search(
                query=query,
                max_results=max_results_per_keyword
            )
            
            for paper in papers:
                arxiv_id = paper.get("arxiv_id")
                if arxiv_id and arxiv_id not in all_papers:
                    all_papers[arxiv_id] = paper
        
        logger.info(f"Found {len(all_papers)} unique papers for {len(keywords)} keywords")
        return list(all_papers.values())


# 测试代码
if __name__ == "__main__":
    downloader = ArxivDownloader()
    
    # 测试搜索
    results = downloader.search(
        query="large language models",
        category="cs.CL",
        max_results=5
    )
    
    print(f"Found {len(results)} results")
    for r in results:
        print(f"- [{r['arxiv_id']}] {r['title'][:60]}...")
        print(f"  Categories: {r['categories']}")
        print()