import copy
import json
import math
import re
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Set, Tuple

import networkx as nx

from experiments import offline_real_revision_audit as audit


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "outputs" / "minimal_real_revision_20260524"
ARCHIVED_RUN_IDS = [item["id"] for item in audit.ARCHIVED_RUNS]

ARXIV_REF_RE = re.compile(r"arXiv:(\d{4}\.\d{4,5})", re.IGNORECASE)
ROLE_PATTERNS = {
    "survey": [r"\bsurvey\b", r"\breview\b", r"\btaxonomy\b"],
    "benchmark": [r"\bbenchmark\b", r"\bbench\b", r"\bevaluation\b", r"\beval\b"],
    "dataset": [r"\bdataset\b", r"\bcorpus\b"],
}
COMPILED_ROLE_PATTERNS = {
    role: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for role, patterns in ROLE_PATTERNS.items()
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_runs() -> List[audit.RunBundle]:
    return audit.load_archived_runs()


def detect_title_role(title: str) -> str:
    for role, patterns in COMPILED_ROLE_PATTERNS.items():
        if any(pattern.search(title or "") for pattern in patterns):
            return role
    return "other"


def compute_core_rankings(run: audit.RunBundle) -> Dict[str, List[str]]:
    papers = run.mekg.get("papers", [])
    paper_map = {paper["id"]: paper for paper in papers}

    graph = nx.DiGraph()
    graph.add_nodes_from(paper_map)
    for rel in run.mekg.get("relations", []):
        src = rel.get("source")
        tgt = rel.get("target")
        if src in paper_map and tgt in paper_map:
            graph.add_edge(src, tgt)

    pagerank = nx.pagerank(graph, alpha=0.85) if graph.number_of_nodes() else {}
    if pagerank:
        max_pr = max(pagerank.values())
        min_pr = min(pagerank.values())
        pr_range = max_pr - min_pr if max_pr != min_pr else 1.0
        pagerank = {
            pid: (score - min_pr) / pr_range
            for pid, score in pagerank.items()
        }
    else:
        pagerank = {pid: 0.0 for pid in paper_map}

    all_citations: List[float] = []
    all_years: List[int] = []
    all_degrees: List[int] = []
    for pid in graph.nodes():
        paper = paper_map.get(pid, {})
        citations = paper.get("citations", paper.get("citation_count", 0))
        if isinstance(citations, (int, float)) and citations >= 0:
            all_citations.append(float(citations))
        year = paper.get("year", 2024)
        if isinstance(year, int) and 1900 < year <= 2024:
            all_years.append(year)
        all_degrees.append(graph.in_degree(pid) + graph.out_degree(pid))

    max_citation = max(all_citations) if all_citations else 1.0
    min_year = min(all_years) if all_years else 2014
    max_year = max(all_years) if all_years else 2024
    year_range = max_year - min_year if max_year > min_year else 1
    max_degree = max(all_degrees) if all_degrees else 1

    base_scores: List[Tuple[str, float]] = []
    pr_scores: List[Tuple[str, float]] = []
    recency_scores: List[Tuple[str, int]] = []
    for pid in graph.nodes():
        paper = paper_map.get(pid, {})

        citations = paper.get("citations", paper.get("citation_count", 0))
        if not isinstance(citations, (int, float)) or citations < 0:
            citations = 0
        citation_score = (
            math.log1p(citations) / math.log1p(max_citation)
            if max_citation > 0
            else 0.0
        )

        year = paper.get("year", 2024)
        if not isinstance(year, int) or year < 1900 or year > 2024:
            year = 2024
        recency_score = (year - min_year) / year_range if year_range > 0 else 0.5

        degree = graph.in_degree(pid) + graph.out_degree(pid)
        degree_score = degree / max_degree if max_degree > 0 else 0.0

        base_score = (
            0.4 * pagerank.get(pid, 0.0)
            + 0.3 * citation_score
            + 0.2 * recency_score
            + 0.1 * degree_score
        )

        base_scores.append((pid, base_score))
        pr_scores.append((pid, pagerank.get(pid, 0.0)))
        recency_scores.append((pid, year))

    base_scores.sort(key=lambda x: x[1], reverse=True)
    pr_scores.sort(key=lambda x: x[1], reverse=True)
    recency_scores.sort(key=lambda x: x[1], reverse=True)

    return {
        "base_top10": [pid for pid, _ in base_scores[:10]],
        "base_top20": [pid for pid, _ in base_scores[:20]],
        "pagerank_top10": [pid for pid, _ in pr_scores[:10]],
        "pagerank_top20": [pid for pid, _ in pr_scores[:20]],
        "recency_top10": [pid for pid, _ in recency_scores[:10]],
        "recency_top20": [pid for pid, _ in recency_scores[:20]],
    }


def collect_survey_reference_targets(run: audit.RunBundle) -> Dict[str, Any]:
    mekg_papers = run.mekg.get("papers", [])
    corpus_id_map = {
        str(paper["id"]).replace("arXiv:", ""): paper
        for paper in mekg_papers
        if str(paper.get("id", "")).startswith("arXiv:")
    }
    sources: List[Dict[str, Any]] = []
    union_ids: Set[str] = set()

    for paper_path in (run.base_dir / "papers").glob("*.json"):
        paper = load_json(paper_path)
        title = paper.get("title", "")
        paper_type = paper.get("paper_type", "")
        if paper_type != "survey" and "survey" not in title.lower() and "review" not in title.lower():
            continue

        referenced_ids = {
            match.group(1)
            for match in ARXIV_REF_RE.finditer(paper.get("md_text", ""))
        }
        overlap_ids = sorted(referenced_ids & set(corpus_id_map))
        if not overlap_ids:
            continue

        union_ids.update(overlap_ids)
        sources.append(
            {
                "title": title,
                "paper_type": paper_type,
                "reference_ids_found": len(referenced_ids),
                "overlap_count": len(overlap_ids),
                "overlap_ids": overlap_ids,
            }
        )

    sources.sort(key=lambda row: (-row["overlap_count"], row["title"]))
    return {
        "external_target_ids": [f"arXiv:{paper_id}" for paper_id in sorted(union_ids)],
        "target_size": len(union_ids),
        "source_survey_count": len(sources),
        "source_surveys": sources,
    }


def run_survey_reference_external_core_audit(
    runs: List[audit.RunBundle],
) -> Dict[str, Any]:
    per_run: List[Dict[str, Any]] = []

    for run in runs:
        target_info = collect_survey_reference_targets(run)
        target_ids = set(target_info["external_target_ids"])
        if len(target_ids) < 3:
            continue

        rankings = compute_core_rankings(run)

        def recall(ids: List[str]) -> float:
            return len(set(ids) & target_ids) / len(target_ids) if target_ids else 0.0

        per_run.append(
            {
                "run_id": run.run_id,
                "label": run.label,
                "external_target_size": len(target_ids),
                "source_survey_count": target_info["source_survey_count"],
                "source_surveys": target_info["source_surveys"],
                "base_top10_recall": recall(rankings["base_top10"]),
                "base_top20_recall": recall(rankings["base_top20"]),
                "pagerank_top10_recall": recall(rankings["pagerank_top10"]),
                "pagerank_top20_recall": recall(rankings["pagerank_top20"]),
                "recency_top10_recall": recall(rankings["recency_top10"]),
                "recency_top20_recall": recall(rankings["recency_top20"]),
            }
        )

    if not per_run:
        return {
            "experiment_type": "survey_reference_external_core_audit",
            "scope_note": "No survey-reference-backed external target sets were recovered from archived runs.",
            "per_run": [],
            "aggregate": {},
        }

    aggregate = {
        "runs_used": len(per_run),
        "external_target_size_mean": mean(row["external_target_size"] for row in per_run),
        "external_target_size_median": median(row["external_target_size"] for row in per_run),
        "source_survey_count_mean": mean(row["source_survey_count"] for row in per_run),
        "base_top10_recall_mean": mean(row["base_top10_recall"] for row in per_run),
        "base_top20_recall_mean": mean(row["base_top20_recall"] for row in per_run),
        "pagerank_top10_recall_mean": mean(row["pagerank_top10_recall"] for row in per_run),
        "pagerank_top20_recall_mean": mean(row["pagerank_top20_recall"] for row in per_run),
        "recency_top10_recall_mean": mean(row["recency_top10_recall"] for row in per_run),
        "recency_top20_recall_mean": mean(row["recency_top20_recall"] for row in per_run),
        "paired_base20_vs_recency20": audit.exact_paired_sign_flip_test(
            [row["base_top20_recall"] - row["recency_top20_recall"] for row in per_run]
        ),
        "paired_base20_vs_pagerank20": audit.exact_paired_sign_flip_test(
            [row["base_top20_recall"] - row["pagerank_top20_recall"] for row in per_run]
        ),
    }

    return {
        "experiment_type": "survey_reference_external_core_audit",
        "scope_note": (
            "External-core proxy built locally by extracting arXiv reference IDs from survey/review papers "
            "already present inside the archived corpora and intersecting them with the same archived paper pool. "
            "This reduces circularity relative to MEKG-derived core sets, but it is still a partial proxy rather "
            "than a public benchmark."
        ),
        "per_run": per_run,
        "aggregate": aggregate,
    }


def run_semantic_target_role_pruning_audit(
    runs: List[audit.RunBundle],
) -> Dict[str, Any]:
    per_run: List[Dict[str, Any]] = []
    by_relation_type: Dict[str, Dict[str, float]] = {
        rel_type: {
            "total": 0.0,
            "pruned": 0.0,
            "cue_support_total": 0.0,
            "cue_support_kept": 0.0,
            "temporal_total": 0.0,
            "temporal_kept": 0.0,
            "kept_total": 0.0,
        }
        for rel_type in audit.SEMANTIC_RELATIONS
    }

    for run in runs:
        paper_json_by_title: Dict[str, Dict[str, Any]] = {}
        for paper_path in (run.base_dir / "papers").glob("*.json"):
            paper = load_json(paper_path)
            paper_json_by_title[paper.get("title", "")] = paper

        papers_by_id = {paper["id"]: paper for paper in run.mekg.get("papers", [])}
        filtered_run = copy.deepcopy(run)
        filtered_relations: List[Dict[str, Any]] = []

        semantic_edges = 0
        pruned_edges = 0

        for rel in run.mekg.get("relations", []):
            rel_type = rel.get("type", "")
            if rel_type not in audit.SEMANTIC_RELATIONS:
                filtered_relations.append(rel)
                continue

            semantic_edges += 1
            src = papers_by_id.get(rel.get("source"), {})
            tgt = papers_by_id.get(rel.get("target"), {})
            tgt_json = paper_json_by_title.get(tgt.get("title", ""), {})
            target_role = detect_title_role(tgt_json.get("title", tgt.get("title", "")))

            src_year = src.get("year")
            tgt_year = tgt.get("year")
            temporal_ok = (
                isinstance(src_year, int)
                and isinstance(tgt_year, int)
                and src_year >= tgt_year
            )
            cue_support = audit.source_cue_present(
                rel_type,
                src.get("title", ""),
                src.get("abstract", ""),
            )

            row = by_relation_type[rel_type]
            row["total"] += 1
            row["cue_support_total"] += float(cue_support)
            row["temporal_total"] += float(temporal_ok)

            should_prune = (
                rel_type in {"extends", "improves"}
                and target_role in {"survey", "benchmark", "dataset"}
            )
            if should_prune:
                pruned_edges += 1
                row["pruned"] += 1
                continue

            filtered_relations.append(rel)
            row["kept_total"] += 1
            row["cue_support_kept"] += float(cue_support)
            row["temporal_kept"] += float(temporal_ok)

        filtered_run.mekg["relations"] = filtered_relations

        original_context = audit.build_retrieval_context(run)
        original_adjacency, original_pairs = audit.build_adjacency(
            run, original_context["paper_map"]
        )
        original_graph_ranker = audit.make_graph_ranker(
            original_context["papers"],
            original_context["paper_map"],
            original_context["idf"],
            original_context["centrality"],
            original_adjacency,
            max_hops=1,
        )
        original_graph = audit.evaluate_union_with_context(
            run,
            lambda title, desc: original_graph_ranker(title, desc)[0],
            original_context,
            original_pairs,
        )

        filtered_context = audit.build_retrieval_context(filtered_run)
        filtered_adjacency, filtered_pairs = audit.build_adjacency(
            filtered_run, filtered_context["paper_map"]
        )
        filtered_graph_ranker = audit.make_graph_ranker(
            filtered_context["papers"],
            filtered_context["paper_map"],
            filtered_context["idf"],
            filtered_context["centrality"],
            filtered_adjacency,
            max_hops=1,
        )
        filtered_graph = audit.evaluate_union_with_context(
            filtered_run,
            lambda title, desc: filtered_graph_ranker(title, desc)[0],
            filtered_context,
            filtered_pairs,
        )

        per_run.append(
            {
                "run_id": run.run_id,
                "label": run.label,
                "semantic_edge_count": semantic_edges,
                "pruned_edge_count": pruned_edges,
                "pruned_edge_share": pruned_edges / semantic_edges if semantic_edges else 0.0,
                "original_graph_core_recall": original_graph["core_paper_recall"],
                "filtered_graph_core_recall": filtered_graph["core_paper_recall"],
                "core_recall_delta": filtered_graph["core_paper_recall"] - original_graph["core_paper_recall"],
                "original_graph_relation_density": original_graph["relation_density"],
                "filtered_graph_relation_density": filtered_graph["relation_density"],
                "relation_density_delta": filtered_graph["relation_density"] - original_graph["relation_density"],
                "original_unique_papers": original_graph["unique_papers"],
                "filtered_unique_papers": filtered_graph["unique_papers"],
            }
        )

    aggregate_by_relation = {}
    for rel_type, row in by_relation_type.items():
        total = row["total"]
        kept = row["kept_total"]
        aggregate_by_relation[rel_type] = {
            "total": int(total),
            "pruned": int(row["pruned"]),
            "pruned_share": row["pruned"] / total if total else 0.0,
            "cue_support_before": row["cue_support_total"] / total if total else 0.0,
            "cue_support_after": row["cue_support_kept"] / kept if kept else 0.0,
            "temporal_consistency_before": row["temporal_total"] / total if total else 0.0,
            "temporal_consistency_after": row["temporal_kept"] / kept if kept else 0.0,
        }

    aggregate = {
        "runs_used": len(per_run),
        "pruned_edge_share_mean": mean(row["pruned_edge_share"] for row in per_run) if per_run else 0.0,
        "original_graph_core_recall_mean": mean(row["original_graph_core_recall"] for row in per_run) if per_run else 0.0,
        "filtered_graph_core_recall_mean": mean(row["filtered_graph_core_recall"] for row in per_run) if per_run else 0.0,
        "core_recall_delta_mean": mean(row["core_recall_delta"] for row in per_run) if per_run else 0.0,
        "original_graph_relation_density_mean": mean(row["original_graph_relation_density"] for row in per_run) if per_run else 0.0,
        "filtered_graph_relation_density_mean": mean(row["filtered_graph_relation_density"] for row in per_run) if per_run else 0.0,
        "relation_density_delta_mean": mean(row["relation_density_delta"] for row in per_run) if per_run else 0.0,
        "paired_core_recall_delta": audit.exact_paired_sign_flip_test(
            [row["core_recall_delta"] for row in per_run]
        ) if per_run else {},
        "paired_relation_density_delta": audit.exact_paired_sign_flip_test(
            [row["relation_density_delta"] for row in per_run]
        ) if per_run else {},
    }

    return {
        "experiment_type": "semantic_target_role_pruning_audit",
        "scope_note": (
            "Low-cost heuristic robustness audit: for extends/improves only, prune edges whose targets look like "
            "survey / benchmark / dataset papers by title regex, then replay the archived graph-retrieval "
            "diagnostic. This is a failure-mode probe, not a learned repair model."
        ),
        "role_heuristics": ROLE_PATTERNS,
        "per_run": per_run,
        "aggregate": aggregate,
        "by_relation_type": aggregate_by_relation,
    }


def build_markdown_report(
    external_core_summary: Dict[str, Any],
    target_role_summary: Dict[str, Any],
) -> str:
    lines: List[str] = []
    lines.append("# Review-Response Low-Cost Audit Additions")
    lines.append("")

    lines.append("## 1. Survey-Reference External-Core Audit")
    lines.append("")
    lines.append(external_core_summary.get("scope_note", ""))
    lines.append("")
    agg = external_core_summary.get("aggregate", {})
    if agg:
        lines.append(
            f"- Runs used: **{agg.get('runs_used', 0)}**; mean external target size: **{agg.get('external_target_size_mean', 0.0):.2f}**; median: **{agg.get('external_target_size_median', 0.0):.2f}**."
        )
        lines.append(
            f"- Mean recall against survey-reference-backed targets: base top-10 **{agg.get('base_top10_recall_mean', 0.0):.3f}**, base top-20 **{agg.get('base_top20_recall_mean', 0.0):.3f}**."
        )
        lines.append(
            f"- Context baselines: recency top-20 **{agg.get('recency_top20_recall_mean', 0.0):.3f}**, PageRank top-20 **{agg.get('pagerank_top20_recall_mean', 0.0):.3f}**."
        )
    lines.append("")
    lines.append("| Run | Target size | Base@10 | Base@20 | Recency@20 | PageRank@20 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in external_core_summary.get("per_run", []):
        lines.append(
            f"| {row['label']} | {row['external_target_size']} | {row['base_top10_recall']:.3f} | {row['base_top20_recall']:.3f} | {row['recency_top20_recall']:.3f} | {row['pagerank_top20_recall']:.3f} |"
        )

    lines.append("")
    lines.append("## 2. Semantic Target-Role Pruning Audit")
    lines.append("")
    lines.append(target_role_summary.get("scope_note", ""))
    lines.append("")
    agg = target_role_summary.get("aggregate", {})
    if agg:
        lines.append(
            f"- Mean pruned-edge share across archived runs: **{agg.get('pruned_edge_share_mean', 0.0):.3f}**."
        )
        lines.append(
            f"- Graph core-paper recall changes from **{agg.get('original_graph_core_recall_mean', 0.0):.3f}** to **{agg.get('filtered_graph_core_recall_mean', 0.0):.3f}** (mean Δ **{agg.get('core_recall_delta_mean', 0.0):+.3f}**)."
        )
        lines.append(
            f"- Graph relation density changes from **{agg.get('original_graph_relation_density_mean', 0.0):.3f}** to **{agg.get('filtered_graph_relation_density_mean', 0.0):.3f}** (mean Δ **{agg.get('relation_density_delta_mean', 0.0):+.3f}**)."
        )
    lines.append("")
    lines.append("| Relation type | Total | Pruned | Pruned share | Cue before | Cue after |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for rel_type, row in target_role_summary.get("by_relation_type", {}).items():
        lines.append(
            f"| {rel_type} | {row['total']} | {row['pruned']} | {row['pruned_share']:.3f} | {row['cue_support_before']:.3f} | {row['cue_support_after']:.3f} |"
        )

    lines.append("")
    lines.append("| Run | Semantic edges | Pruned | Share | Core recall Δ | Relation density Δ |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in target_role_summary.get("per_run", []):
        lines.append(
            f"| {row['label']} | {row['semantic_edge_count']} | {row['pruned_edge_count']} | {row['pruned_edge_share']:.3f} | {row['core_recall_delta']:+.3f} | {row['relation_density_delta']:+.3f} |"
        )

    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    ensure_dir(OUTPUT_ROOT)
    runs = load_runs()

    external_core_summary = run_survey_reference_external_core_audit(runs)
    target_role_summary = run_semantic_target_role_pruning_audit(runs)

    write_json(
        OUTPUT_ROOT / "survey_reference_external_core_audit.json",
        external_core_summary,
    )
    write_json(
        OUTPUT_ROOT / "semantic_target_role_pruning_audit.json",
        target_role_summary,
    )
    (OUTPUT_ROOT / "review_response_audit_additions.md").write_text(
        build_markdown_report(external_core_summary, target_role_summary),
        encoding="utf-8",
    )
    print(f"Wrote outputs to {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()
