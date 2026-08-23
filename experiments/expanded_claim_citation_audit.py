from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit


OUTPUT_DIR = ROOT / "outputs" / "expanded_claim_citation_audit_20260526"

STOPWORDS = set(
    "the a an and or of to in on for with by from via using based this that these those is are was were "
    "be been as at into between among over under through than then such can may might should would could "
    "our their its it we they paper papers method methods model models system systems task tasks approach "
    "approaches results work works study studies survey surveys section table figure"
    .split()
)


def clean_tex(text: str) -> str:
    text = re.sub(r"(?m)%.*$", " ", text or "")
    text = re.sub(r"\\(section|subsection|subsubsection)\*?\{([^{}]*)\}", r". \2. ", text)
    text = re.sub(r"\\cite[a-zA-Z]*\{([^{}]+)\}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", text)
    text = re.sub(r"[{}$~^_]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> set[str]:
    toks = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", clean_tex(text).lower())
    return {tok for tok in toks if tok not in STOPWORDS and len(tok) > 3}


def split_cited_sentences(tex: str) -> List[str]:
    tex = re.sub(r"(?m)^%.*$", " ", tex or "")
    tex = re.sub(r"\n+", " ", tex)
    chunks = re.split(r"(?<=[.!?])\s+(?=(?:[A-Z0-9\\]|``))", tex)
    return [chunk.strip() for chunk in chunks if "\\cite" in chunk and 40 <= len(chunk) <= 1400]


def cite_keys(sentence: str) -> List[str]:
    keys: List[str] = []
    for match in re.finditer(r"\\cite[a-zA-Z]*\{([^{}]+)\}", sentence):
        for key in match.group(1).split(","):
            key = key.strip()
            if key:
                keys.append(key)
    return list(dict.fromkeys(keys))


def _norm_arxiv(value: str) -> str:
    value = str(value or "").strip()
    value = re.sub(r"^arxiv[:_]", "", value, flags=re.I)
    value = re.sub(r"v\d+$", "", value, flags=re.I)
    return value


def build_paper_lookup(run_dir: Path) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for path in (run_dir / "papers").glob("*.json"):
        try:
            paper = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        keys = {path.stem}
        for value in [paper.get("id"), paper.get("paper_id"), paper.get("arxiv_id")]:
            if value:
                raw = str(value)
                keys.add(raw)
                keys.add(raw.replace(":", "_"))
                arxiv = _norm_arxiv(raw)
                if arxiv:
                    keys.add(arxiv)
                    keys.add(f"arXiv_{arxiv}")
                    keys.add(f"arXiv:{arxiv}")
        for key in keys:
            lookup[key] = paper
    return lookup


def _evidence_for_key(lookup: Dict[str, Dict[str, Any]], key: str) -> Dict[str, Any] | None:
    variants = [key, key.replace(":", "_"), key.replace("_", ":"), _norm_arxiv(key), f"arXiv_{_norm_arxiv(key)}"]
    for variant in variants:
        if variant in lookup:
            return lookup[variant]
    return None


def _score_sentence(sentence: str, papers: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    claim_tokens = tokens(sentence)
    evidence_text = " ".join(
        f"{paper.get('title', '')} {paper.get('abstract', '')} {str(paper.get('md_text', ''))[:20000]}"
        for paper in papers
    )
    evidence_tokens = tokens(evidence_text)
    overlap = claim_tokens & evidence_tokens
    precision = len(overlap) / len(claim_tokens) if claim_tokens else 0.0
    recall = len(overlap) / len(evidence_tokens) if evidence_tokens else 0.0
    jaccard = len(overlap) / len(claim_tokens | evidence_tokens) if (claim_tokens or evidence_tokens) else 0.0
    if len(overlap) >= 5 and precision >= 0.18:
        label = "anchored"
    elif len(overlap) >= 3 and precision >= 0.10:
        label = "partial_anchor"
    else:
        label = "weak_or_missing_anchor"
    return {
        "claim_token_count": len(claim_tokens),
        "evidence_token_count": len(evidence_tokens),
        "overlap_count": len(overlap),
        "overlap_precision": precision,
        "overlap_recall": recall,
        "overlap_jaccard": jaccard,
        "overlap_terms": sorted(overlap)[:24],
        "label": label,
    }


def _sample_candidates(candidates: List[Dict[str, Any]], sample_per_run: int) -> List[Dict[str, Any]]:
    if sample_per_run <= 0 or len(candidates) <= sample_per_run:
        return candidates
    singles = [row for row in candidates if row["citation_count"] == 1]
    multis = [row for row in candidates if row["citation_count"] > 1]
    for group in (singles, multis):
        group.sort(key=lambda r: r["stable_hash"])
    single_quota = min(len(singles), sample_per_run // 2)
    multi_quota = min(len(multis), sample_per_run - single_quota)
    chosen = singles[:single_quota] + multis[:multi_quota]
    if len(chosen) < sample_per_run:
        chosen_hashes = {row["stable_hash"] for row in chosen}
        remainder = [row for row in sorted(candidates, key=lambda r: r["stable_hash"]) if row["stable_hash"] not in chosen_hashes]
        chosen.extend(remainder[: sample_per_run - len(chosen)])
    return sorted(chosen, key=lambda r: r["stable_hash"])


def build_audit(sample_per_run: int = 20) -> Dict[str, Any]:
    per_run: List[Dict[str, Any]] = []
    samples: List[Dict[str, Any]] = []

    for run in audit.load_archived_runs():
        run_dir = run.base_dir
        tex_path = run_dir / "latex" / "survey.tex"
        if not tex_path.exists():
            continue
        lookup = build_paper_lookup(run_dir)
        candidates: List[Dict[str, Any]] = []
        tex = tex_path.read_text(encoding="utf-8", errors="ignore")
        for sentence in split_cited_sentences(tex):
            keys = cite_keys(sentence)
            if not keys:
                continue
            cited_papers = []
            missing_keys = []
            for key in keys:
                paper = _evidence_for_key(lookup, key)
                if paper is None:
                    missing_keys.append(key)
                else:
                    cited_papers.append(paper)
            if not cited_papers:
                continue
            score = _score_sentence(sentence, cited_papers)
            row = {
                "run_id": run.run_id,
                "topic": run.label,
                "sentence": clean_tex(sentence),
                "citation_keys": keys,
                "citation_count": len(keys),
                "matched_citation_count": len(cited_papers),
                "missing_citation_keys": missing_keys,
                "cited_titles": [paper.get("title", "") for paper in cited_papers],
                **score,
            }
            row["stable_hash"] = hashlib.sha1(
                f"{run.run_id}\n{row['sentence']}\n{','.join(keys)}".encode("utf-8", errors="ignore")
            ).hexdigest()
            candidates.append(row)

        chosen = _sample_candidates(candidates, sample_per_run)
        samples.extend(chosen)
        counts = Counter(row["label"] for row in chosen)
        per_run.append(
            {
                "run_id": run.run_id,
                "topic": run.label,
                "candidate_sentence_count": len(candidates),
                "sample_count": len(chosen),
                "single_citation_count": sum(1 for row in chosen if row["citation_count"] == 1),
                "multi_citation_count": sum(1 for row in chosen if row["citation_count"] > 1),
                "anchored": counts["anchored"],
                "partial_anchor": counts["partial_anchor"],
                "weak_or_missing_anchor": counts["weak_or_missing_anchor"],
                "anchored_or_partial_rate": (counts["anchored"] + counts["partial_anchor"]) / len(chosen) if chosen else 0.0,
                "mean_overlap_precision": _mean(row["overlap_precision"] for row in chosen),
            }
        )

    label_counts = Counter(row["label"] for row in samples)
    by_citation_arity: Dict[str, Counter] = defaultdict(Counter)
    for row in samples:
        arity = "single" if row["citation_count"] == 1 else "multi"
        by_citation_arity[arity][row["label"]] += 1

    total = len(samples)
    overall = {
        "sample_count": total,
        "anchored": label_counts["anchored"],
        "partial_anchor": label_counts["partial_anchor"],
        "weak_or_missing_anchor": label_counts["weak_or_missing_anchor"],
        "anchored_or_partial_rate": (label_counts["anchored"] + label_counts["partial_anchor"]) / total if total else 0.0,
        "weak_or_missing_rate": label_counts["weak_or_missing_anchor"] / total if total else 0.0,
        "single_citation_count": sum(1 for row in samples if row["citation_count"] == 1),
        "multi_citation_count": sum(1 for row in samples if row["citation_count"] > 1),
        "mean_overlap_precision": _mean(row["overlap_precision"] for row in samples),
    }

    for row in samples:
        row.pop("stable_hash", None)

    return {
        "experiment_type": "expanded_claim_citation_audit",
        "scope_note": (
            "Deterministic zero-API lexical anchoring audit over generated survey sentences with local citations. "
            "Labels compare each cited sentence with repository-local cited titles, abstracts, and cached text; "
            "they are not human entailment labels and should be interpreted as citation-grounding triage."
        ),
        "sample_per_run": sample_per_run,
        "run_count": len(per_run),
        "overall": overall,
        "by_citation_arity": {key: dict(value) for key, value in by_citation_arity.items()},
        "per_run": per_run,
        "samples": samples,
        "weak_examples": [row for row in samples if row["label"] == "weak_or_missing_anchor"][:12],
    }


def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def build_markdown(payload: Dict[str, Any]) -> str:
    overall = payload["overall"]
    lines = [
        "# Expanded Claim-to-Citation Lexical Anchor Audit",
        "",
        f"- Runs: {payload['run_count']}",
        f"- Sampled cited sentences: {overall['sample_count']}",
        f"- Anchored / partial / weak-or-missing: {overall['anchored']} / {overall['partial_anchor']} / {overall['weak_or_missing_anchor']}",
        f"- Anchored-or-partial rate: {overall['anchored_or_partial_rate']:.3f}",
        f"- Single / multi citation sentences: {overall['single_citation_count']} / {overall['multi_citation_count']}",
        "",
        "| Topic | Candidates | Sample | Anchored | Partial | Weak/missing | Anchored/partial |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["per_run"]:
        lines.append(
            f"| {row['topic']} | {row['candidate_sentence_count']} | {row['sample_count']} | "
            f"{row['anchored']} | {row['partial_anchor']} | {row['weak_or_missing_anchor']} | "
            f"{row['anchored_or_partial_rate']:.3f} |"
        )
    lines.extend(
        [
            "",
            "> This audit is lexical grounding triage, not blinded human citation-faithfulness annotation. "
            "Weak/missing-anchor rows mark higher-risk claims for manual review.",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run expanded local claim-to-citation lexical anchoring audit.")
    parser.add_argument("--sample-per-run", type=int, default=20)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_audit(sample_per_run=args.sample_per_run)
    (out_dir / "expanded_claim_citation_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "expanded_claim_citation_audit.md").write_text(
        build_markdown(payload),
        encoding="utf-8",
    )
    print(f"Wrote outputs to {out_dir}")
    print((out_dir / "expanded_claim_citation_audit.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
