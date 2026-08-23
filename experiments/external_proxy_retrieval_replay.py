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

OUTPUT_DIR = ROOT / "outputs" / "external_proxy_retrieval_replay_20260525"
TARGET_TOPICS = (
    "Document Visual Question Answering",
    "Text-to-SQL Agent",
)


def _load_runs() -> List[audit.RunBundle]:
    runs = []
    for run in audit.load_archived_runs():
        if run.label in TARGET_TOPICS:
            runs.append(run)
    return runs


def _evaluate_ranker(
    run: audit.RunBundle,
    ranker,
    context: Dict[str, Any],
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


def build_external_proxy_retrieval_replay_summary() -> Dict[str, Any]:
    topics: List[Dict[str, Any]] = []

    for run in _load_runs():
        target_info = review.collect_survey_reference_targets(run)
        target_ids = {audit.sanitize_key(pid) for pid in target_info["external_target_ids"]}

        context = audit.build_retrieval_context(run)
        papers = context["papers"]
        paper_map = context["paper_map"]
        idf = context["idf"]
        centrality = context["centrality"]
        adjacency, undirected_relation_pairs = audit.build_adjacency(run, paper_map)

        flat_rank = audit.make_flat_ranker(papers, idf)
        graph_rank = audit.make_graph_ranker(papers, paper_map, idf, centrality, adjacency, max_hops=1)
        no_expansion_rank = audit.make_graph_ranker(
            papers,
            paper_map,
            idf,
            centrality,
            adjacency,
            max_hops=0,
        )

        flat = _evaluate_ranker(run, flat_rank, context, undirected_relation_pairs, target_ids)
        graph = _evaluate_ranker(
            run,
            lambda title, desc: graph_rank(title, desc)[0],
            context,
            undirected_relation_pairs,
            target_ids,
        )
        no_expansion = _evaluate_ranker(
            run,
            lambda title, desc: no_expansion_rank(title, desc)[0],
            context,
            undirected_relation_pairs,
            target_ids,
        )

        topics.append(
            {
                "topic": run.label,
                "run_id": run.run_id,
                "external_proxy_target_size": len(target_ids),
                "source_survey_count": target_info["source_survey_count"],
                "flat": flat,
                "graph": graph,
                "no_expansion": no_expansion,
            }
        )

    flat_recalls = [row["flat"]["external_proxy_recall_top5"] for row in topics]
    graph_recalls = [row["graph"]["external_proxy_recall_top5"] for row in topics]
    noexp_recalls = [row["no_expansion"]["external_proxy_recall_top5"] for row in topics]
    flat_precisions = [row["flat"]["external_proxy_precision_top5"] for row in topics]
    graph_precisions = [row["graph"]["external_proxy_precision_top5"] for row in topics]
    noexp_precisions = [row["no_expansion"]["external_proxy_precision_top5"] for row in topics]
    flat_density = [row["flat"]["relation_density_top5"] for row in topics]
    graph_density = [row["graph"]["relation_density_top5"] for row in topics]
    noexp_density = [row["no_expansion"]["relation_density_top5"] for row in topics]

    return {
        "experiment_type": "external_proxy_retrieval_replay",
        "scope_note": (
            "Two-topic replay of the archived section-to-paper retrieval diagnostic against the survey-reference "
            "external proxy target sets already recovered from the repository. This is still a weak proxy rather "
            "than a public benchmark, but it directly tests whether 1-hop graph expansion helps on a less circular target."
        ),
        "topic_count": len(topics),
        "topics": topics,
        "aggregate": {
            "flat_mean_external_proxy_recall_top5": audit.mean(flat_recalls),
            "graph_mean_external_proxy_recall_top5": audit.mean(graph_recalls),
            "no_expansion_mean_external_proxy_recall_top5": audit.mean(noexp_recalls),
            "flat_mean_external_proxy_precision_top5": audit.mean(flat_precisions),
            "graph_mean_external_proxy_precision_top5": audit.mean(graph_precisions),
            "no_expansion_mean_external_proxy_precision_top5": audit.mean(noexp_precisions),
            "flat_mean_relation_density_top5": audit.mean(flat_density),
            "graph_mean_relation_density_top5": audit.mean(graph_density),
            "no_expansion_mean_relation_density_top5": audit.mean(noexp_density),
            "paired_graph_vs_flat_external_proxy_recall_top5": audit.exact_paired_sign_flip_test(
                g - f for g, f in zip(graph_recalls, flat_recalls)
            ),
            "paired_graph_vs_no_expansion_external_proxy_recall_top5": audit.exact_paired_sign_flip_test(
                g - n for g, n in zip(graph_recalls, noexp_recalls)
            ),
        },
    }


def write_outputs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_external_proxy_retrieval_replay_summary()
    (OUTPUT_DIR / "external_proxy_retrieval_replay.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    write_outputs()
    print(f"Wrote outputs to {OUTPUT_DIR}")
