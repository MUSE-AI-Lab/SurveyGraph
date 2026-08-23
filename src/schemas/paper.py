from __future__ import annotations
import os
import json
from dataclasses import dataclass, asdict
from typing import Literal, TypedDict

from src.modules.utils import save_result


class PaperDict(TypedDict):
    title: str = ""
    abstract: str = ""
    md_text: str = ""


@dataclass
class Paper:
    title: str = ""
    abstract: str = ""
    md_text: str = ""
    paper_type: Literal["method", "theory", "benchmark", "survey"] = ""
    attri: dict | None = None
    bib_name: str = ""
    mount_outline: list | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: str):
        save_result(json.dumps(self.to_dict(), indent=4), path)

    @staticmethod
    def from_json(path: str) -> Paper:
        dic = json.load(open(path, "r", encoding="utf-8"))
        # Relaxed assertion to allow missing fields (which will use defaults)
        # assert {
        #     "title",
        #     "abstract",
        #     "md_text",
        #     "paper_type",
        #     "attri",
        #     "mount_outline",
        # }.issubset(dic)
        return Paper(
            **{k: v for k, v in dic.items() if k in Paper.__dataclass_fields__}
        )

    @staticmethod
    def from_dir(dir_path: str) -> list[Paper]:
        papers = []
        for file in os.listdir(dir_path):
            file_path = os.path.join(dir_path, file)
            # 只处理 .json 文件，跳过目录和其他文件
            if not file.endswith('.json') or os.path.isdir(file_path):
                continue
            try:
                papers.append(Paper.from_json(file_path))
            except Exception as e:
                # 跳过无法解析的文件，记录警告
                import logging
                logging.getLogger(__name__).warning(f"Skipping invalid paper file {file_path}: {e}")
                continue
        return papers
