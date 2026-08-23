import sys
from pathlib import Path

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.configs.config import COARSE_GRAINED_TOPK
from src.configs.constants import OUTPUT_DIR
from src.configs.logger import get_logger
from src.models.LLM import ChatAgent
from src.models.monitor.time_monitor import TimeMonitor
from src.models.monitor.token_monitor import TokenMonitor
from src.modules.preprocessor.data_cleaner import DataCleaner
from src.modules.preprocessor.paper_filter import PaperFilter
from src.modules.preprocessor.paper_recaller import PaperRecaller
from src.modules.preprocessor.utils import (
    ArgsNamespace,
    create_tmp_config,
    parse_arguments_for_preprocessor,
    save_papers,
)

logger = get_logger("preprocessing.preprocessor")


def single_preprocessing(args: ArgsNamespace) -> str:
    chat = ChatAgent()
    tmp_config = create_tmp_config(args.title, args.key_words)

    topic = tmp_config["topic"]
    task_id = tmp_config["task_id"]

    chat.token_monitor = TokenMonitor(task_id, "recall paper")

    time_monitor = TimeMonitor(task_id=task_id)
    time_monitor.start("retrieve paper")

    # 1. recall paper.
    recaller = PaperRecaller(
        topic=topic, enable_cache=args.enable_cache, chat_agent=chat
    )
    recalled_papers = recaller.recall_papers_iterative(
        tmp_config["key_words"], args.page, args.time_s, args.time_e
    )
    logger.info(
        f"================= totally {len(recalled_papers)} papers have been recalled =================="
    )
    time_monitor.end("retrieve paper")

    # 2. filter paper
    time_monitor.start("filter paper")
    chat.token_monitor = TokenMonitor(task_id, "filter paper")
    pf = PaperFilter(papers=recalled_papers, chat_agent=chat)
    filtered_papers = pf.run(topic=topic, coarse_grained_topk=COARSE_GRAINED_TOPK)
    logger.info(
        f"================= totally {len(filtered_papers)} papers have been saved after filtered =================="
    )
    save_papers(filtered_papers, Path(f"{OUTPUT_DIR}/{str(task_id)}/jsons"))
    time_monitor.end("filter paper")

    # 3. clean paper.
    chat.token_monitor = TokenMonitor(task_id, "clean paper")
    dc = DataCleaner()
    dc.run(task_id=task_id, chat_agent=chat)

    return task_id


if __name__ == "__main__":
    args = parse_arguments_for_preprocessor()
    single_preprocessing(args=args, chat_agent=ChatAgent())
