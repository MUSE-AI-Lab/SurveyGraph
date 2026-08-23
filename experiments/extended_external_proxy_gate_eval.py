from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit
from experiments import review_response_audit as review
from experiments.semantic_edge_stratified_protocol_audit import _iter_semantic_rows


OUTPUT_DIR = ROOT / "outputs" / "extended_external_proxy_gate_eval_20260526"

MODES = (
    "flat",
    "structural_only",
    "semantic_only",
    "no_support",
    "full",
    "supported_or_partial_gate",
    "supported_only_gate",
)


def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _semantic_label_index() -> Dict[Tuple[str, str, str, str], str]:
    """Index deterministic protocol labels for archived semantic edges."""

    labels: Dict[Tuple[str, str, str, str], str] = {}
    for row in _iter_semantic_rows():
        labels[
            (
                row["run_id"],
                row["relation_type"],
                row["source_title"],
                row["target_title"],
            )
        ] = row["protocol_label"]
    return labels


def _allowed_relation_types_for_mode(mode: str) -> frozenset[str] | None:
    if mode in {"full", "supported_or_partial_gate", "supported_only_gate"}:
        return None
    if mode == "no_support":
        return audit.RELATION_FAMILY_VARIANTS["no_support"]
    if mode == "structural_only":
        return audit.RELATION_FAMILY_VARIANTS["structural_only"]
    if mode == "semantic_only":
        return audit.RELATION_FAMILY_VARIANTS["semantic_only"]
    raise ValueError(f"mode has no relation inventory: {mode}")


def build_adjacency_for_mode(
    run: audit.RunBundle,
    paper_map: Dict[str, Dict[str, Any]],
    semantic_labels: Dict[Tuple[str, str, str, str], str],
    mode: str,
) -> Tuple[Dict[str, List[Tuple[str, float, str]]], set[Tuple[str, str]], Dict[str, int]]:
    """Build an undirected retrieval adjacency with optional semantic evidence gating."""

    if mode == "flat":
        return defaultdict(list), set(), {
            "active_relation_count": 0,
            "nonsemantic_kept": 0,
            "semantic_total": 0,
            "semantic_kept": 0,
            "semantic_dropped": 0,
        }

    allowed_rel_types = _allowed_relation_types_for_mode(mode)
    adjacency: Dict[str, List[Tuple[str, float, str]]] = defaultdict(list)
    undirected_pairs: set[Tuple[str, str]] = set()
    counts = {
        "active_relation_count": 0,
        "nonsemantic_kept": 0,
        "semantic_total": 0,
        "semantic_kept": 0,
        "semantic_dropped": 0,
    }

    for rel in run.mekg.get("relations", []):
        rel_type = rel.get("type", "")
        if allowed_rel_types is not None and rel_type not in allowed_rel_types:
            continue

        src = audit.sanitize_key(rel.get("source", ""))
        tgt = audit.sanitize_key(rel.get("target", ""))
        if src not in paper_map or tgt not in paper_map:
            continue

        keep = True
        if rel_type in audit.SEMANTIC_RELATIONS:
            counts["semantic_total"] += 1
            if mode in {"supported_or_partial_gate", "supported_only_gate"}:
                label = semantic_labels.get(
                    (
                        run.run_id,
                        rel_type,
                        paper_map[src].get("title", ""),
                        paper_map[tgt].get("title", ""),
                    )
                )
                if mode == "supported_or_partial_gate":
                    keep = label in {"supported", "partial"}
                else:
                    keep = label == "supported"
            if keep:
                counts["semantic_kept"] += 1
            else:
                counts["semantic_dropped"] += 1
        else:
            counts["nonsemantic_kept"] += 1

        if not keep:
            continue

        counts["active_relation_count"] += 1
        conf = float(rel.get("confidence", 0.5) or 0.5)
        adjacency[src].append((tgt, conf, rel_type))
        adjacency[tgt].append((src, conf, rel_type))
        undirected_pairs.add(tuple(sorted((src, tgt))))

    return adjacency, undirected_pairs, counts


def evaluate_ranker(
    run: audit.RunBundle,
    ranker,
    relation_pairs: set[tuple[str, str]],
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
            if tuple(sorted((unique_ids[i], unique_ids[j]))) in relation_pairs:
                linked_pairs += 1

    return {
        "sections_evaluated": len(section_rows),
        "unique_papers_top5": len(unique_ids),
        "hit_count_top5": len(hits),
        "external_proxy_recall_top5": len(hits) / len(target_ids) if target_ids else 0.0,
        "external_proxy_precision_top5": len(hits) / len(unique_ids) if unique_ids else 0.0,
        "relation_density_top5": linked_pairs / pair_total if pair_total else 0.0,
    }


def build_eval() -> Dict[str, Any]:
    semantic_labels = _semantic_label_index()
    per_run: List[Dict[str, Any]] = []

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
        flat_rank = audit.make_flat_ranker(papers, idf)
        full_adjacency, full_pairs, full_counts = build_adjacency_for_mode(
            run, paper_map, semantic_labels, "full"
        )

        mode_rows: Dict[str, Any] = {}
        for mode in MODES:
            if mode == "flat":
                # Flat retrieval is still scored for relation density against the full
                # archived MEKG, matching earlier baseline tables.
                metrics = evaluate_ranker(run, flat_rank, full_pairs, target_ids)
                counts = {
                    "active_relation_count": 0,
                    "nonsemantic_kept": 0,
                    "semantic_total": full_counts["semantic_total"],
                    "semantic_kept": 0,
                    "semantic_dropped": 0,
                }
            else:
                adjacency, relation_pairs, counts = build_adjacency_for_mode(
                    run, paper_map, semantic_labels, mode
                )
                graph_rank = audit.make_graph_ranker(
                    papers,
                    paper_map,
                    idf,
                    centrality,
                    adjacency,
                    max_hops=1,
                )
                metrics = evaluate_ranker(
                    run,
                    lambda title, desc, gr=graph_rank: gr(title, desc)[0],
                    relation_pairs,
                    target_ids,
                )
            mode_rows[mode] = {**metrics, "edge_counts": counts}

        per_run.append(
            {
                "run_id": run.run_id,
                "label": run.label,
                "external_proxy_target_size": len(target_ids),
                "source_survey_count": target_info["source_survey_count"],
                "modes": mode_rows,
            }
        )

    aggregate: Dict[str, Any] = {}
    for mode in MODES:
        rows = [row["modes"][mode] for row in per_run]
        aggregate[mode] = {
            "mean_recall_top5": _mean(r["external_proxy_recall_top5"] for r in rows),
            "mean_precision_top5": _mean(r["external_proxy_precision_top5"] for r in rows),
            "mean_relation_density_top5": _mean(r["relation_density_top5"] for r in rows),
            "mean_unique_papers_top5": _mean(r["unique_papers_top5"] for r in rows),
            "mean_active_relations": _mean(r["edge_counts"]["active_relation_count"] for r in rows),
            "mean_semantic_kept": _mean(r["edge_counts"]["semantic_kept"] for r in rows),
            "mean_semantic_dropped": _mean(r["edge_counts"]["semantic_dropped"] for r in rows),
        }

    return {
        "experiment_type": "extended_external_proxy_gate_eval",
        "scope_note": (
            "Seven-run local replay against survey-reference external-proxy targets. "
            "It combines relation-family ablations with deterministic semantic evidence gates under the same top-5 "
            "section budget. The target remains a weak archive-internal survey-reference proxy, not a public benchmark."
        ),
        "modes": list(MODES),
        "run_count": len(per_run),
        "top_k_per_section": 5,
        "per_run": per_run,
        "aggregate": aggregate,
        "paired_supported_or_partial_vs_full_recall": audit.exact_paired_sign_flip_test(
            row["modes"]["supported_or_partial_gate"]["external_proxy_recall_top5"]
            - row["modes"]["full"]["external_proxy_recall_top5"]
            for row in per_run
        ),
        "paired_supported_or_partial_vs_structural_recall": audit.exact_paired_sign_flip_test(
            row["modes"]["supported_or_partial_gate"]["external_proxy_recall_top5"]
            - row["modes"]["structural_only"]["external_proxy_recall_top5"]
            for row in per_run
        ),
        "paired_semantic_only_vs_full_density": audit.exact_paired_sign_flip_test(
            row["modes"]["semantic_only"]["relation_density_top5"]
            - row["modes"]["full"]["relation_density_top5"]
            for row in per_run
        ),
    }


def build_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Extended External-Proxy Semantic-Gate / Relation-Family Replay",
        "",
        f"- Runs used: {payload['run_count']}",
        f"- Top-k per section: {payload['top_k_per_section']}",
        "",
        "| Mode | R@5 | P@5 | Density | Unique papers | Active rels | Sem. kept | Sem. dropped |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        row = payload["aggregate"][mode]
        lines.append(
            f"| {mode} | {row['mean_recall_top5']:.3f} | {row['mean_precision_top5']:.3f} | "
            f"{row['mean_relation_density_top5']:.3f} | {row['mean_unique_papers_top5']:.1f} | "
            f"{row['mean_active_relations']:.1f} | {row['mean_semantic_kept']:.1f} | "
            f"{row['mean_semantic_dropped']:.1f} |"
        )
    lines.extend(
        [
            "",
            "> This is a retrieval-stage external-proxy replay only. It tests whether deterministic edge gates alter "
            "top-k retrieval behavior; it does not regenerate surveys or replace public benchmark evaluation.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_eval()
    (OUTPUT_DIR / "extended_external_proxy_gate_eval.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "extended_external_proxy_gate_eval.md").write_text(
        build_markdown(payload),
        encoding="utf-8",
    )
    print(f"Wrote outputs to {OUTPUT_DIR}")
    print((OUTPUT_DIR / "extended_external_proxy_gate_eval.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
