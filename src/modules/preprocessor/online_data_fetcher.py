"""
Online Data Fetcher - 统一的在线文献获取接口

整合OpenAlex和arXiv两个数据源，提供统一的文献搜索和下载功能。

主要功能:
1. 并行搜索多个数据源
2. 结果合并和去重
3. 批量下载PDF
4. 与现有DataCleaner流程集成
"""

import json
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter

from tqdm import tqdm

from src.configs.logger import get_logger
from src.configs.constants import OUTPUT_DIR, DATASET_DIR, CACHE_DIR
from src.modules.utils import save_result, sanitize_filename
from src.modules.preprocessor.openalex_fetcher import OpenAlexFetcher
from src.modules.preprocessor.arxiv_downloader import ArxivDownloader

logger = get_logger("src.modules.preprocessor.OnlineDataFetcher")


class OnlineDataFetcher:
    """
    统一的在线文献获取接口
    
    整合OpenAlex和arXiv数据源，提供:
    - 并行搜索
    - 智能去重
    - 相关性排序
    - 批量下载
    """
    
    def __init__(
        self,
        openalex_email: str = None,
        enable_cache: bool = True,
        cache_dir: Path = None
    ):
        """
        初始化在线数据获取器
        
        Args:
            openalex_email: OpenAlex API的邮箱（用于polite pool）
            enable_cache: 是否启用缓存
            cache_dir: 缓存目录
        """
        self.enable_cache = enable_cache
        self.cache_dir = cache_dir or Path(CACHE_DIR) / "online_fetcher"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化各数据源
        self.openalex = OpenAlexFetcher(
            email=openalex_email,
            enable_cache=enable_cache
        )
        self.arxiv = ArxivDownloader(enable_cache=enable_cache)
        
        # 默认配置
        self.default_max_results = 100
        self.default_arxiv_categories = ["cs.CL", "cs.AI", "cs.LG", "cs.CV", "cs.IR"]
        
    def search(
        self,
        query: str,
        keywords: List[str] = None,
        max_results: int = None,
        sources: List[str] = None,
        year_from: int = None,
        year_to: int = None,
        arxiv_categories: List[str] = None
    ) -> List[Dict]:
        """
        搜索学术文献
        
        Args:
            query: 主搜索词
            keywords: 额外关键词列表
            max_results: 最大结果数
            sources: 数据源列表 ["openalex", "arxiv"]，默认全部
            year_from: 起始年份
            year_to: 结束年份
            arxiv_categories: arXiv类别过滤
            
        Returns:
            合并去重后的论文列表
        """
        max_results = max_results or self.default_max_results
        sources = sources or ["openalex", "arxiv"]
        arxiv_categories = arxiv_categories or self.default_arxiv_categories
        
        # 构建搜索词列表
        search_terms = [query]
        if keywords:
            search_terms.extend(keywords)
        
        all_papers = []
        
        # 并行搜索各数据源
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = []
            
            if "openalex" in sources:
                futures.append(
                    executor.submit(
                        self._search_openalex,
                        search_terms,
                        max_results,
                        year_from,
                        year_to
                    )
                )
                
            if "arxiv" in sources:
                futures.append(
                    executor.submit(
                        self._search_arxiv,
                        search_terms,
                        max_results,
                        arxiv_categories
                    )
                )
            
            for future in as_completed(futures):
                try:
                    papers = future.result()
                    all_papers.extend(papers)
                except Exception as e:
                    logger.error(f"Search error: {e}")
        
        # 去重和排序
        unique_papers = self._deduplicate(all_papers)
        sorted_papers = self._sort_by_relevance(unique_papers, query)
        
        # 限制结果数
        final_papers = sorted_papers[:max_results]
        
        logger.info(
            f"Search completed: {len(all_papers)} total, "
            f"{len(unique_papers)} unique, {len(final_papers)} returned"
        )
        
        return final_papers
    
    def _search_openalex(
        self,
        search_terms: List[str],
        max_results: int,
        year_from: int = None,
        year_to: int = None
    ) -> List[Dict]:
        """搜索OpenAlex"""
        papers = []
        results_per_term = max(max_results // len(search_terms), 20)
        
        for term in search_terms:
            try:
                # 构建过滤条件
                filters = {}
                if year_from:
                    filters["publication_year"] = f">{year_from - 1}"
                if year_to:
                    if "publication_year" in filters:
                        filters["publication_year"] += f",<{year_to + 1}"
                    else:
                        filters["publication_year"] = f"<{year_to + 1}"
                
                results = self.openalex.search_works(
                    query=term,
                    filters=filters if filters else None,
                    max_results=results_per_term
                )
                papers.extend(results)
                
            except Exception as e:
                logger.error(f"OpenAlex search error for '{term}': {e}")
                
        logger.info(f"OpenAlex: found {len(papers)} papers")
        return papers
    
    def _search_arxiv(
        self,
        search_terms: List[str],
        max_results: int,
        categories: List[str] = None
    ) -> List[Dict]:
        """搜索arXiv"""
        papers = []
        results_per_term = max(max_results // len(search_terms), 20)
        
        for term in search_terms:
            try:
                # 构建类别过滤
                if categories:
                    cat_query = " OR ".join([f"cat:{cat}" for cat in categories])
                    full_query = f"({term}) AND ({cat_query})"
                else:
                    full_query = term
                    
                results = self.arxiv.search(
                    query=full_query,
                    max_results=results_per_term
                )
                papers.extend(results)
                
            except Exception as e:
                logger.error(f"arXiv search error for '{term}': {e}")
                
        logger.info(f"arXiv: found {len(papers)} papers")
        return papers
    
    def _deduplicate(self, papers: List[Dict]) -> List[Dict]:
        """
        去重论文列表
        
        使用标题相似度进行去重，保留信息更完整的版本
        """
        unique = {}
        
        for paper in papers:
            # 生成标准化的标题作为key
            title = paper.get("title", "")
            if not title:
                continue
                
            # 标准化标题：小写，去除标点和多余空格
            normalized = self._normalize_title(title)
            title_hash = hashlib.md5(normalized.encode()).hexdigest()[:16]
            
            if title_hash not in unique:
                unique[title_hash] = paper
            else:
                # 保留信息更完整的版本
                existing = unique[title_hash]
                if self._paper_completeness(paper) > self._paper_completeness(existing):
                    unique[title_hash] = paper
                    
        return list(unique.values())
    
    def _normalize_title(self, title: str) -> str:
        """标准化标题"""
        import re
        # 转小写
        title = title.lower()
        # 去除标点
        title = re.sub(r'[^\w\s]', '', title)
        # 去除多余空格
        title = ' '.join(title.split())
        return title
    
    def _paper_completeness(self, paper: Dict) -> int:
        """计算论文信息完整度分数"""
        score = 0
        
        # 基本字段
        if paper.get("title"):
            score += 1
        if paper.get("abstract") and len(paper["abstract"]) > 100:
            score += 2
        if paper.get("authors"):
            score += 1
        if paper.get("pdf_url"):
            score += 3  # PDF链接很重要
        if paper.get("doi"):
            score += 1
        if paper.get("publication_year") or paper.get("published"):
            score += 1
            
        return score
    
    def _sort_by_relevance(self, papers: List[Dict], query: str) -> List[Dict]:
        """
        按相关性排序
        
        考虑因素:
        - 标题匹配度
        - 引用数
        - 是否有PDF
        - 发表时间
        """
        query_terms = set(query.lower().split())
        
        def relevance_score(paper: Dict) -> float:
            score = 0.0
            
            # 标题匹配
            title = paper.get("title", "").lower()
            title_terms = set(title.split())
            overlap = len(query_terms & title_terms)
            score += overlap * 10
            
            # 引用数（OpenAlex）
            cited_by = paper.get("cited_by_count", 0)
            if cited_by:
                score += min(cited_by / 10, 20)  # 最多加20分
            
            # 有PDF链接
            if paper.get("pdf_url"):
                score += 15
                
            # 开放获取
            if paper.get("is_open_access"):
                score += 5
                
            # 较新的论文
            year = paper.get("publication_year")
            if not year and paper.get("published"):
                try:
                    year = int(paper["published"][:4])
                except:
                    pass
            if year and year >= 2020:
                score += (year - 2019) * 2
                
            return score
        
        return sorted(papers, key=relevance_score, reverse=True)
    
    def download_pdfs(
        self,
        papers: List[Dict],
        save_dir: Path,
        max_downloads: int = None
    ) -> Tuple[List[Path], List[Dict]]:
        """
        下载论文PDF
        
        Args:
            papers: 论文列表
            save_dir: 保存目录
            max_downloads: 最大下载数
            
        Returns:
            (成功下载的文件路径列表, 对应的论文信息列表)
        """
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # 过滤出有PDF链接的论文
        papers_with_pdf = [p for p in papers if p.get("pdf_url")]
        
        if max_downloads:
            papers_with_pdf = papers_with_pdf[:max_downloads]
            
        if not papers_with_pdf:
            logger.warning("No papers with PDF URLs to download")
            return [], []
        
        logger.info(f"Downloading {len(papers_with_pdf)} PDFs...")
        
        downloaded_paths = []
        downloaded_papers = []
        
        for paper in tqdm(papers_with_pdf, desc="Downloading PDFs"):
            source = paper.get("from", "unknown")
            
            try:
                if source == "arxiv":
                    path = self.arxiv.download_pdf(paper=paper, save_dir=save_dir)
                else:
                    path = self.openalex.download_pdf(paper, save_dir)
                    
                if path:
                    downloaded_paths.append(path)
                    downloaded_papers.append(paper)
                    
            except Exception as e:
                logger.error(f"Download error for {paper.get('title', 'Unknown')}: {e}")
        
        logger.info(f"Successfully downloaded {len(downloaded_paths)} PDFs")
        return downloaded_paths, downloaded_papers
    
    def fetch_and_prepare(
        self,
        query: str,
        keywords: List[str] = None,
        task_id: str = None,
        max_papers: int = 50,
        max_downloads: int = 30
    ) -> Dict[str, Any]:
        """
        完整的文献获取和准备流程
        
        Args:
            query: 主搜索词
            keywords: 额外关键词
            task_id: 任务ID
            max_papers: 最大搜索结果数
            max_downloads: 最大下载数
            
        Returns:
            {
                "papers": 搜索到的论文列表,
                "downloaded_pdfs": 下载的PDF路径列表,
                "pdf_dir": PDF保存目录,
                "metadata_file": 元数据文件路径
            }
        """
        # 设置保存目录
        if task_id:
            base_dir = Path(OUTPUT_DIR) / task_id
        else:
            base_dir = Path(DATASET_DIR) / "online_fetch"
            
        pdf_dir = base_dir / "pdfs"
        metadata_dir = base_dir / "metadata"
        
        pdf_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.mkdir(parents=True, exist_ok=True)
        
        # 搜索论文
        logger.info(f"Searching for papers: {query}")
        papers = self.search(
            query=query,
            keywords=keywords,
            max_results=max_papers
        )
        
        # 保存搜索结果元数据
        metadata_file = metadata_dir / "search_results.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(papers, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved metadata to {metadata_file}")
        
        # 下载PDF
        downloaded_paths, downloaded_papers = self.download_pdfs(
            papers=papers,
            save_dir=pdf_dir,
            max_downloads=max_downloads
        )
        
        # 保存下载记录
        download_record = {
            "total_found": len(papers),
            "downloaded": len(downloaded_paths),
            "papers": [
                {
                    "title": p.get("title"),
                    "pdf_path": str(path),
                    "source": p.get("from")
                }
                for p, path in zip(downloaded_papers, downloaded_paths)
            ]
        }
        
        download_record_file = metadata_dir / "download_record.json"
        with open(download_record_file, "w", encoding="utf-8") as f:
            json.dump(download_record, f, indent=2, ensure_ascii=False)
        
        return {
            "papers": papers,
            "downloaded_pdfs": downloaded_paths,
            "downloaded_papers": downloaded_papers,
            "pdf_dir": pdf_dir,
            "metadata_file": metadata_file
        }
    
    def expand_keywords(
        self,
        initial_keywords: List[str],
        papers: List[Dict],
        max_new_keywords: int = 5
    ) -> List[str]:
        """
        基于已搜索的论文扩展关键词
        
        从论文的概念标签和标题中提取高频词作为新关键词
        """
        # 收集所有概念
        concept_counter = Counter()
        
        for paper in papers:
            # OpenAlex的概念
            concepts = paper.get("concepts", [])
            for concept in concepts:
                name = concept.get("name", "")
                if name and name.lower() not in [k.lower() for k in initial_keywords]:
                    concept_counter[name] += 1
            
            # arXiv的类别
            categories = paper.get("categories", [])
            for cat in categories:
                concept_counter[cat] += 1
        
        # 选择最常见的新关键词
        new_keywords = []
        for keyword, count in concept_counter.most_common():
            if len(new_keywords) >= max_new_keywords:
                break
            if keyword.lower() not in [k.lower() for k in initial_keywords]:
                new_keywords.append(keyword)
        
        logger.info(f"Expanded keywords: {new_keywords}")
        return new_keywords


# 测试代码
if __name__ == "__main__":
    fetcher = OnlineDataFetcher(openalex_email="test@example.com")
    
    # 测试搜索
    results = fetcher.search(
        query="large language models survey",
        keywords=["LLM", "GPT"],
        max_results=20
    )
    
    print(f"\nFound {len(results)} unique papers:")
    for i, r in enumerate(results[:5]):
        print(f"\n{i+1}. [{r.get('from')}] {r.get('title', 'No title')[:60]}...")
        print(f"   PDF: {'Yes' if r.get('pdf_url') else 'No'}")
        if r.get("cited_by_count"):
            print(f"   Citations: {r['cited_by_count']}")