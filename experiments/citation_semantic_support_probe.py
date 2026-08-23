from __future__ import annotations

import argparse
import json
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

SOURCE_AUDIT = ROOT / "outputs" / "expanded_claim_citation_audit_20260526" / "expanded_claim_citation_audit.json"
OUTPUT_DIR = ROOT / "outputs" / "citation_semantic_support_probe_20260526"


def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _safe_text(s: str) -> str:
    return " ".join((s or "").replace("\\\\", " ").split())


def _load_samples() -> List[Dict[str, Any]]:
    payload = json.loads(SOURCE_AUDIT.read_text(encoding="utf-8"))
    return list(payload.get("samples", []))


class SimilarityBackend:
    def __init__(self, texts: List[str]) -> None:
        self.encoder_name = "tfidf_word_char_fallback"
        self._model = None
        self._vectorizer = None
        self._matrix = None
        self._init(texts)

    def _init(self, texts: List[str]) -> None:
        # Prefer a locally cached dense encoder, but never download anything.
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer("BAAI/bge-small-en-v1.5", local_files_only=True)
            self.encoder_name = "sentence-transformers/BAAI/bge-small-en-v1.5-local"
            return
        except Exception:
            self._model = None

        self._vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=1,
        )
        self._matrix = self._vectorizer.fit_transform(texts)

    def pair_similarity(self, left: str, rights: List[str]) -> float:
        left = _safe_text(left)
        rights = [_safe_text(r) for r in rights if _safe_text(r)]
        if not left or not rights:
            return 0.0
        if self._model is not None:
            emb = self._model.encode(
                [left] + rights,
                batch_size=16,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            left_vec = np.asarray(emb[0], dtype=np.float32)
            right_vecs = np.asarray(emb[1:], dtype=np.float32)
            return float(np.max(np.dot(right_vecs, left_vec)))

        assert self._vectorizer is not None
        vecs = self._vectorizer.transform([left] + rights)
        sims = cosine_similarity(vecs[0], vecs[1:])[0]
        return float(np.max(sims)) if len(sims) else 0.0


def _norm_title(title: str) -> str:
    return " ".join(_safe_text(title).lower().split())


def _semantic_label(score: float) -> str:
    if score >= 0.55:
        return "semantic_supported"
    if score >= 0.35:
        return "semantic_partial"
    return "semantic_weak"


def build_probe(max_samples: int | None = None) -> Dict[str, Any]:
    samples = _load_samples()
    if max_samples is not None:
        samples = samples[:max_samples]

    corpus_texts: List[str] = []
    for row in samples:
        corpus_texts.append(_safe_text(row.get("sentence", "")))
        corpus_texts.extend(_safe_text(t) for t in row.get("cited_titles", []))
    backend = SimilarityBackend([t for t in corpus_texts if t])

    all_titles_by_topic: Dict[str, List[str]] = defaultdict(list)
    for row in samples:
        topic = row.get("topic", "")
        for title in row.get("cited_titles", []):
            if _safe_text(title):
                all_titles_by_topic[topic].append(title)
    for topic, titles in list(all_titles_by_topic.items()):
        deduped: Dict[str, str] = {}
        for title in titles:
            deduped.setdefault(_norm_title(title), title)
        all_titles_by_topic[topic] = list(deduped.values())

    rows: List[Dict[str, Any]] = []
    for row in samples:
        sentence = row.get("sentence", "")
        cited_titles = row.get("cited_titles", [])
        score = backend.pair_similarity(sentence, cited_titles)
        cited_norms = {_norm_title(t) for t in cited_titles}
        topic_titles = all_titles_by_topic.get(row.get("topic", ""), [])
        hard_negatives = [t for t in topic_titles if _norm_title(t) not in cited_norms]
        if len(hard_negatives) < 5:
            hard_negatives = [
                t
                for titles in all_titles_by_topic.values()
                for t in titles
                if _norm_title(t) not in cited_norms
            ]
        hard_negative_score = backend.pair_similarity(sentence, hard_negatives[:80])
        margin = score - hard_negative_score
        semantic_label = _semantic_label(score)
        rows.append(
            {
                "run_id": row.get("run_id"),
                "topic": row.get("topic"),
                "sentence": row.get("sentence", ""),
                "citation_keys": row.get("citation_keys", []),
                "citation_count": row.get("citation_count", 0),
                "matched_citation_count": row.get("matched_citation_count", 0),
                "cited_titles": cited_titles,
                "lexical_label": row.get("label"),
                "overlap_precision": row.get("overlap_precision", 0.0),
                "max_semantic_similarity": score,
                "hard_negative_max_similarity": hard_negative_score,
                "cited_minus_hard_negative_margin": margin,
                "cited_beats_hard_negative": margin > 0.0,
                "semantic_label": semantic_label,
            }
        )

    semantic_counts = Counter(row["semantic_label"] for row in rows)
    lexical_counts = Counter(row["lexical_label"] for row in rows)
    crosstab: Dict[str, Dict[str, int]] = defaultdict(lambda: Counter())
    by_lexical: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        crosstab[row["lexical_label"]][row["semantic_label"]] += 1
    for lexical_label in sorted(lexical_counts):
        label_rows = [row for row in rows if row["lexical_label"] == lexical_label]
        by_lexical[lexical_label] = {
            "count": len(label_rows),
            "mean_max_semantic_similarity": _mean(row["max_semantic_similarity"] for row in label_rows),
            "mean_hard_negative_similarity": _mean(row["hard_negative_max_similarity"] for row in label_rows),
            "mean_cited_minus_hard_negative_margin": _mean(
                row["cited_minus_hard_negative_margin"] for row in label_rows
            ),
            "cited_beats_hard_negative_rate": _mean(
                bool(row["cited_beats_hard_negative"]) for row in label_rows
            ),
            "semantic_supported_or_partial_rate": _mean(
                row["semantic_label"] in {"semantic_supported", "semantic_partial"}
                for row in label_rows
            ),
        }

    sample_count = len(rows)
    return {
        "experiment_type": "citation_semantic_support_probe",
        "scope_note": (
            "Zero-API semantic support proxy for the 160 cited-sentence lexical anchor audit. "
            "It compares each cited sentence to cited paper titles with a locally cached dense encoder when available "
            "and TF-IDF fallback otherwise. This is not a human faithfulness label or NLI entailment score."
        ),
        "source_audit": str(SOURCE_AUDIT.relative_to(ROOT)),
        "sample_count": sample_count,
        "encoder": backend.encoder_name,
        "overall": {
            "mean_max_semantic_similarity": _mean(row["max_semantic_similarity"] for row in rows),
            "semantic_supported": semantic_counts["semantic_supported"],
            "semantic_partial": semantic_counts["semantic_partial"],
            "semantic_weak": semantic_counts["semantic_weak"],
            "semantic_supported_or_partial_rate": (
                (semantic_counts["semantic_supported"] + semantic_counts["semantic_partial"]) / sample_count
                if sample_count
                else 0.0
            ),
            "lexical_anchored_or_partial_rate": (
                (lexical_counts["anchored"] + lexical_counts["partial_anchor"]) / sample_count
                if sample_count
                else 0.0
            ),
        },
        "negative_control": {
            "mean_hard_negative_similarity": _mean(row["hard_negative_max_similarity"] for row in rows),
            "mean_cited_minus_hard_negative_margin": _mean(
                row["cited_minus_hard_negative_margin"] for row in rows
            ),
            "cited_beats_hard_negative_count": sum(bool(row["cited_beats_hard_negative"]) for row in rows),
            "cited_beats_hard_negative_rate": _mean(
                bool(row["cited_beats_hard_negative"]) for row in rows
            ),
        },
        "lexical_vs_semantic_crosstab": {k: dict(v) for k, v in crosstab.items()},
        "by_lexical_label": by_lexical,
        "samples": rows,
        "weak_semantic_examples": [
            row for row in sorted(rows, key=lambda r: r["max_semantic_similarity"])[:12]
        ],
    }


def build_markdown(payload: Dict[str, Any]) -> str:
    overall = payload["overall"]
    lines = [
        "# Citation Semantic-Support Probe",
        "",
        f"- Samples: {payload['sample_count']}",
        f"- Encoder: {payload['encoder']}",
        f"- Mean max semantic similarity: {overall['mean_max_semantic_similarity']:.3f}",
        f"- Semantic supported / partial / weak: {overall['semantic_supported']} / "
        f"{overall['semantic_partial']} / {overall['semantic_weak']}",
        f"- Semantic supported-or-partial rate: {overall['semantic_supported_or_partial_rate']:.3f}",
        f"- Lexical anchored-or-partial rate: {overall['lexical_anchored_or_partial_rate']:.3f}",
        f"- Cited title beats hard negative: {payload['negative_control']['cited_beats_hard_negative_rate']:.3f} "
        f"({payload['negative_control']['cited_beats_hard_negative_count']}/{payload['sample_count']})",
        f"- Mean cited-minus-negative margin: {payload['negative_control']['mean_cited_minus_hard_negative_margin']:.3f}",
        "",
        "## By lexical label",
        "",
        "| Lexical label | Count | Mean cited sim. | Mean neg. sim. | Mean margin | Cited beats neg. |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, row in payload["by_lexical_label"].items():
        lines.append(
            f"| {label} | {row['count']} | {row['mean_max_semantic_similarity']:.3f} | "
            f"{row['mean_hard_negative_similarity']:.3f} | "
            f"{row['mean_cited_minus_hard_negative_margin']:.3f} | "
            f"{row['cited_beats_hard_negative_rate']:.3f} |"
        )
    lines += [
        "",
        "## Crosstab",
        "",
        "| Lexical label | Semantic supported | Semantic partial | Semantic weak |",
        "|---|---:|---:|---:|",
    ]
    for label, row in payload["lexical_vs_semantic_crosstab"].items():
        lines.append(
            f"| {label} | {row.get('semantic_supported', 0)} | "
            f"{row.get('semantic_partial', 0)} | {row.get('semantic_weak', 0)} |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run citation semantic support probe over lexical citation audit samples.")
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
    (out_dir / "citation_semantic_support_probe.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "citation_semantic_support_probe.md").write_text(
        build_markdown(payload),
        encoding="utf-8",
    )
    print(f"Wrote outputs to {out_dir}")
    print((out_dir / "citation_semantic_support_probe.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
