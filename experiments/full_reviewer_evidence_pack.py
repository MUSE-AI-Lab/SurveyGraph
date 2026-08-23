from __future__ import annotations

import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit
from experiments import review_response_audit as review
from experiments.semantic_edge_stratified_protocol_audit import (
    build_audit as build_stratified_semantic_audit,
)

OUTPUT_DIR = ROOT / "outputs" / "full_reviewer_evidence_pack_20260526"
OPENALEX_MATCHES = ROOT / "outputs" / "openalex_citation_core_audit_20260525" / "openalex_title_matches.json"
TARGET_TOPICS = (
    "Document Visual Question Answering",
    "Text-to-SQL Agent",
    "Large Language Model Function Calling",
    "Memory in the Age of AI Agents",
)


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _safe_median(xs: Iterable[float]) -> float:
    xs = list(xs)
    return statistics.median(xs) if xs else 0.0


def _norm_title(s: str) -> str:
    return re.sub(r"\W+", " ", (s or "").lower()).strip()


def _paper_text(paper: Dict[str, Any], max_chars: int = 900) -> str:
    text = paper.get("abstract") or paper.get("md_text") or ""
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _sentence_with_cue(text: str, rel_type: str) -> str:
    cue_map = {
        "extends": r"\b(extend|extends|extended|extension|builds? upon|based on|follow[- ]?up|generaliz)\w*\b",
        "improves": r"\b(improv|outperform|better|enhanc|boost|gain|surpass|advance)\w*\b",
        "applies": r"\b(appl|use|deploy|adapt|transfer|employ|instantiate)\w*\b",
    }
    pat = re.compile(cue_map.get(rel_type, r"\b(method|approach|model)\b"), re.I)
    pieces = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text or "").strip())
    for sent in pieces:
        if pat.search(sent):
            return sent[:360]
    return (pieces[0] if pieces else "")[:360]


def build_snippet_level_semantic_examples() -> Dict[str, Any]:
    """Turn the deterministic semantic audit into reviewer-facing snippet examples.

    This is deliberately not labelled as a new human study. It samples from the
    existing archived MEKG records and shows what local textual evidence was
    available for pass/fail semantic edges.
    """

    stratified = build_stratified_semantic_audit()
    runs = {run.run_id: run for run in audit.load_archived_runs()}
    examples: List[Dict[str, Any]] = []
    wanted_labels = ("supported", "unsupported", "partial")
    per_key_seen: set[Tuple[str, str]] = set()

    # Prefer one supported and one unsupported case for each semantic type; add
    # partial cases where an unsupported row is not available.
    for rel_type in audit.SEMANTIC_RELATIONS:
        for label in wanted_labels:
            rows = [
                row
                for row in stratified["samples"]
                if row["relation_type"] == rel_type and row["protocol_label"] == label
            ]
            rows = sorted(
                rows,
                key=lambda r: (
                    0 if r.get("source_cue") else 1,
                    -float(r.get("matched_control_delta", 0.0)),
                    r.get("run_id", ""),
                    r.get("source_title", ""),
                ),
            )
            if not rows:
                continue
            row = rows[0]
            key = (rel_type, label)
            if key in per_key_seen:
                continue
            per_key_seen.add(key)
            run = runs[row["run_id"]]
            papers_by_title = {p.get("title", ""): p for p in run.mekg.get("papers", [])}
            source = papers_by_title.get(row["source_title"], {})
            target = papers_by_title.get(row["target_title"], {})
            source_text = _paper_text(source)
            target_text = _paper_text(target)
            examples.append(
                {
                    "relation_type": rel_type,
                    "protocol_label": label,
                    "failure_mode": row.get("failure_mode"),
                    "run_id": row["run_id"],
                    "topic": row["run_label"],
                    "source_title": row["source_title"],
                    "target_title": row["target_title"],
                    "source_year": row["source_year"],
                    "target_year": row["target_year"],
                    "confidence": row["confidence"],
                    "source_snippet": _sentence_with_cue(source_text, rel_type),
                    "target_snippet": _sentence_with_cue(target_text, rel_type),
                    "temporal_ok": row["temporal_ok"],
                    "source_cue": row["source_cue"],
                    "target_role_ok": row["target_role_ok"],
                    "matched_control_delta": row["matched_control_delta"],
                    "matched_control_title": row["matched_control_title"],
                }
            )

    return {
        "experiment_type": "snippet_level_semantic_edge_examples",
        "scope_note": (
            "Reviewer-facing examples sampled from the deterministic stratified semantic-edge audit. "
            "Snippets are extracted from repository-local title/abstract/fulltext fields and illustrate "
            "both passed and failed protocol cases; they are not additional human labels."
        ),
        "source_audit_overall": stratified["overall"],
        "source_audit_by_relation": stratified["by_relation"],
        "example_count": len(examples),
        "examples": examples,
    }


def _load_openalex_citation_map(run: audit.RunBundle, matches: Dict[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for p in run.mekg.get("papers", []):
        m = matches.get(_norm_title(p.get("title", "")), {})
        out[p["id"]] = int(m.get("cited_by_count") or 0)
    return out


def _score_components(run: audit.RunBundle, citation_map: Dict[str, int] | None = None) -> Dict[str, Dict[str, float]]:
    papers = run.mekg.get("papers", [])
    paper_map = {p["id"]: p for p in papers}
    graph = nx.DiGraph()
    graph.add_nodes_from(paper_map)
    for rel in run.mekg.get("relations", []):
        src, tgt = rel.get("source"), rel.get("target")
        if src in paper_map and tgt in paper_map:
            graph.add_edge(src, tgt)

    pagerank = nx.pagerank(graph, alpha=0.85) if graph.number_of_nodes() else {}
    if pagerank:
        mx, mn = max(pagerank.values()), min(pagerank.values())
        rng = mx - mn if mx != mn else 1.0
        pagerank = {pid: (v - mn) / rng for pid, v in pagerank.items()}

    citations: List[int] = []
    years: List[int] = []
    degrees: List[int] = []
    for pid in graph.nodes():
        p = paper_map[pid]
        c = citation_map.get(pid, 0) if citation_map is not None else p.get("citations", 0)
        if isinstance(c, (int, float)) and c >= 0:
            citations.append(int(c))
        y = p.get("year", 2024)
        if isinstance(y, int) and 1900 < y <= 2026:
            years.append(y)
        degrees.append(graph.in_degree(pid) + graph.out_degree(pid))

    max_c = max(citations) if citations else 1
    min_y = min(years) if years else 2014
    max_y = max(years) if years else 2026
    y_rng = max_y - min_y if max_y > min_y else 1
    max_d = max(degrees) if degrees else 1

    comps: Dict[str, Dict[str, float]] = {}
    for pid in graph.nodes():
        p = paper_map[pid]
        c = citation_map.get(pid, 0) if citation_map is not None else p.get("citations", 0)
        if not isinstance(c, (int, float)) or c < 0:
            c = 0
        y = p.get("year", 2024)
        if not isinstance(y, int) or y < 1900 or y > 2026:
            y = 2024
        d = graph.in_degree(pid) + graph.out_degree(pid)
        comps[pid] = {
            "pagerank": float(pagerank.get(pid, 0.0)),
            "citation": math.log1p(float(c)) / math.log1p(float(max_c)) if max_c > 0 else 0.0,
            "recency": (y - min_y) / y_rng if y_rng > 0 else 0.5,
            "degree": d / max_d if max_d > 0 else 0.0,
        }
    return comps


def _rank_from_components(
    comps: Dict[str, Dict[str, float]],
    weights: Dict[str, float],
    k: int,
) -> List[str]:
    scores = {
        pid: sum(weights.get(name, 0.0) * row.get(name, 0.0) for name in ("pagerank", "citation", "recency", "degree"))
        for pid, row in comps.items()
    }
    return [pid for pid, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]]


def build_core_score_calibration() -> Dict[str, Any]:
    matches = _load_json(OPENALEX_MATCHES) if OPENALEX_MATCHES.exists() else {}
    runs = audit.load_archived_runs()
    named_weights: Dict[str, Dict[str, float]] = {
        "default_hybrid": {"pagerank": 0.4, "citation": 0.3, "recency": 0.2, "degree": 0.1},
        "pure_pagerank": {"pagerank": 1.0, "citation": 0.0, "recency": 0.0, "degree": 0.0},
        "pure_citation": {"pagerank": 0.0, "citation": 1.0, "recency": 0.0, "degree": 0.0},
        "pure_recency": {"pagerank": 0.0, "citation": 0.0, "recency": 1.0, "degree": 0.0},
        "pure_degree": {"pagerank": 0.0, "citation": 0.0, "recency": 0.0, "degree": 1.0},
        "pr_citation": {"pagerank": 0.5, "citation": 0.5, "recency": 0.0, "degree": 0.0},
        "citation_recency": {"pagerank": 0.0, "citation": 0.6, "recency": 0.4, "degree": 0.0},
    }

    grid: List[Dict[str, float]] = []
    vals = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    for pr in vals:
        for cit in vals:
            for rec in vals:
                deg = round(1.0 - pr - cit - rec, 10)
                if deg < -1e-9:
                    continue
                if deg < 0:
                    deg = 0.0
                grid.append({"pagerank": pr, "citation": cit, "recency": rec, "degree": deg})

    per_run: List[Dict[str, Any]] = []
    variant_recalls: Dict[str, List[float]] = defaultdict(list)
    tuned_recalls: List[float] = []
    top_k = 20

    for held_out in runs:
        train_runs = [r for r in runs if r.run_id != held_out.run_id]

        def run_target(run: audit.RunBundle) -> set[str]:
            # External target: top cited OpenAlex-matched papers within the archived topic slice.
            cmap = _load_openalex_citation_map(run, matches)
            positives = [pid for pid, c in sorted(cmap.items(), key=lambda x: x[1], reverse=True) if c > 0]
            return set(positives[: max(5, min(20, len(positives)))])

        train_targets = {r.run_id: run_target(r) for r in train_runs}
        held_target = run_target(held_out)

        def eval_weight(run: audit.RunBundle, weights: Dict[str, float], target: set[str]) -> float:
            comps = _score_components(run, _load_openalex_citation_map(run, matches))
            ranked = _rank_from_components(comps, weights, top_k)
            return len(set(ranked) & target) / len(target) if target else 0.0

        grid_scores: List[Tuple[float, Dict[str, float]]] = []
        for w in grid:
            score = _safe_mean(eval_weight(r, w, train_targets[r.run_id]) for r in train_runs)
            grid_scores.append((score, w))
        grid_scores.sort(key=lambda x: (x[0], x[1]["citation"], x[1]["pagerank"]), reverse=True)
        tuned_w = grid_scores[0][1]
        tuned_recall = eval_weight(held_out, tuned_w, held_target)
        tuned_recalls.append(tuned_recall)

        variants: Dict[str, float] = {}
        for name, w in named_weights.items():
            val = eval_weight(held_out, w, held_target)
            variants[name] = val
            variant_recalls[name].append(val)

        per_run.append(
            {
                "run_id": held_out.run_id,
                "label": held_out.label,
                "target_size": len(held_target),
                "heldout_tuned_weights": tuned_w,
                "heldout_tuned_recall_at20": tuned_recall,
                "named_variant_recall_at20": variants,
            }
        )

    aggregate = {
        name: {
            "mean_recall_at20": _safe_mean(vals),
            "median_recall_at20": _safe_median(vals),
        }
        for name, vals in variant_recalls.items()
    }
    aggregate["leave_one_run_grid_tuned"] = {
        "mean_recall_at20": _safe_mean(tuned_recalls),
        "median_recall_at20": _safe_median(tuned_recalls),
    }

    return {
        "experiment_type": "core_score_leave_one_run_calibration",
        "scope_note": (
            "Leave-one-run grid calibration of core-paper score weights against an external OpenAlex citation proxy. "
            "The target is the top cited OpenAlex-matched papers within each archived topic slice, so this is a "
            "calibration stress test rather than expert gold supervision."
        ),
        "top_k": top_k,
        "runs": len(runs),
        "grid_size": len(grid),
        "named_weights": named_weights,
        "per_run": per_run,
        "aggregate": aggregate,
        "paired_tuned_vs_default": audit.exact_paired_sign_flip_test(
            t - d for t, d in zip(tuned_recalls, variant_recalls["default_hybrid"])
        ),
    }


def build_cost_scaling_summary() -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for run in audit.load_archived_runs():
        time_path = run.base_dir / "metrics" / "time_monitor.json"
        token_path = run.base_dir / "metrics" / "token_monitor.json"
        time_data = _load_json(time_path) if time_path.exists() else {}
        token_data = _load_json(token_path) if token_path.exists() else {}
        total_runtime_seconds = sum(float(v.get("duration", 0.0) or 0.0) for v in time_data.values())
        gen_runtime_seconds = float(time_data.get("generate content with reflection", {}).get("duration", 0.0) or 0.0)

        input_tokens = 0
        output_tokens = 0
        total_cost = 0.0
        for stage in token_data.values():
            if not isinstance(stage, dict):
                continue
            for model_stats in stage.values():
                if not isinstance(model_stats, dict):
                    continue
                input_tokens += int(model_stats.get("input_tokens", 0) or 0)
                output_tokens += int(model_stats.get("output_tokens", 0) or 0)
                total_cost += float(model_stats.get("total_cost", 0.0) or 0.0)

        paper_count = len(run.mekg.get("papers", []))
        relation_count = len(run.mekg.get("relations", []))
        semantic_count = sum(1 for rel in run.mekg.get("relations", []) if rel.get("type") in audit.SEMANTIC_RELATIONS)
        rows.append(
            {
                "run_id": run.run_id,
                "label": run.label,
                "paper_count": paper_count,
                "relation_count": relation_count,
                "semantic_relation_count": semantic_count,
                "sections": len(run.outline.get("sections", [])),
                "runtime_minutes": total_runtime_seconds / 60.0,
                "generation_runtime_minutes": gen_runtime_seconds / 60.0,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "logged_cost": total_cost,
                "runtime_minutes_per_100_papers": (total_runtime_seconds / 60.0) / paper_count * 100 if paper_count else 0.0,
                "tokens_per_100_papers": (input_tokens + output_tokens) / paper_count * 100 if paper_count else 0.0,
                "relations_per_100_papers": relation_count / paper_count * 100 if paper_count else 0.0,
            }
        )

    by_size: Dict[str, Any] = {}
    for label, pred in {
        "50_paper_runs": lambda r: r["paper_count"] <= 60,
        "196_200_paper_runs": lambda r: r["paper_count"] >= 190,
        "all_runs": lambda r: True,
    }.items():
        part = [r for r in rows if pred(r)]
        by_size[label] = {
            "runs": len(part),
            "mean_runtime_minutes": _safe_mean(r["runtime_minutes"] for r in part),
            "mean_runtime_minutes_per_100_papers": _safe_mean(r["runtime_minutes_per_100_papers"] for r in part),
            "mean_tokens_per_100_papers": _safe_mean(r["tokens_per_100_papers"] for r in part),
            "mean_logged_cost": _safe_mean(r["logged_cost"] for r in part),
            "mean_relations_per_100_papers": _safe_mean(r["relations_per_100_papers"] for r in part),
        }

    return {
        "experiment_type": "archived_cost_scaling_summary",
        "scope_note": (
            "Aggregates repository-local time_monitor/token_monitor traces. These are archived end-to-end generation "
            "runs, so generation/reflection dominates; graph construction alone was not separately timed in the old logs."
        ),
        "runs": len(rows),
        "per_run": rows,
        "aggregate": by_size,
    }


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


def build_matched_baseline_pack() -> Dict[str, Any]:
    topics: List[Dict[str, Any]] = []
    runs = [run for run in audit.load_archived_runs() if run.label in TARGET_TOPICS]
    for run in runs:
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

        full_adj, full_pairs = audit.build_adjacency(run, paper_map)
        simple_allowed = audit.RELATION_FAMILY_VARIANTS["structural_only"]
        simple_adj, simple_pairs = audit.build_adjacency(run, paper_map, allowed_rel_types=simple_allowed)
        semantic_allowed = audit.RELATION_FAMILY_VARIANTS["semantic_only"]
        semantic_adj, semantic_pairs = audit.build_adjacency(run, paper_map, allowed_rel_types=semantic_allowed)

        full_rank = audit.make_graph_ranker(papers, paper_map, idf, centrality, full_adj, max_hops=1)
        simple_rank = audit.make_graph_ranker(papers, paper_map, idf, centrality, simple_adj, max_hops=1)
        semantic_rank = audit.make_graph_ranker(papers, paper_map, idf, centrality, semantic_adj, max_hops=1)

        flat = _evaluate_ranker(run, flat_rank, full_pairs, target_ids)
        simple = _evaluate_ranker(run, lambda t, d: simple_rank(t, d)[0], simple_pairs, target_ids)
        semantic = _evaluate_ranker(run, lambda t, d: semantic_rank(t, d)[0], semantic_pairs, target_ids)
        full = _evaluate_ranker(run, lambda t, d: full_rank(t, d)[0], full_pairs, target_ids)

        topics.append(
            {
                "topic": run.label,
                "run_id": run.run_id,
                "external_proxy_target_size": len(target_ids),
                "source_survey_count": target_info["source_survey_count"],
                "flat": flat,
                "structural_simple_graph": simple,
                "semantic_only_graph": semantic,
                "full_mekg": full,
            }
        )

    methods = ["flat", "structural_simple_graph", "semantic_only_graph", "full_mekg"]
    aggregate: Dict[str, Any] = {}
    for method in methods:
        aggregate[method] = {
            "mean_recall_top5": _safe_mean(t[method]["external_proxy_recall_top5"] for t in topics),
            "mean_precision_top5": _safe_mean(t[method]["external_proxy_precision_top5"] for t in topics),
            "mean_relation_density_top5": _safe_mean(t[method]["relation_density_top5"] for t in topics),
            "mean_unique_papers_top5": _safe_mean(t[method]["unique_papers_top5"] for t in topics),
        }

    return {
        "experiment_type": "matched_retrieval_stage_baseline_pack",
        "scope_note": (
            "Four-topic matched retrieval-stage replay: same archived topic slices, same outlines, same top-5 "
            "section budget, and the same weak survey-reference external target. This is not end-to-end generation "
            "parity, but it directly compares flat retrieval, structural graph, semantic-only graph, and full MEKG."
        ),
        "topic_count": len(topics),
        "topics": topics,
        "aggregate": aggregate,
        "paired_full_vs_flat_recall": audit.exact_paired_sign_flip_test(
            t["full_mekg"]["external_proxy_recall_top5"] - t["flat"]["external_proxy_recall_top5"] for t in topics
        ),
        "paired_full_vs_structural_recall": audit.exact_paired_sign_flip_test(
            t["full_mekg"]["external_proxy_recall_top5"]
            - t["structural_simple_graph"]["external_proxy_recall_top5"]
            for t in topics
        ),
        "paired_semantic_vs_structural_recall": audit.exact_paired_sign_flip_test(
            t["semantic_only_graph"]["external_proxy_recall_top5"]
            - t["structural_simple_graph"]["external_proxy_recall_top5"]
            for t in topics
        ),
    }


def build_semantic_evidence_gate_from_existing() -> Dict[str, Any]:
    path = ROOT / "outputs" / "semantic_evidence_gate_retrieval_eval_20260526" / "semantic_evidence_gate_retrieval_eval.json"
    if path.exists():
        return _load_json(path)
    return {
        "experiment_type": "semantic_evidence_gate_retrieval_eval",
        "missing": True,
        "scope_note": "Run experiments/semantic_evidence_gate_retrieval_eval.py to populate this field.",
    }


def _write_markdown(pack: Dict[str, Any]) -> str:
    lines: List[str] = ["# Full Reviewer Evidence Pack", ""]

    sem = pack["snippet_semantic_examples"]
    lines += [
        "## Snippet-level semantic-edge validation examples",
        "",
        f"- Source audit sample: {sem['source_audit_overall']['total']} protocol rows; supported-or-partial "
        f"{sem['source_audit_overall']['supported_or_partial_rate']*100:.1f}%.",
        "",
        "| Relation | Label | Source | Target | Failure mode | Source snippet |",
        "|---|---|---|---|---|---|",
    ]
    for ex in sem["examples"][:9]:
        snip = ex["source_snippet"].replace("|", " ")[:140]
        lines.append(
            f"| {ex['relation_type']} | {ex['protocol_label']} | {ex['source_title'][:55]} | "
            f"{ex['target_title'][:55]} | {ex['failure_mode']} | {snip} |"
        )

    cost = pack["cost_scaling"]
    lines += [
        "",
        "## Cost and scaling traces",
        "",
        "| Group | Runs | Runtime min | Runtime min / 100 papers | Tokens / 100 papers | Logged cost | Relations / 100 papers |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in cost["aggregate"].items():
        lines.append(
            f"| {name} | {row['runs']} | {row['mean_runtime_minutes']:.1f} | "
            f"{row['mean_runtime_minutes_per_100_papers']:.1f} | {row['mean_tokens_per_100_papers']:.0f} | "
            f"{row['mean_logged_cost']:.3f} | {row['mean_relations_per_100_papers']:.1f} |"
        )

    core = pack["core_score_calibration"]
    lines += [
        "",
        "## Core-score calibration",
        "",
        "| Variant | Mean recall@20 | Median recall@20 |",
        "|---|---:|---:|",
    ]
    for name, row in core["aggregate"].items():
        lines.append(f"| {name} | {row['mean_recall_at20']:.3f} | {row['median_recall_at20']:.3f} |")

    mb = pack["matched_baseline_pack"]
    lines += [
        "",
        "## Matched retrieval-stage baseline",
        "",
        "| Method | Mean recall@5 | Mean precision@5 | Relation density | Unique papers |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, row in mb["aggregate"].items():
        lines.append(
            f"| {name} | {row['mean_recall_top5']:.3f} | {row['mean_precision_top5']:.3f} | "
            f"{row['mean_relation_density_top5']:.3f} | {row['mean_unique_papers_top5']:.1f} |"
        )

    gate = pack.get("semantic_evidence_gate", {})
    if gate.get("aggregate"):
        lines += [
            "",
            "## Semantic evidence-gated retrieval replay",
            "",
            "| Mode | Mean recall@5 | Mean precision@5 | Relation density | Semantic kept | Semantic dropped |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for name, row in gate["aggregate"].items():
            lines.append(
                f"| {name} | {row['mean_recall_top5']:.3f} | {row['mean_precision_top5']:.3f} | "
                f"{row['mean_relation_density_top5']:.3f} | {row['mean_semantic_kept']:.1f} | "
                f"{row['mean_semantic_dropped']:.1f} |"
            )

    return "\n".join(lines) + "\n"


def build_pack() -> Dict[str, Any]:
    return {
        "experiment_type": "full_reviewer_evidence_pack",
        "scope_note": (
            "Consolidated post-paperreview evidence pack built from repository-local archived runs and cached "
            "OpenAlex matches. No unexecuted or fabricated measurements are included."
        ),
        "snippet_semantic_examples": build_snippet_level_semantic_examples(),
        "cost_scaling": build_cost_scaling_summary(),
        "core_score_calibration": build_core_score_calibration(),
        "matched_baseline_pack": build_matched_baseline_pack(),
        "semantic_evidence_gate": build_semantic_evidence_gate_from_existing(),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pack = build_pack()
    (OUTPUT_DIR / "full_reviewer_evidence_pack.json").write_text(
        json.dumps(pack, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "full_reviewer_evidence_pack.md").write_text(
        _write_markdown(pack),
        encoding="utf-8",
    )
    print(f"Wrote outputs to {OUTPUT_DIR}")
    print((OUTPUT_DIR / "full_reviewer_evidence_pack.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
