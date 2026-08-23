from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs" / "matched_multi_topic_summary_20260525"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_multi_topic_summary(
    subset_payloads: Iterable[Dict[str, Any]],
    alignment_payloads: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    subset_payloads = list(subset_payloads)
    alignment_payloads = list(alignment_payloads)
    alignment_by_topic = {payload["topic"]: payload for payload in alignment_payloads}
    rows: List[Dict[str, Any]] = []
    missing_role_counts: Counter[str] = Counter()

    for subset in subset_payloads:
        topic = subset["topic"]
        alignment = alignment_by_topic[topic]["alignment"]
        missing_roles = alignment["missing_roles_in_scisage"]
        missing_role_counts.update(missing_roles)
        rows.append(
            {
                "topic": topic,
                "surveygraph_top_sections": subset["surveygraph"]["outline_top_level_sections"],
                "surveygraph_total_nodes": subset["surveygraph"]["outline_total_nodes"],
                "scisage_top_sections": subset["scisage"]["top_level_sections"],
                "scisage_total_nodes": subset["scisage"]["total_outline_nodes"],
                "scisage_latency_seconds": round(subset["scisage"]["latency_seconds"], 2),
                "scisage_meets_requirements": bool(subset["scisage"]["meets_requirements"]),
                "role_recall": round(alignment["scisage_role_recall_against_sg"], 3),
                "missing_roles": missing_roles,
            }
        )

    return {
        "topic_count": len(rows),
        "topics": rows,
        "aggregate": {
            "surveygraph_mean_top_sections": round(mean(r["surveygraph_top_sections"] for r in rows), 2),
            "surveygraph_mean_total_nodes": round(mean(r["surveygraph_total_nodes"] for r in rows), 2),
            "scisage_mean_top_sections": round(mean(r["scisage_top_sections"] for r in rows), 2),
            "scisage_mean_total_nodes": round(mean(r["scisage_total_nodes"] for r in rows), 2),
            "scisage_mean_latency_seconds": round(mean(r["scisage_latency_seconds"] for r in rows), 2),
            "mean_role_recall": round(mean(r["role_recall"] for r in rows), 3),
            "meets_requirements_rate": round(
                mean(1.0 if r["scisage_meets_requirements"] else 0.0 for r in rows), 3
            ),
            "missing_role_counts": dict(sorted(missing_role_counts.items())),
        },
        "caveat": (
            "This summary aggregates four same-backend-family, outline-only matched subsets. "
            "It strengthens topic diversity relative to a single matched example, but it is still "
            "not a full same-setting benchmark or full-paper quality evaluation."
        ),
    }


def build_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Multi-Topic Matched Baseline Summary",
        "",
        f"- Topics: {payload['topic_count']}",
        f"- Mean SciSage latency: {payload['aggregate']['scisage_mean_latency_seconds']:.2f} s",
        f"- Mean role recall against SurveyGraph top-level outline roles: {payload['aggregate']['mean_role_recall']:.3f}",
        f"- SciSage reflection-gate pass rate: {payload['aggregate']['meets_requirements_rate']:.3f}",
        f"- Caveat: {payload['caveat']}",
        "",
        "| Topic | SurveyGraph outline | SciSage outline | SciSage latency | Role recall | Missing roles |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in payload["topics"]:
        lines.append(
            f"| {row['topic']} | {row['surveygraph_top_sections']} sec / {row['surveygraph_total_nodes']} nodes "
            f"| {row['scisage_top_sections']} sec / {row['scisage_total_nodes']} nodes | "
            f"{row['scisage_latency_seconds']:.2f} s | {row['role_recall']:.3f} | "
            f"{', '.join(row['missing_roles']) or 'none'} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    subset_paths = [
        ROOT / "outputs" / "matched_baseline_subset_20260525" / "matched_baseline_subset.json",
        ROOT / "outputs" / "matched_baseline_subset_t2sql_20260525" / "matched_baseline_subset.json",
        ROOT / "outputs" / "matched_baseline_subset_llmfc_20260525" / "matched_baseline_subset.json",
        ROOT / "outputs" / "matched_baseline_subset_memory_20260525" / "matched_baseline_subset.json",
    ]
    alignment_paths = [
        ROOT / "outputs" / "matched_outline_alignment_20260525" / "matched_outline_alignment.json",
        ROOT / "outputs" / "matched_outline_alignment_t2sql_20260525" / "matched_outline_alignment.json",
        ROOT / "outputs" / "matched_outline_alignment_llmfc_20260525" / "matched_outline_alignment.json",
        ROOT / "outputs" / "matched_outline_alignment_memory_20260525" / "matched_outline_alignment.json",
    ]
    subset_payloads = [load_json(path) for path in subset_paths]
    alignment_payloads = [load_json(path) for path in alignment_paths]
    payload = build_multi_topic_summary(subset_payloads, alignment_payloads)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "matched_multi_topic_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_DIR / "matched_multi_topic_summary.md").write_text(
        build_markdown(payload), encoding="utf-8"
    )
    print(f"Wrote outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
