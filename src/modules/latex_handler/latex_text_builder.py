import os
from pathlib import Path
from typing import Union

from src.configs.config import BASE_DIR, SURVEY_AUTHOR_URL, SURVEY_AUTHOR_TEXT
from src.schemas.outlines import Outlines
from src.modules.utils import save_result, load_file_as_string
from src.configs.logger import get_logger

logger = get_logger("src.modules.latex_handler.LatexTextBuilder")


class LatexTextBuilder:
    def __init__(self, init_tex_path: str):
        self.tex = load_file_as_string(init_tex_path)

    def escape_latex(self, string):
        # Define LaTeX special characters and their escape sequences
        replacements = {
            "\\": "\\textbackslash{}",
            "{": "\\{",
            "}": "\\}",
            "%": "\\%",
            "#": "\\#",
            "$": "\\$",
            "_": "\\_",
            "&": "\\&",
            "^": "\\textasciicircum{}",
            "~": "\\textasciitilde{}",
            "<": "\\textless{}",
            ">": "\\textgreater{}",
        }
        # Replace each special character with its LaTeX escape sequence
        for original, escape in replacements.items():
            string = string.replace(original, escape)
        return string

    def make_title(self, title: str, author="author"):
        """
        \title{}, \author{}, \begin{document}, \maketitle{}
        """
        # 还是会有warning
        # title = self.escape_latex(title)
        # author = self.escape_latex(author)
        self.tex += f"""\n\\title{{{title}}}\n\\author{{{author}}}\n\
        
\\begin{{document}}\n\\maketitle\n"""

    def make_abstract(self, abstract: str):
        """
        \begin{abstract}, ..., \end{abstract}
        """
        self.tex += f"\n \n{abstract}\n"

    def make_content(self, mainbody):
        self.tex += "\n" + mainbody

    def make_reference(self):
        self.tex += """\\newpage
    
    

\\bibliography{references}
\\bibliographystyle{unsrtnat}

\\vfill"""

    def make_disclaimer(self):
        self.tex += """\\newpage
\\textbf{Disclaimer:}

SurveyX is an AI-powered system designed to automate the generation of surveys. While it aims to produce high-quality, coherent, and comprehensive surveys with accurate citations, the final output is derived from the AI's synthesis of pre-processed materials, which may contain limitations or inaccuracies. As such, the generated content should not be used for academic publication or formal submissions and must be independently reviewed and verified. The developers of SurveyX do not assume responsibility for any errors or consequences arising from the use of the generated surveys.
"""

    def run(
        self,
        outlines_path: Union[str, Path],
        abstract_path: Union[str, Path],
        main_body_path: Union[str, Path],
        latex_save_path: Union[str, Path],
    ):
        """Conver mainbody to a standard latex paper format."""

        outlines = Outlines.from_saved(outlines_path)
        # Generate clickable hyperlink for author
        # Format: \href{URL}{\textcolor{blue}{\underline{display_text}}}
        author_hyperlink = rf"\href{{{SURVEY_AUTHOR_URL}}}{{\textcolor{{blue}}{{\underline{{{SURVEY_AUTHOR_TEXT}}}}}}}"
        self.make_title(
            outlines.title,
            author=author_hyperlink
        )

        abstract = load_file_as_string(abstract_path)
        self.make_abstract(abstract)

        mainbody = load_file_as_string(main_body_path)
        self.make_content(mainbody)

        self.make_reference()

        # self.make_disclaimer()

        self.tex += "\n \\end{document} \n"
        save_result(self.tex, latex_save_path)

        return self.tex


def main():
    task_id = "xxx"

    ltb = LatexTextBuilder(init_tex_path=f"{BASE_DIR}/resources/latex/survey.ini.tex")
    outlines_path = os.path.join("outputs", str(task_id), "outlines.json")
    abstract_path = os.path.join("outputs", str(task_id), "tmp", "abstract.tex")
    main_body_path = os.path.join("outputs", str(task_id), "tmp", "mainbody.tex")
    latex_save_path = os.path.join("outputs", str(task_id), "latex", "survey.tex")

    ltb.run(
        outlines_path=outlines_path,
        abstract_path=abstract_path,
        main_body_path=main_body_path,
        latex_save_path=latex_save_path,
    )


# python -m src.modules.latex_handler.latex_text_builder
if __name__ == "__main__":
    main()
