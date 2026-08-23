from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit
from experiments import review_response_audit as review
from experiments.extended_external_proxy_gate_eval import (
    build_adjacency_for_mode,
    evaluate_ranker,
    _semantic_label_index,
)


OUTPUT_DIR = ROOT / "outputs" / "retrieval_quality_cost_tradeoff_20260526"
VARIANTS = ("flat", "structural_only", "full", "supported_or_partial_gate", "supported_only_gate")


def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def build_tradeoff() -> Dict[str, Any]:
    semantic_labels = _semantic_label_index()
    per_run: List[Dict[str, Any]] = []

    for run in audit.load_archived_runs():
        target_info = review.collect_survey_reference_targets(run)
        target_ids = {audit.sanitize_key(pid) for pid in target_info["external_target_ids"]}
        if len(target_ids) < 3:
            continue

        t0 = time.perf_counter()
        context = audit.build_retrieval_context(run)
        context_seconds = time.perf_counter() - t0
        papers = context["papers"]
        paper_map = context["paper_map"]
        idf = context["idf"]
        centrality = context["centrality"]
        flat_rank = audit.make_flat_ranker(papers, idf)

        full_adj, full_pairs, full_counts = build_adjacency_for_mode(run, paper_map, semantic_labels, "full")

        variant_rows: Dict[str, Any] = {}
        for variant in VARIANTS:
            if variant == "flat":
                t_eval = time.perf_counter()
                metrics = evaluate_ranker(run, flat_rank, full_pairs, target_ids)
                retrieval_seconds = time.perf_counter() - t_eval
                counts = {
                    "active_relation_count": 0,
                    "semantic_total": full_counts["semantic_total"],
                    "semantic_kept": 0,
                    "semantic_dropped": 0,
                    "nonsemantic_kept": 0,
                }
                graph_prep_seconds = 0.0
            else:
                t_prep = time.perf_counter()
                adjacency, pairs, counts = build_adjacency_for_mode(run, paper_map, semantic_labels, variant)
                ranker = audit.make_graph_ranker(papers, paper_map, idf, centrality, adjacency, max_hops=1)
                graph_prep_seconds = time.perf_counter() - t_prep
                t_eval = time.perf_counter()
                metrics = evaluate_ranker(run, lambda title, desc, gr=ranker: gr(title, desc)[0], pairs, target_ids)
                retrieval_seconds = time.perf_counter() - t_eval

            variant_rows[variant] = {
                **metrics,
                "context_seconds": context_seconds,
                "graph_prep_seconds": graph_prep_seconds,
                "retrieval_seconds": retrieval_seconds,
                "total_local_seconds": context_seconds + graph_prep_seconds + retrieval_seconds,
                "edge_counts": counts,
            }

        per_run.append(
            {
                "run_id": run.run_id,
                "label": run.label,
                "paper_count": len(run.mekg.get("papers", [])),
                "external_proxy_target_size": len(target_ids),
                "variants": variant_rows,
            }
        )

    aggregate: Dict[str, Any] = {}
    for variant in VARIANTS:
        rows = [row["variants"][variant] for row in per_run]
        aggregate[variant] = {
            "mean_recall_top5": _mean(r["external_proxy_recall_top5"] for r in rows),
            "mean_precision_top5": _mean(r["external_proxy_precision_top5"] for r in rows),
            "mean_relation_density_top5": _mean(r["relation_density_top5"] for r in rows),
            "mean_unique_papers_top5": _mean(r["unique_papers_top5"] for r in rows),
            "mean_active_relations": _mean(r["edge_counts"]["active_relation_count"] for r in rows),
            "mean_semantic_dropped": _mean(r["edge_counts"]["semantic_dropped"] for r in rows),
            "mean_context_seconds": _mean(r["context_seconds"] for r in rows),
            "mean_graph_prep_seconds": _mean(r["graph_prep_seconds"] for r in rows),
            "mean_retrieval_seconds": _mean(r["retrieval_seconds"] for r in rows),
            "mean_total_local_seconds": _mean(r["total_local_seconds"] for r in rows),
        }

    return {
        "experiment_type": "retrieval_quality_cost_tradeoff",
        "scope_note": (
            "Local retrieval-stage quality/cost replay over seven survey-reference external-proxy runs. "
            "Timing covers artifact-local context construction, adjacency/gate preparation, and top-5 retrieval only; "
            "it does not include LLM relation induction or long-form generation."
        ),
        "variants": list(VARIANTS),
        "run_count": len(per_run),
        "per_run": per_run,
        "aggregate": aggregate,
    }


def build_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Retrieval-Stage Quality/Cost Tradeoff",
        "",
        f"- Runs used: {payload['run_count']}",
        "",
        "| Variant | R@5 | P@5 | Density | Active rels | Sem. dropped | Prep sec | Retrieval sec | Total local sec |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for variant in VARIANTS:
        row = payload["aggregate"][variant]
        lines.append(
            f"| {variant} | {row['mean_recall_top5']:.3f} | {row['mean_precision_top5']:.3f} | "
            f"{row['mean_relation_density_top5']:.3f} | {row['mean_active_relations']:.1f} | "
            f"{row['mean_semantic_dropped']:.1f} | {row['mean_graph_prep_seconds']:.4f} | "
            f"{row['mean_retrieval_seconds']:.4f} | {row['mean_total_local_seconds']:.4f} |"
        )
    lines.extend(
        [
            "",
            "> Timing is a local replay diagnostic. Full SurveyGraph generation remains dominated by LLM relation "
            "induction, section writing, and reflection rather than these post-hoc retrieval/gating steps.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_tradeoff()
    (OUTPUT_DIR / "retrieval_quality_cost_tradeoff.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "retrieval_quality_cost_tradeoff.md").write_text(
        build_markdown(payload),
        encoding="utf-8",
    )
    print(f"Wrote outputs to {OUTPUT_DIR}")
    print((OUTPUT_DIR / "retrieval_quality_cost_tradeoff.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
