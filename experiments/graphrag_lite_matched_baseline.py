from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import networkx as nx
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit
from experiments import review_response_audit as review

OUTPUT_DIR = ROOT / "outputs" / "graphrag_lite_matched_baseline_20260526"


def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _paper_text(paper: Dict[str, Any]) -> str:
    return " ".join(
        str(paper.get(k, "") or "")
        for k in ("title", "abstract", "category", "subcategory")
    ).strip()


def _pagerank_from_adjacency(
    paper_ids: Iterable[str],
    adjacency: Dict[str, List[Tuple[str, float, str]]],
) -> Dict[str, float]:
    graph = nx.Graph()
    graph.add_nodes_from(paper_ids)
    for src, rows in adjacency.items():
        for tgt, conf, _rel_type in rows:
            if src == tgt:
                continue
            graph.add_edge(src, tgt, weight=float(conf or 0.0))
    if graph.number_of_nodes() == 0:
        return {}
    scores = nx.pagerank(graph, weight="weight")
    max_score = max(scores.values()) if scores else 0.0
    if max_score <= 0:
        return {pid: 0.0 for pid in graph.nodes()}
    return {pid: float(score) / max_score for pid, score in scores.items()}


def _build_tfidf_knn_graph(
    papers: List[Dict[str, Any]],
    top_neighbors: int = 5,
    min_similarity: float = 0.05,
) -> Tuple[Dict[str, List[Tuple[str, float, str]]], set[Tuple[str, str]]]:
    """Build a lightweight GraphRAG-style similarity graph without MEKG edges.

    The baseline deliberately uses only local title/abstract/category text and
    TF-IDF cosine neighbors. It is a stronger non-typed graph baseline than flat
    lexical retrieval, but much cheaper and less structured than SurveyGraph's
    typed MEKG.
    """

    paper_ids = [audit.sanitize_key(p["id"]) for p in papers]
    texts = [_paper_text(p) for p in papers]
    adjacency: Dict[str, List[Tuple[str, float, str]]] = defaultdict(list)
    pairs: set[Tuple[str, str]] = set()
    if len(papers) < 2:
        return adjacency, pairs

    matrix = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        min_df=1,
    ).fit_transform(texts)
    sims = cosine_similarity(matrix)
    np.fill_diagonal(sims, -1.0)

    edge_weights: Dict[Tuple[str, str], float] = {}
    for i, src in enumerate(paper_ids):
        order = np.argsort(sims[i])[::-1]
        kept = 0
        for j in order:
            score = float(sims[i, j])
            if score < min_similarity:
                break
            tgt = paper_ids[int(j)]
            if src == tgt:
                continue
            pair = tuple(sorted((src, tgt)))
            edge_weights[pair] = max(edge_weights.get(pair, 0.0), score)
            kept += 1
            if kept >= top_neighbors:
                break

    for (src, tgt), score in edge_weights.items():
        pairs.add((src, tgt))
        adjacency[src].append((tgt, score, "tfidf_similarity"))
        adjacency[tgt].append((src, score, "tfidf_similarity"))
    return adjacency, pairs


def _density(ids: List[str], pairs: set[Tuple[str, str]]) -> float:
    pair_total = 0
    linked = 0
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            pair_total += 1
            if tuple(sorted((ids[i], ids[j]))) in pairs:
                linked += 1
    return linked / pair_total if pair_total else 0.0


def _evaluate_ranker(
    run: audit.RunBundle,
    ranker,
    target_ids: set[str],
    full_pairs: set[Tuple[str, str]],
    active_pairs: set[Tuple[str, str]],
    top_k: int = 5,
) -> Dict[str, Any]:
    started = time.perf_counter()
    union_ids: List[str] = []
    section_rows: List[Dict[str, Any]] = []
    for section in run.outline.get("sections", []):
        title = section.get("title", "")
        if title in audit.SECTION_EXCLUDE_TITLES:
            continue
        ranked = ranker(title, section.get("description", ""))
        chosen = [pid for pid, _score in ranked[:top_k]]
        union_ids.extend(chosen)
        section_rows.append({"title": title, "top_k_ids": chosen})
    elapsed = time.perf_counter() - started

    unique_ids = list(dict.fromkeys(union_ids))
    hits = set(unique_ids) & target_ids
    return {
        "sections_evaluated": len(section_rows),
        "unique_papers_top5": len(unique_ids),
        "hit_count_top5": len(hits),
        "external_proxy_recall_top5": len(hits) / len(target_ids) if target_ids else 0.0,
        "external_proxy_precision_top5": len(hits) / len(unique_ids) if unique_ids else 0.0,
        # Same yardstick for all modes: how connected the retrieved set is in
        # the full archived MEKG.
        "relation_density_top5": _density(unique_ids, full_pairs),
        # Mode-local graph density is reported separately because the TF-IDF
        # baseline and typed MEKG have different edge semantics.
        "active_graph_density_top5": _density(unique_ids, active_pairs),
        "retrieval_seconds": elapsed,
    }


def _graph_ranker_from_adjacency(
    papers: List[Dict[str, Any]],
    paper_map: Dict[str, Dict[str, Any]],
    idf: Dict[str, float],
    adjacency: Dict[str, List[Tuple[str, float, str]]],
):
    paper_ids = [audit.sanitize_key(p["id"]) for p in papers]
    centrality = _pagerank_from_adjacency(paper_ids, adjacency)
    graph_rank = audit.make_graph_ranker(
        papers,
        paper_map,
        idf,
        centrality,
        adjacency,
        max_hops=1,
    )
    return lambda title, desc: graph_rank(title, desc)[0]


def _safe_fusion_ranker(base_ranker, graph_ranker, preserve_base: int = 3):
    def rank(title: str, desc: str) -> List[Tuple[str, float]]:
        base = base_ranker(title, desc)
        graph = graph_ranker(title, desc)
        seen: set[str] = set()
        fused: List[Tuple[str, float]] = []
        for pid, score in base[:preserve_base]:
            fused.append((pid, float(score) + 1_000_000.0))
            seen.add(pid)
        for pid, score in graph:
            if pid not in seen:
                fused.append((pid, score))
                seen.add(pid)
        return fused

    return rank


def build_eval() -> Dict[str, Any]:
    per_topic: List[Dict[str, Any]] = []
    target_runs = [
        run
        for run in audit.load_archived_runs()
        if len(review.collect_survey_reference_targets(run)["external_target_ids"]) >= 3
    ]

    for run in target_runs:
        target_info = review.collect_survey_reference_targets(run)
        target_ids = {audit.sanitize_key(pid) for pid in target_info["external_target_ids"]}
        context = audit.build_retrieval_context(run)
        papers = context["papers"]
        paper_map = context["paper_map"]
        idf = context["idf"]

        flat_rank = audit.make_flat_ranker(papers, idf)
        full_adj, full_pairs = audit.build_adjacency(run, paper_map)
        structural_adj, structural_pairs = audit.build_adjacency(
            run,
            paper_map,
            allowed_rel_types=audit.RELATION_FAMILY_VARIANTS["structural_only"],
        )
        lite_adj, lite_pairs = _build_tfidf_knn_graph(papers)

        rankers = {
            "flat": (flat_rank, set(), 0),
            "tfidf_knn_lite_graph": (
                _graph_ranker_from_adjacency(papers, paper_map, idf, lite_adj),
                lite_pairs,
                len(lite_pairs),
            ),
            "structural_graph": (
                _graph_ranker_from_adjacency(papers, paper_map, idf, structural_adj),
                structural_pairs,
                len(structural_pairs),
            ),
            "full_mekg": (
                _graph_ranker_from_adjacency(papers, paper_map, idf, full_adj),
                full_pairs,
                len(full_pairs),
            ),
        }
        rankers["safe_fusion_full"] = (
            _safe_fusion_ranker(flat_rank, rankers["full_mekg"][0], preserve_base=3),
            full_pairs,
            len(full_pairs),
        )

        topic_rows: Dict[str, Any] = {}
        for name, (ranker, active_pairs, active_relations) in rankers.items():
            row = _evaluate_ranker(
                run,
                ranker,
                target_ids=target_ids,
                full_pairs=full_pairs,
                active_pairs=active_pairs,
            )
            row["active_relation_count"] = active_relations
            topic_rows[name] = row

        per_topic.append(
            {
                "topic": run.label,
                "run_id": run.run_id,
                "source_survey_count": target_info["source_survey_count"],
                "external_proxy_target_size": len(target_ids),
                "methods": topic_rows,
            }
        )

    methods = ["flat", "tfidf_knn_lite_graph", "structural_graph", "full_mekg", "safe_fusion_full"]
    aggregate: Dict[str, Any] = {}
    for method in methods:
        rows = [topic["methods"][method] for topic in per_topic]
        aggregate[method] = {
            "topic_count": len(rows),
            "mean_recall_top5": _mean(row["external_proxy_recall_top5"] for row in rows),
            "mean_precision_top5": _mean(row["external_proxy_precision_top5"] for row in rows),
            "mean_relation_density_top5": _mean(row["relation_density_top5"] for row in rows),
            "mean_active_graph_density_top5": _mean(row["active_graph_density_top5"] for row in rows),
            "mean_unique_papers_top5": _mean(row["unique_papers_top5"] for row in rows),
            "mean_active_relations": _mean(row["active_relation_count"] for row in rows),
            "mean_retrieval_seconds": _mean(row["retrieval_seconds"] for row in rows),
        }

    def recalls(method: str) -> List[float]:
        return [topic["methods"][method]["external_proxy_recall_top5"] for topic in per_topic]

    pairwise = {
        "tfidf_knn_lite_graph_vs_flat_recall": audit.exact_paired_sign_flip_test(
            g - f for g, f in zip(recalls("tfidf_knn_lite_graph"), recalls("flat"))
        ),
        "structural_graph_vs_tfidf_knn_lite_graph_recall": audit.exact_paired_sign_flip_test(
            s - l for s, l in zip(recalls("structural_graph"), recalls("tfidf_knn_lite_graph"))
        ),
        "full_mekg_vs_tfidf_knn_lite_graph_recall": audit.exact_paired_sign_flip_test(
            m - l for m, l in zip(recalls("full_mekg"), recalls("tfidf_knn_lite_graph"))
        ),
        "safe_fusion_full_vs_flat_recall": audit.exact_paired_sign_flip_test(
            s - f for s, f in zip(recalls("safe_fusion_full"), recalls("flat"))
        ),
        "safe_fusion_full_vs_tfidf_knn_lite_graph_recall": audit.exact_paired_sign_flip_test(
            s - l for s, l in zip(recalls("safe_fusion_full"), recalls("tfidf_knn_lite_graph"))
        ),
    }

    return {
        "experiment_type": "graphrag_lite_matched_baseline",
        "scope_note": (
            "Seven-run matched retrieval-stage replay against survey-reference external proxy targets. "
            "The TF-IDF kNN graph is a lightweight GraphRAG-style baseline built only from local paper text, "
            "then evaluated with the same section budget as the typed MEKG variants. This is not full-paper "
            "generation parity and should be read as a retrieval-stage matched baseline."
        ),
        "top_k_per_section": 5,
        "tfidf_knn_top_neighbors": 5,
        "tfidf_knn_min_similarity": 0.05,
        "run_count": len(per_topic),
        "topics": per_topic,
        "aggregate": aggregate,
        "pairwise": pairwise,
    }


def build_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# GraphRAG-lite Matched Baseline",
        "",
        f"- Runs used: {payload['run_count']}",
        f"- Top-k per section: {payload['top_k_per_section']}",
        f"- TF-IDF kNN neighbors: {payload['tfidf_knn_top_neighbors']}",
        "",
        "| Method | R@5 | P@5 | MEKG density | Active graph density | Unique papers | Active rels | Local sec |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, row in payload["aggregate"].items():
        lines.append(
            f"| {method} | {row['mean_recall_top5']:.3f} | {row['mean_precision_top5']:.3f} | "
            f"{row['mean_relation_density_top5']:.3f} | {row['mean_active_graph_density_top5']:.3f} | "
            f"{row['mean_unique_papers_top5']:.1f} | {row['mean_active_relations']:.1f} | "
            f"{row['mean_retrieval_seconds']:.4f} |"
        )

    lines.extend(
        [
            "",
            "| Topic | Flat R@5 | TF-IDF kNN R@5 | Structural R@5 | Full MEKG R@5 | Safe fusion R@5 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for topic in payload["topics"]:
        m = topic["methods"]
        lines.append(
            f"| {topic['topic']} | "
            f"{m['flat']['external_proxy_recall_top5']:.3f} | "
            f"{m['tfidf_knn_lite_graph']['external_proxy_recall_top5']:.3f} | "
            f"{m['structural_graph']['external_proxy_recall_top5']:.3f} | "
            f"{m['full_mekg']['external_proxy_recall_top5']:.3f} | "
            f"{m['safe_fusion_full']['external_proxy_recall_top5']:.3f} |"
        )
    lines.extend(["", "## Pairwise sign-flip tests"])
    for name, row in payload["pairwise"].items():
        lines.append(
            f"- {name}: mean Δ={row['observed_mean_delta']:.3f}, "
            f"+/{row['sample_size']}={row['positive_pairs']}, "
            f"-/{row['sample_size']}={row['negative_pairs']}, "
            f"one-sided p={row['one_sided_p_greater']:.4f}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_eval()
    (OUTPUT_DIR / "graphrag_lite_matched_baseline.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "graphrag_lite_matched_baseline.md").write_text(
        build_markdown(payload),
        encoding="utf-8",
    )
    print(f"Wrote outputs to {OUTPUT_DIR}")
    print((OUTPUT_DIR / "graphrag_lite_matched_baseline.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
