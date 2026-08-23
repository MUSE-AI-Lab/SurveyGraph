from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
SURVEYBENCH_ROOT = ROOT / "refer" / "SurveyForge-main" / "SurveyBench"
DEFAULT_OUTPUT_ROOT = ROOT / "outputs"


def parse_arxiv_date(arxiv_id: str) -> Tuple[Optional[datetime], Optional[int]]:
    match = re.match(r"(\d{2})(\d{2})\.(\d{4,5})", arxiv_id or "")
    if not match:
        return None, None
    year, month, seq_number = match.groups()
    try:
        paper_date = datetime.strptime(f"20{year}-{month}", "%Y-%m")
    except ValueError:
        return None, None
    return paper_date, int(seq_number)


def normalize_arxiv_id(value: str) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip()
    text = re.sub(r"^arxiv[:_]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"v\d+$", "", text, flags=re.IGNORECASE)
    match = re.search(r"(\d{4}\.\d{4,5}|\d{7})", text)
    if match:
        return match.group(1)
    return None


def compute_citation_coverage(
    target_refs: Sequence[str],
    benchmark_refs: Iterable[str],
) -> Dict[str, Any]:
    target_paper_dates: Dict[str, Tuple[datetime, int]] = {}
    for paper_id in target_refs:
        clean_paper_id = normalize_arxiv_id(paper_id)
        if not clean_paper_id:
            continue
        date, seq_num = parse_arxiv_date(clean_paper_id)
        if date is not None and seq_num is not None:
            target_paper_dates[clean_paper_id] = (date, seq_num)

    benchmark_paper_dates: Dict[str, Tuple[datetime, int]] = {}
    for paper_id in benchmark_refs:
        clean_paper_id = normalize_arxiv_id(paper_id)
        if not clean_paper_id:
            continue
        date, seq_num = parse_arxiv_date(clean_paper_id)
        if date is not None and seq_num is not None:
            benchmark_paper_dates[clean_paper_id] = (date, seq_num)

    if not benchmark_paper_dates:
        return {
            "valid_target_count": 0,
            "matched_count": 0,
            "coverage": 0.0,
            "matched_ids": [],
        }

    latest_bench_date, latest_bench_seq = max(
        benchmark_paper_dates.values(),
        key=lambda x: (x[0], x[1]),
    )
    valid_target_ids = {
        paper_id
        for paper_id, (date, seq_num) in target_paper_dates.items()
        if (date < latest_bench_date) or (date == latest_bench_date and seq_num < latest_bench_seq)
    }
    matched_paper_ids = sorted(valid_target_ids.intersection(benchmark_paper_dates.keys()))
    citation_count = len(matched_paper_ids)
    total_papers = len(valid_target_ids)
    return {
        "valid_target_count": total_papers,
        "matched_count": citation_count,
        "coverage": citation_count / total_papers if total_papers > 0 else 0.0,
        "matched_ids": matched_paper_ids,
    }


def extract_reference_ids_from_bib(bib_path: Path) -> List[str]:
    text = bib_path.read_text(encoding="utf-8", errors="ignore")
    ids: List[str] = []
    for key in re.findall(r"@\w+\{([^,]+),", text):
        clean_id = normalize_arxiv_id(key)
        if clean_id:
            ids.append(clean_id)
    return list(dict.fromkeys(ids))


def load_benchmark_refs(topic: str, surveybench_root: Path = SURVEYBENCH_ROOT) -> Dict[str, Any]:
    bench_path = surveybench_root / "ref_bench" / f"{topic}_bench.json"
    return json.loads(bench_path.read_text(encoding="utf-8"))


def load_generated_ref_json(topic: str, surveybench_root: Path = SURVEYBENCH_ROOT) -> Dict[str, Any]:
    path = surveybench_root / "generated_surveys_ref" / topic / "exp_1" / "ref.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_human_ref_json(topic: str, surveybench_root: Path = SURVEYBENCH_ROOT) -> Dict[str, Any]:
    title_map = {
        "3D Gaussian Splatting": "A Survey on 3D Gaussian Splatting",
        "3D Object Detection in Autonomous Driving": "3D Object Detection for Autonomous Driving: A Comprehensive Survey",
        "Evaluation of Large Language Models": "A Survey on Evaluation of Large Language Models",
        "LLM-based Multi-Agent": "A survey on large language model based autonomous agents",
        "Generative Diffusion Models": "A survey on generative diffusion models",
        "Graph Neural Networks": "Graph neural networks: Taxonomy, advances, and trends",
        "Hallucination in Large Language Models": "Siren's Song in the AI Ocean: A Survey on Hallucination in Large Language Models",
        "Multimodal Large Language Models": "A Survey on Multimodal Large Language Models",
        "Retrieval-Augmented Generation for Large Language Models": "Retrieval-augmented generation for large language models: A survey",
        "Vision Transformers": "A survey of visual transformers",
    }
    title = title_map[topic]
    path = surveybench_root / "human_written_ref" / f"{title}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def build_calibration_row(
    *,
    system: str,
    topic: str,
    benchmark_refs: Dict[str, Any],
    target_refs: Sequence[str],
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    stats = compute_citation_coverage(target_refs, benchmark_refs.keys())
    row: Dict[str, Any] = {
        "system": system,
        "topic": topic,
        "benchmark_size": len(benchmark_refs),
        **stats,
    }
    if extra_fields:
        row.update(extra_fields)
    return row


def build_archived_run_result(
    *,
    topic: str,
    run_id: str,
    run_label: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    surveybench_root: Path = SURVEYBENCH_ROOT,
) -> Dict[str, Any]:
    benchmark_refs = load_benchmark_refs(topic, surveybench_root=surveybench_root)
    bib_path = output_root / run_id / "latex" / "references.bib"
    target_refs = extract_reference_ids_from_bib(bib_path)
    return build_calibration_row(
        system="SurveyGraph-archived-corpus",
        topic=topic,
        benchmark_refs=benchmark_refs,
        target_refs=target_refs,
        extra_fields={
            "run_id": run_id,
            "run_label": run_label,
            "run_dir": str((output_root / run_id).relative_to(ROOT)),
            "source_ref_count": len(target_refs),
        },
    )


def build_live_run_result(
    *,
    topic: str,
    run_id: str,
    run_label: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    surveybench_root: Path = SURVEYBENCH_ROOT,
) -> Dict[str, Any]:
    benchmark_refs = load_benchmark_refs(topic, surveybench_root=surveybench_root)
    bib_path = output_root / run_id / "latex" / "references.bib"
    target_refs = extract_reference_ids_from_bib(bib_path)
    return build_calibration_row(
        system="SurveyGraph-live",
        topic=topic,
        benchmark_refs=benchmark_refs,
        target_refs=target_refs,
        extra_fields={
            "run_id": run_id,
            "run_label": run_label,
            "run_dir": str((output_root / run_id).relative_to(ROOT)),
            "source_ref_count": len(target_refs),
        },
    )


def build_topic_probe(
    *,
    topic: str,
    live_run_id: Optional[str] = None,
    live_run_label: str = "SurveyGraph live run",
    archived_rows: Optional[Sequence[Tuple[str, str]]] = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    surveybench_root: Path = SURVEYBENCH_ROOT,
) -> Dict[str, Any]:
    benchmark_refs = load_benchmark_refs(topic, surveybench_root=surveybench_root)
    surveyforge_generated = load_generated_ref_json(topic, surveybench_root=surveybench_root)
    human_refs = load_human_ref_json(topic, surveybench_root=surveybench_root)

    payload: Dict[str, Any] = {
        "experiment_type": "surveybench_live_reference_probe",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "topic": topic,
        "scope_note": (
            "Single-topic SurveyBench-style reference coverage probe. "
            "Coverage is computed with the same date-filtered arXiv-ID overlap rule used by the local SurveyForge SurveyBench script."
        ),
        "rows": [
            build_calibration_row(
                system="SurveyForge-released",
                topic=topic,
                benchmark_refs=benchmark_refs,
                target_refs=list(surveyforge_generated.keys()),
                extra_fields={"source_ref_count": len(surveyforge_generated)},
            ),
            build_calibration_row(
                system="Human-survey",
                topic=topic,
                benchmark_refs=benchmark_refs,
                target_refs=list(human_refs.keys()),
                extra_fields={"source_ref_count": len(human_refs)},
            ),
        ],
    }

    if archived_rows:
        payload["rows"].extend(
            build_archived_run_result(
                topic=topic,
                run_id=run_id,
                run_label=run_label,
                output_root=output_root,
                surveybench_root=surveybench_root,
            )
            for run_id, run_label in archived_rows
        )

    if live_run_id:
        payload["rows"].append(
            build_live_run_result(
                topic=topic,
                run_id=live_run_id,
                run_label=live_run_label,
                output_root=output_root,
                surveybench_root=surveybench_root,
            )
        )

    return payload


def build_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# SurveyBench Live Reference Probe",
        "",
        f"- Topic: {payload['topic']}",
        f"- Generated at: {payload['generated_at']}",
        f"- Scope: {payload['scope_note']}",
        "",
        "| System | Valid target refs | Matched | Coverage | Source refs |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| {row['system']} | {row['valid_target_count']} | {row['matched_count']} | "
            f"{row['coverage']:.3f} | {row.get('source_ref_count', 0)} |"
        )
    lines.append("")
    for row in payload["rows"]:
        if row.get("matched_ids"):
            preview = ", ".join(row["matched_ids"][:15])
            lines.append(f"- **{row['system']} matched IDs (preview):** {preview}")
    lines.append("")
    return "\n".join(lines)


def write_outputs(payload: Dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "surveybench_live_reference_probe.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "surveybench_live_reference_probe.md").write_text(
        build_markdown(payload),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a single-topic SurveyBench-style reference coverage probe")
    parser.add_argument("--topic", required=True, help="SurveyBench topic name")
    parser.add_argument("--live-run-id", default=None, help="outputs/<run_id> to score as SurveyGraph-live")
    parser.add_argument("--live-run-label", default="SurveyGraph live run", help="Display label for live run")
    parser.add_argument(
        "--archived-run",
        action="append",
        default=[],
        help="Archived calibration row in the form run_id::run_label (repeatable)",
    )
    parser.add_argument("--output-dir", default=None, help="Optional explicit output directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    archived_rows: List[Tuple[str, str]] = []
    for item in args.archived_run:
        if "::" not in item:
            raise ValueError(f"Invalid --archived-run value: {item!r}")
        run_id, run_label = item.split("::", 1)
        archived_rows.append((run_id, run_label))

    payload = build_topic_probe(
        topic=args.topic,
        live_run_id=args.live_run_id,
        live_run_label=args.live_run_label,
        archived_rows=archived_rows,
    )
    out_dir = (
        Path(args.output_dir)
        if args.output_dir
        else DEFAULT_OUTPUT_ROOT / f"surveybench_live_reference_probe_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    write_outputs(payload, out_dir)
    print(f"Wrote outputs to {out_dir}")


if __name__ == "__main__":
    main()
