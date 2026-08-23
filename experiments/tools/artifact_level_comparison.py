#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Low-cost artifact-level comparison across SurveyGraph fresh outputs and
released artifacts bundled in the ARISE repository.

This script is intentionally conservative:
- it compares repository-available artifacts, not fair re-runs;
- it extracts lightweight structural signals from PDFs and nearby files;
- it produces CSV / JSON / Markdown outputs for paper-ready reporting.
"""

from __future__ import annotations

import csv
import json
import math
import re
import statistics
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import fitz  # PyMuPDF


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "outputs" / "artifact_level_comparison_20260524"


@dataclass(frozen=True)
class ArtifactSpec:
    system: str
    source_type: str
    glob_pattern: str
    notes: str = ""


ARTIFACT_SPECS: List[ArtifactSpec] = [
    ArtifactSpec(
        system="SurveyGraph-GLM-fresh",
        source_type="fresh_rerun",
        glob_pattern="outputs/20260523_225649_stable_glm_smoke_2506_12689v2/survey.pdf",
        notes="Fresh low-cost end-to-end rerun",
    ),
    ArtifactSpec(
        system="SurveyGraph-Qwen-fresh",
        source_type="fresh_rerun",
        glob_pattern="outputs/20260524_003805_stable_qwen_smoke_2506_12689v2/survey.pdf",
        notes="Fresh low-cost end-to-end rerun",
    ),
    ArtifactSpec(
        system="AutoSurvey",
        source_type="released_artifact",
        glob_pattern="refer/ARISE-main/Dataset/autosurvey/*.pdf",
        notes="Released PDFs bundled with ARISE repo",
    ),
    ArtifactSpec(
        system="SurveyForge",
        source_type="released_artifact",
        glob_pattern="refer/ARISE-main/Dataset/surveyforge/*.pdf",
        notes="Released PDFs bundled with ARISE repo",
    ),
    ArtifactSpec(
        system="SurveyX",
        source_type="released_artifact",
        glob_pattern="refer/ARISE-main/Dataset/surveyx/*.pdf",
        notes="Released PDFs bundled with ARISE repo",
    ),
    ArtifactSpec(
        system="ARISE",
        source_type="released_artifact",
        glob_pattern="refer/ARISE-main/ARISE_sample_surveys_ouput_gpt4.1/*/pdf_output/final_paper_round*.pdf",
        notes="Released multi-round sample outputs bundled with ARISE repo",
    ),
]


COMMON_SECTION_TITLES = {
    "abstract",
    "introduction",
    "background",
    "preliminaries",
    "related work",
    "method",
    "methods",
    "methodology",
    "approach",
    "framework",
    "experiments",
    "evaluation",
    "results",
    "discussion",
    "applications",
    "challenges",
    "limitations",
    "conclusion",
    "conclusions",
    "future work",
    "references",
    "bibliography",
}


def iter_pdf_paths() -> Iterable[tuple[ArtifactSpec, Path]]:
    for spec in ARTIFACT_SPECS:
        for path in sorted(ROOT.glob(spec.glob_pattern)):
            if path.is_file():
                yield spec, path


def infer_artifact_root(pdf_path: Path) -> Path:
    if pdf_path.name == "survey.pdf":
        return pdf_path.parent
    if pdf_path.parent.name == "pdf_output":
        return pdf_path.parent.parent
    return pdf_path.parent


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_pdf_text(pdf_path: Path) -> Dict[str, object]:
    with fitz.open(pdf_path) as doc:
        texts = []
        for page in doc:
            try:
                texts.append(page.get_text("text"))
            except Exception:
                texts.append("")
        toc = doc.get_toc(simple=True)
        return {
            "page_count": len(doc),
            "text": "\n".join(texts),
            "toc": toc,
        }


def count_section_headings(text: str, toc: List[List[object]]) -> int:
    if toc:
        return len(toc)

    headings = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or len(line) > 140:
            continue
        lower = line.lower().rstrip(":")
        if lower in COMMON_SECTION_TITLES:
            headings.add(line)
            continue
        if re.match(r"^(?:\d+(?:\.\d+){0,3})\s+[A-Z].{2,120}$", line):
            headings.add(line)
            continue
    return len(headings)


def safe_bool_any(root: Path, patterns: List[str]) -> bool:
    for pattern in patterns:
        if any(root.rglob(pattern)):
            return True
    return False


def summarize_number_list(values: List[float]) -> Dict[str, Optional[float]]:
    if not values:
        return {"mean": None, "median": None, "min": None, "max": None}
    return {
        "mean": round(statistics.mean(values), 2),
        "median": round(statistics.median(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def percent_true(rows: List[Dict[str, object]], key: str) -> float:
    if not rows:
        return 0.0
    return round(100.0 * sum(1 for row in rows if row.get(key)) / len(rows), 2)


def collect_row(spec: ArtifactSpec, pdf_path: Path) -> Dict[str, object]:
    artifact_root = infer_artifact_root(pdf_path)
    pdf_info = extract_pdf_text(pdf_path)
    text = str(pdf_info["text"])
    toc = list(pdf_info["toc"])

    numeric_citation_mentions = len(re.findall(r"\[(?:\d+[,\-\s]*)+\]", text))
    author_year_citation_mentions = len(
        re.findall(r"\([A-Z][A-Za-z][^)\n]{0,40}\b(?:19|20)\d{2}[a-z]?\)", text)
    )
    figure_mentions = len(re.findall(r"\b(?:Figure|Fig\.)\s*\d+", text, flags=re.I))
    table_mentions = len(re.findall(r"\bTable\s*\d+", text, flags=re.I))
    section_heading_count = count_section_headings(text, toc)
    round_matches = re.findall(r"round(\d+)", pdf_path.stem, flags=re.I)
    round_index = int(round_matches[0]) if round_matches else None

    topic = artifact_root.name
    if spec.system in {"AutoSurvey", "SurveyForge", "SurveyX"}:
        topic = pdf_path.stem

    has_tex = safe_bool_any(artifact_root, ["*.tex"])
    has_bib = safe_bool_any(artifact_root, ["*.bib"])
    has_review_logs = safe_bool_any(
        artifact_root,
        [
            "*review*.csv",
            "*review*.json",
            "*review*.md",
            "review_output/*.csv",
            "review_output/*.json",
        ],
    )
    has_intermediate_markdown = safe_bool_any(artifact_root, ["*.md"])
    multi_round_pdf_count = len(list(artifact_root.rglob("pdf_output/final_paper_round*.pdf")))
    has_multi_round_outputs = multi_round_pdf_count > 1

    references_heading_present = bool(
        re.search(r"(^|\n)\s*(references|bibliography)\s*$", text, flags=re.I | re.M)
    )

    row = {
        "system": spec.system,
        "source_type": spec.source_type,
        "topic": topic,
        "artifact_root": str(artifact_root.relative_to(ROOT)),
        "pdf_name": pdf_path.name,
        "pdf_path": str(pdf_path.relative_to(ROOT)),
        "pdf_sha256_12": sha256_file(pdf_path)[:12],
        "page_count": int(pdf_info["page_count"]),
        "text_chars": len(text),
        "word_count": len(re.findall(r"\b\w+\b", text)),
        "toc_entries": len(toc),
        "section_heading_count": section_heading_count,
        "numeric_citation_mentions": numeric_citation_mentions,
        "author_year_citation_mentions": author_year_citation_mentions,
        "citation_mentions_total": numeric_citation_mentions + author_year_citation_mentions,
        "figure_mentions": figure_mentions,
        "table_mentions": table_mentions,
        "references_heading_present": references_heading_present,
        "has_tex": has_tex,
        "has_bib": has_bib,
        "has_review_logs": has_review_logs,
        "has_intermediate_markdown": has_intermediate_markdown,
        "has_multi_round_outputs": has_multi_round_outputs,
        "multi_round_pdf_count": multi_round_pdf_count,
        "round_index": round_index,
        "notes": spec.notes,
    }
    return row


def write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_summary(rows: List[Dict[str, object]]) -> Dict[str, object]:
    by_system: Dict[str, List[Dict[str, object]]] = {}
    for row in rows:
        by_system.setdefault(str(row["system"]), []).append(row)

    systems_summary: List[Dict[str, object]] = []
    for system, system_rows in sorted(by_system.items()):
        page_values = [float(row["page_count"]) for row in system_rows]
        text_values = [float(row["text_chars"]) for row in system_rows]
        citation_values = [float(row["citation_mentions_total"]) for row in system_rows]
        section_values = [float(row["section_heading_count"]) for row in system_rows]
        figure_values = [float(row["figure_mentions"]) for row in system_rows]
        table_values = [float(row["table_mentions"]) for row in system_rows]

        systems_summary.append(
            {
                "system": system,
                "source_type": system_rows[0]["source_type"],
                "artifact_count": len(system_rows),
                "page_count": summarize_number_list(page_values),
                "text_chars": summarize_number_list(text_values),
                "citation_mentions_total": summarize_number_list(citation_values),
                "section_heading_count": summarize_number_list(section_values),
                "figure_mentions": summarize_number_list(figure_values),
                "table_mentions": summarize_number_list(table_values),
                "tex_coverage_pct": percent_true(system_rows, "has_tex"),
                "bib_coverage_pct": percent_true(system_rows, "has_bib"),
                "review_log_coverage_pct": percent_true(system_rows, "has_review_logs"),
                "markdown_coverage_pct": percent_true(system_rows, "has_intermediate_markdown"),
                "multi_round_coverage_pct": percent_true(system_rows, "has_multi_round_outputs"),
            }
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "comparison_type": "artifact_level",
        "scope_note": (
            "This is a repository-available artifact comparison, not a fair live rerun benchmark."
        ),
        "artifact_count_total": len(rows),
        "systems": systems_summary,
    }


def render_markdown(summary: Dict[str, object], rows: List[Dict[str, object]]) -> str:
    systems = summary["systems"]
    md = []
    md.append("# Artifact-Level Comparison (ARISE bundled outputs + SurveyGraph fresh reruns)")
    md.append("")
    md.append(
        "> Scope note: 这是 **artifact-level comparison**，基于仓库内可获得的 released artifacts 与 SurveyGraph fresh rerun artifacts；**不是** 公平的 live rerun benchmark。"
    )
    md.append("")
    md.append(f"- Generated at: `{summary['generated_at']}`")
    md.append(f"- Total artifacts analyzed: `{summary['artifact_count_total']}`")
    md.append("")
    md.append("## System-level summary")
    md.append("")
    md.append(
        "| System | Source | N | Pages mean | Text chars mean | Citation mentions mean | Section headings mean | Fig mentions mean | Table mentions mean | TeX cov. | Bib cov. | Review-log cov. | Multi-round cov. |"
    )
    md.append(
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    )
    for item in systems:
        md.append(
            "| {system} | {source_type} | {artifact_count} | {pages} | {text_chars} | {cites} | {sections} | {figs} | {tables} | {tex_cov}% | {bib_cov}% | {review_cov}% | {round_cov}% |".format(
                system=item["system"],
                source_type=item["source_type"],
                artifact_count=item["artifact_count"],
                pages=item["page_count"]["mean"],
                text_chars=item["text_chars"]["mean"],
                cites=item["citation_mentions_total"]["mean"],
                sections=item["section_heading_count"]["mean"],
                figs=item["figure_mentions"]["mean"],
                tables=item["table_mentions"]["mean"],
                tex_cov=item["tex_coverage_pct"],
                bib_cov=item["bib_coverage_pct"],
                review_cov=item["review_log_coverage_pct"],
                round_cov=item["multi_round_coverage_pct"],
            )
        )
    md.append("")
    md.append("## Per-artifact file")
    md.append("")
    md.append("- Full CSV: `artifact_level_comparison_rows.csv`")
    md.append("- Full JSON: `artifact_level_comparison_summary.json`")
    md.append("")
    md.append("## Notes")
    md.append("")
    md.append("- `SurveyGraph-GLM-fresh` 与 `SurveyGraph-Qwen-fresh` 是真实 fresh rerun。")
    md.append("- `AutoSurvey` / `SurveyForge` / `SurveyX` / `ARISE` 条目来自 `refer/ARISE-main/` 内置 released artifacts。")
    md.append("- 多轮输出覆盖率仅对目录中存在 `final_paper_round*.pdf` 的样例有效。")
    md.append("- 文本、章节、引用、表图计数均为轻量规则提取，适合作为 artifact-level structural evidence，而非人工语义评测。")
    md.append("")
    return "\n".join(md)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = [collect_row(spec, path) for spec, path in iter_pdf_paths()]
    summary = build_summary(rows)

    csv_path = OUTPUT_DIR / "artifact_level_comparison_rows.csv"
    json_path = OUTPUT_DIR / "artifact_level_comparison_summary.json"
    md_path = OUTPUT_DIR / "artifact_level_comparison_report.md"

    write_csv(csv_path, rows)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(summary, rows), encoding="utf-8")

    print(f"Wrote {len(rows)} artifact rows")
    print(csv_path)
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
