"""
混合大纲生成器 - HybridOutlineGenerator

实现 Top-down + Bottom-up 的混合大纲生成策略，参考 SurveyForge 的设计。

核心流程:
1. Top-down (宏观框架): 基于主题和领域知识生成高层大纲框架
2. Bottom-up (微观涌现): 基于论文 Embedding 聚类发现细粒度主题
3. Merge: 智能合并两种大纲，消除重复，确保覆盖全面

Bottom-up 聚类机制:
- 对论文摘要进行 Embedding 向量化
- 使用 HDBSCAN 或 K-Means 进行聚类
- 对每个聚类簇提取关键词和主题描述
- 产出细粒度主题列表 (Emergent Topics)

Reference:
- SurveyForge: refer/SurveyForge-main/code/src/agents/outline_writer.py
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

from src.configs.config import BASE_DIR, ADVANCED_CHATAGENT_MODEL
from src.configs.logger import get_logger
from src.models.LLM import ChatAgent
from src.models.LLM.utils import load_prompt

# 导入聚类模块
try:
    from src.modules.outline.paper_clustering import (
        PaperClusterer,
        ClusteringResult,
        ClusterInfo,
        cluster_papers_for_outline
    )
    HAS_CLUSTERING = True
except ImportError:
    HAS_CLUSTERING = False

logger = get_logger("src.modules.outline.HybridOutlineGenerator")


@dataclass
class OutlineSection:
    """大纲章节"""
    title: str
    description: str = ""
    key_points: List[str] = field(default_factory=list)
    subsections: List['OutlineSection'] = field(default_factory=list)
    source: str = "hybrid"  # top_down, bottom_up, hybrid
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "key_points": self.key_points,
            "subsections": [s.to_dict() for s in self.subsections],
            "source": self.source
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OutlineSection':
        return cls(
            title=data.get("title", ""),
            description=data.get("description", ""),
            key_points=data.get("key_points", []),
            subsections=[cls.from_dict(s) for s in data.get("subsections", [])],
            source=data.get("source", "hybrid")
        )


@dataclass
class HybridOutline:
    """混合大纲"""
    title: str
    topic: str
    sections: List[OutlineSection] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "topic": self.topic,
            "sections": [s.to_dict() for s in self.sections],
            "metadata": self.metadata
        }
    
    def to_surveyx_format(self) -> Dict[str, Any]:
        """转换为 SurveyX 格式"""
        surveyx_sections = []
        for section in self.sections:
            surveyx_section = {
                "title": section.title,
                "desc": section.description,
                "sub": []
            }
            for subsection in section.subsections:
                surveyx_subsection = {
                    "title": subsection.title,
                    "desc": subsection.description,
                    "sub": []
                }
                for subsubsection in subsection.subsections:
                    surveyx_subsection["sub"].append({
                        "title": subsubsection.title,
                        "desc": subsubsection.description,
                        "sub": []
                    })
                surveyx_section["sub"].append(surveyx_subsection)
            surveyx_sections.append(surveyx_section)
        
        return {
            "title": self.title,
            "sections": surveyx_sections
        }


class HybridOutlineGenerator:
    """
    混合大纲生成器
    
    结合 Top-down 和 Bottom-up 两种策略生成高质量大纲。
    
    Top-down 策略 (宏观框架):
    - 基于主题生成标准 Survey 结构
    - 参考领域内已有 Survey 的大纲结构
    - 确保逻辑完整性和学术规范性
    
    Bottom-up 策略 (微观涌现) - 基于 Embedding 聚类:
    - 对论文摘要进行 Embedding 向量化
    - 使用 HDBSCAN 或 K-Means 进行聚类
    - 对每个聚类簇提取关键词和主题描述
    - 产出细粒度主题列表 (Emergent Topics)
    
    Merge 策略:
    - 智能合并两种大纲
    - 消除重复章节
    - 补充遗漏主题
    
    创新点:
    - 使用 HDBSCAN 自动发现聚类数量，无需预设
    - 结合 LLM 和聚类算法，兼顾语义理解和统计特征
    - 支持多种聚类算法切换 (HDBSCAN, K-Means, Agglomerative)
    """
    
    # Top-down 大纲生成 Prompt
    TOP_DOWN_PROMPT = """You are an expert in writing comprehensive academic survey papers.

Given the topic: "{topic}"

Generate a high-level survey outline following standard academic survey structure.

Requirements:
1. Include Introduction, main body sections (4-6 sections), and Conclusion
2. Each section should have a clear title and brief description
3. Main body sections should cover: Background/Preliminaries, Core Methods/Approaches, Applications, Evaluation/Benchmarks, Challenges and Future Directions
4. Descriptions should be informative and guide content generation

Output format (JSON):
{{
    "title": "Survey title",
    "sections": [
        {{
            "title": "Section title",
            "description": "Brief description of what this section covers",
            "key_points": ["point1", "point2", ...]
        }},
        ...
    ]
}}

Generate the outline:"""

    # Bottom-up 主题发现 Prompt (用于 LLM-only 模式，作为回退)
    BOTTOM_UP_PROMPT = """You are an expert in analyzing academic papers and discovering research themes.

Given the following paper abstracts related to "{topic}":

{abstracts}

Analyze these papers and identify the main research themes/topics.

Requirements:
1. Identify 5-8 distinct research themes
2. For each theme, provide a title and description
3. List key papers (by index) that belong to each theme
4. Themes should be mutually exclusive and collectively exhaustive

Output format (JSON):
{{
    "themes": [
        {{
            "title": "Theme title",
            "description": "Description of this research theme",
            "key_aspects": ["aspect1", "aspect2", ...],
            "paper_indices": [0, 1, 5, ...]
        }},
        ...
    ]
}}

Analyze and output:"""

    # 聚类结果转换为大纲的 Prompt
    CLUSTER_TO_OUTLINE_PROMPT = """You are an expert in organizing academic survey outlines.

Given the following clustering results from {n_papers} papers on "{topic}":

{clusters_text}

Convert these clusters into well-organized survey sections.

Requirements:
1. Each cluster should become a section or subsection
2. Merge similar clusters if they overlap significantly
3. Order sections logically (from foundational to advanced)
4. Provide clear titles and descriptions for each section
5. Ensure comprehensive coverage of all clusters

Output format (JSON):
{{
    "sections": [
        {{
            "title": "Section title",
            "description": "Section description",
            "key_points": ["point1", "point2"],
            "source_clusters": [0, 1]
        }},
        ...
    ]
}}

Output only the JSON:"""

    # 大纲合并 Prompt
    MERGE_PROMPT = """You are an expert in organizing academic survey outlines.

Given two outlines for a survey on "{topic}":

Top-down outline (structure-focused):
{top_down_outline}

Bottom-up outline (content-focused):
{bottom_up_outline}

Merge these outlines into a comprehensive, well-organized survey outline.

Requirements:
1. Preserve the logical structure from top-down outline
2. Incorporate specific themes from bottom-up outline
3. Eliminate redundancy and overlap
4. Ensure comprehensive coverage of the topic
5. Each section should have 2-4 subsections
6. Total sections: 6-8 (including Introduction and Conclusion)

Output format (JSON):
{{
    "title": "Final survey title",
    "sections": [
        {{
            "title": "Section title",
            "description": "Section description",
            "key_points": ["point1", "point2"],
            "subsections": [
                {{
                    "title": "Subsection title",
                    "description": "Subsection description",
                    "key_points": ["point1", "point2"]
                }},
                ...
            ]
        }},
        ...
    ]
}}

Generate the merged outline:"""

    def __init__(
        self,
        chat_agent: Optional[ChatAgent] = None,
        enable_bottom_up: bool = True,
        enable_merge: bool = True,
        max_papers_for_clustering: int = 100,
        clustering_algorithm: str = "auto",  # auto, hdbscan, kmeans, agglomerative
        use_embedding_clustering: bool = True,  # 是否使用 Embedding 聚类（推荐）
        min_cluster_size: int = 3,  # HDBSCAN 最小聚类大小
        n_clusters: int = 7  # K-Means 聚类数量
    ):
        """
        初始化混合大纲生成器
        
        Args:
            chat_agent: ChatAgent 实例
            enable_bottom_up: 是否启用 Bottom-up 策略
            enable_merge: 是否启用合并策略
            max_papers_for_clustering: 用于聚类的最大论文数
            clustering_algorithm: 聚类算法 (auto, hdbscan, kmeans, agglomerative)
            use_embedding_clustering: 是否使用 Embedding 聚类（推荐开启）
            min_cluster_size: HDBSCAN 最小聚类大小
            n_clusters: K-Means 聚类数量
        """
        self.chat_agent = chat_agent or ChatAgent()
        self.enable_bottom_up = enable_bottom_up
        self.enable_merge = enable_merge
        self.max_papers_for_clustering = max_papers_for_clustering
        self.clustering_algorithm = clustering_algorithm
        self.use_embedding_clustering = use_embedding_clustering and HAS_CLUSTERING
        self.min_cluster_size = min_cluster_size
        self.n_clusters = n_clusters
        
        # 初始化聚类器
        if self.use_embedding_clustering:
            self.clusterer = PaperClusterer(
                chat_agent=self.chat_agent,
                algorithm=clustering_algorithm if clustering_algorithm != "auto" else "hdbscan",
                min_cluster_size=min_cluster_size,
                n_clusters=n_clusters,
                use_llm_for_topics=True
            )
            logger.info(f"Initialized PaperClusterer with algorithm={clustering_algorithm}")
        else:
            self.clusterer = None
            logger.info("Embedding clustering disabled, using LLM-only bottom-up")

    def _remote_chat_once(self, prompt: str, **kwargs) -> str:
        """Call the chat agent once when outline generation can fall back safely."""
        chat_once = getattr(self.chat_agent, "remote_chat_no_retry", self.chat_agent.remote_chat)
        return chat_once(prompt, **kwargs)
    
    def generate(
        self,
        topic: str,
        papers: Optional[List[Dict[str, Any]]] = None,
        reference_surveys: Optional[List[Dict[str, Any]]] = None
    ) -> HybridOutline:
        """
        生成混合大纲
        
        Args:
            topic: 综述主题
            papers: 论文列表 (用于 Bottom-up)
            reference_surveys: 参考 Survey 列表 (用于 Top-down)
            
        Returns:
            HybridOutline 对象
        """
        logger.info(f"开始生成混合大纲: {topic}")
        
        # Step 1: Top-down 大纲生成
        logger.info("Step 1: 生成 Top-down 大纲...")
        top_down_outline = self._generate_top_down_outline(topic, reference_surveys)
        
        # Step 2: Bottom-up 主题发现 (如果启用且有论文)
        bottom_up_themes = None
        clustering_result = None
        
        if self.enable_bottom_up and papers:
            logger.info("Step 2: 生成 Bottom-up 主题 (基于 Embedding 聚类)...")
            
            if self.use_embedding_clustering:
                # 使用 Embedding 聚类（推荐）
                clustering_result = self._cluster_papers_with_embedding(topic, papers)
                if clustering_result and clustering_result.clusters:
                    bottom_up_themes = self._convert_clusters_to_themes(clustering_result)
                    logger.info(f"   ✓ 聚类发现 {len(bottom_up_themes)} 个主题 (算法: {clustering_result.algorithm})")
                    logger.info(f"   ✓ 轮廓系数: {clustering_result.silhouette_score:.3f}")
                else:
                    logger.warning("   ⚠️ 聚类失败，回退到 LLM-only 模式")
                    bottom_up_themes = self._discover_bottom_up_themes_llm(topic, papers)
            else:
                # 使用 LLM-only 模式（回退）
                bottom_up_themes = self._discover_bottom_up_themes_llm(topic, papers)
        
        # Step 3: 合并大纲 (如果启用)
        if self.enable_merge and bottom_up_themes:
            logger.info("Step 3: 合并大纲...")
            final_outline = self._merge_outlines(topic, top_down_outline, bottom_up_themes)
        else:
            final_outline = top_down_outline
        
        logger.info(f"大纲生成完成: {len(final_outline.sections)} 个章节")
        return final_outline
    
    def _generate_top_down_outline(
        self,
        topic: str,
        reference_surveys: Optional[List[Dict[str, Any]]] = None
    ) -> HybridOutline:
        """生成 Top-down 大纲"""
        prompt = self.TOP_DOWN_PROMPT.format(topic=topic)
        
        # 如果有参考 Survey，添加到 prompt
        if reference_surveys:
            survey_info = "\n\nReference survey outlines for inspiration:\n"
            for i, survey in enumerate(reference_surveys[:3]):
                survey_info += f"\n{i+1}. {survey.get('title', 'Unknown')}\n"
                if 'outline' in survey:
                    survey_info += f"   Outline: {survey['outline'][:500]}...\n"
            prompt = prompt.replace("Generate the outline:", survey_info + "\nGenerate the outline:")
        
        response = self._remote_chat_once(prompt, model=ADVANCED_CHATAGENT_MODEL)
        
        # 解析响应
        try:
            outline_data = self._parse_json_response(response)
            sections = []
            for section_data in outline_data.get("sections", []):
                section = OutlineSection(
                    title=section_data.get("title", ""),
                    description=section_data.get("description", ""),
                    key_points=section_data.get("key_points", []),
                    source="top_down"
                )
                sections.append(section)
            
            return HybridOutline(
                title=outline_data.get("title", f"A Survey on {topic}"),
                topic=topic,
                sections=sections,
                metadata={"source": "top_down"}
            )
        except Exception as e:
            logger.error(f"解析 Top-down 大纲失败: {e}")
            # 返回默认大纲
            return self._create_default_outline(topic)
    
    def _cluster_papers_with_embedding(
        self,
        topic: str,
        papers: List[Dict[str, Any]]
    ) -> Optional[ClusteringResult]:
        """
        使用 Embedding 聚类发现主题
        
        这是 Bottom-up 的核心实现，使用 HDBSCAN 或 K-Means 对论文进行聚类。
        
        Args:
            topic: 综述主题
            papers: 论文列表
            
        Returns:
            ClusteringResult 对象
        """
        if not self.clusterer:
            logger.warning("Clusterer not initialized")
            return None
        
        # 限制论文数量
        papers_subset = papers[:self.max_papers_for_clustering]
        
        # 自动选择算法
        if self.clustering_algorithm == "auto":
            algorithm = self.clusterer.auto_select_algorithm(len(papers_subset))
            self.clusterer.algorithm = algorithm
            logger.info(f"   Auto-selected clustering algorithm: {algorithm}")
        
        try:
            result = self.clusterer.cluster_papers(papers_subset, topic)
            return result
        except Exception as e:
            logger.error(f"Embedding clustering failed: {e}")
            return None
    
    def _convert_clusters_to_themes(
        self,
        clustering_result: ClusteringResult
    ) -> List[OutlineSection]:
        """
        将聚类结果转换为大纲主题
        
        Args:
            clustering_result: 聚类结果
            
        Returns:
            OutlineSection 列表
        """
        themes = []
        
        for cluster in clustering_result.clusters:
            # 跳过太小的聚类
            if len(cluster.paper_indices) < 2:
                continue
            
            theme = OutlineSection(
                title=cluster.title,
                description=cluster.description,
                key_points=cluster.key_aspects,
                source="bottom_up_clustering"
            )
            themes.append(theme)
        
        return themes
    
    def _discover_bottom_up_themes_llm(
        self,
        topic: str,
        papers: List[Dict[str, Any]]
    ) -> List[OutlineSection]:
        """
        使用 LLM 发现 Bottom-up 主题（回退方案）
        
        当 Embedding 聚类不可用时使用此方法。
        """
        # 限制论文数量
        papers_subset = papers[:self.max_papers_for_clustering]
        
        # 准备摘要文本
        abstracts = ""
        for i, paper in enumerate(papers_subset):
            title = paper.get("title", "")
            abstract = paper.get("abstract", "")[:500]
            abstracts += f"\n[{i}] {title}\n{abstract}\n"
        
        prompt = self.BOTTOM_UP_PROMPT.format(topic=topic, abstracts=abstracts)
        response = self._remote_chat_once(prompt, model=ADVANCED_CHATAGENT_MODEL)
        
        # 解析响应
        try:
            themes_data = self._parse_json_response(response)
            themes = []
            for theme_data in themes_data.get("themes", []):
                theme = OutlineSection(
                    title=theme_data.get("title", ""),
                    description=theme_data.get("description", ""),
                    key_points=theme_data.get("key_aspects", []),
                    source="bottom_up_llm"
                )
                themes.append(theme)
            return themes
        except Exception as e:
            logger.error(f"解析 Bottom-up 主题失败: {e}")
            return []
    
    def _merge_outlines(
        self,
        topic: str,
        top_down_outline: HybridOutline,
        bottom_up_themes: List[OutlineSection]
    ) -> HybridOutline:
        """合并 Top-down 和 Bottom-up 大纲"""
        # 准备 Top-down 大纲文本
        top_down_text = json.dumps({
            "title": top_down_outline.title,
            "sections": [
                {
                    "title": s.title,
                    "description": s.description,
                    "key_points": s.key_points
                }
                for s in top_down_outline.sections
            ]
        }, indent=2)
        
        # 准备 Bottom-up 主题文本
        bottom_up_text = json.dumps({
            "themes": [
                {
                    "title": t.title,
                    "description": t.description,
                    "key_aspects": t.key_points
                }
                for t in bottom_up_themes
            ]
        }, indent=2)
        
        prompt = self.MERGE_PROMPT.format(
            topic=topic,
            top_down_outline=top_down_text,
            bottom_up_outline=bottom_up_text
        )
        
        response = self._remote_chat_once(prompt, model=ADVANCED_CHATAGENT_MODEL)
        
        # 解析响应
        try:
            merged_data = self._parse_json_response(response)
            sections = []
            for section_data in merged_data.get("sections", []):
                subsections = []
                for sub_data in section_data.get("subsections", []):
                    subsection = OutlineSection(
                        title=sub_data.get("title", ""),
                        description=sub_data.get("description", ""),
                        key_points=sub_data.get("key_points", []),
                        source="hybrid"
                    )
                    subsections.append(subsection)
                
                section = OutlineSection(
                    title=section_data.get("title", ""),
                    description=section_data.get("description", ""),
                    key_points=section_data.get("key_points", []),
                    subsections=subsections,
                    source="hybrid"
                )
                sections.append(section)
            
            return HybridOutline(
                title=merged_data.get("title", top_down_outline.title),
                topic=topic,
                sections=sections,
                metadata={"source": "hybrid", "merge_strategy": "llm_merge"}
            )
        except Exception as e:
            logger.error(f"合并大纲失败: {e}")
            # 返回 Top-down 大纲作为回退
            return top_down_outline
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """解析 JSON 响应"""
        # 尝试提取 JSON
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response
        
        return json.loads(json_str)
    
    def _create_default_outline(self, topic: str) -> HybridOutline:
        """创建默认大纲"""
        default_sections = [
            OutlineSection(
                title="Introduction",
                description=f"Introduction to {topic}, including motivation, scope, and contributions.",
                key_points=["Background and motivation", "Scope of the survey", "Main contributions"],
                source="default"
            ),
            OutlineSection(
                title="Background and Preliminaries",
                description="Foundational concepts and background knowledge.",
                key_points=["Key definitions", "Related concepts", "Problem formulation"],
                source="default"
            ),
            OutlineSection(
                title="Methods and Approaches",
                description="Main methods and approaches in the field.",
                key_points=["Classification of methods", "Key techniques", "Comparative analysis"],
                source="default"
            ),
            OutlineSection(
                title="Applications",
                description="Applications and use cases.",
                key_points=["Domain applications", "Case studies", "Real-world deployments"],
                source="default"
            ),
            OutlineSection(
                title="Evaluation and Benchmarks",
                description="Evaluation methods, datasets, and benchmarks.",
                key_points=["Evaluation metrics", "Benchmark datasets", "Experimental results"],
                source="default"
            ),
            OutlineSection(
                title="Challenges and Future Directions",
                description="Open challenges and future research directions.",
                key_points=["Current limitations", "Open problems", "Future trends"],
                source="default"
            ),
            OutlineSection(
                title="Conclusion",
                description="Summary and concluding remarks.",
                key_points=["Key findings", "Recommendations", "Final thoughts"],
                source="default"
            )
        ]
        
        return HybridOutline(
            title=f"A Comprehensive Survey on {topic}",
            topic=topic,
            sections=default_sections,
            metadata={"source": "default"}
        )


# 便捷函数
def generate_hybrid_outline(
    topic: str,
    papers: Optional[List[Dict[str, Any]]] = None,
    chat_agent: Optional[ChatAgent] = None,
    enable_bottom_up: bool = True,
    use_embedding_clustering: bool = True,
    clustering_algorithm: str = "auto"
) -> HybridOutline:
    """
    生成混合大纲的便捷函数
    
    Args:
        topic: 综述主题
        papers: 论文列表
        chat_agent: ChatAgent 实例
        enable_bottom_up: 是否启用 Bottom-up 策略
        use_embedding_clustering: 是否使用 Embedding 聚类（推荐）
        clustering_algorithm: 聚类算法 (auto, hdbscan, kmeans, agglomerative)
        
    Returns:
        HybridOutline 对象
    """
    generator = HybridOutlineGenerator(
        chat_agent=chat_agent,
        enable_bottom_up=enable_bottom_up,
        use_embedding_clustering=use_embedding_clustering,
        clustering_algorithm=clustering_algorithm
    )
    return generator.generate(topic, papers)


if __name__ == "__main__":
    # 测试代码
    topic = "Large Language Model Agents"
    
    # 测试论文数据
    test_papers = [
        {"title": "ReAct: Synergizing Reasoning and Acting in Language Models",
         "abstract": "Large language models (LLMs) have shown remarkable capabilities in reasoning and acting. We propose ReAct, a general paradigm that synergizes reasoning and acting in language models for solving diverse language reasoning and decision making tasks."},
        {"title": "Toolformer: Language Models Can Teach Themselves to Use Tools",
         "abstract": "Language models exhibit remarkable abilities to solve new tasks from just a few examples or textual instructions. We show that LLMs can teach themselves to use external tools via simple APIs."},
        {"title": "HuggingGPT: Solving AI Tasks with ChatGPT and its Friends in Hugging Face",
         "abstract": "Solving complicated AI tasks with different domains and modalities is a key step toward artificial general intelligence. We present HuggingGPT, a system that leverages LLMs as a controller to manage existing AI models."},
        {"title": "AutoGPT: An Autonomous GPT-4 Experiment",
         "abstract": "Auto-GPT is an experimental open-source application showcasing the capabilities of the GPT-4 language model. This program, driven by GPT-4, chains together LLM thoughts to autonomously achieve whatever goal you set."},
        {"title": "ToolBench: An Open Platform for Training, Serving, and Evaluating Large Language Model for Tool Learning",
         "abstract": "We present ToolBench, an open platform for training, serving, and evaluating large language models for tool learning. ToolBench provides a comprehensive benchmark for evaluating LLMs' tool-use capabilities."},
    ]
    
    print("=" * 60)
    print("测试 HybridOutlineGenerator (带 Embedding 聚类)")
    print("=" * 60)
    
    generator = HybridOutlineGenerator(
        use_embedding_clustering=True,
        clustering_algorithm="auto"
    )
    outline = generator.generate(topic, test_papers)
    
    print(f"\n生成的大纲: {outline.title}")
    print(f"来源: {outline.metadata.get('source', 'unknown')}")
    print(f"\n章节结构:")
    for section in outline.sections:
        print(f"  [{section.source}] {section.title}")
        if section.description:
            print(f"      {section.description[:80]}...")
        for sub in section.subsections:
            print(f"    - {sub.title}")
