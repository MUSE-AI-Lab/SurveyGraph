from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import bibliometric_rerank_baseline as bib
from experiments import graphrag_lite_matched_baseline as lite
from experiments import offline_real_revision_audit as audit
from experiments import review_response_audit as review

OUTPUT_DIR = ROOT / "outputs" / "matched_quality_graph_mini_benchmark_20260526"


def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _density(ids: List[str], pairs: set[Tuple[str, str]]) -> float:
    pair_total = 0
    linked = 0
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            pair_total += 1
            if tuple(sorted((ids[i], ids[j]))) in pairs:
                linked += 1
    return linked / pair_total if pair_total else 0.0


def _section_alignment(
    section_title: str,
    section_desc: str,
    chosen: List[str],
    paper_map: Dict[str, Dict[str, Any]],
) -> float:
    query_tokens = set(audit.tokenize(f"{section_title} {section_desc}"))
    if not query_tokens:
        return 0.0
    evidence_tokens: set[str] = set()
    for pid in chosen:
        paper = paper_map.get(pid, {})
        evidence_tokens.update(audit.tokenize(f"{paper.get('title', '')} {paper.get('abstract', '')}"))
    return len(query_tokens & evidence_tokens) / len(query_tokens)


def _safe_fusion_ranker(base_ranker, expansion_ranker, preserve_base: int = 3):
    def rank(title: str, desc: str) -> List[Tuple[str, float]]:
        base = base_ranker(title, desc)
        expanded = expansion_ranker(title, desc)
        out: List[Tuple[str, float]] = []
        seen: set[str] = set()
        for pid, score in base[:preserve_base]:
            out.append((pid, float(score) + 1_000_000.0))
            seen.add(pid)
        for pid, score in expanded:
            if pid not in seen:
                out.append((pid, float(score)))
                seen.add(pid)
        return out

    return rank


def _evaluate_method(
    run: audit.RunBundle,
    method_name: str,
    ranker,
    target_ids: set[str],
    paper_map: Dict[str, Dict[str, Any]],
    full_pairs: set[Tuple[str, str]],
    active_pairs: set[Tuple[str, str]],
    quality: Dict[str, Dict[str, float]],
    top_k: int = 5,
) -> Dict[str, Any]:
    started = time.perf_counter()
    all_slots = 0
    union_ids: List[str] = []
    section_rows: List[Dict[str, Any]] = []
    alignments: List[float] = []
    for section in run.outline.get("sections", []):
        title = section.get("title", "")
        if title in audit.SECTION_EXCLUDE_TITLES:
            continue
        desc = section.get("description", "")
        ranked = ranker(title, desc)
        chosen = [pid for pid, _score in ranked[:top_k]]
        all_slots += len(chosen)
        union_ids.extend(chosen)
        alignments.append(_section_alignment(title, desc, chosen, paper_map))
        section_rows.append({"title": title, "top_k_ids": chosen})
    elapsed = time.perf_counter() - started

    unique_ids = list(dict.fromkeys(union_ids))
    hits = set(unique_ids) & target_ids
    return {
        "method": method_name,
        "sections_evaluated": len(section_rows),
        "total_slots": all_slots,
        "unique_papers_top5": len(unique_ids),
        "duplicate_rate_top5": 1.0 - (len(unique_ids) / all_slots) if all_slots else 0.0,
        "hit_count_top5": len(hits),
        "external_proxy_recall_top5": len(hits) / len(target_ids) if target_ids else 0.0,
        "external_proxy_precision_top5": len(hits) / len(unique_ids) if unique_ids else 0.0,
        "section_evidence_alignment": _mean(alignments),
        "full_mekg_relation_density_top5": _density(unique_ids, full_pairs),
        "active_graph_density_top5": _density(unique_ids, active_pairs),
        "mean_quality_score_top5": _mean(quality.get(pid, {}).get("quality", 0.0) for pid in unique_ids),
        "mean_openalex_citations_top5": _mean(quality.get(pid, {}).get("citation_count", 0.0) for pid in unique_ids),
        "retrieval_seconds": elapsed,
        "section_rows": section_rows,
    }


def build_benchmark() -> Dict[str, Any]:
    matches = bib._load_openalex_matches()
    runs = [
        run
        for run in audit.load_archived_runs()
        if len(review.collect_survey_reference_targets(run)["external_target_ids"]) >= 3
    ]

    per_topic: List[Dict[str, Any]] = []
    method_rows: Dict[str, List[Dict[str, Any]]] = {}

    for run in runs:
        target_info = review.collect_survey_reference_targets(run)
        target_ids = {audit.sanitize_key(pid) for pid in target_info["external_target_ids"]}
        context = audit.build_retrieval_context(run)
        papers = context["papers"]
        paper_map = context["paper_map"]
        idf = context["idf"]

        full_adj, full_pairs = audit.build_adjacency(run, paper_map)
        lite_adj, lite_pairs = lite._build_tfidf_knn_graph(papers)
        citation_map, _matched = bib._openalex_citation_map(papers, matches)
        quality = bib._quality_scores(papers, citation_map)

        biblio_rankers = bib._make_bibliometric_rankers(papers, idf, quality)
        flat_rank = biblio_rankers["flat"]
        biblio_rrf = biblio_rankers["lexical_biblio_rrf"]
        tfidf_graph = lite._graph_ranker_from_adjacency(papers, paper_map, idf, lite_adj)
        full_mekg = lite._graph_ranker_from_adjacency(papers, paper_map, idf, full_adj)

        methods = {
            "flat": (flat_rank, set()),
            "bibliometric_rrf": (biblio_rrf, set()),
            "tfidf_graphrag_lite": (tfidf_graph, lite_pairs),
            "surveygraph_full_mekg": (full_mekg, full_pairs),
            "safe_fusion_full_mekg": (_safe_fusion_ranker(flat_rank, full_mekg, preserve_base=3), full_pairs),
            "safe_fusion_biblio_tfidf": (_safe_fusion_ranker(biblio_rrf, tfidf_graph, preserve_base=3), lite_pairs),
            "safe_fusion_biblio_mekg": (_safe_fusion_ranker(biblio_rrf, full_mekg, preserve_base=3), full_pairs),
        }

        topic_row: Dict[str, Any] = {
            "topic": run.label,
            "run_id": run.run_id,
            "external_proxy_target_size": len(target_ids),
            "source_survey_count": target_info["source_survey_count"],
            "methods": {},
        }
        for name, (ranker, active_pairs) in methods.items():
            result = _evaluate_method(
                run,
                name,
                ranker,
                target_ids,
                paper_map,
                full_pairs,
                active_pairs,
                quality,
            )
            topic_row["methods"][name] = result
            method_rows.setdefault(name, []).append(result)
        per_topic.append(topic_row)

    aggregate: Dict[str, Dict[str, Any]] = {}
    for name, rows in method_rows.items():
        aggregate[name] = {
            "topic_count": len(rows),
            "mean_recall_top5": _mean(row["external_proxy_recall_top5"] for row in rows),
            "mean_precision_top5": _mean(row["external_proxy_precision_top5"] for row in rows),
            "mean_section_evidence_alignment": _mean(row["section_evidence_alignment"] for row in rows),
            "mean_duplicate_rate_top5": _mean(row["duplicate_rate_top5"] for row in rows),
            "mean_full_mekg_relation_density_top5": _mean(row["full_mekg_relation_density_top5"] for row in rows),
            "mean_active_graph_density_top5": _mean(row["active_graph_density_top5"] for row in rows),
            "mean_quality_score_top5": _mean(row["mean_quality_score_top5"] for row in rows),
            "mean_openalex_citations_top5": _mean(row["mean_openalex_citations_top5"] for row in rows),
            "mean_retrieval_seconds": _mean(row["retrieval_seconds"] for row in rows),
        }

    pairwise: Dict[str, Any] = {}
    flat_rows = method_rows.get("flat", [])
    for name, rows in method_rows.items():
        if name == "flat" or len(rows) != len(flat_rows):
            continue
        pairwise[f"{name}_vs_flat_recall"] = audit.exact_paired_sign_flip_test(
            row["external_proxy_recall_top5"] - base["external_proxy_recall_top5"]
            for row, base in zip(rows, flat_rows)
        )
        pairwise[f"{name}_vs_flat_alignment"] = audit.exact_paired_sign_flip_test(
            row["section_evidence_alignment"] - base["section_evidence_alignment"]
            for row, base in zip(rows, flat_rows)
        )

    return {
        "experiment_type": "matched_quality_graph_mini_benchmark",
        "scope_note": (
            "Seven-run equal-budget retrieval-to-outline mini benchmark. Each method sees the same archived section queries "
            "and returns top-5 papers per section; metrics are survey-reference weak-proxy recall/precision, section-evidence "
            "lexical alignment, duplicate rate, MEKG relation density, and OpenAlex quality proxies. This is stronger than an "
            "artifact-only comparison but remains retrieval-stage, not a full public benchmark."
        ),
        "run_count": len(per_topic),
        "top_k_per_section": 5,
        "methods": list(method_rows),
        "per_topic": per_topic,
        "aggregate": aggregate,
        "pairwise": pairwise,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_benchmark()
    (OUTPUT_DIR / "matched_quality_graph_mini_benchmark.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Matched Quality/Graph Mini-Benchmark",
        "",
        f"- Runs used: {payload['run_count']}",
        f"- Equal budget: top-{payload['top_k_per_section']} per section",
        "",
        "| Method | R@5 | P@5 | Align | Dup. | MEKG dens. | Active dens. | Quality | Cit. | sec |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in payload["methods"]:
        row = payload["aggregate"][name]
        lines.append(
            "| {name} | {r:.3f} | {p:.3f} | {a:.3f} | {dup:.3f} | {d:.3f} | {ad:.3f} | {q:.3f} | {c:.1f} | {s:.4f} |".format(
                name=name.replace("_", "\\_"),
                r=row["mean_recall_top5"],
                p=row["mean_precision_top5"],
                a=row["mean_section_evidence_alignment"],
                dup=row["mean_duplicate_rate_top5"],
                d=row["mean_full_mekg_relation_density_top5"],
                ad=row["mean_active_graph_density_top5"],
                q=row["mean_quality_score_top5"],
                c=row["mean_openalex_citations_top5"],
                s=row["mean_retrieval_seconds"],
            )
        )
    lines.extend(
        [
            "",
            "Interpretation: this table puts flat retrieval, a quality-aware bibliometric baseline, TF-IDF GraphRAG-lite, "
            "SurveyGraph typed MEKG, and safe-fusion variants under the same section queries and top-k budget.",
        ]
    )
    (OUTPUT_DIR / "matched_quality_graph_mini_benchmark.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
