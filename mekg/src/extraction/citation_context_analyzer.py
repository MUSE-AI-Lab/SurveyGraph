"""
引用上下文分析器 - CitationContextAnalyzer

核心功能：
1. 从论文全文中定位引用位置
2. 提取引用上下文（前后句）
3. 分析引用意图（Extends, Compares, Uses, Background）

借鉴 NLP-AKG 的分类体系。
"""

import re
import json
import asyncio
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from loguru import logger
from enum import Enum

from src.models.LLM.ChatAgent import ChatAgent

class CitationRelationType(Enum):
    EXTENDS = "extends"
    COMPARES = "compares"
    USES = "uses"
    BACKGROUND = "background"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"

@dataclass
class CitationRelation:
    citing_paper_id: str
    cited_paper_id: str
    relation_type: CitationRelationType
    confidence: float
    context: str
    evidence: str = ""

@dataclass
class CitationContext:
    context: str          # 引用上下文文本
    citation_marker: str  # 引用标记，如 "[1]", "Smith et al."
    relation_type: str    # 推断的关系类型
    confidence: float     # 置信度
    span: Tuple[int, int] # 上下文在全文中的位置

class CitationContextAnalyzer:
    def __init__(self, chat_agent: ChatAgent = None):
        self.chat_agent = chat_agent or ChatAgent()
        
        # 引用标记正则
        self.citation_regex = re.compile(r'(\[[0-9,\s\-]+\]|\([A-Za-z\s\.,]+[0-9]{4}\))')

    async def extract_contexts(self, full_text: str) -> List[CitationContext]:
        """
        从全文中提取所有引用上下文，并使用 LLM 分析关系
        """
        contexts = []
        if not full_text:
            return contexts

        # 1. 定位引用上下文 (使用正则快速定位)
        raw_contexts = self._locate_citation_contexts(full_text)
        
        if not raw_contexts:
            return []

        # 2. 批量分析 (使用 LLM)
        # 为了效率，我们将多个上下文合并成一个 Prompt 发送
        batch_size = 5
        for i in range(0, len(raw_contexts), batch_size):
            batch = raw_contexts[i:i+batch_size]
            analyzed_batch = await self._analyze_batch_with_llm(batch)
            contexts.extend(analyzed_batch)
                
        return contexts

    def _locate_citation_contexts(self, full_text: str) -> List[Dict]:
        """
        定位引用标记及其周围文本
        """
        contexts = []
        sentences = self._split_sentences(full_text)
        
        for i, (sent_text, start_idx, end_idx) in enumerate(sentences):
            matches = self.citation_regex.finditer(sent_text)
            for match in matches:
                marker = match.group()
                
                # 获取上下文：前1句 + 当前句 + 后1句
                context_start = sentences[i-1][1] if i > 0 else start_idx
                context_end = sentences[i+1][2] if i < len(sentences)-1 else end_idx
                
                context_text = full_text[context_start:context_end].strip()
                
                contexts.append({
                    "marker": marker,
                    "context": context_text,
                    "span": (context_start, context_end)
                })
        return contexts

    async def _analyze_batch_with_llm(self, batch: List[Dict]) -> List[CitationContext]:
        """
        使用 LLM 批量分析引用关系
        """
        # 构建 Prompt
        items_str = ""
        for idx, item in enumerate(batch):
            items_str += f"""
Item {idx+1}:
Marker: {item['marker']}
Context: "{item['context']}"
"""

        prompt = f"""Analyze the citation relationships in the following contexts.
For each item, determine the relationship between the citing paper (the author) and the cited paper (referenced by the marker).

Relationship Types:
- **extends**: The author builds upon, improves, or extends the cited work.
- **compares**: The author compares their work with the cited work (e.g., as a baseline).
- **uses**: The author uses the cited work (e.g., dataset, tool, definition) directly.
- **background**: The cited work is mentioned as related work or background info.
- **neutral**: No clear relationship or just a general mention.

Input:
{items_str}

Output ONLY a JSON list of objects with keys: "item_index", "relation_type", "confidence" (0.0-1.0).
Example:
[
  {{"item_index": 1, "relation_type": "extends", "confidence": 0.9}},
  {{"item_index": 2, "relation_type": "background", "confidence": 0.6}}
]
"""
        try:
            response = self.chat_agent.remote_chat(prompt)
            results = self._parse_json(response)
            
            analyzed = []
            for res in results:
                idx = res.get("item_index", 0) - 1
                if 0 <= idx < len(batch):
                    item = batch[idx]
                    analyzed.append(CitationContext(
                        context=item['context'],
                        citation_marker=item['marker'],
                        relation_type=res.get("relation_type", "neutral"),
                        confidence=res.get("confidence", 0.5),
                        span=item['span']
                    ))
            return analyzed
            
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            # Fallback: return neutral for all
            return [
                CitationContext(
                    context=b['context'],
                    citation_marker=b['marker'],
                    relation_type="neutral",
                    confidence=0.0,
                    span=b['span']
                ) for b in batch
            ]

    def _split_sentences(self, text: str) -> List[Tuple[str, int, int]]:
        """简单的分句"""
        sentence_endings = re.compile(r'(?<!et al)(?<!e\.g)(?<!i\.e)(?<!Fig)(?<!Eq)[\.\!\?]\s+')
        sentences = []
        start = 0
        for match in sentence_endings.finditer(text):
            end = match.end()
            sentences.append((text[start:end].strip(), start, end))
            start = end
        if start < len(text):
            sentences.append((text[start:].strip(), start, len(text)))
        return sentences

    def _parse_json(self, text: str) -> List[Dict]:
        try:
            # 尝试提取 JSON 块
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return json.loads(text)
        except:
            return []

# 测试代码
if __name__ == "__main__":
    async def test():
        analyzer = CitationContextAnalyzer()
        text = """
        Graph Neural Networks have achieved great success.
        Kipf et al. [1] proposed GCN for semi-supervised classification.
        However, GCN fails to handle directed graphs.
        To address this, we extend the method of [1] by introducing a new attention mechanism.
        We also compare our model with GAT [2] on three datasets.
        We use the Cora dataset [3] for evaluation.
        """
        
        print("Analyzing text with LLM...")
        results = await analyzer.extract_contexts(text)
        for res in results:
            print(f"\nMarker: {res.citation_marker}")
            print(f"Type: {res.relation_type} (conf={res.confidence})")
            print(f"Context: ...{res.context}...")

    asyncio.run(test())