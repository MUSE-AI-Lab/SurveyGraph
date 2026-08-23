import random
from typing import Dict, List, Optional

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_distances

from src.configs.config import (
    BASE_DIR,
    DEFAULT_ITERATION_LIMIT,
    DEFAULT_PAPER_POOL_LIMIT,
    MAX_TOTAL_KEYWORDS,
    MIN_PAPERS_BEFORE_EXPANSION,
    KEYWORD_SIMILARITY_THRESHOLD,
)
from src.configs.logger import get_logger
from src.models.LLM import ChatAgent
from src.models.LLM import EmbedAgent
from src.models.LLM.utils import load_prompt
from src.modules.preprocessor.data_cleaner import DataCleaner
from src.modules.preprocessor.data_fetcher import DataFetcher
from src.configs.config import DEFAULT_DATA_FETCHER_ENABLE_CACHE

logger = get_logger("src.modules.preprocessor.PaperRecaller")


class PaperRecaller:
    """
    Class to iteratively recall and process papers based on evolving keywords.
    """

    def __init__(
        self,
        topic: str,
        iteration_limit: int = DEFAULT_ITERATION_LIMIT,
        paper_pool_limit: int = DEFAULT_PAPER_POOL_LIMIT,
        enable_cache: bool = DEFAULT_DATA_FETCHER_ENABLE_CACHE,
        chat_agent: ChatAgent = None,
    ):
        """
        Initialize the PaperRecaller.

        Args:
            key_word_pool (List[str]): initial key word pool.
            iteration_limit (int): Maximum number of iterations.
            paper_pool_limit (int): Maximum number of papers to maintain in the pool.
        """

        self.iteration_limit = iteration_limit
        self.paper_pool_limit = paper_pool_limit

        self.data_fetcher = DataFetcher(enable_cache=enable_cache)
        self.embed_agent = EmbedAgent()
        self.chat_agent = ChatAgent() if chat_agent is None else chat_agent

        self.paper_pool: List[Dict] = []
        self.keyword_pool: List[str] = []
        self.existing_keyword_embeddings: np.ndarray = np.array(
            self.embed_agent.batch_local_embed([topic])
        ).astype(float)

        if not isinstance(self.existing_keyword_embeddings, np.ndarray):
            self.existing_keyword_embeddings = np.array(
                [self.existing_keyword_embeddings]
            )

    def _search_papers(
        self, keyword: str, page: str, time_s: str, time_e: str
    ) -> List[Dict]:
        """
        Search for papers using Google Scholar and arXiv.

        Args:
            keyword (str): The keyword to search for.

        Returns:
            List[Dict]: A list of paper dictionaries.
        """
        logger.debug(
            f"Searching papers on google: key word={keyword}, page={page}, time_s={time_s}, time_e={time_e}."
        )
        google_papers = self.data_fetcher.search_on_google(
            key_words=keyword, page=page, time_s=time_s, time_e=time_e
        )
        logger.debug(f"Searching papers on arxiv: key word={keyword}.")
        arxiv_papers = self.data_fetcher.search_on_arxiv(key_words=keyword)
        combined_papers = google_papers + arxiv_papers
        logger.debug(
            f"Total papers retrieved from google scholar & arxiv: {len(combined_papers)}"
        )
        return combined_papers

    def _clean_paper_pool(self, new_papers: List[Dict]):
        """
        Clean the paper pool by removing invalid entries and deduplicating.

        Args:
            new_papers (List[Dict]): Newly retrieved papers to add.
        """
        logger.debug("Cleaning and deduplicating paper pool.")

        # Filter out papers
        dc = DataCleaner(new_papers)
        valid_papers = dc.quick_check()
        logger.debug(f"Papers after filtering empty fields: {len(valid_papers)}")

        # Deduplicate based on _id
        existing_ids = {paper["_id"] for paper in self.paper_pool}
        unique_papers = [
            paper for paper in valid_papers if paper["_id"] not in existing_ids
        ]
        logger.debug(f"Papers after deduplication: {len(unique_papers)}")

        self.paper_pool.extend(unique_papers)

    def _embed_papers(self):
        """
        Embed new papers that do not have embeddings.
        """
        logger.debug("Embedding new papers.")

        # Identify papers without embeddings
        new_papers = [paper for paper in self.paper_pool if "embedding" not in paper]
        logger.debug(f"Papers to embed: {len(new_papers)}")

        if not new_papers:
            logger.debug("No new papers to embed.")
            return

        # Extract abstracts for embedding
        texts = [
            ("Title: " + paper["title"] + "\nAbstract: " + paper["abstract"])
            for paper in new_papers
        ]
        embeddings = self.embed_agent.batch_local_embed(texts)

        # Assign embeddings or remove papers with failed embeddings
        for paper, embedding in zip(new_papers, embeddings):
            if (
                isinstance(embedding, list) and embedding
            ):  # filter out "no response" and []
                paper["embedding"] = embedding
            else:
                logger.warning(
                    f"Embedding failed for paper: '{paper.get('title', 'No Title')}'. Removing from pool."
                )
                self.paper_pool.remove(paper)

    def _cluster_papers(self) -> List[List[Dict]]:
        """
        Cluster papers based on their embeddings.

        Returns:
            List[List[Dict]]: A list of clusters, each containing a list of papers.
        """
        logger.debug("Clustering papers based on embeddings.")

        # Prepare embedding matrix
        embeddings = np.array([paper["embedding"] for paper in self.paper_pool])
        if embeddings.size == 0:
            logger.warning("No embeddings available for clustering.")
            return []

        num_clusters = len(self.keyword_pool) + 1
        logger.debug(f"Number of clusters to form: {num_clusters}")

        # Perform KMeans clustering
        kmeans = KMeans(n_clusters=num_clusters, random_state=42)
        labels = kmeans.fit_predict(embeddings)

        # Organize papers into clusters
        clusters = [[] for _ in range(num_clusters)]
        for label, paper in zip(labels, self.paper_pool):
            clusters[label].append(paper)

        logger.debug("Clustering completed.")
        return clusters

    def _should_expand_keywords(self) -> bool:
        """
        判断是否应该扩展关键词。
        
        根据导师建议：如果用户给定的关键词已经足够清晰，就只搜索这一个关键词，
        只有在 embedding 粗筛和 LLM 细筛后 target 不够时才分裂关键词。
        
        Returns:
            bool: 是否应该扩展关键词
        """
        # 1. 如果已经达到最大关键词数量，不再扩展
        if len(self.keyword_pool) >= MAX_TOTAL_KEYWORDS:
            logger.info(f"已达到最大关键词数量限制 ({MAX_TOTAL_KEYWORDS})，停止扩展关键词")
            return False
        
        # 2. 如果论文数量已经足够，不需要扩展
        if len(self.paper_pool) >= MIN_PAPERS_BEFORE_EXPANSION:
            logger.info(f"论文数量已足够 ({len(self.paper_pool)} >= {MIN_PAPERS_BEFORE_EXPANSION})，无需扩展关键词")
            return False
        
        return True

    def _generate_keywords(self, clusters: List[List[Dict]]) -> List[str]:
        """
        Generate keywords from each cluster using ChatAgent.
        
        优化策略：
        1. 限制生成的关键词数量
        2. 过滤掉与现有关键词过于相似的关键词
        3. 支持 "NO_NEW_KEYWORD" 响应

        Args:
            clusters (List[List[Dict]]): Clusters of papers.

        Returns:
            List[str]: Generated keywords.
        """
        logger.debug("Generating keywords from clusters.")
        
        # 检查是否应该扩展关键词
        if not self._should_expand_keywords():
            return []

        prompts = []
        for cluster in clusters:
            sampled_papers = random.sample(cluster, min(15, len(cluster)))
            titles = [paper["title"] for paper in sampled_papers]
            abstracts = [paper["abstract"] for paper in sampled_papers]
            if len(self.paper_pool) >= 1000:
                combined_text = "\n".join([f"Title: {t}\n" for t in titles])
            else:
                combined_text = "\n".join(
                    [f"Title: {t}\nAbstract: {a}" for t, a in zip(titles, abstracts)]
                )
            exclude_keywords = ", ".join(self.keyword_pool)
            prompt = load_prompt(
                f"{BASE_DIR}/resources/LLM/prompts/preprocessor/PaperRecall_gen_key_word.md",
                combined_text=combined_text,
                exclude_keywords=exclude_keywords,
            )
            prompts.append(prompt)

        generated_responses = self.chat_agent.batch_remote_chat(prompts)
        
        # 过滤响应：排除空响应和 "NO_NEW_KEYWORD" 响应
        generated_keywords = []
        for response in generated_responses:
            response = response.strip()
            if response and response.upper() != "NO_NEW_KEYWORD":
                generated_keywords.append(response)
        
        # 过滤掉与现有关键词过于相似的关键词
        if generated_keywords and self.existing_keyword_embeddings.size > 0:
            generated_keywords = self._filter_similar_keywords(generated_keywords)

        logger.debug(f"Generated keywords (after filtering): {generated_keywords}")
        return generated_keywords
    
    def _filter_similar_keywords(self, keywords: List[str]) -> List[str]:
        """
        过滤掉与现有关键词过于相似的关键词。
        
        Args:
            keywords: 待过滤的关键词列表
            
        Returns:
            过滤后的关键词列表
        """
        if not keywords:
            return []
        
        # 嵌入新关键词
        keyword_embeddings = np.array(
            self.embed_agent.batch_local_embed(keywords)
        ).astype(float)
        
        # 计算与现有关键词的相似度
        similarities = 1 - cosine_distances(keyword_embeddings, self.existing_keyword_embeddings)
        
        # 过滤掉相似度过高的关键词
        filtered_keywords = []
        for i, kw in enumerate(keywords):
            max_similarity = similarities[i].max()
            if max_similarity < KEYWORD_SIMILARITY_THRESHOLD:
                filtered_keywords.append(kw)
            else:
                logger.debug(f"关键词 '{kw}' 与现有关键词相似度过高 ({max_similarity:.2f})，已过滤")
        
        return filtered_keywords

    def _select_new_keyword(self, generated_keywords: List[str]) -> str:
        """
        Select the most appropriate new keyword to add from generated keywords.

        Args:
            generated_keywords (List[str]): List of generated keywords.

        Returns:
            str: The selected new keyword.
        """
        logger.debug("Selecting a new keyword from generated keywords.")

        if not generated_keywords:
            logger.warning("No generated keywords to select from.")
            return ""

        # Embed the generated keywords
        keyword_embeddings = np.array(
            self.embed_agent.batch_local_embed(generated_keywords)
        ).astype(float)

        # Calculate distances to existing keywords (return a cosine sim matrix given two sets of vectors)
        distances = cosine_distances(
            keyword_embeddings, self.existing_keyword_embeddings
        )

        # Double the weight for the distance to the initial keyword.
        weights = np.ones(self.existing_keyword_embeddings.shape[0])
        weights[0] = 2

        avg_distances = np.average(distances, axis=1, weights=weights)
        max_distances = distances.max(axis=1)

        # Rank based on weighted average distance (descending) and max distance (ascending)
        avg_rank = avg_distances.argsort()[::-1]
        max_rank = max_distances.argsort()

        # Calculate average rank
        combined_ranks = []
        for i in range(len(generated_keywords)):
            combined_rank = (
                np.where(avg_rank == i)[0][0] + np.where(max_rank == i)[0][0]
            ) / 2
            combined_ranks.append(combined_rank)

        # Select the keyword with the smallest combined rank
        selected_index = np.argmin(combined_ranks)
        new_keyword = generated_keywords[selected_index]

        # Embed and add to existing_keyword_embeddings
        new_embedding = keyword_embeddings[selected_index].reshape(1, -1)
        self.existing_keyword_embeddings = np.vstack(
            [self.existing_keyword_embeddings, new_embedding]
        )

        logger.debug(
            f"Selected new keyword: '{new_keyword}' with index {selected_index}"
        )
        return new_keyword

    def deal_init_keywords(self, key_words: str, page: str, time_s: str, time_e: str):
        key_words = key_words.split(",")

        for kw in key_words:
            new_papers = self._search_papers(kw, page, time_s, time_e)
            self._clean_paper_pool(new_papers)
            self.keyword_pool.append(kw)

            if len(self.paper_pool) >= self.paper_pool_limit:
                logger.info(
                    f"Reached paper pool limit of {self.paper_pool_limit}. Stopping recalling."
                )
                break

        logger.info(f"Initialized keywords retrieved  {len(self.paper_pool)} papers.")

    def recall_papers_iterative(
        self, key_word: str, page: str, time_s: str, time_e: str
    ):
        """
        Perform iterative paper recall and processing.
        
        优化策略（根据导师建议）：
        1. 限制最大关键词数量为 3-4 个
        2. 如果用户给定的关键词已经足够清晰，优先使用原始关键词
        3. 只有在论文数量不足时才扩展关键词
        """
        self.deal_init_keywords(key_word, 5, time_s, time_e)
        
        # 记录初始关键词数量
        initial_keyword_count = len(self.keyword_pool)
        logger.info(f"初始关键词数量: {initial_keyword_count}, 关键词: {self.keyword_pool}")

        for iteration in range(1, self.iteration_limit + 1):
            logger.info(f"============= Iteration {iteration} ===============")
            
            # 检查是否已达到关键词数量限制
            if len(self.keyword_pool) >= MAX_TOTAL_KEYWORDS:
                logger.info(f"已达到最大关键词数量限制 ({MAX_TOTAL_KEYWORDS})，停止迭代")
                break

            # Embed all papers
            self._embed_papers()

            # Cluster papers
            clusters = self._cluster_papers()
            logger.info(f"Formed {len(clusters)} clusters.")

            # Generate new keywords from clusters (内部会检查是否应该扩展)
            generated_keywords = self._generate_keywords(clusters)
            
            if not generated_keywords:
                logger.info("没有生成新关键词（可能已达到限制或现有关键词已足够覆盖）")
                break
            
            logger.info(f"Generated {len(generated_keywords)} keywords from clusters.")

            # Select the most appropriate keyword to add
            new_keyword = self._select_new_keyword(generated_keywords)
            if new_keyword:
                logger.info(f"Selected new keyword: '{new_keyword}'")
                self.keyword_pool.append(new_keyword)
            else:
                logger.warning("No suitable new keyword found. Stopping recalling.")
                break

            # Search for papers using the current keyword
            new_papers = self._search_papers(new_keyword, page, time_s, time_e)
            logger.info(f"Retrieved {len(new_papers)} new papers.")

            # Clean and deduplicate the paper pool
            self._clean_paper_pool(new_papers)
            logger.info(f"Paper pool size after cleaning: {len(self.paper_pool)}")

            if len(self.paper_pool) >= self.paper_pool_limit:
                logger.info(
                    f"Reached paper pool limit of {self.paper_pool_limit}. Stopping recalling."
                )
                break

        logger.info(
            f"Paper recall iterations completed. Total papers in pool: {len(self.paper_pool)}, "
            f"Total keywords: {len(self.keyword_pool)}, Keywords: {self.keyword_pool}"
        )
        return self.paper_pool


# python -m src.modules.preprocessor.paper_recaller
if __name__ == "__main__":
    pr = PaperRecaller()
    papers = pr.recall_papers_iterative(
        "battery electrolyte formulation", "1", "2016", "2025"
    )
