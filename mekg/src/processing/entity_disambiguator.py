"""
实体消歧器 - EntityDisambiguator

核心功能：
1. 对语义实体（Task, Method, Dataset等）进行消歧
2. 将相似实体（如 "LLM Agent" 和 "LLM-based Agent"）合并
3. 维护实体映射表

借鉴 NLP-AKG 的 K-means 聚类思路，但针对小规模数据优化为基于相似度的聚类。
"""

import numpy as np
from typing import List, Dict, Tuple, Set
from collections import Counter, defaultdict
from loguru import logger
from dataclasses import dataclass

from src.models.LLM.EmbedAgent import EmbedAgent

@dataclass
class EntityCluster:
    cluster_id: int
    representative: str
    entities: List[str]
    frequencies: Dict[str, int]

@dataclass
class DisambiguationResult:
    entity_type: str
    clusters: List[EntityCluster]
    mapping: Dict[str, str]  # original -> canonical

class EntityDisambiguator:
    def __init__(self, embed_agent: EmbedAgent = None, similarity_threshold: float = 0.85):
        self.embed_agent = embed_agent or EmbedAgent()
        self.similarity_threshold = similarity_threshold
        
    async def disambiguate(self, entities: List) -> Dict[str, str]:
        """
        对实体列表进行消歧
        
        Args:
            entities: 原始实体列表（可能包含字符串或嵌套列表）
            
        Returns:
            {原始实体: 规范实体} 的映射字典
        """
        if not entities:
            return {}
        
        # 1. 预处理：展平列表并过滤非字符串元素
        flat_entities = []
        for e in entities:
            if isinstance(e, str):
                flat_entities.append(e)
            elif isinstance(e, list):
                # 递归展平嵌套列表
                for item in e:
                    if isinstance(item, str):
                        flat_entities.append(item)
                    elif isinstance(item, list):
                        for sub_item in item:
                            if isinstance(sub_item, str):
                                flat_entities.append(sub_item)
        
        if not flat_entities:
            return {}
            
        # 2. 去重并统计频率
        entity_counts = Counter(flat_entities)
        unique_entities = list(entity_counts.keys())
        
        if len(unique_entities) < 2:
            return {e: e for e in unique_entities}
            
        logger.info(f"Disambiguating {len(unique_entities)} unique entities...")
        
        # 2. 获取嵌入向量 (尝试获取，失败则使用 None)
        embeddings = None
        try:
            # 优先使用远程嵌入
            embeddings = self.embed_agent.batch_remote_embed(unique_entities)
            
            # 检查是否有效
            if not embeddings or any(isinstance(e, str) for e in embeddings):
                logger.warning("Remote embedding failed, trying local...")
                try:
                    embeddings = self.embed_agent.batch_local_embed(unique_entities)
                except:
                    embeddings = None
        except Exception as e:
            logger.error(f"Failed to get embeddings: {e}")
            embeddings = None
            
        # 3. 基于相似度的聚类
        clusters = []
        
        # 按频率降序排序
        sorted_entities = sorted(unique_entities, key=lambda x: entity_counts[x], reverse=True)
        sorted_indices = [unique_entities.index(e) for e in sorted_entities]
        
        processed = set()
        mapping = {}
        
        for i in sorted_indices:
            entity = unique_entities[i]
            if entity in processed:
                continue
                
            cluster_members = [entity]
            processed.add(entity)
            
            # 寻找相似实体
            for j in sorted_indices:
                other_entity = unique_entities[j]
                if other_entity in processed:
                    continue
                
                similarity = 0.0
                if embeddings and embeddings[i] and embeddings[j]:
                    # 使用向量相似度
                    similarity = self._cosine_similarity(embeddings[i], embeddings[j])
                else:
                    # 回退到文本相似度
                    similarity = self._text_similarity(entity, other_entity)
                
                if similarity >= self.similarity_threshold:
                    cluster_members.append(other_entity)
                    processed.add(other_entity)
            
            # 确定代表实体
            representative = cluster_members[0]
            
            # 记录映射
            for member in cluster_members:
                mapping[member] = representative
                
        logger.info(f"Reduced {len(unique_entities)} entities to {len(set(mapping.values()))} clusters")
        return mapping

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        """计算余弦相似度"""
        vec1 = np.array(v1)
        vec2 = np.array(v2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
            
        return np.dot(vec1, vec2) / (norm1 * norm2)

    def _text_similarity(self, s1: str, s2: str) -> float:
        """
        计算文本相似度 (Jaccard + 编辑距离)
        用于 Embedding 失败时的回退
        """
        s1 = s1.lower().strip()
        s2 = s2.lower().strip()
        
        if s1 == s2:
            return 1.0
            
        # 1. Jaccard Similarity (基于字符 n-gram)
        def get_ngrams(text, n=2):
            return set(text[i:i+n] for i in range(len(text)-n+1))
            
        ngrams1 = get_ngrams(s1)
        ngrams2 = get_ngrams(s2)
        
        if not ngrams1 or not ngrams2:
            return 0.0
            
        intersection = len(ngrams1 & ngrams2)
        union = len(ngrams1 | ngrams2)
        jaccard = intersection / union
        
        # 2. 包含关系奖励
        if s1 in s2 or s2 in s1:
            jaccard = max(jaccard, 0.8)
            
        return jaccard

# 测试代码
if __name__ == "__main__":
    import asyncio
    
    async def test():
        disambiguator = EntityDisambiguator()
        
        entities = [
            "Large Language Model",
            "LLM",
            "Large Language Models",
            "Graph Neural Network",
            "GNN",
            "Graph Neural Networks",
            "Transformer",
            "Transformers"
        ]
        
        print("Disambiguating entities...")
        mapping = await disambiguator.disambiguate(entities)
        
        print("\nMapping Results:")
        for original, canonical in mapping.items():
            print(f"'{original}' -> '{canonical}'")
            
    asyncio.run(test())