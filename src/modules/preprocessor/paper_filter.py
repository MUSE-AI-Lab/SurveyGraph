import json
import os
import re
from pathlib import Path
from typing import Union
from llama_index.core import Document
from llama_index.core.schema import NodeWithScore
from tqdm import tqdm

from src.configs.config import BASE_DIR, COARSE_GRAINED_TOPK, MIN_FILTERED_LIMIT
from src.configs.logger import get_logger
from src.models.LLM import ChatAgent
from src.models.LLM.utils import load_prompt
from src.models.rag.modeling_llamaidx import LlamaIndexWrapper
from src.modules.utils import load_file_as_string

logger = get_logger("preprocessor.PaperFilter")


class PaperFilter:
    def __init__(self, papers: list[dict], chat_agent: ChatAgent = None):
        self.papers = papers
        self.embed_agent = LlamaIndexWrapper()
        self.chat_agent = chat_agent if chat_agent is not None else ChatAgent()

    @staticmethod
    def from_saved(
        dir_path: Union[str, Path], chat_agent: ChatAgent = None
    ) -> "PaperFilter":
        chat_agent if chat_agent is not None else ChatAgent()
        papers = []
        for f in os.listdir(dir_path):
            if not f.endswith(".json"):
                continue
            p = Path(dir_path) / f
            papers.append(json.loads(load_file_as_string(p)))
        logger.debug(f"Load {len(papers)} papers from saved dir: {dir_path}")
        return PaperFilter(papers=papers, chat_agent=chat_agent)

    def create_index(self):
        docs = []
        for i, paper in tqdm(enumerate(self.papers)):
            title = paper.get("title", "")
            abstract = paper.get("abstract", "")
            doc_for_llamaindex = Document(
                text=title + abstract, metadata={"title": title, "index": i}
            )
            docs.append(doc_for_llamaindex)

        logger.debug(f"==== Creating index of {len(self.papers)} papers.=======")
        self.embed_agent.create_vector_index(nodes=docs, store_local=False)

    def get_top_similarity(self, topic: str, top_k: int = 300) -> list[NodeWithScore]:
        retriever = self.embed_agent.get_retriever(self.embed_agent.index, top_k=top_k)
        results = retriever.retrieve(topic)
        return results

    def coarse_grained_sort(self, topic: str, topk: int = 300) -> list[dict]:
        """Coarse grained sort based on semantic similarity between user topic and paper abstract.
        Seletct the most similar top k papers and return.
        """
        self.create_index()
        nodes = self.get_top_similarity(topic, top_k=topk)
        papers = []
        for node in nodes:
            paper = self.papers[node.metadata["index"]]
            paper["similarity_score"] = node.score
            papers.append(paper)
        return papers

    def fine_grained_sort(
        self, papers: list[dict], topic: str, min_limit: int = 100
    ) -> list[dict]:
        """Given abstract and user topic, use chatgpt to determine the relevant papers.

        Args:
            papers (list[dict]): Papers need to filter.
            topic (str): User input topic.

        Returns:
            list[dict]: Papers that gpt consider whose abstract is relevant to the topic.
        """

        extract_content = lambda text: re.findall(
            r"<Answer>(.*?)</Answer>", text, re.DOTALL
        )[0]
        prompt_path = Path(
            f"{BASE_DIR}/resources/LLM/prompts/preprocessor/judge_relevance.md"
        )
        prompts = [
            load_prompt(prompt_path, Abstract=paper["abstract"], Topic=topic)
            for paper in papers
        ]

        responses = self.chat_agent.batch_remote_chat(
            prompt_l=prompts, desc="batch_remote_chat for fine grained sorting..."
        )

        sorted_papers = []
        for res, paper in zip(responses, papers):
            try:
                ans = extract_content(res)
            except Exception as e:
                ans = ""
                logger.error(
                    f"Error occurs when dealing with gpt's response. Error: {str(e)}. Response: {res}"
                )
            if "1" in ans:
                sorted_papers.append(paper)
        return sorted_papers

    def run(
        self,
        topic: str,
        coarse_grained_topk: int = COARSE_GRAINED_TOPK,
        min_limit: int = MIN_FILTERED_LIMIT,
    ) -> list[dict]:
        coarse_grained_papers = self.coarse_grained_sort(
            topic=topic, topk=coarse_grained_topk
        )
        logger.info(
            f"=========== {len(coarse_grained_papers)} left after coarse_grained ==========="
        )
        fine_grained_papers = self.fine_grained_sort(
            papers=coarse_grained_papers, topic=topic, min_limit=min_limit
        )
        logger.info(
            f"=========== {len(fine_grained_papers)} left after fine_grained ==========="
        )
        return fine_grained_papers


# python -m src.modules.preprocessor.paper_filter
if __name__ == "__main__":
    data_dir = Path(f"{BASE_DIR}/resources/dummy_data/papers")
    topic = """An attention head in a large language model (LLM) is a component of the transformer architecture that focuses on different parts of the input sequence to capture relationships between words and improve the model's understanding of context and meaning."""
    pf = PaperFilter.from_saved(dir_path=data_dir, chat_agent=ChatAgent())
    coarse_grained_papers = pf.coarse_grained_sort(topic=topic, topk=10)
    for p in coarse_grained_papers:
        print(p["similarity_score"])
    filted_paperes = pf.run(topic, 10)
