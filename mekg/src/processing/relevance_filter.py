"""
论文相关性过滤器
================

用于过滤与主题不相关的论文，确保爬取的论文质量。

支持两种过滤方式：
1. 基于关键词的快速过滤
2. 基于LLM的语义相关性判断（更准确但更慢）

LLM过滤支持高并发（默认100），推荐使用开源模型如 kimi-k2 进行快速过滤。
"""

import re
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from loguru import logger
from tqdm import tqdm

from src.configs.config import RELEVANCE_FILTER_MODEL


@dataclass
class RelevanceResult:
    """相关性判断结果"""
    paper_id: str
    is_relevant: bool
    score: float
    reason: str


# 简洁高效的快速过滤 prompt（用于高并发场景）
FAST_RELEVANCE_PROMPT = """判断论文是否与主题"{topic}"相关。

标题: {title}
摘要: {abstract}

只输出JSON: {{"relevant": true/false, "score": 0.0-1.0}}"""


# 详细的相关性检查 prompt（用于精确判断）
RELEVANCE_CHECK_PROMPT = """你是一个学术论文相关性判断专家。请判断以下论文是否与给定的研究主题相关。

研究主题: {topic}

论文标题: {title}
论文摘要: {abstract}

请判断这篇论文是否与研究主题相关。考虑以下因素：
1. 论文是否直接研究该主题
2. 论文是否使用了该主题相关的技术/方法
3. 论文是否解决了该主题相关的问题
4. 论文是否可以作为该主题综述的参考文献

输出JSON格式：
```json
{{
    "is_relevant": true/false,
    "score": 0.0-1.0,
    "reason": "简短说明原因"
}}
```

只输出JSON，不要其他内容。"""


class RelevanceFilter:
    """论文相关性过滤器"""
    
    def __init__(
        self,
        chat_agent=None,
        use_llm: bool = True,
        keyword_threshold: float = 0.3,
        llm_threshold: float = 0.5,
        max_workers: int = None,
        filter_model: str = None,
        use_fast_prompt: bool = True
    ):
        """
        初始化过滤器
        
        Args:
            chat_agent: ChatAgent实例，用于LLM判断
            use_llm: 是否使用LLM进行语义判断
            keyword_threshold: 关键词匹配阈值
            llm_threshold: LLM相关性阈值
            max_workers: 并发工作线程数（默认从 config.RELEVANCE_FILTER_WORKERS 读取）
            filter_model: 用于过滤的模型名称，None则使用配置中的默认模型
            use_fast_prompt: 是否使用简洁的快速过滤prompt（推荐True）
        """
        from src.configs.config import RELEVANCE_FILTER_WORKERS
        
        self.chat_agent = chat_agent
        self.use_llm = use_llm and chat_agent is not None
        self.keyword_threshold = keyword_threshold
        self.llm_threshold = llm_threshold
        self.max_workers = max_workers if max_workers is not None else RELEVANCE_FILTER_WORKERS
        self.filter_model = filter_model or RELEVANCE_FILTER_MODEL
        self.use_fast_prompt = use_fast_prompt
    
    def filter_papers(
        self,
        papers: List[Dict],
        topic: str,
        use_llm_filter: bool = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        过滤论文列表
        
        Args:
            papers: 论文列表
            topic: 研究主题
            use_llm_filter: 是否使用LLM过滤（None则使用默认设置）
            
        Returns:
            (相关论文列表, 不相关论文列表)
        """
        if use_llm_filter is None:
            use_llm_filter = self.use_llm
        
        # 生成主题关键词
        topic_keywords = self._extract_keywords(topic)
        logger.info(f"Topic keywords: {topic_keywords}")
        
        relevant_papers = []
        irrelevant_papers = []
        
        # 第一轮：关键词快速过滤
        keyword_passed = []
        keyword_failed = []
        
        for paper in papers:
            score = self._keyword_relevance(paper, topic_keywords)
            if score >= self.keyword_threshold:
                keyword_passed.append((paper, score))
            else:
                keyword_failed.append((paper, score))
        
        logger.info(f"Keyword filter: {len(keyword_passed)} passed, {len(keyword_failed)} failed")
        
        # 对于关键词匹配度高的论文，直接通过
        high_confidence = [(p, s) for p, s in keyword_passed if s >= 0.6]
        need_llm_check = [(p, s) for p, s in keyword_passed if s < 0.6]
        
        for paper, score in high_confidence:
            relevant_papers.append(paper)
        
        # 第二轮：LLM语义判断（可选）
        if use_llm_filter and self.chat_agent and need_llm_check:
            logger.info(f"LLM relevance check for {len(need_llm_check)} papers (workers={self.max_workers})...")
            
            llm_results = self._batch_llm_check(
                [p for p, s in need_llm_check],
                topic
            )
            
            for paper, result in zip([p for p, s in need_llm_check], llm_results):
                if result.is_relevant and result.score >= self.llm_threshold:
                    relevant_papers.append(paper)
                else:
                    irrelevant_papers.append(paper)
        else:
            # 不使用LLM，直接通过关键词过滤的论文
            for paper, score in need_llm_check:
                relevant_papers.append(paper)
        
        # 关键词过滤失败的论文
        for paper, score in keyword_failed:
            irrelevant_papers.append(paper)
        
        logger.info(f"Final: {len(relevant_papers)} relevant, {len(irrelevant_papers)} irrelevant")
        
        return relevant_papers, irrelevant_papers
    
    def filter_papers_llm_only(
        self,
        papers: List[Dict],
        topic: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        仅使用LLM进行论文过滤（跳过关键词预过滤）
        
        适用于需要更精确过滤的场景，支持高并发（100+）。
        推荐使用开源模型如 kimi-k2 进行快速过滤。
        
        Args:
            papers: 论文列表
            topic: 研究主题
            
        Returns:
            (相关论文列表, 不相关论文列表)
        """
        if not self.chat_agent:
            logger.warning("No chat_agent provided, falling back to keyword filter")
            return self.filter_papers(papers, topic, use_llm_filter=False)
        
        logger.info(f"LLM-only filter for {len(papers)} papers (workers={self.max_workers}, model={self.filter_model or 'default'})...")
        
        llm_results = self._batch_llm_check(papers, topic)
        
        relevant_papers = []
        irrelevant_papers = []
        
        for paper, result in zip(papers, llm_results):
            if result.is_relevant and result.score >= self.llm_threshold:
                relevant_papers.append(paper)
            else:
                irrelevant_papers.append(paper)
        
        logger.info(f"LLM filter result: {len(relevant_papers)} relevant, {len(irrelevant_papers)} irrelevant")
        
        return relevant_papers, irrelevant_papers
    
    def _extract_keywords(self, topic: str) -> List[str]:
        """从主题中提取关键词"""
        # 基本分词
        words = topic.lower().split()
        
        # 添加常见变体
        keywords = set(words)
        
        # 添加缩写和全称映射
        abbreviations = {
            "llm": ["large language model", "language model"],
            "nlp": ["natural language processing"],
            "ml": ["machine learning"],
            "dl": ["deep learning"],
            "ai": ["artificial intelligence"],
            "gpt": ["generative pre-trained transformer"],
            "bert": ["bidirectional encoder representations"],
            "rag": ["retrieval augmented generation"],
            "api": ["application programming interface"],
        }
        
        for word in words:
            word_lower = word.lower()
            if word_lower in abbreviations:
                keywords.update(abbreviations[word_lower])
            # 反向查找
            for abbr, full_forms in abbreviations.items():
                for full in full_forms:
                    if word_lower in full.split():
                        keywords.add(abbr)
        
        # 添加组合关键词
        if len(words) >= 2:
            keywords.add(" ".join(words[:2]))
            keywords.add(" ".join(words[-2:]))
        
        return list(keywords)
    
    def _keyword_relevance(self, paper: Dict, keywords: List[str]) -> float:
        """计算关键词相关性得分"""
        title = (paper.get("title") or "").lower()
        abstract = (paper.get("abstract") or "").lower()
        text = f"{title} {abstract}"
        
        if not text.strip():
            return 0.0
        
        # 计算匹配的关键词数量
        matched = 0
        total_weight = 0
        
        for kw in keywords:
            weight = len(kw.split())  # 多词关键词权重更高
            total_weight += weight
            
            if kw in text:
                matched += weight
                # 标题中出现加分
                if kw in title:
                    matched += weight * 0.5
        
        if total_weight == 0:
            return 0.0
        
        return min(matched / total_weight, 1.0)
    
    def _batch_llm_check(
        self,
        papers: List[Dict],
        topic: str
    ) -> List[RelevanceResult]:
        """批量LLM相关性检查（支持高并发）"""
        results = [None] * len(papers)
        
        def check_single(idx: int, paper: Dict) -> Tuple[int, RelevanceResult]:
            result = self._llm_check_single(paper, topic)
            return idx, result
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(check_single, i, p): i
                for i, p in enumerate(papers)
            }
            
            model_info = f" ({self.filter_model})" if self.filter_model else ""
            for future in tqdm(as_completed(futures), total=len(futures), desc=f"LLM过滤{model_info}"):
                try:
                    idx, result = future.result()
                    results[idx] = result
                except Exception as e:
                    idx = futures[future]
                    results[idx] = RelevanceResult(
                        paper_id=papers[idx].get("paper_id", ""),
                        is_relevant=True,  # 出错时默认保留
                        score=0.5,
                        reason=f"LLM check failed: {e}"
                    )
        
        return results
    
    def _llm_check_single(self, paper: Dict, topic: str) -> RelevanceResult:
        """单篇论文LLM相关性检查"""
        paper_id = paper.get("paper_id") or paper.get("id", "")
        
        if not self.chat_agent:
            return RelevanceResult(paper_id, True, 0.5, "No LLM available")
        
        # 选择 prompt 模板
        if self.use_fast_prompt:
            prompt = FAST_RELEVANCE_PROMPT.format(
                topic=topic,
                title=paper.get("title", ""),
                abstract=(paper.get("abstract") or "")[:300]  # 快速模式使用更短的摘要
            )
        else:
            prompt = RELEVANCE_CHECK_PROMPT.format(
                topic=topic,
                title=paper.get("title", ""),
                abstract=(paper.get("abstract") or "")[:500]
            )
        
        try:
            # 使用指定的过滤模型或默认模型
            kwargs = {"temperature": 0.1, "timeout": 30}  # 快速过滤使用更低温度和更短超时
            if self.filter_model:
                kwargs["model"] = self.filter_model
            
            response = self.chat_agent.remote_chat(prompt, **kwargs)
            
            # 解析响应
            import json
            # 尝试多种格式解析
            match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
            else:
                # 尝试直接解析 JSON
                json_match = re.search(r'\{[^{}]*\}', response)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    data = json.loads(response)
            
            # 兼容两种格式的响应
            is_relevant = data.get("relevant", data.get("is_relevant", True))
            score = float(data.get("score", 0.5))
            reason = data.get("reason", "")
            
            return RelevanceResult(
                paper_id=paper_id,
                is_relevant=is_relevant,
                score=score,
                reason=reason
            )
        except Exception as e:
            logger.debug(f"LLM relevance check failed for {paper_id}: {e}")
            return RelevanceResult(paper_id, True, 0.5, f"Parse error: {e}")


def filter_papers_by_relevance(
    papers: List[Dict],
    topic: str,
    chat_agent=None,
    use_llm: bool = False,
    threshold: float = 0.3,
    max_workers: int = None,
    filter_model: str = None
) -> List[Dict]:
    """
    便捷函数：过滤论文列表
    
    Args:
        papers: 论文列表
        topic: 研究主题
        chat_agent: ChatAgent实例
        use_llm: 是否使用LLM
        threshold: 相关性阈值
        max_workers: LLM并发数（默认从 config 读取）
        filter_model: 用于过滤的模型名称（如 "kimi-k2"）
        
    Returns:
        相关论文列表
    """
    filter_obj = RelevanceFilter(
        chat_agent=chat_agent,
        use_llm=use_llm,
        keyword_threshold=threshold,
        max_workers=max_workers,
        filter_model=filter_model
    )
    relevant, _ = filter_obj.filter_papers(papers, topic)
    return relevant


def filter_papers_by_llm(
    papers: List[Dict],
    topic: str,
    chat_agent,
    threshold: float = 0.5,
    max_workers: int = None,
    filter_model: str = None
) -> List[Dict]:
    """
    便捷函数：仅使用LLM过滤论文（高并发，推荐使用开源模型）
    
    Args:
        papers: 论文列表
        topic: 研究主题
        chat_agent: ChatAgent实例
        threshold: LLM相关性阈值（默认0.5）
        max_workers: 并发数（默认从 config 读取）
        filter_model: 模型名称（默认 kimi-k2）
        
    Returns:
        相关论文列表
        
    Example:
        >>> from src.models.LLM.ChatAgent import ChatAgent
        >>> agent = ChatAgent()
        >>> relevant = filter_papers_by_llm(papers, "Large Language Model Function Calling", agent)
    """
    filter_obj = RelevanceFilter(
        chat_agent=chat_agent,
        use_llm=True,
        llm_threshold=threshold,
        max_workers=max_workers,
        filter_model=filter_model,
        use_fast_prompt=True
    )
    relevant, _ = filter_obj.filter_papers_llm_only(papers, topic)
    return relevant
