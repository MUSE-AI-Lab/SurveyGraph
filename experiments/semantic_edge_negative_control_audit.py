from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Sequence, Set

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as base
from experiments.semantic_edge_validation_extension import target_role_ok

OUT = ROOT / "outputs" / "semantic_edge_negative_control_audit_20260525"

EXTRA_STOPWORDS = {
    "large",
    "language",
    "languages",
    "model",
    "models",
    "using",
    "based",
    "towards",
    "survey",
    "via",
    "new",
    "novel",
    "approach",
    "approaches",
    "framework",
    "frameworks",
    "method",
    "methods",
    "benchmark",
    "benchmarks",
    "evaluation",
    "evaluating",
    "study",
    "studies",
    "paper",
    "papers",
    "llm",
    "llms",
    "agent",
    "agents",
}

STOPWORDS = set(base.SECTION_STOPWORDS) | EXTRA_STOPWORDS


def toks(text: str) -> Set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9\-]+", (text or "").lower())
        if len(token) > 2 and token not in STOPWORDS
    }


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def summarize_scores(rows: Sequence[Dict[str, Any]], control_key: str) -> Dict[str, Any]:
    edge_scores = [float(r["edge_score"]) for r in rows]
    control_scores = [float(r[control_key]) for r in rows]
    deltas = [a - b for a, b in zip(edge_scores, control_scores)]
    return {
        "pairs": len(rows),
        "edge_mean": mean(edge_scores) if edge_scores else 0.0,
        "control_mean": mean(control_scores) if control_scores else 0.0,
        "edge_median": median(edge_scores) if edge_scores else 0.0,
        "control_median": median(control_scores) if control_scores else 0.0,
        "mean_delta": mean(deltas) if deltas else 0.0,
        "edge_gt_control": sum(1 for d in deltas if d > 0),
        "control_gt_edge": sum(1 for d in deltas if d < 0),
        "ties": sum(1 for d in deltas if d == 0),
    }


def exact_test_from_run_deltas(run_deltas: Iterable[float]) -> Dict[str, Any]:
    return base.exact_paired_sign_flip_test(list(run_deltas))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    per_run: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

    for run in base.load_archived_runs():
        papers = {paper.get("id"): paper for paper in run.mekg.get("papers", [])}
        paper_tokens = {
            paper_id: toks((paper.get("title", "") or "") + " " + (paper.get("abstract", "") or ""))
            for paper_id, paper in papers.items()
        }
        semantic_edges = [
            rel
            for rel in run.mekg.get("relations", [])
            if rel.get("type") in base.SEMANTIC_RELATIONS
            and rel.get("source") in papers
            and rel.get("target") in papers
        ]
        existing_any = {(rel.get("source"), rel.get("target")) for rel in semantic_edges}

        for edge_index, rel in enumerate(semantic_edges):
            rel_type = rel.get("type")
            source_id = rel.get("source")
            target_id = rel.get("target")
            if source_id not in papers or target_id not in papers:
                continue
            source = papers[source_id]
            target = papers[target_id]
            source_tokens = paper_tokens[source_id]
            edge_score = jaccard(source_tokens, paper_tokens[target_id])

            matched_candidates: List[str] = []
            easy_candidates: List[str] = []
            source_year = source.get("year")
            target_role_flag = target_role_ok(rel_type, target.get("title", ""))
            for candidate_id, candidate in papers.items():
                if candidate_id == source_id or (source_id, candidate_id) in existing_any:
                    continue
                easy_candidates.append(candidate_id)
                candidate_year = candidate.get("year")
                if isinstance(source_year, int) and isinstance(candidate_year, int) and candidate_year > source_year:
                    continue
                if target_role_ok(rel_type, candidate.get("title", "")) != target_role_flag:
                    continue
                matched_candidates.append(candidate_id)

            if not matched_candidates or not easy_candidates:
                continue

            matched_candidates = sorted(matched_candidates, key=lambda pid: (papers[pid].get("title", ""), pid))
            matched_control_id = matched_candidates[(edge_index * 17 + len(rel_type)) % len(matched_candidates)]
            easy_control_id = min(easy_candidates, key=lambda pid: jaccard(source_tokens, paper_tokens[pid]))

            matched_score = jaccard(source_tokens, paper_tokens[matched_control_id])
            easy_score = jaccard(source_tokens, paper_tokens[easy_control_id])
            row = {
                "run_id": run.run_id,
                "relation_type": rel_type,
                "source_title": source.get("title", ""),
                "target_title": target.get("title", ""),
                "matched_control_title": papers[matched_control_id].get("title", ""),
                "easy_control_title": papers[easy_control_id].get("title", ""),
                "edge_score": edge_score,
                "matched_control_score": matched_score,
                "easy_control_score": easy_score,
                "edge_minus_matched": edge_score - matched_score,
                "edge_minus_easy": edge_score - easy_score,
            }
            rows.append(row)
            per_run[run.run_id]["edge"].append(edge_score)
            per_run[run.run_id]["matched"].append(matched_score)
            per_run[run.run_id]["easy"].append(easy_score)

    by_relation: Dict[str, Dict[str, Any]] = {}
    for rel_type in base.SEMANTIC_RELATIONS:
        rel_rows = [row for row in rows if row["relation_type"] == rel_type]
        by_relation[rel_type] = {
            "matched_control": summarize_scores(rel_rows, "matched_control_score"),
            "easy_control": summarize_scores(rel_rows, "easy_control_score"),
        }

    run_summaries = []
    for run_id, values in per_run.items():
        edge_mean = mean(values["edge"])
        matched_mean = mean(values["matched"])
        easy_mean = mean(values["easy"])
        run_summaries.append(
            {
                "run_id": run_id,
                "pairs": len(values["edge"]),
                "edge_mean": edge_mean,
                "matched_control_mean": matched_mean,
                "easy_control_mean": easy_mean,
                "edge_minus_matched_mean": edge_mean - matched_mean,
                "edge_minus_easy_mean": edge_mean - easy_mean,
            }
        )

    result = {
        "experiment_type": "semantic_edge_negative_control_audit",
        "scope_note": (
            "Deterministic zero-API negative-control audit over archived semantic edges. "
            "For each saved extends/improves/applies edge, we compare lexical overlap of the observed source-target pair "
            "against (i) a temporally and target-role matched non-edge control from the same archived corpus and "
            "(ii) an intentionally easy low-overlap non-edge control. This tests whether local lexical evidence alone "
            "separates semantic edges from non-edges; it is not a human precision/recall estimate."
        ),
        "pair_count": len(rows),
        "overall": {
            "matched_control": summarize_scores(rows, "matched_control_score"),
            "easy_control": summarize_scores(rows, "easy_control_score"),
            "matched_control_run_sign_test": exact_test_from_run_deltas(
                row["edge_minus_matched_mean"] for row in run_summaries
            ),
            "easy_control_run_sign_test": exact_test_from_run_deltas(
                row["edge_minus_easy_mean"] for row in run_summaries
            ),
        },
        "by_relation": by_relation,
        "per_run": run_summaries,
        "first_20_rows": rows[:20],
    }

    (OUT / "semantic_edge_negative_control_audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    overall = result["overall"]
    lines = [
        "# Semantic Edge Negative-Control Audit",
        "",
        f"- Semantic edges with controls: {len(rows)}",
        "- Matched controls: non-edge papers from the same archived run, constrained to temporal direction and target-role compatibility.",
        "- Easy controls: deliberately low-overlap non-edge papers from the same archived run.",
        "",
        "| Control | Edge mean | Control mean | Mean delta | Edge > control | Control > edge | Run sign p (one-sided) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, key, test_key in [
        ("Matched non-edge", "matched_control", "matched_control_run_sign_test"),
        ("Easy non-edge", "easy_control", "easy_control_run_sign_test"),
    ]:
        summary = overall[key]
        test = overall[test_key]
        lines.append(
            f"| {label} | {summary['edge_mean']:.4f} | {summary['control_mean']:.4f} | "
            f"{summary['mean_delta']:.4f} | {summary['edge_gt_control']} | {summary['control_gt_edge']} | "
            f"{test['one_sided_p_greater']:.4f} |"
        )
    lines.extend(
        [
            "",
            "> The matched-control contrast is intentionally hard and nearly tied, showing that lexical overlap alone is not a sufficient semantic-edge validator. The easy-control contrast only rules out arbitrary low-overlap links.",
        ]
    )
    (OUT / "semantic_edge_negative_control_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(result["overall"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
