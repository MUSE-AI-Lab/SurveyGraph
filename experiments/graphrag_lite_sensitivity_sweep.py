from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import graphrag_lite_matched_baseline as lite
from experiments import offline_real_revision_audit as audit
from experiments import review_response_audit as review

OUTPUT_DIR = ROOT / "outputs" / "graphrag_lite_sensitivity_sweep_20260526"


def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _load_runs() -> list[audit.RunBundle]:
    runs: list[audit.RunBundle] = []
    for run in audit.load_archived_runs():
        target_info = review.collect_survey_reference_targets(run)
        if len(target_info["external_target_ids"]) >= 3:
            runs.append(run)
    return runs


def _evaluate_flat_for_run(run: audit.RunBundle) -> Dict[str, Any]:
    target_info = review.collect_survey_reference_targets(run)
    target_ids = {audit.sanitize_key(pid) for pid in target_info["external_target_ids"]}
    context = audit.build_retrieval_context(run)
    papers = context["papers"]
    paper_map = context["paper_map"]
    idf = context["idf"]
    flat_rank = audit.make_flat_ranker(papers, idf)
    full_adj, full_pairs = audit.build_adjacency(run, paper_map)
    return lite._evaluate_ranker(
        run,
        flat_rank,
        target_ids=target_ids,
        full_pairs=full_pairs,
        active_pairs=set(),
    )


def _evaluate_setting_for_run(
    run: audit.RunBundle,
    top_neighbors: int,
    min_similarity: float,
) -> Dict[str, Any]:
    target_info = review.collect_survey_reference_targets(run)
    target_ids = {audit.sanitize_key(pid) for pid in target_info["external_target_ids"]}
    context = audit.build_retrieval_context(run)
    papers = context["papers"]
    paper_map = context["paper_map"]
    idf = context["idf"]
    _full_adj, full_pairs = audit.build_adjacency(run, paper_map)
    lite_adj, lite_pairs = lite._build_tfidf_knn_graph(
        papers,
        top_neighbors=top_neighbors,
        min_similarity=min_similarity,
    )
    ranker = lite._graph_ranker_from_adjacency(papers, paper_map, idf, lite_adj)
    row = lite._evaluate_ranker(
        run,
        ranker,
        target_ids=target_ids,
        full_pairs=full_pairs,
        active_pairs=lite_pairs,
    )
    row["active_relation_count"] = len(lite_pairs)
    return row


def _aggregate_rows(rows: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    return {
        "topic_count": len(rows),
        "mean_recall_top5": _mean(row["external_proxy_recall_top5"] for row in rows),
        "mean_precision_top5": _mean(row["external_proxy_precision_top5"] for row in rows),
        "mean_mekg_density_top5": _mean(row["relation_density_top5"] for row in rows),
        "mean_active_graph_density_top5": _mean(row["active_graph_density_top5"] for row in rows),
        "mean_unique_papers_top5": _mean(row["unique_papers_top5"] for row in rows),
        "mean_active_relations": _mean(row.get("active_relation_count", 0) for row in rows),
        "mean_retrieval_seconds": _mean(row["retrieval_seconds"] for row in rows),
    }


def build_sweep(
    neighbor_values: Sequence[int] = (2, 3, 5, 8),
    min_similarity_values: Sequence[float] = (0.00, 0.05, 0.10, 0.15),
) -> Dict[str, Any]:
    runs = _load_runs()
    flat_rows = [_evaluate_flat_for_run(run) for run in runs]
    flat_baseline = _aggregate_rows(flat_rows)
    flat_baseline["mean_active_relations"] = 0.0

    settings: List[Dict[str, Any]] = []
    per_setting_topics: Dict[str, List[Dict[str, Any]]] = {}
    for top_neighbors in neighbor_values:
        for min_similarity in min_similarity_values:
            rows = [
                _evaluate_setting_for_run(run, top_neighbors, min_similarity)
                for run in runs
            ]
            agg = _aggregate_rows(rows)
            setting = {
                "top_neighbors": top_neighbors,
                "min_similarity": float(min_similarity),
                **agg,
                "delta_recall_vs_flat": agg["mean_recall_top5"] - flat_baseline["mean_recall_top5"],
                "delta_precision_vs_flat": agg["mean_precision_top5"] - flat_baseline["mean_precision_top5"],
                "delta_mekg_density_vs_flat": agg["mean_mekg_density_top5"] - flat_baseline["mean_mekg_density_top5"],
            }
            key = f"k{top_neighbors}_sim{min_similarity:.2f}"
            settings.append(setting)
            per_setting_topics[key] = rows

    best_by_recall = max(settings, key=lambda r: (r["mean_recall_top5"], r["mean_precision_top5"]))
    candidates = [
        row
        for row in settings
        if row["mean_recall_top5"] >= flat_baseline["mean_recall_top5"]
        and row["mean_active_relations"] <= 1.25 * best_by_recall["mean_active_relations"]
    ]
    recommended = max(
        candidates or settings,
        key=lambda r: (r["mean_recall_top5"], r["mean_mekg_density_top5"], -r["mean_active_relations"]),
    )

    return {
        "experiment_type": "graphrag_lite_sensitivity_sweep",
        "scope_note": (
            "Parameter sensitivity sweep for the TF-IDF kNN GraphRAG-lite baseline. "
            "It varies kNN degree and minimum cosine similarity while holding the archived runs, "
            "section budget, candidate paper pools, and survey-reference external proxy fixed."
        ),
        "run_count": len(runs),
        "setting_count": len(settings),
        "neighbor_values": list(neighbor_values),
        "min_similarity_values": [float(x) for x in min_similarity_values],
        "flat_baseline": flat_baseline,
        "settings": settings,
        "best_by_recall": best_by_recall,
        "recommended_balanced": recommended,
    }


def build_markdown(payload: Dict[str, Any]) -> str:
    flat = payload["flat_baseline"]
    lines = [
        "# GraphRAG-lite Sensitivity Sweep",
        "",
        f"- Runs used: {payload['run_count']}",
        f"- Settings: {payload['setting_count']}",
        f"- Flat baseline R@5/P@5/density: {flat['mean_recall_top5']:.3f} / "
        f"{flat['mean_precision_top5']:.3f} / {flat['mean_mekg_density_top5']:.3f}",
        "",
        "| k | min sim | R@5 | P@5 | MEKG density | Active density | Active rels | ΔR vs flat |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(payload["settings"], key=lambda r: (r["top_neighbors"], r["min_similarity"])):
        lines.append(
            f"| {row['top_neighbors']} | {row['min_similarity']:.2f} | "
            f"{row['mean_recall_top5']:.3f} | {row['mean_precision_top5']:.3f} | "
            f"{row['mean_mekg_density_top5']:.3f} | {row['mean_active_graph_density_top5']:.3f} | "
            f"{row['mean_active_relations']:.1f} | {row['delta_recall_vs_flat']:.3f} |"
        )
    best = payload["best_by_recall"]
    rec = payload["recommended_balanced"]
    lines += [
        "",
        f"- Best by recall: k={best['top_neighbors']}, min_sim={best['min_similarity']:.2f}, "
        f"R@5={best['mean_recall_top5']:.3f}, P@5={best['mean_precision_top5']:.3f}.",
        f"- Recommended balanced setting: k={rec['top_neighbors']}, min_sim={rec['min_similarity']:.2f}, "
        f"R@5={rec['mean_recall_top5']:.3f}, active rels={rec['mean_active_relations']:.1f}.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_sweep()
    (OUTPUT_DIR / "graphrag_lite_sensitivity_sweep.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "graphrag_lite_sensitivity_sweep.md").write_text(
        build_markdown(payload),
        encoding="utf-8",
    )
    print(f"Wrote outputs to {OUTPUT_DIR}")
    print((OUTPUT_DIR / "graphrag_lite_sensitivity_sweep.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
