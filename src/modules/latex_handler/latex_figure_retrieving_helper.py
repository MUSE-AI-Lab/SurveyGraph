import re
from pathlib import Path

from src.configs.utils import load_latest_task_id
from src.configs.logger import get_logger
from src.models.LLM import ChatAgent
from src.configs.config import ADVANCED_CHATAGENT_MODEL
from src.configs.constants import OUTPUT_DIR, RESOURCE_DIR
from src.modules.utils import load_prompt

logger = get_logger("src.modules.latex_handler.LatexFigureRetrievingHelper")


class LatexFigureRetrievingHelper(object):
    def __init__(self, task_dir: Path = None, chat_agent: ChatAgent = None, **kwargs):
        if chat_agent is None:
            self.chat_agent = ChatAgent()
        else:
            self.chat_agent = chat_agent

        if task_dir is None:
            task_id = load_latest_task_id()
            task_dir = Path(f"{OUTPUT_DIR}/{task_id}")

        # general
        self.task_dir = task_dir
        self.latex_directory = self.task_dir / "latex"
        self.refine_prompt_dir = Path(
            f"{RESOURCE_DIR}/LLM/prompts/fig_retrieve_refiner"
        )

        # latex
        self.global_label_idx = 0
        self.subfig_hspace = 0.03
        # Use [H] from float package to force figure placement at this exact position
        self.fig_latex_prefix = r"""
{
\begin{figure}[H]
\centering
"""

        self.fig_latex_suffix = r"""
\end{figure}
}
"""

    def get_fig_label(self):
        self.global_label_idx += 1
        return f"fig:retrieve_fig_{self.global_label_idx}"

    def get_fig_latex_parameters(self, num_of_figs: int):
        assert num_of_figs <= 3 and num_of_figs > 0
        if num_of_figs == 2:
            return [{"textwidth": 0.45}, {"textwidth": 0.45}]
        else:
            return [{"textwidth": 0.28}, {"textwidth": 0.28}, {"textwidth": 0.28}]

    def construct_fig_latex(
        self, sec_title: str, subsec_title: str, figure_list: list = []
    ):
        latex_code = ""
        latex_code += self.fig_latex_prefix

        fig_prompt_content = ""

        num_of_figs = len(figure_list)
        parameters = self.get_fig_latex_parameters(num_of_figs=num_of_figs)
        for fig, param in zip(figure_list, parameters):
            text_width = param["textwidth"]
            figure_title = fig["title"]
            image_path = str(Path(fig["image_path"]).relative_to(self.latex_directory))
            figure_desc = fig["desc"]
            bib_name = fig["bib_name"]
            sub_latex_code = f"""\\subfloat[{figure_title}\\cite{{{bib_name}}}]{{\\includegraphics[width={text_width}\\textwidth]{{{image_path}}}}}\\hspace{{{self.subfig_hspace}\\textwidth}}
"""
            latex_code += sub_latex_code

            fig_prompt_content += (
                f'- "{figure_title}": \n' + figure_desc.replace("\n", " ") + "\n\n"
            )

        # ---- create caption and label ----
        fig_label = self.get_fig_label()
        caption = f"Examples of {subsec_title}"
        additional_line = f"\caption{{{caption}}}\label{{{fig_label}}}"
        latex_code += additional_line
        latex_code += self.fig_latex_suffix
        return latex_code, fig_prompt_content, fig_label

    def get_example_data(self):
        figure_list = [
            {
                "figure_desc": "**Title: Human Name Processing Model**\n\n### Description:\n\nThe chart illustrates the processing of human names within a se...ng the human name process.\n\n12. **Relation (Yellow):**\n    - Represents the relationship between entities.\n    - Connected",
                "figure_link": "https://public-pdf-extract-kit.oss-cn-shanghai.aliyuncs.com/c0ea/c0eafee3-f013-4d6c-babb-dea8a30ecf65.png",
                "figure_size": [1882, 825],
                "rank_score": 0.43067196011543274,
            },
            {
                "figure_desc": "### Title: Comprehensive Overview of Neural Architecture Search (NAS) Techniques\n\n### Description:\n\nThe image provides a ...s and practitioners in the field of deep learning, providing a clear and structured overview of the various approaches to NAS.",
                "figure_link": "https://public-pdf-extract-kit.oss-cn-shanghai.aliyuncs.com/d740/d7409a92-c521-4014-abec-2293fa73569b.png",
                "figure_size": [2119, 951],
                "rank_score": 0.42766353487968445,
            },
            {
                "figure_desc": "### Title: Recurrent Neural Network (RNN) with Attention Mechanism\n\n### Description:\n\nThe image illustrates the architect...tion from past inputs and uses attention to selectively focus on relevant parts of the input sequence when generating outputs.",
                "figure_link": "https://public-pdf-extract-kit.oss-cn-shanghai.aliyuncs.com/5888/5888e931-0056-4c81-8532-19a07cb495e5.png",
                "figure_size": [1373, 1193],
                "rank_score": 0.4264509975910187,
            },
        ]

        return figure_list

    def clean_subsec_describe_content(self, content):
        # Define the regex pattern to match \cite{}, \citet{}, and \citep{} including their contents
        pattern = r"\\cite(?:t|p)?\{.*?\}"

        # Use re.sub() to replace all occurrences with an empty string
        cleaned_content = re.sub(pattern, "", content)

        return cleaned_content

    def generate_fig_description(
        self, sec_title: str, subsec_title: str, figure_list: list = []
    ):
        latex_code, fig_prompt_content, fig_label = self.construct_fig_latex(
            sec_title=sec_title, subsec_title=subsec_title, figure_list=figure_list
        )
        bib_names = [one["bib_name"] for one in figure_list]
        bib_names_string = ",".join(bib_names)
        subsec_describe_content_prompt = load_prompt(
            filename=str(
                self.refine_prompt_dir.joinpath(
                    "write_paragraphs_to_introduce_figs.md"
                ).absolute()
            ),
            topic=f"{sec_title}; {subsec_title}",
            latex_code=latex_code,
            fig_prompt_content=fig_prompt_content,
        )
        subsec_describe_content = f"As shown in \\autoref{{{fig_label}}}, {self.chat_agent.remote_chat(subsec_describe_content_prompt, model=ADVANCED_CHATAGENT_MODEL)}"
        subsec_describe_content += f" \cite({bib_names_string})"
        subsec_describe_content = self.clean_subsec_describe_content(
            subsec_describe_content
        )
        return subsec_describe_content, latex_code, fig_prompt_content

    def unit_test(self):
        pass


# python -m src.modules.latex_handler.latex_figure_builder
if __name__ == "__main__":
    helper = LatexFigureRetrievingHelper()
