"""
语义实体抽取器 - SemanticEntityExtractor

借鉴NLP-AKG的设计，从论文中抽取细粒度语义实体：
- Problem: 论文解决的问题
- Method: 提出的方法
- Model: 提出的模型名称
- Task: 应用的任务
- Dataset: 使用的数据集
- Metric: 评估指标
- Innovation: 主要创新点

抽取流程：
1. 从摘要+标题抽取：Problem, Method, Model, Task
2. 从实验部分/表格抽取：Dataset, Metric
3. 综合生成：Innovation
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum

from loguru import logger

from src.models.LLM.ChatAgent import ChatAgent
from src.configs.config import DEFAULT_CHATAGENT_MODEL, ENTITY_EXTRACTION_WORKERS


class SemanticEntityType(Enum):
    """语义实体类型"""
    PROBLEM = "problem"
    METHOD = "method"
    MODEL = "model"
    TASK = "task"
    DATASET = "dataset"
    METRIC = "metric"
    INNOVATION = "innovation"


@dataclass
class SemanticEntity:
    """语义实体"""
    entity_type: SemanticEntityType
    value: str
    confidence: float = 1.0
    source: str = "abstract"  # abstract, table, full_text, inferred
    canonical_value: Optional[str] = None  # 消歧后的标准值
    
    def to_dict(self) -> Dict:
        return {
            "entity_type": self.entity_type.value,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "canonical_value": self.canonical_value
        }


@dataclass
class PaperSemanticEntities:
    """论文的语义实体集合"""
    paper_id: str
    title: str
    problems: List[SemanticEntity] = field(default_factory=list)
    methods: List[SemanticEntity] = field(default_factory=list)
    models: List[SemanticEntity] = field(default_factory=list)
    tasks: List[SemanticEntity] = field(default_factory=list)
    datasets: List[SemanticEntity] = field(default_factory=list)
    metrics: List[SemanticEntity] = field(default_factory=list)
    innovations: List[SemanticEntity] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "problems": [e.to_dict() for e in self.problems],
            "methods": [e.to_dict() for e in self.methods],
            "models": [e.to_dict() for e in self.models],
            "tasks": [e.to_dict() for e in self.tasks],
            "datasets": [e.to_dict() for e in self.datasets],
            "metrics": [e.to_dict() for e in self.metrics],
            "innovations": [e.to_dict() for e in self.innovations]
        }
    
    def get_all_entities(self) -> List[SemanticEntity]:
        """获取所有实体"""
        return (
            self.problems + self.methods + self.models + 
            self.tasks + self.datasets + self.metrics + self.innovations
        )
    
    def entity_count(self) -> int:
        """实体总数"""
        return len(self.get_all_entities())


class SemanticEntityExtractor:
    """
    语义实体抽取器
    
    从论文中抽取细粒度语义实体，借鉴NLP-AKG的设计思路
    """
    
    # 抽取Prompt模板
    EXTRACT_FROM_ABSTRACT_PROMPT = """You are an expert in analyzing academic papers. Given the title and abstract of a research paper, extract the following semantic entities:

**Title**: {title}

**Abstract**: {abstract}

Please extract and return the following entities in JSON format:

1. **problem**: The main problem or challenge this paper addresses (1-2 sentences, max 50 words)
2. **method**: The main method or approach proposed to solve the problem (1-2 sentences, max 50 words)
3. **model**: The name of the proposed model/framework/system (if any, just the name)
4. **task**: The specific task(s) this paper works on (e.g., "text classification", "question answering")

Return ONLY a valid JSON object with these keys. If an entity is not clearly mentioned, use null.

Example output:
{{
    "problem": "Existing methods fail to capture long-range dependencies in text sequences",
    "method": "A transformer-based architecture with multi-head attention mechanism",
    "model": "BERT",
    "task": ["language understanding", "question answering"]
}}

Your response (JSON only):"""

    EXTRACT_DATASETS_METRICS_PROMPT = """You are an expert in analyzing academic papers. Given the title and abstract of a research paper, extract the datasets and evaluation metrics mentioned.

**Title**: {title}

**Abstract**: {abstract}

Please extract:
1. **datasets**: Names of datasets used for experiments (e.g., "MNIST", "ImageNet", "SQuAD")
2. **metrics**: Evaluation metrics used (e.g., "accuracy", "F1-score", "BLEU")

Return ONLY a valid JSON object. If not mentioned, use empty lists.

Example output:
{{
    "datasets": ["SQuAD", "GLUE", "SuperGLUE"],
    "metrics": ["accuracy", "F1-score", "exact match"]
}}

Your response (JSON only):"""

    GENERATE_INNOVATION_PROMPT = """You are an expert in analyzing academic papers. Based on the following information about a paper, summarize its main innovation in one sentence (max 50 words).

**Title**: {title}
**Problem**: {problem}
**Method**: {method}
**Task**: {task}

The innovation should follow this template:
"To solve [problem] in [task], this paper proposes [method] which achieves [key contribution]."

Return ONLY the innovation sentence, nothing else.

Your response:"""

    EXTRACT_FULL_TEXT_PROMPT = """You are an expert researcher. Analyze the following academic paper content and extract advanced attributes.

**Title**: {title}
**Content**: {content}

Please extract the following in JSON format:
1. **innovation_point**: The core innovation (1 sentence).
2. **limitations**: List of limitations mentioned by authors.
3. **future_work**: Future directions mentioned.
4. **implementation_details**: Key implementation details (e.g., learning rate, batch size, hardware).
5. **ablation_studies**: Summary of ablation studies (what was tested).

Return ONLY valid JSON.
"""

    def __init__(
        self,
        chat_agent: ChatAgent = None,
        max_workers: int = None,
        model: str = None
    ):
        """
        初始化语义实体抽取器
        
        Args:
            chat_agent: LLM对话代理
            max_workers: 并发线程数（默认从 config.ENTITY_EXTRACTION_WORKERS 读取）
            model: 使用的模型（默认使用配置文件中的DEFAULT_CHATAGENT_MODEL）
        """
        self.chat_agent = chat_agent or ChatAgent()
        self.max_workers = max_workers if max_workers is not None else ENTITY_EXTRACTION_WORKERS
        self.model = model or DEFAULT_CHATAGENT_MODEL
        
        logger.info(f"SemanticEntityExtractor initialized with model={self.model}, workers={self.max_workers}")
    
    async def extract_from_paper(
        self,
        paper: Dict[str, Any],
        extract_innovation: bool = True
    ) -> PaperSemanticEntities:
        """
        从单篇论文抽取语义实体
        
        Args:
            paper: 论文信息字典，需包含title和abstract
            extract_innovation: 是否生成创新点
        
        Returns:
            PaperSemanticEntities对象
        """
        paper_id = paper.get("paper_id") or paper.get("id") or paper.get("openalex_id", "unknown")
        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        
        if not title or not abstract:
            logger.warning(f"Paper {paper_id} missing title or abstract, skipping extraction")
            return PaperSemanticEntities(paper_id=paper_id, title=title)
        
        result = PaperSemanticEntities(paper_id=paper_id, title=title)
        
        try:
            # 1. 从摘要抽取Problem, Method, Model, Task
            abstract_entities = await self._extract_from_abstract(title, abstract)
            
            if abstract_entities.get("problem"):
                result.problems.append(SemanticEntity(
                    entity_type=SemanticEntityType.PROBLEM,
                    value=abstract_entities["problem"],
                    source="abstract"
                ))
            
            if abstract_entities.get("method"):
                result.methods.append(SemanticEntity(
                    entity_type=SemanticEntityType.METHOD,
                    value=abstract_entities["method"],
                    source="abstract"
                ))
            
            if abstract_entities.get("model"):
                result.models.append(SemanticEntity(
                    entity_type=SemanticEntityType.MODEL,
                    value=abstract_entities["model"],
                    source="abstract"
                ))
            
            tasks = abstract_entities.get("task", [])
            if isinstance(tasks, str):
                tasks = [tasks]
            for task in tasks:
                if task:
                    result.tasks.append(SemanticEntity(
                        entity_type=SemanticEntityType.TASK,
                        value=task,
                        source="abstract"
                    ))
            
            # 2. 抽取Dataset和Metric
            dataset_metric_entities = await self._extract_datasets_metrics(title, abstract)
            
            for dataset in dataset_metric_entities.get("datasets", []):
                if dataset:
                    result.datasets.append(SemanticEntity(
                        entity_type=SemanticEntityType.DATASET,
                        value=dataset,
                        source="abstract"
                    ))
            
            for metric in dataset_metric_entities.get("metrics", []):
                if metric:
                    result.metrics.append(SemanticEntity(
                        entity_type=SemanticEntityType.METRIC,
                        value=metric,
                        source="abstract"
                    ))
            
            # 3. 生成Innovation
            if extract_innovation and (result.problems or result.methods):
                innovation = await self._generate_innovation(
                    title=title,
                    problem=result.problems[0].value if result.problems else "",
                    method=result.methods[0].value if result.methods else "",
                    task=result.tasks[0].value if result.tasks else ""
                )
                if innovation:
                    result.innovations.append(SemanticEntity(
                        entity_type=SemanticEntityType.INNOVATION,
                        value=innovation,
                        source="inferred"
                    ))
            
            logger.debug(f"Extracted {result.entity_count()} entities from paper {paper_id}")
            
        except Exception as e:
            logger.error(f"Error extracting entities from paper {paper_id}: {e}")
        
        return result

    async def extract_from_full_text(self, title: str, full_text: str) -> Dict[str, Any]:
        """从全文抽取进阶属性"""
        # 截取前 10000 字符 (避免 token 溢出，通常包含 Intro, Method, Conclusion)
        # 更好的做法是分块处理，这里简化
        content = full_text[:15000]
        
        prompt = self.EXTRACT_FULL_TEXT_PROMPT.format(title=title, content=content)
        
        try:
            response = self.chat_agent.remote_chat(
                text_content=prompt,
                temperature=0.2,
                model=self.model
            )
            return self._parse_json_response(response)
        except Exception as e:
            logger.error(f"Full text extraction failed: {e}")
            return {}
    
    async def _extract_from_abstract(self, title: str, abstract: str) -> Dict[str, Any]:
        """从摘要抽取Problem, Method, Model, Task"""
        prompt = self.EXTRACT_FROM_ABSTRACT_PROMPT.format(
            title=title,
            abstract=abstract[:2000]  # 限制长度
        )
        
        try:
            response = self.chat_agent.remote_chat(
                text_content=prompt,
                temperature=0.3,
                model=self.model
            )
            
            # 解析JSON
            result = self._parse_json_response(response)
            return result
            
        except Exception as e:
            logger.error(f"Error in _extract_from_abstract: {e}")
            return {}
    
    async def _extract_datasets_metrics(self, title: str, abstract: str) -> Dict[str, List[str]]:
        """抽取Dataset和Metric"""
        prompt = self.EXTRACT_DATASETS_METRICS_PROMPT.format(
            title=title,
            abstract=abstract[:2000]
        )
        
        try:
            response = self.chat_agent.remote_chat(
                text_content=prompt,
                temperature=0.3,
                model=self.model
            )
            
            result = self._parse_json_response(response)
            return {
                "datasets": result.get("datasets", []),
                "metrics": result.get("metrics", [])
            }
            
        except Exception as e:
            logger.error(f"Error in _extract_datasets_metrics: {e}")
            return {"datasets": [], "metrics": []}
    
    async def _generate_innovation(
        self,
        title: str,
        problem: str,
        method: str,
        task: str
    ) -> Optional[str]:
        """生成Innovation"""
        if not problem and not method:
            return None
        
        prompt = self.GENERATE_INNOVATION_PROMPT.format(
            title=title,
            problem=problem or "not specified",
            method=method or "not specified",
            task=task or "not specified"
        )
        
        try:
            response = self.chat_agent.remote_chat(
                text_content=prompt,
                temperature=0.5,
                model=self.model
            )
            
            # 清理响应
            innovation = response.strip()
            if innovation.startswith('"') and innovation.endswith('"'):
                innovation = innovation[1:-1]
            
            return innovation if len(innovation) > 10 else None
            
        except Exception as e:
            logger.error(f"Error in _generate_innovation: {e}")
            return None
    
    def _parse_json_response(self, response: str) -> Dict:
        """解析LLM返回的JSON"""
        try:
            # 尝试直接解析
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # 尝试提取JSON块
        json_patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'\{[^{}]*\}'
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, response, re.DOTALL)
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue
        
        logger.warning(f"Failed to parse JSON from response: {response[:200]}")
        return {}
    
    async def batch_extract(
        self,
        papers: List[Dict[str, Any]],
        extract_innovation: bool = True,
        show_progress: bool = True
    ) -> List[PaperSemanticEntities]:
        """
        批量抽取语义实体
        
        Args:
            papers: 论文列表
            extract_innovation: 是否生成创新点
            show_progress: 是否显示进度
        
        Returns:
            PaperSemanticEntities列表
        """
        results = []
        
        # 使用线程池并发处理
        def extract_single(paper):
            return asyncio.run(self.extract_from_paper(paper, extract_innovation))
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(extract_single, paper): paper for paper in papers}
            
            from tqdm import tqdm
            iterator = tqdm(as_completed(futures), total=len(futures), desc="Extracting entities") if show_progress else as_completed(futures)
            
            for future in iterator:
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    paper = futures[future]
                    logger.error(f"Error extracting from paper {paper.get('title', 'unknown')}: {e}")
        
        logger.info(f"Extracted entities from {len(results)} papers")
        return results
    
    def extract_shared_entities(
        self,
        entities_a: PaperSemanticEntities,
        entities_b: PaperSemanticEntities
    ) -> Dict[str, List[Tuple[str, str]]]:
        """
        找出两篇论文共享的实体
        
        Args:
            entities_a: 论文A的语义实体
            entities_b: 论文B的语义实体
        
        Returns:
            共享实体字典，key为实体类型，value为(实体A值, 实体B值)列表
        """
        shared = {
            "tasks": [],
            "datasets": [],
            "metrics": [],
            "methods": [],
            "models": []
        }
        
        # 比较Task
        for task_a in entities_a.tasks:
            for task_b in entities_b.tasks:
                if self._entities_similar(task_a.value, task_b.value):
                    shared["tasks"].append((task_a.value, task_b.value))
        
        # 比较Dataset
        for ds_a in entities_a.datasets:
            for ds_b in entities_b.datasets:
                if self._entities_similar(ds_a.value, ds_b.value):
                    shared["datasets"].append((ds_a.value, ds_b.value))
        
        # 比较Metric
        for m_a in entities_a.metrics:
            for m_b in entities_b.metrics:
                if self._entities_similar(m_a.value, m_b.value):
                    shared["metrics"].append((m_a.value, m_b.value))
        
        # 比较Method（使用更宽松的匹配）
        for method_a in entities_a.methods:
            for method_b in entities_b.methods:
                if self._entities_similar(method_a.value, method_b.value, threshold=0.5):
                    shared["methods"].append((method_a.value, method_b.value))
        
        # 比较Model
        for model_a in entities_a.models:
            for model_b in entities_b.models:
                if self._entities_similar(model_a.value, model_b.value):
                    shared["models"].append((model_a.value, model_b.value))
        
        return shared
    
    def _entities_similar(self, value_a: str, value_b: str, threshold: float = 0.8) -> bool:
        """
        判断两个实体值是否相似
        
        使用简单的字符串匹配，后续可以用向量相似度替换
        """
        if not value_a or not value_b:
            return False
        
        # 标准化
        a = value_a.lower().strip()
        b = value_b.lower().strip()
        
        # 完全匹配
        if a == b:
            return True
        
        # 包含关系
        if a in b or b in a:
            return True
        
        # 简单的Jaccard相似度
        words_a = set(a.split())
        words_b = set(b.split())
        
        if not words_a or not words_b:
            return False
        
        intersection = len(words_a & words_b)
        union = len(words_a | words_b)
        
        jaccard = intersection / union if union > 0 else 0
        
        return jaccard >= threshold
    
    def infer_relations_from_shared_entities(
        self,
        entities_a: PaperSemanticEntities,
        entities_b: PaperSemanticEntities
    ) -> List[Dict[str, Any]]:
        """
        基于共享实体推断论文间关系
        
        Args:
            entities_a: 论文A的语义实体
            entities_b: 论文B的语义实体
        
        Returns:
            推断的关系列表
        """
        relations = []
        shared = self.extract_shared_entities(entities_a, entities_b)
        
        # 共享Task -> shares_task关系
        if shared["tasks"]:
            relations.append({
                "relation_type": "shares_task",
                "confidence": min(0.9, 0.6 + 0.1 * len(shared["tasks"])),
                "evidence": f"Shared tasks: {[t[0] for t in shared['tasks'][:3]]}"
            })
        
        # 共享Dataset -> shares_dataset关系
        if shared["datasets"]:
            relations.append({
                "relation_type": "shares_dataset",
                "confidence": min(0.95, 0.7 + 0.1 * len(shared["datasets"])),
                "evidence": f"Shared datasets: {[d[0] for d in shared['datasets'][:3]]}"
            })
        
        # 共享Metric -> shares_baseline关系（可能在同一benchmark上比较）
        if shared["metrics"] and shared["datasets"]:
            relations.append({
                "relation_type": "shares_baseline",
                "confidence": 0.8,
                "evidence": f"Shared metrics on same datasets"
            })
        
        # 共享Method -> shares_methodology关系
        if shared["methods"]:
            relations.append({
                "relation_type": "shares_methodology",
                "confidence": min(0.85, 0.5 + 0.15 * len(shared["methods"])),
                "evidence": f"Similar methods: {[m[0] for m in shared['methods'][:2]]}"
            })
        
        # 共享Model -> is_variant_of关系（可能是变体）
        if shared["models"]:
            relations.append({
                "relation_type": "is_variant_of",
                "confidence": 0.7,
                "evidence": f"Related models: {[m[0] for m in shared['models'][:2]]}"
            })
        
        return relations


# 便捷函数
async def extract_semantic_entities(
    papers: List[Dict[str, Any]],
    max_workers: int = None,
    model: str = "gpt-4o-mini"
) -> List[PaperSemanticEntities]:
    """
    便捷函数：批量抽取语义实体
    
    Args:
        papers: 论文列表
        max_workers: 并发数（默认从 config.ENTITY_EXTRACTION_WORKERS 读取）
        model: 使用的模型
    
    Returns:
        语义实体列表
    """
    if max_workers is None:
        max_workers = ENTITY_EXTRACTION_WORKERS
    extractor = SemanticEntityExtractor(max_workers=max_workers, model=model)
    return await extractor.batch_extract(papers)


if __name__ == "__main__":
    # 测试
    import asyncio
    
    test_papers = [
        {
            "paper_id": "test_001",
            "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
            "abstract": "We introduce a new language representation model called BERT, which stands for Bidirectional Encoder Representations from Transformers. Unlike recent language representation models, BERT is designed to pre-train deep bidirectional representations from unlabeled text by jointly conditioning on both left and right context in all layers. As a result, the pre-trained BERT model can be fine-tuned with just one additional output layer to create state-of-the-art models for a wide range of tasks, such as question answering and language inference, without substantial task-specific architecture modifications. BERT is conceptually simple and empirically powerful. It obtains new state-of-the-art results on eleven natural language processing tasks, including pushing the GLUE score to 80.5% (7.7% point absolute improvement), MultiNLI accuracy to 86.7% (4.6% absolute improvement), SQuAD v1.1 question answering Test F1 to 93.2 (1.5 point absolute improvement) and SQuAD v2.0 Test F1 to 83.1 (5.1 point absolute improvement)."
        },
        {
            "paper_id": "test_002",
            "title": "Attention Is All You Need",
            "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely. Experiments on two machine translation tasks show these models to be superior in quality while being more parallelizable and requiring significantly less time to train. Our model achieves 28.4 BLEU on the WMT 2014 English-to-German translation task, improving over the existing best results, including ensembles, by over 2 BLEU. On the WMT 2014 English-to-French translation task, our model establishes a new single-model state-of-the-art BLEU score of 41.8 after training for 3.5 days on eight GPUs."
        }
    ]
    
    async def test():
        extractor = SemanticEntityExtractor(max_workers=2, model="gpt-4o-mini")
        
        print("Testing single paper extraction...")
        result = await extractor.extract_from_paper(test_papers[0])
        print(f"\nPaper: {result.title}")
        print(f"Problems: {[p.value for p in result.problems]}")
        print(f"Methods: {[m.value for m in result.methods]}")
        print(f"Models: {[m.value for m in result.models]}")
        print(f"Tasks: {[t.value for t in result.tasks]}")
        print(f"Datasets: {[d.value for d in result.datasets]}")
        print(f"Metrics: {[m.value for m in result.metrics]}")
        print(f"Innovations: {[i.value for i in result.innovations]}")
        
        print("\n" + "="*50)
        print("Testing batch extraction...")
        results = await extractor.batch_extract(test_papers)
        
        for r in results:
            print(f"\n{r.title}: {r.entity_count()} entities")
        
        print("\n" + "="*50)
        print("Testing shared entity detection...")
        if len(results) >= 2:
            shared = extractor.extract_shared_entities(results[0], results[1])
            print(f"Shared entities: {shared}")
            
            relations = extractor.infer_relations_from_shared_entities(results[0], results[1])
            print(f"Inferred relations: {relations}")
    
    asyncio.run(test())