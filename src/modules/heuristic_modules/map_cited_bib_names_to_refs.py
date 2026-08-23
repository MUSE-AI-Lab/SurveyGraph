import re
from pathlib import Path

from src.configs.utils import load_latest_task_id
from src.configs.constants import OUTPUT_DIR
from src.configs.logger import get_logger
from src.modules.utils import save_result, load_file_as_string
from src.modules.latex_handler.utils import fuzzy_match

logger = get_logger("src.modules.heuristic_modules.BibNameReplacer")


class BibNameReplacer(object):
    def __init__(self, task_id: str = None):
        self.ref_bibs = None
        self.task_id = task_id

        # ======== settings ========
        self.pattern_of_bib_name_in_paper = r"\\cite[t|p]*\{(.*?)\}"
        self.pattern_of_bib_name_in_references = (
            r"@[\w\-]+\{([^,]+),"  # 匹配 @xxx{ 后面的内容直到第一个逗号
        )
        self.ref_file_path = Path(f"{OUTPUT_DIR}/{task_id}/latex/references.bib")

        self.collect_ref_bibs()

    def collect_ref_bibs(self):
        ref_content = load_file_as_string(path=self.ref_file_path)
        bib_names = re.findall(
            pattern=self.pattern_of_bib_name_in_references, string=ref_content
        )
        self.ref_bibs = bib_names

    def process(self, content: str):
        # 先收集新的缩写对
        bibs_in_content = re.findall(
            pattern=self.pattern_of_bib_name_in_paper, string=content
        )
        bibs_in_content = set(bibs_in_content)
        for bib_name_content in bibs_in_content:
            bib_names = [one.strip() for one in bib_name_content.split(",")]
            for bib_name in bib_names:
                closet_ref_bib_name = fuzzy_match(
                    text=bib_name, candidates=self.ref_bibs
                )[0]
                if closet_ref_bib_name != bib_name:
                    logger.error(
                        f"There is no {bib_name} in reference.bib; It has been replaced to {closet_ref_bib_name}"
                    )
                    content = content.replace(bib_name, closet_ref_bib_name)
        return content


# 示例使用
if __name__ == "__main__":
    task_id = load_latest_task_id()
    print(f"task_id: {task_id}")
    replacer = BibNameReplacer(task_id=task_id)
    content = """{
\begin{figure}[ht!]
\centering
            \subfloat[Memory Usage and Throughput of Existing Systems vs vLLM\cite{kwon2023efficiently}]{\includegraphics[width=0.28\textwidth]{figs/Memory Usage and Throughput of Existing Systems vs vLLM.jpg}}\hspace{0.03\textwidth}
            
            \subfloat[Architecture of a Distributed System\cite{kwon2023efficient}]{\includegraphics[width=0.28\textwidth]{figs/Architecture of a Distributed System.jpg}}\hspace{0.03\textwidth}
            
            \subfloat[Model Structure Overview\cite{pope2022efficiently}]{\includegraphics[width=0.28\textwidth]{figs/Model Structure Overview.jpg}}\hspace{0.03\textwidth}
            
\end{figure}
}
"""
    processed_text = replacer.process(content)
