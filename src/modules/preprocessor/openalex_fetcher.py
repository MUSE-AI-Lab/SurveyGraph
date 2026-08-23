"""
OpenAlex Fetcher - 使用OpenAlex API搜索学术文献

OpenAlex是一个开放的学术文献数据库，提供免费API访问。
API文档: https://docs.openalex.org/

主要功能:
1. 根据关键词搜索学术论文
2. 获取论文元数据（标题、摘要、作者、引用等）
3. 获取论文PDF下载链接
4. 获取相关论文推荐
"""

import json
import time
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm

from src.configs.logger import get_logger
from src.configs.constants import CACHE_DIR, DATASET_DIR
from src.modules.utils import save_result, sanitize_filename

logger = get_logger("src.modules.preprocessor.OpenAlexFetcher")


class OpenAlexFetcher:
    """
    使用OpenAlex API搜索和获取学术文献
    
    OpenAlex提供了丰富的学术文献数据，包括:
    - Works: 学术论文
    - Authors: 作者信息
    - Sources: 期刊/会议信息
    - Institutions: 机构信息
    - Concepts: 学科概念
    """
    
    BASE_URL = "https://api.openalex.org"
    
    # 请求间隔（秒），遵守API礼貌规则
    REQUEST_INTERVAL = 0.1
    
    # 每页结果数
    PER_PAGE = 50
    
    # 最大结果数
    MAX_RESULTS = 200
    
    def __init__(
        self, 
        email: str = None,
        enable_cache: bool = True,
        cache_dir: Path = None
    ):
        """
        初始化OpenAlex Fetcher
        
        Args:
            email: 用于polite pool的邮箱地址，可获得更高的请求限制
            enable_cache: 是否启用缓存
            cache_dir: 缓存目录
        """
        self.email = email
        self.enable_cache = enable_cache
        self.cache_dir = cache_dir or Path(CACHE_DIR) / "openalex"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置请求头
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "SurveyX/1.0 (Academic Survey Generator)"
        }
        
        # 上次请求时间
        self._last_request_time = 0
        
    def _build_url(self, endpoint: str, params: Dict[str, Any] = None) -> str:
        """构建API URL"""
        url = f"{self.BASE_URL}/{endpoint}"
        
        if params:
            query_parts = []
            for key, value in params.items():
                if value is not None:
                    if isinstance(value, list):
                        value = ",".join(str(v) for v in value)
                    query_parts.append(f"{key}={quote(str(value))}")
            if query_parts:
                url += "?" + "&".join(query_parts)
        
        # 添加邮箱用于polite pool
        if self.email:
            separator = "&" if "?" in url else "?"
            url += f"{separator}mailto={self.email}"
            
        return url
    
    def _rate_limit(self):
        """请求速率限制"""
        current_time = time.time()
        elapsed = current_time - self._last_request_time
        if elapsed < self.REQUEST_INTERVAL:
            time.sleep(self.REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()
    
    def _make_request(self, url: str, retries: int = 3) -> Optional[Dict]:
        """发送API请求"""
        self._rate_limit()
        
        for attempt in range(retries):
            try:
                response = requests.get(url, headers=self.headers, timeout=30)
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    # 请求过多，等待后重试
                    wait_time = 2 ** attempt
                    logger.warning(f"Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"API request failed: {response.status_code} - {response.text[:200]}")
                    
            except requests.RequestException as e:
                logger.error(f"Request error (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    
        return None
    
    def search_works(
        self,
        query: str,
        filters: Dict[str, Any] = None,
        sort: str = "relevance_score:desc",
        max_results: int = None
    ) -> List[Dict]:
        """
        搜索学术论文
        
        Args:
            query: 搜索关键词
            filters: 过滤条件，如 {"publication_year": ">2020", "type": "article"}
            sort: 排序方式
            max_results: 最大结果数
            
        Returns:
            论文列表，每个论文包含元数据
        """
        max_results = max_results or self.MAX_RESULTS
        
        # 检查缓存
        cache_key = f"search_{sanitize_filename(query)}_{max_results}"
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if self.enable_cache and cache_file.exists():
            logger.info(f"Loading cached results for query: {query}")
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        
        works = []
        page = 1
        
        with tqdm(total=max_results, desc=f"Searching OpenAlex: {query[:30]}...") as pbar:
            while len(works) < max_results:
                params = {
                    "search": query,
                    "per_page": min(self.PER_PAGE, max_results - len(works)),
                    "page": page,
                    "sort": sort
                }
                
                # 添加过滤条件
                if filters:
                    filter_parts = []
                    for key, value in filters.items():
                        filter_parts.append(f"{key}:{value}")
                    params["filter"] = ",".join(filter_parts)
                
                url = self._build_url("works", params)
                data = self._make_request(url)
                
                if not data or "results" not in data:
                    break
                    
                results = data["results"]
                if not results:
                    break
                    
                for work in results:
                    processed = self._process_work(work)
                    if processed:
                        works.append(processed)
                        pbar.update(1)
                        
                        if len(works) >= max_results:
                            break
                
                page += 1
                
                # 检查是否还有更多结果
                if len(results) < self.PER_PAGE:
                    break
        
        logger.info(f"Found {len(works)} works for query: {query}")
        
        # 保存缓存
        if self.enable_cache and works:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(works, f, indent=2, ensure_ascii=False)
                
        return works
    
    def _process_work(self, work: Dict) -> Optional[Dict]:
        """处理单个论文数据"""
        try:
            # 提取基本信息
            processed = {
                "openalex_id": work.get("id", ""),
                "doi": work.get("doi", ""),
                "title": work.get("title", ""),
                "abstract": self._get_abstract(work),
                "publication_year": work.get("publication_year"),
                "publication_date": work.get("publication_date"),
                "type": work.get("type", ""),
                "cited_by_count": work.get("cited_by_count", 0),
                "is_open_access": (work.get("open_access") or {}).get("is_oa", False),
                "pdf_url": self._get_pdf_url(work),
                "source": self._get_source(work),
                "authors": self._get_authors(work),
                "concepts": self._get_concepts(work),
                "from": "openalex"
            }
            
            # 只返回有标题的论文
            if processed["title"]:
                return processed
                
        except Exception as e:
            logger.error(f"Error processing work: {e}")
            
        return None
    
    def _get_abstract(self, work: Dict) -> str:
        """提取摘要"""
        abstract_inverted_index = work.get("abstract_inverted_index")
        if not abstract_inverted_index:
            return ""
            
        # OpenAlex使用倒排索引存储摘要，需要重建
        try:
            # 找出最大位置
            max_pos = max(
                pos 
                for positions in abstract_inverted_index.values() 
                for pos in positions
            )
            
            # 重建摘要
            words = [""] * (max_pos + 1)
            for word, positions in abstract_inverted_index.items():
                for pos in positions:
                    words[pos] = word
                    
            return " ".join(words)
        except Exception:
            return ""
    
    def _get_pdf_url(self, work: Dict) -> Optional[str]:
        """获取PDF下载链接"""
        # 优先使用开放获取链接
        oa_info = work.get("open_access") or {}
        if oa_info.get("is_oa"):
            oa_url = oa_info.get("oa_url")
            if oa_url:
                return oa_url
        
        # 尝试从best_oa_location获取
        best_oa = work.get("best_oa_location") or {}
        if best_oa:
            pdf_url = best_oa.get("pdf_url")
            if pdf_url:
                return pdf_url
                
        # 尝试从primary_location获取
        primary = work.get("primary_location") or {}
        if primary:
            pdf_url = primary.get("pdf_url")
            if pdf_url:
                return pdf_url
                
        return None
    
    def _get_source(self, work: Dict) -> Dict:
        """获取来源信息（期刊/会议）"""
        primary = work.get("primary_location") or {}
        source = (primary.get("source") or {}) if primary else {}
        
        return {
            "name": source.get("display_name", ""),
            "type": source.get("type", ""),
            "issn": source.get("issn_l", "")
        }
    
    def _get_authors(self, work: Dict) -> List[Dict]:
        """获取作者信息"""
        authors = []
        authorships = work.get("authorships") or []
        for authorship in authorships[:10]:  # 限制作者数量
            author = authorship.get("author") or {}
            authors.append({
                "name": author.get("display_name", ""),
                "orcid": author.get("orcid", ""),
                "institution": self._get_first_institution(authorship)
            })
        return authors
    
    def _get_first_institution(self, authorship: Dict) -> str:
        """获取第一个机构名称"""
        institutions = authorship.get("institutions", [])
        if institutions:
            return institutions[0].get("display_name", "")
        return ""
    
    def _get_concepts(self, work: Dict) -> List[Dict]:
        """获取概念标签"""
        concepts = []
        work_concepts = work.get("concepts") or []
        for concept in work_concepts[:5]:  # 限制概念数量
            concepts.append({
                "name": concept.get("display_name", ""),
                "score": concept.get("score", 0)
            })
        return concepts
    
    def get_work_by_id(self, openalex_id: str) -> Optional[Dict]:
        """根据OpenAlex ID获取论文详情"""
        url = self._build_url(f"works/{openalex_id}")
        data = self._make_request(url)
        
        if data:
            return self._process_work(data)
        return None
    
    def get_work_by_doi(self, doi: str) -> Optional[Dict]:
        """根据DOI获取论文详情"""
        # 确保DOI格式正确
        if not doi.startswith("https://doi.org/"):
            doi = f"https://doi.org/{doi}"
            
        url = self._build_url(f"works/{quote(doi, safe='')}")
        data = self._make_request(url)
        
        if data:
            return self._process_work(data)
        return None
    
    def get_related_works(self, openalex_id: str, max_results: int = 20) -> List[Dict]:
        """获取相关论文"""
        params = {
            "filter": f"related_to:{openalex_id}",
            "per_page": max_results,
            "sort": "relevance_score:desc"
        }
        
        url = self._build_url("works", params)
        data = self._make_request(url)
        
        if data and "results" in data:
            return [
                self._process_work(work) 
                for work in data["results"] 
                if self._process_work(work)
            ]
        return []
    
    def get_cited_by(self, openalex_id: str, max_results: int = 50) -> List[Dict]:
        """获取引用该论文的论文"""
        params = {
            "filter": f"cites:{openalex_id}",
            "per_page": max_results,
            "sort": "cited_by_count:desc"
        }
        
        url = self._build_url("works", params)
        data = self._make_request(url)
        
        if data and "results" in data:
            return [
                self._process_work(work) 
                for work in data["results"] 
                if self._process_work(work)
            ]
        return []
    
    def download_pdf(
        self, 
        work: Dict, 
        save_dir: Path,
        timeout: int = 60
    ) -> Optional[Path]:
        """
        下载论文PDF
        
        Args:
            work: 论文信息字典
            save_dir: 保存目录
            timeout: 下载超时时间
            
        Returns:
            下载成功返回文件路径，否则返回None
        """
        pdf_url = work.get("pdf_url")
        if not pdf_url:
            logger.warning(f"No PDF URL for: {work.get('title', 'Unknown')}")
            return None
            
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        title = work.get("title", "unknown")
        safe_title = sanitize_filename(title)[:100]
        filename = f"{safe_title}.pdf"
        filepath = save_dir / filename
        
        # 检查是否已存在
        if filepath.exists():
            logger.info(f"PDF already exists: {filepath}")
            return filepath
        
        try:
            logger.info(f"Downloading PDF: {pdf_url}")
            response = requests.get(
                pdf_url, 
                headers=self.headers, 
                timeout=timeout,
                stream=True
            )
            
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if "pdf" in content_type.lower() or pdf_url.endswith(".pdf"):
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
    
    def batch_download_pdfs(
        self,
        works: List[Dict],
        save_dir: Path,
        max_workers: int = 4
    ) -> List[Path]:
        """
        批量下载PDF
        
        Args:
            works: 论文列表
            save_dir: 保存目录
            max_workers: 并发下载数
            
        Returns:
            成功下载的文件路径列表
        """
        downloaded = []
        
        # 过滤出有PDF链接的论文
        works_with_pdf = [w for w in works if w.get("pdf_url")]
        
        if not works_with_pdf:
            logger.warning("No works with PDF URLs to download")
            return downloaded
            
        logger.info(f"Downloading {len(works_with_pdf)} PDFs...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.download_pdf, work, save_dir): work
                for work in works_with_pdf
            }
            
            for future in tqdm(
                as_completed(futures), 
                total=len(futures),
                desc="Downloading PDFs"
            ):
                result = future.result()
                if result:
                    downloaded.append(result)
                    
        logger.info(f"Successfully downloaded {len(downloaded)} PDFs")
        return downloaded


# 测试代码
if __name__ == "__main__":
    fetcher = OpenAlexFetcher(email="test@example.com")
    
    # 测试搜索
    results = fetcher.search_works(
        query="large language models survey",
        filters={"publication_year": ">2022"},
        max_results=10
    )
    
    print(f"Found {len(results)} results")
    for r in results[:3]:
        print(f"- {r['title']}")
        print(f"  PDF: {r['pdf_url']}")
        print()