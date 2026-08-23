from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit
from experiments import review_response_audit as review

OUTPUT_DIR = ROOT / "outputs" / "matched_simpler_graph_baseline_eval_20260526"
TARGET_TOPICS = (
    "Document Visual Question Answering",
    "Text-to-SQL Agent",
    "Large Language Model Function Calling",
    "Memory in the Age of AI Agents",
)


def _load_runs() -> List[audit.RunBundle]:
    return [run for run in audit.load_archived_runs() if run.label in TARGET_TOPICS]


def _evaluate_ranker(
    run: audit.RunBundle,
    ranker,
    undirected_relation_pairs: set[tuple[str, str]],
    target_ids: set[str],
    top_k: int = 5,
) -> Dict[str, Any]:
    union_ids: List[str] = []
    section_rows: List[Dict[str, Any]] = []
    for section in run.outline.get("sections", []):
        title = section.get("title", "")
        if title in audit.SECTION_EXCLUDE_TITLES:
            continue
        ranked = ranker(title, section.get("description", ""))
        chosen = [pid for pid, _ in ranked[:top_k]]
        union_ids.extend(chosen)
        section_rows.append({"title": title, "top_k_ids": chosen})

    unique_ids = list(dict.fromkeys(union_ids))
    hits = set(unique_ids) & target_ids

    pair_total = 0
    linked_pairs = 0
    for i in range(len(unique_ids)):
        for j in range(i + 1, len(unique_ids)):
            pair_total += 1
            if tuple(sorted((unique_ids[i], unique_ids[j]))) in undirected_relation_pairs:
                linked_pairs += 1

    return {
        "sections_evaluated": len(section_rows),
        "unique_papers_top5": len(unique_ids),
        "hit_count_top5": len(hits),
        "external_proxy_recall_top5": len(hits) / len(target_ids) if target_ids else 0.0,
        "external_proxy_precision_top5": len(hits) / len(unique_ids) if unique_ids else 0.0,
        "relation_density_top5": linked_pairs / pair_total if pair_total else 0.0,
    }


def build_summary() -> Dict[str, Any]:
    topics: List[Dict[str, Any]] = []

    for run in _load_runs():
        target_info = review.collect_survey_reference_targets(run)
        target_ids = {audit.sanitize_key(pid) for pid in target_info["external_target_ids"]}
        if len(target_ids) < 3:
            continue

        context = audit.build_retrieval_context(run)
        papers = context["papers"]
        paper_map = context["paper_map"]
        idf = context["idf"]
        centrality = context["centrality"]

        flat_rank = audit.make_flat_ranker(papers, idf)
        full_adjacency, full_pairs = audit.build_adjacency(run, paper_map)
        simple_allowed = audit.RELATION_FAMILY_VARIANTS["structural_only"]
        simple_adjacency, simple_pairs = audit.build_adjacency(
            run,
            paper_map,
            allowed_rel_types=simple_allowed,
        )

        simple_rank = audit.make_graph_ranker(
            papers,
            paper_map,
            idf,
            centrality,
            simple_adjacency,
            max_hops=1,
        )
        full_rank = audit.make_graph_ranker(
            papers,
            paper_map,
            idf,
            centrality,
            full_adjacency,
            max_hops=1,
        )

        flat = _evaluate_ranker(run, flat_rank, full_pairs, target_ids)
        simple_graph = _evaluate_ranker(
            run,
            lambda title, desc: simple_rank(title, desc)[0],
            simple_pairs,
            target_ids,
        )
        full_graph = _evaluate_ranker(
            run,
            lambda title, desc: full_rank(title, desc)[0],
            full_pairs,
            target_ids,
        )

        topics.append(
            {
                "topic": run.label,
                "run_id": run.run_id,
                "external_proxy_target_size": len(target_ids),
                "source_survey_count": target_info["source_survey_count"],
                "active_relation_count": {
                    "simple_graph": sum(
                        1
                        for rel in run.mekg.get("relations", [])
                        if rel.get("type", "") in simple_allowed
                    ),
                    "full_graph": len(run.mekg.get("relations", [])),
                },
                "flat": flat,
                "simple_graph": simple_graph,
                "full_graph": full_graph,
                "delta_vs_flat": {
                    "simple_graph_recall_top5": simple_graph["external_proxy_recall_top5"] - flat["external_proxy_recall_top5"],
                    "full_graph_recall_top5": full_graph["external_proxy_recall_top5"] - flat["external_proxy_recall_top5"],
                    "simple_graph_density_top5": simple_graph["relation_density_top5"] - flat["relation_density_top5"],
                    "full_graph_density_top5": full_graph["relation_density_top5"] - flat["relation_density_top5"],
                },
                "delta_vs_simple_graph": {
                    "full_graph_recall_top5": full_graph["external_proxy_recall_top5"] - simple_graph["external_proxy_recall_top5"],
                    "full_graph_precision_top5": full_graph["external_proxy_precision_top5"] - simple_graph["external_proxy_precision_top5"],
                    "full_graph_density_top5": full_graph["relation_density_top5"] - simple_graph["relation_density_top5"],
                },
            }
        )

    flat_recalls = [row["flat"]["external_proxy_recall_top5"] for row in topics]
    simple_recalls = [row["simple_graph"]["external_proxy_recall_top5"] for row in topics]
    full_recalls = [row["full_graph"]["external_proxy_recall_top5"] for row in topics]
    flat_precisions = [row["flat"]["external_proxy_precision_top5"] for row in topics]
    simple_precisions = [row["simple_graph"]["external_proxy_precision_top5"] for row in topics]
    full_precisions = [row["full_graph"]["external_proxy_precision_top5"] for row in topics]
    flat_density = [row["flat"]["relation_density_top5"] for row in topics]
    simple_density = [row["simple_graph"]["relation_density_top5"] for row in topics]
    full_density = [row["full_graph"]["relation_density_top5"] for row in topics]

    return {
        "experiment_type": "matched_simpler_graph_baseline_eval",
        "scope_note": (
            "Four-topic matched replay against the weak survey-reference external proxy. "
            "This isolates whether the full typed MEKG improves over a simpler structural/meta graph "
            "under the same archived topic slices, retrieval budget, and 1-hop expansion policy."
        ),
        "matched_topics": list(TARGET_TOPICS),
        "topic_count": len(topics),
        "topics": topics,
        "aggregate": {
            "flat_mean_external_proxy_recall_top5": audit.mean(flat_recalls),
            "simple_graph_mean_external_proxy_recall_top5": audit.mean(simple_recalls),
            "full_graph_mean_external_proxy_recall_top5": audit.mean(full_recalls),
            "flat_mean_external_proxy_precision_top5": audit.mean(flat_precisions),
            "simple_graph_mean_external_proxy_precision_top5": audit.mean(simple_precisions),
            "full_graph_mean_external_proxy_precision_top5": audit.mean(full_precisions),
            "flat_mean_relation_density_top5": audit.mean(flat_density),
            "simple_graph_mean_relation_density_top5": audit.mean(simple_density),
            "full_graph_mean_relation_density_top5": audit.mean(full_density),
            "paired_full_vs_simple_external_proxy_recall_top5": audit.exact_paired_sign_flip_test(
                f - s for f, s in zip(full_recalls, simple_recalls)
            ),
            "paired_full_vs_flat_external_proxy_recall_top5": audit.exact_paired_sign_flip_test(
                f - b for f, b in zip(full_recalls, flat_recalls)
            ),
            "paired_simple_vs_flat_external_proxy_recall_top5": audit.exact_paired_sign_flip_test(
                s - b for s, b in zip(simple_recalls, flat_recalls)
            ),
        },
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_summary()
    (OUTPUT_DIR / "matched_simpler_graph_baseline_eval.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    agg = payload["aggregate"]
    lines = [
        "# Matched Simpler-Graph Baseline Eval",
        "",
        f"- Topics: {payload['topic_count']}",
        f"- Flat mean recall@5: {agg['flat_mean_external_proxy_recall_top5']:.3f}",
        f"- Simple-graph mean recall@5: {agg['simple_graph_mean_external_proxy_recall_top5']:.3f}",
        f"- Full-graph mean recall@5: {agg['full_graph_mean_external_proxy_recall_top5']:.3f}",
        f"- Flat mean relation density: {agg['flat_mean_relation_density_top5']:.3f}",
        f"- Simple-graph mean relation density: {agg['simple_graph_mean_relation_density_top5']:.3f}",
        f"- Full-graph mean relation density: {agg['full_graph_mean_relation_density_top5']:.3f}",
        "",
        "| Topic | Flat recall@5 | Simple recall@5 | Full recall@5 | Flat density | Simple density | Full density |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["topics"]:
        lines.append(
            f"| {row['topic']} | "
            f"{row['flat']['external_proxy_recall_top5']:.3f} | "
            f"{row['simple_graph']['external_proxy_recall_top5']:.3f} | "
            f"{row['full_graph']['external_proxy_recall_top5']:.3f} | "
            f"{row['flat']['relation_density_top5']:.3f} | "
            f"{row['simple_graph']['relation_density_top5']:.3f} | "
            f"{row['full_graph']['relation_density_top5']:.3f} |"
        )
    (OUTPUT_DIR / "matched_simpler_graph_baseline_eval.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
