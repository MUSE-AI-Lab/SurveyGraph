import base64
import os
import re
from pathlib import Path
from string import Template

import tiktoken

from src.configs.config import CUT_WORD_LENGTH
from src.configs.logger import get_logger

logger = get_logger("src.modules.LLM.utils")


def load_prompt(file_path: Path, safe_substitute: bool = False, **kwargs):
    """
    读取prompt模板
    
    Args:
        file_path: prompt 模板文件路径
        safe_substitute: 是否使用安全替换模式。当为 True 时，使用 string.Template
                        的 safe_substitute 方法，可以安全处理包含 {} 的内容（如 JSON）。
                        当为 False 时，使用传统的 str.format() 方法。
        **kwargs: 模板变量
        
    Returns:
        格式化后的 prompt 字符串
    """
    if os.path.exists(file_path):
        with open(file_path, encoding="utf-8") as f:
            template_content = f.read()
            
        if safe_substitute:
            # 使用 string.Template，它使用 $var 或 ${var} 语法
            # 需要将 {var} 转换为 ${var} 格式
            # 先将模板中的 {key} 转换为 ${key}
            for key in kwargs.keys():
                template_content = template_content.replace(f"{{{key}}}", f"${{{key}}}")
            template = Template(template_content)
            return template.safe_substitute(**kwargs)
        else:
            return template_content.format(**kwargs)
    else:
        logger.error(f"Prompt template not found at {file_path}")
        return ""


def num_token_from_string(text: str, model: str = "gpt-4o-mini") -> int:
    """Return token nums of a string."""
    encoding = tiktoken.encoding_for_model(model)
    encoded_text = encoding.encode(text)
    return len(encoded_text)


def cut_text_by_token(text: str, max_tokens: int, model: str = "gpt-4o-mini"):
    """Cut text by token num."""
    try:
        encoding = tiktoken.encoding_for_model(model)
        encoded_text = encoding.encode(text)
        cut_text = encoding.decode(encoded_text[:max_tokens])
    except Exception as e:
        logger.error(e)
        cut_text = text[: CUT_WORD_LENGTH * max_tokens]
    return cut_text


# 图片转base64函数
def encode_image(image_path: Path) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")
