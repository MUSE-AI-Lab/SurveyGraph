"""
学术答疑服务 - AcademicQAService

提供基于论文内容的问答功能，支持：
1. 单文章深度问答
2. 多轮对话
3. 选段回复（引用原文）
4. 跨文章综合问答
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger

from src.models.LLM.ChatAgent import ChatAgent
from mekg.src.storage.semantic_entity_db import SemanticEntityDB

class AcademicQAService:
    """
    学术答疑服务
    """
    
    def __init__(self, db_path: str = "data/graph_db/global_academic_graph.db"):
        """
        初始化答疑服务
        
        Args:
            db_path: 全局数据库路径
        """
        self.db = SemanticEntityDB(db_path)
        self.chat_agent = ChatAgent()
        logger.info(f"AcademicQAService initialized with DB: {db_path}")
        
    def get_paper_content(self, paper_id: str) -> Optional[str]:
        """
        获取论文全文内容
        
        Args:
            paper_id: 论文ID
            
        Returns:
            全文内容或None
        """
        paper = self.db.get_paper(paper_id)
        if not paper:
            return None
            
        # 尝试从 attributes 中获取 md_path 或直接获取全文
        # 注意：实际项目中全文可能存储在文件系统中
        # 这里假设我们能通过某种方式获取到全文
        
        # 模拟逻辑：检查 outputs 目录下是否有对应的 json
        # 实际应用中应该从数据库记录的路径读取
        return paper.get("abstract", "") # 暂时返回摘要作为兜底

    async def answer_question(
        self, 
        question: str, 
        paper_ids: List[str], 
        history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        回答关于论文的问题
        
        Args:
            question: 用户问题
            paper_ids: 相关论文ID列表
            history: 对话历史 [{"role": "user", "content": "..."}, ...]
            
        Returns:
            回答结果 {
                "answer": str,
                "references": [{"paper_id": str, "snippet": str}, ...]
            }
        """
        # 1. 准备上下文
        contexts = []
        for pid in paper_ids:
            paper = self.db.get_paper(pid)
            if paper:
                content = self.get_paper_content(pid)
                contexts.append(f"Paper ID: {pid}\nTitle: {paper['title']}\nContent: {content}")
        
        context_str = "\n\n---\n\n".join(contexts)
        
        # 2. 构建Prompt
        system_prompt = """You are an academic assistant. Answer the user's question based on the provided paper contents.
If the answer is found in the text, cite the Paper ID and provide the relevant snippet.
If you are unsure or the information is missing, state it clearly.
Support multi-turn conversation by considering the history.
"""
        
        prompt = f"""Context Information:
{context_str}

User Question: {question}

Please provide a detailed answer with citations."""

        # 3. 调用LLM
        # 这里简化处理，直接调用 remote_chat
        # 实际应用中应该将 history 传入
        response = self.chat_agent.remote_chat(prompt, system_prompt=system_prompt)
        
        return {
            "answer": response,
            "paper_ids": paper_ids
        }

    async def extract_summary(self, paper_id: str) -> Dict[str, Any]:
        """
        提取文章概况（创新点、不足等）
        
        Args:
            paper_id: 论文ID
            
        Returns:
            概况信息
        """
        paper = self.db.get_paper(paper_id)
        if not paper:
            return {"error": "Paper not found"}
            
        # 如果数据库中已经有了提取好的实体，直接返回
        # 否则调用 LLM 提取
        
        # 这里演示调用 LLM 提取
        content = self.get_paper_content(paper_id)
        
        prompt = f"""Analyze the following paper and extract its summary:
Title: {paper['title']}
Content: {content}

Please provide:
1. Core Innovation
2. Main Limitations
3. Key Methodology
4. Potential Impact
"""
        response = self.chat_agent.remote_chat(prompt)
        return {
            "paper_id": paper_id,
            "summary": response
        }

if __name__ == "__main__":
    # 测试代码
    service = AcademicQAService("data/graph_db/test_global_graph.db")
    # asyncio.run(service.answer_question("What is the main contribution of BERT?", ["arXiv:1810.04805"]))