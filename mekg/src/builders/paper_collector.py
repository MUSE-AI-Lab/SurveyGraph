#!/usr/bin/env python3
"""
LLM Tool Use Survey 构建脚本

完整流程：
1. 从 OpenAlex 爬取 LLM Tool Use 相关论文
2. 基于引用关系和LLM语义分析构建层级结构
3. 发现21种关系类型（结构、语义、概念、时序、作者）
4. 生成2D层级可视化

使用方法：
    python mekg/scripts/tools/build_llm_tool_use_survey.py
"""

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from tqdm import tqdm

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 导入 ChatAgent
try:
    from src.models.LLM.ChatAgent import ChatAgent
    HAS_CHAT_AGENT = True
except ImportError:
    HAS_CHAT_AGENT = False
    print("⚠️ ChatAgent 未找到，将使用规则发现关系")

# ============================================================================
# 数据结构定义
# ============================================================================

@dataclass
class HierarchyNode:
    """层级节点"""
    id: str
    title: str
    level: int
    node_type: str
    children: List['HierarchyNode'] = field(default_factory=list)
    parent: Optional['HierarchyNode'] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 0.5


@dataclass
class HierarchyEdge:
    """层级边"""
    source_id: str
    target_id: str
    relation_type: str
    confidence: float = 1.0
    evidence: str = ""


# ============================================================================
# OpenAlex 论文爬取
# ============================================================================

class OpenAlexCrawler:
    """OpenAlex 论文爬取器"""
    
    KEYWORD_GENERATION_PROMPT = """你是一个学术搜索专家。请根据给定的研究主题，生成一组用于OpenAlex搜索的关键词。

研究主题: {topic}

要求:
1. **最多生成 2-3 个**相关的搜索关键词（保守策略，避免引用过于分散）。
2. 关键词应包含：
   - 核心概念的变体（如 "LLM" -> "Large Language Model"）
   - 最重要的同义词（如 "Function Calling" -> "Tool Use"）
3. **不要生成过多关键词**，只保留最核心、最相关的。
4. 按相关性从高到低排序。

输出格式（JSON列表）:
["keyword1", "keyword2"]

只输出JSON列表，不要其他内容。"""

    KEYWORD_SPLIT_PROMPT = """你是一个学术搜索专家。请分析以下研究主题是否需要拆分为多个关键词进行搜索。

研究主题: {topic}

**重要原则：保守拆分，避免引用分散**
- 优先使用用户提供的原始关键词
- 只有在原始关键词确实过于宽泛或模糊时才拆分
- 拆分后的关键词数量**最多 3-4 个**

判断标准:
1. 如果主题清晰、具体（如 "BERT", "GPT-3", "Document Visual Question Answering"）→ **不需要拆分**
2. 如果主题是一个完整的研究领域名称（如 "Visual Question Answering"）→ **不需要拆分**
3. 只有当主题确实包含多个独立概念且需要分别搜索时 → 才需要拆分

如果需要拆分，请生成 **最多 3-4 个**相关的搜索关键词，确保：
- **第一个关键词必须是原始主题本身**（权重最高）
- 只包含最核心的同义词或变体
- **为每个关键词分配权重（0.0-1.0），权重之和应为1.0，权重越高表示该关键词越重要/相关**
- **原始主题的权重应至少为 0.4**

输出格式（JSON）:
{{
  "need_split": true/false,
  "reason": "判断理由",
  "keywords": [
    {{"keyword": "关键词1", "weight": 0.5}},
    {{"keyword": "关键词2", "weight": 0.3}},
    {{"keyword": "关键词3", "weight": 0.2}}
  ]
}}

示例:
- 输入: "BERT"
  输出: {{"need_split": false, "reason": "BERT是一个具体的模型名称，不需要拆分", "keywords": [{{"keyword": "BERT", "weight": 1.0}}]}}

- 输入: "Document Visual Question Answering"
  输出: {{"need_split": false, "reason": "这是一个完整的研究领域名称，不需要拆分", "keywords": [{{"keyword": "Document Visual Question Answering", "weight": 1.0}}]}}

- 输入: "Large Language Model Function Calling"
  输出: {{"need_split": true, "reason": "主题包含多个概念：LLM和Function Calling，可以适度拆分", "keywords": [{{"keyword": "Large Language Model Function Calling", "weight": 0.5}}, {{"keyword": "LLM Tool Use", "weight": 0.3}}, {{"keyword": "LLM Function Calling", "weight": 0.2}}]}}

只输出JSON，不要其他内容。"""

    def __init__(self, email: str = "surveygraph@example.com", chat_agent=None):
        self.base_url = "https://api.openalex.org/works"
        self.headers = {"User-Agent": f"SurveyGraph/1.0 (mailto:{email})"}
        self.rate_limit_delay = 0.1  # 100ms between requests
        self.chat_agent = chat_agent
        
        if self.chat_agent is None and HAS_CHAT_AGENT:
            try:
                self.chat_agent = ChatAgent()
            except:
                pass
    
    def split_keywords_with_llm(self, topic: str) -> List[Dict[str, any]]:
        """
        使用LLM判断是否需要拆分关键词，并返回带权重的关键词列表
        
        Args:
            topic: 研究主题
            
        Returns:
            带权重的关键词列表，格式: [{"keyword": str, "weight": float}, ...]
            如果不需要拆分，返回原始主题（权重为1.0）
        """
        if not self.chat_agent:
            print(f"   ⚠️ ChatAgent不可用，使用原始关键词")
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
                    print(f"   🤖 LLM建议拆分关键词（按权重排序）:")
                    for kw in keywords_data:
                        print(f"      - {kw['keyword']}: {kw['weight']:.1%}")
                    print(f"      理由: {result.get('reason', 'N/A')}")
                    return keywords_data
                else:
                    print(f"   🤖 LLM判断无需拆分: {result.get('reason', 'N/A')}")
                    return [{"keyword": topic, "weight": 1.0}]
            else:
                print(f"   ⚠️ LLM响应解析失败，使用原始关键词")
                return [{"keyword": topic, "weight": 1.0}]
                
        except Exception as e:
            print(f"   ⚠️ LLM关键词拆分失败: {e}，使用原始关键词")
            return [{"keyword": topic, "weight": 1.0}]
    
    async def search_papers(
        self,
        query: str,
        limit: int = 100,
        year_start: int = 2020,
        sort_by: str = "cited_by_count:desc",
        use_keyword_split: bool = True
    ) -> List[Dict]:
        """
        搜索论文
        
        Args:
            query: 搜索查询
            limit: 最大论文数
            year_start: 起始年份
            sort_by: 排序方式
            use_keyword_split: 是否使用LLM拆分关键词（默认True）
            
        Returns:
            论文列表
        """
        papers = []
        seen_ids = set()
        
        # 1. 使用LLM拆分关键词（如果启用）
        if use_keyword_split and self.chat_agent:
            keywords_with_weights = self.split_keywords_with_llm(query)
        else:
            keywords_with_weights = [{"keyword": query, "weight": 1.0}]
        
        # 2. 按权重分配配额并搜索
        if len(keywords_with_weights) >= 1:
            print(f"   📋 使用 {len(keywords_with_weights)} 个关键词搜索（按权重分配配额）:")
            
            # 按权重分配配额，确保每个关键词至少有最小配额
            min_quota = 20  # 最小配额
            total_weight = sum(kw["weight"] for kw in keywords_with_weights)
            
            for kw_data in keywords_with_weights:
                if len(papers) >= limit:
                    print(f"   ✅ 已达到目标数量 {limit}，停止搜索")
                    break
                
                keyword = kw_data["keyword"]
                weight = kw_data["weight"] / total_weight if total_weight > 0 else 1.0 / len(keywords_with_weights)
                
                # 按权重计算配额，但要考虑剩余需要的数量
                remaining = limit - len(papers)
                # 配额 = max(按权重分配的配额, 最小配额)，但不超过剩余需要的数量
                quota = max(int(limit * weight * 1.5), min_quota)  # 1.5倍冗余，因为可能有重复
                quota = min(quota, remaining + 50)  # 允许一些冗余以应对重复
                
                print(f"   🔍 关键词: '{keyword}' (权重: {weight:.1%}, 配额: {quota})")
                new_papers = await self._search_single_query(
                    keyword, quota, year_start, sort_by, seen_ids
                )
                papers.extend(new_papers)
                print(f"      ✓ 获取 {len(new_papers)} 篇，累计 {len(papers)} 篇")
                
                # 如果已经达到目标，立即停止
                if len(papers) >= limit:
                    print(f"   ✅ 第一轮搜索已达到目标数量，无需继续")
                    break
        
        # 3. 如果数量不足，使用LLM生成扩展关键词（第二轮）
        if len(papers) < limit:
            print(f"   ⚠️ 第一轮结果不足 ({len(papers)}/{limit})，启动第二轮扩展搜索...")
            
            extended_keywords = []
            searched_keywords = [kw["keyword"].lower() for kw in keywords_with_weights]
            
            if self.chat_agent:
                try:
                    prompt = self.KEYWORD_GENERATION_PROMPT.format(topic=query)
                    response = self.chat_agent.remote_chat(prompt, temperature=0.7)
                    match = re.search(r'\[.*\]', response, re.DOTALL)
                    if match:
                        extended_keywords = json.loads(match.group())
                        # 过滤掉已经搜索过的关键词
                        extended_keywords = [kw for kw in extended_keywords if kw.lower() not in searched_keywords]
                        if extended_keywords:
                            print(f"   🤖 LLM建议扩展关键词: {extended_keywords}")
                except Exception as e:
                    print(f"   ⚠️ LLM关键词生成失败: {e}")
            
            # 如果LLM失败，回退到简单拆分
            if not extended_keywords:
                words = query.split()
                if len(words) > 2:
                    extended_keywords.append(" ".join(words[:2]))
            
            # 执行扩展搜索
            for kw in extended_keywords:
                if len(papers) >= limit:
                    break
                if kw.lower() in searched_keywords:
                    continue
                    
                print(f"   🔍 扩展搜索: '{kw}'")
                new_papers = await self._search_single_query(
                    kw, limit - len(papers), year_start, sort_by, seen_ids
                )
                papers.extend(new_papers)
                print(f"      ✓ 获取 {len(new_papers)} 篇，累计 {len(papers)} 篇")
            
            # 4. 尝试放宽年份（第三轮）
            if len(papers) < limit and year_start > 2018:
                print(f"   ⚠️ 第二轮结果仍不足 ({len(papers)}/{limit})，启动第三轮（放宽年份）...")
                print(f"   🔍 放宽年份限制: {year_start-2}+")
                new_papers = await self._search_single_query(
                    query, limit - len(papers), year_start - 2, sort_by, seen_ids
                )
                papers.extend(new_papers)
                print(f"      ✓ 获取 {len(new_papers)} 篇，累计 {len(papers)} 篇")

        print(f"   ✓ 爬取到 {len(papers)} 篇论文")
        return papers[:limit]

    async def _search_single_query(
        self,
        query: str,
        limit: int,
        year_start: int,
        sort_by: str,
        seen_ids: set
    ) -> List[Dict]:
        """执行单个查询"""
        papers = []
        per_page = min(limit, 50)
        
        params = {
            "search": query,
            "per-page": per_page,
            "filter": f"from_publication_date:{year_start}-01-01",
            "sort": sort_by
        }
        
        async with httpx.AsyncClient(timeout=30.0, headers=self.headers) as client:
            cursor = "*"
            fetched = 0
            
            while fetched < limit:
                params["cursor"] = cursor
                
                try:
                    print(f"      正在获取... ({fetched}/{limit})")
                    response = await client.get(self.base_url, params=params)
                    
                    if response.status_code != 200:
                        print(f"      ⚠️ API错误: {response.status_code}")
                        break
                    
                    data = response.json()
                    results = data.get("results", [])
                    
                    if not results:
                        break
                    
                    for work in results:
                        paper = self._parse_work(work)
                        if paper and paper['paper_id'] not in seen_ids:
                            papers.append(paper)
                            seen_ids.add(paper['paper_id'])
                            fetched += 1
                            if fetched >= limit:
                                break
                    
                    # 获取下一页游标
                    meta = data.get("meta", {})
                    cursor = meta.get("next_cursor")
                    if not cursor:
                        break
                    
                    await asyncio.sleep(self.rate_limit_delay)
                    
                except Exception as e:
                    print(f"      ❌ 请求失败: {e}")
                    break
        
        return papers
    
    def _parse_work(self, work: Dict) -> Optional[Dict]:
        """解析OpenAlex论文数据"""
        openalex_id = work.get("id", "")
        paper_id = openalex_id.split("/")[-1] if openalex_id else None
        
        if not paper_id:
            return None
        
        # 提取作者
        authors = []
        for authorship in work.get("authorships", [])[:5]:
            author = authorship.get("author", {})
            name = author.get("display_name", "")
            if name:
                authors.append(name)
        
        # 提取摘要
        abstract = ""
        inverted_index = work.get("abstract_inverted_index", {})
        if inverted_index:
            words = []
            for word, positions in inverted_index.items():
                for pos in positions:
                    words.append((pos, word))
            words.sort()
            abstract = " ".join(w[1] for w in words[:500])
        
        # 提取引用
        referenced_works = []
        for ref in work.get("referenced_works", []):
            if isinstance(ref, str) and "openalex.org" in ref:
                ref_id = ref.split("/")[-1]
                referenced_works.append(ref_id)
        
        # 提取venue
        venue = ""
        primary_location = work.get("primary_location", {})
        if primary_location:
            source = primary_location.get("source", {})
            if source:
                venue = source.get("display_name", "")
        
        # 提取概念/主题
        concepts = []
        for concept in work.get("concepts", [])[:10]:
            concepts.append({
                "name": concept.get("display_name", ""),
                "score": concept.get("score", 0)
            })
        
        return {
            "paper_id": paper_id,
            "openalex_id": openalex_id,
            "title": work.get("title", ""),
            "abstract": abstract,
            "authors": authors,
            "year": work.get("publication_year"),
            "venue": venue,
            "citations": work.get("cited_by_count", 0),
            "referenced_works": referenced_works,
            "concepts": concepts,
            "doi": work.get("doi"),
            "type": work.get("type", "")
        }


# ============================================================================
# 论文分类器
# ============================================================================

class PaperClassifier:
    """基于关键词和概念的论文分类器"""
    
    # LLM Tool Use 的分类体系
    CATEGORIES = {
        "Tool Definition & Representation": {
            "keywords": ["tool definition", "api", "function calling", "tool description", 
                        "tool representation", "schema", "specification"],
            "subcategories": {
                "API Design": ["api design", "function signature", "parameter"],
                "Tool Description": ["tool description", "documentation", "specification"]
            }
        },
        "Tool Selection & Planning": {
            "keywords": ["tool selection", "planning", "reasoning", "decision", 
                        "chain of thought", "task decomposition"],
            "subcategories": {
                "Planning Methods": ["planning", "task decomposition", "multi-step"],
                "Selection Strategies": ["tool selection", "tool choice", "retrieval"]
            }
        },
        "Tool Execution & Integration": {
            "keywords": ["tool execution", "integration", "plugin", "external tool",
                        "code execution", "interpreter"],
            "subcategories": {
                "Code Execution": ["code execution", "interpreter", "sandbox"],
                "External APIs": ["external api", "web api", "plugin"]
            }
        },
        "Tool Learning & Adaptation": {
            "keywords": ["tool learning", "fine-tuning", "training", "adaptation",
                        "in-context learning", "few-shot"],
            "subcategories": {
                "Fine-tuning": ["fine-tuning", "training", "supervised"],
                "In-context Learning": ["in-context", "few-shot", "prompt"]
            }
        },
        "Evaluation & Benchmarks": {
            "keywords": ["benchmark", "evaluation", "dataset", "metric",
                        "assessment", "testing"],
            "subcategories": {
                "Benchmarks": ["benchmark", "dataset", "test suite"],
                "Metrics": ["metric", "evaluation", "accuracy"]
            }
        },
        "Applications": {
            "keywords": ["application", "agent", "assistant", "chatbot",
                        "automation", "workflow"],
            "subcategories": {
                "Agents": ["agent", "autonomous", "multi-agent"],
                "Assistants": ["assistant", "chatbot", "copilot"]
            }
        }
    }
    
    def classify_paper(self, paper: Dict) -> Tuple[str, str, float]:
        """
        分类论文
        
        Returns:
            (category, subcategory, confidence)
        """
        title = paper.get("title", "").lower()
        abstract = paper.get("abstract", "").lower()
        text = f"{title} {abstract}"
        
        best_category = "Applications"  # 默认分类
        best_subcategory = "Agents"
        best_score = 0.0
        
        for category, config in self.CATEGORIES.items():
            # 计算主分类得分
            cat_score = sum(1 for kw in config["keywords"] if kw in text)
            
            if cat_score > best_score:
                best_score = cat_score
                best_category = category
                
                # 找最佳子分类
                best_sub_score = 0
                for subcat, sub_keywords in config.get("subcategories", {}).items():
                    sub_score = sum(1 for kw in sub_keywords if kw in text)
                    if sub_score > best_sub_score:
                        best_sub_score = sub_score
                        best_subcategory = subcat
        
        confidence = min(best_score / 5.0, 1.0)  # 归一化置信度
        return best_category, best_subcategory, confidence
    
    def classify_papers(self, papers: List[Dict]) -> Dict[str, Dict[str, List[Dict]]]:
        """批量分类论文"""
        classified = defaultdict(lambda: defaultdict(list))
        
        for paper in papers:
            category, subcategory, confidence = self.classify_paper(paper)
            paper["category"] = category
            paper["subcategory"] = subcategory
            paper["classification_confidence"] = confidence
            classified[category][subcategory].append(paper)
        
        return dict(classified)


# ============================================================================
# 关系类型元数据（21种关系，分5大类）
# ============================================================================

RELATION_METADATA = {
    # 结构关系（Structural）- 基于引用网络
    "cites": {"directed": True, "category": "structural", "requires_llm": False, "color": "#6366f1"},
    "cited_by": {"directed": True, "category": "structural", "requires_llm": False, "color": "#8b5cf6"},
    "co_citation": {"directed": False, "category": "structural", "requires_llm": False, "color": "#a78bfa"},
    "bibliographic_coupling": {"directed": False, "category": "structural", "requires_llm": False, "color": "#c4b5fd"},
    
    # 语义关系（Semantic）- 基于内容分析，需要LLM
    "extends": {"directed": True, "category": "semantic", "requires_llm": True, "color": "#10b981"},
    "improves": {"directed": True, "category": "semantic", "requires_llm": True, "color": "#34d399"},
    "applies": {"directed": True, "category": "semantic", "requires_llm": True, "color": "#6ee7b7"},
    "compares": {"directed": False, "category": "semantic", "requires_llm": True, "color": "#a7f3d0"},
    "combines": {"directed": True, "category": "semantic", "requires_llm": True, "color": "#059669"},
    "reproduces": {"directed": True, "category": "semantic", "requires_llm": True, "color": "#047857"},
    "refutes": {"directed": True, "category": "semantic", "requires_llm": True, "color": "#ef4444"},
    "supports": {"directed": True, "category": "semantic", "requires_llm": True, "color": "#22c55e"},
    
    # 概念关系（Conceptual）- 基于方法论
    "is_variant_of": {"directed": True, "category": "conceptual", "requires_llm": True, "color": "#f59e0b"},
    "is_instance_of": {"directed": True, "category": "conceptual", "requires_llm": True, "color": "#fbbf24"},
    "shares_methodology": {"directed": False, "category": "conceptual", "requires_llm": False, "color": "#fcd34d"},
    "shares_task": {"directed": False, "category": "conceptual", "requires_llm": False, "color": "#fde68a"},
    "shares_dataset": {"directed": False, "category": "conceptual", "requires_llm": False, "color": "#fef3c7"},
    "shares_baseline": {"directed": False, "category": "conceptual", "requires_llm": False, "color": "#d97706"},
    "shares_architecture": {"directed": False, "category": "conceptual", "requires_llm": True, "color": "#b45309"},
    
    # 时序关系（Temporal）- 基于时间演进
    "precedes": {"directed": True, "category": "temporal", "requires_llm": False, "color": "#3b82f6"},
    "succeeds": {"directed": True, "category": "temporal", "requires_llm": False, "color": "#60a5fa"},
    "concurrent": {"directed": False, "category": "temporal", "requires_llm": False, "color": "#93c5fd"},
    
    # 作者关系（Authorship）- 基于作者信息
    "same_author": {"directed": False, "category": "authorship", "requires_llm": False, "color": "#ec4899"},
    "same_group": {"directed": False, "category": "authorship", "requires_llm": False, "color": "#f472b6"},
}

# LLM 关系发现 Prompt
RELATION_DISCOVERY_PROMPT = """你是学术论文关系分析专家。分析以下两篇论文之间的学术关系。

论文A: {title_a} ({year_a})
摘要: {abstract_a}

论文B: {title_b} ({year_b})
摘要: {abstract_b}

请分析这两篇论文之间可能存在的关系。只输出置信度 > 0.6 的关系。

可选的关系类型：
1. extends: A扩展了B的方法/理论（A比B新，A在B基础上增加新功能/场景）
2. improves: A改进了B的性能/效果（A比B新，A在相同任务上取得更好结果）
3. applies: A将B的方法应用到新领域/任务
4. compares: A和B进行了实验对比（通常在同一篇论文中对比）
5. combines: A结合了B和其他方法
6. reproduces: A复现了B的实验
7. refutes: A反驳/质疑了B的结论
8. supports: A验证/支持了B的结论
9. is_variant_of: A是B方法的变体（如BERT和RoBERTa）
10. is_instance_of: A是B方法类别的具体实例
11. shares_architecture: A和B使用相似的模型架构

输出格式（JSON）：
```json
{{
  "relations": [
    {{
      "type": "关系类型",
      "direction": "A->B 或 B->A 或 bidirectional",
      "confidence": 0.6-1.0,
      "evidence": "简短证据说明"
    }}
  ]
}}
```

如果没有明显关系，返回空列表：{{"relations": []}}

只输出JSON，不要其他内容。"""


# ============================================================================
# 关系发现器（支持21种关系类型）
# ============================================================================

class RelationDiscoverer:
    """
    增强版关系发现器 - 支持21种关系类型
    
    发现方式：
    1. 规则发现：结构关系、部分概念关系、时序关系、作者关系
    2. LLM发现：语义关系、部分概念关系
    """
    
    def __init__(self, use_llm: bool = True, max_workers: int = 10):
        self.use_llm = use_llm and HAS_CHAT_AGENT
        self.max_workers = max_workers
        self.chat_agent = None
        
        if self.use_llm:
            try:
                self.chat_agent = ChatAgent()
                print("   ✓ LLM 关系发现已启用")
            except Exception as e:
                print(f"   ⚠️ ChatAgent 初始化失败: {e}")
                self.use_llm = False
        
        # 统计
        self.stats = {
            "rule_discoveries": 0,
            "llm_discoveries": 0,
            "llm_calls": 0,
            "pairs_analyzed": 0,
            "by_category": defaultdict(int),
            "by_type": defaultdict(int)
        }
    
    def discover_relations(
        self,
        papers: List[Dict],
        classified: Dict[str, Dict[str, List[Dict]]],
        max_pairs: int = 500
    ) -> List[HierarchyEdge]:
        """
        发现论文间的所有关系
        
        Args:
            papers: 论文列表
            classified: 分类后的论文
            max_pairs: 最大分析对数（LLM调用限制）
        
        Returns:
            关系列表
        """
        relations = []
        paper_map = {p["paper_id"]: p for p in papers}
        
        print(f"   📊 开始关系发现: {len(papers)} 篇论文")
        
        # 1. 规则发现（快速，不需要LLM）
        print("   🔧 规则发现中...")
        rule_relations = self._discover_by_rules(papers, paper_map)
        relations.extend(rule_relations)
        print(f"      ✓ 规则发现: {len(rule_relations)} 条关系")
        
        # 2. LLM发现（语义关系）
        if self.use_llm and self.chat_agent:
            print("   🤖 LLM语义分析中...")
            llm_relations = self._discover_by_llm(papers, paper_map, max_pairs)
            relations.extend(llm_relations)
            print(f"      ✓ LLM发现: {len(llm_relations)} 条关系")
        
        # 3. 去重合并
        relations = self._merge_relations(relations)
        
        # 打印统计
        self._print_stats()
        
        return relations
    
    def _discover_by_rules(
        self,
        papers: List[Dict],
        paper_map: Dict[str, Dict]
    ) -> List[HierarchyEdge]:
        """规则发现关系"""
        relations = []
        
        for paper in papers:
            paper_id = paper["paper_id"]
            refs = set(paper.get("referenced_works", []))
            year = paper.get("year", 2024)
            
            for ref_id in refs:
                if ref_id not in paper_map:
                    continue
                
                ref_paper = paper_map[ref_id]
                ref_year = ref_paper.get("year", 2024)
                
                # 1. 引用关系 (cites)
                relations.append(HierarchyEdge(
                    source_id=paper_id,
                    target_id=ref_id,
                    relation_type="cites",
                    confidence=1.0,
                    evidence="Direct citation"
                ))
                self.stats["rule_discoveries"] += 1
                self.stats["by_type"]["cites"] += 1
                self.stats["by_category"]["structural"] += 1
                
                # 2. 时序关系
                if year and ref_year:
                    if ref_year < year - 1:
                        relations.append(HierarchyEdge(
                            source_id=ref_id,
                            target_id=paper_id,
                            relation_type="precedes",
                            confidence=0.9,
                            evidence=f"{ref_year} -> {year}"
                        ))
                        self.stats["rule_discoveries"] += 1
                        self.stats["by_type"]["precedes"] += 1
                        self.stats["by_category"]["temporal"] += 1
        
        # 3. 共引关系 (co_citation) - 被同一篇论文引用
        # 4. 书目耦合 (bibliographic_coupling) - 引用相同论文
        relations.extend(self._discover_coupling_relations(papers, paper_map))
        
        # 5. 共享任务关系
        relations.extend(self._discover_shared_task_relations(papers))
        
        # 6. 同作者关系
        relations.extend(self._discover_author_relations(papers))
        
        return relations
    
    def _discover_coupling_relations(
        self,
        papers: List[Dict],
        paper_map: Dict[str, Dict]
    ) -> List[HierarchyEdge]:
        """发现书目耦合关系"""
        relations = []
        
        # 计算每对论文的共同引用数
        paper_ids = list(paper_map.keys())
        for i, pid1 in enumerate(paper_ids):
            refs1 = set(paper_map[pid1].get("referenced_works", []))
            for pid2 in paper_ids[i+1:]:
                refs2 = set(paper_map[pid2].get("referenced_works", []))
                common_refs = refs1 & refs2
                
                if len(common_refs) >= 3:
                    confidence = min(len(common_refs) / 10.0, 1.0)
                    relations.append(HierarchyEdge(
                        source_id=pid1,
                        target_id=pid2,
                        relation_type="bibliographic_coupling",
                        confidence=confidence,
                        evidence=f"Share {len(common_refs)} references"
                    ))
                    self.stats["rule_discoveries"] += 1
                    self.stats["by_type"]["bibliographic_coupling"] += 1
                    self.stats["by_category"]["structural"] += 1
        
        return relations
    
    def _discover_shared_task_relations(
        self,
        papers: List[Dict]
    ) -> List[HierarchyEdge]:
        """发现共享任务关系"""
        relations = []
        
        # 按分类分组
        category_papers = defaultdict(list)
        for paper in papers:
            cat = paper.get("category", "")
            subcat = paper.get("subcategory", "")
            if cat and subcat:
                category_papers[(cat, subcat)].append(paper)
        
        # 同子分类的论文共享任务
        for (cat, subcat), cat_papers in category_papers.items():
            if len(cat_papers) >= 2:
                # 取高引用论文
                sorted_papers = sorted(cat_papers, key=lambda x: x.get("citations", 0), reverse=True)
                top_papers = sorted_papers[:6]
                
                for i, p1 in enumerate(top_papers):
                    for p2 in top_papers[i+1:]:
                        relations.append(HierarchyEdge(
                            source_id=p1["paper_id"],
                            target_id=p2["paper_id"],
                            relation_type="shares_task",
                            confidence=0.7,
                            evidence=f"Same subcategory: {subcat}"
                        ))
                        self.stats["rule_discoveries"] += 1
                        self.stats["by_type"]["shares_task"] += 1
                        self.stats["by_category"]["conceptual"] += 1
        
        return relations
    
    def _discover_author_relations(
        self,
        papers: List[Dict]
    ) -> List[HierarchyEdge]:
        """发现作者关系"""
        relations = []
        
        # 按作者分组
        author_papers = defaultdict(list)
        for paper in papers:
            for author in paper.get("authors", [])[:3]:  # 只看前3作者
                author_papers[author.lower()].append(paper)
        
        # 同作者的论文
        for author, author_pps in author_papers.items():
            if len(author_pps) >= 2:
                for i, p1 in enumerate(author_pps):
                    for p2 in author_pps[i+1:]:
                        relations.append(HierarchyEdge(
                            source_id=p1["paper_id"],
                            target_id=p2["paper_id"],
                            relation_type="same_author",
                            confidence=1.0,
                            evidence=f"Same author: {author}"
                        ))
                        self.stats["rule_discoveries"] += 1
                        self.stats["by_type"]["same_author"] += 1
                        self.stats["by_category"]["authorship"] += 1
        
        return relations
    
    def _discover_by_llm(
        self,
        papers: List[Dict],
        paper_map: Dict[str, Dict],
        max_pairs: int
    ) -> List[HierarchyEdge]:
        """LLM发现语义关系"""
        relations = []
        
        # 生成候选对（优先分析有引用关系的论文对）
        candidates = self._generate_candidate_pairs(papers, paper_map, max_pairs)
        print(f"      📋 候选对数: {len(candidates)}")
        
        if not candidates:
            return relations
        
        # 并发调用LLM
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for pid1, pid2 in candidates:
                if pid1 in paper_map and pid2 in paper_map:
                    future = executor.submit(
                        self._analyze_pair_with_llm,
                        paper_map[pid1],
                        paper_map[pid2]
                    )
                    futures[future] = (pid1, pid2)
            
            for future in tqdm(as_completed(futures), total=len(futures), desc="      LLM分析"):
                try:
                    pair_relations = future.result()
                    relations.extend(pair_relations)
                    self.stats["pairs_analyzed"] += 1
                except Exception as e:
                    pass  # 忽略单个失败
        
        return relations
    
    def _generate_candidate_pairs(
        self,
        papers: List[Dict],
        paper_map: Dict[str, Dict],
        max_pairs: int
    ) -> List[Tuple[str, str]]:
        """生成候选论文对"""
        candidates = set()
        paper_ids = set(paper_map.keys())
        
        # 1. 有引用关系的论文对（最重要）
        for paper in papers:
            pid = paper["paper_id"]
            for ref_id in paper.get("referenced_works", []):
                if ref_id in paper_ids:
                    candidates.add(tuple(sorted([pid, ref_id])))
        
        # 2. 同分类的高引用论文对
        category_papers = defaultdict(list)
        for paper in papers:
            cat = paper.get("category", "")
            if cat:
                category_papers[cat].append(paper)
        
        for cat, cat_papers in category_papers.items():
            sorted_papers = sorted(cat_papers, key=lambda x: x.get("citations", 0), reverse=True)
            top_papers = sorted_papers[:10]
            for i, p1 in enumerate(top_papers):
                for p2 in top_papers[i+1:]:
                    candidates.add(tuple(sorted([p1["paper_id"], p2["paper_id"]])))
        
        # 限制数量
        candidates = list(candidates)
        if len(candidates) > max_pairs:
            import random
            candidates = random.sample(candidates, max_pairs)
        
        return candidates
    
    def _analyze_pair_with_llm(
        self,
        paper_a: Dict,
        paper_b: Dict
    ) -> List[HierarchyEdge]:
        """使用LLM分析论文对"""
        relations = []
        
        if not self.chat_agent:
            return relations
        
        pid_a = paper_a.get("paper_id", "")
        pid_b = paper_b.get("paper_id", "")
        
        # 构建prompt
        prompt = RELATION_DISCOVERY_PROMPT.format(
            title_a=paper_a.get("title", ""),
            year_a=paper_a.get("year", "?"),
            abstract_a=(paper_a.get("abstract", "") or "")[:500],
            title_b=paper_b.get("title", ""),
            year_b=paper_b.get("year", "?"),
            abstract_b=(paper_b.get("abstract", "") or "")[:500]
        )
        
        try:
            self.stats["llm_calls"] += 1
            response = self.chat_agent.remote_chat(prompt, temperature=0.3)
            relations = self._parse_llm_response(response, pid_a, pid_b)
        except Exception as e:
            pass  # 忽略LLM错误
        
        return relations
    
    def _parse_llm_response(
        self,
        response: str,
        pid_a: str,
        pid_b: str
    ) -> List[HierarchyEdge]:
        """解析LLM响应"""
        relations = []
        
        try:
            # 提取JSON
            match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                json_str = response
            
            data = json.loads(json_str)
            
            for rel in data.get("relations", []):
                rel_type = rel.get("type", "")
                
                # 只接受需要LLM的关系类型
                if rel_type not in RELATION_METADATA:
                    continue
                if not RELATION_METADATA[rel_type].get("requires_llm", False):
                    continue
                
                direction = rel.get("direction", "A->B")
                confidence = float(rel.get("confidence", 0.5))
                evidence = rel.get("evidence", "")
                
                if confidence < 0.6:
                    continue
                
                # 确定方向
                is_directed = RELATION_METADATA[rel_type]["directed"]
                if is_directed:
                    if direction == "A->B":
                        src, tgt = pid_a, pid_b
                    elif direction == "B->A":
                        src, tgt = pid_b, pid_a
                    else:
                        continue
                else:
                    src, tgt = sorted([pid_a, pid_b])
                
                relations.append(HierarchyEdge(
                    source_id=src,
                    target_id=tgt,
                    relation_type=rel_type,
                    confidence=confidence,
                    evidence=evidence
                ))
                
                self.stats["llm_discoveries"] += 1
                self.stats["by_type"][rel_type] += 1
                self.stats["by_category"][RELATION_METADATA[rel_type]["category"]] += 1
                
        except Exception as e:
            pass  # 解析失败忽略
        
        return relations
    
    def _merge_relations(
        self,
        relations: List[HierarchyEdge]
    ) -> List[HierarchyEdge]:
        """去重合并关系"""
        grouped = {}
        
        for rel in relations:
            is_directed = RELATION_METADATA.get(rel.relation_type, {}).get("directed", True)
            
            if is_directed:
                key = (rel.source_id, rel.target_id, rel.relation_type)
            else:
                key = (min(rel.source_id, rel.target_id), max(rel.source_id, rel.target_id), rel.relation_type)
            
            if key not in grouped or rel.confidence > grouped[key].confidence:
                grouped[key] = rel
        
        return list(grouped.values())
    
    def _print_stats(self):
        """打印统计信息"""
        print(f"\n   📊 关系发现统计:")
        print(f"      规则发现: {self.stats['rule_discoveries']}")
        print(f"      LLM发现: {self.stats['llm_discoveries']}")
        print(f"      LLM调用: {self.stats['llm_calls']}")
        print(f"      分析对数: {self.stats['pairs_analyzed']}")
        print(f"\n      按类别:")
        for cat, count in sorted(self.stats['by_category'].items()):
            print(f"         {cat}: {count}")
        print(f"\n      按类型:")
        for rel_type, count in sorted(self.stats['by_type'].items(), key=lambda x: -x[1]):
            print(f"         {rel_type}: {count}")


# ============================================================================
# 层级构建器
# ============================================================================

class SurveyHierarchyBuilder:
    """综述层级构建器"""
    
    def __init__(self):
        self.nodes: Dict[str, HierarchyNode] = {}
        self.edges: List[HierarchyEdge] = []
        self.root: Optional[HierarchyNode] = None
    
    def build_from_classified_papers(
        self,
        topic: str,
        classified: Dict[str, Dict[str, List[Dict]]],
        relations: List[HierarchyEdge]
    ) -> HierarchyNode:
        """从分类后的论文构建层级"""
        # 创建根节点
        self.root = HierarchyNode(
            id=f"topic_{topic.replace(' ', '_')}",
            title=topic,
            level=0,
            node_type='topic'
        )
        self.nodes[self.root.id] = self.root
        
        # 创建分类层级
        for category, subcategories in classified.items():
            cat_node = HierarchyNode(
                id=f"cat_{category.replace(' ', '_').replace('&', 'and')}",
                title=category,
                level=1,
                node_type='category',
                parent=self.root
            )
            self.nodes[cat_node.id] = cat_node
            self.root.children.append(cat_node)
            
            for subcategory, papers in subcategories.items():
                if not papers:
                    continue
                
                # 如果论文数量少，直接挂在分类下
                if len(papers) <= 3:
                    for paper in papers:
                        paper_node = self._create_paper_node(paper, cat_node)
                        cat_node.children.append(paper_node)
                else:
                    # 创建子分类
                    subcat_node = HierarchyNode(
                        id=f"subcat_{subcategory.replace(' ', '_')}",
                        title=subcategory,
                        level=2,
                        node_type='subcategory',
                        parent=cat_node
                    )
                    self.nodes[subcat_node.id] = subcat_node
                    cat_node.children.append(subcat_node)
                    
                    # 按引用数排序，取top论文
                    sorted_papers = sorted(papers, key=lambda x: x.get("citations", 0), reverse=True)
                    top_papers = sorted_papers[:8]  # 每个子分类最多8篇
                    
                    for paper in top_papers:
                        paper_node = self._create_paper_node(paper, subcat_node)
                        subcat_node.children.append(paper_node)
        
        # 过滤关系（只保留图中存在的节点）
        valid_paper_ids = {n.id for n in self.nodes.values() if n.node_type == 'paper'}
        self.edges = [
            e for e in relations
            if e.source_id in valid_paper_ids and e.target_id in valid_paper_ids
        ]
        
        return self.root
    
    def _create_paper_node(self, paper: Dict, parent: HierarchyNode) -> HierarchyNode:
        """创建论文节点"""
        node = HierarchyNode(
            id=paper["paper_id"],
            title=paper.get("title", paper["paper_id"])[:60],
            level=parent.level + 1,
            node_type='paper',
            parent=parent,
            metadata={
                'year': paper.get('year'),
                'citations': paper.get('citations', 0),
                'authors': paper.get('authors', []),
                'venue': paper.get('venue', ''),
                'full_title': paper.get('title', ''),
                'abstract': paper.get('abstract', '')[:300]
            }
        )
        self.nodes[node.id] = node
        return node


# ============================================================================
# 布局引擎
# ============================================================================

class HierarchyLayoutEngine:
    """层级布局引擎"""
    
    def __init__(self, level_height: float = 2.5, node_spacing: float = 2.0,
                 min_node_width: float = 2.5, max_node_width: float = 8.0):
        self.level_height = level_height
        self.node_spacing = node_spacing
        self.min_node_width = min_node_width
        self.max_node_width = max_node_width
    
    def layout(self, root: HierarchyNode) -> Dict[str, Tuple[float, float, float, float]]:
        """计算所有节点的布局位置"""
        positions = {}
        subtree_widths = self._calculate_subtree_widths(root)
        self._assign_positions(root, 0, subtree_widths, positions)
        return positions
    
    def _calculate_subtree_widths(self, node: HierarchyNode) -> Dict[str, float]:
        widths = {}
        
        def calc_width(n: HierarchyNode) -> float:
            if not n.children:
                width = self._get_node_width(n)
            else:
                children_width = sum(calc_width(c) for c in n.children)
                children_width += self.node_spacing * (len(n.children) - 1)
                width = max(children_width, self._get_node_width(n))
            widths[n.id] = width
            return width
        
        calc_width(node)
        return widths
    
    def _get_node_width(self, node: HierarchyNode) -> float:
        base_width = len(node.title) * 0.1
        if node.node_type == 'topic':
            return max(self.max_node_width, base_width)
        elif node.node_type == 'category':
            return max(self.min_node_width * 1.5, min(base_width, self.max_node_width))
        elif node.node_type == 'subcategory':
            return max(self.min_node_width * 1.2, min(base_width, self.max_node_width * 0.8))
        else:
            return max(self.min_node_width, min(base_width, self.max_node_width * 0.6))
    
    def _assign_positions(self, node: HierarchyNode, x_offset: float,
                          subtree_widths: Dict[str, float],
                          positions: Dict[str, Tuple[float, float, float, float]]):
        width = self._get_node_width(node)
        height = 0.6 if node.node_type == 'paper' else 0.8
        
        subtree_width = subtree_widths[node.id]
        x = x_offset + subtree_width / 2
        y = -node.level * self.level_height
        
        positions[node.id] = (x, y, width, height)
        node.x = x
        node.y = y
        node.width = width
        node.height = height
        
        if node.children:
            child_x = x_offset
            for child in node.children:
                child_width = subtree_widths[child.id]
                self._assign_positions(child, child_x, subtree_widths, positions)
                child_x += child_width + self.node_spacing


# ============================================================================
# HTML渲染器
# ============================================================================

class SurveyHierarchyRenderer:
    """综述层级可视化渲染器"""
    
    def __init__(self):
        self.template_path = Path(__file__).parent.parent.parent / 'src' / 'visualization' / 'templates' / 'hierarchy_template.html'
    
    def render_html(self, root: HierarchyNode, edges: List[HierarchyEdge],
                    positions: Dict[str, Tuple[float, float, float, float]],
                    output_path: Path, title: str) -> str:
        """生成交互式HTML可视化"""
        all_nodes = self._collect_all_nodes(root)
        
        nodes_data = []
        for node in all_nodes:
            pos = positions[node.id]
            nodes_data.append({
                'id': node.id,
                'title': node.title,
                'fullTitle': node.metadata.get('full_title', node.title) if node.metadata else node.title,
                'type': node.node_type,
                'level': node.level,
                'x': pos[0] * 100,
                'y': -pos[1] * 100,
                'width': pos[2] * 100,
                'height': pos[3] * 100,
                'year': node.metadata.get('year') if node.metadata else None,
                'citations': node.metadata.get('citations', 0) if node.metadata else 0,
                'parentId': node.parent.id if node.parent else None
            })
        
        edges_data = []
        for edge in edges:
            if edge.source_id in positions and edge.target_id in positions:
                edges_data.append({
                    'source': edge.source_id,
                    'target': edge.target_id,
                    'type': edge.relation_type,
                    'confidence': edge.confidence,
                    'evidence': edge.evidence
                })
        
        hierarchy_edges = []
        for node in all_nodes:
            if node.parent:
                hierarchy_edges.append({
                    'source': node.parent.id,
                    'target': node.id,
                    'type': 'hierarchy'
                })
        
        template = self._load_template()
        html_content = template.replace('{{TITLE}}', title)
        html_content = html_content.replace('{{NODES_DATA}}', json.dumps(nodes_data, ensure_ascii=False, indent=2))
        html_content = html_content.replace('{{EDGES_DATA}}', json.dumps(edges_data, ensure_ascii=False, indent=2))
        html_content = html_content.replace('{{HIERARCHY_DATA}}', json.dumps(hierarchy_edges, ensure_ascii=False, indent=2))
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"✅ 交互式HTML已保存到: {output_path}")
        return str(output_path)
    
    def _collect_all_nodes(self, root: HierarchyNode) -> List[HierarchyNode]:
        nodes = [root]
        for child in root.children:
            nodes.extend(self._collect_all_nodes(child))
        return nodes
    
    def _load_template(self) -> str:
        if self.template_path.exists():
            with open(self.template_path, 'r', encoding='utf-8') as f:
                return f.read()
        raise FileNotFoundError(f"模板文件不存在: {self.template_path}")


# ============================================================================
# 主流程
# ============================================================================

def print_hierarchy(node, indent=0):
    """打印层级结构"""
    prefix = "  " * indent
    type_emoji = {
        'topic': '🎯',
        'category': '📁',
        'subcategory': '📂',
        'paper': '📄'
    }
    emoji = type_emoji.get(node.node_type, '•')
    
    extra = ""
    if node.node_type == 'paper' and node.metadata:
        year = node.metadata.get('year', '')
        citations = node.metadata.get('citations', 0)
        if year or citations:
            extra = f" ({year}, {citations} cites)"
    
    print(f"{prefix}{emoji} {node.title}{extra}")
    
    for child in node.children:
        print_hierarchy(child, indent + 1)


async def main():
    """主函数"""
    print("=" * 70)
    print("🚀 LLM Tool Use Survey 构建流程")
    print("=" * 70)
    
    topic = "LLM Tool Use"
    
    # 1. 爬取论文
    print("\n📥 步骤1: 从 OpenAlex 爬取论文...")
    crawler = OpenAlexCrawler()
    
    # 搜索多个相关查询
    queries = [
        "large language model tool use",
        "LLM function calling",
        "language model API integration",
        "tool-augmented language model",
        "LLM agent tool"
    ]
    
    all_papers = []
    seen_ids = set()
    
    for query in queries:
        print(f"\n   🔍 搜索: {query}")
        papers = await crawler.search_papers(query, limit=30, year_start=2022)
        for paper in papers:
            if paper["paper_id"] not in seen_ids:
                all_papers.append(paper)
                seen_ids.add(paper["paper_id"])
        print(f"   ✓ 获取 {len(papers)} 篇，累计 {len(all_papers)} 篇")
    
    print(f"\n   📊 总计获取 {len(all_papers)} 篇论文")
    
    # 2. 分类论文
    print("\n📊 步骤2: 分类论文...")
    classifier = PaperClassifier()
    classified = classifier.classify_papers(all_papers)
    
    for cat, subcats in classified.items():
        total = sum(len(papers) for papers in subcats.values())
        print(f"   📁 {cat}: {total} 篇")
        for subcat, papers in subcats.items():
            print(f"      📂 {subcat}: {len(papers)} 篇")
    
    # 3. 发现关系（使用LLM发现21种关系类型）
    print("\n🔗 步骤3: 发现论文间关系（21种类型）...")
    
    # 检查LLM可用性
    use_llm = True
    if HAS_CHAT_AGENT:
        print("   💡 检测到 ChatAgent，将使用 LLM 发现语义关系")
    else:
        print("   ⚠️ ChatAgent 不可用，仅使用规则发现")
        use_llm = False
    
    relation_discoverer = RelationDiscoverer(use_llm=use_llm, max_workers=10)
    relations = relation_discoverer.discover_relations(all_papers, classified, max_pairs=300)
    
    print(f"\n   ✅ 总计发现 {len(relations)} 条关系")
    
    # 4. 构建层级
    print("\n🏗️ 步骤4: 构建层级结构...")
    builder = SurveyHierarchyBuilder()
    root = builder.build_from_classified_papers(topic, classified, relations)
    
    print(f"   ✓ 根节点: {root.title}")
    print(f"   ✓ 总节点数: {len(builder.nodes)}")
    print(f"   ✓ 有效关系数: {len(builder.edges)}")
    
    # 打印层级预览
    print("\n📋 层级结构预览:")
    print_hierarchy(root, indent=0)
    
    # 5. 计算布局
    print("\n📐 步骤5: 计算布局...")
    layout_engine = HierarchyLayoutEngine()
    positions = layout_engine.layout(root)
    print(f"   ✓ 已计算 {len(positions)} 个节点的位置")
    
    # 6. 渲染HTML
    print("\n🎨 步骤6: 渲染HTML可视化...")
    renderer = SurveyHierarchyRenderer()
    
    output_dir = project_root / 'outputs' / 'visualization'
    output_path = output_dir / 'llm_tool_use_survey_hierarchy.html'
    
    renderer.render_html(
        root=root,
        edges=builder.edges,
        positions=positions,
        output_path=output_path,
        title="LLM Tool Use - Survey Structure"
    )
    
    # 7. 保存数据
    print("\n💾 步骤7: 保存数据...")
    data_path = output_dir / 'llm_tool_use_data.json'
    
    # 统计关系类型
    relation_stats = defaultdict(int)
    relation_by_category = defaultdict(int)
    for rel in relations:
        relation_stats[rel.relation_type] += 1
        if rel.relation_type in RELATION_METADATA:
            relation_by_category[RELATION_METADATA[rel.relation_type]["category"]] += 1
    
    save_data = {
        "topic": topic,
        "papers_count": len(all_papers),
        "nodes_count": len(builder.nodes),
        "relations_count": len(builder.edges),
        "relation_stats": {
            "by_type": dict(relation_stats),
            "by_category": dict(relation_by_category),
            "discovery_stats": relation_discoverer.stats
        },
        "categories": {
            cat: {
                subcat: len(papers)
                for subcat, papers in subcats.items()
            }
            for cat, subcats in classified.items()
        },
        "papers": [
            {
                "id": p["paper_id"],
                "title": p["title"],
                "year": p.get("year"),
                "citations": p.get("citations", 0),
                "category": p.get("category"),
                "subcategory": p.get("subcategory")
            }
            for p in all_papers
        ],
        "relations": [
            {
                "source": rel.source_id,
                "target": rel.target_id,
                "type": rel.relation_type,
                "confidence": rel.confidence,
                "evidence": rel.evidence
            }
            for rel in relations
        ]
    }
    
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    print(f"   ✓ 数据已保存到: {data_path}")
    
    print("\n" + "=" * 70)
    print("✅ LLM Tool Use Survey 构建完成!")
    print(f"📁 可视化文件: {output_path}")
    print(f"📁 数据文件: {data_path}")
    print("\n💡 提示: 用浏览器打开HTML文件查看交互式可视化")
    print("=" * 70)
    
    return output_path


if __name__ == '__main__':
    asyncio.run(main())