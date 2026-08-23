from collections import Counter
import json
import time
from pathlib import Path

import requests
from tqdm import tqdm

from src.configs.constants import (
    AVAILABLE_DATA_SOURCES,
    CACHE_DIR,
    OUTPUT_DIR,
    DATASET_DIR,
)
from src.configs.logger import get_logger
from src.configs.config import (
    CRAWLER_BASE_URL,
    CRAWLER_GOOGLE_SCHOLAR_SEND_TASK_URL,
    DEFAULT_DATA_FETCHER_ENABLE_CACHE,
    ARXIV_PROJECTION,
)
from src.modules.preprocessor.utils import wait_for_crawling
from src.modules.utils import load_file_as_string, save_result, sanitize_filename

logger = get_logger("src.modules.preprocessor.DataFetcher")


class DataFetcher:
    BASE_API_URL = CRAWLER_BASE_URL
    SEND_TASK_API_URL = CRAWLER_GOOGLE_SCHOLAR_SEND_TASK_URL
    ARXIV_DB_URL = CRAWLER_GOOGLE_SCHOLAR_SEND_TASK_URL
    BATCH_SIZE = 200
    CRAWLING_TIMEOUT = 300  # Maximum allowed crawling time in seconds. Set to 5 mins
    SINGLE_WORD_LIMIT = 1000  # Maximum papers on single key word searched in arxiv
    OLD_AUTHEN_PATH = Path(OUTPUT_DIR) / "tmp" / "db_authen.txt"

    def __init__(self, enable_cache: bool = DEFAULT_DATA_FETCHER_ENABLE_CACHE):
        self.authen: str = self._get_db_authentication()
        self.search_id_list: list = []  # used for storing all search_id.
        self.enable_cache = enable_cache
        self.arxiv_request_token = ""

    def __try_authentication(self, authentication: str) -> bool:
        # Check if an authentication can be accepted.
        pass

    def load_old_authen(self) -> str:
        if self.OLD_AUTHEN_PATH.exists():
            return load_file_as_string(self.OLD_AUTHEN_PATH)
        else:
            return None

    def _get_db_authentication(self) -> str:
        pass

    def task_submit(self, key_words: str, page: str, time_s: str, time_e: str) -> str:
        """submit single task, return the search_id.

        Returns:
            int: The search ID of the submitted task.
        """
        search_id = int(time.time() * 1000)
        url = f""
        message = f"q={key_words}&page={page}&time_s={time_s}&time_e={time_e}&search_id={search_id}"
        payload = {
            "queue_name": "CRAWLER-PY-GOOGLE-SCHOLAR-SEARCH",
            "msg": message,
            # "queue_type": "Redis",
        }
        headers = {
            "Accept": "application/json, text/plain, */*",
            # "Authorization": self.authen,
            "token": "",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info("Task submitted successfully.")
            logger.debug(
                f"Parameters - key_words: {key_words}, page: {page}, "
                f"time_s: {time_s}, time_e: {time_e}"
            )
            logger.debug(
                f"Task submit sesponse: {json.dumps(response.json(), indent=4)}"
            )
        except requests.RequestException as e:
            logger.error(f"Failed to submit task: {e}")
            raise

        # Save search_id and key_words to config
        logger.info(f"Search id: {search_id}")
        self.search_id_list.append(search_id)

        return str(search_id)

    def task_track_for_google_scholar(
        self, search_id: str
    ) -> tuple[str, int, int, int]:
        """task_track_for_google_scholar"""
        url = f"{self.BASE_API_URL}:9876/api/dq/select"
        payload = {
            "dbName": "crawler_spider",
            "collection": "google_scholar_monitor",
            "filter": json.dumps({"search_id": search_id}),
        }
        headers = {"Authorization": self.authen}

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        content = response.json()["data"][0]
        status = content.get("status", 0)
        final_succ_count = content.get("final_succ_count", 0)
        final_fail_count = content.get("final_fail_count", 0)
        meta_count = content.get("meta_count", 0)

        return status, final_succ_count, final_fail_count, meta_count

    def _get_data(self, collection: str, filter: str, projection: str = "") -> list:
        """Retrieve data from the database."""
        logger.debug(f"collect data from {collection}.")
        url = f"{self.BASE_API_URL}:9876/api/dq/select"
        payload = {
            "dbName": "crawler_spider",
            "collection": collection,
            "sort": "_id",
            "filter": json.dumps(filter),
            "projection": projection,
            "sortType": 1,  # 1 or -1
            "limit": str(self.BATCH_SIZE),
        }
        headers = {
            "Authorization": self.authen,
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()

            data = response.json().get("data", [])
            logger.debug(f"Retrieved {len(data)} records from the database.")
            return data
        except requests.RequestException as e:
            logger.error(f"Failed to retrieve data: {e}")
            return []

    def _get_data_arxiv(
        self,
        keyword: str,
        projection: str = "",
        last_id: str = "00000000000000000000000000000000",
    ) -> list[dict]:
        """Retrieve data from the arxiv database."""
        url = f"{self.ARXIV_DB_URL}:9876/api/search_arxiv"
        payload = json.dumps(
            {
                "abstract": keyword,
                "title": keyword,
                "start_id": last_id,
                "projection": projection,
                "limit": str(self.BATCH_SIZE),
            }
        )

        headers = {
            "token": self.arxiv_request_token,
            "Content-Type": "application/json",
        }
        try:
            response = requests.request("POST", url, headers=headers, data=payload)
            data_l = response.json().get("data", {}).get("datas", [])

            papers = []
            for data in data_l:
                paper = data.get("_source", {})
                paper["_id"] = data.get("_id", "")
                papers.append(paper)
            return papers
        except Exception as e:
            logger.error(f"Failed to fetch papers batch: {str(e)}")
            logger.error(response)
            return []

    def search_on_google(
        self, key_words: str, page: str, time_s: str = "", time_e: str = ""
    ) -> list[dict]:
        dataset_dir = Path(f"{DATASET_DIR}/raw")
        paper_store_dir = dataset_dir / "papers"
        mapping_file_path = dataset_dir / "mappings.json"
        paper_store_dir.mkdir(parents=True, exist_ok=True)
        cache_file_path = Path(CACHE_DIR) / "key_words_cache.json"

        if mapping_file_path.exists():
            file_content = mapping_file_path.open("r", encoding="utf-8").read()
            mapping_dict = json.loads(file_content)

        else:
            mapping_dict = dict(
                [
                    (data_src, {"title_to_id": {}, "id_to_title": {}})
                    for data_src in AVAILABLE_DATA_SOURCES
                ]
            )

        if cache_file_path.exists():
            file_content = cache_file_path.open("r", encoding="utf-8").read()
            cache_dict = json.loads(file_content)
        else:
            cache_dict = dict(
                [(data_src, {"kw_to_ids": {}}) for data_src in AVAILABLE_DATA_SOURCES]
            )

        # ________1. Try to use cache. ________
        if self.enable_cache and (
            key_words in cache_dict["google_scholar"]["kw_to_ids"]
        ):
            logger.info(f"load papers from paper dataset {paper_store_dir}")
            papers = []
            paper_ids = cache_dict["google_scholar"]["kw_to_ids"][key_words]
            for paper_id in paper_ids:
                paper_path = paper_store_dir / f"{paper_id}.json"
                if paper_path.exists():
                    paper_content = json.load(paper_path.open("r", encoding="utf-8"))
                    papers.append(paper_content)
            if len(papers) > 0:
                logger.debug(
                    f"||||google_scholar: Retrieved {len(papers)} papers from cached, whose key_word is {key_words}||||"
                )
                return papers

        # ________2. Try to retrieve online. ________
        cache_dict["google_scholar"]["kw_to_ids"][key_words] = []
        search_id = self.task_submit(key_words, page, time_s, time_e)

        start_time = time.time()
        page = int(page)
        status, final_succ_count, final_fail_count, meta_count = "", -1, -1, 0
        tqdm_bar = tqdm(total=page * 10)
        while (
            meta_count != page * 10 or final_succ_count + final_fail_count < meta_count
        ):
            status, final_succ_count, final_fail_count, meta_count = (
                self.task_track_for_google_scholar(search_id)
            )
            if status == "排队中" or (status != "未搜到结果" and meta_count == 0):
                logger.debug(f"Waiting in the queue...")
                wait_for_crawling(5)
                continue
            tqdm_bar.set_description(
                f"succeeded: {final_succ_count}, failed: {final_fail_count}"
            )
            tqdm_bar.n = final_succ_count + final_fail_count
            tqdm_bar.refresh()
            time.sleep(3)

            if time.time() - start_time > self.CRAWLING_TIMEOUT:
                logger.debug(
                    f"Crawling timeout, timeout limit: {self.CRAWLING_TIMEOUT}s"
                )
                break

        tqdm_bar.close()

        papers = []
        last_id = "000000000000000000000000"
        while True:
            filter = {"_id": {"$gt": last_id}, "search_id": str(search_id)}
            batch = self._get_data("google_scholar", filter=filter)
            for paper in batch:
                paper["from"] = "google"
            papers.extend(batch)
            last_id = batch[-1]["_id"]
            if len(batch) < self.BATCH_SIZE:
                break
        logger.debug(
            f"google_scholar: Retrieved {len(papers)} papers whose key_word is {key_words}"
        )

        if self.enable_cache:  # update cache
            for paper in papers:
                file_id = paper["_id"]
                if "title" not in paper:
                    logger.debug(f"title not in {file_id}")
                file_title = (
                    paper["title"]
                    if "title" in paper
                    else f"unk title, and id {file_id}"
                )
                filename = file_id + ".json"
                filename = sanitize_filename(filename)
                paper_path = paper_store_dir / filename
                cache_dict["google_scholar"]["kw_to_ids"][key_words].append(file_id)
                mapping_dict["google_scholar"]["title_to_id"][file_title] = file_id
                mapping_dict["google_scholar"]["id_to_title"][file_id] = file_title
                if paper_path.exists():
                    logger.debug(f"{paper_path} already exists. Overwrite it.")
                save_result(json.dumps(paper, indent=4), paper_path)

            save_result(json.dumps(cache_dict, indent=4), cache_file_path)
            save_result(json.dumps(mapping_dict, indent=4), mapping_file_path)
            logger.debug(f"Cache is enabled in search_on_google")

        return papers

    def search_on_arxiv(self, key_words: str) -> list[dict]:
        """Splite key words to individual part, and return search results with an overlap of 2 or more."""
        key_words = key_words.split(",")  # keywords is splited by comma
        id_counter = Counter()
        id2paper = {}

        for key_word in key_words:
            papers = self.search_on_arxiv_single_word(key_word)

            _ids = [paper["_id"] for paper in papers]
            id_counter.update(_ids)
            id2paper.update({paper["_id"]: paper for paper in papers})

        overlaped_papers = [
            paper for _id, paper in id2paper.items() if id_counter[_id] >= 1
        ]
        logger.debug(
            f"Searched {len(id_counter)} papers for {key_words}, return {len(overlaped_papers)} overlaped degree greater than 2 papers"
        )
        return overlaped_papers

    def search_on_arxiv_single_word(
        self, key_word: str, projection=ARXIV_PROJECTION
    ) -> list[dict]:
        """Retrieve all papers from the arXiv database where the title or abstract contains the specified keyword. Essentially this function returns papers where `key_word` appears as a substring within the title or abstract.

        Args:
            key_words (str): a substring might appear in a paper's abstract and title.

        Returns:
            list[dict]: The dict contains keys "_id, title, authors, detail_url, abstract, reference"
        """
        dataset_dir = Path(f"{DATASET_DIR}/raw")
        paper_store_dir = dataset_dir / "papers"
        mapping_file_path = dataset_dir / "mappings.json"
        paper_store_dir.mkdir(parents=True, exist_ok=True)
        cache_file_path = Path(CACHE_DIR) / "key_words_cache.json"

        mapping_dict = (
            json.load(open(mapping_file_path, "r", encoding="utf-8"))
            if mapping_file_path.exists()
            else (
                dict(
                    [
                        (data_src, {"title_to_id": {}, "id_to_title": {}})
                        for data_src in AVAILABLE_DATA_SOURCES
                    ]
                )
            )
        )
        cache_dict = (
            json.load(open(cache_file_path, "r", encoding="utf-8"))
            if cache_file_path.exists()
            else (
                dict(
                    [
                        (data_src, {"kw_to_ids": {}})
                        for data_src in AVAILABLE_DATA_SOURCES
                    ]
                )
            )
        )

        if self.enable_cache and (key_word in cache_dict["arxiv"]["kw_to_ids"]):
            logger.info(f"load papers from paper dataset {paper_store_dir}")
            papers = []
            paper_ids = cache_dict["arxiv"]["kw_to_ids"][key_word]
            for paper_id in paper_ids:
                paper_path = paper_store_dir / f"{paper_id}.json"
                if paper_path.exists():
                    paper_content = json.load(paper_path.open("r", encoding="utf-8"))
                    papers.append(paper_content)
            if len(papers) > 0:
                return papers

        cache_dict["arxiv"]["kw_to_ids"][key_word] = []

        papers = []
        last_id = "00000000000000000000000000000000"
        logger.debug(f"Searching papers from arxiv which keyword is {key_word}")
        while True:
            batch = self._get_data_arxiv(
                keyword=key_word, projection=projection, last_id=last_id
            )
            if not batch:
                break

            for paper in batch:
                paper["from"] = "arxiv"
            papers.extend(batch)
            last_id = batch[-1]["_id"]

            if self.enable_cache:
                for data in batch:
                    file_id = data["_id"]
                    file_title = data["title"]
                    filename = file_id + ".json"
                    filename = sanitize_filename(filename)
                    paper_path = paper_store_dir / filename
                    cache_dict["arxiv"]["kw_to_ids"][key_word].append(file_id)
                    mapping_dict["arxiv"]["title_to_id"][file_title] = file_id
                    mapping_dict["arxiv"]["id_to_title"][file_id] = file_title
                    # if paper_path.exists():
                    #     logger.debug(f"{paper_path} already exists. Overwrite it.")
                    save_result(json.dumps(data, indent=4), paper_path)

            if len(batch) < self.BATCH_SIZE or len(papers) > self.SINGLE_WORD_LIMIT:
                break

        if self.enable_cache:
            save_result(json.dumps(cache_dict, indent=4), cache_file_path)
            save_result(json.dumps(mapping_dict, indent=4), mapping_file_path)

        logger.debug(
            f"arxiv: Retrieved {len(papers)} papers which key_word is {key_word}"
        )
        return papers


# python -m src.modules.preprocessor.data_fetcher
if __name__ == "__main__":
    data_fetcher = DataFetcher()
