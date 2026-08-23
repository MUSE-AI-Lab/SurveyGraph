from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as base
from experiments.semantic_edge_negative_control_audit import jaccard, toks
from experiments.semantic_edge_validation_extension import target_role_ok

OUTPUT_DIR = ROOT / "outputs" / "semantic_edge_stratified_protocol_audit_20260526"
RELATIONS = tuple(base.SEMANTIC_RELATIONS)
BUCKET_ORDER = ("low", "mid", "high")
SAMPLES_PER_STRATUM = 8
ROLE_RE = re.compile(r"\b(survey|review|benchmark|bench|dataset|corpus|leaderboard|evaluation|challenge)\b", re.I)


def confidence_bucket(confidence: float) -> str:
    if confidence < 0.7:
        return "low"
    if confidence < 0.85:
        return "mid"
    return "high"


def _failure_mode(row: Dict[str, Any]) -> str:
    if not row["temporal_ok"]:
        return "temporal_reversal"
    if not row["target_role_ok"]:
        return "target_role_mismatch"
    if row["matched_control_delta"] <= 0 and not row["source_cue"]:
        return "weak_lineage_signal"
    if row["matched_control_delta"] <= 0:
        return "lexical_overlap_not_better_than_matched_control"
    if not row["source_cue"]:
        return "missing_explicit_source_cue"
    return "well_supported_under_protocol"


def protocol_label(row: Dict[str, Any]) -> str:
    if row["temporal_ok"] and row["target_role_ok"] and row["source_cue"] and row["matched_control_delta"] > 0:
        return "supported"
    if row["temporal_ok"] and row["target_role_ok"] and (row["source_cue"] or row["matched_control_delta"] > 0):
        return "partial"
    return "unsupported"


def _iter_semantic_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for run in base.load_archived_runs():
        papers = {paper.get("id"): paper for paper in run.mekg.get("papers", [])}
        paper_tokens = {
            paper_id: toks((paper.get("title", "") or "") + " " + (paper.get("abstract", "") or ""))
            for paper_id, paper in papers.items()
        }
        semantic_edges = [
            rel
            for rel in run.mekg.get("relations", [])
            if rel.get("type") in RELATIONS
            and rel.get("source") in papers
            and rel.get("target") in papers
        ]
        existing_any = {(rel.get("source"), rel.get("target")) for rel in semantic_edges}

        for edge_index, rel in enumerate(semantic_edges):
            rel_type = rel.get("type", "")
            source_id = rel.get("source")
            target_id = rel.get("target")
            source = papers.get(source_id)
            target = papers.get(target_id)
            if not source or not target:
                continue

            confidence = float(rel.get("confidence", 0.0) or 0.0)
            src_year = source.get("year")
            tgt_year = target.get("year")
            temporal_ok = isinstance(src_year, int) and isinstance(tgt_year, int) and src_year >= tgt_year
            source_cue = base.source_cue_present(rel_type, source.get("title", ""), source.get("abstract", ""))
            role_ok = target_role_ok(rel_type, target.get("title", ""))

            source_tokens = paper_tokens[source_id]
            target_tokens = paper_tokens[target_id]
            edge_score = jaccard(source_tokens, target_tokens)
            target_role_flag = role_ok

            matched_candidates: List[str] = []
            for candidate_id, candidate in papers.items():
                if candidate_id == source_id or (source_id, candidate_id) in existing_any:
                    continue
                candidate_year = candidate.get("year")
                if isinstance(src_year, int) and isinstance(candidate_year, int) and candidate_year > src_year:
                    continue
                if target_role_ok(rel_type, candidate.get("title", "")) != target_role_flag:
                    continue
                matched_candidates.append(candidate_id)

            if not matched_candidates:
                continue

            matched_candidates = sorted(
                matched_candidates,
                key=lambda pid: (papers[pid].get("title", ""), pid),
            )
            matched_control_id = matched_candidates[(edge_index * 17 + len(rel_type)) % len(matched_candidates)]
            matched_score = jaccard(source_tokens, paper_tokens[matched_control_id])

            row = {
                "run_id": run.run_id,
                "run_label": run.label,
                "relation_type": rel_type,
                "source_title": source.get("title", ""),
                "target_title": target.get("title", ""),
                "source_year": src_year,
                "target_year": tgt_year,
                "confidence": confidence,
                "confidence_bucket": confidence_bucket(confidence),
                "temporal_ok": bool(temporal_ok),
                "source_cue": bool(source_cue),
                "target_role_ok": bool(role_ok),
                "edge_lexical_overlap": edge_score,
                "matched_control_title": papers[matched_control_id].get("title", ""),
                "matched_control_overlap": matched_score,
                "matched_control_delta": edge_score - matched_score,
                "target_role_triggered": bool(ROLE_RE.search(target.get("title", "") or "")),
            }
            row["protocol_label"] = protocol_label(row)
            row["failure_mode"] = _failure_mode(row)
            rows.append(row)
    return rows


def _select_stratified_sample(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sampled: List[Dict[str, Any]] = []
    for rel_type in RELATIONS:
        for bucket in BUCKET_ORDER:
            bucket_rows = [
                row for row in rows
                if row["relation_type"] == rel_type and row["confidence_bucket"] == bucket
            ]
            bucket_rows = sorted(
                bucket_rows,
                key=lambda row: (
                    row["run_id"],
                    row["source_title"],
                    row["target_title"],
                ),
            )
            if not bucket_rows:
                continue
            for idx in range(SAMPLES_PER_STRATUM):
                base_row = dict(bucket_rows[idx % len(bucket_rows)])
                base_row["sample_repeat_index"] = idx // len(bucket_rows)
                sampled.append(base_row)
    return sampled


def _summarize(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    out = {"supported": 0, "partial": 0, "unsupported": 0, "total": 0}
    for row in rows:
        out[row["protocol_label"]] += 1
        out["total"] += 1
    return out


def build_audit() -> Dict[str, Any]:
    all_rows = _iter_semantic_rows()
    sampled = _select_stratified_sample(all_rows)

    by_relation: Dict[str, Dict[str, Any]] = {}
    for rel_type in RELATIONS:
        rel_rows = [row for row in sampled if row["relation_type"] == rel_type]
        summary = _summarize(rel_rows)
        summary.update(
            {
                "supported_or_partial_rate": (
                    (summary["supported"] + summary["partial"]) / summary["total"] if summary["total"] else 0.0
                ),
                "matched_control_win_rate": mean([row["matched_control_delta"] > 0 for row in rel_rows]) if rel_rows else 0.0,
                "source_cue_rate": mean([row["source_cue"] for row in rel_rows]) if rel_rows else 0.0,
                "temporal_ok_rate": mean([row["temporal_ok"] for row in rel_rows]) if rel_rows else 0.0,
            }
        )
        by_relation[rel_type] = summary

    by_confidence_bucket: Dict[str, Dict[str, Any]] = {}
    for bucket in BUCKET_ORDER:
        bucket_rows = [row for row in sampled if row["confidence_bucket"] == bucket]
        summary = _summarize(bucket_rows)
        summary.update(
            {
                "supported_or_partial_rate": (
                    (summary["supported"] + summary["partial"]) / summary["total"] if summary["total"] else 0.0
                ),
                "matched_control_win_rate": mean([row["matched_control_delta"] > 0 for row in bucket_rows]) if bucket_rows else 0.0,
            }
        )
        by_confidence_bucket[bucket] = summary

    overall = _summarize(sampled)
    overall["supported_or_partial_rate"] = (
        (overall["supported"] + overall["partial"]) / overall["total"] if overall["total"] else 0.0
    )
    overall["matched_control_win_rate"] = mean([row["matched_control_delta"] > 0 for row in sampled]) if sampled else 0.0

    failure_mode_counts = Counter(row["failure_mode"] for row in sampled)

    return {
        "experiment_type": "semantic_edge_stratified_protocol_audit",
        "scope_note": (
            "Deterministic repeated-protocol audit over archived semantic edges. "
            "We stratify by relation type and confidence bucket, then assign protocol-level support tiers "
            "using temporal direction, source-side cue support, target-role admissibility, and matched-control lexical contrast. "
            "This remains a zero-API reviewer-facing audit, not a human precision/recall study."
        ),
        "relation_types": list(RELATIONS),
        "confidence_buckets": list(BUCKET_ORDER),
        "strata_per_relation": len(BUCKET_ORDER),
        "samples_per_stratum": SAMPLES_PER_STRATUM,
        "sample_count": len(sampled),
        "by_relation": by_relation,
        "by_confidence_bucket": by_confidence_bucket,
        "overall": overall,
        "failure_mode_counts": dict(failure_mode_counts),
        "samples": sampled,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_audit()
    (OUTPUT_DIR / "semantic_edge_stratified_protocol_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Semantic Edge Stratified Protocol Audit",
        "",
        f"- Sample count: {payload['sample_count']}",
        f"- Supported-or-partial rate: {payload['overall']['supported_or_partial_rate']*100:.1f}%",
        f"- Matched-control win rate: {payload['overall']['matched_control_win_rate']*100:.1f}%",
        "",
        "| Relation | Total | Supported | Partial | Unsupported | Supported+Partial | Matched-control win |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for rel_type in RELATIONS:
        row = payload["by_relation"][rel_type]
        lines.append(
            f"| {rel_type} | {row['total']} | {row['supported']} | {row['partial']} | {row['unsupported']} | "
            f"{row['supported_or_partial_rate']*100:.1f}% | {row['matched_control_win_rate']*100:.1f}% |"
        )

    lines.extend(
        [
            "",
            "## Failure modes",
            "",
        ]
    )
    for key, value in sorted(payload["failure_mode_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {key}: {value}")

    (OUTPUT_DIR / "semantic_edge_stratified_protocol_audit.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
