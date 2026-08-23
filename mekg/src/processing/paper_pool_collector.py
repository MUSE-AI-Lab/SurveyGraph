"""
论文池收集器
支持 OpenAlex API 直接调用
"""

import asyncio
import time
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Set, Optional
from datetime import datetime, timedelta

import httpx
from loguru import logger

# 导入配置
from src.configs import config

class PaperPoolCollector:
    def __init__(
        self,
        email: str = None,
        max_concurrent: int = 10,
        rate_limit_delay: float = 0.1
    ):
        self.base_url = "https://api.openalex.org"
        self.email = email or getattr(config, 'OPENALEX_EMAIL', 'user@example.com')
        self.max_concurrent = max_concurrent
        self.rate_limit_delay = rate_limit_delay
        self.headers = {"User-Agent": f"SurveyY/1.0 (mailto:{self.email})"}

    async def collect_comprehensive_pool(
        self,
        keywords: List[str],
        target_count: int = 500,
        year_start: int = 2018,
        year_end: int = 2024,
        enrich_cited_by: bool = True,
        use_survey_strategy: bool = True,
        survey_count: int = 10,
        max_refs_per_survey: int = 100
    ) -> List[Dict[str, Any]]:
        """
        综合论文池收集
        
        策略：
        1. 如果启用综述策略，先搜索综述论文，然后展开其引用
        2. 直接关键词搜索补充
        3. 去重并返回
        """
        logger.info(f"开始收集论文池: keywords={keywords}, target={target_count}")
        
        all_papers = []
        seen_ids = set()
        
        # 1. 综述优先策略
        if use_survey_strategy:
            logger.info("使用综述优先策略...")
            surveys = await self.search_survey_papers(
                keywords=keywords,
                max_surveys=survey_count,
                year_start=year_start,
                year_end=year_end
            )
            logger.info(f"找到 {len(surveys)} 篇综述论文")
            
            # 添加综述本身
            for survey in surveys:
                paper_id = survey.get('paper_id')
                if paper_id and paper_id not in seen_ids:
                    all_papers.append(survey)
                    seen_ids.add(paper_id)
            
            # 展开综述的引用
            if surveys:
                ref_papers = await self.expand_from_survey_references(
                    surveys=surveys,
                    max_refs_per_survey=max_refs_per_survey,
                    year_filter=year_start
                )
                for paper in ref_papers:
                    paper_id = paper.get('paper_id')
                    if paper_id and paper_id not in seen_ids:
                        all_papers.append(paper)
                        seen_ids.add(paper_id)
                logger.info(f"从综述引用中获取 {len(ref_papers)} 篇论文")
        
        # 2. 直接关键词搜索补充
        remaining = target_count - len(all_papers)
        if remaining > 0:
            logger.info(f"关键词搜索补充 {remaining} 篇...")
            keyword_papers = await self.search_papers_by_keywords(
                keywords=keywords,
                target_count=remaining,
                year_start=year_start,
                year_end=year_end
            )
            for paper in keyword_papers:
                paper_id = paper.get('paper_id')
                if paper_id and paper_id not in seen_ids:
                    all_papers.append(paper)
                    seen_ids.add(paper_id)
        
        logger.info(f"论文池收集完成: 共 {len(all_papers)} 篇")
        return all_papers[:target_count]

    async def search_papers_by_keywords(
        self,
        keywords: List[str],
        target_count: int = 500,
        year_start: int = 2018,
        year_end: int = 2024,
        min_citations: int = 0
    ) -> List[Dict[str, Any]]:
        """通过关键词搜索论文"""
        all_papers = []
        seen_ids = set()
        
        for keyword in keywords:
            if len(all_papers) >= target_count:
                break
                
            papers = await self._search_keyword(
                keyword=keyword,
                max_results=min(200, target_count - len(all_papers)),
                year_start=year_start,
                year_end=year_end,
                min_citations=min_citations
            )
            
            for paper in papers:
                paper_id = paper.get('paper_id')
                if paper_id and paper_id not in seen_ids:
                    all_papers.append(paper)
                    seen_ids.add(paper_id)
        
        return all_papers

    async def _search_keyword(
        self,
        keyword: str,
        max_results: int = 200,
        year_start: int = 2018,
        year_end: int = 2024,
        min_citations: int = 0
    ) -> List[Dict[str, Any]]:
        """搜索单个关键词"""
        papers = []
        cursor = "*"
        per_page = min(200, max_results)
        
        async with httpx.AsyncClient(timeout=30.0, headers=self.headers) as client:
            while len(papers) < max_results:
                try:
                    # 构建查询
                    params = {
                        "search": keyword,
                        "filter": f"publication_year:{year_start}-{year_end},cited_by_count:>{min_citations}",
                        "sort": "cited_by_count:desc",
                        "per_page": per_page,
                        "cursor": cursor,
                        "mailto": self.email
                    }
                    
                    response = await client.get(f"{self.base_url}/works", params=params)
                    
                    if response.status_code != 200:
                        logger.warning(f"OpenAlex API error: {response.status_code}")
                        break
                    
                    data = response.json()
                    results = data.get("results", [])
                    
                    if not results:
                        break
                    
                    for work in results:
                        paper = self._parse_openalex_work(work)
                        if paper:
                            papers.append(paper)
                    
                    # 获取下一页游标
                    meta = data.get("meta", {})
                    cursor = meta.get("next_cursor")
                    if not cursor:
                        break
                    
                    # 速率限制
                    await asyncio.sleep(self.rate_limit_delay)
                    
                except Exception as e:
                    logger.error(f"搜索关键词 '{keyword}' 失败: {e}")
                    break
        
        logger.info(f"关键词 '{keyword}' 搜索到 {len(papers)} 篇论文")
        return papers

    def _parse_openalex_work(self, work: Dict) -> Optional[Dict[str, Any]]:
        """解析 OpenAlex 返回的论文数据"""
        try:
            openalex_id = work.get("id", "")
            paper_id = openalex_id.split("/")[-1] if openalex_id else None
            
            if not paper_id:
                return None
            
            # 提取作者
            authors = []
            for authorship in work.get("authorships", [])[:10]:
                author = authorship.get("author", {})
                if author.get("display_name"):
                    authors.append(author["display_name"])
            
            # 提取摘要
            abstract = self._reconstruct_abstract(work.get("abstract_inverted_index"))
            
            # 提取引用
            referenced_works = []
            for ref in work.get("referenced_works", []):
                if isinstance(ref, str) and "openalex.org" in ref:
                    ref_id = ref.split("/")[-1]
                    referenced_works.append(ref_id)
            
            # 提取 PDF URL
            pdf_url = None
            primary_location = work.get("primary_location", {}) or {}
            if primary_location.get("pdf_url"):
                pdf_url = primary_location["pdf_url"]
            elif work.get("open_access", {}).get("oa_url"):
                pdf_url = work["open_access"]["oa_url"]
            
            # 提取发表地点
            venue = ""
            source = primary_location.get("source", {}) or {}
            if source.get("display_name"):
                venue = source["display_name"]
            
            return {
                "paper_id": paper_id,
                "openalex_id": openalex_id,
                "title": work.get("title", ""),
                "abstract": abstract or "",
                "authors": ", ".join(authors),
                "year": work.get("publication_year"),
                "venue": venue,
                "citations": work.get("cited_by_count", 0),
                "referenced_works": referenced_works,
                "pdf_url": pdf_url,
                "doi": work.get("doi"),
                "type": work.get("type", ""),
                "source": "openalex"
            }
        except Exception as e:
            logger.debug(f"解析论文失败: {e}")
            return None

    def _reconstruct_abstract(self, inverted_index: Dict) -> str:
        """从倒排索引重建摘要"""
        if not inverted_index:
            return ""
        
        try:
            # 找出最大位置
            max_pos = 0
            for positions in inverted_index.values():
                if positions:
                    max_pos = max(max_pos, max(positions))
            
            # 重建文本
            words = [""] * (max_pos + 1)
            for word, positions in inverted_index.items():
                for pos in positions:
                    if pos <= max_pos:
                        words[pos] = word
            
            return " ".join(words)
        except Exception:
            return ""

    async def search_survey_papers(
        self,
        keywords: List[str],
        max_surveys: int = 10,
        year_start: int = 2018,
        year_end: int = 2024,
        min_citations: int = 50
    ) -> List[Dict[str, Any]]:
        """搜索综述论文"""
        surveys = []
        
        for keyword in keywords:
            # 搜索包含 "survey" 或 "review" 的论文
            survey_keywords = [
                f"{keyword} survey",
                f"{keyword} review",
                f"{keyword} overview"
            ]
            
            for sk in survey_keywords:
                if len(surveys) >= max_surveys:
                    break
                    
                papers = await self._search_keyword(
                    keyword=sk,
                    max_results=max_surveys,
                    year_start=year_start,
                    year_end=year_end,
                    min_citations=min_citations
                )
                
                for paper in papers:
                    title_lower = paper.get("title", "").lower()
                    if any(term in title_lower for term in ["survey", "review", "overview", "tutorial"]):
                        surveys.append(paper)
                        if len(surveys) >= max_surveys:
                            break
        
        return surveys[:max_surveys]

    async def expand_from_survey_references(
        self,
        surveys: List[Dict],
        max_refs_per_survey: int = 100,
        year_filter: int = None
    ) -> List[Dict[str, Any]]:
        """从综述的引用中展开获取论文"""
        all_ref_ids = set()
        
        for survey in surveys:
            refs = survey.get("referenced_works", [])[:max_refs_per_survey]
            all_ref_ids.update(refs)
        
        if not all_ref_ids:
            return []
        
        logger.info(f"从综述中收集到 {len(all_ref_ids)} 个引用ID")
        
        # 批量获取论文详情
        papers = await self._batch_fetch_papers_by_ids(
            paper_ids=list(all_ref_ids),
            year_filter=year_filter
        )
        
        return papers

    async def _batch_fetch_papers_by_ids(
        self,
        paper_ids: List[str],
        year_filter: int = None,
        batch_size: int = 50
    ) -> List[Dict[str, Any]]:
        """批量获取论文详情"""
        papers = []
        
        async with httpx.AsyncClient(timeout=30.0, headers=self.headers) as client:
            for i in range(0, len(paper_ids), batch_size):
                batch_ids = paper_ids[i:i+batch_size]
                
                # 构建过滤器
                ids_filter = "|".join(batch_ids)
                params = {
                    "filter": f"openalex_id:{ids_filter}",
                    "per_page": batch_size,
                    "mailto": self.email
                }
                
                if year_filter:
                    params["filter"] += f",publication_year:>{year_filter}"
                
                try:
                    response = await client.get(f"{self.base_url}/works", params=params)
                    
                    if response.status_code == 200:
                        data = response.json()
                        for work in data.get("results", []):
                            paper = self._parse_openalex_work(work)
                            if paper:
                                papers.append(paper)
                    
                    await asyncio.sleep(self.rate_limit_delay)
                    
                except Exception as e:
                    logger.error(f"批量获取论文失败: {e}")
        
        return papers

    async def fetch_latest_arxiv_papers(
        self,
        categories: List[str] = ["cs.AI", "cs.CL", "cs.CV", "cs.LG"],
        max_results: int = 20
    ) -> List[Dict[str, Any]]:
        """
        从 arXiv 获取最新论文，并使用 OpenAlex 增强元数据
        """
        logger.info(f"Fetching latest papers from arXiv: {categories}")
        
        # 1. 从 arXiv 获取基础列表
        cat_query = " OR ".join([f"cat:{c}" for c in categories])
        url = "https://export.arxiv.org/api/query"
        params = {
            "search_query": cat_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending"
        }
        
        arxiv_papers = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                root = ET.fromstring(response.content)
                ns = {'atom': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
                
                for entry in root.findall('atom:entry', ns):
                    paper_id = entry.find('atom:id', ns).text.split('/')[-1].split('v')[0]
                    title = entry.find('atom:title', ns).text.replace('\n', ' ').strip()
                    summary = entry.find('atom:summary', ns).text.replace('\n', ' ').strip()
                    published = entry.find('atom:published', ns).text
                    
                    # 获取 PDF 链接
                    pdf_url = ""
                    for link in entry.findall('atom:link', ns):
                        if link.attrib.get('title') == 'pdf':
                            pdf_url = link.attrib.get('href')
                            if pdf_url.startswith("http://"):
                                pdf_url = pdf_url.replace("http://", "https://")
                    
                    arxiv_papers.append({
                        "paper_id": f"arXiv:{paper_id}",
                        "arxiv_id": paper_id,
                        "title": title,
                        "abstract": summary,
                        "year": int(published[:4]),
                        "pdf_url": pdf_url,
                        "source": "arxiv"
                    })
                    
            except Exception as e:
                logger.error(f"arXiv fetch failed: {e}")
                return []

        if not arxiv_papers:
            return []

        # 2. 使用 OpenAlex 增强
        logger.info(f"Enriching {len(arxiv_papers)} papers with OpenAlex data...")
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def fetch_openalex(paper):
            async with semaphore:
                try:
                    work_id = f"https://arxiv.org/abs/{paper['arxiv_id']}"
                    async with httpx.AsyncClient(timeout=10.0, headers=self.headers) as client:
                        res = await client.get(f"{self.base_url}/works/{work_id}")
                        if res.status_code == 200:
                            work = res.json()
                            refs = [r.split('/')[-1] for r in work.get('referenced_works', [])]
                            paper['referenced_works'] = refs
                            paper['citations'] = work.get('cited_by_count', 0)
                            paper['openalex_id'] = work.get('id')
                except Exception:
                    pass
                return paper

        tasks = [fetch_openalex(p) for p in arxiv_papers]
        enriched_papers = await asyncio.gather(*tasks)
        
        logger.info(f"Successfully enriched {len(enriched_papers)} papers")
        return enriched_papers


# 测试代码
if __name__ == "__main__":
    async def test():
        collector = PaperPoolCollector()
        papers = await collector.collect_comprehensive_pool(
            keywords=["Large Language Model Agents"],
            target_count=50,
            year_start=2020,
            year_end=2024
        )
        print(f"Collected {len(papers)} papers")
        for p in papers[:5]:
            print(f"  - {p['title'][:60]}... ({p['year']}, citations={p['citations']})")
    
    asyncio.run(test())
