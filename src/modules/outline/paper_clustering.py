"""
论文聚类模块 - Paper Clustering Module

实现基于 Embedding 的论文聚类，用于 Bottom-up 大纲生成。

支持的聚类算法:
1. HDBSCAN: 密度聚类，自动发现聚类数量，适合发现任意形状的聚类
2. K-Means: 经典聚类，需要预设聚类数量，适合球形聚类
3. Agglomerative: 层次聚类，可以生成层次化的主题结构

算法选择建议:
- HDBSCAN: 推荐用于探索性分析，不确定主题数量时使用
- K-Means: 推荐用于已知大致主题数量时使用
- Agglomerative: 推荐用于需要层次化主题结构时使用

Reference:
- HDBSCAN: https://hdbscan.readthedocs.io/
- SurveyForge clustering approach
"""

import json
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict, Counter
import numpy as np

from src.configs.logger import get_logger
from src.models.LLM import EmbedAgent, ChatAgent

logger = get_logger("src.modules.outline.PaperClustering")

# 尝试导入聚类库
try:
    import hdbscan
    HAS_HDBSCAN = True
except ImportError:
    HAS_HDBSCAN = False
    logger.warning("HDBSCAN not installed. Install with: pip install hdbscan")

try:
    from sklearn.cluster import KMeans, AgglomerativeClustering
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import normalize
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    logger.warning("scikit-learn not installed. Install with: pip install scikit-learn")

try:
    from sklearn.decomposition import PCA
    from sklearn.manifold import TSNE
    HAS_DIM_REDUCTION = True
except ImportError:
    HAS_DIM_REDUCTION = False


@dataclass
class ClusterInfo:
    """聚类信息"""
    cluster_id: int
    title: str = ""
    description: str = ""
    key_aspects: List[str] = field(default_factory=list)
    paper_indices: List[int] = field(default_factory=list)
    paper_titles: List[str] = field(default_factory=list)
    centroid: Optional[np.ndarray] = None
    coherence_score: float = 0.0  # 聚类内部一致性分数
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "title": self.title,
            "description": self.description,
            "key_aspects": self.key_aspects,
            "paper_indices": self.paper_indices,
            "paper_titles": self.paper_titles[:5],  # 只保留前5篇
            "coherence_score": self.coherence_score,
            "paper_count": len(self.paper_indices)
        }


@dataclass
class ClusteringResult:
    """聚类结果"""
    clusters: List[ClusterInfo]
    algorithm: str
    n_clusters: int
    n_noise: int = 0  # HDBSCAN 的噪声点数量
    silhouette_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "n_clusters": self.n_clusters,
            "n_noise": self.n_noise,
            "silhouette_score": self.silhouette_score,
            "clusters": [c.to_dict() for c in self.clusters],
            "metadata": self.metadata
        }


class PaperClusterer:
    """
    论文聚类器
    
    使用 Embedding 向量对论文进行聚类，发现研究主题。
    
    工作流程:
    1. 对论文摘要进行 Embedding 向量化
    2. 使用聚类算法（HDBSCAN/K-Means）进行聚类
    3. 对每个聚类提取关键词和主题描述
    4. 返回结构化的聚类结果
    """
    
    # 主题提取 Prompt
    TOPIC_EXTRACTION_PROMPT = """You are an expert in analyzing academic papers and extracting research themes.

Given the following papers from a cluster:

{papers_text}

Analyze these papers and extract the common research theme.

Requirements:
1. Provide a concise theme title (3-8 words)
2. Write a brief description (1-2 sentences)
3. List 3-5 key aspects/keywords that characterize this theme

Output format (JSON):
{{
    "title": "Theme title",
    "description": "Brief description of the research theme",
    "key_aspects": ["aspect1", "aspect2", "aspect3"]
}}

Output only the JSON, no additional text."""

    def __init__(
        self,
        embed_agent: Optional[EmbedAgent] = None,
        chat_agent: Optional[ChatAgent] = None,
        algorithm: str = "hdbscan",  # hdbscan, kmeans, agglomerative
        min_cluster_size: int = 3,  # HDBSCAN 参数
        min_samples: int = 2,  # HDBSCAN 参数
        n_clusters: int = 7,  # K-Means 参数
        use_llm_for_topics: bool = True,
        normalize_embeddings: bool = True
    ):
        """
        初始化论文聚类器
        
        Args:
            embed_agent: Embedding 代理
            chat_agent: LLM 代理（用于主题提取）
            algorithm: 聚类算法 (hdbscan, kmeans, agglomerative)
            min_cluster_size: HDBSCAN 最小聚类大小
            min_samples: HDBSCAN 最小样本数
            n_clusters: K-Means 聚类数量
            use_llm_for_topics: 是否使用 LLM 提取主题
            normalize_embeddings: 是否对 Embedding 进行 L2 归一化
        """
        self.embed_agent = embed_agent or EmbedAgent()
        self.chat_agent = chat_agent or ChatAgent()
        self.algorithm = algorithm
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.n_clusters = n_clusters
        self.use_llm_for_topics = use_llm_for_topics
        self.normalize_embeddings = normalize_embeddings
        
        # 验证算法可用性
        if algorithm == "hdbscan" and not HAS_HDBSCAN:
            logger.warning("HDBSCAN not available, falling back to K-Means")
            self.algorithm = "kmeans"
        
        if not HAS_SKLEARN:
            raise ImportError("scikit-learn is required for clustering. Install with: pip install scikit-learn")

    def _remote_chat_once(self, prompt: str, **kwargs) -> str:
        """Call the chat agent once for optional cluster labeling."""
        chat_once = getattr(self.chat_agent, "remote_chat_no_retry", self.chat_agent.remote_chat)
        return chat_once(prompt, **kwargs)
    
    def cluster_papers(
        self,
        papers: List[Dict[str, Any]],
        topic: str = ""
    ) -> ClusteringResult:
        """
        对论文进行聚类
        
        Args:
            papers: 论文列表，每篇论文需要包含 title 和 abstract
            topic: 综述主题（用于上下文）
            
        Returns:
            ClusteringResult 对象
        """
        if not papers:
            logger.warning("No papers provided for clustering")
            return ClusteringResult(clusters=[], algorithm=self.algorithm, n_clusters=0)
        
        logger.info(f"Clustering {len(papers)} papers using {self.algorithm}...")
        
        # Step 1: 生成 Embedding
        embeddings = self._embed_papers(papers)
        
        if embeddings is None or len(embeddings) == 0:
            logger.error("Failed to generate embeddings")
            return ClusteringResult(clusters=[], algorithm=self.algorithm, n_clusters=0)
        
        # Step 2: 执行聚类
        labels, n_clusters, n_noise = self._perform_clustering(embeddings)
        
        # Step 3: 构建聚类信息
        clusters = self._build_cluster_info(papers, embeddings, labels, n_clusters)
        
        # Step 4: 提取主题（使用 LLM 或关键词）
        if self.use_llm_for_topics:
            self._extract_topics_with_llm(clusters, papers, topic)
        else:
            self._extract_topics_with_keywords(clusters, papers)
        
        # Step 5: 计算聚类质量
        silhouette = self._calculate_silhouette(embeddings, labels)
        
        result = ClusteringResult(
            clusters=clusters,
            algorithm=self.algorithm,
            n_clusters=n_clusters,
            n_noise=n_noise,
            silhouette_score=silhouette,
            metadata={
                "total_papers": len(papers),
                "topic": topic,
                "algorithm_params": self._get_algorithm_params()
            }
        )
        
        logger.info(f"Clustering complete: {n_clusters} clusters, {n_noise} noise points, silhouette={silhouette:.3f}")
        return result
    
    def _embed_papers(self, papers: List[Dict[str, Any]]) -> Optional[np.ndarray]:
        """生成论文 Embedding"""
        logger.info(f"Generating embeddings for {len(papers)} papers...")
        
        # 构建文本：标题 + 摘要
        texts = []
        for paper in papers:
            title = paper.get("title", "")
            abstract = paper.get("abstract", "")[:1000]  # 限制摘要长度
            text = f"Title: {title}\nAbstract: {abstract}"
            texts.append(text)
        
        try:
            # 使用本地 Embedding（更快）
            embeddings = self.embed_agent.batch_local_embed(texts)
            embeddings = np.array(embeddings).astype(np.float32)
            
            # L2 归一化（对于余弦相似度很重要）
            if self.normalize_embeddings:
                embeddings = normalize(embeddings, norm='l2')
            
            logger.info(f"Generated embeddings with shape: {embeddings.shape}")
            return embeddings
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            return None
    
    def _perform_clustering(self, embeddings: np.ndarray) -> Tuple[np.ndarray, int, int]:
        """
        执行聚类
        
        Returns:
            (labels, n_clusters, n_noise)
        """
        n_samples = len(embeddings)
        n_noise = 0
        
        if self.algorithm == "hdbscan" and HAS_HDBSCAN:
            # HDBSCAN 聚类
            # 动态调整参数
            min_cluster_size = max(self.min_cluster_size, n_samples // 20)
            min_samples = max(self.min_samples, min_cluster_size // 2)
            
            logger.info(f"Running HDBSCAN with min_cluster_size={min_cluster_size}, min_samples={min_samples}")
            
            clusterer = hdbscan.HDBSCAN(
                min_cluster_size=min_cluster_size,
                min_samples=min_samples,
                metric='euclidean',  # 对于归一化向量，euclidean ≈ cosine
                cluster_selection_method='eom',  # Excess of Mass
                prediction_data=True
            )
            labels = clusterer.fit_predict(embeddings)
            
            # 统计聚类数量和噪声点
            unique_labels = set(labels)
            n_clusters = len(unique_labels) - (1 if -1 in unique_labels else 0)
            n_noise = list(labels).count(-1)
            
            logger.info(f"HDBSCAN found {n_clusters} clusters, {n_noise} noise points")
            
        elif self.algorithm == "agglomerative":
            # 层次聚类
            n_clusters = min(self.n_clusters, n_samples // 3)
            n_clusters = max(n_clusters, 2)
            
            logger.info(f"Running Agglomerative Clustering with n_clusters={n_clusters}")
            
            clusterer = AgglomerativeClustering(
                n_clusters=n_clusters,
                metric='euclidean',
                linkage='ward'
            )
            labels = clusterer.fit_predict(embeddings)
            
        else:
            # K-Means 聚类（默认）
            n_clusters = min(self.n_clusters, n_samples // 3)
            n_clusters = max(n_clusters, 2)
            
            logger.info(f"Running K-Means with n_clusters={n_clusters}")
            
            clusterer = KMeans(
                n_clusters=n_clusters,
                random_state=42,
                n_init=10,
                max_iter=300
            )
            labels = clusterer.fit_predict(embeddings)
        
        return labels, n_clusters, n_noise
    
    def _build_cluster_info(
        self,
        papers: List[Dict[str, Any]],
        embeddings: np.ndarray,
        labels: np.ndarray,
        n_clusters: int
    ) -> List[ClusterInfo]:
        """构建聚类信息"""
        clusters = []
        
        for cluster_id in range(n_clusters):
            # 获取该聚类的论文索引
            indices = np.where(labels == cluster_id)[0].tolist()
            
            if not indices:
                continue
            
            # 获取论文标题
            paper_titles = [papers[i].get("title", "") for i in indices]
            
            # 计算聚类中心
            cluster_embeddings = embeddings[indices]
            centroid = np.mean(cluster_embeddings, axis=0)
            
            # 计算聚类内部一致性（平均余弦相似度）
            if len(indices) > 1:
                similarities = []
                for emb in cluster_embeddings:
                    sim = np.dot(emb, centroid) / (np.linalg.norm(emb) * np.linalg.norm(centroid) + 1e-8)
                    similarities.append(sim)
                coherence = float(np.mean(similarities))
            else:
                coherence = 1.0
            
            cluster_info = ClusterInfo(
                cluster_id=cluster_id,
                paper_indices=indices,
                paper_titles=paper_titles,
                centroid=centroid,
                coherence_score=coherence
            )
            clusters.append(cluster_info)
        
        # 按论文数量排序（降序）
        clusters.sort(key=lambda x: len(x.paper_indices), reverse=True)
        
        return clusters
    
    def _extract_topics_with_llm(
        self,
        clusters: List[ClusterInfo],
        papers: List[Dict[str, Any]],
        topic: str
    ):
        """使用 LLM 提取主题"""
        logger.info("Extracting topics using LLM...")
        
        for cluster in clusters:
            # 准备论文文本
            papers_text = ""
            sample_indices = cluster.paper_indices[:10]  # 最多取10篇
            
            for i, idx in enumerate(sample_indices):
                paper = papers[idx]
                title = paper.get("title", "")
                abstract = paper.get("abstract", "")[:300]
                papers_text += f"\n[{i+1}] {title}\n{abstract}\n"
            
            prompt = self.TOPIC_EXTRACTION_PROMPT.format(papers_text=papers_text)
            
            try:
                response = self._remote_chat_once(prompt, temperature=0.3)
                topic_data = self._parse_json_response(response)
                
                cluster.title = topic_data.get("title", f"Cluster {cluster.cluster_id}")
                cluster.description = topic_data.get("description", "")
                cluster.key_aspects = topic_data.get("key_aspects", [])
                
            except Exception as e:
                logger.warning(f"Failed to extract topic for cluster {cluster.cluster_id}: {e}")
                # 回退到关键词提取
                self._extract_topic_with_keywords_single(cluster, papers)
    
    def _extract_topics_with_keywords(
        self,
        clusters: List[ClusterInfo],
        papers: List[Dict[str, Any]]
    ):
        """使用关键词提取主题（不使用 LLM）"""
        logger.info("Extracting topics using keywords...")
        
        for cluster in clusters:
            self._extract_topic_with_keywords_single(cluster, papers)
    
    def _extract_topic_with_keywords_single(
        self,
        cluster: ClusterInfo,
        papers: List[Dict[str, Any]]
    ):
        """为单个聚类提取关键词主题"""
        # 收集所有标题和摘要中的词
        all_words = []
        for idx in cluster.paper_indices:
            paper = papers[idx]
            title = paper.get("title", "").lower()
            abstract = paper.get("abstract", "").lower()
            
            # 简单分词
            words = re.findall(r'\b[a-z]{3,}\b', f"{title} {abstract}")
            all_words.extend(words)
        
        # 统计词频
        word_counts = Counter(all_words)
        
        # 过滤停用词
        stopwords = {
            'the', 'and', 'for', 'with', 'that', 'this', 'from', 'are', 'was',
            'were', 'been', 'have', 'has', 'had', 'can', 'could', 'will', 'would',
            'should', 'may', 'might', 'must', 'shall', 'our', 'their', 'its',
            'which', 'what', 'when', 'where', 'who', 'how', 'why', 'all', 'each',
            'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such', 'than',
            'too', 'very', 'just', 'also', 'only', 'into', 'over', 'after', 'before',
            'between', 'under', 'again', 'further', 'then', 'once', 'here', 'there',
            'these', 'those', 'through', 'during', 'about', 'against', 'above', 'below',
            'using', 'based', 'paper', 'propose', 'proposed', 'method', 'methods',
            'approach', 'approaches', 'model', 'models', 'results', 'show', 'shows',
            'demonstrate', 'demonstrates', 'achieve', 'achieves', 'performance',
            'experiments', 'experimental', 'evaluation', 'evaluate', 'evaluates'
        }
        
        # 获取最常见的关键词
        top_words = [
            word for word, count in word_counts.most_common(20)
            if word not in stopwords
        ][:5]
        
        # 生成标题
        if top_words:
            cluster.title = " ".join(top_words[:3]).title()
            cluster.key_aspects = top_words
            cluster.description = f"Research theme related to {', '.join(top_words[:3])}"
        else:
            cluster.title = f"Cluster {cluster.cluster_id}"
            cluster.key_aspects = []
            cluster.description = ""
    
    def _calculate_silhouette(self, embeddings: np.ndarray, labels: np.ndarray) -> float:
        """计算轮廓系数"""
        # 过滤噪声点
        valid_mask = labels >= 0
        valid_embeddings = embeddings[valid_mask]
        valid_labels = labels[valid_mask]
        
        if len(set(valid_labels)) < 2:
            return 0.0
        
        try:
            score = silhouette_score(valid_embeddings, valid_labels)
            return float(score)
        except Exception as e:
            logger.warning(f"Failed to calculate silhouette score: {e}")
            return 0.0
    
    def _get_algorithm_params(self) -> Dict[str, Any]:
        """获取算法参数"""
        if self.algorithm == "hdbscan":
            return {
                "min_cluster_size": self.min_cluster_size,
                "min_samples": self.min_samples
            }
        elif self.algorithm == "kmeans":
            return {
                "n_clusters": self.n_clusters
            }
        elif self.algorithm == "agglomerative":
            return {
                "n_clusters": self.n_clusters
            }
        return {}
    
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
    
    def auto_select_algorithm(self, n_papers: int) -> str:
        """
        根据论文数量自动选择最佳算法
        
        Args:
            n_papers: 论文数量
            
        Returns:
            推荐的算法名称
        """
        if n_papers < 20:
            # 论文太少，使用 K-Means 更稳定
            return "kmeans"
        elif n_papers < 50:
            # 中等数量，HDBSCAN 可能效果不好
            return "kmeans"
        elif n_papers < 200:
            # 适合 HDBSCAN
            return "hdbscan" if HAS_HDBSCAN else "kmeans"
        else:
            # 大量论文，HDBSCAN 效果最好
            return "hdbscan" if HAS_HDBSCAN else "kmeans"


def cluster_papers_for_outline(
    papers: List[Dict[str, Any]],
    topic: str = "",
    algorithm: str = "auto",
    use_llm: bool = True
) -> ClusteringResult:
    """
    为大纲生成进行论文聚类的便捷函数
    
    Args:
        papers: 论文列表
        topic: 综述主题
        algorithm: 聚类算法 (auto, hdbscan, kmeans, agglomerative)
        use_llm: 是否使用 LLM 提取主题
        
    Returns:
        ClusteringResult 对象
    """
    clusterer = PaperClusterer(use_llm_for_topics=use_llm)
    
    # 自动选择算法
    if algorithm == "auto":
        algorithm = clusterer.auto_select_algorithm(len(papers))
        logger.info(f"Auto-selected algorithm: {algorithm}")
    
    clusterer.algorithm = algorithm
    
    return clusterer.cluster_papers(papers, topic)


if __name__ == "__main__":
    # 测试代码
    test_papers = [
        {"title": "BERT: Pre-training of Deep Bidirectional Transformers", "abstract": "We introduce BERT, a new language representation model..."},
        {"title": "GPT-3: Language Models are Few-Shot Learners", "abstract": "We demonstrate that scaling up language models..."},
        {"title": "Attention Is All You Need", "abstract": "The dominant sequence transduction models are based on complex recurrent..."},
    ]
    
    result = cluster_papers_for_outline(test_papers, topic="Large Language Models", use_llm=False)
    print(f"Clustering result: {result.n_clusters} clusters")
    for cluster in result.clusters:
        print(f"  - {cluster.title}: {len(cluster.paper_indices)} papers")
