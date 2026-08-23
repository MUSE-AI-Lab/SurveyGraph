"""
论文收集器
================

支持论文收集，默认只使用 arXiv 作为数据源。

核心特性：
1. **只使用 arXiv**：默认只从 arXiv 搜索论文，确保 PDF 可下载
2. **目标数量保证**：确保收集到目标数量的 90%，不够则自动重试
3. **智能关键词扩展**：使用 LLM 生成关键词变体，扩大搜索范围
4. **智能筛选**：Embedding 初筛 + LLM 细筛
5. **自动重试机制**：如果论文数量不足，自动生成新关键词重新搜索

可选数据源（默认关闭）：
- OpenAlex（备用来源，元数据丰富，但 PDF 下载困难）
- Semantic Scholar（获取参考文献列表，但不用于搜索）

使用方法:
    collector = EnhancedPaperCollector()
    papers = await collector.collect_papers(
        topic="Large Language Model Function Calling",
        target_count=100,
        min_target_ratio=0.9  # 确保收集到 90% 的目标数量
    )
"""

import asyncio
import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from loguru import logger
from tqdm import tqdm

# 尝试导入 embedding 模型
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    HAS_EMBEDDING = True
except ImportError:
    HAS_EMBEDDING = False
    logger.warning("sentence-transformers 未安装，将跳过 embedding 筛选")

# 尝试导入 ChatAgent
try:
    import sys
    project_root = Path(__file__).parent.parent.parent.parent
    sys.path.insert(0, str(project_root))
    from src.models.LLM.ChatAgent import ChatAgent
    from src.configs.config import (
        RELEVANCE_FILTER_WORKERS,
        PAPER_SEARCH_WORKERS,
        PDF_DOWNLOAD_WORKERS
    )
    HAS_CHAT_AGENT = True
except ImportError:
    HAS_CHAT_AGENT = False
    # 默认值
    RELEVANCE_FILTER_WORKERS = 50
    PAPER_SEARCH_WORKERS = 50
    PDF_DOWNLOAD_WORKERS = 50


@dataclass
class PaperData:
    """统一的论文数据结构"""
    paper_id: str
    title: str
    abstract: str = ""
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    venue: str = ""
    citations: int = 0
    referenced_works: List[str] = field(default_factory=list)
    pdf_url: Optional[str] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    openalex_id: Optional[str] = None
    source: str = "unknown"  # arxiv, openalex, semantic_scholar
    is_survey: bool = False
    relevance_score: float = 0.0
    md_text: str = ""  # 论文全文（从 PDF 解析）
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors if isinstance(self.authors, list) else [self.authors],
            "year": self.year,
            "venue": self.venue,
            "citations": self.citations,
            "referenced_works": self.referenced_works,
            "pdf_url": self.pdf_url,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "openalex_id": self.openalex_id,
            "source": self.source,
            "is_survey": self.is_survey,
            "relevance_score": self.relevance_score,
            "md_text": self.md_text  # 论文全文
        }


class ArxivSearcher:
    """
    arXiv 搜索器
    
    使用 arXiv API 搜索论文，支持：
    - 关键词搜索
    - 分类过滤（自动根据主题判断）
    - 时间范围过滤
    """
    
    BASE_URL = "https://export.arxiv.org/api/query"
    
    # arXiv 所有主要分类（完整列表）
    # 参考: https://arxiv.org/category_taxonomy
    ALL_CATEGORIES = {
        # 计算机科学 (Computer Science)
        "cs.AI": "Artificial Intelligence",
        "cs.CL": "Computation and Language",
        "cs.CC": "Computational Complexity",
        "cs.CE": "Computational Engineering, Finance, and Science",
        "cs.CG": "Computational Geometry",
        "cs.GT": "Computer Science and Game Theory",
        "cs.CV": "Computer Vision and Pattern Recognition",
        "cs.CY": "Computers and Society",
        "cs.CR": "Cryptography and Security",
        "cs.DS": "Data Structures and Algorithms",
        "cs.DB": "Databases",
        "cs.DL": "Digital Libraries",
        "cs.DM": "Discrete Mathematics",
        "cs.DC": "Distributed, Parallel, and Cluster Computing",
        "cs.ET": "Emerging Technologies",
        "cs.FL": "Formal Languages and Automata Theory",
        "cs.GL": "General Literature",
        "cs.GR": "Graphics",
        "cs.AR": "Hardware Architecture",
        "cs.HC": "Human-Computer Interaction",
        "cs.IR": "Information Retrieval",
        "cs.IT": "Information Theory",
        "cs.LO": "Logic in Computer Science",
        "cs.LG": "Machine Learning",
        "cs.MS": "Mathematical Software",
        "cs.MA": "Multiagent Systems",
        "cs.MM": "Multimedia",
        "cs.NI": "Networking and Internet Architecture",
        "cs.NE": "Neural and Evolutionary Computing",
        "cs.NA": "Numerical Analysis",
        "cs.OS": "Operating Systems",
        "cs.OH": "Other Computer Science",
        "cs.PF": "Performance",
        "cs.PL": "Programming Languages",
        "cs.RO": "Robotics",
        "cs.SI": "Social and Information Networks",
        "cs.SE": "Software Engineering",
        "cs.SD": "Sound",
        "cs.SC": "Symbolic Computation",
        "cs.SY": "Systems and Control",
        
        # 经济学 (Economics)
        "econ.EM": "Econometrics",
        "econ.GN": "General Economics",
        "econ.TH": "Theoretical Economics",
        
        # 电气工程与系统科学 (Electrical Engineering and Systems Science)
        "eess.AS": "Audio and Speech Processing",
        "eess.IV": "Image and Video Processing",
        "eess.SP": "Signal Processing",
        "eess.SY": "Systems and Control",
        
        # 数学 (Mathematics)
        "math.AG": "Algebraic Geometry",
        "math.AT": "Algebraic Topology",
        "math.AP": "Analysis of PDEs",
        "math.CT": "Category Theory",
        "math.CA": "Classical Analysis and ODEs",
        "math.CO": "Combinatorics",
        "math.AC": "Commutative Algebra",
        "math.CV": "Complex Variables",
        "math.DG": "Differential Geometry",
        "math.DS": "Dynamical Systems",
        "math.FA": "Functional Analysis",
        "math.GM": "General Mathematics",
        "math.GN": "General Topology",
        "math.GT": "Geometric Topology",
        "math.GR": "Group Theory",
        "math.HO": "History and Overview",
        "math.IT": "Information Theory",
        "math.KT": "K-Theory and Homology",
        "math.LO": "Logic",
        "math.MP": "Mathematical Physics",
        "math.MG": "Metric Geometry",
        "math.NT": "Number Theory",
        "math.NA": "Numerical Analysis",
        "math.OA": "Operator Algebras",
        "math.OC": "Optimization and Control",
        "math.PR": "Probability",
        "math.QA": "Quantum Algebra",
        "math.RT": "Representation Theory",
        "math.RA": "Rings and Algebras",
        "math.SP": "Spectral Theory",
        "math.ST": "Statistics Theory",
        "math.SG": "Symplectic Geometry",
        
        # 物理学 (Physics)
        "astro-ph": "Astrophysics",
        "astro-ph.CO": "Cosmology and Nongalactic Astrophysics",
        "astro-ph.EP": "Earth and Planetary Astrophysics",
        "astro-ph.GA": "Astrophysics of Galaxies",
        "astro-ph.HE": "High Energy Astrophysical Phenomena",
        "astro-ph.IM": "Instrumentation and Methods for Astrophysics",
        "astro-ph.SR": "Solar and Stellar Astrophysics",
        "cond-mat": "Condensed Matter",
        "cond-mat.dis-nn": "Disordered Systems and Neural Networks",
        "cond-mat.mes-hall": "Mesoscale and Nanoscale Physics",
        "cond-mat.mtrl-sci": "Materials Science",
        "cond-mat.other": "Other Condensed Matter",
        "cond-mat.quant-gas": "Quantum Gases",
        "cond-mat.soft": "Soft Condensed Matter",
        "cond-mat.stat-mech": "Statistical Mechanics",
        "cond-mat.str-el": "Strongly Correlated Electrons",
        "cond-mat.supr-con": "Superconductivity",
        "gr-qc": "General Relativity and Quantum Cosmology",
        "hep-ex": "High Energy Physics - Experiment",
        "hep-lat": "High Energy Physics - Lattice",
        "hep-ph": "High Energy Physics - Phenomenology",
        "hep-th": "High Energy Physics - Theory",
        "math-ph": "Mathematical Physics",
        "nlin.AO": "Adaptation and Self-Organizing Systems",
        "nlin.CG": "Cellular Automata and Lattice Gases",
        "nlin.CD": "Chaotic Dynamics",
        "nlin.SI": "Exactly Solvable and Integrable Systems",
        "nlin.PS": "Pattern Formation and Solitons",
        "nucl-ex": "Nuclear Experiment",
        "nucl-th": "Nuclear Theory",
        "physics.acc-ph": "Accelerator Physics",
        "physics.ao-ph": "Atmospheric and Oceanic Physics",
        "physics.atom-ph": "Atomic Physics",
        "physics.atm-clus": "Atomic and Molecular Clusters",
        "physics.bio-ph": "Biological Physics",
        "physics.chem-ph": "Chemical Physics",
        "physics.class-ph": "Classical Physics",
        "physics.comp-ph": "Computational Physics",
        "physics.data-an": "Data Analysis, Statistics and Probability",
        "physics.flu-dyn": "Fluid Dynamics",
        "physics.gen-ph": "General Physics",
        "physics.geo-ph": "Geophysics",
        "physics.hist-ph": "History and Philosophy of Physics",
        "physics.ins-det": "Instrumentation and Detectors",
        "physics.med-ph": "Medical Physics",
        "physics.optics": "Optics",
        "physics.ed-ph": "Physics Education",
        "physics.soc-ph": "Physics and Society",
        "physics.plasm-ph": "Plasma Physics",
        "physics.pop-ph": "Popular Physics",
        "physics.space-ph": "Space Physics",
        "quant-ph": "Quantum Physics",
        
        # 定量生物学 (Quantitative Biology)
        "q-bio.BM": "Biomolecules",
        "q-bio.CB": "Cell Behavior",
        "q-bio.GN": "Genomics",
        "q-bio.MN": "Molecular Networks",
        "q-bio.NC": "Neurons and Cognition",
        "q-bio.OT": "Other Quantitative Biology",
        "q-bio.PE": "Populations and Evolution",
        "q-bio.QM": "Quantitative Methods",
        "q-bio.SC": "Subcellular Processes",
        "q-bio.TO": "Tissues and Organs",
        
        # 定量金融 (Quantitative Finance)
        "q-fin.CP": "Computational Finance",
        "q-fin.EC": "Economics",
        "q-fin.GN": "General Finance",
        "q-fin.MF": "Mathematical Finance",
        "q-fin.PM": "Portfolio Management",
        "q-fin.PR": "Pricing of Securities",
        "q-fin.RM": "Risk Management",
        "q-fin.ST": "Statistical Finance",
        "q-fin.TR": "Trading and Market Microstructure",
        
        # 统计学 (Statistics)
        "stat.AP": "Applications",
        "stat.CO": "Computation",
        "stat.ML": "Machine Learning",
        "stat.ME": "Methodology",
        "stat.OT": "Other Statistics",
        "stat.TH": "Statistics Theory",
    }
    
    # 按学科领域分组的分类
    CATEGORY_GROUPS = {
        "computer_science": [
            "cs.AI", "cs.CL", "cs.LG", "cs.CV", "cs.IR", "cs.SE", "cs.NE",
            "cs.RO", "cs.HC", "cs.CR", "cs.DB", "cs.DC", "cs.NI", "cs.SI",
            "cs.MA", "cs.GT", "cs.PL", "cs.DS", "cs.CC", "cs.LO"
        ],
        "machine_learning": [
            "cs.LG", "cs.AI", "cs.CL", "cs.CV", "cs.NE", "stat.ML"
        ],
        "nlp": [
            "cs.CL", "cs.AI", "cs.IR", "cs.LG"
        ],
        "computer_vision": [
            "cs.CV", "cs.LG", "cs.AI", "eess.IV"
        ],
        "physics": [
            "physics.comp-ph", "physics.data-an", "quant-ph", "cond-mat",
            "hep-th", "hep-ph", "gr-qc", "astro-ph"
        ],
        "mathematics": [
            "math.OC", "math.ST", "math.PR", "math.NA", "math.CO", "math.LO"
        ],
        "biology": [
            "q-bio.BM", "q-bio.GN", "q-bio.NC", "q-bio.QM", "q-bio.CB"
        ],
        "finance": [
            "q-fin.CP", "q-fin.ST", "q-fin.RM", "q-fin.MF", "econ.EM"
        ],
        "statistics": [
            "stat.ML", "stat.ME", "stat.AP", "stat.CO", "stat.TH"
        ],
        "electrical_engineering": [
            "eess.SP", "eess.IV", "eess.AS", "eess.SY"
        ],
    }
    
    # 默认分类（用于 LLM 无法判断时）
    DEFAULT_CATEGORIES = ["cs.AI", "cs.LG", "cs.CL"]
    
    def __init__(self, rate_limit_delay: float = 3.0):
        """
        初始化 arXiv 搜索器
        
        Args:
            rate_limit_delay: API 调用间隔（秒），arXiv 建议至少 3 秒
        """
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0
    
    async def search(
        self,
        query: str,
        max_results: int = 100,
        categories: Optional[List[str]] = None,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        sort_by: str = "relevance",  # relevance, lastUpdatedDate, submittedDate
        sort_order: str = "descending"
    ) -> List[PaperData]:
        """
        搜索 arXiv 论文
        
        Args:
            query: 搜索查询
            max_results: 最大结果数
            categories: 限制的分类列表
            year_start: 起始年份
            year_end: 结束年份
            sort_by: 排序方式
            sort_order: 排序顺序
            
        Returns:
            论文列表
        """
        papers = []
        
        # 构建搜索查询
        search_query = self._build_query(query, categories)
        
        # 分批获取（arXiv 每次最多返回 2000 条）
        batch_size = min(100, max_results)
        start = 0
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            while len(papers) < max_results:
                # 速率限制
                await self._rate_limit()
                
                params = {
                    "search_query": search_query,
                    "start": start,
                    "max_results": batch_size,
                    "sortBy": sort_by,
                    "sortOrder": sort_order
                }
                
                try:
                    logger.info(f"arXiv 搜索: {query} (start={start}, batch={batch_size})")
                    response = await client.get(self.BASE_URL, params=params)
                    response.raise_for_status()
                    
                    batch_papers = self._parse_response(response.text)
                    
                    if not batch_papers:
                        break
                    
                    # 过滤年份
                    if year_start or year_end:
                        batch_papers = [
                            p for p in batch_papers
                            if self._filter_by_year(p, year_start, year_end)
                        ]
                    
                    papers.extend(batch_papers)
                    start += batch_size
                    
                    logger.info(f"   获取 {len(batch_papers)} 篇，累计 {len(papers)} 篇")
                    
                    # 如果返回数量少于请求数量，说明没有更多结果
                    if len(batch_papers) < batch_size:
                        break
                        
                except Exception as e:
                    logger.error(f"arXiv 搜索失败: {e}")
                    break
        
        return papers[:max_results]
    
    async def search_surveys(
        self,
        topic: str,
        max_results: int = 20,
        year_start: Optional[int] = None
    ) -> List[PaperData]:
        """
        搜索 survey/review 论文
        
        Args:
            topic: 研究主题
            max_results: 最大结果数
            year_start: 起始年份
            
        Returns:
            survey 论文列表
        """
        # 构建 survey 搜索查询
        survey_queries = [
            f'ti:"{topic}" AND (ti:survey OR ti:review OR ti:overview)',
            f'abs:"{topic}" AND (ti:survey OR ti:review)',
            f'{topic} survey',
            f'{topic} review'
        ]
        
        all_surveys = []
        seen_ids = set()
        
        for query in survey_queries:
            if len(all_surveys) >= max_results:
                break
                
            papers = await self.search(
                query=query,
                max_results=max_results - len(all_surveys),
                year_start=year_start,
                sort_by="relevance"
            )
            
            for paper in papers:
                # 验证是否真的是 survey
                if self._is_survey_paper(paper) and paper.paper_id not in seen_ids:
                    paper.is_survey = True
                    all_surveys.append(paper)
                    seen_ids.add(paper.paper_id)
        
        # 按引用数排序（如果有的话）
        all_surveys.sort(key=lambda x: x.citations, reverse=True)
        
        return all_surveys[:max_results]
    
    def _build_query(self, query: str, categories: Optional[List[str]] = None) -> str:
        """
        构建 arXiv 查询字符串
        
        使用更宽松的搜索策略：
        1. 对于短查询（1-2个词），使用精确匹配
        2. 对于长查询，拆分为多个词并使用 AND 连接
        3. 同时搜索标题和摘要
        """
        words = query.split()
        
        if len(words) <= 2:
            # 短查询：使用精确短语匹配
            base_query = f'all:"{query}"'
        else:
            # 长查询：拆分词组，使用 AND 连接核心词
            # 提取核心词（去除常见停用词）
            stopwords = {'a', 'an', 'the', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or', 'with', 'by'}
            core_words = [w for w in words if w.lower() not in stopwords]
            
            if len(core_words) >= 3:
                # 对于长短语，使用两种策略组合：
                # 1. 精确短语匹配（权重高但结果少）
                # 2. 核心词 AND 匹配（结果多但可能不精确）
                exact_query = f'all:"{query}"'
                
                # 构建核心词查询：每个词在标题或摘要中出现
                word_queries = []
                for word in core_words[:4]:  # 最多取4个核心词
                    word_queries.append(f'(ti:{word} OR abs:{word})')
                and_query = " AND ".join(word_queries)
                
                # 组合：精确匹配 OR 核心词匹配
                base_query = f'({exact_query}) OR ({and_query})'
            else:
                # 核心词较少，直接使用 AND 连接
                word_queries = [f'(ti:{w} OR abs:{w})' for w in core_words]
                base_query = " AND ".join(word_queries)
        
        # 添加分类过滤
        if categories:
            cat_query = " OR ".join([f"cat:{cat}" for cat in categories])
            return f"({base_query}) AND ({cat_query})"
        
        return base_query
    
    def _parse_response(self, xml_text: str) -> List[PaperData]:
        """解析 arXiv API 响应"""
        papers = []
        
        try:
            root = ET.fromstring(xml_text)
            ns = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
            for entry in root.findall('atom:entry', ns):
                paper = self._parse_entry(entry, ns)
                if paper:
                    papers.append(paper)
                    
        except ET.ParseError as e:
            logger.error(f"XML 解析错误: {e}")
        
        return papers
    
    def _parse_entry(self, entry: ET.Element, ns: Dict[str, str]) -> Optional[PaperData]:
        """解析单个论文条目"""
        try:
            # 提取 arXiv ID
            id_elem = entry.find('atom:id', ns)
            if id_elem is None:
                return None
            
            arxiv_url = id_elem.text
            arxiv_id = arxiv_url.split('/')[-1]
            # 移除版本号
            arxiv_id_base = arxiv_id.split('v')[0]
            
            # 提取标题
            title_elem = entry.find('atom:title', ns)
            title = title_elem.text.replace('\n', ' ').strip() if title_elem is not None else ""
            
            # 提取摘要
            summary_elem = entry.find('atom:summary', ns)
            abstract = summary_elem.text.replace('\n', ' ').strip() if summary_elem is not None else ""
            
            # 提取作者
            authors = []
            for author_elem in entry.findall('atom:author', ns):
                name_elem = author_elem.find('atom:name', ns)
                if name_elem is not None:
                    authors.append(name_elem.text)
            
            # 提取发布日期
            published_elem = entry.find('atom:published', ns)
            year = None
            if published_elem is not None:
                try:
                    year = int(published_elem.text[:4])
                except:
                    pass
            
            # 提取 PDF 链接
            pdf_url = None
            for link in entry.findall('atom:link', ns):
                if link.attrib.get('title') == 'pdf':
                    pdf_url = link.attrib.get('href')
                    if pdf_url and pdf_url.startswith("http://"):
                        pdf_url = pdf_url.replace("http://", "https://")
                    break
            
            # 提取分类
            categories = []
            for cat in entry.findall('arxiv:primary_category', ns):
                categories.append(cat.attrib.get('term', ''))
            for cat in entry.findall('atom:category', ns):
                categories.append(cat.attrib.get('term', ''))
            
            # 提取 DOI（如果有）
            doi = None
            doi_elem = entry.find('arxiv:doi', ns)
            if doi_elem is not None:
                doi = doi_elem.text
            
            return PaperData(
                paper_id=f"arXiv:{arxiv_id_base}",
                title=title,
                abstract=abstract,
                authors=authors,
                year=year,
                venue="arXiv",
                pdf_url=pdf_url,
                doi=doi,
                arxiv_id=arxiv_id_base,
                source="arxiv"
            )
            
        except Exception as e:
            logger.debug(f"解析 arXiv 条目失败: {e}")
            return None
    
    def _filter_by_year(self, paper: PaperData, year_start: Optional[int], year_end: Optional[int]) -> bool:
        """按年份过滤"""
        if paper.year is None:
            return True
        if year_start and paper.year < year_start:
            return False
        if year_end and paper.year > year_end:
            return False
        return True
    
    def _is_survey_paper(self, paper: PaperData) -> bool:
        """判断是否为 survey 论文"""
        title_lower = paper.title.lower()
        survey_keywords = ['survey', 'review', 'overview', 'tutorial', 'comprehensive study']
        return any(kw in title_lower for kw in survey_keywords)
    
    async def _rate_limit(self):
        """速率限制"""
        current_time = asyncio.get_event_loop().time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = asyncio.get_event_loop().time()


class SemanticScholarClient:
    """
    Semantic Scholar API 客户端
    
    用于获取论文的参考文献列表和引用信息
    """
    
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    
    def __init__(self, api_key: Optional[str] = None, rate_limit_delay: float = 1.0):
        """
        初始化 Semantic Scholar 客户端
        
        Args:
            api_key: API Key（可选，免费版有限制）
            rate_limit_delay: API 调用间隔（秒）
        """
        self.api_key = api_key
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0
        
        self.headers = {}
        if api_key:
            self.headers["x-api-key"] = api_key
    
    async def search_papers(
        self,
        query: str,
        max_results: int = 100,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        fields: Optional[List[str]] = None
    ) -> List[PaperData]:
        """
        搜索论文
        
        Args:
            query: 搜索查询
            max_results: 最大结果数
            year_start: 起始年份
            year_end: 结束年份
            fields: 返回的字段列表
            
        Returns:
            论文列表
        """
        if fields is None:
            fields = [
                "paperId", "title", "abstract", "authors", "year",
                "venue", "citationCount", "references", "externalIds"
            ]
        
        papers = []
        offset = 0
        limit = min(100, max_results)  # S2 每次最多 100 条
        
        async with httpx.AsyncClient(timeout=30.0, headers=self.headers) as client:
            while len(papers) < max_results:
                await self._rate_limit()
                
                params = {
                    "query": query,
                    "offset": offset,
                    "limit": limit,
                    "fields": ",".join(fields)
                }
                
                # 添加年份过滤
                if year_start or year_end:
                    year_filter = ""
                    if year_start:
                        year_filter = f"{year_start}-"
                    if year_end:
                        year_filter += str(year_end)
                    elif year_start:
                        year_filter += str(datetime.now().year)
                    params["year"] = year_filter
                
                try:
                    response = await client.get(
                        f"{self.BASE_URL}/paper/search",
                        params=params
                    )
                    
                    if response.status_code == 429:
                        logger.warning("Semantic Scholar 速率限制，等待后重试...")
                        await asyncio.sleep(60)
                        continue
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    batch_papers = [
                        self._parse_paper(p) for p in data.get("data", [])
                        if p.get("title")
                    ]
                    
                    if not batch_papers:
                        break
                    
                    papers.extend(batch_papers)
                    offset += limit
                    
                    # 检查是否还有更多结果
                    total = data.get("total", 0)
                    if offset >= total:
                        break
                        
                except Exception as e:
                    logger.error(f"Semantic Scholar 搜索失败: {e}")
                    break
        
        return papers[:max_results]
    
    async def get_paper_references(
        self,
        paper_id: str,
        max_refs: int = 100
    ) -> List[PaperData]:
        """
        获取论文的参考文献列表
        
        Args:
            paper_id: 论文 ID（可以是 S2 ID、DOI、arXiv ID 等）
            max_refs: 最大参考文献数
            
        Returns:
            参考文献列表
        """
        references = []
        offset = 0
        limit = min(100, max_refs)
        
        # 转换 ID 格式
        s2_id = self._convert_to_s2_id(paper_id)
        
        fields = [
            "paperId", "title", "abstract", "authors", "year",
            "venue", "citationCount", "externalIds"
        ]
        
        async with httpx.AsyncClient(timeout=30.0, headers=self.headers) as client:
            while len(references) < max_refs:
                await self._rate_limit()
                
                params = {
                    "offset": offset,
                    "limit": limit,
                    "fields": ",".join(fields)
                }
                
                try:
                    response = await client.get(
                        f"{self.BASE_URL}/paper/{s2_id}/references",
                        params=params
                    )
                    
                    if response.status_code == 404:
                        logger.warning(f"论文未找到: {paper_id}")
                        break
                    
                    if response.status_code == 429:
                        logger.warning("Semantic Scholar 速率限制，等待后重试...")
                        await asyncio.sleep(60)
                        continue
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    batch_refs = []
                    for ref_data in data.get("data", []):
                        cited_paper = ref_data.get("citedPaper", {})
                        if cited_paper and cited_paper.get("title"):
                            paper = self._parse_paper(cited_paper)
                            batch_refs.append(paper)
                    
                    if not batch_refs:
                        break
                    
                    references.extend(batch_refs)
                    offset += limit
                    
                except Exception as e:
                    logger.error(f"获取参考文献失败: {e}")
                    break
        
        return references[:max_refs]
    
    async def get_paper_by_id(self, paper_id: str) -> Optional[PaperData]:
        """
        通过 ID 获取论文详情
        
        Args:
            paper_id: 论文 ID
            
        Returns:
            论文数据
        """
        s2_id = self._convert_to_s2_id(paper_id)
        
        fields = [
            "paperId", "title", "abstract", "authors", "year",
            "venue", "citationCount", "references", "externalIds"
        ]
        
        async with httpx.AsyncClient(timeout=30.0, headers=self.headers) as client:
            await self._rate_limit()
            
            try:
                response = await client.get(
                    f"{self.BASE_URL}/paper/{s2_id}",
                    params={"fields": ",".join(fields)}
                )
                
                if response.status_code == 404:
                    return None
                
                response.raise_for_status()
                data = response.json()
                
                return self._parse_paper(data)
                
            except Exception as e:
                logger.error(f"获取论文详情失败: {e}")
                return None
    
    def _parse_paper(self, data: Dict) -> PaperData:
        """解析 Semantic Scholar 论文数据"""
        # 提取作者
        authors = []
        for author in data.get("authors", []):
            if author.get("name"):
                authors.append(author["name"])
        
        # 提取外部 ID
        external_ids = data.get("externalIds", {}) or {}
        arxiv_id = external_ids.get("ArXiv")
        doi = external_ids.get("DOI")
        
        # 生成统一 ID
        paper_id = data.get("paperId", "")
        if arxiv_id:
            paper_id = f"arXiv:{arxiv_id}"
        elif doi:
            paper_id = f"DOI:{doi}"
        elif paper_id:
            paper_id = f"S2:{paper_id}"
        
        # 提取参考文献 ID
        referenced_works = []
        for ref in data.get("references", []) or []:
            if isinstance(ref, dict) and ref.get("paperId"):
                referenced_works.append(f"S2:{ref['paperId']}")
            elif isinstance(ref, str):
                referenced_works.append(ref)
        
        return PaperData(
            paper_id=paper_id,
            title=data.get("title", ""),
            abstract=data.get("abstract", "") or "",
            authors=authors,
            year=data.get("year"),
            venue=data.get("venue", "") or "",
            citations=data.get("citationCount", 0) or 0,
            referenced_works=referenced_works,
            doi=doi,
            arxiv_id=arxiv_id,
            source="semantic_scholar"
        )
    
    def _convert_to_s2_id(self, paper_id: str) -> str:
        """转换为 Semantic Scholar ID 格式"""
        if paper_id.startswith("arXiv:"):
            return f"ARXIV:{paper_id[6:]}"
        elif paper_id.startswith("DOI:"):
            return f"DOI:{paper_id[4:]}"
        elif paper_id.startswith("S2:"):
            return paper_id[3:]
        elif paper_id.startswith("10."):  # DOI
            return f"DOI:{paper_id}"
        else:
            return paper_id
    
    async def _rate_limit(self):
        """速率限制"""
        current_time = asyncio.get_event_loop().time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = asyncio.get_event_loop().time()


class OpenAlexClient:
    """
    OpenAlex API 客户端（备用数据源）
    """
    
    BASE_URL = "https://api.openalex.org"
    
    def __init__(self, email: str = "surveygraph@example.com", rate_limit_delay: float = 0.1):
        self.email = email
        self.rate_limit_delay = rate_limit_delay
        self.headers = {"User-Agent": f"SurveyGraph/1.0 (mailto:{email})"}
    
    async def search_papers(
        self,
        query: str,
        max_results: int = 100,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        min_citations: int = 0
    ) -> List[PaperData]:
        """搜索论文"""
        papers = []
        cursor = "*"
        per_page = min(200, max_results)
        
        async with httpx.AsyncClient(timeout=30.0, headers=self.headers) as client:
            while len(papers) < max_results:
                # 构建过滤器
                filters = []
                if year_start and year_end:
                    filters.append(f"publication_year:{year_start}-{year_end}")
                elif year_start:
                    filters.append(f"publication_year:>{year_start-1}")
                if min_citations > 0:
                    filters.append(f"cited_by_count:>{min_citations}")
                
                params = {
                    "search": query,
                    "per_page": per_page,
                    "cursor": cursor,
                    "mailto": self.email
                }
                
                if filters:
                    params["filter"] = ",".join(filters)
                
                try:
                    response = await client.get(f"{self.BASE_URL}/works", params=params)
                    
                    if response.status_code != 200:
                        logger.warning(f"OpenAlex API 错误: {response.status_code}")
                        break
                    
                    data = response.json()
                    results = data.get("results", [])
                    
                    if not results:
                        break
                    
                    for work in results:
                        paper = self._parse_work(work)
                        if paper:
                            papers.append(paper)
                    
                    # 获取下一页游标
                    meta = data.get("meta", {})
                    cursor = meta.get("next_cursor")
                    if not cursor:
                        break
                    
                    await asyncio.sleep(self.rate_limit_delay)
                    
                except Exception as e:
                    logger.error(f"OpenAlex 搜索失败: {e}")
                    break
        
        return papers[:max_results]
    
    async def get_paper_by_arxiv_id(self, arxiv_id: str) -> Optional[PaperData]:
        """通过 arXiv ID 获取 OpenAlex 论文数据"""
        async with httpx.AsyncClient(timeout=30.0, headers=self.headers) as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/works/https://arxiv.org/abs/{arxiv_id}",
                    params={"mailto": self.email}
                )
                
                if response.status_code == 200:
                    return self._parse_work(response.json())
                    
            except Exception as e:
                logger.debug(f"OpenAlex 查询失败: {e}")
        
        return None
    
    def _parse_work(self, work: Dict) -> Optional[PaperData]:
        """解析 OpenAlex 论文数据"""
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
            
            # 提取 venue
            venue = ""
            source = primary_location.get("source", {}) or {}
            if source.get("display_name"):
                venue = source["display_name"]
            
            # 提取 arXiv ID
            arxiv_id = None
            ids = work.get("ids", {}) or {}
            if ids.get("arxiv"):
                arxiv_id = ids["arxiv"].replace("https://arxiv.org/abs/", "")
            
            return PaperData(
                paper_id=paper_id,
                title=work.get("title", ""),
                abstract=abstract,
                authors=authors,
                year=work.get("publication_year"),
                venue=venue,
                citations=work.get("cited_by_count", 0),
                referenced_works=referenced_works,
                pdf_url=pdf_url,
                doi=work.get("doi"),
                arxiv_id=arxiv_id,
                openalex_id=openalex_id,
                source="openalex"
            )
            
        except Exception as e:
            logger.debug(f"解析 OpenAlex 论文失败: {e}")
            return None
    
    def _reconstruct_abstract(self, inverted_index: Optional[Dict]) -> str:
        """从倒排索引重建摘要"""
        if not inverted_index:
            return ""
        
        try:
            max_pos = 0
            for positions in inverted_index.values():
                if positions:
                    max_pos = max(max_pos, max(positions))
            
            words = [""] * (max_pos + 1)
            for word, positions in inverted_index.items():
                for pos in positions:
                    if pos <= max_pos:
                        words[pos] = word
            
            return " ".join(words)
        except Exception:
            return ""


class EmbeddingFilter:
    """
    基于 Embedding 的论文相关性过滤器
    
    使用 sentence-transformers 计算论文与主题的语义相似度
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        初始化 Embedding 过滤器
        
        Args:
            model_name: sentence-transformers 模型名称
        """
        self.model = None
        self.model_name = model_name
        
        if HAS_EMBEDDING:
            try:
                logger.info(f"加载 Embedding 模型: {model_name}")
                self.model = SentenceTransformer(model_name)
            except Exception as e:
                logger.warning(f"加载 Embedding 模型失败: {e}")
    
    def filter_papers(
        self,
        papers: List[PaperData],
        topic: str,
        threshold: float = 0.3,
        top_k: Optional[int] = None
    ) -> Tuple[List[PaperData], List[PaperData]]:
        """
        使用 Embedding 过滤论文
        
        Args:
            papers: 论文列表
            topic: 研究主题
            threshold: 相似度阈值
            top_k: 只保留 top_k 篇（可选）
            
        Returns:
            (相关论文, 不相关论文)
        """
        if not self.model or not papers:
            return papers, []
        
        # 计算主题 embedding
        topic_embedding = self.model.encode(topic, convert_to_numpy=True)
        
        # 计算每篇论文的 embedding 和相似度
        paper_scores = []
        for paper in tqdm(papers, desc="Embedding 筛选"):
            text = f"{paper.title}. {paper.abstract[:500]}"
            paper_embedding = self.model.encode(text, convert_to_numpy=True)
            
            # 计算余弦相似度
            similarity = np.dot(topic_embedding, paper_embedding) / (
                np.linalg.norm(topic_embedding) * np.linalg.norm(paper_embedding)
            )
            
            paper.relevance_score = float(similarity)
            paper_scores.append((paper, similarity))
        
        # 按相似度排序
        paper_scores.sort(key=lambda x: x[1], reverse=True)
        
        # 过滤
        if top_k:
            relevant = [p for p, s in paper_scores[:top_k]]
            irrelevant = [p for p, s in paper_scores[top_k:]]
        else:
            relevant = [p for p, s in paper_scores if s >= threshold]
            irrelevant = [p for p, s in paper_scores if s < threshold]
        
        logger.info(f"Embedding 筛选: {len(relevant)} 相关, {len(irrelevant)} 不相关")
        
        return relevant, irrelevant


class LLMRelevanceFilter:
    """
    基于 LLM 的论文相关性精筛器
    """
    
    RELEVANCE_PROMPT = """判断以下论文是否与研究主题"{topic}"高度相关。

论文标题: {title}
论文摘要: {abstract}

判断标准：
1. 论文是否直接研究该主题的核心问题
2. 论文的方法/技术是否与该主题直接相关
3. 论文是否可以作为该主题综述的重要参考文献

输出JSON格式：
{{"relevant": true/false, "score": 0.0-1.0, "reason": "简短理由"}}

只输出JSON，不要其他内容。"""

    def __init__(self, chat_agent=None, max_workers: int = None, model: str = None):
        """
        初始化 LLM 过滤器
        
        Args:
            chat_agent: ChatAgent 实例
            max_workers: 并发数（默认从 config.RELEVANCE_FILTER_WORKERS 读取）
            model: 使用的模型名称
        """
        self.chat_agent = chat_agent
        self.max_workers = max_workers if max_workers is not None else RELEVANCE_FILTER_WORKERS
        self.model = model
        
        if self.chat_agent is None and HAS_CHAT_AGENT:
            try:
                self.chat_agent = ChatAgent()
            except:
                pass
    
    def filter_papers(
        self,
        papers: List[PaperData],
        topic: str,
        threshold: float = 0.5
    ) -> Tuple[List[PaperData], List[PaperData]]:
        """
        使用 LLM 过滤论文
        
        Args:
            papers: 论文列表
            topic: 研究主题
            threshold: 相关性阈值
            
        Returns:
            (相关论文, 不相关论文)
        """
        if not self.chat_agent or not papers:
            return papers, []
        
        relevant = []
        irrelevant = []
        
        def check_single(paper: PaperData) -> Tuple[PaperData, bool, float]:
            try:
                prompt = self.RELEVANCE_PROMPT.format(
                    topic=topic,
                    title=paper.title,
                    abstract=paper.abstract[:500]
                )
                
                kwargs = {"temperature": 0.1, "timeout": 30}
                if self.model:
                    kwargs["model"] = self.model
                
                response = self.chat_agent.remote_chat(prompt, **kwargs)
                
                # 解析响应
                match = re.search(r'\{[^{}]*\}', response)
                if match:
                    data = json.loads(match.group())
                    is_relevant = data.get("relevant", True)
                    score = float(data.get("score", 0.5))
                    paper.relevance_score = max(paper.relevance_score, score)
                    return paper, is_relevant and score >= threshold, score
                
                return paper, True, 0.5  # 解析失败默认保留
                
            except Exception as e:
                logger.debug(f"LLM 过滤失败: {e}")
                return paper, True, 0.5
        
        # 并发处理
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(check_single, p): p for p in papers}
            
            for future in tqdm(as_completed(futures), total=len(futures), desc="LLM 精筛"):
                try:
                    paper, is_relevant, score = future.result()
                    if is_relevant:
                        relevant.append(paper)
                    else:
                        irrelevant.append(paper)
                except Exception as e:
                    paper = futures[future]
                    relevant.append(paper)  # 出错默认保留
        
        logger.info(f"LLM 精筛: {len(relevant)} 相关, {len(irrelevant)} 不相关")
        
        return relevant, irrelevant


class EnhancedPaperCollector:
    """
    增强版论文收集器
    
    整合多数据源搜索、Survey 策略、智能筛选
    支持自动判断 arXiv 分类，适用于各学科领域
    """
    
    # arXiv 分类判断 Prompt
    CATEGORY_DETECTION_PROMPT = """你是一个学术分类专家。请根据研究主题判断最适合在 arXiv 上搜索的分类。

研究主题: {topic}

arXiv 主要分类包括：
- 计算机科学 (cs.*): cs.AI(人工智能), cs.CL(计算语言学/NLP), cs.LG(机器学习), cs.CV(计算机视觉), cs.IR(信息检索), cs.SE(软件工程), cs.RO(机器人), cs.CR(密码学), cs.DB(数据库), cs.NI(网络), cs.HC(人机交互), cs.DC(分布式计算), cs.PL(编程语言), cs.NE(神经进化计算)
- 统计学 (stat.*): stat.ML(机器学习), stat.ME(方法论), stat.AP(应用), stat.TH(理论)
- 数学 (math.*): math.OC(优化控制), math.ST(统计理论), math.PR(概率), math.NA(数值分析), math.CO(组合数学)
- 物理学: quant-ph(量子物理), cond-mat(凝聚态), hep-th(高能理论), astro-ph(天体物理), physics.*(各物理子领域)
- 定量生物学 (q-bio.*): q-bio.NC(神经认知), q-bio.GN(基因组学), q-bio.BM(生物分子)
- 定量金融 (q-fin.*): q-fin.ST(统计金融), q-fin.CP(计算金融), q-fin.RM(风险管理)
- 电气工程 (eess.*): eess.SP(信号处理), eess.IV(图像视频), eess.AS(音频语音)
- 经济学 (econ.*): econ.EM(计量经济学), econ.TH(理论经济学)

请选择 3-6 个最相关的 arXiv 分类代码。

输出格式（JSON）:
{{
  "categories": ["分类1", "分类2", ...],
  "primary_field": "主要学科领域（如 computer_science, physics, mathematics, biology, finance 等）",
  "reason": "简短理由"
}}

示例:
- 输入: "Large Language Model Function Calling"
  输出: {{"categories": ["cs.CL", "cs.AI", "cs.LG", "cs.SE"], "primary_field": "computer_science", "reason": "LLM和Function Calling属于NLP和AI领域"}}

- 输入: "Quantum Machine Learning"
  输出: {{"categories": ["quant-ph", "cs.LG", "cs.AI", "physics.comp-ph"], "primary_field": "physics", "reason": "量子机器学习跨越量子物理和机器学习"}}

- 输入: "Protein Structure Prediction"
  输出: {{"categories": ["q-bio.BM", "cs.LG", "q-bio.QM", "physics.bio-ph"], "primary_field": "biology", "reason": "蛋白质结构预测属于计算生物学"}}

只输出JSON，不要其他内容。"""

    KEYWORD_SPLIT_PROMPT = """你是一个 arXiv 论文搜索专家。请为以下研究主题生成有效的搜索关键词，并为每个关键词分配重要性权重。

研究主题: {topic}

**重要**：生成的关键词必须是 arXiv 上实际存在的论文会使用的术语。
- 使用简短、常见的术语（2-4个词最佳）
- 避免过于学术化或生僻的表达
- 包含该领域的常用缩写和变体
- **为每个关键词分配权重（0.0-1.0），权重之和应为1.0，权重越高表示该关键词越核心/重要**

请生成 5-8 个搜索关键词，确保：
1. 包含原始主题的核心概念（权重最高）
2. 包含同义词或常见变体（权重次之）
3. 包含相关的具体技术或方法名称（权重较低）
4. 关键词要简洁，便于搜索匹配

输出格式（JSON）:
{{
  "need_split": true,
  "reason": "简短理由",
  "keywords": [
    {{"keyword": "关键词1", "weight": 0.25}},
    {{"keyword": "关键词2", "weight": 0.20}},
    {{"keyword": "关键词3", "weight": 0.15}},
    ...
  ]
}}

示例:
- 输入: "Large Language Model Function Calling"
  输出: {{
    "need_split": true,
    "reason": "需要覆盖不同的术语表达",
    "keywords": [
      {{"keyword": "LLM function calling", "weight": 0.25}},
      {{"keyword": "LLM tool use", "weight": 0.20}},
      {{"keyword": "tool learning LLM", "weight": 0.15}},
      {{"keyword": "language model API", "weight": 0.12}},
      {{"keyword": "LLM agent tool", "weight": 0.10}},
      {{"keyword": "ReAct LLM", "weight": 0.08}},
      {{"keyword": "Toolformer", "weight": 0.06}},
      {{"keyword": "GPT function call", "weight": 0.04}}
    ]
  }}

只输出JSON，不要其他内容。"""

    def __init__(
        self,
        chat_agent=None,
        semantic_scholar_api_key: Optional[str] = None,
        openalex_email: str = "surveygraph@example.com"
    ):
        """
        初始化收集器
        
        Args:
            chat_agent: ChatAgent 实例
            semantic_scholar_api_key: Semantic Scholar API Key
            openalex_email: OpenAlex 邮箱
        """
        self.chat_agent = chat_agent
        self.disable_keyword_split = self._env_flag("SURVEYGRAPH_DISABLE_KEYWORD_SPLIT")
        self.disable_keyword_variants = self._env_flag("SURVEYGRAPH_DISABLE_KEYWORD_VARIANTS")

        if self.chat_agent is None and HAS_CHAT_AGENT:
            try:
                self.chat_agent = ChatAgent()
            except:
                pass
        
        # 初始化各数据源客户端
        self.arxiv = ArxivSearcher()
        self.semantic_scholar = SemanticScholarClient(api_key=semantic_scholar_api_key)
        self.openalex = OpenAlexClient(email=openalex_email)
        
        # 初始化过滤器
        self.embedding_filter = EmbeddingFilter() if HAS_EMBEDDING else None
        self.llm_filter = LLMRelevanceFilter(chat_agent=self.chat_agent)

    @staticmethod
    def _env_flag(name: str) -> bool:
        value = os.getenv(name, "")
        return value.strip().lower() in {"1", "true", "yes", "on"}
    
    def detect_arxiv_categories(self, topic: str) -> Tuple[List[str], str]:
        """
        使用 LLM 自动判断研究主题对应的 arXiv 分类
        
        Args:
            topic: 研究主题
            
        Returns:
            (分类列表, 主要学科领域)
        """
        if not self.chat_agent:
            logger.warning("ChatAgent 不可用，使用默认分类 (cs.AI, cs.LG, cs.CL)")
            return ArxivSearcher.DEFAULT_CATEGORIES, "computer_science"
        
        try:
            prompt = self.CATEGORY_DETECTION_PROMPT.format(topic=topic)
            response = self.chat_agent.remote_chat(prompt, temperature=0.3)
            
            # 提取 JSON
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                result = json.loads(match.group())
                categories = result.get("categories", ArxivSearcher.DEFAULT_CATEGORIES)
                primary_field = result.get("primary_field", "computer_science")
                reason = result.get("reason", "N/A")
                
                # 验证分类是否有效
                valid_categories = []
                for cat in categories:
                    if cat in ArxivSearcher.ALL_CATEGORIES:
                        valid_categories.append(cat)
                    else:
                        # 尝试模糊匹配
                        for valid_cat in ArxivSearcher.ALL_CATEGORIES:
                            if cat.lower() in valid_cat.lower() or valid_cat.lower() in cat.lower():
                                valid_categories.append(valid_cat)
                                break
                
                if not valid_categories:
                    logger.warning(f"LLM 返回的分类无效: {categories}，使用默认分类")
                    valid_categories = ArxivSearcher.DEFAULT_CATEGORIES
                
                logger.info(f"🏷️ LLM 判断 arXiv 分类: {valid_categories}")
                logger.info(f"   主要领域: {primary_field}")
                logger.info(f"   理由: {reason}")
                
                return valid_categories, primary_field
            else:
                logger.warning("LLM 响应解析失败，使用默认分类")
                return ArxivSearcher.DEFAULT_CATEGORIES, "computer_science"
                
        except Exception as e:
            logger.warning(f"LLM 分类判断失败: {e}，使用默认分类")
            return ArxivSearcher.DEFAULT_CATEGORIES, "computer_science"
    
    def split_keywords_with_llm(self, topic: str) -> List[Dict[str, any]]:
        """
        使用LLM判断是否需要拆分关键词，并返回带权重的关键词列表
        
        Args:
            topic: 研究主题
            
        Returns:
            带权重的关键词列表，格式: [{"keyword": str, "weight": float}, ...]
            如果不需要拆分，返回原始主题（权重为1.0）
        """
        if self.disable_keyword_split:
            logger.info("检测到 SURVEYGRAPH_DISABLE_KEYWORD_SPLIT，使用原始关键词")
            return [{"keyword": topic, "weight": 1.0}]

        if not self.chat_agent:
            logger.warning(f"ChatAgent不可用，使用原始关键词")
            return [{"keyword": topic, "weight": 1.0}]
        
        try:
            prompt = self.KEYWORD_SPLIT_PROMPT.format(topic=topic)
            response = self.chat_agent.remote_chat(prompt, temperature=0.3)
            
            # 提取JSON
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                result = json.loads(match.group())
                
                keywords_data = result.get("keywords", [])
                
                # 兼容旧格式（纯字符串列表）和新格式（带权重的字典列表）
                if keywords_data and isinstance(keywords_data[0], str):
                    # 旧格式：平均分配权重
                    weight = 1.0 / len(keywords_data)
                    keywords_data = [{"keyword": kw, "weight": weight} for kw in keywords_data]
                elif keywords_data and isinstance(keywords_data[0], dict):
                    # 新格式：确保权重归一化
                    total_weight = sum(kw.get("weight", 0) for kw in keywords_data)
                    if total_weight > 0:
                        for kw in keywords_data:
                            kw["weight"] = kw.get("weight", 0) / total_weight
                    else:
                        # 如果权重都是0，平均分配
                        weight = 1.0 / len(keywords_data)
                        for kw in keywords_data:
                            kw["weight"] = weight
                
                if result.get("need_split", False) and keywords_data:
                    # 按权重排序（高权重在前）
                    keywords_data = sorted(keywords_data, key=lambda x: x.get("weight", 0), reverse=True)
                    
                    # 提取关键词字符串用于日志
                    keyword_strs = [kw["keyword"] for kw in keywords_data]
                    logger.info(f"🤖 LLM建议拆分关键词: {keyword_strs}")
                    logger.info(f"   理由: {result.get('reason', 'N/A')}")
                    
                    # 显示权重分配
                    for kw in keywords_data:
                        logger.debug(f"      - {kw['keyword']}: {kw['weight']:.1%}")
                    
                    return keywords_data
                else:
                    logger.info(f"🤖 LLM判断无需拆分: {result.get('reason', 'N/A')}")
                    return [{"keyword": topic, "weight": 1.0}]
            else:
                logger.warning(f"LLM响应解析失败，使用原始关键词")
                return [{"keyword": topic, "weight": 1.0}]
                
        except Exception as e:
            logger.warning(f"LLM关键词拆分失败: {e}，使用原始关键词")
            return [{"keyword": topic, "weight": 1.0}]

    async def collect_papers(
        self,
        topic: str,
        target_count: int = 100,
        year_start: int = 2020,
        year_end: Optional[int] = None,
        use_survey_strategy: bool = False,  # 默认关闭 Survey 策略，因为参考文献获取不稳定
        survey_count: int = 10,
        max_refs_per_survey: int = 50,
        use_embedding_filter: bool = True,
        use_llm_filter: bool = True,
        embedding_threshold: float = 0.3,
        llm_threshold: float = 0.5,
        use_openalex: bool = False,  # 默认关闭 OpenAlex，因为搜索结果相关性差且PDF难以下载
        download_pdf: bool = True,  # 默认开启 PDF 下载和解析
        pdf_output_dir: Optional[Path] = None,  # PDF 保存目录
        min_target_ratio: float = 0.9,  # 最小目标比例，默认 90%
        max_retry_rounds: int = 5  # 最大重试轮数
    ) -> List[Dict[str, Any]]:
        """
        收集论文（只使用 arXiv，确保收集到目标数量的 90%）
        
        Args:
            topic: 研究主题
            target_count: 目标论文数
            year_start: 起始年份
            year_end: 结束年份
            use_survey_strategy: 是否使用 Survey 优先策略（默认关闭，因为参考文献获取不稳定）
            survey_count: 搜索的 survey 数量
            max_refs_per_survey: 每篇 survey 最多获取的参考文献数
            use_embedding_filter: 是否使用 Embedding 筛选
            use_llm_filter: 是否使用 LLM 精筛
            embedding_threshold: Embedding 相似度阈值
            llm_threshold: LLM 相关性阈值
            min_target_ratio: 最小目标比例（默认 0.9，即 90%）
            max_retry_rounds: 最大重试轮数
            
        Returns:
            论文列表（字典格式）
        """
        if year_end is None:
            year_end = datetime.now().year
        
        min_required = int(target_count * min_target_ratio)
        
        all_papers: List[PaperData] = []
        seen_ids: Set[str] = set()
        used_keywords: Set[str] = set()  # 已使用的关键词
        
        logger.info(f"开始收集论文: topic={topic}, target={target_count}, min_required={min_required}")
        
        # 0. 自动判断 arXiv 分类
        arxiv_categories, primary_field = self.detect_arxiv_categories(topic)
        logger.info(f"📚 使用 arXiv 分类: {arxiv_categories} (领域: {primary_field})")
        
        # 0.1 关键词拆分（返回带权重的关键词列表）
        keywords_with_weights = self.split_keywords_with_llm(topic)
        # 提取关键词字符串列表（用于兼容后续代码）
        keywords = [kw["keyword"] for kw in keywords_with_weights]
        
        # ========== 阶段 1: Survey 优先策略（默认跳过，只使用 arXiv）==========
        if use_survey_strategy:
            logger.info("=" * 50)
            logger.info("阶段 1: Survey 优先策略 (仅 arXiv)")
            logger.info("=" * 50)
            
            # 1.1 搜索 survey 论文（只使用 arXiv）
            logger.info(f"1.1 搜索 survey 论文 (目标: {survey_count} 篇)...")
            surveys = await self._search_surveys_arxiv_only(topic, max_surveys=survey_count, year_start=year_start)
            
            for survey in surveys:
                if survey.paper_id not in seen_ids:
                    all_papers.append(survey)
                    seen_ids.add(survey.paper_id)
            
            logger.info(f"   找到 {len(surveys)} 篇 survey 论文")
        else:
            logger.info("=" * 50)
            logger.info("跳过 Survey 策略，直接使用关键词搜索")
            logger.info("=" * 50)
        
        # ========== 阶段 2: 直接搜索（只使用 arXiv）==========
        # 循环搜索直到达到目标数量的 90%
        retry_round = 0
        
        # 并行搜索配置
        # arXiv API 建议至少 3 秒间隔，但我们可以通过多个关键词并行搜索来提高效率
        # 使用信号量控制并发数，避免触发速率限制
        # 从 config 读取并发数，但 arXiv API 限制较严，建议不要设置太高
        max_concurrent_searches = min(PAPER_SEARCH_WORKERS, 10)  # 限制最大 10 并发以保护 arXiv API
        
        while retry_round < max_retry_rounds:
            retry_round += 1
            
            logger.info("=" * 50)
            logger.info(f"阶段 2: arXiv 并行搜索 (第 {retry_round} 轮)")
            logger.info("=" * 50)
            
            # 计算还需要多少论文（考虑筛选损耗，多搜索一些）
            current_count = len(all_papers)
            remaining = int(target_count * 2) - current_count  # 多搜索一些用于筛选
            
            if remaining <= 0:
                logger.info(f"已有足够论文 ({current_count} 篇)，跳过搜索")
                break
            
            # 获取本轮要使用的关键词
            current_keywords = [kw for kw in keywords if kw not in used_keywords]
            
            # 如果所有关键词都用过了，生成新的关键词变体
            if not current_keywords:
                if self.disable_keyword_variants:
                    logger.info("检测到 SURVEYGRAPH_DISABLE_KEYWORD_VARIANTS，停止新关键词扩展")
                    break
                logger.info("所有关键词已使用，生成新的关键词变体...")
                new_keywords = await self._generate_keyword_variants(topic, list(used_keywords))
                current_keywords = [kw for kw in new_keywords if kw not in used_keywords]
                
                if not current_keywords:
                    logger.warning("无法生成新的关键词变体，尝试放宽搜索条件...")
                    # 放宽年份限制
                    if year_start > 2015:
                        year_start -= 2
                        logger.info(f"放宽年份限制到 {year_start}")
                        # 重新使用原始关键词
                        current_keywords = keywords.copy()
                        used_keywords.clear()
                    else:
                        logger.warning("已达到最宽松的搜索条件，停止搜索")
                        break
            
            # 按权重分配配额
            # 获取当前关键词的权重信息
            keyword_weights = {}
            for kw_data in keywords_with_weights:
                keyword_weights[kw_data["keyword"]] = kw_data["weight"]
            
            # 计算当前关键词的总权重
            current_total_weight = sum(keyword_weights.get(kw, 0.1) for kw in current_keywords)
            
            min_quota = 30  # 最小配额
            
            # 准备并行搜索任务
            search_tasks = []
            keyword_quotas = []
            
            for kw in current_keywords:
                used_keywords.add(kw)
                
                # 按权重计算配额
                weight = keyword_weights.get(kw, 0.1)  # 默认权重0.1
                normalized_weight = weight / current_total_weight if current_total_weight > 0 else 1.0 / len(current_keywords)
                
                # 配额 = max(按权重分配的配额, 最小配额)
                quota_per_keyword = max(int(remaining * normalized_weight * 1.2), min_quota)  # 1.2倍冗余
                
                keyword_quotas.append((kw, weight, quota_per_keyword))
            
            logger.info(f"   🚀 并行搜索 {len(keyword_quotas)} 个关键词 (最大并发: {max_concurrent_searches})")
            
            # 使用信号量控制并发
            semaphore = asyncio.Semaphore(max_concurrent_searches)
            
            async def search_keyword(kw: str, quota: int) -> Tuple[str, List[PaperData]]:
                """搜索单个关键词"""
                async with semaphore:
                    try:
                        papers = await self.arxiv.search(
                            query=kw,
                            max_results=quota,
                            categories=arxiv_categories,
                            year_start=year_start,
                            year_end=year_end
                        )
                        return kw, papers
                    except Exception as e:
                        logger.warning(f"搜索关键词 '{kw}' 失败: {e}")
                        return kw, []
            
            # 创建所有搜索任务
            tasks = [
                search_keyword(kw, quota)
                for kw, weight, quota in keyword_quotas
            ]
            
            # 并行执行搜索
            papers_this_round = 0
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"搜索任务异常: {result}")
                    continue
                
                kw, arxiv_papers = result
                weight = keyword_weights.get(kw, 0.1)
                quota = next((q for k, w, q in keyword_quotas if k == kw), 0)
                
                new_arxiv_count = 0
                for paper in arxiv_papers:
                    if paper.paper_id not in seen_ids:
                        all_papers.append(paper)
                        seen_ids.add(paper.paper_id)
                        new_arxiv_count += 1
                
                papers_this_round += new_arxiv_count
                logger.info(f"      ✓ '{kw}' (权重: {weight:.1%}, 配额: {quota}): 获取 {new_arxiv_count} 篇新论文")
            
            logger.info(f"本轮并行搜索完成，新增 {papers_this_round} 篇，累计 {len(all_papers)} 篇")
            
            # 检查是否已经有足够的论文进行筛选
            if len(all_papers) >= int(target_count * 1.5):
                logger.info(f"已收集足够论文用于筛选 ({len(all_papers)} 篇)")
                break
            
            # 如果本轮没有新增论文，说明搜索已经饱和
            if papers_this_round == 0:
                logger.warning("本轮未获取新论文，搜索可能已饱和")
                # 继续尝试生成新关键词
        
        logger.info(f"搜索阶段完成，共 {len(all_papers)} 篇论文")
        
        # ========== 阶段 3: 智能筛选 ==========
        logger.info("=" * 50)
        logger.info("阶段 3: 智能筛选")
        logger.info("=" * 50)
        
        filtered_papers = all_papers
        
        # 3.1 Embedding 初筛
        if use_embedding_filter and self.embedding_filter and self.embedding_filter.model:
            logger.info(f"3.1 Embedding 初筛 (阈值: {embedding_threshold})...")
            filtered_papers, rejected_papers = self.embedding_filter.filter_papers(
                filtered_papers, topic, threshold=embedding_threshold
            )
            logger.info(f"   Embedding 筛选后: {len(filtered_papers)} 篇")
        
        # 3.2 LLM 精筛（只在论文数量超过目标时进行）
        if use_llm_filter and self.llm_filter.chat_agent and len(filtered_papers) > target_count:
            logger.info(f"3.2 LLM 精筛 (阈值: {llm_threshold})...")
            filtered_papers, _ = self.llm_filter.filter_papers(
                filtered_papers, topic, threshold=llm_threshold
            )
            logger.info(f"   LLM 筛选后: {len(filtered_papers)} 篇")
        
        # 3.3 按相关性和引用数排序，取 top
        filtered_papers.sort(
            key=lambda x: (x.relevance_score, x.citations),
            reverse=True
        )
        
        # ========== 阶段 3.5: 检查是否达到最小目标，如果不够则补充 ==========
        if len(filtered_papers) < min_required:
            logger.warning(f"筛选后论文数量 ({len(filtered_papers)}) 低于最小目标 ({min_required})")
            logger.info("尝试降低筛选阈值或补充更多论文...")
            
            # 策略1: 降低 embedding 阈值重新筛选
            if use_embedding_filter and self.embedding_filter and self.embedding_filter.model:
                lower_threshold = max(embedding_threshold - 0.1, 0.1)
                logger.info(f"降低 Embedding 阈值到 {lower_threshold} 重新筛选...")
                filtered_papers, _ = self.embedding_filter.filter_papers(
                    all_papers, topic, threshold=lower_threshold
                )
                filtered_papers.sort(
                    key=lambda x: (x.relevance_score, x.citations),
                    reverse=True
                )
            
            # 如果还是不够，直接使用所有论文
            if len(filtered_papers) < min_required:
                logger.warning(f"降低阈值后仍不足 ({len(filtered_papers)} 篇)，使用所有收集到的论文")
                filtered_papers = all_papers
                filtered_papers.sort(
                    key=lambda x: (x.relevance_score, x.citations),
                    reverse=True
                )
        
        final_papers = filtered_papers[:target_count]
        
        logger.info(f"筛选完成，最终 {len(final_papers)} 篇论文")
        
        # 检查是否达到最小目标
        if len(final_papers) < min_required:
            logger.warning(f"⚠️ 最终论文数量 ({len(final_papers)}) 未达到最小目标 ({min_required})")
            logger.warning(f"   目标完成率: {len(final_papers) / target_count * 100:.1f}%")
        else:
            logger.info(f"✅ 达到目标: {len(final_papers)}/{target_count} ({len(final_papers) / target_count * 100:.1f}%)")
        
        # ========== 阶段 4: PDF 下载和解析（仅 arXiv 论文）==========
        if download_pdf:
            logger.info("=" * 50)
            logger.info("阶段 4: PDF 下载和解析")
            logger.info("=" * 50)
            
            final_papers = await self._download_and_parse_pdfs(
                final_papers,
                output_dir=pdf_output_dir
            )
        
        # 转换为字典格式
        return [p.to_dict() for p in final_papers]
    
    async def _generate_keyword_variants(self, topic: str, used_keywords: List[str]) -> List[str]:
        """
        使用 LLM 生成新的关键词变体
        
        Args:
            topic: 研究主题
            used_keywords: 已使用的关键词列表
            
        Returns:
            新的关键词列表
        """
        if not self.chat_agent:
            # 如果没有 LLM，使用简单的变体生成
            variants = []
            # 添加一些通用变体
            base_terms = topic.split()
            if len(base_terms) > 1:
                # 尝试不同的词序组合
                variants.append(" ".join(reversed(base_terms)))
                # 添加引号强调
                variants.append(f'"{topic}"')
                # 添加相关术语
                if "LLM" in topic.upper() or "language model" in topic.lower():
                    variants.extend([
                        "GPT tool use",
                        "ChatGPT function",
                        "AI agent tool",
                        "neural network API"
                    ])
            return [v for v in variants if v not in used_keywords]
        
        prompt = f"""你是一个 arXiv 论文搜索专家。我正在搜索关于 "{topic}" 的论文，但已使用的关键词搜索结果不足。

已使用的关键词:
{chr(10).join(f'- {kw}' for kw in used_keywords)}

请生成 5-8 个新的搜索关键词。

**关键要求**：
1. 关键词必须简短（2-4个词），便于 arXiv 搜索匹配
2. 使用该领域实际论文中常见的术语
3. 可以包含具体的模型名称、方法名称、benchmark 名称
4. 避免过于抽象或学术化的表达

好的关键词示例：
- "GPT tool use"
- "LLM agent"
- "function calling benchmark"
- "API-Bank"
- "ToolBench"

不好的关键词示例（太学术化，搜不到）：
- "Schema-guided Language Models"
- "Neural-Symbolic Action Generation"
- "Executable Action Spaces for LLMs"

输出格式（JSON）:
{{
  "keywords": ["关键词1", "关键词2", ...]
}}

只输出JSON，不要其他内容。"""

        try:
            response = self.chat_agent.remote_chat(prompt, temperature=0.7)
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                result = json.loads(match.group())
                new_keywords = result.get("keywords", [])
                logger.info(f"🤖 LLM 生成新关键词: {new_keywords}")
                return new_keywords
        except Exception as e:
            logger.warning(f"LLM 生成关键词失败: {e}")
        
        return []
    
    async def _search_surveys_arxiv_only(
        self,
        topic: str,
        max_surveys: int,
        year_start: int
    ) -> List[PaperData]:
        """搜索 survey 论文（只使用 arXiv）"""
        surveys = []
        seen_ids = set()
        
        # 只使用 arXiv 搜索 survey
        arxiv_surveys = await self.arxiv.search_surveys(
            topic=topic,
            max_results=max_surveys,
            year_start=year_start
        )
        
        for survey in arxiv_surveys:
            if survey.paper_id not in seen_ids:
                surveys.append(survey)
                seen_ids.add(survey.paper_id)
        
        return surveys
    
    async def _search_surveys(
        self,
        topic: str,
        max_surveys: int,
        year_start: int
    ) -> List[PaperData]:
        """搜索 survey 论文（只使用 arXiv，不使用 Semantic Scholar）"""
        # 直接调用 arXiv-only 版本
        return await self._search_surveys_arxiv_only(topic, max_surveys, year_start)
    
    async def _get_survey_references(
        self,
        surveys: List[PaperData],
        max_refs_per_survey: int,
        year_filter: int
    ) -> List[PaperData]:
        """
        获取 survey 的参考文献
        
        注意：由于只使用 arXiv（arXiv 不提供参考文献信息），此方法现在返回空列表。
        如果需要获取参考文献，需要启用 Semantic Scholar 或 OpenAlex。
        """
        # 由于只使用 arXiv，不再获取参考文献
        # arXiv API 不提供参考文献信息
        logger.info("   跳过参考文献获取（仅使用 arXiv 模式）")
        return []
    
    async def _download_and_parse_pdfs(
        self,
        papers: List[PaperData],
        output_dir: Optional[Path] = None,
        max_workers: int = None
    ) -> List[PaperData]:
        """
        下载 arXiv 论文 PDF 并解析为文本
        
        使用 PyMuPDF (fitz) 进行 PDF 解析，它比 pypdf 更快更准确。
        支持共享 PDF 库，避免重复下载。
        
        优化说明：
        - 并发数从 5 提升到 15，显著提高下载速度
        - arXiv 对 PDF 下载的速率限制比 API 宽松
        - 使用 asyncio.Semaphore 控制并发，避免过载
        
        Args:
            papers: 论文列表
            output_dir: PDF 保存目录（任务特定的目录）
            max_workers: 并发下载数（默认从 config.PDF_DOWNLOAD_WORKERS 读取）
            
        Returns:
            更新后的论文列表（包含 md_text 字段）
        """
        if max_workers is None:
            max_workers = PDF_DOWNLOAD_WORKERS
        # 尝试导入 PDF 解析库（优先使用 PyMuPDF）
        fitz = None
        pypdf = None
        
        try:
            import fitz  # PyMuPDF
            logger.info("使用 PyMuPDF (fitz) 进行 PDF 解析")
        except ImportError:
            logger.warning("PyMuPDF 未安装，尝试使用 pypdf 作为备选")
            try:
                import pypdf
            except ImportError:
                try:
                    import PyPDF2 as pypdf
                except ImportError:
                    logger.warning("PDF 解析库未安装，跳过 PDF 解析。请运行: pip install pymupdf")
                    return papers
        
        # 筛选有 PDF URL 的 arXiv 论文
        arxiv_papers = [p for p in papers if p.source == "arxiv" and p.pdf_url]
        
        if not arxiv_papers:
            logger.info("没有可下载的 arXiv 论文")
            return papers
        
        logger.info(f"开始下载 {len(arxiv_papers)} 篇 arXiv 论文的 PDF...")
        
        # 确定共享 PDF 目录
        import os
        shared_pdf_dir = Path(os.getenv("SHARED_PDF_DIR", "D:/SurveyGraphPdfs"))
        try:
            shared_pdf_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"使用共享 PDF 库: {shared_pdf_dir}")
        except Exception as e:
            logger.warning(f"无法创建共享 PDF 目录 {shared_pdf_dir}: {e}")
            # 回退到项目内目录
            shared_pdf_dir = Path("shared_pdfs")
            shared_pdf_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"使用回退共享 PDF 库: {shared_pdf_dir}")

        # 创建任务特定的输出目录（如果需要）
        if output_dir is None:
            import tempfile
            output_dir = Path(tempfile.mkdtemp(prefix="surveygraph_pdfs_"))
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        
        # 下载和解析函数
        async def download_and_parse_single(paper: PaperData) -> Tuple[str, str]:
            """下载并解析单篇论文，返回 (paper_id, md_text)"""
            try:
                # 文件名使用 arXiv ID
                filename = f"{paper.arxiv_id}.pdf"
                shared_path = shared_pdf_dir / filename
                task_path = output_dir / filename
                
                # 1. 检查共享库中是否存在
                if shared_path.exists():
                    # logger.debug(f"从共享库加载 PDF: {filename}")
                    # 如果需要，可以复制到任务目录（可选，为了节省空间这里不复制，直接解析）
                    # import shutil
                    # shutil.copy2(shared_path, task_path)
                    pdf_path = shared_path
                else:
                    # 2. 下载 PDF
                    # logger.debug(f"下载 PDF: {filename}")
                    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                        response = await client.get(paper.pdf_url)
                        response.raise_for_status()
                        
                        # 保存到共享库
                        with open(shared_path, 'wb') as f:
                            f.write(response.content)
                    
                    pdf_path = shared_path
                
                # 3. 解析 PDF（优先使用 PyMuPDF）
                # 检查是否有缓存的解析结果（可选优化，这里暂不实现，直接解析）
                if fitz is not None:
                    md_text = self._parse_pdf_with_pymupdf(pdf_path)
                else:
                    md_text = self._parse_pdf_with_pypdf(pdf_path, pypdf)
                
                return paper.paper_id, md_text
                
            except Exception as e:
                logger.debug(f"下载/解析 PDF 失败 ({paper.arxiv_id}): {e}")
                return paper.paper_id, ""
        
        # 并发下载
        paper_id_to_text = {}
        
        # 使用 semaphore 限制并发
        semaphore = asyncio.Semaphore(max_workers)
        
        async def limited_download(paper):
            async with semaphore:
                return await download_and_parse_single(paper)
        
        tasks = [limited_download(p) for p in arxiv_papers]
        
        results = []
        for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="下载 PDF"):
            result = await coro
            results.append(result)
        
        for paper_id, md_text in results:
            if md_text:
                paper_id_to_text[paper_id] = md_text
        
        logger.info(f"成功解析 {len(paper_id_to_text)} 篇论文的 PDF")
        
        # 更新论文数据
        for paper in papers:
            if paper.paper_id in paper_id_to_text:
                # 添加 md_text 到论文数据
                paper.md_text = paper_id_to_text[paper.paper_id]
        
        return papers
    
    def _parse_pdf_with_pymupdf(self, pdf_path: Path) -> str:
        """
        使用 PyMuPDF (fitz) 解析 PDF 文件为文本
        
        PyMuPDF 的优势：
        - 解析速度快（比 pypdf 快 10 倍以上）
        - 文本提取更准确
        - 支持更多 PDF 格式
        - 可以保留文本布局
        
        Args:
            pdf_path: PDF 文件路径
            
        Returns:
            提取的文本内容
        """
        try:
            import fitz  # PyMuPDF
            
            text_parts = []
            
            # 打开 PDF 文档
            doc = fitz.open(str(pdf_path))
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # 提取文本（使用 "text" 模式获取纯文本）
                text = page.get_text("text")
                
                if text:
                    text_parts.append(text)
            
            doc.close()
            
            full_text = "\n\n".join(text_parts)
            
            # 清理文本
            full_text = self._clean_pdf_text(full_text)
            
            return full_text
            
        except Exception as e:
            logger.debug(f"PyMuPDF 解析失败 ({pdf_path}): {e}")
            return ""
    
    def _parse_pdf_with_pypdf(self, pdf_path: Path, pypdf_module) -> str:
        """
        使用 pypdf/PyPDF2 解析 PDF 文件为文本（备选方案）
        
        Args:
            pdf_path: PDF 文件路径
            pypdf_module: pypdf 或 PyPDF2 模块
            
        Returns:
            提取的文本内容
        """
        try:
            text_parts = []
            
            with open(pdf_path, 'rb') as f:
                # 尝试使用 pypdf (新版)
                if hasattr(pypdf_module, 'PdfReader'):
                    reader = pypdf_module.PdfReader(f)
                    for page in reader.pages:
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)
                # 兼容 PyPDF2 (旧版)
                elif hasattr(pypdf_module, 'PdfFileReader'):
                    reader = pypdf_module.PdfFileReader(f)
                    for page_num in range(reader.numPages):
                        page = reader.getPage(page_num)
                        text = page.extractText()
                        if text:
                            text_parts.append(text)
            
            full_text = "\n\n".join(text_parts)
            
            # 清理文本
            full_text = self._clean_pdf_text(full_text)
            
            return full_text
            
        except Exception as e:
            logger.debug(f"pypdf 解析失败 ({pdf_path}): {e}")
            return ""
    
    def _clean_pdf_text(self, text: str) -> str:
        """
        清理 PDF 提取的文本
        
        Args:
            text: 原始文本
            
        Returns:
            清理后的文本
        """
        import re
        
        # 移除多余的空白
        text = re.sub(r'\s+', ' ', text)
        
        # 移除页眉页脚（常见模式）
        text = re.sub(r'\d+\s*$', '', text, flags=re.MULTILINE)
        
        # 移除参考文献部分（可选，保留可能更好）
        # ref_patterns = [r'References\s*\n', r'REFERENCES\s*\n', r'Bibliography\s*\n']
        # for pattern in ref_patterns:
        #     match = re.search(pattern, text)
        #     if match:
        #         text = text[:match.start()]
        #         break
        
        # 限制长度（避免过长）
        max_length = 50000  # 约 50K 字符
        if len(text) > max_length:
            text = text[:max_length] + "..."
        
        return text.strip()

    async def enrich_with_openalex(self, papers: List[PaperData]) -> List[PaperData]:
        """
        使用 OpenAlex 丰富论文元数据
        
        主要用于获取引用数和参考文献列表
        """
        enriched = []
        
        for paper in tqdm(papers, desc="OpenAlex 丰富元数据"):
            if paper.arxiv_id:
                try:
                    openalex_data = await self.openalex.get_paper_by_arxiv_id(paper.arxiv_id)
                    if openalex_data:
                        # 合并数据
                        paper.citations = max(paper.citations, openalex_data.citations)
                        paper.openalex_id = openalex_data.openalex_id
                        if not paper.referenced_works:
                            paper.referenced_works = openalex_data.referenced_works
                except Exception as e:
                    logger.debug(f"OpenAlex 丰富失败: {e}")
            
            enriched.append(paper)
        
        return enriched


    async def collect_papers_stream(
        self,
        topic: str,
        target_count: int = 100,
        year_start: int = 2020,
        year_end: Optional[int] = None,
        use_embedding_filter: bool = True,
        embedding_threshold: float = 0.3,
        batch_size: int = 20
    ):
        """
        流式收集论文（数据流管道化优化）
        
        与 collect_papers 不同，此方法使用异步生成器，
        允许在收集论文的同时开始处理，减少整体等待时间。
        
        使用场景：
        - 当需要边收集边处理时（如边收集边构建图谱）
        - 当需要实时显示进度时
        - 当内存有限，需要分批处理时
        
        Args:
            topic: 研究主题
            target_count: 目标论文数
            year_start: 起始年份
            year_end: 结束年份
            use_embedding_filter: 是否使用 Embedding 筛选
            embedding_threshold: Embedding 相似度阈值
            batch_size: 每批返回的论文数量
            
        Yields:
            Dict[str, Any]: 论文数据（字典格式）
            
        Example:
            ```python
            collector = EnhancedPaperCollector()
            async for paper in collector.collect_papers_stream(
                topic="Large Language Model",
                target_count=100,
                batch_size=10
            ):
                # 边收集边处理
                process_paper(paper)
            ```
        """
        if year_end is None:
            year_end = datetime.now().year
        
        seen_ids: Set[str] = set()
        yielded_count = 0
        
        logger.info(f"开始流式收集论文: topic={topic}, target={target_count}")
        
        # 自动判断 arXiv 分类
        arxiv_categories, primary_field = self.detect_arxiv_categories(topic)
        
        # 关键词拆分
        keywords_with_weights = self.split_keywords_with_llm(topic)
        keywords = [kw["keyword"] for kw in keywords_with_weights]
        
        # 计算每个关键词的配额
        keyword_weights = {kw["keyword"]: kw["weight"] for kw in keywords_with_weights}
        total_weight = sum(keyword_weights.values())
        
        # 流式搜索每个关键词
        for kw in keywords:
            if yielded_count >= target_count:
                break
            
            weight = keyword_weights.get(kw, 0.1)
            normalized_weight = weight / total_weight if total_weight > 0 else 1.0 / len(keywords)
            quota = max(int(target_count * normalized_weight * 1.5), 30)
            
            logger.info(f"   🔍 流式搜索: '{kw}' (配额: {quota})")
            
            # 搜索论文
            try:
                papers = await self.arxiv.search(
                    query=kw,
                    max_results=quota,
                    categories=arxiv_categories,
                    year_start=year_start,
                    year_end=year_end
                )
            except Exception as e:
                logger.warning(f"搜索关键词 '{kw}' 失败: {e}")
                continue
            
            # 批量处理和返回
            batch: List[PaperData] = []
            
            for paper in papers:
                if paper.paper_id in seen_ids:
                    continue
                
                seen_ids.add(paper.paper_id)
                
                # 如果启用 embedding 筛选，计算相关性
                if use_embedding_filter and self.embedding_filter and self.embedding_filter.model:
                    text = f"{paper.title}. {paper.abstract[:500]}"
                    topic_embedding = self.embedding_filter.model.encode(topic, convert_to_numpy=True)
                    paper_embedding = self.embedding_filter.model.encode(text, convert_to_numpy=True)
                    
                    similarity = np.dot(topic_embedding, paper_embedding) / (
                        np.linalg.norm(topic_embedding) * np.linalg.norm(paper_embedding)
                    )
                    
                    if similarity < embedding_threshold:
                        continue
                    
                    paper.relevance_score = float(similarity)
                
                batch.append(paper)
                
                # 当批次满了或达到目标数量时，yield 批次
                if len(batch) >= batch_size:
                    for p in batch:
                        if yielded_count >= target_count:
                            break
                        yield p.to_dict()
                        yielded_count += 1
                    batch = []
                    
                    if yielded_count >= target_count:
                        break
            
            # yield 剩余的论文
            for p in batch:
                if yielded_count >= target_count:
                    break
                yield p.to_dict()
                yielded_count += 1
        
        logger.info(f"流式收集完成，共返回 {yielded_count} 篇论文")


# ============================================================================
# 便捷函数
# ============================================================================

async def collect_papers_for_survey(
    topic: str,
    target_count: int = 100,
    year_start: int = 2020,
    use_survey_strategy: bool = True,
    use_embedding_filter: bool = True,
    use_llm_filter: bool = True
) -> List[Dict[str, Any]]:
    """
    便捷函数：为综述收集论文
    
    Args:
        topic: 研究主题
        target_count: 目标论文数
        year_start: 起始年份
        use_survey_strategy: 是否使用 Survey 优先策略
        use_embedding_filter: 是否使用 Embedding 筛选
        use_llm_filter: 是否使用 LLM 精筛
        
    Returns:
        论文列表
    """
    collector = EnhancedPaperCollector()
    return await collector.collect_papers(
        topic=topic,
        target_count=target_count,
        year_start=year_start,
        use_survey_strategy=use_survey_strategy,
        use_embedding_filter=use_embedding_filter,
        use_llm_filter=use_llm_filter
    )


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    async def test():
        collector = EnhancedPaperCollector()
        
        papers = await collector.collect_papers(
            topic="Large Language Model Function Calling",
            target_count=50,
            year_start=2022,
            use_survey_strategy=True,
            use_embedding_filter=True,
            use_llm_filter=False  # 测试时关闭 LLM 筛选
        )
        
        print(f"\n收集到 {len(papers)} 篇论文:")
        for i, p in enumerate(papers[:10], 1):
            print(f"{i}. [{p['source']}] {p['title'][:60]}... ({p['year']}, {p['citations']} cites)")
            if p.get('is_survey'):
                print(f"   📚 Survey 论文")
    
    asyncio.run(test())
