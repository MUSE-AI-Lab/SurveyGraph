from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit
from experiments.semantic_edge_stratified_protocol_audit import _iter_semantic_rows

OUTPUT_DIR = ROOT / "outputs" / "semantic_gate_error_analysis_20260526"


def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _sample_rows(rows: List[Dict[str, Any]], n: int = 3) -> List[Dict[str, Any]]:
    out = []
    for row in rows[:n]:
        out.append(
            {
                "run_id": row["run_id"],
                "topic": row["run_label"],
                "relation_type": row["relation_type"],
                "protocol_label": row["protocol_label"],
                "failure_mode": row.get("failure_mode"),
                "source_title": row["source_title"],
                "target_title": row["target_title"],
                "confidence": row["confidence"],
                "source_year": row["source_year"],
                "target_year": row["target_year"],
                "source_cue": row["source_cue"],
                "target_role_ok": row["target_role_ok"],
                "temporal_ok": row["temporal_ok"],
                "matched_control_delta": row["matched_control_delta"],
                "matched_control_title": row["matched_control_title"],
            }
        )
    return out


def build_analysis() -> Dict[str, Any]:
    rows = list(_iter_semantic_rows())
    total = len(rows)
    label_counts = Counter(row["protocol_label"] for row in rows)
    rel_label: Dict[str, Counter] = defaultdict(Counter)
    failure_modes = Counter()
    unsupported_failure_by_rel: Dict[str, Counter] = defaultdict(Counter)
    gate = {
        "supported_or_partial_kept": 0,
        "supported_or_partial_dropped": 0,
        "supported_only_kept": 0,
        "supported_only_dropped": 0,
    }

    for row in rows:
        rel = row["relation_type"]
        label = row["protocol_label"]
        rel_label[rel][label] += 1
        if label in {"supported", "partial"}:
            gate["supported_or_partial_kept"] += 1
        else:
            gate["supported_or_partial_dropped"] += 1
            mode = row.get("failure_mode") or "unknown"
            failure_modes[mode] += 1
            unsupported_failure_by_rel[rel][mode] += 1

        if label == "supported":
            gate["supported_only_kept"] += 1
        else:
            gate["supported_only_dropped"] += 1

    by_relation = {}
    for rel in audit.SEMANTIC_RELATIONS:
        cnt = rel_label[rel]
        denom = sum(cnt.values())
        rel_rows = [r for r in rows if r["relation_type"] == rel]
        unsupported_rows = [r for r in rel_rows if r["protocol_label"] == "unsupported"]
        partial_rows = [r for r in rel_rows if r["protocol_label"] == "partial"]
        supported_rows = [r for r in rel_rows if r["protocol_label"] == "supported"]
        by_relation[rel] = {
            "total": denom,
            "supported": cnt["supported"],
            "partial": cnt["partial"],
            "unsupported": cnt["unsupported"],
            "supported_or_partial_rate": (cnt["supported"] + cnt["partial"]) / denom if denom else 0.0,
            "unsupported_rate": cnt["unsupported"] / denom if denom else 0.0,
            "source_cue_rate": _mean(bool(r["source_cue"]) for r in rel_rows),
            "target_role_ok_rate": _mean(bool(r["target_role_ok"]) for r in rel_rows),
            "temporal_ok_rate": _mean(bool(r["temporal_ok"]) for r in rel_rows),
            "matched_control_win_rate": _mean(float(r["matched_control_delta"] > 0) for r in rel_rows),
            "unsupported_failure_modes": dict(unsupported_failure_by_rel[rel]),
            "examples": {
                "supported": _sample_rows(supported_rows, 2),
                "partial": _sample_rows(partial_rows, 2),
                "unsupported": _sample_rows(unsupported_rows, 3),
            },
        }

    unsupported_rows = [r for r in rows if r["protocol_label"] == "unsupported"]
    unsupported_sorted = sorted(
        unsupported_rows,
        key=lambda r: (
            0 if r["relation_type"] == "extends" else 1,
            r.get("failure_mode") or "",
            -float(r.get("confidence", 0.0) or 0.0),
        ),
    )
    return {
        "experiment_type": "semantic_gate_error_analysis",
        "scope_note": (
            "Post-hoc error analysis over all archived semantic-edge rows scored by the deterministic protocol "
            "used to build the 72-row stratified audit. This is not a new human annotation study; it summarizes "
            "which relation types and failure modes are filtered by the evidence gate."
        ),
        "overall": {
            "total": total,
            "label_counts": dict(label_counts),
            "supported_or_partial_rate": (label_counts["supported"] + label_counts["partial"]) / total if total else 0.0,
            "supported_rate": label_counts["supported"] / total if total else 0.0,
            "unsupported_rate": label_counts["unsupported"] / total if total else 0.0,
        },
        "gate_effect_on_audit_rows": gate,
        "failure_mode_counts_among_unsupported": dict(failure_modes),
        "by_relation": by_relation,
        "representative_unsupported_examples": _sample_rows(unsupported_sorted, 8),
    }


def build_markdown(payload: Dict[str, Any]) -> str:
    overall = payload["overall"]
    gate = payload["gate_effect_on_audit_rows"]
    lines = [
        "# Semantic Gate Error Analysis",
        "",
        f"- Protocol rows: {overall['total']}",
        f"- Supported / partial / unsupported: {overall['label_counts'].get('supported', 0)} / {overall['label_counts'].get('partial', 0)} / {overall['label_counts'].get('unsupported', 0)}",
        f"- Supported-or-partial rate: {overall['supported_or_partial_rate']:.3f}",
        f"- Supported-or-partial gate keeps/drops: {gate['supported_or_partial_kept']} / {gate['supported_or_partial_dropped']}",
        f"- Supported-only gate keeps/drops: {gate['supported_only_kept']} / {gate['supported_only_dropped']}",
        "",
        "| Relation | Total | Supp. | Partial | Unsupp. | Supp./partial rate | Source cue | Target role OK | Temporal OK |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rel, row in payload["by_relation"].items():
        lines.append(
            f"| {rel} | {row['total']} | {row['supported']} | {row['partial']} | {row['unsupported']} | "
            f"{row['supported_or_partial_rate']:.3f} | {row['source_cue_rate']:.3f} | "
            f"{row['target_role_ok_rate']:.3f} | {row['temporal_ok_rate']:.3f} |"
        )
    lines.extend(["", "## Unsupported failure modes"])
    for mode, count in sorted(payload["failure_mode_counts_among_unsupported"].items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- {mode}: {count}")
    lines.extend(["", "## Representative unsupported examples"])
    for row in payload["representative_unsupported_examples"]:
        lines.append(
            f"- `{row['relation_type']}` / {row['failure_mode']}: {row['source_title']} -> {row['target_title']}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_analysis()
    (OUTPUT_DIR / "semantic_gate_error_analysis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "semantic_gate_error_analysis.md").write_text(
        build_markdown(payload),
        encoding="utf-8",
    )
    print(f"Wrote outputs to {OUTPUT_DIR}")
    print((OUTPUT_DIR / "semantic_gate_error_analysis.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
