import os
import json
import logging
import re
import ast
from pathlib import Path
from collections import defaultdict
from typing import List, Tuple, Union, Dict

from src.configs.logger import get_logger

logger = get_logger("src.modules.utils")


def shut_loggers():
    for logger in logging.Logger.manager.loggerDict:
        logging.getLogger(logger).setLevel(logging.INFO)


def sanitize_filename(filename: str) -> str:
    return re.sub(r'[\\/:"*?<>|]', "_", filename)


def save_result(result: str, path: Union[str, Path]) -> None:
    """save a string to a file, if the prefix dir doesn't exit, create them.

    Args:
        result (str): string waiting to be saved.
        path (str): where to save this string.
    """
    if isinstance(path, str):
        path = Path(path)
    directory = path.parent
    # 如果目录不存在，则创建目录
    if not directory.exists():
        directory.mkdir(exist_ok=True, parents=True)
    # 写入文件
    with path.open("w", encoding="utf-8") as fw:
        fw.write(result)


def load_file_as_string(path: Union[str, Path]) -> str:
    if isinstance(path, str):
        with open(path, "r", encoding="utf-8") as fr:
            return fr.read()
    elif isinstance(path, Path):
        with path.open("r", encoding="utf-8") as fr:
            return fr.read()
    else:
        raise ValueError(path)


def update_config(dic: dict, config_path: str):
    """update the config file

    Args:
        dic (dict): new config dict.
    """
    config_path = Path(config_path)
    if config_path.exists():
        config: dict = json.load(open(config_path, "r", encoding="utf-8"))
        config.update(dic)
    else:
        config: dict = dic
    save_result(json.dumps(config, indent=4), config_path)


def save_as_json(result: dict, path: str):
    """
    Save the result as a JSON file.
    """
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=4)


def load_meta_data(dir_path):
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


def load_prompt(filename: str, **kwargs) -> str:
    """
    读取prompt模板
    
    使用简单的字符串替换来处理占位符，避免 Python str.format() 与 LaTeX 花括号的冲突。
    模板中使用 {key} 作为占位符，使用 {{...}} 表示字面量花括号 {...}。
    """
    path = os.path.join("", filename)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            template = f.read()
        
        # 使用简单的字符串替换，避免 str.format() 与 LaTeX 代码中的 {} 冲突
        result = template
        for key, value in kwargs.items():
            placeholder = '{' + key + '}'
            result = result.replace(placeholder, str(value))
        
        # 将双花括号转换为单花括号（兼容原有模板中的 {{...}} 语法）
        result = result.replace('{{', '{').replace('}}', '}')
        
        return result
    else:
        logger.error(f"Prompt template not found at {path}")
        return ""


Clean_patten = re.compile(pattern=r"```(json|latex)?", flags=re.DOTALL)


def clean_chat_agent_format(content: str):
    content = re.sub(Clean_patten, "", content)
    return content


def load_papers(paper_dir_path_or_papers: Union[Path, List[Dict]]) -> list[dict]:
    if isinstance(paper_dir_path_or_papers, Path):
        papers = []
        for file in os.listdir(paper_dir_path_or_papers):
            file_path = paper_dir_path_or_papers / file
            if file_path.is_dir():
                # 如果是目录，尝试找到其中的 JSON 文件
                dir_files = os.listdir(file_path)
                json_files = [f for f in dir_files if f.endswith('.json')]
                if not json_files:
                    # 使用 DEBUG 级别，因为跳过 pdfs 等非 JSON 目录是预期行为
                    logger.debug(f"Skipping directory with no JSON files: {file_path}")
                    continue
                file_path = file_path / json_files[0]
            
            # 只处理 .json 文件
            if not str(file_path).endswith('.json'):
                logger.debug(f"Skipping non-JSON file: {file_path}")
                continue
                
            if not file_path.is_file():
                logger.error(f"loading paper error: {file_path} is not a file.")
                continue
            
            # 检查文件是否为空
            if file_path.stat().st_size == 0:
                logger.warning(f"Skipping empty file: {file_path}")
                continue
            
            try:
                paper = json.loads(load_file_as_string(file_path))
                papers.append(paper)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON file {file_path}: {e}")
                continue
        return papers
    elif isinstance(paper_dir_path_or_papers, list):
        return paper_dir_path_or_papers
    else:
        raise ValueError()


def load_file_as_text(file_path: Path):
    with file_path.open("r", encoding="utf-8") as fr:
        return fr.read()
