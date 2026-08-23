from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit

MINREAL_DIR = ROOT / "outputs" / "minimal_real_revision_20260524"
SCISAGE_RESULT = ROOT / "outputs" / "scisage_outline_docvqa_20260525" / "scisage_outline_live_result.json"
OUTPUT_DIR = ROOT / "outputs" / "matched_baseline_subset_20260525"
DEFAULT_TOPIC = "Document Visual Question Answering"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def count_outline_nodes(section: Dict[str, Any]) -> int:
    total = 1
    for subsection in section.get("subsections") or []:
        total += count_outline_nodes(subsection)
    return total


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def resolve_cli_args(argv: List[str]) -> tuple[str, Path, Path]:
    topic_label = argv[1] if len(argv) > 1 else DEFAULT_TOPIC
    scisage_result_path = Path(argv[2]) if len(argv) > 2 else SCISAGE_RESULT
    output_dir = Path(argv[3]) if len(argv) > 3 else OUTPUT_DIR
    if not scisage_result_path.is_absolute():
        scisage_result_path = ROOT / scisage_result_path
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    return topic_label, scisage_result_path, output_dir


def _find_external_core_row(topic_label: str) -> Dict[str, Any]:
    data = load_json(MINREAL_DIR / "survey_reference_external_core_audit.json")
    for row in data.get("per_run", []):
        if row.get("label") == topic_label:
            return row
    raise KeyError(f"external core row not found for {topic_label}")


def _find_graph_row(topic_label: str) -> Dict[str, Any]:
    data = load_json(MINREAL_DIR / "graph_retrieval_diagnostic_summary.json")
    for row in data.get("per_run", []):
        if row.get("label") == topic_label:
            return row
    raise KeyError(f"graph row not found for {topic_label}")


def _find_runtime_row(topic_label: str) -> Dict[str, Any]:
    data = load_json(MINREAL_DIR / "runtime_cost_summary.json")
    for row in data.get("archived_full_runs", {}).get("per_run", []):
        if row.get("label") == topic_label:
            return row
    raise KeyError(f"runtime row not found for {topic_label}")


def _load_topic_outline(topic_label: str) -> Dict[str, Any]:
    for run in audit.load_archived_runs():
        if run.label == topic_label:
            return run.outline
    raise KeyError(f"outline not found for {topic_label}")


def _outline_stats_from_surveygraph(outline: Dict[str, Any]) -> Dict[str, int]:
    sections = outline.get("sections") or outline.get("survey_structure") or []
    top_level = len(sections)
    total_nodes = 0
    for section in sections:
        total_nodes += count_outline_nodes(section)
    return {
        "top_level_sections": top_level,
        "total_outline_nodes": total_nodes,
    }


def build_matched_summary(
    topic_label: str = DEFAULT_TOPIC,
    scisage_result_path: Path = SCISAGE_RESULT,
) -> Dict[str, Any]:
    external = _find_external_core_row(topic_label)
    graph = _find_graph_row(topic_label)
    runtime = _find_runtime_row(topic_label)
    scisage = load_json(scisage_result_path)
    sg_outline = _load_topic_outline(topic_label)
    sg_outline_stats = _outline_stats_from_surveygraph(sg_outline)

    return {
        "topic": topic_label,
        "matched_setup": {
            "backend_family": "DashScope-compatible OpenAI",
            "comparison_scope": "same-backend matched subset",
            "surveygraph_source": "archived topic slice",
            "scisage_source": "live outline-only baseline",
            "caveat": "Matched on backend family and low-cost subset scope, not full-paper parity.",
        },
        "surveygraph": {
            "source": "archived",
            "external_core_proxy_target_size": external["external_target_size"],
            "external_core_proxy_recall_top10": external["base_top10_recall"],
            "external_core_proxy_recall_top20": external["base_top20_recall"],
            "graph_core_recall_top5": graph["one_hop"]["core_paper_recall"],
            "graph_relation_density_top5": graph["one_hop"]["relation_density"],
            "sections_evaluated": graph["one_hop"]["sections_evaluated"],
            "outline_top_level_sections": sg_outline_stats["top_level_sections"],
            "outline_total_nodes": sg_outline_stats["total_outline_nodes"],
            "runtime_minutes_archived": runtime["total_minutes"],
        },
        "scisage": {
            "source": "live_outline",
            "result_path": _display_path(scisage_result_path),
            "query": scisage["user_query"],
            "top_level_sections": scisage["artifact_stats"]["top_level_sections"],
            "total_outline_nodes": scisage["artifact_stats"]["total_outline_nodes"],
            "latency_seconds": scisage["runtime"]["latency_seconds"],
            "model": scisage["backend"]["model"],
            "meets_requirements": scisage["quality_gate"]["meets_requirements"],
        },
    }


def build_markdown_summary(payload: Dict[str, Any]) -> str:
    sg = payload["surveygraph"]
    ss = payload["scisage"]
    lines: List[str] = []
    lines.append("# Matched Baseline Subset Summary")
    lines.append("")
    lines.append(f"- Topic: **{payload['topic']}**")
    lines.append(f"- Scope: {payload['matched_setup']['comparison_scope']}")
    lines.append(f"- Caveat: {payload['matched_setup']['caveat']}")
    lines.append("")
    lines.append("| System | Topic/setup | Ext-core proxy | Outline breadth | Runtime | Cost/note |")
    lines.append("|---|---|---:|---:|---:|---|")
    lines.append(
        f"| SurveyGraph | archived topic slice | {sg['external_core_proxy_recall_top20']:.3f} (@20) | {sg['outline_top_level_sections']} sec / {sg['outline_total_nodes']} nodes | {sg['runtime_minutes_archived']:.2f} min | archived full run |"
    )
    lines.append(
        f"| SciSage | live outline-only baseline | -- | {ss['top_level_sections']} sec / {ss['total_outline_nodes']} nodes | {ss['latency_seconds']:.2f} s | {ss['model']} / meets={ss['meets_requirements']} |"
    )
    lines.append("")
    lines.append(
        f"SurveyGraph retrieval-side diagnostic on this topic: core recall {sg['graph_core_recall_top5']:.3f}, relation density {sg['graph_relation_density_top5']:.3f}, sections evaluated {sg['sections_evaluated']}."
    )
    return "\n".join(lines) + "\n"

def main() -> None:
    topic_label, scisage_result_path, output_dir = resolve_cli_args(sys.argv)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_matched_summary(topic_label, scisage_result_path=scisage_result_path)
    (output_dir / "matched_baseline_subset.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "matched_baseline_subset_summary.md").write_text(
        build_markdown_summary(payload), encoding="utf-8"
    )
    print(f"Wrote outputs to {output_dir}")


if __name__ == "__main__":
    main()
