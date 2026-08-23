import io
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from datetime import datetime
import glob
from shutil import which

import fitz

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))  # run code in any path

from src.configs.constants import OUTPUT_DIR, RESOURCE_DIR
from src.configs.logger import get_logger
from src.configs.utils import load_latest_task_id
from src.models.LLM import ChatAgent
from src.models.monitor.time_monitor import TimeMonitor
from src.modules.latex_handler.latex_text_builder import LatexTextBuilder

logger = get_logger("src.modules.generator.LatexGenerator")


class LatexGenerator:
    def __init__(self, task_id: str, **kwargs):
        task_id = load_latest_task_id() if task_id is None else task_id
        assert task_id is not None
        self.task_id = task_id
        self.outlines_path = Path(f"{OUTPUT_DIR}/{str(self.task_id)}/outlines.json")

        # for text builder
        self.init_text_tex_path = Path(f"{RESOURCE_DIR}/latex/survey.ini.tex")
        
        # 确定 mainbody 路径
        # 优先使用增强后的多模态内容（包含AI生成的图片和表格）
        enhanced_multimodal_path = Path(
            f"{OUTPUT_DIR}/{str(self.task_id)}/tmp/mainbody_enhanced_multimodal.tex"
        )
        post_refined_path = Path(
            f"{OUTPUT_DIR}/{str(self.task_id)}/tmp/mainbody_post_refined.tex"
        )
        
        if enhanced_multimodal_path.exists():
            self.mainbody_tex_path = enhanced_multimodal_path
            self.post_refined_mainbody_tex_path = enhanced_multimodal_path
            logger.info(f"Using enhanced multimodal content: {enhanced_multimodal_path}")
        else:
            self.mainbody_tex_path = post_refined_path
            self.post_refined_mainbody_tex_path = post_refined_path
            logger.info(f"Using post-refined content: {post_refined_path}")
        self.abstract_path = Path(f"{OUTPUT_DIR}/{str(self.task_id)}/tmp/abstract.tex")
        self.survey_tex_path = Path(
            f"{OUTPUT_DIR}/{str(self.task_id)}/latex/survey.tex"
        )

        # init builders
        # -- text
        self.text_builder = LatexTextBuilder(init_tex_path=self.init_text_tex_path)

    def add_watermark(self, input_pdf: Path, output_pdf: Path, watermark_pdf: Path):
        # 打开输入的 PDF 和水印 PDF
        doc = fitz.open(input_pdf)
        watermark = fitz.open(watermark_pdf)
        # 获取水印页面（假设水印文件只有一页）
        watermark_page = watermark[0]
        # 获取水印页面的 pixmap（即图像）
        watermark_pixmap = watermark_page.get_pixmap()
        # 将水印图像转换为字节流
        img_stream = io.BytesIO(watermark_pixmap.tobytes())
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            # 获取当前页面的尺寸
            page_rect = page.rect
            # 将水印图像插入页面
            page.insert_image(page_rect, stream=img_stream, overlay=False, alpha=0.3)
        # 保存修改后的 PDF
        doc.save(output_pdf)

    def compile_single_survey(self):
        time_monitor = TimeMonitor(self.task_id)
        time_monitor.start("compile latex")

        task_dir = Path(BASE_DIR) / "outputs" / self.task_id
        latex_dir = task_dir / "latex"
        sty_file_path = Path(BASE_DIR) / "resources" / "latex" / "neurips_2024.sty"
        water_mark_pdf_path = Path(BASE_DIR) / "resources" / "latex" / "watermark.png"
        original_cwd = Path.cwd()

        def _run_logged(command, output_file, *, use_shell: bool = False) -> int:
            logger.debug(f'Running "{command if isinstance(command, str) else " ".join(command)}"')
            result = subprocess.run(
                command,
                shell=use_shell,
                stdout=output_file,
                stderr=output_file,
                check=False,
            )
            return int(result.returncode)

        try:
            os.chdir(task_dir)
            # 删除文件 output/survey.pdf (跨平台兼容)
            survey_pdf = task_dir / "survey.pdf"
            survey_wtmk_pdf = task_dir / "survey_wtmk.pdf"
            if survey_pdf.exists():
                survey_pdf.unlink()
            if survey_wtmk_pdf.exists():
                survey_wtmk_pdf.unlink()

            # 切换到 latex 目录
            os.chdir(latex_dir)

            # prepare sty file (跨平台兼容)
            shutil.copy(sty_file_path, latex_dir / "neurips_2024.sty")

            compile_log_path = latex_dir / "compile.log"
            latexmk_rc = 1
            with open(compile_log_path, "w", encoding="utf-8") as output_file:
                logger.debug(
                    f'Primary compile command prefers latexmk. The compile.log is at {compile_log_path}'
                )
                latexmk_path = which("latexmk")
                if latexmk_path:
                    latexmk_rc = _run_logged(
                        [latexmk_path, "-pdf", "-interaction=nonstopmode", "-f", "survey.tex"],
                        output_file,
                    )
                else:
                    output_file.write("[compile] latexmk not found; skip primary compiler.\n")

                survey_pdf_in_latex = latex_dir / "survey.pdf"
                if latexmk_rc != 0 or not survey_pdf_in_latex.exists():
                    output_file.write(
                        f"\n[compile] latexmk unavailable/failed (rc={latexmk_rc}) or survey.pdf missing; "
                        "falling back to pdflatex/bibtex pipeline.\n"
                    )
                    logger.warning(
                        "latexmk failed or did not produce survey.pdf; falling back to pdflatex/bibtex pipeline"
                    )

                    pdflatex_path = which("pdflatex")
                    if not pdflatex_path:
                        raise FileNotFoundError("pdflatex not found in PATH")

                    _run_logged([pdflatex_path, "-interaction=nonstopmode", "survey.tex"], output_file)

                    aux_path = latex_dir / "survey.aux"
                    bibtex_path = which("bibtex")
                    if aux_path.exists() and bibtex_path:
                        _run_logged([bibtex_path, "survey"], output_file)
                    elif not bibtex_path:
                        output_file.write("[compile] bibtex not found; skip bibliography pass.\n")

                    _run_logged([pdflatex_path, "-interaction=nonstopmode", "survey.tex"], output_file)
                    _run_logged([pdflatex_path, "-interaction=nonstopmode", "survey.tex"], output_file)

            # 执行 latexmk -c 删除中间文件（仅在 latexmk 可用时尝试）
            latexmk_cleanup_path = which("latexmk")
            if latexmk_cleanup_path:
                with open(compile_log_path, "a", encoding="utf-8") as output_file:
                    cleanup_rc = _run_logged([latexmk_cleanup_path, "-c"], output_file)
                    if cleanup_rc != 0:
                        output_file.write(f"[compile] latexmk -c failed with rc={cleanup_rc}; skip cleanup.\n")

            # 删除所有 .bbl 文件 (跨平台兼容)
            for bbl_file in glob.glob(str(latex_dir / "*.bbl")):
                Path(bbl_file).unlink()

            # 删除 neurips_2024.sty (跨平台兼容)
            sty_in_latex = latex_dir / "neurips_2024.sty"
            if sty_in_latex.exists():
                sty_in_latex.unlink()

            # 将生成的 survey.pdf 移动到上一级目录 (跨平台兼容)
            survey_pdf_in_latex = latex_dir / "survey.pdf"
            if survey_pdf_in_latex.exists():
                shutil.move(str(survey_pdf_in_latex), str(task_dir / "survey.pdf"))

            if not survey_pdf.exists():
                raise FileNotFoundError(
                    f"survey.pdf was not produced. Check compile log: {compile_log_path}"
                )

            self.add_watermark(
                task_dir / "survey.pdf", task_dir / "survey_wtmk.pdf", water_mark_pdf_path
            )
        finally:
            os.chdir(original_cwd)

        time_monitor.end("compile latex")

    def _backup_before_update(self, file_path: Path, backup_type: str = "auto"):
        """
        在更新文件之前自动备份当前版本
        
        备份策略：
        1. 如果文件存在，备份到 backups/ 子目录
        2. 备份文件名格式: {filename}.{backup_type}_{timestamp}
        3. 保留最近 10 个备份，自动清理旧备份
        
        Args:
            file_path: 要备份的文件路径
            backup_type: 备份类型标识（如 "auto", "step_5" 等）
        """
        if not file_path.exists():
            return
        
        # 创建备份目录
        backup_dir = file_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成备份文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.name}.{backup_type}_{timestamp}"
        backup_path = backup_dir / backup_name
        
        try:
            shutil.copy2(file_path, backup_path)
            logger.info(f"📦 Backed up {file_path.name} -> {backup_name}")
            
            # 清理旧备份，只保留最近 10 个
            self._cleanup_old_backups(backup_dir, file_path.name, max_keep=10)
        except Exception as e:
            logger.warning(f"⚠️ Failed to backup {file_path.name}: {e}")
    
    def _cleanup_old_backups(self, backup_dir: Path, filename_prefix: str, max_keep: int = 10):
        """
        清理旧备份，只保留最近的 max_keep 个
        
        Args:
            backup_dir: 备份目录
            filename_prefix: 文件名前缀（用于匹配备份文件）
            max_keep: 最多保留的备份数量
        """
        try:
            # 查找所有匹配的备份文件
            pattern = f"{filename_prefix}.*"
            backups = list(backup_dir.glob(pattern))
            
            if len(backups) <= max_keep:
                return
            
            # 按修改时间排序，删除最旧的
            backups.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            for old_backup in backups[max_keep:]:
                old_backup.unlink()
                logger.debug(f"🗑️ Removed old backup: {old_backup.name}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to cleanup old backups: {e}")

    def generate_full_survey(self, backup_type: str = "auto"):
        """
        生成完整的 survey.tex 文件
        
        在生成新版本之前，会自动备份当前版本（如果存在）。
        
        Args:
            backup_type: 备份类型标识，用于区分不同来源的备份
                        - "auto": 自动备份（默认）
                        - "step_X": 来自 pipeline 步骤 X 的备份
                        - "manual": 手动触发的备份
        
        Returns:
            生成的 LaTeX 内容
        """
        # 在生成新版本之前，备份当前版本
        self._backup_before_update(self.survey_tex_path, backup_type)
        
        # make survey.tex
        tex_content = self.text_builder.run(
            outlines_path=self.outlines_path,
            abstract_path=self.abstract_path,
            main_body_path=self.post_refined_mainbody_tex_path,
            latex_save_path=self.survey_tex_path,
        )
        return tex_content


# python -m src.models.generator.latex_generator
if __name__ == "__main__":
    # task_id = load_latest_task_id()
    task_id = "ref1"
    print(f"task_id: {task_id}")
    latex_generator = LatexGenerator(task_id=task_id)

    latex_generator.generate_full_survey()
    latex_generator.compile_single_survey()
