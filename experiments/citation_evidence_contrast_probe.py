from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit

SOURCE_AUDIT = ROOT / "outputs" / "expanded_claim_citation_audit_20260526" / "expanded_claim_citation_audit.json"
OUTPUT_DIR = ROOT / "outputs" / "citation_evidence_contrast_probe_20260526"


def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _safe_text(s: str, max_chars: int | None = None) -> str:
    text = " ".join((s or "").replace("\\\\", " ").split())
    return text[:max_chars] if max_chars else text


def _norm_arxiv_id(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"^arxiv[_:\s-]*", "", s, flags=re.I)
    s = s.replace("_", ".")
    return s.lower()


def _paper_evidence_text(paper: Dict[str, Any]) -> str:
    title = paper.get("title", "")
    abstract = paper.get("abstract", "")
    md_text = paper.get("md_text", "")
    # Keep enough local evidence to include title + abstract + beginning of body,
    # but avoid making the dense encoder dominated by long unrelated tails.
    return _safe_text(f"{title}. {abstract}. {md_text}", max_chars=1800)


class SimilarityBackend:
    def __init__(self, texts: List[str]) -> None:
        self.encoder_name = "tfidf_char_evidence_contrast"
        self._vectorizer = None
        self._init(texts)

    def _init(self, texts: List[str]) -> None:
        # Deterministic local backend. Dense claim-vs-many-document contrast is
        # slow on this workspace and the title-level dense probe is already
        # reported separately; here we want a fast evidence-text contrast.
        self._vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=1,
        ).fit(texts)

    def max_similarity(self, query: str, docs: List[str]) -> float:
        query = _safe_text(query)
        docs = [_safe_text(d) for d in docs if _safe_text(d)]
        if not query or not docs:
            return 0.0
        assert self._vectorizer is not None
        vecs = self._vectorizer.transform([query] + docs)
        sims = cosine_similarity(vecs[0], vecs[1:])[0]
        return float(np.max(sims)) if len(sims) else 0.0


def _load_audit_samples() -> List[Dict[str, Any]]:
    return json.loads(SOURCE_AUDIT.read_text(encoding="utf-8")).get("samples", [])


def _run_maps() -> Dict[str, Dict[str, Any]]:
    maps: Dict[str, Dict[str, Any]] = {}
    for run in audit.load_archived_runs():
        by_arxiv: Dict[str, Dict[str, Any]] = {}
        for paper in run.mekg.get("papers", []):
            ids = {
                _norm_arxiv_id(paper.get("id", "")),
                _norm_arxiv_id(paper.get("arxiv_id", "")),
            }
            for pid in ids:
                if pid:
                    by_arxiv[pid] = paper
        maps[run.run_id] = {"run": run, "by_arxiv": by_arxiv, "papers": run.mekg.get("papers", [])}
    return maps


def _candidate_negative_docs(
    papers: List[Dict[str, Any]],
    cited_papers: List[Dict[str, Any]],
    limit: int = 80,
) -> List[str]:
    cited_ids = {_norm_arxiv_id(p.get("id", "")) for p in cited_papers} | {_norm_arxiv_id(p.get("arxiv_id", "")) for p in cited_papers}
    rows = []
    for paper in papers:
        ids = {_norm_arxiv_id(paper.get("id", "")), _norm_arxiv_id(paper.get("arxiv_id", ""))}
        if ids & cited_ids:
            continue
        rows.append(_paper_evidence_text(paper))
    return rows[:limit]


def build_probe(max_samples: int | None = None) -> Dict[str, Any]:
    samples = _load_audit_samples()
    if max_samples is not None:
        samples = samples[:max_samples]
    maps = _run_maps()

    matched_rows: List[Dict[str, Any]] = []
    corpus: List[str] = []
    for row in samples:
        run_map = maps.get(row.get("run_id"), {})
        by_arxiv = run_map.get("by_arxiv", {})
        cited_papers = []
        for key in row.get("citation_keys", []):
            paper = by_arxiv.get(_norm_arxiv_id(key))
            if paper:
                cited_papers.append(paper)
        if not cited_papers:
            continue
        cited_docs = [_paper_evidence_text(p) for p in cited_papers]
        negative_docs = _candidate_negative_docs(run_map.get("papers", []), cited_papers)
        if not negative_docs:
            continue
        matched_rows.append({"row": row, "cited_docs": cited_docs, "negative_docs": negative_docs})
        corpus.append(_safe_text(row.get("sentence", "")))
        corpus.extend(cited_docs[:2])
        corpus.extend(negative_docs[:8])

    backend = SimilarityBackend(corpus)
    out_rows: List[Dict[str, Any]] = []
    for item in matched_rows:
        row = item["row"]
        sentence = row.get("sentence", "")
        cited_sim = backend.max_similarity(sentence, item["cited_docs"])
        neg_sim = backend.max_similarity(sentence, item["negative_docs"])
        margin = cited_sim - neg_sim
        out_rows.append(
            {
                "run_id": row.get("run_id"),
                "topic": row.get("topic"),
                "sentence": sentence,
                "citation_keys": row.get("citation_keys", []),
                "citation_count": row.get("citation_count", 0),
                "lexical_label": row.get("label"),
                "cited_titles": row.get("cited_titles", []),
                "cited_evidence_similarity": cited_sim,
                "hard_negative_evidence_similarity": neg_sim,
                "cited_minus_hard_negative_margin": margin,
                "cited_beats_hard_negative": margin > 0.0,
                "overlap_precision": row.get("overlap_precision", 0.0),
            }
        )

    by_label: Dict[str, Dict[str, Any]] = {}
    label_counts = Counter(row["lexical_label"] for row in out_rows)
    for label in sorted(label_counts):
        rows = [row for row in out_rows if row["lexical_label"] == label]
        by_label[label] = {
            "count": len(rows),
            "mean_cited_evidence_similarity": _mean(row["cited_evidence_similarity"] for row in rows),
            "mean_hard_negative_evidence_similarity": _mean(row["hard_negative_evidence_similarity"] for row in rows),
            "mean_cited_minus_negative_margin": _mean(row["cited_minus_hard_negative_margin"] for row in rows),
            "cited_beats_hard_negative_rate": _mean(bool(row["cited_beats_hard_negative"]) for row in rows),
        }

    sample_count = len(out_rows)
    return {
        "experiment_type": "citation_evidence_contrast_probe",
        "scope_note": (
            "Zero-API evidence-level citation contrast over the expanded cited-sentence audit. "
            "Each generated cited sentence is compared with locally archived title+abstract/body snippets "
            "from the cited paper(s) and with non-cited papers from the same archived run as hard negatives. "
            "This is still a proxy, not a human or NLI faithfulness judgment."
        ),
        "source_audit": str(SOURCE_AUDIT.relative_to(ROOT)),
        "sample_count": sample_count,
        "matched_evidence_count": sample_count,
        "encoder": backend.encoder_name,
        "overall": {
            "mean_cited_evidence_similarity": _mean(row["cited_evidence_similarity"] for row in out_rows),
            "mean_hard_negative_evidence_similarity": _mean(row["hard_negative_evidence_similarity"] for row in out_rows),
            "mean_cited_minus_negative_margin": _mean(row["cited_minus_hard_negative_margin"] for row in out_rows),
            "cited_beats_hard_negative_count": sum(bool(row["cited_beats_hard_negative"]) for row in out_rows),
            "cited_beats_hard_negative_rate": _mean(bool(row["cited_beats_hard_negative"]) for row in out_rows),
        },
        "by_lexical_label": by_label,
        "samples": out_rows,
        "worst_margin_examples": sorted(out_rows, key=lambda r: r["cited_minus_hard_negative_margin"])[:12],
    }


def build_markdown(payload: Dict[str, Any]) -> str:
    overall = payload["overall"]
    lines = [
        "# Citation Evidence Contrast Probe",
        "",
        f"- Samples with matched evidence: {payload['sample_count']}",
        f"- Encoder: {payload['encoder']}",
        f"- Mean cited evidence similarity: {overall['mean_cited_evidence_similarity']:.3f}",
        f"- Mean hard-negative evidence similarity: {overall['mean_hard_negative_evidence_similarity']:.3f}",
        f"- Mean cited-minus-negative margin: {overall['mean_cited_minus_negative_margin']:.3f}",
        f"- Cited beats hard negative: {overall['cited_beats_hard_negative_rate']:.3f} "
        f"({overall['cited_beats_hard_negative_count']}/{payload['sample_count']})",
        "",
        "| Lexical label | N | Cited sim. | Neg. sim. | Margin | Cited > neg. |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, row in payload["by_lexical_label"].items():
        lines.append(
            f"| {label} | {row['count']} | {row['mean_cited_evidence_similarity']:.3f} | "
            f"{row['mean_hard_negative_evidence_similarity']:.3f} | "
            f"{row['mean_cited_minus_negative_margin']:.3f} | "
            f"{row['cited_beats_hard_negative_rate']:.3f} |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run evidence-level citation contrast probe.")
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_probe(max_samples=args.max_samples)
    (out_dir / "citation_evidence_contrast_probe.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "citation_evidence_contrast_probe.md").write_text(
        build_markdown(payload),
        encoding="utf-8",
    )
    print(f"Wrote outputs to {out_dir}")
    print((out_dir / "citation_evidence_contrast_probe.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
