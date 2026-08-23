import copy
import json
import os
import sys
from collections import Counter
from pathlib import Path

from matplotlib import pyplot as plt
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed
from tqdm import tqdm

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))  # run code in any path

from src.configs.config import ADVANCED_CHATAGENT_MODEL
from src.configs.constants import OUTPUT_DIR
from src.configs.logger import get_logger
from src.configs.utils import load_latest_task_id
from src.models.LLM import ChatAgent
from src.models.LLM.utils import load_prompt
from src.models.monitor.time_monitor import TimeMonitor
from src.models.monitor.token_monitor import TokenMonitor
from src.modules.utils import clean_chat_agent_format, load_papers
from src.schemas.base import Base
from src.schemas.outlines import Outlines, SingleOutline

logger = get_logger("src.modules.generator.OutlinesGenerator")


class OutlinesGenerator(Base):
    def __init__(self, task_id: str):
        super().__init__(task_id)
        self.paper_path = Path(f"{BASE_DIR}/outputs/{task_id}/papers")
        self.outlines_save_path = Path(f"{BASE_DIR}/outputs/{task_id}/outlines.json")
        self.mekg_outline_path = Path(f"{BASE_DIR}/outputs/{task_id}/outline.json")  # MEKG outline

        self.papers = self.load_papers(self.paper_path)
        self.mekg_outline = self._load_mekg_outline()
    
    def _load_mekg_outline(self) -> str:
        """Load MEKG outline as reference if available."""
        if self.mekg_outline_path.exists():
            try:
                with open(self.mekg_outline_path, 'r', encoding='utf-8') as f:
                    mekg_data = json.load(f)
                
                # Format MEKG outline as reference text
                lines = [f"**MEKG Outline Reference (from knowledge graph analysis):**\n"]
                lines.append(f"Title: {mekg_data.get('title', 'N/A')}\n")
                
                for section in mekg_data.get('sections', []):
                    lines.append(f"\n{section.get('number', '')}. {section.get('title', '')}")
                    if section.get('description'):
                        lines.append(f"   Description: {section.get('description', '')[:200]}...")
                    
                    for sub in section.get('subsections', []):
                        lines.append(f"   {sub.get('number', '')}. {sub.get('title', '')}")
                        
                        for subsub in sub.get('subsections', []):
                            lines.append(f"      {subsub.get('number', '')}. {subsub.get('title', '')}")
                
                logger.info(f"Loaded MEKG outline from {self.mekg_outline_path}")
                return "\n".join(lines)
            except Exception as e:
                logger.warning(f"Failed to load MEKG outline: {e}")
                return "No MEKG outline available."
        else:
            logger.info("No MEKG outline found, proceeding without reference.")
            return "No MEKG outline available."

    def load_papers(self, paper_dir: Path) -> list[dict]:
        """Concatenate all the attri trees."""
        papers = load_papers(paper_dir_path_or_papers=paper_dir)
        return papers

    def provide_relevant_paper_infos(self, papers: list, paper_limit: int = 60):
        paper_list = []
        for paper in tqdm(papers[:paper_limit], "provide_relevant_paper_infos"):
            paper_list.append(
                f"Title: {paper['title']}; Abstract: {paper['abstract']}."
            )
        return json.dumps(paper_list, indent=4)

    def extract_json_body(self, content: str):
        stack = []
        start = None

        for i, char in enumerate(content):
            if char == "{":
                if not stack:
                    start = i
                stack.append(char)
            elif char == "}":
                if stack:
                    stack.pop()
                    if not stack:
                        return json.loads(content[start : i + 1])
        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(json.JSONDecodeError),
    )
    def gen_outline_sections(self, chat_agent: ChatAgent) -> dict:
        """Get outlines from gpt using prompt;
        Extract answer from the response.
        """
        prompt = load_prompt(
            f"{BASE_DIR}/resources/LLM/prompts/outline_generator/write_primary_outline.md",
            paper_list=self.provide_relevant_paper_infos(self.papers),
            keyword=self.key_words,
            topic=self.topic,
            mekg_outline_reference=self.mekg_outline,  # Add MEKG reference
        )
        res = chat_agent.remote_chat(
            prompt, model=ADVANCED_CHATAGENT_MODEL, temperature=0.3
        )
        res = clean_chat_agent_format(content=res)
        try:
            dic = self.extract_json_body(content=res)
        except json.JSONDecodeError as e:
            logger.error(f"json load failed.{e}")
            logger.error(f"Response from gpt: {res}")
            raise json.JSONDecodeError(f"JSON decode failed: {e}")

        return dic

    def _check_response(self, res: str) -> bool:
        try:
            res = clean_chat_agent_format(content=res)
            dic = json.loads(res)
            return all(
                "section number" in mount and "information" in mount for mount in dic
            )
        except (json.JSONDecodeError, AssertionError) as e:
            logger.debug(f"Invalid mount response: {e} - {res}")
            return False

    def draw_mount_details(self, mount_l: list[list[dict]], fig_save_path: Path):
        section_counter = Counter()
        for mount in mount_l:
            sec_num = [x["section number"] for x in mount]
            section_counter.update(sec_num)
        section_counter = dict(sorted(section_counter.items()))
        plt.bar(section_counter.keys(), section_counter.values())
        for i, count in enumerate(section_counter.values()):
            plt.text(i, count + 0.1, str(count), ha="center", va="bottom", fontsize=10)
        plt.title("Mount on primary outline")
        logger.info(f"Mount details for primary outline saved in {str(fig_save_path)}")
        os.makedirs(fig_save_path.parent, exist_ok=True)
        plt.savefig(fig_save_path)

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_fixed(1),
    )
    def _write_secondary_outline(
        self, prompt: str, chat_agent: ChatAgent
    ) -> SingleOutline:
        res = chat_agent.remote_chat(prompt, model=ADVANCED_CHATAGENT_MODEL)
        try:
            res = clean_chat_agent_format(content=res)
            res_dic = json.loads(res)
            secondary_outline = SingleOutline.construct_primary_outline_from_dict(
                res_dic
            )
            return secondary_outline
        except Exception as e:
            logger.error(f"Error occurs when writing secondary outline. {e}")
            logger.error(f"The response is {res}")
            raise e
        
    def run(self):
        chat = ChatAgent(TokenMonitor(self.task_id, "generate outline"))
        time_monitor = TimeMonitor(self.task_id)
        time_monitor.start("generate outline")

        # ________ 1. Generate plain outline. ____________
        plain_outline_dic = self.gen_outline_sections(chat_agent=chat)
        for i, section in enumerate(plain_outline_dic["sections"]):
            plain_outline_dic["sections"][i]["subsections"] = []

        plain_outline = Outlines.from_dict(plain_outline_dic)
        logger.debug(f"generate plain outline: \n{str(plain_outline)}")

        # ________ 2. Mount papers on outline. ________________________
        papers = self.load_papers(self.paper_path)
        prompts = []
        for paper in papers:
            attri = json.dumps(paper["attri"], indent=4)
            prompt = load_prompt(
                f"{BASE_DIR}/resources/LLM/prompts/outline_generator/mout_paper_on_plain_outline.md",
                outlines=plain_outline,
                paper=attri,
            )
            prompts.append(prompt)

        cnt = 0
        mount_l = []
        while len(prompts) and cnt < 3:
            batch_res = chat.batch_remote_chat(
                prompts, desc="Mounting papers on primary outline..."
            )

            prompts_tmp = []
            for i, res in enumerate(batch_res):
                if self._check_response(res):
                    res = clean_chat_agent_format(content=res)
                    mount_l.append(json.loads(res))
                else:
                    prompts_tmp.append(prompts[i])

            prompts = prompts_tmp
            cnt += 1

        mount_fig_save_path = Path(
            f"{OUTPUT_DIR}/{self.task_id}/tmp/mount_details_outline.jpg"
        )
        if not mount_fig_save_path.parent.exists():
            mount_fig_save_path.parent.mkdir(exist_ok=True, parents=True)
        self.draw_mount_details(mount_l, mount_fig_save_path)

        # ________ 3. generate secondary outline. ___________________________
        secondary_outline = copy.deepcopy(plain_outline)
        clue_record = {}
        for mount in mount_l:
            for dic in mount:
                sec_num = dic["section number"]
                clue = dic["information"]
                clue_record.setdefault(sec_num, []).append(clue)

        for i, section in tqdm(
            enumerate(plain_outline.sections[:-1]),
            total=len(plain_outline.sections[:-1]),
            desc="writing secondary outlines",
        ):
            papers = "\n".join(clue_record.get(str(i + 1), []))
            prompt = load_prompt(
                f"{BASE_DIR}/resources/LLM/prompts/outline_generator/write_secondary_outline.md",
                keyword=self.key_words,
                topic=self.topic,
                primary_outlines=str(plain_outline),
                outline_title=section.title,
                outline_desc=section.desc,
                paper=papers,
            )
            secondary_outline.sections[i] = self._write_secondary_outline(prompt, chat)

        # __________ 4. Deduplicate the subsections ___________
        subsections = []
        for section in secondary_outline.sections:
            for subsection in section.sub:
                subsections.append(str(subsection.title))
        subsections = "\n".join(subsections)
        deduplicate_prompt = load_prompt(
            Path(BASE_DIR)
            / "resources"
            / "LLM"
            / "prompts"
            / "outline_generator"
            / "deduplicate_subsection.md",
            secondary_outlines=subsections,
        )
        logger.debug(f"deduplicating subsections...")
        deduplicated_outlines = chat.remote_chat(
            deduplicate_prompt, model=ADVANCED_CHATAGENT_MODEL
        )

        # __________ 5. Reorganize outlines ___________
        reorganize_prompt = load_prompt(
            Path(BASE_DIR)
            / "resources"
            / "LLM"
            / "prompts"
            / "outline_generator"
            / "reorganize_outline.md",
            primary_outlines=str(plain_outline),
            secondary_outlines=deduplicated_outlines,
            mekg_outline_reference=self.mekg_outline,  # Add MEKG reference
        )
        logger.debug(f"reorganizing outlines...")
        reorganized_outlines = chat.remote_chat(
            reorganize_prompt, model=ADVANCED_CHATAGENT_MODEL
        )
        reorganized_outlines = clean_chat_agent_format(content=reorganized_outlines)
        final_outlines = Outlines.from_dict(dic=json.loads(reorganized_outlines))
        final_outlines.save_to_file(self.outlines_save_path)

        time_monitor.end("generate outline")


# python -m src.models.generator.outlines_generator
if __name__ == "__main__":
    # task_id = "2024-12-02-1637_contr"
    task_id = load_latest_task_id()
    og = OutlinesGenerator(task_id=task_id)
    for i in range(4, 10):
        og.outlines_save_path = Path(f"{BASE_DIR}/outputs/{task_id}/outlines_{i}.json")
        og.run()
