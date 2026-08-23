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
from typing import Any, Dict, List, Mapping, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.surveybench_live_reference_probe import (
    compute_citation_coverage,
    load_benchmark_refs,
)

COLLECTOR_MODULE_PATH = ROOT / "mekg" / "src" / "processing" / "enhanced_paper_collector.py"
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "surveybench_query_expansion_probe_20260526"
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

QUERY_VARIANTS: Dict[str, List[Tuple[str, float]]] = {
    "3D Gaussian Splatting": [
        ("3D Gaussian Splatting", 1.0),
        ("Gaussian splatting", 0.8),
        ("3DGS neural rendering", 0.6),
    ],
    "3D Object Detection in Autonomous Driving": [
        ("3D Object Detection in Autonomous Driving", 1.0),
        ("LiDAR 3D object detection", 0.8),
        ("autonomous driving 3D detection", 0.6),
    ],
    "Evaluation of Large Language Models": [
        ("Evaluation of Large Language Models", 1.0),
        ("large language model evaluation", 0.8),
        ("LLM benchmark evaluation", 0.6),
    ],
    "LLM-based Multi-Agent": [
        ("LLM-based Multi-Agent", 1.0),
        ("large language model multi-agent", 0.8),
        ("multi-agent LLM", 0.6),
        ("LLM multi-agent systems", 0.5),
    ],
    "Generative Diffusion Models": [
        ("Generative Diffusion Models", 1.0),
        ("diffusion models", 0.8),
        ("denoising diffusion probabilistic models", 0.6),
    ],
    "Graph Neural Networks": [
        ("Graph Neural Networks", 1.0),
        ("graph neural network", 0.8),
        ("graph representation learning", 0.6),
    ],
    "Hallucination in Large Language Models": [
        ("Hallucination in Large Language Models", 1.0),
        ("LLM hallucination", 0.8),
        ("large language model hallucination", 0.6),
    ],
    "Multimodal Large Language Models": [
        ("Multimodal Large Language Models", 1.0),
        ("multimodal LLM", 0.8),
        ("vision language large model", 0.6),
    ],
    "Retrieval-Augmented Generation for Large Language Models": [
        ("Retrieval-Augmented Generation for Large Language Models", 1.0),
        ("retrieval augmented generation", 0.8),
        ("RAG large language models", 0.6),
    ],
    "Vision Transformers": [
        ("Vision Transformers", 1.0),
        ("vision transformer", 0.8),
        ("ViT image recognition", 0.6),
    ],
}


def load_collector_module():
    spec = importlib.util.spec_from_file_location(
        "surveybench_query_expansion_probe_collector",
        COLLECTOR_MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def paper_arxiv_id(paper: Any) -> str | None:
    arxiv_id = getattr(paper, "arxiv_id", None)
    if arxiv_id:
        return str(arxiv_id)
    paper_id = getattr(paper, "paper_id", None)
    if paper_id:
        text = str(paper_id)
        return text.replace("arXiv:", "")
    return None


def merge_variant_results(
    variant_results: Mapping[str, Sequence[Any]],
    *,
    variant_weights: Mapping[str, float],
    target_count: int,
) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for query, papers in variant_results.items():
        weight = float(variant_weights.get(query, 0.1))
        for rank, paper in enumerate(papers):
            arxiv_id = paper_arxiv_id(paper)
            if not arxiv_id:
                continue
            score = weight / (rank + 1)
            if arxiv_id not in merged:
                merged[arxiv_id] = {
                    "arxiv_id": arxiv_id,
                    "title": getattr(paper, "title", ""),
                    "score": 0.0,
                    "best_rank": rank + 1,
                    "query_hits": [],
                }
            merged[arxiv_id]["score"] += score
            merged[arxiv_id]["best_rank"] = min(int(merged[arxiv_id]["best_rank"]), rank + 1)
            if query not in merged[arxiv_id]["query_hits"]:
                merged[arxiv_id]["query_hits"].append(query)

    rows = sorted(
        merged.values(),
        key=lambda item: (-float(item["score"]), int(item["best_rank"]), item["arxiv_id"]),
    )
    return rows[:target_count]


def build_comparison_row(
    *,
    topic: str,
    benchmark_refs: Dict[str, Any],
    expanded_refs: Sequence[str],
    exact_refs: Sequence[str],
    expanded_raw_count: int,
    exact_raw_count: int,
) -> Dict[str, Any]:
    expanded_stats = compute_citation_coverage(expanded_refs, benchmark_refs.keys())
    exact_stats = compute_citation_coverage(exact_refs, benchmark_refs.keys())
    return {
        "topic": topic,
        "benchmark_size": len(benchmark_refs),
        "expanded_raw_count": expanded_raw_count,
        "exact_raw_count": exact_raw_count,
        "expanded": expanded_stats,
        "exact": exact_stats,
        "coverage_delta": expanded_stats["coverage"] - exact_stats["coverage"],
        "matched_delta": expanded_stats["matched_count"] - exact_stats["matched_count"],
    }


def summarize_rows(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {
            "topic_count": 0,
            "topics_expanded_better": 0,
            "topics_exact_better": 0,
            "topics_tied": 0,
            "mean_coverage_delta": 0.0,
            "median_coverage_delta": 0.0,
            "mean_expanded_coverage": 0.0,
            "mean_exact_coverage": 0.0,
            "mean_expanded_matched_count": 0.0,
            "mean_exact_matched_count": 0.0,
        }
    deltas = [row["coverage_delta"] for row in rows]
    return {
        "topic_count": len(rows),
        "topics_expanded_better": sum(1 for d in deltas if d > 0),
        "topics_exact_better": sum(1 for d in deltas if d < 0),
        "topics_tied": sum(1 for d in deltas if d == 0),
        "mean_coverage_delta": mean(deltas),
        "median_coverage_delta": median(deltas),
        "mean_expanded_coverage": mean(row["expanded"]["coverage"] for row in rows),
        "mean_exact_coverage": mean(row["exact"]["coverage"] for row in rows),
        "mean_expanded_matched_count": mean(row["expanded"]["matched_count"] for row in rows),
        "mean_exact_matched_count": mean(row["exact"]["matched_count"] for row in rows),
    }


async def run_probe(
    topics: Sequence[str],
    *,
    per_query_results: int,
    target_count: int,
    year_start: int | None,
    year_end: int | None,
) -> Dict[str, Any]:
    module = load_collector_module()
    searcher = module.ArxivSearcher(rate_limit_delay=3.0)
    rows: List[Dict[str, Any]] = []
    per_topic_details: List[Dict[str, Any]] = []

    for topic in topics:
        variants = QUERY_VARIANTS.get(topic, [(topic, 1.0)])
        variant_results: Dict[str, Sequence[Any]] = {}
        variant_weights = {query: weight for query, weight in variants}
        for query, _weight in variants:
            variant_results[query] = await searcher.search(
                query=query,
                max_results=per_query_results,
                year_start=year_start,
                year_end=year_end,
            )
        selected = merge_variant_results(
            variant_results,
            variant_weights=variant_weights,
            target_count=target_count,
        )
        # Same-budget exact-topic baseline. The first variant may use a smaller
        # per-query budget, so run the raw topic again with target_count to avoid
        # comparing expanded@target_count against exact@per_query_results.
        exact_papers = await searcher.search(
            query=topic,
            max_results=target_count,
            year_start=year_start,
            year_end=year_end,
        )
        benchmark_refs = load_benchmark_refs(topic)
        row = build_comparison_row(
            topic=topic,
            benchmark_refs=benchmark_refs,
            expanded_refs=[item["arxiv_id"] for item in selected],
            exact_refs=[paper_arxiv_id(p) for p in exact_papers if paper_arxiv_id(p)],
            expanded_raw_count=sum(len(papers) for papers in variant_results.values()),
            exact_raw_count=len(exact_papers),
        )
        rows.append(row)
        per_topic_details.append(
            {
                "topic": topic,
                "variants": [{"query": q, "weight": w, "raw_count": len(variant_results[q])} for q, w in variants],
                "selected": selected,
            }
        )

    return {
        "experiment_type": "surveybench_query_expansion_probe",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope_note": (
            "Live collection-stage SurveyBench-facing probe. It uses fixed, human-written query variants, arXiv metadata search, "
            "no LLM keyword expansion, no embedding/LLM filtering, no PDF download, and no survey generation. "
            "The metric is date-filtered arXiv-ID overlap with local SurveyBench reference targets."
        ),
        "topics": list(topics),
        "per_query_results": per_query_results,
        "target_count": target_count,
        "rows": rows,
        "details": per_topic_details,
        "aggregate": summarize_rows(rows),
    }


def build_markdown(payload: Dict[str, Any]) -> str:
    agg = payload["aggregate"]
    lines = [
        "# SurveyBench Query-Expansion Collection Probe",
        "",
        "- Scope: live collection-stage probe only; no full survey generation.",
        "- Retrieval rule: fixed human-written query variants over arXiv; no LLM keyword expansion, no PDF download.",
        "- Scoring rule: date-filtered arXiv-ID overlap with local SurveyBench reference targets.",
        "",
        f"- Topics: {agg['topic_count']}",
        f"- Mean expanded coverage: {agg['mean_expanded_coverage']:.3f}",
        f"- Mean exact coverage: {agg['mean_exact_coverage']:.3f}",
        f"- Mean coverage delta: {agg['mean_coverage_delta']:.3f}",
        f"- Expanded / exact / tied topics: {agg['topics_expanded_better']} / {agg['topics_exact_better']} / {agg['topics_tied']}",
        "",
        "| Topic | Expanded matched | Expanded cov. | Exact matched | Exact cov. | Delta |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| {row['topic']} | {row['expanded']['matched_count']} | {row['expanded']['coverage']:.3f} | "
            f"{row['exact']['matched_count']} | {row['exact']['coverage']:.3f} | {row['coverage_delta']:.3f} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def write_outputs(payload: Dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "surveybench_query_expansion_probe.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "surveybench_query_expansion_probe.md").write_text(
        build_markdown(payload),
        encoding="utf-8",
    )
    with (out_dir / "surveybench_query_expansion_probe_rows.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "topic",
                "expanded_matched",
                "expanded_coverage",
                "exact_matched",
                "exact_coverage",
                "coverage_delta",
                "matched_delta",
            ],
        )
        writer.writeheader()
        for row in payload["rows"]:
            writer.writerow(
                {
                    "topic": row["topic"],
                    "expanded_matched": row["expanded"]["matched_count"],
                    "expanded_coverage": f"{row['expanded']['coverage']:.6f}",
                    "exact_matched": row["exact"]["matched_count"],
                    "exact_coverage": f"{row['exact']['coverage']:.6f}",
                    "coverage_delta": f"{row['coverage_delta']:.6f}",
                    "matched_delta": row["matched_delta"],
                }
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fixed-query SurveyBench arXiv collection probe")
    parser.add_argument("--topic", action="append", default=[], help="Topic override; repeatable")
    parser.add_argument("--per-query-results", type=int, default=12)
    parser.add_argument("--target-count", type=int, default=30)
    parser.add_argument("--year-start", type=int, default=None)
    parser.add_argument("--year-end", type=int, default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    topics = args.topic or DEFAULT_TOPICS
    payload = asyncio.run(
        run_probe(
            topics,
            per_query_results=args.per_query_results,
            target_count=args.target_count,
            year_start=args.year_start,
            year_end=args.year_end,
        )
    )
    out_dir = Path(args.output_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    write_outputs(payload, out_dir)
    print(f"Wrote outputs to {out_dir}")
    print(build_markdown(payload))


if __name__ == "__main__":
    main()
