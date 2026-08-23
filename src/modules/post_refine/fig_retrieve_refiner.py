"""
@Reference:
1. How to create llama index templates: https://blog.csdn.net/lovechris00/article/details/137782020
"""

import json
import os
import re
from typing import List, Dict
from pathlib import Path
import traceback

from src.configs.constants import OUTPUT_DIR, RESOURCE_DIR
from src.configs.logger import get_logger
from src.configs.utils import load_latest_task_id
from src.models.monitor.token_monitor import TokenMonitor
from src.modules.utils import load_file_as_string, save_result, load_prompt
from src.schemas.paragraph import Paragraph
from src.modules.fig_retrieve.fig_retriever import FigRetriever
from src.modules.latex_handler import LatexFigureRetrievingHelper
from src.modules.post_refine import RagRefiner
from src.modules.post_refine.utils import are_key_words_contained, list_citation_names
from src.modules.utils import clean_chat_agent_format

logger = get_logger("src.modules.post_refine.FigRetrieveRefiner")


class FigRetrieveRefiner(RagRefiner):
    def __init__(self, task_id: str = None, **kwargs) -> None:
        if "llamaindex_topk" not in kwargs:
            kwargs["llamaindex_topk"] = 30
        super().__init__(task_id=task_id, **kwargs)
        self.refined_mainbody_path = Path(
            f"{OUTPUT_DIR}/{self.task_id}/tmp/mainbody_fig_retrieve_refined.tex"
        )
        self.refine_prompt_dir = Path(
            f"{RESOURCE_DIR}/LLM/prompts/fig_retrieve_refiner"
        )

        # ========= settings for retrieving ============
        self.fig_retriever = FigRetriever(is_debug=False)
        self.chat_agent.token_monitor = TokenMonitor(
            task_id, "Multimodal figure retrieve"
        )
        self.fig_latex_helper = LatexFigureRetrievingHelper(
            task_dir=self.task_dir, chat_agent=self.chat_agent
        )
        self.trigger_words_in_subsections = [
            "techniques",
            "visualization",
            "applications",
            "mechanisms",
            "methodologies",
            "frameworks",
            "architecture",
            "enhancements",
        ]
        # how many times the fig retrieving has been triggered
        self.trigger_count = 0
        self.trigger_limit = 2
        self.relevant_paper_limit = 30
        self.fig_retrieve_topk = self.relevant_paper_limit
        self.paper_retrieve_limit = 10
        self.max_figs_in_single_paper = 4
        self.rag_seg_topk = self.relevant_paper_limit + 10
        self.fig_used_for_generate_latex_limit = 3
        self.random_select_paper_limit = self.relevant_paper_limit
        self.fig_size_filter_scale = 1.5

        # ============ making latex ===============
        self.figs_dir = self.task_dir / "latex/figs"
        self.global_visited_fig_links = set()

        # openai agent
        self.chat_agent_parse_retries = 3

    def collect_papers_by_citation_names(
        self, papers: list = None, citation_list: list = []
    ):
        if papers is None:
            papers = self.papers
        filtered_papers = []
        for paper in papers:
            if are_key_words_contained(
                content=paper["bib_name"], key_words=citation_list
            ):
                # Keep only the desired attributes
                filtered_paper = {
                    "image": []
                    if paper.get("image") is None
                    else paper["image"][: self.max_figs_in_single_paper],
                    "bib_name": paper.get("bib_name"),
                    "scholar_id": paper.get("scholar_id"),
                    "detail_id": paper.get("detail_id"),
                    "title": paper.get("title"),
                    "from": paper.get("from"),
                }
                if len(filtered_paper["image"]) == 0:
                    logger.error(f'Paper "{paper["title"]}" has no images.')
                filtered_papers.append(filtered_paper)
        return filtered_papers

    def get_paper_id(self, paper: dict):
        if ("scholar_id" in paper) and paper["scholar_id"] is not None:
            return paper["scholar_id"]
        elif ("detail_id" in paper) and paper["detail_id"] is not None:
            return paper["detail_id"]
        else:
            raise ValueError()

    def collect_paper_image_items(self, papers: List[Dict]):
        image_urls = []
        paper_ids = []
        paper_sources = []

        image_paper_mappings = {}
        paper_count = 0
        for paper in papers:
            one_paper_images = paper["image"][: self.max_figs_in_single_paper]
            if len(one_paper_images) > 0:
                paper_count += 1
            image_urls.extend(one_paper_images)
            paper_ids.extend(
                [self.get_paper_id(paper) for _ in range(len(one_paper_images))]
            )
            paper_sources.extend([paper["from"] for _ in range(len(one_paper_images))])
            for one in one_paper_images:
                image_paper_mappings[one] = paper
        for i in range(len(paper_sources)):
            if paper_sources[i] == "google":
                paper_sources[i] = "google_scholar"
        return (image_urls, paper_ids, paper_sources), image_paper_mappings, paper_count

    def collect_papers_with_images(self, papers: list):
        new_paper_set = []
        for paper in papers:
            if (paper["image"] is None) or (len(paper["image"]) == 0):
                continue
            new_paper_set.append(paper)
        return new_paper_set

    def process_and_download_figs(self, figure_list: list, figs_dir: Path = None):
        # 有一些图片的信息不对，需要清洗一下
        prompt_l = []
        for i in range(len(figure_list)):
            origin_desc = figure_list[i]["figure_desc"]

            tile_desc_extraction_prompt = load_prompt(
                filename=str(
                    self.refine_prompt_dir.joinpath(
                        "generate_fig_title_desc.md"
                    ).absolute()
                ),
                origin_desc=origin_desc,
            )
            prompt_l.append(tile_desc_extraction_prompt)
        res_l = self.chat_agent.batch_remote_chat(
            prompt_l=prompt_l, desc="tile_desc_extraction..."
        )

        figure_list_with_desc = []
        for i in range(len(figure_list)):
            content = res_l[i]
            content = clean_chat_agent_format(content=content)
            try:
                # clean json str if necessary
                content = json.loads(content)
                figure_list[i]["title"] = content["title"]
                figure_list[i]["desc"] = content["desc"]
                figure_list_with_desc.append(figure_list[i])
            except Exception as e:
                logger.error(f"Fail to parse figure {i}: {content}; Exception: {e}")

        # 去掉有问题的图片
        figure_list = figure_list_with_desc

        # 存储图片
        image_paths = self.fig_retriever.download_figs(
            figure_list=figure_list, figs_dir=figs_dir
        )
        for i in range(len(figure_list)):
            image_path = image_paths[i]
            figure_list[i]["image_path"] = image_path

        return figure_list

    def is_paper_fig_qualified(self, figure_link):
        fig_filter_prompt = load_prompt(
            filename=str(self.refine_prompt_dir.joinpath("filter_figs.md").absolute()),
        )
        res = self.chat_agent.remote_chat(
            text_content=fig_filter_prompt, image_urls=[figure_link]
        )
        try:
            match = re.search(r"\b(yes|no)\b", res, re.IGNORECASE)
            return match.group().lower() == "yes"
        except Exception as e:
            logger.error(f"check_if_paper_fig_qualified: {e}")

    def make_figs_for_latex(
        self, image_paper_mappings: dict, figure_list: list, fig_limit: int
    ):
        figure_list = figure_list[: fig_limit + 1]
        visited_papers = set()
        filtered_figure_list = []
        for one in figure_list:
            figure_link = one["figure_link"]
            paper = image_paper_mappings[figure_link]
            if paper["bib_name"] in visited_papers:
                continue
            if not self.is_paper_fig_qualified(figure_link=figure_link):
                continue
            if figure_link in self.global_visited_fig_links:
                continue
            one["bib_name"] = paper["bib_name"]
            filtered_figure_list.append(one)
            visited_papers.add(paper["bib_name"])
            self.global_visited_fig_links.add(figure_link)
        filtered_figure_list = filtered_figure_list[:fig_limit]
        return filtered_figure_list

    def filter_figs_by_fig_size(self, figure_list: list, scale=None):
        if len(figure_list) == 0:
            return figure_list
        if scale is None:
            scale = self.fig_size_filter_scale
        # 计算第一个图片的比例
        base_ratio = figure_list[0]["figure_size"][0] / figure_list[0]["figure_size"][1]

        # 筛选符合比例范围的图片
        filtered_list = [
            figure
            for figure in figure_list
            if base_ratio
            <= figure["figure_size"][0] * scale / figure["figure_size"][1]
            <= scale * base_ratio
        ]
        return filtered_list

    def refine_a_subsection(
        self, subsection: Paragraph, section_title: str, paper_retrieve_limit: int
    ):
        # ---- rag to retrieve relevant papers ---------
        logger.debug("retrieve relevant papers...")
        results = self.llamaindex_retriever.retrieve(subsection.title)[
            :paper_retrieve_limit
        ]
        logger.debug(f"filter_results_by_scores... the results size: {len(results)}")
        results = self.filter_results_by_scores(
            nodes=results, threshold=self.llamaindex_score_threshold
        )
        bib_list = list(set([one.metadata["bib_name"] for one in results]))[
            : self.relevant_paper_limit
        ]

        papers = self.collect_papers_with_images(papers=self.papers)
        selected_papers = self.collect_papers_by_citation_names(
            papers=papers, citation_list=bib_list
        )

        if len(selected_papers) == 0:
            logger.error(
                f"selected_papers is empty! we chose random papers up to {self.random_select_paper_limit} instead."
            )
            selected_papers = papers[: self.random_select_paper_limit]

        title = subsection.title
        (image_urls, paper_ids, paper_sources), image_paper_mappings, paper_count = (
            self.collect_paper_image_items(selected_papers)
        )
        if paper_count < self.fig_used_for_generate_latex_limit:
            logger.debug(
                f"Paper count {paper_count} is less than {self.relevant_paper_limit}; Refining is broken."
            )
            return None
        query_text = f"{title}"
        logger.debug(
            f"Retrieve images; number of images: {len(image_urls)}; Start to rerank these images..."
        )
        try:
            image_data = self.fig_retriever.wrap_data_2(
                query_text=query_text,
                figure_linkes=image_urls,
                paper_ids=paper_ids,
                sources=paper_sources,
                match_topk=self.fig_retrieve_topk,
            )
            figure_list = self.fig_retriever.retrieve_relevant_images(
                image_data_dict=image_data,
                request_url=self.fig_retriever.enhanced_fig_retrieve_url,
            )
            logger.debug(
                f"Retrieve images; number of images: {len(image_urls)}; Start to rerank these images..."
            )
            figure_list = self.filter_figs_by_fig_size(
                figure_list=figure_list, scale=self.fig_size_filter_scale
            )
            # only generate paragraphs for retrieved figs if at least have two figures
            figure_list = self.process_and_download_figs(
                figure_list=figure_list, figs_dir=self.figs_dir
            )
            figure_list = self.make_figs_for_latex(
                image_paper_mappings=image_paper_mappings,
                figure_list=figure_list,
                fig_limit=self.fig_used_for_generate_latex_limit,
            )
            if len(figure_list) <= 1:
                logger.debug(
                    f"Only retrieved {len(figure_list)} figs. Failed to insert retrieved figs in subsection {subsection.title}"
                )
                return None  # failed
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(f"An error occurred: {e}; The traceback: {tb_str}")
            return None

        subsec_describe_content, latex_code, _ = (
            self.fig_latex_helper.generate_fig_description(
                sec_title=section_title,
                subsec_title=subsection.title,
                figure_list=figure_list,
            )
        )

        revised_content = (
            subsection.content + f"\n\n{latex_code}\n\n{subsec_describe_content}\n"
        )
        return revised_content

    def refine_a_section(self, section: Paragraph, sec_id: int):
        if self.trigger_count > self.trigger_limit:
            # directly return without refinement
            return section, 0
        success_count_total = 0
        revised_content = section.content
        for sub_sec_id, sub_sec in enumerate(section.sub):
            title = sub_sec.title
            if not are_key_words_contained(
                content=title, key_words=self.trigger_words_in_subsections
            ):
                continue
            # --- refine this subsection---
            # try:
            revised_subsection = self.refine_a_subsection(
                subsection=sub_sec,
                section_title=section.title,
                paper_retrieve_limit=self.paper_retrieve_limit,
            )
            # except Exception as e:
            #     logger.error(f"Fail to improve section with retrieved figs; Exception: {e}")
            #     revised_content = None
            if revised_subsection is None:
                continue
            success_count_total += 1
            revised_content = revised_content.replace(
                sub_sec.content, revised_subsection
            )
        return revised_content, success_count_total

    def run(self, mainbody_path=None):
        if mainbody_path is None:
            mainbody_path = self.mainbody_path
        survey_sections = self.load_survey_sections(mainbody_path)
        candidate_sec_ids = list(range(3, 6))  # section 3 to section 5
        refined_survey = []
        for section in survey_sections:
            # exclude the sections such as introduction, background, limitaitons, conclusion
            if int(section.no) not in candidate_sec_ids:
                refined_survey.append(section.content)
            else:
                refined_section, success_count = self.refine_a_section(
                    section=section, sec_id=section.no
                )
                refined_survey.append(refined_section)
                logger.info(
                    f"Insert {success_count} figs into subsections in section {section.no}"
                )
        refined_content = "\n".join(refined_survey)
        save_result(refined_content, self.refined_mainbody_path)
        logger.debug(f"Save content to {self.refined_mainbody_path}.")
        return refined_content


if __name__ == "__main__":
    task_id = load_latest_task_id()
    print(f"task_id: {task_id}")
    # store vector index into local directory for the convenience of debugging
    fig_retrieve_refiner = FigRetrieveRefiner(task_id=task_id)
    fig_retrieve_refiner.run()
