from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit

SCISAGE_RESULT = (
    ROOT / "outputs" / "scisage_outline_docvqa_20260525" / "scisage_outline_live_result.json"
)
OUTPUT_DIR = ROOT / "outputs" / "matched_outline_alignment_20260525"
DEFAULT_TOPIC = "Document Visual Question Answering"


ROLE_RULES = [
    ("intro_scope", ("introduction", "foundation")),
    ("task_background", ("background", "problem formulation", "task formulation")),
    ("motivation", ("why", "motivation")),
    ("methods", ("technical workflow", "paradigm", "architectural", "methodological", "architecture")),
    ("evaluation", ("benchmark", "evaluation")),
    ("challenges", ("challenge", "future")),
    ("conclusion", ("conclusion",)),
]


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _load_topic_outline(topic_label: str) -> Dict[str, Any]:
    for run in audit.load_archived_runs():
        if run.label == topic_label:
            return run.outline
    raise KeyError(f"outline not found for {topic_label}")


def _section_titles(outline: Dict[str, Any]) -> List[str]:
    sections = outline.get("sections") or outline.get("survey_structure") or []
    titles: List[str] = []
    for section in sections:
        title = section.get("title") or section.get("section_title")
        if title:
            titles.append(str(title))
    return titles


def _assign_roles(title: str) -> List[str]:
    lower = title.lower()
    matched: List[str] = []
    for role, keywords in ROLE_RULES:
        if any(keyword in lower for keyword in keywords):
            matched.append(role)
    return matched or ["other"]


def _roles_from_titles(titles: Iterable[str]) -> List[str]:
    roles: List[str] = []
    for title in titles:
        for role in _assign_roles(title):
            if not roles or roles[-1] != role:
                roles.append(role)
    return roles


def _lcs(seq_a: List[str], seq_b: List[str]) -> List[str]:
    dp: List[List[List[str]]] = [[[] for _ in range(len(seq_b) + 1)] for _ in range(len(seq_a) + 1)]
    for i, a in enumerate(seq_a, start=1):
        for j, b in enumerate(seq_b, start=1):
            if a == b:
                dp[i][j] = dp[i - 1][j - 1] + [a]
            else:
                dp[i][j] = dp[i - 1][j] if len(dp[i - 1][j]) >= len(dp[i][j - 1]) else dp[i][j - 1]
    return dp[-1][-1]


def build_alignment_payload(
    topic_label: str,
    surveygraph_outline: Dict[str, Any],
    scisage_result: Dict[str, Any],
) -> Dict[str, Any]:
    sg_titles = _section_titles(surveygraph_outline)
    ss_titles = _section_titles(scisage_result["final_outline"])
    sg_roles = _roles_from_titles(sg_titles)
    ss_roles = _roles_from_titles(ss_titles)
    shared = _lcs(sg_roles, ss_roles)
    missing = [role for role in sg_roles if role not in ss_roles]

    return {
        "topic": topic_label,
        "surveygraph_titles": sg_titles,
        "scisage_titles": ss_titles,
        "alignment": {
            "surveygraph_unique_role_count": len(sg_roles),
            "scisage_unique_role_count": len(ss_roles),
            "role_order_lcs": len(shared),
            "shared_roles_in_order": shared,
            "scisage_role_recall_against_sg": (len(shared) / len(sg_roles)) if sg_roles else 0.0,
            "missing_roles_in_scisage": missing,
        },
        "caveat": (
            "Role alignment is title-based and coarse-grained; it evaluates top-level structural coverage only, "
            "not subsection quality, evidence grounding, or full-paper usefulness."
        ),
    }


def build_alignment_for_topic(topic_label: str, scisage_result_path: Path) -> Dict[str, Any]:
    surveygraph_outline = _load_topic_outline(topic_label)
    scisage_result = load_json(scisage_result_path)
    payload = build_alignment_payload(topic_label, surveygraph_outline, scisage_result)
    payload["scisage_result_path"] = _display_path(scisage_result_path)
    return payload


def build_markdown(payload: Dict[str, Any]) -> str:
    alignment = payload["alignment"]
    return (
        "# Matched Outline Alignment Summary\n\n"
        f"- Topic: **{payload['topic']}**\n"
        f"- SurveyGraph top-level titles: {len(payload['surveygraph_titles'])}\n"
        f"- SciSage top-level titles: {len(payload['scisage_titles'])}\n"
        f"- Shared role order LCS: {alignment['role_order_lcs']}\n"
        f"- SciSage role recall against SurveyGraph: {alignment['scisage_role_recall_against_sg']:.3f}\n"
        f"- Missing roles in SciSage: {', '.join(alignment['missing_roles_in_scisage']) or 'none'}\n"
        f"- Shared roles in order: {', '.join(alignment['shared_roles_in_order']) or 'none'}\n"
        f"- Caveat: {payload['caveat']}\n"
    )


def main() -> None:
    topic_label, scisage_result_path, output_dir = resolve_cli_args(sys.argv)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_alignment_for_topic(topic_label, scisage_result_path)
    (output_dir / "matched_outline_alignment.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "matched_outline_alignment_summary.md").write_text(
        build_markdown(payload), encoding="utf-8"
    )
    print(f"Wrote outputs to {output_dir}")


if __name__ == "__main__":
    main()
