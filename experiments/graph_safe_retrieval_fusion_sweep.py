from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit
from experiments import review_response_audit as review
from experiments.embedding_retrieval_encoder_sensitivity import (
    LexicalRanker,
    TfidfRanker,
    DenseRanker,
    _evaluate_ranker,
    _graph_rank_from_base,
)

OUTPUT_DIR = ROOT / "outputs" / "graph_safe_retrieval_fusion_sweep_20260526"


def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _safe_fusion_ranker(base_ranker, graph_ranker, preserve_base: int):
    def rank(title: str, desc: str) -> List[Tuple[str, float]]:
        base = base_ranker.rank(title, desc)
        graph = graph_ranker(title, desc)
        seen = set()
        fused: List[Tuple[str, float]] = []
        # A very large offset ensures the preserved lexical/dense anchors remain
        # in front under the top-k budget; graph expansion only fills the rest.
        for pid, score in base[:preserve_base]:
            fused.append((pid, float(score) + 1_000_000.0))
            seen.add(pid)
        for pid, score in graph:
            if pid not in seen:
                fused.append((pid, score))
                seen.add(pid)
        return fused

    return rank


def build_eval() -> Dict[str, Any]:
    dense_models = ["sentence-transformers/all-MiniLM-L6-v2", "BAAI/bge-small-en-v1.5"]
    per_topic: List[Dict[str, Any]] = []
    load_failures: List[Dict[str, Any]] = []
    preserve_values = [0, 1, 2, 3, 4, 5]

    for run in audit.load_archived_runs():
        target_info = review.collect_survey_reference_targets(run)
        target_ids = {audit.sanitize_key(pid) for pid in target_info["external_target_ids"]}
        if len(target_ids) < 3:
            continue

        context = audit.build_retrieval_context(run)
        papers = context["papers"]
        paper_map = context["paper_map"]
        centrality = context["centrality"]
        adjacency, pairs = audit.build_adjacency(run, paper_map)

        rankers = [
            LexicalRanker(papers),
            TfidfRanker(
                "tfidf_word_unigram_bigram",
                papers,
                TfidfVectorizer(lowercase=True, stop_words="english", ngram_range=(1, 2), min_df=1),
            ),
            TfidfRanker(
                "tfidf_char_3_5",
                papers,
                TfidfVectorizer(lowercase=True, analyzer="char_wb", ngram_range=(3, 5), min_df=1),
            ),
        ]
        for model_name in dense_models:
            try:
                rankers.append(DenseRanker(f"dense_{model_name.replace('/', '__')}", papers, model_name))
            except Exception as exc:  # noqa: BLE001
                load_failures.append({"run_id": run.run_id, "topic": run.label, "model": model_name, "error": repr(exc)})

        encoders: Dict[str, Any] = {}
        for ranker in rankers:
            graph_rank = _graph_rank_from_base(ranker, paper_map, centrality, adjacency, max_hops=1)
            rows: Dict[str, Any] = {}
            for preserve in preserve_values:
                if preserve == 0:
                    eval_rank = graph_rank
                    mode = "graph_only"
                elif preserve == 5:
                    eval_rank = ranker.rank
                    mode = "base_only"
                else:
                    eval_rank = _safe_fusion_ranker(ranker, graph_rank, preserve)
                    mode = f"preserve_base_{preserve}"
                rows[mode] = _evaluate_ranker(run, eval_rank, pairs, target_ids)
            encoders[ranker.name] = rows

        per_topic.append(
            {
                "run_id": run.run_id,
                "topic": run.label,
                "external_proxy_target_size": len(target_ids),
                "encoders": encoders,
            }
        )

    aggregate: Dict[str, Any] = {}
    encoder_names = sorted({name for topic in per_topic for name in topic["encoders"]})
    mode_names = ["graph_only", "preserve_base_1", "preserve_base_2", "preserve_base_3", "preserve_base_4", "base_only"]
    for enc in encoder_names:
        aggregate[enc] = {}
        for mode in mode_names:
            rows = [topic["encoders"][enc][mode] for topic in per_topic if enc in topic["encoders"] and mode in topic["encoders"][enc]]
            aggregate[enc][mode] = {
                "topic_count": len(rows),
                "mean_recall_top5": _mean(r["external_proxy_recall_top5"] for r in rows),
                "mean_precision_top5": _mean(r["external_proxy_precision_top5"] for r in rows),
                "mean_relation_density_top5": _mean(r["relation_density_top5"] for r in rows),
                "mean_unique_papers_top5": _mean(r["unique_papers_top5"] for r in rows),
            }

    # Pick a compact recommendation per encoder: highest density among modes
    # whose recall is at least 95% of the base-only recall.
    recommendations: Dict[str, Any] = {}
    for enc, modes in aggregate.items():
        base_recall = modes["base_only"]["mean_recall_top5"]
        candidates = [
            (mode, row)
            for mode, row in modes.items()
            if row["mean_recall_top5"] >= 0.95 * base_recall
        ]
        if candidates:
            mode, row = max(candidates, key=lambda x: (x[1]["mean_relation_density_top5"], x[1]["mean_recall_top5"]))
            recommendations[enc] = {"mode": mode, **row, "base_recall": base_recall}

    return {
        "experiment_type": "graph_safe_retrieval_fusion_sweep",
        "scope_note": (
            "Seven-run retrieval-stage sweep that constrains graph expansion to preserve the top base-ranker anchors "
            "before filling the remaining section budget from graph-neighbor candidates. This tests whether graph structure "
            "can add relation density without the external-proxy recall loss observed under unconstrained graph expansion."
        ),
        "top_k_per_section": 5,
        "runs_used": len(per_topic),
        "load_failures": load_failures,
        "per_topic": per_topic,
        "aggregate": aggregate,
        "recommendations": recommendations,
    }


def build_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Graph-Safe Retrieval Fusion Sweep",
        "",
        f"- Runs used: {payload['runs_used']}",
        f"- Dense load failures: {len(payload['load_failures'])}",
        "",
    ]
    for enc, modes in sorted(payload["aggregate"].items()):
        rec = payload["recommendations"].get(enc, {})
        lines.append(f"## {enc}")
        if rec:
            lines.append(
                f"- Recommended high-density mode under >=95% base recall: `{rec['mode']}` "
                f"(R@5={rec['mean_recall_top5']:.3f}, density={rec['mean_relation_density_top5']:.3f}; "
                f"base R@5={rec['base_recall']:.3f})"
            )
        lines.extend(
            [
                "",
                "| Mode | Recall@5 | Precision@5 | Relation density | Unique papers |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for mode, row in modes.items():
            lines.append(
                f"| {mode} | {row['mean_recall_top5']:.3f} | {row['mean_precision_top5']:.3f} | "
                f"{row['mean_relation_density_top5']:.3f} | {row['mean_unique_papers_top5']:.1f} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_eval()
    (OUTPUT_DIR / "graph_safe_retrieval_fusion_sweep.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "graph_safe_retrieval_fusion_sweep.md").write_text(
        build_markdown(payload),
        encoding="utf-8",
    )
    print(f"Wrote outputs to {OUTPUT_DIR}")
    print((OUTPUT_DIR / "graph_safe_retrieval_fusion_sweep.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
