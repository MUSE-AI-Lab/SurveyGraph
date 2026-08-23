from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "outputs" / "semantic_edge_stratified_protocol_audit_20260526" / "semantic_edge_stratified_protocol_audit.json"
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "extends_gate_quality_audit_20260715"


def _stats(rows: Iterable[dict[str, Any]]) -> dict[str, int | float]:
    selected = list(rows)
    supported_or_partial = sum(row.get("protocol_label") in {"supported", "partial"} for row in selected)
    total = len(selected)
    return {
        "supported_or_partial": supported_or_partial,
        "total": total,
        "rate": supported_or_partial / total if total else 0.0,
    }


def summarize_extends(rows: Iterable[dict[str, Any]], confidence_threshold: float = 0.8) -> dict[str, Any]:
    extends = [row for row in rows if row.get("relation_type") == "extends"]
    role_compatible = [row for row in extends if row.get("target_role_ok") is True]
    strict_combined = [
        row for row in role_compatible
        if row.get("temporal_ok") is True and float(row.get("confidence", 0.0)) >= confidence_threshold
    ]
    return {
        "audit_type": "deterministic_stratified_protocol_replay",
        "scope_note": (
            "Descriptive protocol audit over the archived 24-edge extends stratum. "
            "This is separate from the independent 108-edge human annotation audit."
        ),
        "confidence_threshold": confidence_threshold,
        "raw": _stats(extends),
        "role_compatible": _stats(role_compatible),
        "strict_combined": _stats(strict_combined),
    }


def render_markdown(summary: dict[str, Any], source: Path) -> str:
    def row(label: str, key: str) -> str:
        item = summary[key]
        return f"| {label} | {item['supported_or_partial']}/{item['total']} | {100 * item['rate']:.1f}% |"

    return "\n".join([
        "# Extends Gate Quality Audit",
        "",
        f"Source: `{source.as_posix()}`",
        "",
        summary["scope_note"],
        "",
        "| View | Supported or partial | Rate |",
        "|---|---:|---:|",
        row("Raw extends sample", "raw"),
        row("Role-compatible", "role_compatible"),
        row(f"Confidence >= {summary['confidence_threshold']:.1f} + role-compatible + temporal-valid", "strict_combined"),
        "",
        "Interpretation: role-aware pruning removes target-role mismatches and raises the descriptive protocol S/P rate. "
        "The independent human audit remains the reliability estimate for raw semantic edges.",
        "",
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--confidence-threshold", type=float, default=0.8)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    summary = summarize_extends(payload["samples"], args.confidence_threshold)
    summary["source"] = str(args.input)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "extends_gate_quality_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "extends_gate_quality_audit.md").write_text(
        render_markdown(summary, args.input), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
