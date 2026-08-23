from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit
from experiments import review_response_audit as review
from experiments.semantic_edge_stratified_protocol_audit import _iter_semantic_rows

OUTPUT_DIR = ROOT / "outputs" / "semantic_evidence_gate_retrieval_eval_20260526"
TARGET_TOPICS = (
    "Document Visual Question Answering",
    "Text-to-SQL Agent",
    "Large Language Model Function Calling",
    "Memory in the Age of AI Agents",
)


def _semantic_label_index() -> Dict[Tuple[str, str, str, str], str]:
    idx: Dict[Tuple[str, str, str, str], str] = {}
    for row in _iter_semantic_rows():
        idx[
            (
                row["run_id"],
                row["relation_type"],
                row["source_title"],
                row["target_title"],
            )
        ] = row["protocol_label"]
    return idx


def _build_filtered_adjacency(
    run: audit.RunBundle,
    paper_map: Dict[str, Dict[str, Any]],
    semantic_labels: Dict[Tuple[str, str, str, str], str],
    mode: str,
) -> Tuple[Dict[str, List[Tuple[str, float, str]]], set[Tuple[str, str]], Dict[str, int]]:
    adjacency: Dict[str, List[Tuple[str, float, str]]] = defaultdict(list)
    pairs: set[Tuple[str, str]] = set()
    counts = {
        "nonsemantic_kept": 0,
        "semantic_kept": 0,
        "semantic_dropped": 0,
        "semantic_total": 0,
    }
    for rel in run.mekg.get("relations", []):
        rel_type = rel.get("type", "")
        src = audit.sanitize_key(rel.get("source", ""))
        tgt = audit.sanitize_key(rel.get("target", ""))
        if src not in paper_map or tgt not in paper_map:
            continue

        keep = True
        if mode == "structural_only" and rel_type in audit.SEMANTIC_RELATIONS:
            keep = False
        elif rel_type in audit.SEMANTIC_RELATIONS:
            counts["semantic_total"] += 1
            key = (
                run.run_id,
                rel_type,
                paper_map[src].get("title", ""),
                paper_map[tgt].get("title", ""),
            )
            label = semantic_labels.get(key)
            if mode == "supported_or_partial_gate":
                keep = label in {"supported", "partial"}
            elif mode == "supported_only_gate":
                keep = label == "supported"
            elif mode == "full":
                keep = True
            else:
                raise ValueError(f"unknown mode: {mode}")
            if keep:
                counts["semantic_kept"] += 1
            else:
                counts["semantic_dropped"] += 1
        else:
            counts["nonsemantic_kept"] += 1

        if not keep:
            continue
        conf = float(rel.get("confidence", 0.5) or 0.5)
        adjacency[src].append((tgt, conf, rel_type))
        adjacency[tgt].append((src, conf, rel_type))
        pairs.add(tuple(sorted((src, tgt))))
    return adjacency, pairs, counts


def _evaluate_ranker(
    run: audit.RunBundle,
    ranker,
    pairs: set[tuple[str, str]],
    target_ids: set[str],
    top_k: int = 5,
) -> Dict[str, Any]:
    union_ids: List[str] = []
    for section in run.outline.get("sections", []):
        title = section.get("title", "")
        if title in audit.SECTION_EXCLUDE_TITLES:
            continue
        ranked = ranker(title, section.get("description", ""))
        union_ids.extend([pid for pid, _ in ranked[:top_k]])
    unique_ids = list(dict.fromkeys(union_ids))
    hits = set(unique_ids) & target_ids
    pair_total = 0
    linked = 0
    for i in range(len(unique_ids)):
        for j in range(i + 1, len(unique_ids)):
            pair_total += 1
            if tuple(sorted((unique_ids[i], unique_ids[j]))) in pairs:
                linked += 1
    return {
        "unique_papers_top5": len(unique_ids),
        "hit_count_top5": len(hits),
        "external_proxy_recall_top5": len(hits) / len(target_ids) if target_ids else 0.0,
        "external_proxy_precision_top5": len(hits) / len(unique_ids) if unique_ids else 0.0,
        "relation_density_top5": linked / pair_total if pair_total else 0.0,
    }


def build_eval() -> Dict[str, Any]:
    semantic_labels = _semantic_label_index()
    modes = ("full", "supported_or_partial_gate", "supported_only_gate", "structural_only")
    topics: List[Dict[str, Any]] = []
    for run in audit.load_archived_runs():
        if run.label not in TARGET_TOPICS:
            continue
        target_info = review.collect_survey_reference_targets(run)
        target_ids = {audit.sanitize_key(pid) for pid in target_info["external_target_ids"]}
        if len(target_ids) < 3:
            continue
        context = audit.build_retrieval_context(run)
        papers = context["papers"]
        paper_map = context["paper_map"]
        idf = context["idf"]
        centrality = context["centrality"]

        mode_rows: Dict[str, Any] = {}
        for mode in modes:
            adjacency, pairs, counts = _build_filtered_adjacency(run, paper_map, semantic_labels, mode)
            ranker = audit.make_graph_ranker(papers, paper_map, idf, centrality, adjacency, max_hops=1)
            metrics = _evaluate_ranker(run, lambda t, d: ranker(t, d)[0], pairs, target_ids)
            mode_rows[mode] = {**metrics, "edge_counts": counts}

        topics.append(
            {
                "topic": run.label,
                "run_id": run.run_id,
                "external_proxy_target_size": len(target_ids),
                "source_survey_count": target_info["source_survey_count"],
                "modes": mode_rows,
            }
        )

    aggregate: Dict[str, Any] = {}
    for mode in modes:
        aggregate[mode] = {
            "mean_recall_top5": audit.mean(row["modes"][mode]["external_proxy_recall_top5"] for row in topics),
            "mean_precision_top5": audit.mean(row["modes"][mode]["external_proxy_precision_top5"] for row in topics),
            "mean_relation_density_top5": audit.mean(row["modes"][mode]["relation_density_top5"] for row in topics),
            "mean_unique_papers_top5": audit.mean(row["modes"][mode]["unique_papers_top5"] for row in topics),
            "mean_semantic_kept": audit.mean(row["modes"][mode]["edge_counts"]["semantic_kept"] for row in topics),
            "mean_semantic_dropped": audit.mean(row["modes"][mode]["edge_counts"]["semantic_dropped"] for row in topics),
        }

    return {
        "experiment_type": "semantic_evidence_gate_retrieval_eval",
        "scope_note": (
            "Four-topic matched retrieval replay where semantic edges are gated by the deterministic protocol labels "
            "from the stratified semantic-edge audit. Non-semantic edges are kept unless the structural-only mode is used. "
            "This tests whether adding a cheap evidence gate changes the same external-proxy retrieval picture."
        ),
        "topic_count": len(topics),
        "modes": list(modes),
        "topics": topics,
        "aggregate": aggregate,
        "paired_supported_or_partial_vs_full_recall": audit.exact_paired_sign_flip_test(
            row["modes"]["supported_or_partial_gate"]["external_proxy_recall_top5"]
            - row["modes"]["full"]["external_proxy_recall_top5"]
            for row in topics
        ),
        "paired_supported_only_vs_full_recall": audit.exact_paired_sign_flip_test(
            row["modes"]["supported_only_gate"]["external_proxy_recall_top5"]
            - row["modes"]["full"]["external_proxy_recall_top5"]
            for row in topics
        ),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_eval()
    (OUTPUT_DIR / "semantic_evidence_gate_retrieval_eval.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Semantic Evidence-Gate Retrieval Eval",
        "",
        f"- Topics: {payload['topic_count']}",
        "",
        "| Mode | Recall@5 | Precision@5 | Relation density | Unique papers | Semantic kept | Semantic dropped |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for mode, row in payload["aggregate"].items():
        lines.append(
            f"| {mode} | {row['mean_recall_top5']:.3f} | {row['mean_precision_top5']:.3f} | "
            f"{row['mean_relation_density_top5']:.3f} | {row['mean_unique_papers_top5']:.1f} | "
            f"{row['mean_semantic_kept']:.1f} | {row['mean_semantic_dropped']:.1f} |"
        )
    (OUTPUT_DIR / "semantic_evidence_gate_retrieval_eval.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote outputs to {OUTPUT_DIR}")
    print((OUTPUT_DIR / "semantic_evidence_gate_retrieval_eval.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
