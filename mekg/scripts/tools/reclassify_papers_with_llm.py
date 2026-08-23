
#!/usr/bin/env python3
"""
使用 LLM 重新分类论文并生成新的 mekg_data.json

原理说明：
=========
1. 分类体系生成：
   - 读取 outline.json 中的章节结构
   - 提取技术性章节（排除 Introduction/Conclusion/Background）
   - 使用 LLM 基于大纲生成适合论文分类的 Taxonomy
   - Taxonomy 的每个分类对应大纲中的一个或多个技术主题

2. 论文分类：
   - 对每篇论文，使用 LLM 判断其属于哪些分类
   - 一篇论文可以属于 1-3 个分类（多标签分类）
   - 使用论文标题 + 摘要作为输入
   - 使用模糊匹配确保分类名称的鲁棒性

3. 数据结构：
   - categories: {category: {subcategory: count}}
   - 每篇论文的 all_categories 字段保存所有分类
   - 第一个分类作为主分类（category/subcategory 字段）

使用方法：
    python mekg/scripts/tools/reclassify_papers_with_llm.py

输出：
    outputs/.../mekg/mekg_data_new.json
"""

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Set, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from collections import defaultdict
import time
from difflib import SequenceMatcher

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from tqdm import tqdm

# 导入 ChatAgent
try:
    from src.models.LLM.ChatAgent import ChatAgent
    HAS_CHAT_AGENT = True
except ImportError:
    HAS_CHAT_AGENT = False
    print("⚠️ ChatAgent 未找到，无法运行此脚本")
    sys.exit(1)


# ============================================================================
# 配置
# ============================================================================

# 数据目录
DATA_DIR = project_root / 'outputs' / 'reclassify_papers_with_llm.py2025-12-23-1426_Large_Language_Model'

# 并发数
MAX_WORKERS = 200

# LLM 模型（用于分类）
CLASSIFICATION_MODEL = "kimi-k2"  # 使用快速模型

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
# 核心逻辑
# ============================================================================

class LLMPaperClassifier:
    """使用 LLM 进行论文分类"""
    
    def __init__(self, max_workers: int = 200):
        self.max_workers = max_workers
        self.chat_agent = ChatAgent()
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
            "fuzzy_matched": 0,  # 模糊匹配成功的次数
            "retries": 0,
        }
    
    def load_data(self) -> Tuple[Dict, Dict]:
        """加载数据"""
        # 加载 MEKG 数据
        mekg_path = DATA_DIR / 'mekg' / 'mekg_data.json'
        with open(mekg_path, 'r', encoding='utf-8') as f:
            mekg_data = json.load(f)
        print(f"✅ 已加载 MEKG 数据: {mekg_data.get('papers_count', 0)} 篇论文")
        
        # 加载大纲
        outline_path = DATA_DIR / 'outline.json'
        with open(outline_path, 'r', encoding='utf-8') as f:
            outline_data = json.load(f)
        print(f"✅ 已加载大纲: {len(outline_data.get('sections', []))} 个章节")
        
        return mekg_data, outline_data
    
    def generate_taxonomy(self, outline_data: Dict, topic: str) -> List[TaxonomyNode]:
        """使用 LLM 生成分类体系"""
        print("\n📋 正在生成分类体系...")
        
        # 构建大纲文本（只包含技术性章节）
        outline_text = ""
        skip_keywords = ['introduction', 'conclusion', 'background', 'related work', 'preliminaries']
        
        for section in outline_data.get('sections', []):
            title = section.get('title', '')
            
            # 跳过非技术性章节
            if any(kw in title.lower() for kw in skip_keywords):
                continue
            
            desc = section.get('description', '')[:300]
            outline_text += f"\n## {section.get('number', '')}. {title}\n"
            outline_text += f"   {desc}\n"
            
            for subsection in section.get('subsections', []):
                sub_title = subsection.get('title', '')
                sub_desc = subsection.get('description', '')[:200]
                outline_text += f"   ### {subsection.get('number', '')} {sub_title}\n"
                outline_text += f"       {sub_desc}\n"
        
        # 调用 LLM
        prompt = GENERATE_TAXONOMY_PROMPT.format(
            topic=topic,
            outline_text=outline_text
        )
        
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self.chat_agent.remote_chat(prompt, temperature=0.3)
                self.stats["llm_calls"] += 1
                
                # 解析 JSON
                match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
                if match:
                    json_str = match.group(1)
                else:
                    # 尝试找到 JSON 对象
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
                
                print(f"✅ 生成了 {len(self.taxonomy)} 个主分类")
                for node in self.taxonomy:
                    print(f"   📁 {node.name}: {len(node.subcategories)} 个子分类")
                    for sub in node.subcategories:
                        print(f"      - {sub.get('name', '')}")
                
                return self.taxonomy
                
            except Exception as e:
                if attempt < MAX_RETRIES:
                    print(f"   ⚠️ 生成失败 (尝试 {attempt + 1}/{MAX_RETRIES + 1}): {e}")
                    self.stats["retries"] += 1
                    time.sleep(1)
                else:
                    print(f"❌ 生成分类体系失败: {e}")
                    print("   使用默认分类体系...")
                    return self._get_default_taxonomy()
        
        return self._get_default_taxonomy()
    
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
    
    def _get_default_taxonomy(self) -> List[TaxonomyNode]:
        """默认分类体系（备用）"""
        self.taxonomy = [
            TaxonomyNode(
                name="Tool Retrieval & Selection",
                description="Methods for discovering and selecting appropriate tools from a library",
                subcategories=[
                    {"name": "Retrieval Methods", "description": "RAG, embedding-based, BM25 retrieval"},
                    {"name": "Selection Strategies", "description": "Tool ranking, filtering, and selection"}
                ]
            ),
            TaxonomyNode(
                name="Reasoning & Planning",
                description="Reasoning and planning mechanisms for tool use",
                subcategories=[
                    {"name": "Chain-of-Thought", "description": "CoT, ReAct, and reasoning methods"},
                    {"name": "Multi-step Planning", "description": "Task decomposition and planning"}
                ]
            ),
            TaxonomyNode(
                name="Argument Generation",
                description="Generating correct API arguments and parameters",
                subcategories=[
                    {"name": "Parameter Filling", "description": "Filling API parameters correctly"},
                    {"name": "Schema Adherence", "description": "Following API schemas and formats"}
                ]
            ),
            TaxonomyNode(
                name="Training & Fine-tuning",
                description="Training methods for tool-augmented LLMs",
                subcategories=[
                    {"name": "Supervised Fine-tuning", "description": "SFT on tool-use datasets"},
                    {"name": "Reinforcement Learning", "description": "RL and RLHF for tool use"},
                    {"name": "Data Synthesis", "description": "Synthetic data generation for training"}
                ]
            ),
            TaxonomyNode(
                name="Benchmarks & Evaluation",
                description="Evaluation datasets, benchmarks, and metrics",
                subcategories=[
                    {"name": "Benchmarks", "description": "ToolBench, APIBank, etc."},
                    {"name": "Metrics", "description": "Accuracy, Pass@k, and other metrics"}
                ]
            ),
            TaxonomyNode(
                name="Agent Systems",
                description="Autonomous agents and multi-agent systems",
                subcategories=[
                    {"name": "Single Agent", "description": "Single autonomous agent systems"},
                    {"name": "Multi-Agent", "description": "Multi-agent collaboration"}
                ]
            ),
            TaxonomyNode(
                name="Applications",
                description="Real-world applications and domain-specific uses",
                subcategories=[
                    {"name": "Code Generation", "description": "Code and programming tools"},
                    {"name": "Web & API", "description": "Web browsing and API integration"},
                    {"name": "Domain-Specific", "description": "Healthcare, finance, etc."}
                ]
            ),
        ]
        self._build_lookup_sets()
        self._build_taxonomy_text()
        return self.taxonomy
    
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
            # 递归验证子分类
            return self._validate_and_fix_classification({
                "category": matched_cat,
                "subcategory": subcat,
                "confidence": confidence * 0.9
            })
        
        return None
    
    def classify_paper(self, paper: Dict) -> PaperClassification:
        """使用 LLM 分类单篇论文"""
        paper_id = paper.get("id", "")
        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        
        # 使用更多内容
        if len(abstract) < 200:
            # 如果摘要太短，尝试使用 md_text
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
        
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self.chat_agent.remote_chat(
                    prompt, 
                    temperature=0.2,
                    model=CLASSIFICATION_MODEL
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
                seen = set()  # 避免重复
                
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
                if attempt < MAX_RETRIES:
                    self.stats["retries"] += 1
                    time.sleep(0.5)
                else:
                    return PaperClassification(paper_id=paper_id, error=str(e))
        
        return PaperClassification(paper_id=paper_id, error="Max retries exceeded")
    
    def classify_papers_concurrent(self, papers: List[Dict]) -> Dict[str, PaperClassification]:
        """并发分类所有论文"""
        print(f"\n🚀 开始并发分类 {len(papers)} 篇论文 (并发数: {self.max_workers})...")
        
        results = {}
        self.stats["total_papers"] = len(papers)
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            futures = {
                executor.submit(self.classify_paper, paper): paper.get("id", f"paper_{i}")
                for i, paper in enumerate(papers)
            }
            
            # 收集结果
            for future in tqdm(as_completed(futures), total=len(futures), desc="   分类进度"):
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
        
        elapsed = time.time() - start_time
        print(f"\n✅ 分类完成! 耗时: {elapsed:.1f}s ({elapsed/len(papers)*1000:.1f}ms/篇)")
        print(f"   成功: {self.stats['classified_papers']}, 失败: {self.stats['failed_papers']}")
        print(f"   多分类论文: {self.stats['multi_class_papers']}")
        print(f"   模糊匹配: {self.stats['fuzzy_matched']}")
        print(f"   重试次数: {self.stats['retries']}")
        print(f"   LLM 调用: {self.stats['llm_calls']}")
        
        return results
    
    def build_new_mekg_data(
        self,
        original_data: Dict,
        classification_results: Dict[str, PaperClassification]
    ) -> Dict:
        """构建新的 MEKG 数据"""
        print("\n📦 构建新的 MEKG 数据...")
        
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
    
    def save_new_data(self, new_data: Dict, output_path: Path):
        """保存新数据"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 新数据已保存到: {output_path}")
    
    def print_stats(self):
        """打印统计信息"""
        print("\n" + "=" * 60)
        print("📊 分类统计")
        print("=" * 60)
        print(f"   总论文数: {self.stats['total_papers']}")
        print(f"   成功分类: {self.stats['classified_papers']} ({self.stats['classified_papers']/max(1,self.stats['total_papers'])*100:.1f}%)")
        print(f"   分类失败: {self.stats['failed_papers']}")
        print(f"   多分类论文: {self.stats['multi_class_papers']} ({self.stats['multi_class_papers']/max(1,self.stats['classified_papers'])*100:.1f}%)")
        print(f"   模糊匹配: {self.stats['fuzzy_matched']}")
        print(f"   重试次数: {self.stats['retries']}")
        print(f"   LLM 调用: {self.stats['llm_calls']}")
        print("=" * 60)


def main():
    """主函数"""
    print("=" * 60)
    print("🚀 LLM 论文重分类工具 v2.0")
    print("=" * 60)
    print("\n📖 原理说明:")
    print("   1. 读取大纲，使用 LLM 生成适合论文分类的 Taxonomy")
    print("   2. 200 并发调用 LLM 对每篇论文进行多标签分类")
    print("   3. 使用模糊匹配确保分类名称的鲁棒性")
    print("   4. 一篇论文可以属于 1-3 个分类")
    print()
    
    # 创建分类器
    classifier = LLMPaperClassifier(max_workers=MAX_WORKERS)
    
    # 1. 加载数据
    mekg_data, outline_data = classifier.load_data()
    topic = mekg_data.get("topic", "Survey")
    
    # 2. 生成分类体系
    classifier.generate_taxonomy(outline_data, topic)
    
    # 3. 并发分类论文
    papers = mekg_data.get("papers", [])
    classification_results = classifier.classify_papers_concurrent(papers)
    
    # 4. 构建新数据
    new_data = classifier.build_new_mekg_data(mekg_data, classification_results)
    
    # 5. 保存新数据
    output_path = DATA_DIR / 'mekg' / 'mekg_data_new.json'
    classifier.save_new_data(new_data, output_path)
    
    # 6. 打印统计
    classifier.print_stats()
    
    # 7. 打印新分类结构
    print("\n📋 新分类结构:")
    for cat, subcats in sorted(new_data.get("categories", {}).items()):
        total = sum(subcats.values())
        print(f"   📁 {cat}: {total} 篇")
        for subcat, count in sorted(subcats.items(), key=lambda x: -x[1]):
            print(f"      📂 {subcat}: {count} 篇")
    
    print("\n✅ 完成! 请使用新的 mekg_data_new.json 文件")
    print(f"   路径: {output_path}")
    

if __name__ == "__main__":
    main()