from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import citation_evidence_contrast_probe as contrast
from experiments import expanded_claim_citation_audit as grounding
from experiments import offline_real_revision_audit as audit
from experiments import section_reference_alignment_audit as alignment

DEFAULT_FULL_DIR = ROOT / "outputs" / "20260709_mainconf_pilot_qwen_full_llmfc"
DEFAULT_FLAT_DIR = ROOT / "outputs" / "20260715_matched_flat_qwen_llmfc"
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "matched_generation_quality_audit_20260716"


def _paper_id(paper: Dict[str, Any]) -> str:
    return str(paper.get("id") or paper.get("arxiv_id") or paper.get("paper_id") or "").strip()


def _relations(mekg: Dict[str, Any]) -> List[Any]:
    value = mekg.get("relations", mekg.get("edges", []))
    return value if isinstance(value, list) else []


def validate_matched_runs(
    full_mekg: Dict[str, Any],
    flat_mekg: Dict[str, Any],
    *,
    full_section_count: int,
    flat_section_count: int,
) -> Dict[str, Any]:
    full_ids = sorted(filter(None, (_paper_id(p) for p in full_mekg.get("papers", []))))
    flat_ids = sorted(filter(None, (_paper_id(p) for p in flat_mekg.get("papers", []))))
    if full_ids != flat_ids:
        raise ValueError("Matched comparison must use the same paper corpus")
    flat_relation_count = len(_relations(flat_mekg))
    if flat_relation_count != 0:
        raise ValueError("Matched flat run must contain zero relations")
    if full_section_count != flat_section_count:
        raise ValueError("Matched comparison must use the same section count")
    return {
        "paper_count": len(full_ids),
        "same_paper_ids": True,
        "full_relation_count": len(_relations(full_mekg)),
        "flat_relation_count": flat_relation_count,
        "full_section_count": full_section_count,
        "flat_section_count": flat_section_count,
    }


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def _row(run_rows: Iterable[Dict[str, Any]], run_id: str) -> Dict[str, Any]:
    for row in run_rows:
        if row.get("run_id") == run_id:
            return row
    raise KeyError(f"Missing audit row for {run_id}")


def aggregate_comparison(
    grounding_payload: Dict[str, Any],
    contrast_payload: Dict[str, Any],
    alignment_payload: Dict[str, Any],
    full_run_id: str,
    flat_run_id: str,
) -> List[Dict[str, Any]]:
    full_ground = _row(grounding_payload["per_run"], full_run_id)
    flat_ground = _row(grounding_payload["per_run"], flat_run_id)
    full_ground_count = int(full_ground.get("anchored", 0)) + int(full_ground.get("partial_anchor", 0))
    flat_ground_count = int(flat_ground.get("anchored", 0)) + int(flat_ground.get("partial_anchor", 0))
    full_ground_total = int(full_ground.get("sample_count", 0))
    flat_ground_total = int(flat_ground.get("sample_count", 0))

    contrast_by_run: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for sample in contrast_payload.get("samples", []):
        contrast_by_run[str(sample.get("run_id"))].append(sample)
    full_contrast = contrast_by_run[full_run_id]
    flat_contrast = contrast_by_run[flat_run_id]
    full_contrast_count = sum(bool(row.get("cited_beats_hard_negative")) for row in full_contrast)
    flat_contrast_count = sum(bool(row.get("cited_beats_hard_negative")) for row in flat_contrast)

    full_align = _row(alignment_payload["per_run"], full_run_id)
    flat_align = _row(alignment_payload["per_run"], flat_run_id)
    full_buckets = full_align.get("bucket_counts", {})
    flat_buckets = flat_align.get("bucket_counts", {})
    full_align_count = int(full_buckets.get("aligned", 0)) + int(full_buckets.get("partially_aligned", 0))
    flat_align_count = int(flat_buckets.get("aligned", 0)) + int(flat_buckets.get("partially_aligned", 0))
    full_align_total = int(full_align.get("section_count", 0))
    flat_align_total = int(flat_align.get("section_count", 0))

    def rate_row(key: str, label: str, fc: int, ft: int, bc: int, bt: int) -> Dict[str, Any]:
        full_rate = _rate(fc, ft)
        flat_rate = _rate(bc, bt)
        return {
            "key": key,
            "label": label,
            "full_count": fc,
            "full_total": ft,
            "full_rate": full_rate,
            "flat_count": bc,
            "flat_total": bt,
            "flat_rate": flat_rate,
            "delta_percentage_points": 100.0 * (full_rate - flat_rate),
        }

    rows = [
        rate_row(
            "citation_grounding",
            "Citation grounding (anchored or partial)",
            full_ground_count,
            full_ground_total,
            flat_ground_count,
            flat_ground_total,
        ),
        rate_row(
            "hard_negative",
            "Cited evidence beats hard negative",
            full_contrast_count,
            len(full_contrast),
            flat_contrast_count,
            len(flat_contrast),
        ),
        rate_row(
            "section_alignment",
            "Section alignment (aligned or partial)",
            full_align_count,
            full_align_total,
            flat_align_count,
            flat_align_total,
        ),
        {
            "key": "uncited_sections",
            "label": "Uncited sections",
            "full_value": int(full_align.get("uncited_section_count", 0)),
            "flat_value": int(flat_align.get("uncited_section_count", 0)),
            "delta": int(full_align.get("uncited_section_count", 0)) - int(flat_align.get("uncited_section_count", 0)),
        },
    ]
    return rows


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _section_count(outline: Dict[str, Any]) -> int:
    sections = outline.get("sections") or outline.get("outline") or []
    if isinstance(sections, dict):
        sections = sections.get("sections", [])
    return len(sections) if isinstance(sections, list) else 0


def _bundle(run_dir: Path, label: str) -> audit.RunBundle:
    mekg_path = run_dir / "mekg" / "mekg_data.json"
    outline_path = run_dir / "outlines.json"
    if not outline_path.exists():
        outline_path = run_dir / "outline.json"
    survey_path = run_dir / "latex" / "survey.tex"
    for required in (mekg_path, outline_path, survey_path):
        if not required.exists():
            raise FileNotFoundError(required)
    return audit.RunBundle(
        run_id=run_dir.name,
        label=label,
        base_dir=run_dir,
        mekg=_load_json(mekg_path),
        outline=_load_json(outline_path),
    )


@contextmanager
def _patched_runs(bundles: List[audit.RunBundle]) -> Iterator[None]:
    original = audit.load_archived_runs
    audit.load_archived_runs = lambda: bundles
    try:
        yield
    finally:
        audit.load_archived_runs = original


def build_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Matched Generation Quality Audit",
        "",
        "Same 30-paper corpus, Qwen backend, top-down outline, and generation/reflection settings; the flat condition removes MEKG relations and graph-derived attributes.",
        "",
        "| Final-output check | SurveyGraph | Matched flat | Delta |",
        "|---|---:|---:|---:|",
    ]
    for row in payload["comparison"]:
        if row["key"] == "uncited_sections":
            lines.append(f"| {row['label']} | {row['full_value']} | {row['flat_value']} | {row['delta']:+d} |")
        else:
            full = f"{100 * row['full_rate']:.1f}% ({row['full_count']}/{row['full_total']})"
            flat = f"{100 * row['flat_rate']:.1f}% ({row['flat_count']}/{row['flat_total']})"
            is_directional_section_check = (
                row["key"] == "section_alignment"
                and row["full_count"] == row["flat_count"]
                and max(row["full_total"], row["flat_total"]) <= 5
            )
            delta = "directional" if is_directional_section_check else f"{row['delta_percentage_points']:+.1f} pp"
            lines.append(f"| {row['label']} | {full} | {flat} | {delta} |")
    lines.extend(
        [
            "",
            "> These deterministic audits are graph-independent lexical/evidence diagnostics, not human preference or semantic-entailment judgments.",
            "",
        ]
    )
    return "\n".join(lines)


def run_audit(full_dir: Path, flat_dir: Path, output_dir: Path, sample_per_run: int = 20) -> Dict[str, Any]:
    full = _bundle(full_dir, "SurveyGraph")
    flat = _bundle(flat_dir, "Matched flat")
    match = validate_matched_runs(
        full.mekg,
        flat.mekg,
        full_section_count=_section_count(full.outline),
        flat_section_count=_section_count(flat.outline),
    )
    bundles = [full, flat]
    output_dir.mkdir(parents=True, exist_ok=True)
    grounding_path = output_dir / "grounding_audit.json"
    with _patched_runs(bundles):
        grounding_payload = grounding.build_audit(sample_per_run=sample_per_run)
        grounding_path.write_text(json.dumps(grounding_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        original_source = contrast.SOURCE_AUDIT
        contrast.SOURCE_AUDIT = grounding_path
        try:
            contrast_payload = contrast.build_probe()
        finally:
            contrast.SOURCE_AUDIT = original_source
        alignment_payload = alignment.build_audit()

    comparison = aggregate_comparison(
        grounding_payload,
        contrast_payload,
        alignment_payload,
        full.run_id,
        flat.run_id,
    )
    payload = {
        "experiment_type": "matched_generation_quality_audit",
        "scope_note": "Matched final-output diagnostic with identical corpus/backend/outline/generation settings; only graph-derived structure is removed in the flat condition.",
        "full_run_id": full.run_id,
        "flat_run_id": flat.run_id,
        "sample_per_run": sample_per_run,
        "match_validation": match,
        "comparison": comparison,
        "grounding_audit": grounding_payload,
        "contrast_audit": contrast_payload,
        "section_alignment_audit": alignment_payload,
    }
    (output_dir / "matched_generation_quality_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "matched_generation_quality_audit.md").write_text(build_markdown(payload), encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run matched SurveyGraph-vs-flat final-output audits.")
    parser.add_argument("--full-dir", type=Path, default=DEFAULT_FULL_DIR)
    parser.add_argument("--flat-dir", type=Path, default=DEFAULT_FLAT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--sample-per-run", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_audit(args.full_dir, args.flat_dir, args.output_dir, args.sample_per_run)
    print(build_markdown(payload))


if __name__ == "__main__":
    main()

