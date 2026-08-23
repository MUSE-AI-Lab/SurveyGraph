# used in latex_table_builder.py

from collections import defaultdict
import json
import os
import re
from typing import List, Tuple
from rapidfuzz import process
from src.configs.logger import get_logger

logger = get_logger("latex_handler.utils")


def load_all_papers(dir_path: str) -> list[dict]:
    """
    Load all JSON files in the directory.
    """
    data = []
    for filename in os.listdir(dir_path):
        if filename.endswith(".json"):
            file_path = os.path.join(dir_path, filename)
            with open(file_path, "r", encoding="utf-8") as file:
                result = json.load(file)  # 将 JSON 文件内容读取为 Python 列表
            data.append(result)
    return data


def load_single_file(file_path):
    """
    Load a single JSON file based on its path.
    """
    # 判断文件路径是否存在
    if not os.path.exists(file_path):
        return ""

    # 如果路径存在，打开并读取文件
    with open(file_path, "r") as file:
        article = json.load(file)
    return article


def fuzzy_match(text: str, candidates: list[str]) -> Tuple[str, int]:
    """Select the text most similar to `text` from the `candidates` list."""
    closest_text, score, idx = process.extractOne(text, candidates)
    return closest_text, idx
