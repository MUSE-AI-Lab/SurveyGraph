from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit
from experiments.expanded_claim_citation_audit import (
    build_paper_lookup,
    cite_keys,
    clean_tex,
    tokens,
    _evidence_for_key,
)


OUTPUT_DIR = ROOT / "outputs" / "section_reference_alignment_audit_20260526"
EXCLUDED_SECTION_PAT = re.compile(r"\b(abstract|introduction|conclusion|references|acknowledg|appendix)\b", re.I)


def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def split_top_level_sections(tex: str) -> List[Tuple[str, str]]:
    matches = list(re.finditer(r"\\section\*?\{([^{}]+)\}", tex or ""))
    sections: List[Tuple[str, str]] = []
    for idx, match in enumerate(matches):
        title = clean_tex(match.group(1))
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(tex)
        body = tex[start:end]
        if title and not EXCLUDED_SECTION_PAT.search(title):
            sections.append((title, body))
    return sections


def _score_section(title: str, body: str, lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    keys = cite_keys(body)
    cited_papers: List[Dict[str, Any]] = []
    missing_keys: List[str] = []
    for key in keys:
        paper = _evidence_for_key(lookup, key)
        if paper is None:
            missing_keys.append(key)
        else:
            cited_papers.append(paper)

    query_tokens = tokens(f"{title} {clean_tex(body)[:3000]}")
    evidence_tokens = tokens(
        " ".join(
            f"{paper.get('title', '')} {paper.get('abstract', '')} {str(paper.get('md_text', ''))[:10000]}"
            for paper in cited_papers
        )
    )
    overlap = query_tokens & evidence_tokens
    precision = len(overlap) / len(query_tokens) if query_tokens else 0.0
    recall = len(overlap) / len(evidence_tokens) if evidence_tokens else 0.0
    jaccard = len(overlap) / len(query_tokens | evidence_tokens) if (query_tokens or evidence_tokens) else 0.0
    if not keys:
        bucket = "uncited"
    elif precision >= 0.18 and len(overlap) >= 6:
        bucket = "aligned"
    elif precision >= 0.10 and len(overlap) >= 3:
        bucket = "partially_aligned"
    else:
        bucket = "weak_alignment"

    return {
        "title": title,
        "citation_keys": keys,
        "citation_count": len(keys),
        "matched_citation_count": len(cited_papers),
        "missing_citation_keys": missing_keys,
        "alignment_precision": precision,
        "alignment_recall": recall,
        "alignment_jaccard": jaccard,
        "overlap_count": len(overlap),
        "overlap_terms": sorted(overlap)[:24],
        "bucket": bucket,
        "cited_titles": [paper.get("title", "") for paper in cited_papers[:8]],
    }


def build_audit() -> Dict[str, Any]:
    per_run: List[Dict[str, Any]] = []
    section_rows: List[Dict[str, Any]] = []

    for run in audit.load_archived_runs():
        tex_path = run.base_dir / "latex" / "survey.tex"
        if not tex_path.exists():
            continue
        tex = tex_path.read_text(encoding="utf-8", errors="ignore")
        lookup = build_paper_lookup(run.base_dir)
        rows = []
        for title, body in split_top_level_sections(tex):
            row = {
                "run_id": run.run_id,
                "topic": run.label,
                **_score_section(title, body, lookup),
            }
            rows.append(row)
            section_rows.append(row)

        bucket_counts = {bucket: sum(1 for row in rows if row["bucket"] == bucket) for bucket in ("aligned", "partially_aligned", "weak_alignment", "uncited")}
        per_run.append(
            {
                "run_id": run.run_id,
                "topic": run.label,
                "section_count": len(rows),
                "cited_section_count": sum(1 for row in rows if row["citation_count"] > 0),
                "uncited_section_count": bucket_counts["uncited"],
                "weak_alignment_count": bucket_counts["weak_alignment"],
                "mean_alignment_precision": _mean(row["alignment_precision"] for row in rows if row["citation_count"] > 0),
                "mean_citation_count": _mean(row["citation_count"] for row in rows),
                "bucket_counts": bucket_counts,
            }
        )

    section_count = len(section_rows)
    overall = {
        "section_count": section_count,
        "cited_section_count": sum(1 for row in section_rows if row["citation_count"] > 0),
        "uncited_section_rate": sum(1 for row in section_rows if row["bucket"] == "uncited") / section_count if section_count else 0.0,
        "weak_alignment_rate": sum(1 for row in section_rows if row["bucket"] == "weak_alignment") / section_count if section_count else 0.0,
        "aligned_or_partial_rate": sum(1 for row in section_rows if row["bucket"] in {"aligned", "partially_aligned"}) / section_count if section_count else 0.0,
        "mean_alignment_precision": _mean(row["alignment_precision"] for row in section_rows if row["citation_count"] > 0),
        "mean_citation_count": _mean(row["citation_count"] for row in section_rows),
    }

    return {
        "experiment_type": "section_reference_alignment_audit",
        "scope_note": (
            "Zero-API section-reference alignment diagnostic over archived generated surveys. "
            "It computes lexical overlap between each top-level generated section and its locally cached cited evidence; "
            "it is a grounding proxy, not semantic entailment or human preference evaluation."
        ),
        "run_count": len(per_run),
        "overall": overall,
        "per_run": per_run,
        "sections": section_rows,
        "weak_examples": [row for row in section_rows if row["bucket"] in {"weak_alignment", "uncited"}][:12],
    }


def build_markdown(payload: Dict[str, Any]) -> str:
    overall = payload["overall"]
    lines = [
        "# Section-Reference Alignment Audit",
        "",
        f"- Runs: {payload['run_count']}",
        f"- Sections: {overall['section_count']}",
        f"- Mean alignment precision over cited sections: {overall['mean_alignment_precision']:.3f}",
        f"- Aligned-or-partial section rate: {overall['aligned_or_partial_rate']:.3f}",
        f"- Uncited section rate: {overall['uncited_section_rate']:.3f}",
        "",
        "| Topic | Sections | Cited | Uncited | Weak align | Mean align precision | Mean cites |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["per_run"]:
        lines.append(
            f"| {row['topic']} | {row['section_count']} | {row['cited_section_count']} | "
            f"{row['uncited_section_count']} | {row['weak_alignment_count']} | "
            f"{row['mean_alignment_precision']:.3f} | {row['mean_citation_count']:.1f} |"
        )
    lines.extend(
        [
            "",
            "> The metric is intentionally lexical and conservative. It complements graph-internal SC/WCR diagnostics "
            "by checking whether generated sections carry local citation evidence.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_audit()
    (OUTPUT_DIR / "section_reference_alignment_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "section_reference_alignment_audit.md").write_text(
        build_markdown(payload),
        encoding="utf-8",
    )
    print(f"Wrote outputs to {OUTPUT_DIR}")
    print((OUTPUT_DIR / "section_reference_alignment_audit.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
