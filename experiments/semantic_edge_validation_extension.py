
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import offline_real_revision_audit as base

OUT = ROOT / "outputs" / "semantic_edge_validation_extension_20260525"
SEMANTIC = set(base.SEMANTIC_RELATIONS)
TARGET_ROLE_RE = re.compile(r"\b(survey|review|benchmark|bench|dataset|corpus|leaderboard|evaluation|evaluating|challenge)\b", re.I)


def target_role_ok(rel_type: str, target_title: str) -> bool:
    # Reviewer-identified failure mode mainly affects lineage-style edges.
    # For applies, dataset/task target papers can be legitimate, so we do not apply this filter.
    if rel_type in {"extends", "improves"}:
        return TARGET_ROLE_RE.search(target_title or "") is None
    return True


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for rel_type in base.SEMANTIC_RELATIONS:
        subset = [r for r in rows if r["relation_type"] == rel_type]
        if not subset:
            out[rel_type] = {"count": 0}
            continue
        strict = [r for r in subset if r["strict_rule_validated"]]
        out[rel_type] = {
            "count": len(subset),
            "strict_rule_validated": len(strict),
            "strict_rule_validated_rate": len(strict) / len(subset),
            "temporal_ok_rate": mean([r["temporal_ok"] for r in subset]),
            "source_cue_rate": mean([r["source_cue"] for r in subset]),
            "target_role_ok_rate": mean([r["target_role_ok"] for r in subset]),
            "confidence_ge_0_7_rate": mean([r["confidence_ge_0_7"] for r in subset]),
            "avg_confidence": mean([r["confidence"] for r in subset]),
        }
    strict_all = [r for r in rows if r["strict_rule_validated"]]
    out["overall"] = {
        "count": len(rows),
        "strict_rule_validated": len(strict_all),
        "strict_rule_validated_rate": len(strict_all) / len(rows) if rows else 0.0,
        "temporal_ok_rate": mean([r["temporal_ok"] for r in rows]) if rows else 0.0,
        "source_cue_rate": mean([r["source_cue"] for r in rows]) if rows else 0.0,
        "target_role_ok_rate": mean([r["target_role_ok"] for r in rows]) if rows else 0.0,
        "confidence_ge_0_7_rate": mean([r["confidence_ge_0_7"] for r in rows]) if rows else 0.0,
        "avg_confidence": mean([r["confidence"] for r in rows]) if rows else 0.0,
    }
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    runs = base.load_archived_runs()
    rows: List[Dict[str, Any]] = []
    examples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for run in runs:
        papers = {p.get("id"): p for p in run.mekg.get("papers", [])}
        for rel in run.mekg.get("relations", []):
            rel_type = rel.get("type")
            if rel_type not in SEMANTIC:
                continue
            src = papers.get(rel.get("source"))
            tgt = papers.get(rel.get("target"))
            if not src or not tgt:
                continue
            confidence = float(rel.get("confidence", 0.0) or 0.0)
            src_year = src.get("year")
            tgt_year = tgt.get("year")
            temporal_ok = isinstance(src_year, int) and isinstance(tgt_year, int) and src_year >= tgt_year
            source_cue = base.source_cue_present(rel_type, src.get("title", ""), src.get("abstract", ""))
            role_ok = target_role_ok(rel_type, tgt.get("title", ""))
            conf_ok = confidence >= 0.7
            strict = bool(temporal_ok and source_cue and role_ok and conf_ok)
            row = {
                "run_id": run.run_id,
                "relation_type": rel_type,
                "source_title": src.get("title", ""),
                "target_title": tgt.get("title", ""),
                "source_year": src_year,
                "target_year": tgt_year,
                "confidence": confidence,
                "temporal_ok": temporal_ok,
                "source_cue": source_cue,
                "target_role_ok": role_ok,
                "confidence_ge_0_7": conf_ok,
                "strict_rule_validated": strict,
            }
            rows.append(row)
            if strict and len(examples[rel_type]) < 5:
                examples[rel_type].append(row)

    result = {
        "experiment_type": "semantic_edge_rule_validated_subset_audit",
        "scope_note": (
            "Zero-API deterministic extension over all archived extends/improves/applies edges. "
            "An edge enters the high-precision subset only if it has temporal direction consistency, "
            "explicit source-side lexical cue support, confidence >= 0.7, and no survey/benchmark/dataset-style target for lineage edges. "
            "This is a rule-validated high-precision subset diagnostic, not human precision/recall."
        ),
        "runs": [r.run_id for r in runs],
        "criteria": {
            "temporal_direction": "source_year >= target_year",
            "source_cue": "relation-specific lexical cue in source title/abstract",
            "confidence": ">= 0.7",
            "target_role": "extends/improves targets do not match survey/review/benchmark/dataset/evaluation cues",
        },
        "summary": summarize(rows),
        "strict_examples": examples,
    }
    (OUT / "semantic_edge_rule_validated_subset_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    s = result["summary"]
    lines = [
        "# Semantic Edge Rule-Validated Subset Audit",
        "",
        f"- Archived semantic edges audited: {s['overall']['count']}",
        f"- Strict rule-validated subset: {s['overall']['strict_rule_validated']} ({s['overall']['strict_rule_validated_rate']*100:.1f}%)",
        f"- Temporal direction consistency: {s['overall']['temporal_ok_rate']*100:.1f}%",
        f"- Explicit source cue support: {s['overall']['source_cue_rate']*100:.1f}%",
        f"- Target-role admissibility: {s['overall']['target_role_ok_rate']*100:.1f}%",
        "",
        "| Relation | Edges | Strict subset | Strict rate | Temporal ok | Source cue | Target role ok |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for rel_type in base.SEMANTIC_RELATIONS:
        r = s[rel_type]
        lines.append(
            f"| `{rel_type}` | {r['count']} | {r['strict_rule_validated']} | {r['strict_rule_validated_rate']*100:.1f}% | "
            f"{r['temporal_ok_rate']*100:.1f}% | {r['source_cue_rate']*100:.1f}% | {r['target_role_ok_rate']*100:.1f}% |"
        )
    lines.append("")
    lines.append("> This is a high-precision subset diagnostic: it identifies the edge portion that simultaneously satisfies conservative rule evidence, rather than estimating full human precision/recall.")
    (OUT / "semantic_edge_rule_validated_subset_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "out_dir": str(OUT),
        "overall": s["overall"],
        "by_relation": {k: s[k] for k in base.SEMANTIC_RELATIONS},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
