"""
Community Labeler - 社区命名和特征提取

功能：
1. 为论文社区生成语义标签（2-5词）
2. 提取社区特征（研究主题、方法、趋势）
3. 批量处理多个社区
4. 生成社区摘要

借鉴NLP-AKG的设计：通过代表性论文的标题和摘要来理解社区主题
"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from loguru import logger

from src.models.LLM.ChatAgent import ChatAgent
from src.configs.config import DEFAULT_CHATAGENT_MODEL


@dataclass
class CommunityInfo:
    """社区信息"""
    community_id: int
    name: str
    paper_count: int
    top_papers: List[Dict[str, Any]]
    features: Dict[str, Any]
    summary: str = ""


class CommunityLabeler:
    """
    社区命名器
    
    使用LLM为论文社区生成语义标签和特征描述
    """
    
    # 命名Prompt
    LABEL_PROMPT = """You are a scientific taxonomy expert. Below are titles and abstracts of research papers belonging to the same research community.

Papers:
{paper_text}

Task:
Analyze these papers and generate a specific, concise Topic Name (2-5 words) that best represents this research community.

Requirements:
1. Be specific (not just "Machine Learning" but "Transformer-based NLP")
2. Capture the core research theme
3. Use standard academic terminology

Examples: "Large Language Model Agents", "Retrieval Augmented Generation", "Multimodal Representation Learning"

Topic Name (2-5 words only):"""

    # 特征提取Prompt
    FEATURE_PROMPT = """Analyze the following research papers from the same community and extract key features.

Papers:
{paper_text}

Extract the following in JSON format:
{{
    "main_topic": "The primary research topic (2-5 words)",
    "sub_topics": ["List of 2-3 sub-topics"],
    "key_methods": ["List of 2-3 key methods/techniques used"],
    "research_trend": "Brief description of the research trend (1 sentence)",
    "application_domains": ["List of 1-2 application domains"]
}}

JSON output:"""

    # 摘要生成Prompt
    SUMMARY_PROMPT = """Based on the following research papers from a community named "{community_name}", write a brief summary (2-3 sentences) describing what this research community focuses on.

Papers:
{paper_text}

Summary:"""

    def __init__(self, model: str = None):
        self.chat_agent = ChatAgent()
        self.model = model or DEFAULT_CHATAGENT_MODEL
        logger.info(f"CommunityLabeler initialized with model: {self.model}")
    
    def _build_paper_text(self, papers: List[Dict[str, Any]], include_abstract: bool = True, max_papers: int = 5) -> str:
        """构建论文文本"""
        paper_text = ""
        for i, p in enumerate(papers[:max_papers]):
            title = p.get('title', 'Unknown')
            paper_text += f"{i+1}. Title: {title}\n"
            
            if include_abstract:
                abstract = p.get('abstract', '')
                if abstract:
                    # 截断摘要
                    abstract = abstract[:300] + "..." if len(abstract) > 300 else abstract
                    paper_text += f"   Abstract: {abstract}\n"
            
            paper_text += "\n"
        
        return paper_text
    
    async def label_community(self, papers: List[Dict[str, Any]]) -> str:
        """
        为社区生成标签名称
        
        Args:
            papers: 论文列表，每篇论文需包含 'title'，可选 'abstract'
            
        Returns:
            生成的Topic名称（2-5词）
        """
        if not papers:
            return "Unknown Community"
        
        # 按引用数排序，取代表性论文
        sorted_papers = sorted(papers, key=lambda x: x.get('citations', 0), reverse=True)
        paper_text = self._build_paper_text(sorted_papers, include_abstract=True, max_papers=5)
        
        prompt = self.LABEL_PROMPT.format(paper_text=paper_text)
        
        try:
            response = self.chat_agent.remote_chat(
                text_content=prompt,
                temperature=0.3,
                model=self.model
            )
            
            # 清理响应
            label = response.strip().strip('"').strip("'")
            
            # 移除可能的前缀
            if ":" in label:
                label = label.split(":")[-1].strip()
            
            # 限制长度
            words = label.split()
            if len(words) > 5:
                label = " ".join(words[:5])
            
            logger.info(f"Generated community label: {label}")
            return label
            
        except Exception as e:
            logger.error(f"Failed to label community: {e}")
            return "Unlabeled Community"
    
    async def extract_features(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        提取社区特征
        
        Args:
            papers: 论文列表
            
        Returns:
            特征字典
        """
        if not papers:
            return {}
        
        sorted_papers = sorted(papers, key=lambda x: x.get('citations', 0), reverse=True)
        paper_text = self._build_paper_text(sorted_papers, include_abstract=True, max_papers=5)
        
        prompt = self.FEATURE_PROMPT.format(paper_text=paper_text)
        
        try:
            response = self.chat_agent.remote_chat(
                text_content=prompt,
                temperature=0.3,
                model=self.model
            )
            
            # 解析JSON
            import json
            import re
            
            # 尝试提取JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                features = json.loads(json_match.group())
                return features
            
            return {}
            
        except Exception as e:
            logger.error(f"Failed to extract features: {e}")
            return {}
    
    async def generate_summary(self, papers: List[Dict[str, Any]], community_name: str) -> str:
        """
        生成社区摘要
        
        Args:
            papers: 论文列表
            community_name: 社区名称
            
        Returns:
            摘要文本
        """
        if not papers:
            return ""
        
        sorted_papers = sorted(papers, key=lambda x: x.get('citations', 0), reverse=True)
        paper_text = self._build_paper_text(sorted_papers, include_abstract=True, max_papers=5)
        
        prompt = self.SUMMARY_PROMPT.format(
            community_name=community_name,
            paper_text=paper_text
        )
        
        try:
            response = self.chat_agent.remote_chat(
                text_content=prompt,
                temperature=0.5,
                model=self.model
            )
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return ""
    
    async def process_community(
        self,
        community_id: int,
        papers: List[Dict[str, Any]],
        extract_features: bool = True,
        generate_summary: bool = True
    ) -> CommunityInfo:
        """
        完整处理单个社区
        
        Args:
            community_id: 社区ID
            papers: 社区内的论文列表
            extract_features: 是否提取特征
            generate_summary: 是否生成摘要
            
        Returns:
            CommunityInfo对象
        """
        # 1. 生成名称
        name = await self.label_community(papers)
        
        # 2. 提取特征
        features = {}
        if extract_features:
            features = await self.extract_features(papers)
        
        # 3. 生成摘要
        summary = ""
        if generate_summary:
            summary = await self.generate_summary(papers, name)
        
        # 4. 获取代表性论文
        top_papers = sorted(papers, key=lambda x: x.get('citations', 0), reverse=True)[:5]
        
        return CommunityInfo(
            community_id=community_id,
            name=name,
            paper_count=len(papers),
            top_papers=top_papers,
            features=features,
            summary=summary
        )
    
    async def batch_label_communities(
        self,
        communities: Dict[int, List[Dict[str, Any]]],
        min_size: int = 5,
        max_concurrent: int = 3
    ) -> List[CommunityInfo]:
        """
        批量处理多个社区
        
        Args:
            communities: {community_id: [papers]}
            min_size: 最小社区大小
            max_concurrent: 最大并发数
            
        Returns:
            CommunityInfo列表
        """
        results = []
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(comm_id: int, papers: List[Dict]):
            async with semaphore:
                if len(papers) < min_size:
                    return None
                return await self.process_community(comm_id, papers)
        
        tasks = [
            process_with_semaphore(comm_id, papers)
            for comm_id, papers in communities.items()
        ]
        
        processed = await asyncio.gather(*tasks)
        results = [r for r in processed if r is not None]
        
        logger.info(f"Processed {len(results)} communities")
        return results


# 便捷函数
async def label_community(papers: List[Dict[str, Any]]) -> str:
    """便捷函数：为社区生成标签"""
    labeler = CommunityLabeler()
    return await labeler.label_community(papers)


async def process_communities(
    communities: Dict[int, List[Dict[str, Any]]],
    min_size: int = 5
) -> List[CommunityInfo]:
    """便捷函数：批量处理社区"""
    labeler = CommunityLabeler()
    return await labeler.batch_label_communities(communities, min_size)


if __name__ == "__main__":
    # 测试
    test_papers = [
        {
            "title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "abstract": "We introduce BERT, a new language representation model...",
            "citations": 50000
        },
        {
            "title": "GPT-3: Language Models are Few-Shot Learners",
            "abstract": "We demonstrate that scaling up language models...",
            "citations": 30000
        },
        {
            "title": "Attention Is All You Need",
            "abstract": "The dominant sequence transduction models are based on...",
            "citations": 80000
        }
    ]
    
    async def test():
        labeler = CommunityLabeler()
        
        # 测试命名
        name = await labeler.label_community(test_papers)
        print(f"Community Name: {name}")
        
        # 测试特征提取
        features = await labeler.extract_features(test_papers)
        print(f"Features: {features}")
        
        # 测试完整处理
        info = await labeler.process_community(0, test_papers)
        print(f"Community Info: {info}")
    
    asyncio.run(test())