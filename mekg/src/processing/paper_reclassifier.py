"""
论文重分类模块
==============

基于大纲结构使用 LLM 重新分类论文，使得 MEKG 的分类体系更加系统化。

原理说明：
1. 分类体系生成：
   - 读取 outline.json 中的章节结构
   - 提取技术性章节（排除 Introduction/Conclusion/Background）
   - 使用 LLM 基于大纲生成适合论文分类的 Taxonomy

2. 论文分类：
   - 对每篇论文，使用 LLM 判断其属于哪些分类
   - 一篇论文可以属于 1-3 个分类（多标签分类）
   - 使用模糊匹配确保分类名称的鲁棒性

3. 数据结构：
   - categories: {category: {subcategory: count}}
   - 每篇论文的 all_categories 字段保存所有分类
   - 第一个分类作为主分类（category/subcategory 字段）

使用方法：
    from mekg.src.processing.paper_reclassifier import PaperReclassifier
    
    reclassifier = PaperReclassifier(chat_agent=chat_agent)
    new_mekg_data = reclassifier.reclassify(mekg_data, outline_data, topic)
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict

from src.configs.config import DEFAULT_CHATAGENT_MODEL


# ============================================================================
# 配置
# ============================================================================

# 并发数
DEFAULT_MAX_WORKERS = 100

# LLM 模型（用于分类）
DEFAULT_CLASSIFICATION_MODEL = DEFAULT_CHATAGENT_MODEL

# 重试次数
MAX_RETRIES = 2

# 模糊匹配阈值
FUZZY_MATCH_THRESHOLD = 0.7


# ============================================================================
# Prompt 模板
# ============================================================================

GENERATE_TAXONOMY_PROMPT = """你是一个学术论文分类专家。请根据以下综述大纲，生成一个适合论文分类的分类体系（Taxonomy）。

综述主题: {topic}

综述大纲:
{outline_text}

要求:
1. 生成 5-8 个主要分类（Category），每个分类有 2-4 个子分类（Subcategory）
2. 分类应该直接对应大纲中的技术章节，确保每个技术章节都有对应的分类
3. 分类名称应该简洁明了（英文，2-5个单词）
4. 排除非技术性章节（Introduction, Conclusion, Background, Related Work）
5. 每个分类必须有明确的技术含义

重要：分类体系必须能够覆盖该领域的所有论文类型！

输出格式（JSON）:
```json
{{
  "taxonomy": [
    {{
      "category": "Category Name",
      "description": "One sentence description",
      "subcategories": [
        {{"name": "Subcategory 1", "description": "Description"}},
        {{"name": "Subcategory 2", "description": "Description"}}
      ]
    }}
  ]
}}
```

只输出 JSON，不要其他内容。"""


CLASSIFY_PAPER_PROMPT = """你是一个学术论文分类专家。请将以下论文分类到给定的分类体系中。

论文标题: {title}

论文摘要: {abstract}

分类体系（必须从以下分类中选择）:
{taxonomy_text}

要求:
1. 必须至少选择 1 个分类，最多选择 3 个分类
2. 只选择论文确实相关的分类
3. category 和 subcategory 名称必须与上面的分类体系完全一致
4. confidence 表示相关程度（0.5-1.0）

输出格式（JSON）:
```json
{{
  "classifications": [
    {{"category": "分类名称", "subcategory": "子分类名称", "confidence": 0.9}}
  ]
}}
```

只输出 JSON，不要其他内容。"""


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class TaxonomyNode:
    """分类节点"""
    name: str
    description: str = ""
    subcategories: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class PaperClassification:
    """论文分类结果"""
    paper_id: str
    classifications: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""


# ============================================================================
# 工具函数
# ============================================================================

def fuzzy_match(s1: str, s2: str) -> float:
    """计算两个字符串的相似度"""
    return SequenceMatcher(None, s1.lower().strip(), s2.lower().strip()).ratio()


def find_best_match(target: str, candidates: Set[str], threshold: float = FUZZY_MATCH_THRESHOLD) -> Optional[str]:
    """在候选集中找到最佳匹配"""
    best_match = None
    best_score = 0
    
    for candidate in candidates:
        score = fuzzy_match(target, candidate)
        if score > best_score and score >= threshold:
            best_score = score
            best_match = candidate
    
    return best_match


# ============================================================================
# 核心类
# ============================================================================

class PaperReclassifier:
    """
    论文重分类器
    
    基于大纲结构使用 LLM 重新分类论文，使得 MEKG 的分类体系更加系统化。
    """
    
    def __init__(
        self,
        chat_agent=None,
        max_workers: int = DEFAULT_MAX_WORKERS,
        classification_model: str = DEFAULT_CLASSIFICATION_MODEL
    ):
        """
        初始化重分类器
        
        Args:
            chat_agent: ChatAgent 实例
            max_workers: 并发数
            classification_model: 用于分类的 LLM 模型
        """
        self.chat_agent = chat_agent
        self.max_workers = max_workers
        self.classification_model = classification_model
        
        self.taxonomy: List[TaxonomyNode] = []
        self.taxonomy_text = ""
        
        # 用于快速查找的集合
        self.valid_categories: Set[str] = set()
        self.valid_subcategories: Dict[str, Set[str]] = {}
        
        # 统计
        self.stats = {
            "total_papers": 0,
            "classified_papers": 0,
            "failed_papers": 0,
            "llm_calls": 0,
            "multi_class_papers": 0,
            "fuzzy_matched": 0,
            "retries": 0,
        }

    def _has_no_retry_chat(self) -> bool:
        return callable(getattr(self.chat_agent, "remote_chat_no_retry", None))

    def _llm_attempt_count(self) -> int:
        return 1 if self._has_no_retry_chat() else MAX_RETRIES + 1

    def _remote_chat_once(self, prompt: str, **kwargs) -> str:
        chat_once = getattr(self.chat_agent, "remote_chat_no_retry", None)
        if callable(chat_once):
            return chat_once(prompt, **kwargs)
        return self.chat_agent.remote_chat(prompt, **kwargs)
    
    def reclassify(
        self,
        mekg_data: Dict,
        outline_data: Dict,
        topic: str,
        verbose: bool = True
    ) -> Dict:
        """
        重新分类论文
        
        Args:
            mekg_data: MEKG 数据（包含 papers 和 relations）
            outline_data: 大纲数据（SurveyOutline 格式或 dict）
            topic: 综述主题
            verbose: 是否打印详细信息
            
        Returns:
            更新后的 MEKG 数据
        """
        if not self.chat_agent:
            if verbose:
                print("   ⚠️ ChatAgent 不可用，跳过论文重分类")
            return mekg_data
        
        if verbose:
            print("   🔄 开始论文重分类...")
        
        # 重置统计
        self.stats = {
            "total_papers": 0,
            "classified_papers": 0,
            "failed_papers": 0,
            "llm_calls": 0,
            "multi_class_papers": 0,
            "fuzzy_matched": 0,
            "retries": 0,
        }
        
        # 1. 生成分类体系
        self._generate_taxonomy(outline_data, topic, verbose)
        
        if not self.taxonomy:
            if verbose:
                print("   ⚠️ 分类体系生成失败，跳过重分类")
            return mekg_data
        
        # 2. 并发分类论文
        papers = mekg_data.get("papers", [])
        classification_results = self._classify_papers_concurrent(papers, verbose)
        
        # 3. 构建新的 MEKG 数据
        new_mekg_data = self._build_new_mekg_data(mekg_data, classification_results)
        
        if verbose:
            self._print_stats()
        
        return new_mekg_data
    
    def _generate_taxonomy(self, outline_data: Dict, topic: str, verbose: bool = True):
        """使用 LLM 生成分类体系"""
        if verbose:
            print("   📋 生成分类体系...")
        
        # 构建大纲文本（只包含技术性章节）
        outline_text = self._build_outline_text(outline_data)
        
        if not outline_text.strip():
            if verbose:
                print("   ⚠️ 大纲为空，使用默认分类体系")
            self._use_default_taxonomy()
            return
        
        # 调用 LLM
        prompt = GENERATE_TAXONOMY_PROMPT.format(
            topic=topic,
            outline_text=outline_text
        )
        
        max_attempts = self._llm_attempt_count()
        for attempt in range(max_attempts):
            try:
                response = self._remote_chat_once(prompt, temperature=0.3)
                self.stats["llm_calls"] += 1
                
                # 解析 JSON
                match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
                if match:
                    json_str = match.group(1)
                else:
                    match = re.search(r'\{[\s\S]*\}', response)
                    if match:
                        json_str = match.group()
                    else:
                        raise ValueError("No JSON found in response")
                
                data = json.loads(json_str)
                taxonomy_list = data.get("taxonomy", [])
                
                if not taxonomy_list:
                    raise ValueError("Empty taxonomy")
                
                # 转换为 TaxonomyNode
                self.taxonomy = []
                for item in taxonomy_list:
                    node = TaxonomyNode(
                        name=item.get("category", ""),
                        description=item.get("description", ""),
                        subcategories=item.get("subcategories", [])
                    )
                    if node.name and node.subcategories:
                        self.taxonomy.append(node)
                
                # 构建查找集合
                self._build_lookup_sets()
                
                # 构建分类文本（用于后续分类）
                self._build_taxonomy_text()
                
                if verbose:
                    print(f"   ✓ 生成了 {len(self.taxonomy)} 个主分类")
                    for node in self.taxonomy:
                        print(f"      📁 {node.name}: {len(node.subcategories)} 个子分类")
                
                return
                
            except Exception as e:
                if attempt < max_attempts - 1:
                    if verbose:
                        print(f"   ⚠️ 生成失败 (尝试 {attempt + 1}/{max_attempts}): {e}")
                    self.stats["retries"] += 1
                    time.sleep(1)
                else:
                    if verbose:
                        print(f"   ⚠️ 生成分类体系失败: {e}，使用默认分类体系")
                    self._use_default_taxonomy()
    
    def _build_outline_text(self, outline_data: Dict) -> str:
        """从大纲数据构建文本"""
        outline_text = ""
        skip_keywords = ['introduction', 'conclusion', 'background', 'related work', 'preliminaries']
        
        # 支持两种格式：SurveyOutline 格式和 dict 格式
        sections = outline_data.get('sections', [])
        
        for section in sections:
            title = section.get('title', '')
            
            # 跳过非技术性章节
            if any(kw in title.lower() for kw in skip_keywords):
                continue
            
            desc = section.get('description', '')[:300]
            number = section.get('number', '')
            outline_text += f"\n## {number}. {title}\n"
            outline_text += f"   {desc}\n"
            
            for subsection in section.get('subsections', []):
                sub_title = subsection.get('title', '')
                sub_desc = subsection.get('description', '')[:200]
                sub_number = subsection.get('number', '')
                outline_text += f"   ### {sub_number} {sub_title}\n"
                outline_text += f"       {sub_desc}\n"
        
        return outline_text
    
    def _build_lookup_sets(self):
        """构建用于快速查找的集合"""
        self.valid_categories = {node.name for node in self.taxonomy}
        self.valid_subcategories = {}
        for node in self.taxonomy:
            self.valid_subcategories[node.name] = {
                sub.get("name", "") for sub in node.subcategories
            }
    
    def _build_taxonomy_text(self):
        """构建分类体系文本"""
        lines = []
        for i, node in enumerate(self.taxonomy, 1):
            lines.append(f"{i}. 【{node.name}】: {node.description}")
            for j, sub in enumerate(node.subcategories, 1):
                lines.append(f"   {i}.{j} {sub.get('name', '')}: {sub.get('description', '')}")
        self.taxonomy_text = "\n".join(lines)
    
    def _use_default_taxonomy(self):
        """使用默认分类体系（备用）"""
        self.taxonomy = [
            TaxonomyNode(
                name="Core Methods",
                description="Core technical methods and algorithms",
                subcategories=[
                    {"name": "Architecture Design", "description": "Model architecture and design"},
                    {"name": "Training Methods", "description": "Training and optimization methods"},
                    {"name": "Inference Methods", "description": "Inference and deployment methods"}
                ]
            ),
            TaxonomyNode(
                name="Applications",
                description="Real-world applications and use cases",
                subcategories=[
                    {"name": "Domain Applications", "description": "Domain-specific applications"},
                    {"name": "Task Applications", "description": "Task-specific applications"}
                ]
            ),
            TaxonomyNode(
                name="Evaluation",
                description="Benchmarks, datasets, and evaluation methods",
                subcategories=[
                    {"name": "Benchmarks", "description": "Evaluation benchmarks and datasets"},
                    {"name": "Metrics", "description": "Evaluation metrics and methods"}
                ]
            ),
            TaxonomyNode(
                name="Analysis",
                description="Analysis and understanding",
                subcategories=[
                    {"name": "Empirical Analysis", "description": "Empirical studies and analysis"},
                    {"name": "Theoretical Analysis", "description": "Theoretical analysis and proofs"}
                ]
            ),
        ]
        self._build_lookup_sets()
        self._build_taxonomy_text()
    
    def _validate_and_fix_classification(self, cls: Dict) -> Optional[Dict]:
        """验证并修复分类结果"""
        cat = cls.get("category", "").strip()
        subcat = cls.get("subcategory", "").strip()
        confidence = cls.get("confidence", 0.5)
        
        if not cat:
            return None
        
        # 精确匹配
        if cat in self.valid_categories:
            if cat in self.valid_subcategories:
                if subcat in self.valid_subcategories[cat]:
                    return {"category": cat, "subcategory": subcat, "confidence": confidence}
                else:
                    # 子分类模糊匹配
                    matched_subcat = find_best_match(subcat, self.valid_subcategories[cat])
                    if matched_subcat:
                        self.stats["fuzzy_matched"] += 1
                        return {"category": cat, "subcategory": matched_subcat, "confidence": confidence}
                    # 使用第一个子分类
                    if self.valid_subcategories[cat]:
                        first_subcat = list(self.valid_subcategories[cat])[0]
                        return {"category": cat, "subcategory": first_subcat, "confidence": confidence * 0.8}
            return None
        
        # 分类模糊匹配
        matched_cat = find_best_match(cat, self.valid_categories)
        if matched_cat:
            self.stats["fuzzy_matched"] += 1
            return self._validate_and_fix_classification({
                "category": matched_cat,
                "subcategory": subcat,
                "confidence": confidence * 0.9
            })
        
        return None
    
    def _classify_paper(self, paper: Dict) -> PaperClassification:
        """使用 LLM 分类单篇论文"""
        paper_id = paper.get("id", "")
        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        
        # 使用更多内容
        if len(abstract) < 200:
            md_text = paper.get("md_text", "")
            if md_text:
                abstract = md_text[:1500]
        else:
            abstract = abstract[:1200]
        
        if not title:
            return PaperClassification(paper_id=paper_id, error="No title")
        
        prompt = CLASSIFY_PAPER_PROMPT.format(
            title=title,
            abstract=abstract,
            taxonomy_text=self.taxonomy_text
        )
        
        max_attempts = self._llm_attempt_count()
        for attempt in range(max_attempts):
            try:
                response = self._remote_chat_once(
                    prompt,
                    temperature=0.2,
                    model=self.classification_model
                )
                self.stats["llm_calls"] += 1
                
                # 解析 JSON
                match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
                if match:
                    json_str = match.group(1)
                else:
                    match = re.search(r'\{[\s\S]*\}', response)
                    if match:
                        json_str = match.group()
                    else:
                        raise ValueError("No JSON found")
                
                data = json.loads(json_str)
                raw_classifications = data.get("classifications", [])
                
                # 验证并修复分类
                valid_classifications = []
                seen = set()
                
                for cls in raw_classifications:
                    fixed = self._validate_and_fix_classification(cls)
                    if fixed:
                        key = (fixed["category"], fixed["subcategory"])
                        if key not in seen:
                            seen.add(key)
                            valid_classifications.append(fixed)
                
                # 按置信度排序
                valid_classifications.sort(key=lambda x: x.get("confidence", 0), reverse=True)
                
                # 限制最多 3 个分类
                valid_classifications = valid_classifications[:3]
                
                if valid_classifications:
                    return PaperClassification(paper_id=paper_id, classifications=valid_classifications)
                else:
                    raise ValueError("No valid classifications")
                
            except Exception as e:
                if attempt < max_attempts - 1:
                    self.stats["retries"] += 1
                    time.sleep(0.5)
                else:
                    return PaperClassification(paper_id=paper_id, error=str(e))
        
        return PaperClassification(paper_id=paper_id, error="Max retries exceeded")
    
    def _classify_papers_concurrent(self, papers: List[Dict], verbose: bool = True) -> Dict[str, PaperClassification]:
        """并发分类所有论文"""
        if verbose:
            print(f"   🚀 并发分类 {len(papers)} 篇论文 (并发数: {self.max_workers})...")
        
        results = {}
        self.stats["total_papers"] = len(papers)
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._classify_paper, paper): paper.get("id", f"paper_{i}")
                for i, paper in enumerate(papers)
            }
            
            completed = 0
            for future in as_completed(futures):
                paper_id = futures[future]
                try:
                    result = future.result()
                    results[paper_id] = result
                    
                    if result.classifications:
                        self.stats["classified_papers"] += 1
                        if len(result.classifications) > 1:
                            self.stats["multi_class_papers"] += 1
                    else:
                        self.stats["failed_papers"] += 1
                        
                except Exception as e:
                    self.stats["failed_papers"] += 1
                    results[paper_id] = PaperClassification(paper_id=paper_id, error=str(e))
                
                completed += 1
                if verbose and completed % 20 == 0:
                    print(f"      进度: {completed}/{len(papers)}")
        
        elapsed = time.time() - start_time
        if verbose:
            print(f"   ✓ 分类完成! 耗时: {elapsed:.1f}s ({elapsed/max(1, len(papers))*1000:.1f}ms/篇)")
        
        return results
    
    def _build_new_mekg_data(
        self,
        original_data: Dict,
        classification_results: Dict[str, PaperClassification]
    ) -> Dict:
        """构建新的 MEKG 数据"""
        # 构建新的 categories 结构
        new_categories = defaultdict(lambda: defaultdict(int))
        
        # 更新论文数据
        new_papers = []
        for paper in original_data.get("papers", []):
            paper_id = paper.get("id", "")
            
            # 获取分类结果
            if paper_id in classification_results:
                cls_result = classification_results[paper_id]
                classifications = cls_result.classifications
            else:
                classifications = []
            
            # 如果有分类结果，使用第一个作为主分类
            if classifications:
                primary = classifications[0]
                paper["category"] = primary.get("category", "")
                paper["subcategory"] = primary.get("subcategory", "")
                paper["all_categories"] = classifications
                
                # 更新 categories 统计（每个分类都计数）
                for cls in classifications:
                    cat = cls.get("category", "")
                    subcat = cls.get("subcategory", "")
                    if cat and subcat:
                        new_categories[cat][subcat] += 1
            else:
                # 分类失败，放入 "Other" 分类
                paper["category"] = "Other"
                paper["subcategory"] = "Uncategorized"
                paper["all_categories"] = []
                new_categories["Other"]["Uncategorized"] += 1
            
            new_papers.append(paper)
        
        # 构建新的 MEKG 数据
        new_data = {
            "topic": original_data.get("topic", ""),
            "papers_count": len(new_papers),
            "relations_count": original_data.get("relations_count", 0),
            "categories": {cat: dict(subcats) for cat, subcats in new_categories.items()},
            "taxonomy": [
                {
                    "category": node.name,
                    "description": node.description,
                    "subcategories": node.subcategories
                }
                for node in self.taxonomy
            ],
            "classification_stats": {
                "total": self.stats["total_papers"],
                "success": self.stats["classified_papers"],
                "failed": self.stats["failed_papers"],
                "multi_class": self.stats["multi_class_papers"],
            },
            "papers": new_papers,
            "relations": original_data.get("relations", [])
        }
        
        return new_data
    
    def _print_stats(self):
        """打印统计信息"""
        print(f"   📊 重分类统计:")
        print(f"      总论文数: {self.stats['total_papers']}")
        success_rate = self.stats['classified_papers'] / max(1, self.stats['total_papers']) * 100
        print(f"      成功分类: {self.stats['classified_papers']} ({success_rate:.1f}%)")
        print(f"      分类失败: {self.stats['failed_papers']}")
        multi_rate = self.stats['multi_class_papers'] / max(1, self.stats['classified_papers']) * 100
        print(f"      多分类论文: {self.stats['multi_class_papers']} ({multi_rate:.1f}%)")
        print(f"      模糊匹配: {self.stats['fuzzy_matched']}")
        print(f"      LLM 调用: {self.stats['llm_calls']}")


def reclassify_papers(
    mekg_data: Dict,
    outline_data: Dict,
    topic: str,
    chat_agent=None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    verbose: bool = True
) -> Dict:
    """
    便捷函数：重新分类论文
    
    Args:
        mekg_data: MEKG 数据
        outline_data: 大纲数据
        topic: 综述主题
        chat_agent: ChatAgent 实例
        max_workers: 并发数
        verbose: 是否打印详细信息
        
    Returns:
        更新后的 MEKG 数据
    """
    reclassifier = PaperReclassifier(
        chat_agent=chat_agent,
        max_workers=max_workers
    )
    return reclassifier.reclassify(mekg_data, outline_data, topic, verbose)
