import json
from pathlib import Path
import re

from src.configs.logger import get_logger
from src.modules.utils import load_file_as_string, save_result
import os

logger = get_logger("Outlines")


class SingleOutline:
    def __init__(self, title: str, desc: str, sub: list = []) -> None:
        """Construct single outline

        Args:
            title (str): the title of this outline
            desc (str): the description, also what to write in this outline
            sub (list): point to the subsections (can be nested for 3-level structure)
        """
        self.title: str = title
        self.desc: str = desc
        self.sub: list[SingleOutline] = sub if sub else []

    @staticmethod
    def construct_tertiary_outline_from_dict(dic: dict) -> "SingleOutline":
        """construct a tertiary outline (subsubsection, level 3)

        Args:
            dic (dict): a dict which contains the keys "subsubsection title" and "description"
        """
        return SingleOutline(dic["subsubsection title"], dic["description"], [])

    @staticmethod
    def construct_secondary_outline_from_dict(dic: dict) -> "SingleOutline":
        """construct a secondary outline (subsection, level 2)

        Args:
            dic (dict): a dict which contains the keys "subsection title", "description"
                       and optionally "subsubsections" for 3-level structure
        """
        dic.setdefault("subsubsections", [])
        sub = [
            SingleOutline.construct_tertiary_outline_from_dict(x)
            for x in dic["subsubsections"]
        ]
        return SingleOutline(dic["subsection title"], dic["description"], sub)

    @staticmethod
    def construct_primary_outline_from_dict(dic: dict) -> "SingleOutline":
        """constrcut a primary outline (section, level 1), which contains several secondary outlines

        Args:
            dic (dict): a dict which contains the key "section title", "description" and "subsections"
        """
        dic.setdefault("subsections", [])
        sub = [
            SingleOutline.construct_secondary_outline_from_dict(x)
            for x in dic["subsections"]
        ]
        return SingleOutline(dic["section title"], dic["description"], sub)

    def __str__(self):
        return "\n".join([self.title, self.desc])
    
    def to_dict(self) -> dict:
        """Convert SingleOutline to dictionary representation.
        
        Returns:
            dict: Dictionary with title, description, and nested sub-outlines
        """
        result = {
            "title": self.title,
            "description": self.desc,
        }
        if self.sub:
            result["sub"] = [sub_outline.to_dict() for sub_outline in self.sub]
        return result
    
    def has_subsubsections(self) -> bool:
        """Check if this outline has any subsubsections (3-level structure)"""
        return any(len(subsec.sub) > 0 for subsec in self.sub)


class Outlines:
    """The outline architecture of the survey."""

    def __init__(self, title: str, sections: list[SingleOutline]) -> None:
        """Construct the Outlines."""
        self.title: str = title
        self.sections: list[SingleOutline] = sections

    @staticmethod
    def from_saved(file_path: str) -> "Outlines":
        """load from saved json files, that always is a dict, containing "title" and "sections" keys."""
        dic = json.loads(load_file_as_string(file_path))
        title = dic["title"]
        sections = []
        for sec in dic["sections"]:
            sections.append(SingleOutline.construct_primary_outline_from_dict(sec))
        logger.debug("construct outlines from saved path: {}".format(file_path))
        return Outlines(title, sections)

    @staticmethod
    def from_dict(dic: dict):
        """Construct from a dict.

        Args:
            dic (dict): a dict contains "title" and "sections" keys.

        Returns:
            Outlines
        """
        title = dic["title"]
        sections = []
        for sec in dic["sections"]:
            sections.append(SingleOutline.construct_primary_outline_from_dict(sec))
        return Outlines(title, sections)

    def save_to_file(self, file_path: Path):
        """Save the Outlines instance to a JSON file."""
        dic = self.to_dict()  # Convert the Outlines instance to a dictionary
        save_result(json.dumps(dic, indent=4), file_path)
        logger.debug(f"Outlines saved to {file_path}")

    def to_dict(self) -> dict:
        """Return as dict with support for 3-level structure."""

        dic = {"title": self.title, "sections": []}
        for section in self.sections:
            section_dict = {
                "section title": section.title,
                "description": section.desc,
                "subsections": [],
            }
            for subsection in section.sub:
                subsection_dict = {
                    "subsection title": subsection.title,
                    "description": subsection.desc,
                }
                # Add subsubsections if present (3-level structure)
                if subsection.sub:
                    subsection_dict["subsubsections"] = [
                        {
                            "subsubsection title": subsubsec.title,
                            "description": subsubsec.desc,
                        }
                        for subsubsec in subsection.sub
                    ]
                section_dict["subsections"].append(subsection_dict)
            dic["sections"].append(section_dict)
        return dic

    def __str__(self) -> str:
        """print the Outlines with support for 3-level structure

        Returns:
            str: print each section, subsection and subsubsection info
        """
        res = [self.title]
        for i, sec in enumerate(self.sections):
            res.append(f"{i + 1}. " + sec.__str__())
            for j, subsec in enumerate(sec.sub):
                res.append(f"{i + 1}.{j + 1} " + subsec.__str__())
                # Add subsubsections (3-level structure)
                for k, subsubsec in enumerate(subsec.sub):
                    res.append(f"{i + 1}.{j + 1}.{k + 1} " + subsubsec.__str__())
        return "\n".join(res)

    def serial_no_to_single_outline(self, serial_no_raw: str) -> SingleOutline | None:
        """Given a serial no in a survey, map to the single outline.
        Supports 3-level structure like "1.1.1", "2.1.3" etc.

        Args:
            serial_no (str): shaped like "1.1.1", "1.1", "2.1" or "5"

        Returns:
            SingleOutline: corresponding single outline, or None if not found.
        """
        if not serial_no_raw:
            logger.warning(f"Empty serial_no_raw provided")
            return None
            
        serial_no = None
        try:
            if "." in serial_no_raw:
                # Try to match 3-level pattern first (e.g., "1.2.3")
                match_3level = re.search(r"\d+\.\d+\.\d+", serial_no_raw)
                if match_3level:
                    serial_no = match_3level.group(0)
                    parts = serial_no.split(".")
                    primary_idx = int(parts[0]) - 1
                    secondary_idx = int(parts[1]) - 1
                    tertiary_idx = int(parts[2]) - 1
                    
                    if primary_idx < len(self.sections):
                        section = self.sections[primary_idx]
                        if secondary_idx < len(section.sub):
                            subsection = section.sub[secondary_idx]
                            if tertiary_idx < len(subsection.sub):
                                return subsection.sub[tertiary_idx]
                    return None
                
                # Try to match 2-level pattern (e.g., "1.2")
                match = re.search(r"\d+\.\d*", serial_no_raw)
                if not match:
                    logger.warning(f"No valid section number pattern found in: {serial_no_raw}")
                    return None
                serial_no = match.group(0)
                primary_section_index = int(serial_no.split(".")[0])
                secondary_section_index = serial_no.split(".")[1]
                if secondary_section_index != "":
                    secondary_section_index = int(secondary_section_index)
                    if primary_section_index - 1 < len(self.sections):
                        section = self.sections[primary_section_index - 1]
                        if secondary_section_index - 1 < len(section.sub):
                            return section.sub[secondary_section_index - 1]
                    return None
                else:
                    if primary_section_index - 1 < len(self.sections):
                        return self.sections[primary_section_index - 1]
                    return None
            else:
                match = re.search(r"\d+", serial_no_raw)
                if not match:
                    logger.warning(f"No valid section number found in: {serial_no_raw}")
                    return None
                serial_no = match.group(0)
                primary_section_index = int(serial_no)
                if primary_section_index - 1 < len(self.sections):
                    return self.sections[primary_section_index - 1]
                return None
        except Exception as e:
            logger.error(
                f"Error occurs: {e}, the serial_no_raw is {serial_no_raw}, the serial_no is {serial_no}"
            )
            return None
    
    def has_three_level_structure(self) -> bool:
        """Check if this outline has any 3-level structure (subsubsections)"""
        for section in self.sections:
            for subsection in section.sub:
                if subsection.sub:
                    return True
        return False
    
    def get_all_outlines_flat(self) -> list[tuple[str, SingleOutline]]:
        """Get all outlines in a flat list with their serial numbers.
        
        Returns:
            list of tuples: [(serial_no, SingleOutline), ...]
        """
        result = []
        for i, sec in enumerate(self.sections):
            result.append((f"{i + 1}", sec))
            for j, subsec in enumerate(sec.sub):
                result.append((f"{i + 1}.{j + 1}", subsec))
                for k, subsubsec in enumerate(subsec.sub):
                    result.append((f"{i + 1}.{j + 1}.{k + 1}", subsubsec))
        return result


def unitest():
    p = os.path.join("outputs", "2025-01-10-1935_recom", "outlines.json")
    outlines = Outlines.from_saved(p)
    # print(outlines)
    print(outlines.serial_no_to_single_outline("3"))


# python -m src.schemas.outlines
if __name__ == "__main__":
    unitest()
