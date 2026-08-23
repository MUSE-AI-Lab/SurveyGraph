"""
@Reference:
1. How to create llama index templates: https://blog.csdn.net/lovechris00/article/details/137782020
"""

from pathlib import Path

from typing import List, Union, Dict

from src.configs.utils import load_latest_task_id
from src.configs.constants import OUTPUT_DIR
from src.configs.logger import get_logger
from src.models.monitor.token_monitor import TokenMonitor
from src.schemas.paragraph import Paragraph
from src.models.LLM import ChatAgent
from src.modules.utils import load_papers

logger = get_logger("src.modules.post_refine.BaseRefiner")


class BaseRefiner:
    def __init__(self, task_id: str = None, **kwargs) -> None:
        task_id = load_latest_task_id() if task_id is None else task_id
        assert task_id is not None
        self.task_id = task_id
        self.task_dir = Path(f"{OUTPUT_DIR}/{self.task_id}")
        self.paper_dir = self.task_dir / "papers"
        self.latex_tmp_dir = self.task_dir / "tmp"
        self.mainbody_path = self.latex_tmp_dir / "mainbody.tex"
        self.refined_mainbody_path = self.latex_tmp_dir / "mainbody_refined.tex"

        # refine settings
        if "papers" not in kwargs:
            self.papers = self.load_papers(self.paper_dir)
        else:
            self.papers = kwargs["papers"]

        # openai agent
        if "chat_agent" in kwargs:
            self.chat_agent = kwargs["chat_agent"]
        else:
            self.chat_agent = ChatAgent(TokenMonitor(task_id, "post refine"))

    def load_papers(
        self, paper_dir_path_or_papers: Union[Path, List[Dict]]
    ) -> list[dict]:
        return load_papers(paper_dir_path_or_papers=paper_dir_path_or_papers)

    def load_survey_sections(self, mainbody_path: Path) -> list[Paragraph]:
        paragraph_l = Paragraph.from_mainbody_path(mainbody_path)
        return paragraph_l


if __name__ == "__main__":
    # store vector index into local directory for the convenience of debugging
    rag_refiner = BaseRefiner()
