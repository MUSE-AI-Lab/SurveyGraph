
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

OUTPUT_DIR = ROOT / "outputs" / "external_proxy_relation_family_ablation_20260525"


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
    per_run: List[Dict[str, Any]] = []
    variant_names = list(audit.RELATION_FAMILY_VARIANTS.keys())

    for run in audit.load_archived_runs():
        target_info = review.collect_survey_reference_targets(run)
        target_ids = {audit.sanitize_key(pid) for pid in target_info["external_target_ids"]}
        if len(target_ids) < 3:
            continue

        context = audit.build_retrieval_context(run)
        papers = context["papers"]
        paper_map = context["paper_map"]
        idf = context["idf"]
        centrality = context["centrality"]

        variant_rows: Dict[str, Any] = {}
        for variant_name, allowed_rel_types in audit.RELATION_FAMILY_VARIANTS.items():
            adjacency, undirected_relation_pairs = audit.build_adjacency(run, paper_map, allowed_rel_types=allowed_rel_types)
            graph_rank = audit.make_graph_ranker(papers, paper_map, idf, centrality, adjacency, max_hops=1)
            metrics = _evaluate_ranker(
                run,
                lambda title, desc: graph_rank(title, desc)[0],
                undirected_relation_pairs,
                target_ids,
            )
            metrics["active_relation_count"] = sum(
                1 for rel in run.mekg.get("relations", [])
                if allowed_rel_types is None or rel.get("type", "") in allowed_rel_types
            )
            variant_rows[variant_name] = metrics

        per_run.append(
            {
                "run_id": run.run_id,
                "label": run.label,
                "external_target_size": len(target_ids),
                "source_survey_count": target_info["source_survey_count"],
                "variants": variant_rows,
            }
        )

    aggregate: Dict[str, Any] = {}
    for variant_name in variant_names:
        aggregate[variant_name] = {
            "external_proxy_recall_top5_mean": audit.mean(row["variants"][variant_name]["external_proxy_recall_top5"] for row in per_run),
            "external_proxy_precision_top5_mean": audit.mean(row["variants"][variant_name]["external_proxy_precision_top5"] for row in per_run),
            "relation_density_top5_mean": audit.mean(row["variants"][variant_name]["relation_density_top5"] for row in per_run),
            "active_relation_count_mean": audit.mean(row["variants"][variant_name]["active_relation_count"] for row in per_run),
        }

    pairwise_vs_full: Dict[str, Any] = {}
    for variant_name in variant_names:
        if variant_name == "full":
            continue
        deltas_recall = [
            row["variants"][variant_name]["external_proxy_recall_top5"] - row["variants"]["full"]["external_proxy_recall_top5"]
            for row in per_run
        ]
        deltas_precision = [
            row["variants"][variant_name]["external_proxy_precision_top5"] - row["variants"]["full"]["external_proxy_precision_top5"]
            for row in per_run
        ]
        deltas_density = [
            row["variants"][variant_name]["relation_density_top5"] - row["variants"]["full"]["relation_density_top5"]
            for row in per_run
        ]
        pairwise_vs_full[variant_name] = {
            "external_proxy_recall_top5": {
                "full_mean": aggregate["full"]["external_proxy_recall_top5_mean"],
                "variant_mean": aggregate[variant_name]["external_proxy_recall_top5_mean"],
                "delta_mean": audit.mean(deltas_recall),
                "paired_significance": audit.exact_paired_sign_flip_test(deltas_recall),
            },
            "external_proxy_precision_top5": {
                "full_mean": aggregate["full"]["external_proxy_precision_top5_mean"],
                "variant_mean": aggregate[variant_name]["external_proxy_precision_top5_mean"],
                "delta_mean": audit.mean(deltas_precision),
                "paired_significance": audit.exact_paired_sign_flip_test(deltas_precision),
            },
            "relation_density_top5": {
                "full_mean": aggregate["full"]["relation_density_top5_mean"],
                "variant_mean": aggregate[variant_name]["relation_density_top5_mean"],
                "delta_mean": audit.mean(deltas_density),
                "paired_significance": audit.exact_paired_sign_flip_test(deltas_density),
            },
        }

    return {
        "experiment_type": "external_proxy_relation_family_ablation",
        "scope_note": (
            "Seven-run replay of the 1-hop graph-aware section-to-paper ranker against the survey-reference external proxy target sets. "
            "Unlike the internal core-paper recall diagnostic, this ablation uses a less circular archive-external target and isolates "
            "how structural/meta versus semantic relation inventories affect top-5 recall, precision, and relation density."
        ),
        "runs_used": len(per_run),
        "variants": {
            "full": "All relation families enabled.",
            "no_support": "All relations except generic support edges.",
            "structural_only": "Generic support + structural/meta relations, without evolutionary semantic edges.",
            "semantic_only": "Only extends/improves/applies/refutes edges.",
        },
        "per_run": per_run,
        "aggregate": aggregate,
        "pairwise_vs_full": pairwise_vs_full,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_summary()
    (OUTPUT_DIR / "external_proxy_relation_family_ablation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# External-Proxy Relation-Family Ablation",
        "",
        f"- Runs used: {payload['runs_used']}",
        f"- Full-graph mean top-5 external proxy recall: {payload['aggregate']['full']['external_proxy_recall_top5_mean']:.3f}",
        f"- Structural-only mean top-5 external proxy recall: {payload['aggregate']['structural_only']['external_proxy_recall_top5_mean']:.3f}",
        f"- Semantic-only mean top-5 external proxy recall: {payload['aggregate']['semantic_only']['external_proxy_recall_top5_mean']:.3f}",
        "",
        "| Variant | Recall@5 | Precision@5 | Relation density | Active relations |",
        "|---|---:|---:|---:|---:|",
    ]
    for variant_name in ["full", "no_support", "structural_only", "semantic_only"]:
        agg = payload["aggregate"][variant_name]
        lines.append(
            f"| {variant_name} | {agg['external_proxy_recall_top5_mean']:.3f} | {agg['external_proxy_precision_top5_mean']:.3f} | {agg['relation_density_top5_mean']:.3f} | {agg['active_relation_count_mean']:.1f} |"
        )
    (OUTPUT_DIR / "external_proxy_relation_family_ablation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
