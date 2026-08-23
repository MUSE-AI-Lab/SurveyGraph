"""
Relation Reasoner
使用 LLM 基于论文的深度属性来推断论文间的语义关系。
"""

from typing import Dict, List, Any, Optional
import json
from loguru import logger
from src.models.LLM.ChatAgent import ChatAgent
from src.configs.config import DEFAULT_CHATAGENT_MODEL

class RelationReasoner:
    RELATION_INFERENCE_PROMPT = """You are an expert researcher. Analyze the relationship between two research papers based on their details.

**Paper A (Source)**:
- Title: {title_a}
- Method: {method_a}
- Innovation: {innovation_a}
- Abstract: {abstract_a}

**Paper B (Target)**:
- Title: {title_b}
- Method: {method_b}
- Innovation: {innovation_b}
- Abstract: {abstract_b}

Determine the semantic relationship from Paper A to Paper B. Choose ONE from:
- **EXTENDS**: A builds upon B's work or improves B's method.
- **USES**: A uses B as a component or baseline.
- **COMPARES**: A compares with B (e.g., A outperforms B).
- **ALTERNATIVE**: A proposes an alternative approach to B for the same problem.
- **BACKGROUND**: B is just background literature for A.
- **NONE**: No significant direct relationship found.

Return JSON format:
{{
    "relation_type": "EXTENDS",
    "confidence": 0.9,
    "reasoning": "Paper A explicitly mentions improving the efficiency of B's attention mechanism."
}}

Your response (JSON only):"""

    def __init__(self, model: str = None):
        self.chat_agent = ChatAgent()
        self.model = model or DEFAULT_CHATAGENT_MODEL

    async def infer_relation(self, paper_a: Dict, paper_b: Dict) -> Optional[Dict]:
        """推断 Paper A -> Paper B 的关系"""
        
        # 准备 prompt 数据，截断过长的内容
        data = {
            "title_a": paper_a.get('title', 'Unknown'),
            "method_a": paper_a.get('method_info', {}).get('name', 'Unknown'),
            "innovation_a": (paper_a.get('innovations') or [''])[0],
            "abstract_a": paper_a.get('abstract', '')[:500],
            
            "title_b": paper_b.get('title', 'Unknown'),
            "method_b": paper_b.get('method_info', {}).get('name', 'Unknown'),
            "innovation_b": (paper_b.get('innovations') or [''])[0],
            "abstract_b": paper_b.get('abstract', '')[:500],
        }
        
        prompt = self.RELATION_INFERENCE_PROMPT.format(**data)
        
        try:
            response = self.chat_agent.remote_chat(
                text_content=prompt,
                temperature=0.1, # 需要精确判断
                model=self.model
            )
            
            # 解析 JSON
            start = response.find('{')
            end = response.rfind('}') + 1
            if start != -1 and end != -1:
                json_str = response[start:end]
                result = json.loads(json_str)
                
                if result.get('relation_type') and result['relation_type'] != 'NONE':
                    return result
                    
            return None
            
        except Exception as e:
            logger.error(f"Relation inference failed: {e}")
            return None