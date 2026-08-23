from __future__ import annotations

import json
import math
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit
from experiments import review_response_audit as review

OUTPUT_DIR = ROOT / "outputs" / "bibliometric_rerank_baseline_20260526"
OPENALEX_MATCHES = ROOT / "outputs" / "openalex_citation_core_audit_20260525" / "openalex_title_matches.json"


def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _norm_title(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _load_openalex_matches() -> Dict[str, Any]:
    if not OPENALEX_MATCHES.exists():
        return {}
    return json.loads(OPENALEX_MATCHES.read_text(encoding="utf-8"))


def _openalex_citation_map(
    papers: List[Dict[str, Any]],
    matches: Dict[str, Any],
) -> Tuple[Dict[str, int], Dict[str, bool]]:
    citations: Dict[str, int] = {}
    matched: Dict[str, bool] = {}
    for paper in papers:
        pid = audit.sanitize_key(paper.get("id", ""))
        row = matches.get(_norm_title(paper.get("title", "")), {})
        is_match = bool(row.get("matched"))
        matched[pid] = is_match
        citations[pid] = int(row.get("cited_by_count") or 0) if is_match else 0
    return citations, matched


def _quality_scores(
    papers: List[Dict[str, Any]],
    citation_map: Dict[str, int],
) -> Dict[str, Dict[str, float]]:
    years = [
        int(paper.get("year"))
        for paper in papers
        if isinstance(paper.get("year"), int) and 1900 < int(paper.get("year")) <= 2026
    ]
    min_year = min(years) if years else 2014
    max_year = max(years) if years else 2026
    year_range = max(max_year - min_year, 1)
    max_citation = max(citation_map.values()) if citation_map else 0

    out: Dict[str, Dict[str, float]] = {}
    for paper in papers:
        pid = audit.sanitize_key(paper.get("id", ""))
        citation = citation_map.get(pid, 0)
        year = paper.get("year", max_year)
        if not isinstance(year, int) or year < 1900 or year > 2026:
            year = max_year
        title = paper.get("title", "") or ""
        title_lower = title.lower()
        # Lightweight quality/role prior: surveys and benchmarks are useful
        # orientation papers, but this baseline is deliberately graph-free.
        role_prior = 0.0
        if re.search(r"\b(survey|review|taxonomy)\b", title_lower):
            role_prior = 1.0
        elif re.search(r"\b(benchmark|bench|dataset|corpus|leaderboard|evaluation)\b", title_lower):
            role_prior = 0.7
        elif re.search(r"\b(framework|system|method|model|agent|rag|graph)\b", title_lower):
            role_prior = 0.4
        citation_norm = math.log1p(citation) / math.log1p(max_citation) if max_citation > 0 else 0.0
        recency = (year - min_year) / year_range
        quality = 0.55 * citation_norm + 0.30 * recency + 0.15 * role_prior
        out[pid] = {
            "citation_norm": citation_norm,
            "recency": recency,
            "role_prior": role_prior,
            "quality": quality,
            "citation_count": float(citation),
        }
    return out


def _normalize_rank_scores(rows: List[Tuple[str, float]]) -> Dict[str, float]:
    values = [float(score) for _, score in rows]
    if not values:
        return {}
    lo = min(values)
    hi = max(values)
    if hi <= lo:
        return {pid: 0.0 for pid, _ in rows}
    return {pid: (float(score) - lo) / (hi - lo) for pid, score in rows}


def _quality_rank(quality: Dict[str, Dict[str, float]]) -> List[Tuple[str, float]]:
    return sorted(
        ((pid, row["quality"]) for pid, row in quality.items()),
        key=lambda x: x[1],
        reverse=True,
    )


def _make_bibliometric_rankers(
    papers: List[Dict[str, Any]],
    idf: Dict[str, float],
    quality: Dict[str, Dict[str, float]],
):
    flat_rank = audit.make_flat_ranker(papers, idf)
    q_rank = _quality_rank(quality)
    q_rank_pos = {pid: idx for idx, (pid, _score) in enumerate(q_rank)}

    def quality_only(_title: str, _desc: str) -> List[Tuple[str, float]]:
        return q_rank

    def rerank_top20(title: str, desc: str) -> List[Tuple[str, float]]:
        base = flat_rank(title, desc)
        base_norm = _normalize_rank_scores(base)
        candidates = base[:20]
        scored = [
            (
                pid,
                0.70 * base_norm.get(pid, 0.0) + 0.30 * quality.get(pid, {}).get("quality", 0.0),
            )
            for pid, _score in candidates
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def flat_plus_quality(title: str, desc: str) -> List[Tuple[str, float]]:
        base = flat_rank(title, desc)
        base_norm = _normalize_rank_scores(base)
        scored = [
            (
                pid,
                0.80 * base_norm.get(pid, 0.0) + 0.20 * quality.get(pid, {}).get("quality", 0.0),
            )
            for pid, _score in base
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def lexical_biblio_rrf(title: str, desc: str) -> List[Tuple[str, float]]:
        base = flat_rank(title, desc)
        base_pos = {pid: idx for idx, (pid, _score) in enumerate(base)}
        scored = []
        for pid, _score in base:
            # RRF keeps the query-specific lexical rank dominant while allowing
            # high-citation/recency papers to break ties.
            score = 1.0 / (60.0 + base_pos[pid]) + 0.45 / (60.0 + q_rank_pos.get(pid, len(q_rank)))
            scored.append((pid, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    return {
        "flat": flat_rank,
        "openalex_quality_only": quality_only,
        "bibliometric_rerank_top20": rerank_top20,
        "flat_plus_quality": flat_plus_quality,
        "lexical_biblio_rrf": lexical_biblio_rrf,
    }


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
    relation_pairs: set[Tuple[str, str]],
    quality: Dict[str, Dict[str, float]],
    matched: Dict[str, bool],
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
        "relation_density_top5": _density(unique_ids, relation_pairs),
        "mean_quality_score_top5": _mean(quality.get(pid, {}).get("quality", 0.0) for pid in unique_ids),
        "mean_openalex_citations_top5": _mean(quality.get(pid, {}).get("citation_count", 0.0) for pid in unique_ids),
        "openalex_match_rate_top5": _mean(1.0 if matched.get(pid, False) else 0.0 for pid in unique_ids),
        "retrieval_seconds": elapsed,
    }


def build_eval() -> Dict[str, Any]:
    matches = _load_openalex_matches()
    runs = [
        run
        for run in audit.load_archived_runs()
        if len(review.collect_survey_reference_targets(run)["external_target_ids"]) >= 3
    ]

    per_topic: List[Dict[str, Any]] = []
    aggregate_rows: Dict[str, List[Dict[str, Any]]] = {}

    for run in runs:
        target_info = review.collect_survey_reference_targets(run)
        target_ids = {audit.sanitize_key(pid) for pid in target_info["external_target_ids"]}
        context = audit.build_retrieval_context(run)
        papers = context["papers"]
        paper_map = context["paper_map"]
        idf = context["idf"]
        _adj, relation_pairs = audit.build_adjacency(run, paper_map)
        citation_map, matched = _openalex_citation_map(papers, matches)
        quality = _quality_scores(papers, citation_map)
        rankers = _make_bibliometric_rankers(papers, idf, quality)

        topic_row: Dict[str, Any] = {
            "topic": run.label,
            "run_id": run.run_id,
            "external_proxy_target_size": len(target_ids),
            "source_survey_count": target_info["source_survey_count"],
            "openalex_title_match_rate": _mean(1.0 if v else 0.0 for v in matched.values()),
            "openalex_nonzero_citation_rate": _mean(1.0 if c > 0 else 0.0 for c in citation_map.values()),
            "methods": {},
        }

        for name, ranker in rankers.items():
            result = _evaluate_ranker(run, ranker, target_ids, relation_pairs, quality, matched)
            topic_row["methods"][name] = result
            aggregate_rows.setdefault(name, []).append(result)
        per_topic.append(topic_row)

    aggregate: Dict[str, Any] = {}
    for name, rows in aggregate_rows.items():
        aggregate[name] = {
            "topic_count": len(rows),
            "mean_recall_top5": _mean(row["external_proxy_recall_top5"] for row in rows),
            "mean_precision_top5": _mean(row["external_proxy_precision_top5"] for row in rows),
            "mean_relation_density_top5": _mean(row["relation_density_top5"] for row in rows),
            "mean_quality_score_top5": _mean(row["mean_quality_score_top5"] for row in rows),
            "mean_openalex_citations_top5": _mean(row["mean_openalex_citations_top5"] for row in rows),
            "mean_openalex_match_rate_top5": _mean(row["openalex_match_rate_top5"] for row in rows),
            "mean_retrieval_seconds": _mean(row["retrieval_seconds"] for row in rows),
        }

    pairwise = {}
    flat_rows = aggregate_rows.get("flat", [])
    for name, rows in aggregate_rows.items():
        if name == "flat" or len(rows) != len(flat_rows):
            continue
        pairwise[f"{name}_vs_flat_recall"] = audit.exact_paired_sign_flip_test(
            row["external_proxy_recall_top5"] - base["external_proxy_recall_top5"]
            for row, base in zip(rows, flat_rows)
        )
        pairwise[f"{name}_vs_flat_precision"] = audit.exact_paired_sign_flip_test(
            row["external_proxy_precision_top5"] - base["external_proxy_precision_top5"]
            for row, base in zip(rows, flat_rows)
        )

    return {
        "experiment_type": "bibliometric_rerank_baseline",
        "scope_note": (
            "Equal-budget retrieval-stage baseline that adds OpenAlex title-matched citation counts, recency, "
            "and lightweight paper-role priors without using MEKG edges. It is a quality-aware reranking proxy, "
            "not a full SurveyGen/QUAL-SG reproduction."
        ),
        "openalex_matches_path": str(OPENALEX_MATCHES.relative_to(ROOT)) if OPENALEX_MATCHES.exists() else None,
        "run_count": len(per_topic),
        "top_k_per_section": 5,
        "methods": list(aggregate_rows),
        "per_topic": per_topic,
        "aggregate": aggregate,
        "pairwise": pairwise,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_eval()
    (OUTPUT_DIR / "bibliometric_rerank_baseline.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    agg = payload["aggregate"]
    lines = [
        "# Bibliometric / Quality-Aware Rerank Baseline",
        "",
        f"- Runs used: {payload['run_count']}",
        f"- Top-k per section: {payload['top_k_per_section']}",
        f"- OpenAlex source: `{payload['openalex_matches_path']}`",
        "",
        "| Method | R@5 | P@5 | MEKG density | Quality | Citations | OA match | sec |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in payload["methods"]:
        row = agg[name]
        lines.append(
            "| {name} | {r:.3f} | {p:.3f} | {d:.3f} | {q:.3f} | {c:.1f} | {m:.3f} | {s:.4f} |".format(
                name=name.replace("_", "\\_"),
                r=row["mean_recall_top5"],
                p=row["mean_precision_top5"],
                d=row["mean_relation_density_top5"],
                q=row["mean_quality_score_top5"],
                c=row["mean_openalex_citations_top5"],
                m=row["mean_openalex_match_rate_top5"],
                s=row["mean_retrieval_seconds"],
            )
        )
    lines.extend(
        [
            "",
            "Interpretation: this baseline tests whether a graph-free quality signal (OpenAlex citation proxy + recency + role prior) "
            "is sufficient under the same section-level retrieval budget. It should be read as a matched quality-aware retrieval "
            "baseline, not as a full bibliometric survey-generation system.",
        ]
    )
    (OUTPUT_DIR / "bibliometric_rerank_baseline.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
