from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.surveybench_live_reference_probe import (
    compute_citation_coverage,
    load_benchmark_refs,
)

COLLECTOR_MODULE_PATH = ROOT / "mekg" / "src" / "processing" / "enhanced_paper_collector.py"
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "exact_topic_live_arxiv_probe_20260525"
DEFAULT_TOPICS = [
    "3D Gaussian Splatting",
    "3D Object Detection in Autonomous Driving",
    "Evaluation of Large Language Models",
    "LLM-based Multi-Agent",
    "Generative Diffusion Models",
    "Graph Neural Networks",
    "Hallucination in Large Language Models",
    "Multimodal Large Language Models",
    "Retrieval-Augmented Generation for Large Language Models",
    "Vision Transformers",
]


def load_collector_module():
    spec = importlib.util.spec_from_file_location(
        "surveygraph_exact_topic_live_probe_collector",
        COLLECTOR_MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_row(
    *,
    topic: str,
    raw_count: int,
    source_ref_ids: Sequence[str],
    benchmark_refs: Dict[str, Any],
) -> Dict[str, Any]:
    stats = compute_citation_coverage(source_ref_ids, benchmark_refs.keys())
    return {
        "topic": topic,
        "raw_count": raw_count,
        "source_ref_count": len(source_ref_ids),
        **stats,
    }


def summarize_rows(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    coverages = [row["coverage"] for row in rows]
    valid_counts = [row["valid_target_count"] for row in rows]
    matched_counts = [row["matched_count"] for row in rows]
    nonzero_rows = [row for row in rows if row["raw_count"] > 0]
    return {
        "topic_count": len(rows),
        "topics_with_nonzero_results": len(nonzero_rows),
        "mean_coverage": mean(coverages) if coverages else 0.0,
        "median_coverage": median(coverages) if coverages else 0.0,
        "mean_valid_target_count": mean(valid_counts) if valid_counts else 0.0,
        "mean_matched_count": mean(matched_counts) if matched_counts else 0.0,
    }


def build_markdown(payload: Dict[str, Any]) -> str:
    agg = payload["aggregate"]
    lines = [
        "# Exact-Topic Live arXiv Probe",
        "",
        "- Scope: live collection-stage probe only; no full SurveyGraph paper generation is executed.",
        "- Retrieval rule: exact topic string sent to the repository arXiv retriever with no LLM keyword expansion.",
        "- Scoring rule: same date-filtered arXiv-ID overlap definition as the local SurveyBench-style reference probe.",
        "",
        f"- Topics: {agg['topic_count']}",
        f"- Topics with non-zero results: {agg['topics_with_nonzero_results']}",
        f"- Mean coverage: {agg['mean_coverage']:.3f}",
        f"- Median coverage: {agg['median_coverage']:.3f}",
        f"- Mean matched references: {agg['mean_matched_count']:.2f}",
        "",
        "| Topic | Raw results | Valid target refs | Matched | Coverage |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| {row['topic']} | {row['raw_count']} | {row['valid_target_count']} | "
            f"{row['matched_count']} | {row['coverage']:.3f} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def write_outputs(payload: Dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "exact_topic_live_arxiv_probe.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "exact_topic_live_arxiv_probe.md").write_text(
        build_markdown(payload),
        encoding="utf-8",
    )
    with (out_dir / "exact_topic_live_arxiv_probe_rows.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "topic",
                "raw_count",
                "source_ref_count",
                "valid_target_count",
                "matched_count",
                "coverage",
            ],
        )
        writer.writeheader()
        for row in payload["rows"]:
            writer.writerow(
                {
                    "topic": row["topic"],
                    "raw_count": row["raw_count"],
                    "source_ref_count": row["source_ref_count"],
                    "valid_target_count": row["valid_target_count"],
                    "matched_count": row["matched_count"],
                    "coverage": f"{row['coverage']:.6f}",
                }
            )


async def run_probe(topics: Sequence[str], max_results: int, retries: int) -> Dict[str, Any]:
    module = load_collector_module()
    searcher = module.ArxivSearcher(rate_limit_delay=3.0)
    rows: List[Dict[str, Any]] = []

    for topic in topics:
        papers = []
        for attempt in range(retries + 1):
            papers = await searcher.search(query=topic, max_results=max_results)
            if papers:
                break
            if attempt < retries:
                await asyncio.sleep(3.0)

        source_ref_ids = []
        for paper in papers:
            paper_id = getattr(paper, "arxiv_id", None) or getattr(paper, "paper_id", None)
            if paper_id:
                source_ref_ids.append(str(paper_id))

        benchmark_refs = load_benchmark_refs(topic)
        rows.append(
            build_row(
                topic=topic,
                raw_count=len(papers),
                source_ref_ids=source_ref_ids,
                benchmark_refs=benchmark_refs,
            )
        )

    payload = {
        "experiment_type": "surveybench_exact_topic_live_arxiv_probe",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope_note": (
            "Live collection-stage benchmark-facing probe. "
            "It only measures exact-topic arXiv retrieval overlap against SurveyBench reference targets "
            "and does not evaluate SurveyGraph's outline generation, writing quality, or citation support in full papers."
        ),
        "rows": rows,
        "aggregate": summarize_rows(rows),
    }
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an exact-topic live arXiv probe against SurveyBench topics")
    parser.add_argument("--topic", action="append", default=[], help="Optional topic override (repeatable)")
    parser.add_argument("--max-results", type=int, default=30, help="Max arXiv results per topic")
    parser.add_argument("--retries", type=int, default=1, help="Extra retries when a topic returns zero results")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    topics = args.topic or DEFAULT_TOPICS
    payload = asyncio.run(run_probe(topics, max_results=args.max_results, retries=args.retries))
    out_dir = Path(args.output_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    write_outputs(payload, out_dir)
    print(f"Wrote outputs to {out_dir}")


if __name__ == "__main__":
    main()
