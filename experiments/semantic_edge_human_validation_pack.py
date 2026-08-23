from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import semantic_edge_stratified_protocol_audit as protocol

OUTPUT_DIR = ROOT / "outputs" / "semantic_edge_human_validation_pack_20260526"
SAMPLES_PER_STRATUM = 12


def _shorten(text: str, limit: int = 700) -> str:
    text = " ".join((text or "").split())
    return text[: limit - 1] + "…" if len(text) > limit else text


def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _select_annotation_sample(rows: List[Dict[str, Any]], per_stratum: int = SAMPLES_PER_STRATUM) -> List[Dict[str, Any]]:
    """Deterministic relation x confidence sample for human annotation.

    The existing protocol audit samples 72 rows. For a human-validation pack we
    take a slightly larger, non-repeating sample where possible: 3 relation
    types x 3 confidence buckets x 12 rows = up to 108 rows.
    """

    sample: List[Dict[str, Any]] = []
    for rel_type in protocol.RELATIONS:
        for bucket in protocol.BUCKET_ORDER:
            bucket_rows = [
                row for row in rows
                if row["relation_type"] == rel_type and row["confidence_bucket"] == bucket
            ]
            bucket_rows = sorted(
                bucket_rows,
                key=lambda row: (
                    row["run_label"],
                    row["source_year"] if row["source_year"] is not None else 0,
                    row["source_title"],
                    row["target_title"],
                ),
            )
            sample.extend(bucket_rows[:per_stratum])
    for idx, row in enumerate(sample, start=1):
        row["sample_id"] = f"edge-{idx:03d}"
    return sample


def _annotation_csv_rows(sample: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in sample:
        rows.append(
            {
                "sample_id": row["sample_id"],
                "run_label": row["run_label"],
                "relation_type": row["relation_type"],
                "confidence": f"{float(row['confidence']):.3f}",
                "confidence_bucket": row["confidence_bucket"],
                "source_year": row["source_year"],
                "target_year": row["target_year"],
                "source_title": row["source_title"],
                "target_title": row["target_title"],
                "matched_control_title": row["matched_control_title"],
                "source_abstract_snippet": _shorten(row.get("source_abstract", "")),
                "target_abstract_snippet": _shorten(row.get("target_abstract", "")),
                "human_relation_correct": "",
                "human_direction_correct": "",
                "human_evidence_support": "",
                "human_keep_edge": "",
                "human_error_type": "",
                "annotator_id": "",
                "notes": "",
            }
        )
    return rows


def _attach_abstracts(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Recover snippets from archived rows for annotation context.

    The protocol rows contain titles and labels. To keep this package
    self-contained for annotators, add compact local evidence snippets by
    matching titles back through the already materialized protocol iterator.
    """

    # The protocol iterator does not expose abstracts, so we import the base run
    # loader here and title-match within each run. This stays local and
    # deterministic.
    from experiments import offline_real_revision_audit as base

    by_run_title: Dict[tuple[str, str], Dict[str, Any]] = {}
    for run in base.load_archived_runs():
        for paper in run.mekg.get("papers", []):
            by_run_title[(run.label, paper.get("title", ""))] = paper

    out = []
    for row in rows:
        row = dict(row)
        src = by_run_title.get((row["run_label"], row["source_title"]), {})
        tgt = by_run_title.get((row["run_label"], row["target_title"]), {})
        row["source_abstract"] = src.get("abstract", "")
        row["target_abstract"] = tgt.get("abstract", "")
        out.append(row)
    return out


def _summarize(sample: List[Dict[str, Any]]) -> Dict[str, Any]:
    label_counts = Counter(row["protocol_label"] for row in sample)
    relation_counts = Counter(row["relation_type"] for row in sample)
    bucket_counts = Counter(row["confidence_bucket"] for row in sample)
    failure_counts = Counter(row["failure_mode"] for row in sample)

    by_relation: Dict[str, Dict[str, Any]] = {}
    for rel_type in protocol.RELATIONS:
        rel_rows = [row for row in sample if row["relation_type"] == rel_type]
        labels = Counter(row["protocol_label"] for row in rel_rows)
        by_relation[rel_type] = {
            "count": len(rel_rows),
            "deterministic_supported": labels.get("supported", 0),
            "deterministic_partial": labels.get("partial", 0),
            "deterministic_unsupported": labels.get("unsupported", 0),
            "deterministic_supported_or_partial_rate": (
                (labels.get("supported", 0) + labels.get("partial", 0)) / len(rel_rows)
                if rel_rows else 0.0
            ),
            "matched_control_win_rate": _mean(row["matched_control_delta"] > 0 for row in rel_rows),
        }

    return {
        "sample_count": len(sample),
        "samples_per_relation_confidence_stratum_target": SAMPLES_PER_STRATUM,
        "relation_counts": dict(relation_counts),
        "confidence_bucket_counts": dict(bucket_counts),
        "deterministic_protocol_label_counts": dict(label_counts),
        "deterministic_supported_or_partial_rate": (
            (label_counts.get("supported", 0) + label_counts.get("partial", 0)) / len(sample)
            if sample else 0.0
        ),
        "failure_mode_counts": dict(failure_counts),
        "by_relation": by_relation,
    }


def _guideline_text() -> str:
    return """# Semantic-Edge Human Validation Guideline

This packet is designed for a small human validation study of SurveyGraph's
semantic MEKG edges. It is **not** pre-filled with human labels.

## Unit of annotation

Each row is one directed candidate edge:

`source paper --relation_type--> target paper`

Judge the edge using the source/target titles, years, and abstract snippets.

## Fields to fill

- `human_relation_correct`: `yes`, `partial`, `no`, or `unclear`.
- `human_direction_correct`: `yes`, `no`, or `unclear`.
- `human_evidence_support`: `supported`, `partial`, `unsupported`, or `unclear`.
- `human_keep_edge`: `yes` if the edge should remain as candidate evidence, otherwise `no`.
- `human_error_type`: one of `none`, `topical_overlap`, `target_role_mismatch`,
  `temporal_reversal`, `wrong_relation_type`, `insufficient_evidence`, `other`.
- `annotator_id`: anonymized annotator identifier.
- `notes`: short rationale when the label is not clearly supported.

## Relation definitions

- `extends`: the source builds on, generalizes, adapts, or follows from the target.
- `improves`: the source claims better performance, robustness, efficiency, or capability over the target.
- `applies`: the source applies a method or paradigm from the target to a task/domain/setting.

## Recommended reporting

For a camera-ready human validation, report:

1. number of annotators and adjudication rule;
2. support rate for `supported` and `supported-or-partial`;
3. relation-type precision;
4. direction correctness;
5. Cohen/Fleiss agreement if two or more annotators label the same rows;
6. comparison between deterministic protocol labels and human labels.
"""


def build_pack() -> Dict[str, Any]:
    all_rows = protocol._iter_semantic_rows()
    sample = _attach_abstracts(_select_annotation_sample(all_rows))
    summary = _summarize(sample)

    return {
        "experiment_type": "semantic_edge_human_validation_pack",
        "scope_note": (
            "Human-validation-ready annotation package for semantic MEKG edges. "
            "The CSV is intentionally blank in human-label columns; the included protocol labels are deterministic references, "
            "not human annotations."
        ),
        "human_labels_completed": False,
        "annotation_csv": "semantic_edge_annotation_sample_blinded.csv",
        "guideline": "semantic_edge_annotation_guideline.md",
        "deterministic_reference": "deterministic_protocol_reference.json",
        "summary": summary,
        "sample": sample,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_pack()

    annotation_rows = _annotation_csv_rows(payload["sample"])
    csv_path = OUTPUT_DIR / payload["annotation_csv"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(annotation_rows[0]))
        writer.writeheader()
        writer.writerows(annotation_rows)

    (OUTPUT_DIR / payload["guideline"]).write_text(_guideline_text(), encoding="utf-8")
    (OUTPUT_DIR / payload["deterministic_reference"]).write_text(
        json.dumps(
            [
                {
                    "sample_id": row["sample_id"],
                    "relation_type": row["relation_type"],
                    "confidence_bucket": row["confidence_bucket"],
                    "protocol_label": row["protocol_label"],
                    "failure_mode": row["failure_mode"],
                    "temporal_ok": row["temporal_ok"],
                    "source_cue": row["source_cue"],
                    "target_role_ok": row["target_role_ok"],
                    "matched_control_delta": row["matched_control_delta"],
                }
                for row in payload["sample"]
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    summary_payload = dict(payload)
    summary_payload.pop("sample")
    (OUTPUT_DIR / "semantic_edge_human_validation_pack.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    s = payload["summary"]
    lines = [
        "# Semantic-Edge Human Validation Pack",
        "",
        f"- Human labels completed: {payload['human_labels_completed']}",
        f"- Annotation sample rows: {s['sample_count']}",
        f"- Annotation CSV: `{payload['annotation_csv']}`",
        f"- Guideline: `{payload['guideline']}`",
        f"- Deterministic reference: `{payload['deterministic_reference']}`",
        f"- Deterministic supported-or-partial rate on sample: {s['deterministic_supported_or_partial_rate']:.3f}",
        "",
        "| Relation | N | Det. supported | Det. partial | Det. unsupported | Det. supported-or-partial | Control win |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for rel_type, row in s["by_relation"].items():
        lines.append(
            "| {rel} | {n} | {sup} | {part} | {unsup} | {rate:.3f} | {win:.3f} |".format(
                rel=rel_type,
                n=row["count"],
                sup=row["deterministic_supported"],
                part=row["deterministic_partial"],
                unsup=row["deterministic_unsupported"],
                rate=row["deterministic_supported_or_partial_rate"],
                win=row["matched_control_win_rate"],
            )
        )
    lines.extend(
        [
            "",
            "Important: the table above reports deterministic protocol labels only. "
            "Do not cite it as human annotation until the blank human-label columns in the CSV are completed by annotators.",
        ]
    )
    (OUTPUT_DIR / "semantic_edge_human_validation_pack.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
