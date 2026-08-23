from collections import Counter
import os, sys, json, re
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
import traceback

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))  # run code in any path

import requests

from src.configs.constants import OUTPUT_DIR
from src.configs.logger import get_logger
from src.configs.config import (
    FIG_RETRIEVE_Authorization,
    FIG_RETRIEVE_TOKEN,
    FIG_CHUNK_SIZE,
    MATCH_TOPK,
    FIG_RETRIEVE_URL,
    ENHANCED_FIG_RETRIEVE_URL,
)
from src.configs.constants import OUTPUT_DIR

logger = get_logger("src.modules.fig_retrieve.fig_retriever")


class FigRetriever(object):
    def __init__(self, is_debug=False):
        self.fig_retrieve_url = FIG_RETRIEVE_URL
        self.enhanced_fig_retrieve_url = ENHANCED_FIG_RETRIEVE_URL
        self.authorization = FIG_RETRIEVE_Authorization
        self.token = FIG_RETRIEVE_TOKEN

        self.fig_retrieve_debug_dir = Path(f"{OUTPUT_DIR}/debug/fig_retrieve")
        self.is_debug = is_debug
        if self.is_debug:
            self.fig_retrieve_debug_dir.mkdir(exist_ok=True, parents=True)
            logger.debug(
                f"FigRetriever is using debug mode, create the directory of {self.fig_retrieve_debug_dir}."
            )

    def wrap_data_1(
        self, query_text: str, image_list: list, match_topk: int = MATCH_TOPK
    ):
        data = {
            "image_list": image_list,
            "query_text": query_text,
            "match_topk": match_topk,
        }
        return data

    def wrap_data_2(
        self,
        query_text: str,
        figure_linkes: list,
        paper_ids: list,
        sources: list,
        match_topk: int = MATCH_TOPK,
    ):
        data = {
            "pic_urls": figure_linkes,
            "paper_ids": paper_ids,
            "sources": sources,
            "query": query_text,
            "match_topk": match_topk,
        }
        return data

    def retrieve_relevant_images(
        self, image_data_dict: dict, request_url: str = FIG_RETRIEVE_URL
    ):
        # 开始时间
        start_time = datetime.now()

        response = requests.post(
            request_url,
            json=image_data_dict,
            headers={"Authorization": self.authorization, "token": self.token},
        )
        results = response.json()
        if request_url == self.fig_retrieve_url:
            figure_list = results["figure_list"]
        elif request_url == self.enhanced_fig_retrieve_url:
            if "topk_entries" not in results:
                logger.error(
                    f"topk_entries not in topk_entries； request_url: {request_url}; image_data_dict:{image_data_dict}; results {results}"
                )
            try:
                for one in results["topk_entries"]:
                    one["figure_desc"] = one["caption"]
                    one["figure_link"] = one["pic_url"]
                    one["figure_size"] = one["pic_size"]
                figure_list = results["topk_entries"]
                if one["caption"] == "ERROR!!!":
                    logger.error(
                        ("-" * 100 + "\n").join(
                            [
                                f"ERROR!!! in topk_entries. request_url: {request_url}",
                                f"image_data_dict:{image_data_dict};",
                                f"results {results} ",
                            ]
                        )
                    )
            except Exception as e:
                tb_str = traceback.format_exc()
                logger.error(
                    f"An error occurred: {e}; The traceback: {tb_str}； results: {results} "
                )
                figure_list = []
                return figure_list
        else:
            raise NotImplemented()

        # debug content
        if self.is_debug:
            self.download_figs(figure_list)

        # 结束时间
        end_time = datetime.now()

        # 计算时间差
        duration = end_time - start_time
        total_seconds = int(duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        # 格式化输出时间
        logger.debug(
            f"Time taken for retrieve_relevant_images: {hours} hours, {minutes} minutes, {seconds} seconds"
        )

        return figure_list

    def extract_fig_name(self, fig_link: str):
        parsed_url = urlparse(fig_link)
        return parsed_url.path.strip().split("/")[-1]

    def download_figs(
        self, figure_list: list, figs_dir: Path = None, chunk_size: int = FIG_CHUNK_SIZE
    ):
        # Define the directory to store images
        figs_dir = (
            os.path.join(self.fig_retrieve_debug_dir, "figs")
            if figs_dir is None
            else figs_dir
        )

        # Create the directory if it doesn't exist
        os.makedirs(figs_dir, exist_ok=True)

        image_paths = []
        # Loop through each image link and download the image
        for idx, one in enumerate(figure_list):
            try:
                # Send a GET request to the image URL
                response = requests.get(one["figure_link"], stream=True)
                response.raise_for_status()  # Raise an error for bad responses

                # Define the path for saving the image
                image_path = os.path.join(
                    figs_dir, self.extract_fig_name(fig_link=one["figure_link"])
                )

                # Write the content of the response (image) to a file
                with open(image_path, "wb") as fw:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        fw.write(chunk)
                    logger.info(f"Image {idx + 1} downloaded and saved to {image_path}")
                image_paths.append(image_path)

            except requests.exceptions.RequestException as e:
                logger.info(f"Failed to download {one['figure_link']}: {e}")
        return image_paths
