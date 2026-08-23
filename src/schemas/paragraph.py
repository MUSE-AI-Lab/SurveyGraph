from pathlib import Path
import re

from src.configs.config import BASE_DIR
from src.modules.utils import load_file_as_string, save_result


class Paragraph:
    def __init__(
        self, title: str = "", content: str = "", sub: list = [], no: str = ""
    ):
        self.title = title
        self.content = content
        self.sub: list[Paragraph] = sub
        self.no = no

    @staticmethod
    def from_subsubsection(subsubsection: str, no):
        """
        format:
        \subsubsection{xxx} xxx
        xxx ...
        """
        extract_braced_content = lambda s: (
            m.group(1) if (m := re.search(r"\{(.*?)\}", s)) else None
        )
        title = extract_braced_content(subsubsection.splitlines()[0])
        return Paragraph(title, subsubsection, [], no)

    @staticmethod
    def from_subsection(subsection: str, no):
        """
        format:
        \subsection{xxx} xxx
        \subsubsection{xxx} xxx (optional)
        xxx ...
        """
        extract_braced_content = lambda s: (
            m.group(1) if (m := re.search(r"\{(.*?)\}", s)) else None
        )
        title = extract_braced_content(subsection.splitlines()[0])
        content = subsection
        sub = []
        
        # Check if there are subsubsections
        if r"\subsubsection" in subsection:
            for i, subsubsection in enumerate(subsection.split(r"\subsubsection")):
                if subsubsection.startswith(r"\subsection"):
                    # This is the subsection header part, skip it
                    continue
                subsubsection = r"\subsubsection" + subsubsection
                sub.append(Paragraph.from_subsubsection(subsubsection, i))
        
        return Paragraph(title, content, sub, no)

    @staticmethod
    def from_section(section: str, no):
        """
        given the section(1-level paragraph), format:
        \section{xxx} xxxx
        \subsection{xxx} xxx
        \subsection{xxx} xxx
        """
        title = ""
        content = section
        sub = []
        extract_braced_content = lambda s: (
            m.group(1) if (m := re.search(r"\{(.*?)\}", s)) else None
        )
        for i, subsection in enumerate(section.split(r"\subsection")):
            if subsection.startswith(r"\section"):
                title = extract_braced_content(subsection)
                continue
            subsection = r"\subsection" + subsection
            sub.append(Paragraph.from_subsection(subsection, i))
        return Paragraph(title, content, sub, no)

    @staticmethod
    def from_mainbody(mainbody: str) -> list["Paragraph"]:
        res = []
        sections = re.split(r"(?=\\section\{)", mainbody.strip())
        for i, section in enumerate(sections):
            if section.startswith("\\section"):
                res.append(Paragraph.from_section(section, i))
        return res

    @staticmethod
    def from_mainbody_path(mainbody_path: Path) -> list["Paragraph"]:
        mainbody = load_file_as_string(mainbody_path)
        res = Paragraph.from_mainbody(mainbody)
        return res

    @staticmethod
    def save_to_file(paragraph_l: list["Paragraph"], save_path: Path):
        text = "\n".join([paragraph.content for paragraph in paragraph_l])
        save_result(text, save_path)
