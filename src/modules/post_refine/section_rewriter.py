"""
@Reference:
1. How to create llama index templates: https://blog.csdn.net/lovechris00/article/details/137782020
"""

import re
from tqdm import tqdm
import traceback
from pathlib import Path

from src.configs.constants import OUTPUT_DIR, RESOURCE_DIR
from src.configs.config import ADVANCED_CHATAGENT_MODEL
from src.configs.logger import get_logger
from src.configs.utils import load_latest_task_id
from src.models.monitor.token_monitor import TokenMonitor
from src.modules.utils import save_result, load_prompt, clean_chat_agent_format
from src.modules.post_refine import BaseRefiner

# 导入压缩配置
try:
    from frontend.config import SectionRewriterConfig
except ImportError:
    # 如果无法导入，使用默认值
    class SectionRewriterConfig:
        MIN_COMPRESSION_RATIO = 0.50
        TARGET_COMPRESSION_RATIO = 0.70
        MAX_RETRY_ATTEMPTS = 2
        MAX_SECTION_WORDS = 15000

logger = get_logger("src.modules.post_refine.SectionRewriter")


class SectionRewriter(BaseRefiner):
    def __init__(self, task_id: str = None, **kwargs) -> None:
        super().__init__(task_id, **kwargs)
        self.refined_mainbody_path = Path(
            f"{OUTPUT_DIR}/{self.task_id}/tmp/mainbody_sec_rewritten.tex"
        )
        self.rewrite_prompt_dir = Path(f"{RESOURCE_DIR}/LLM/prompts/section_rewriter")

        self.maintain_commands = ["section", "subsection", "subsubsection", "label", "autoref"]
        self.chat_agent.token_monitor = TokenMonitor(task_id, "section rewrite")

    def extract_environment_content(self, content, command):
        """Extracts the content of LaTeX environment commands from a text."""
        pattern = re.compile(r"\\" + command + r"\{([^}]+)\}")
        res = pattern.findall(content)
        return res if res is not None else []

    def extract_fig_name(self, content):
        pattern = re.compile(r"\\includegraphics\[.*?\]\{figs/([^.]+)\.png\}")
        return pattern.findall(content)

    def replace_environment_contents(
        self, rewritten_text: str, original_text: str, commands: list[str]
    ):
        for command in commands:
            """Replaces the content of LaTeX environment commands in a text."""
            original_contents = self.extract_environment_content(
                content=original_text, command=command
            )
            current_contents = self.extract_environment_content(
                content=rewritten_text, command=command
            )
            
            # 去重处理：原始内容可能有重复（如 \subsection{Title}\label{Title}）
            # 使用有序去重，保持原始顺序
            original_unique = list(dict.fromkeys(original_contents))
            current_unique = list(dict.fromkeys(current_contents))
            
            if len(original_unique) != len(current_unique):
                # 如果去重后数量仍不匹配，记录警告但尝试继续处理
                logger.warning(
                    f"Command '{command}' count mismatch after dedup. "
                    f"original_unique: {original_unique}; current_unique: {current_unique}. "
                    f"Attempting partial restoration."
                )
                # 尝试恢复能匹配的部分
                for i, orig_content in enumerate(original_unique):
                    if i < len(current_unique) and current_unique[i] != orig_content:
                        # 替换重写文本中的内容为原始内容
                        rewritten_text = rewritten_text.replace(
                            f"\\{command}{{{current_unique[i]}}}",
                            f"\\{command}{{{orig_content}}}",
                        )
            else:
                # 数量匹配，正常替换
                for i, content in enumerate(current_unique):
                    if content != original_unique[i]:
                        rewritten_text = rewritten_text.replace(
                            f"\\{command}{{{content}}}",
                            f"\\{command}{{{original_unique[i]}}}",
                        )
        
        # 图片也要对应一下
        original_content = self.extract_fig_name(content=original_text)
        current_content = self.extract_fig_name(content=rewritten_text)
        if len(original_content) == len(current_content):
            for i, content in enumerate(current_content):
                if content != original_content[i]:
                    rewritten_text = rewritten_text.replace(content, original_content[i])
        elif len(current_content) > 0:
            logger.warning(
                f"Figure count mismatch. original: {original_content}; current: {current_content}"
            )
        return rewritten_text

    def extract_section_line(self, latex_text):
        # 使用正则表达式匹配\section部分
        match = re.search(r"\\section\{([^}]*)\}\s*\\label\{([^}]*)\}", latex_text)
        if match:
            section_title = match.group(0)  # 提取完整的\section那一行
            return section_title
        return None

    def rule_address_gpt_rewrite_issues(
        self, origin_sec_contents: list, new_sec_contents: list
    ):
        # gpt 有一个很奇怪的bug，会丢掉\section那一行，尝试用规则解决这个问题，或者把\section改成\subsection
        if len(origin_sec_contents) != len(new_sec_contents):
            logger.error(
                f"origin_sec_contents: {origin_sec_contents};\n new_sec_contents: {new_sec_contents}"
            )
        assert len(origin_sec_contents) == len(new_sec_contents)
        for idx in range(len(origin_sec_contents)):
            if ("\\section" in origin_sec_contents[idx]) and (
                "\\section" not in new_sec_contents[idx]
            ):
                origin_sec_head = origin_sec_contents[idx].strip()[:200]
                sec_line = self.extract_section_line(latex_text=origin_sec_head)
                if sec_line not in origin_sec_head:
                    raise ValueError(
                        f"sec_content is None, origin_sec_head: {origin_sec_head}"
                    )
                new_sec_contents[idx] = f"{sec_line}\n\n{new_sec_contents[idx]}"
                logger.debug(f'"{sec_line}" is inserted into original section')

                potential_subsec_line = sec_line.replace("\\section", "\\subsection")
                if potential_subsec_line in new_sec_contents[idx]:
                    logger.debug(
                        f"{potential_subsec_line} was added in rewritten section by mistake, which has been corrected"
                    )
                    new_sec_contents[idx] = new_sec_contents[idx].replace(
                        potential_subsec_line, ""
                    )

        # 保证不改变特定内容
        assert len(origin_sec_contents) == len(new_sec_contents)
        for idx in range(len(origin_sec_contents)):
            new_sec_contents[idx] = self.replace_environment_contents(
                rewritten_text=new_sec_contents[idx],
                original_text=origin_sec_contents[idx],
                commands=self.maintain_commands,
            )

    # 从配置文件加载压缩参数
    MIN_COMPRESSION_RATIO = SectionRewriterConfig.MIN_COMPRESSION_RATIO
    TARGET_COMPRESSION_RATIO = SectionRewriterConfig.TARGET_COMPRESSION_RATIO
    MAX_RETRY_ATTEMPTS = SectionRewriterConfig.MAX_RETRY_ATTEMPTS
    MAX_SECTION_WORDS = SectionRewriterConfig.MAX_SECTION_WORDS
    
    def _split_section_by_subsections(self, sec_content: str) -> list[str]:
        """将 section 按 subsection 分割成多个块"""
        # 使用正则表达式按 \subsection 分割
        pattern = r'(\\subsection\{[^}]+\})'
        parts = re.split(pattern, sec_content)
        
        if len(parts) <= 1:
            # 没有 subsection，返回原内容
            return [sec_content]
        
        # 重新组合：每个 subsection 标题和其内容组合在一起
        chunks = []
        current_chunk = parts[0]  # 第一部分（section 标题和开头内容）
        
        for i in range(1, len(parts), 2):
            if i + 1 < len(parts):
                subsection_header = parts[i]
                subsection_content = parts[i + 1] if i + 1 < len(parts) else ""
                subsection_full = subsection_header + subsection_content
                
                # 检查当前块加上新内容是否超过阈值
                combined_words = len((current_chunk + subsection_full).split())
                if combined_words > self.MAX_SECTION_WORDS and current_chunk.strip():
                    chunks.append(current_chunk)
                    current_chunk = subsection_full
                else:
                    current_chunk += subsection_full
            else:
                current_chunk += parts[i]
        
        if current_chunk.strip():
            chunks.append(current_chunk)
        
        return chunks if chunks else [sec_content]
    
    def _compress_single_section(self, sec_content: str, attempt: int = 1) -> str:
        """压缩单个章节，支持重试机制和分块处理"""
        word_count = len(sec_content.split())
        
        # 如果内容过长，进行分块处理
        if word_count > self.MAX_SECTION_WORDS:
            logger.info(f"Section has {word_count} words, exceeds {self.MAX_SECTION_WORDS}, splitting into chunks")
            chunks = self._split_section_by_subsections(sec_content)
            
            if len(chunks) > 1:
                logger.info(f"Split into {len(chunks)} chunks")
                compressed_chunks = []
                for i, chunk in enumerate(chunks):
                    logger.info(f"Compressing chunk {i+1}/{len(chunks)} ({len(chunk.split())} words)")
                    compressed_chunk = self._compress_single_chunk(chunk, attempt)
                    compressed_chunks.append(compressed_chunk)
                return "\n\n".join(compressed_chunks)
        
        return self._compress_single_chunk(sec_content, attempt)
    
    def _compress_single_chunk(self, sec_content: str, attempt: int = 1) -> str:
        """压缩单个内容块"""
        # 根据重试次数调整prompt
        if attempt == 1:
            prompt_file = "compress_sections.md"
        else:
            # 重试时使用更保守的压缩策略
            prompt_file = "compress_sections_conservative.md"
        
        prompt_path = self.rewrite_prompt_dir.joinpath(prompt_file)
        
        # 如果保守版本的prompt不存在，使用原始prompt但添加额外指导
        if not prompt_path.exists():
            sec_rewrite_prompt = load_prompt(
                filename=str(self.rewrite_prompt_dir.joinpath("compress_sections.md").absolute()),
                content=sec_content,
            )
            # 添加额外的保留内容指导
            if attempt > 1:
                sec_rewrite_prompt = sec_rewrite_prompt.replace(
                    "Now read the content above",
                    f"**IMPORTANT: Previous attempt removed too much content. This time, you MUST preserve at least {int(self.TARGET_COMPRESSION_RATIO * 100)}% of the original content. Only remove clearly redundant sentences.**\n\nNow read the content above"
                )
        else:
            sec_rewrite_prompt = load_prompt(
                filename=str(prompt_path.absolute()),
                content=sec_content,
            )
        
        result = self.chat_agent.remote_chat(
            sec_rewrite_prompt, model=ADVANCED_CHATAGENT_MODEL
        )
        return clean_chat_agent_format(content=result)
    
    def compress_sections(self, origin_sec_contents: list[str]) -> list[str]:
        """压缩章节内容，使用智能重试机制"""
        # make the paper content more compact (but not too much)
        sec_prompts = []
        origin_lengths = []
        for sec_content in origin_sec_contents:
            sec_rewrite_prompt = load_prompt(
                filename=str(
                    self.rewrite_prompt_dir.joinpath("compress_sections.md").absolute()
                ),
                content=sec_content,
            )
            origin_lengths.append(len(sec_content.strip().split()))
            sec_prompts.append(sec_rewrite_prompt)
        section_content_list = self.chat_agent.batch_remote_chat(
            prompt_l=sec_prompts, desc="compress sections..."
        )
        new_sec_contents = [
            clean_chat_agent_format(content=one) for one in section_content_list
        ]
        
        # 修复代码块中的异常空格
        for i in range(len(new_sec_contents)):
            # 修复类似 search_weather(city='Paris,            TX') 的问题
            # 匹配代码块中的内容，然后替换多余空格
            new_sec_contents[i] = re.sub(r"(\w+='[^']+,)\s{2,}([^']+')", r"\1 \2", new_sec_contents[i])
            # 修复texttt命令中的异常空格
            new_sec_contents[i] = re.sub(r"(\\texttt\{[^}]*),\s{2,}([^}]*\})", r"\1, \2", new_sec_contents[i])

        self.rule_address_gpt_rewrite_issues(
            origin_sec_contents=origin_sec_contents, new_sec_contents=new_sec_contents
        )

        # 检查压缩比例，如果压缩过度则尝试重新生成或使用原始内容
        current_lengths = [len(one.strip().split()) for one in new_sec_contents]
        for id_, (ori, cur) in enumerate(zip(origin_lengths, current_lengths)):
            ratio = round(cur / ori, 2) if ori > 0 else 1.0
            logger.info(
                f"Section {id_ + 1}: the words of original section is {ori}, and the words of compressed section is {cur}, the ratio is {ratio}"
            )
            
            # 如果压缩过度（低于阈值）
            if ratio < self.MIN_COMPRESSION_RATIO:
                logger.warning(
                    f"Section {id_ + 1}: compression ratio {ratio} is below threshold {self.MIN_COMPRESSION_RATIO}"
                )
                
                # 尝试重新生成，使用更保守的策略
                retry_success = False
                for attempt in range(2, self.MAX_RETRY_ATTEMPTS + 2):
                    logger.info(f"Section {id_ + 1}: Retry attempt {attempt - 1} with conservative compression")
                    try:
                        retry_content = self._compress_single_section(origin_sec_contents[id_], attempt)
                        retry_length = len(retry_content.strip().split())
                        retry_ratio = round(retry_length / ori, 2) if ori > 0 else 1.0
                        
                        logger.info(f"Section {id_ + 1}: Retry result - ratio {retry_ratio}")
                        
                        if retry_ratio >= self.MIN_COMPRESSION_RATIO:
                            # 重试成功，使用新内容
                            new_sec_contents[id_] = retry_content
                            retry_success = True
                            logger.info(f"Section {id_ + 1}: Retry successful, using new content with ratio {retry_ratio}")
                            break
                    except Exception as e:
                        logger.warning(f"Section {id_ + 1}: Retry attempt {attempt - 1} failed: {e}")
                        continue
                
                # 如果所有重试都失败，使用原始内容
                if not retry_success:
                    logger.warning(
                        f"Section {id_ + 1}: All retry attempts failed, using original content"
                    )
                    new_sec_contents[id_] = origin_sec_contents[id_]

        return new_sec_contents

    def rewrite_main_sections(self, origin_sec_contents: list[str]) -> list[str]:
        new_sec_contents = []

        # compress the introduction section
        introduction_content = origin_sec_contents[0]
        intro_compression_prompt = load_prompt(
            filename=str(
                self.rewrite_prompt_dir.joinpath(
                    "introduction_compression.md"
                ).absolute()
            ),
            introduction_sec=introduction_content,
        )
        compressed_intro = self.chat_agent.remote_chat(
            intro_compression_prompt, model=ADVANCED_CHATAGENT_MODEL
        )
        new_sec_contents.append(introduction_content)

        # iteratively rewrite sections
        compressed_context = compressed_intro
        sec_id = 2
        for sec_content in tqdm(
            origin_sec_contents[1:], desc=f"iteratively rewriting section no.{sec_id}"
        ):
            sec_rewrite_prompt = load_prompt(
                filename=str(
                    self.rewrite_prompt_dir.joinpath(
                        "rewrite_section_with_compressed_context.md"
                    ).absolute()
                ),
                context=compressed_context,
                content=sec_content,
            )
            new_sec_content = self.chat_agent.remote_chat(
                sec_rewrite_prompt, model=ADVANCED_CHATAGENT_MODEL
            )
            new_sec_content = clean_chat_agent_format(content=new_sec_content)
            
            # 检查重写后的内容是否压缩过度
            ori_len = len(sec_content.strip().split())
            new_len = len(new_sec_content.strip().split())
            ratio = new_len / ori_len if ori_len > 0 else 1.0
            
            if ratio < self.MIN_COMPRESSION_RATIO:
                logger.warning(
                    f"Section {sec_id}: rewrite ratio {ratio:.2f} is below threshold {self.MIN_COMPRESSION_RATIO}, using original content"
                )
                new_sec_contents.append(sec_content)
            else:
                new_sec_contents.append(new_sec_content)

            sec_id += 1
            if len(new_sec_contents) >= len(origin_sec_contents):
                break

            # ----
            compression_prompt = load_prompt(
                filename=str(
                    self.rewrite_prompt_dir.joinpath(
                        "iterative_compression.md"
                    ).absolute()
                ),
                previous_compression=compressed_context,
                content_for_compressions=sec_content,
            )
            compressed_context = self.chat_agent.remote_chat(
                compression_prompt, model=ADVANCED_CHATAGENT_MODEL
            )
            compressed_context = clean_chat_agent_format(content=compressed_context)
        self.rule_address_gpt_rewrite_issues(
            origin_sec_contents=origin_sec_contents, new_sec_contents=new_sec_contents
        )

        # print length and check for over-compression
        origin_lengths = [len(one.strip().split()) for one in origin_sec_contents]
        current_lengths = [len(one.strip().split()) for one in new_sec_contents]
        for id_, (ori, cur) in enumerate(zip(origin_lengths, current_lengths)):
            ratio = round(cur / ori, 2) if ori > 0 else 1.0
            logger.info(
                f"Section {id_ + 1}: the words of original section is {ori}, and the words of rewritten section is {cur}, the ratio is {ratio}"
            )

        return new_sec_contents

    def rewrite_conclusion(self, origin_conclusion_text: str, introduction_text: str):
        prompt = load_prompt(
            filename=str(
                self.rewrite_prompt_dir.joinpath("rewrite_conclusion.md").absolute()
            ),
            introduction=introduction_text,
            origin_conclusion=origin_conclusion_text,
        )
        conclusion = self.chat_agent.remote_chat(prompt, model=ADVANCED_CHATAGENT_MODEL)
        conclusion = clean_chat_agent_format(content=conclusion)

        # 查看重写后是否有问题
        origin_conclusion_tmp_list = [origin_conclusion_text]
        new_conclusion_tmp_list = [conclusion]
        self.rule_address_gpt_rewrite_issues(
            origin_sec_contents=origin_conclusion_tmp_list,
            new_sec_contents=new_conclusion_tmp_list,
        )
        logger.info(f"Rewrote the conclusion section.")
        conclusion = new_conclusion_tmp_list[0]
        return conclusion

    def run(self, mainbody_path=None):
        if mainbody_path is None:
            mainbody_path = self.mainbody_path
        survey_sections = self.load_survey_sections(mainbody_path)
        # compression
        sec_contents = [one.content for one in survey_sections]
        try:
            compressed_survey_sections = self.compress_sections(
                origin_sec_contents=sec_contents
            )
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(
                f"Compression failed.  An error occurred: {e}; The traceback: {tb_str} "
            )
            compressed_survey_sections = sec_contents

        # ------ 使用迭代重写 --------
        # enhance coherence
        try:
            rewritten_survey_sections = self.rewrite_main_sections(
                origin_sec_contents=compressed_survey_sections[:-1]
            )
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(
                f"Rewritten failed.  An error occurred: {e}; The traceback: {tb_str} "
            )
            rewritten_survey_sections = compressed_survey_sections[:-1]

        new_conclusion = self.rewrite_conclusion(
            origin_conclusion_text=compressed_survey_sections[-1],
            introduction_text=compressed_survey_sections[0],
        )
        rewritten_survey_sections.append(new_conclusion)

        # # ------- 不使用迭代重写 --------
        # rewritten_survey_sections = compressed_survey_sections

        rewritten_survey_text = "\n".join(rewritten_survey_sections)
        save_result(rewritten_survey_text, self.refined_mainbody_path)
        logger.debug(f"Save content to {self.refined_mainbody_path}.")
        return rewritten_survey_text


if __name__ == "__main__":
    task_id = load_latest_task_id()
    print(f"task_id: {task_id}")
    # store vector index into local directory for the convenience of debugging
    sec_rewriter = SectionRewriter(task_id=task_id)
    sec_rewriter.run()
