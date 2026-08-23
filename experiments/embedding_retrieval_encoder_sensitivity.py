from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit
from experiments import review_response_audit as review

OUTPUT_DIR = ROOT / "outputs" / "embedding_retrieval_encoder_sensitivity_20260526"


def _paper_text(paper: Dict[str, Any]) -> str:
    return " ".join(
        str(paper.get(k, "") or "")
        for k in ("title", "abstract", "category", "subcategory")
    )


def _section_text(title: str, desc: str) -> str:
    return f"{title}. {desc or ''}".strip()


def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _evaluate_ranker(
    run: audit.RunBundle,
    ranker,
    pairs: set[tuple[str, str]],
    target_ids: set[str],
    top_k: int = 5,
) -> Dict[str, Any]:
    union_ids: List[str] = []
    for section in run.outline.get("sections", []):
        title = section.get("title", "")
        if title in audit.SECTION_EXCLUDE_TITLES:
            continue
        ranked = ranker(title, section.get("description", ""))
        union_ids.extend([pid for pid, _ in ranked[:top_k]])
    unique_ids = list(dict.fromkeys(union_ids))
    hits = set(unique_ids) & target_ids

    pair_total = 0
    linked = 0
    for i in range(len(unique_ids)):
        for j in range(i + 1, len(unique_ids)):
            pair_total += 1
            if tuple(sorted((unique_ids[i], unique_ids[j]))) in pairs:
                linked += 1

    return {
        "unique_papers_top5": len(unique_ids),
        "hit_count_top5": len(hits),
        "external_proxy_recall_top5": len(hits) / len(target_ids) if target_ids else 0.0,
        "external_proxy_precision_top5": len(hits) / len(unique_ids) if unique_ids else 0.0,
        "relation_density_top5": linked / pair_total if pair_total else 0.0,
    }


class BaseRanker:
    def __init__(self, name: str, papers: List[Dict[str, Any]]) -> None:
        self.name = name
        self.papers = papers
        self.paper_ids = [audit.sanitize_key(p["id"]) for p in papers]

    def rank(self, title: str, desc: str) -> List[Tuple[str, float]]:
        raise NotImplementedError


class LexicalRanker(BaseRanker):
    def __init__(self, papers: List[Dict[str, Any]]) -> None:
        super().__init__("lexical_existing", papers)
        self.idf = audit.build_idf(papers)

    def rank(self, title: str, desc: str) -> List[Tuple[str, float]]:
        return audit.lexical_scores(self.papers, self.idf, title, desc)


class TfidfRanker(BaseRanker):
    def __init__(self, name: str, papers: List[Dict[str, Any]], vectorizer: TfidfVectorizer) -> None:
        super().__init__(name, papers)
        self.vectorizer = vectorizer
        self.matrix = vectorizer.fit_transform([_paper_text(p) for p in papers])

    def rank(self, title: str, desc: str) -> List[Tuple[str, float]]:
        q = self.vectorizer.transform([_section_text(title, desc)])
        sims = cosine_similarity(q, self.matrix)[0]
        rows = list(zip(self.paper_ids, (float(x) for x in sims)))
        rows.sort(key=lambda x: x[1], reverse=True)
        return rows


class DenseRanker(BaseRanker):
    def __init__(self, name: str, papers: List[Dict[str, Any]], model_name: str) -> None:
        super().__init__(name, papers)
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        # local_files_only avoids unplanned downloads; skipped encoders are logged.
        self.model = SentenceTransformer(model_name, local_files_only=True)
        emb = self.model.encode(
            [_paper_text(p) for p in papers],
            batch_size=32,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        self.emb = np.asarray(emb, dtype=np.float32)

    def rank(self, title: str, desc: str) -> List[Tuple[str, float]]:
        q = self.model.encode(
            [_section_text(title, desc)],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        sims = np.dot(self.emb, np.asarray(q[0], dtype=np.float32))
        rows = list(zip(self.paper_ids, (float(x) for x in sims)))
        rows.sort(key=lambda x: x[1], reverse=True)
        return rows


def _graph_rank_from_base(
    base_ranker: BaseRanker,
    paper_map: Dict[str, Dict[str, Any]],
    centrality: Dict[str, float],
    adjacency: Dict[str, List[Tuple[str, float, str]]],
    max_hops: int = 1,
    overlap_weight: float = 0.8,
    seed_centrality_weight: float = 1.0,
    expansion_centrality_weight: float = 0.5,
):
    def graph_rank(section_title: str, section_desc: str) -> List[Tuple[str, float]]:
        base = base_ranker.rank(section_title, section_desc)
        qtokens = set(audit.tokenize(f"{section_title} {section_desc}"))
        scores: Dict[str, float] = {}
        for pid, base_score in base:
            paper = paper_map[pid]
            community_tokens = set(audit.tokenize(f"{paper.get('category', '')} {paper.get('subcategory', '')}"))
            scores[pid] = (
                base_score
                + overlap_weight * len(qtokens & community_tokens)
                + seed_centrality_weight * centrality.get(pid, 0.0)
            )

        frontier: List[Tuple[str, float, int]] = [(pid, score, 0) for pid, score in base[:5]]
        best_depth = {pid: 0 for pid, _ in base[:5]}
        while frontier:
            node_id, seed_score, depth = frontier.pop(0)
            if depth >= max_hops:
                continue
            for nb_id, conf, rel_type in adjacency.get(node_id, []):
                hop = depth + 1
                scores[nb_id] = scores.get(nb_id, 0.0) + (0.5 ** (hop - 1)) * (
                    0.25 * seed_score
                    + audit.relation_bonus(rel_type) * conf
                    + expansion_centrality_weight * centrality.get(nb_id, 0.0)
                )
                if best_depth.get(nb_id, 999) > hop:
                    best_depth[nb_id] = hop
                    frontier.append((nb_id, seed_score, hop))

        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

    return graph_rank


def _make_rankers(papers: List[Dict[str, Any]], dense_models: Sequence[str]) -> Tuple[List[BaseRanker], List[Dict[str, Any]]]:
    rankers: List[BaseRanker] = [
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
    failures: List[Dict[str, Any]] = []
    for model_name in dense_models:
        short = model_name.replace("/", "__")
        started = time.perf_counter()
        try:
            rankers.append(DenseRanker(f"dense_{short}", papers, model_name))
        except Exception as exc:  # noqa: BLE001 - intentionally records local-model failures
            failures.append(
                {
                    "encoder": f"dense_{short}",
                    "model_name": model_name,
                    "error": repr(exc),
                    "load_seconds": time.perf_counter() - started,
                }
            )
    return rankers, failures


def build_eval(dense_models: Sequence[str]) -> Dict[str, Any]:
    per_topic: List[Dict[str, Any]] = []
    load_failures: List[Dict[str, Any]] = []

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
        rankers, failures = _make_rankers(papers, dense_models)
        for failure in failures:
            load_failures.append({"run_id": run.run_id, "topic": run.label, **failure})

        enc_rows: Dict[str, Any] = {}
        for ranker in rankers:
            started = time.perf_counter()
            flat = _evaluate_ranker(run, ranker.rank, pairs, target_ids)
            flat_seconds = time.perf_counter() - started
            graph_rank = _graph_rank_from_base(ranker, paper_map, centrality, adjacency, max_hops=1)
            started = time.perf_counter()
            graph = _evaluate_ranker(run, graph_rank, pairs, target_ids)
            graph_seconds = time.perf_counter() - started
            enc_rows[ranker.name] = {
                "flat": flat,
                "graph": graph,
                "delta_graph_minus_flat": {
                    "recall_top5": graph["external_proxy_recall_top5"] - flat["external_proxy_recall_top5"],
                    "precision_top5": graph["external_proxy_precision_top5"] - flat["external_proxy_precision_top5"],
                    "relation_density_top5": graph["relation_density_top5"] - flat["relation_density_top5"],
                },
                "timing_seconds": {
                    "flat_eval": flat_seconds,
                    "graph_eval": graph_seconds,
                },
            }

        per_topic.append(
            {
                "run_id": run.run_id,
                "topic": run.label,
                "external_proxy_target_size": len(target_ids),
                "source_survey_count": target_info["source_survey_count"],
                "encoders": enc_rows,
            }
        )

    encoder_names = sorted({name for row in per_topic for name in row["encoders"]})
    aggregate: Dict[str, Any] = {}
    for enc in encoder_names:
        rows = [row["encoders"][enc] for row in per_topic if enc in row["encoders"]]
        flat_recalls = [r["flat"]["external_proxy_recall_top5"] for r in rows]
        graph_recalls = [r["graph"]["external_proxy_recall_top5"] for r in rows]
        flat_precisions = [r["flat"]["external_proxy_precision_top5"] for r in rows]
        graph_precisions = [r["graph"]["external_proxy_precision_top5"] for r in rows]
        flat_density = [r["flat"]["relation_density_top5"] for r in rows]
        graph_density = [r["graph"]["relation_density_top5"] for r in rows]
        aggregate[enc] = {
            "topic_count": len(rows),
            "flat_mean_recall_top5": _mean(flat_recalls),
            "graph_mean_recall_top5": _mean(graph_recalls),
            "flat_mean_precision_top5": _mean(flat_precisions),
            "graph_mean_precision_top5": _mean(graph_precisions),
            "flat_mean_relation_density_top5": _mean(flat_density),
            "graph_mean_relation_density_top5": _mean(graph_density),
            "mean_delta_recall_top5": _mean(g - f for g, f in zip(graph_recalls, flat_recalls)),
            "mean_delta_precision_top5": _mean(g - f for g, f in zip(graph_precisions, flat_precisions)),
            "mean_delta_relation_density_top5": _mean(g - f for g, f in zip(graph_density, flat_density)),
            "paired_graph_vs_flat_recall": audit.exact_paired_sign_flip_test(
                g - f for g, f in zip(graph_recalls, flat_recalls)
            ),
        }

    return {
        "experiment_type": "embedding_retrieval_encoder_sensitivity",
        "scope_note": (
            "Seven-run retrieval-stage sensitivity replay against survey-reference external proxy targets. "
            "It varies the section-to-paper base encoder/ranker, then applies the same one-hop graph expansion. "
            "Dense sentence-transformer models are loaded from local cache only; missing models are recorded as failures."
        ),
        "top_k_per_section": 5,
        "runs_used": len(per_topic),
        "dense_models_requested": list(dense_models),
        "load_failures": load_failures,
        "per_topic": per_topic,
        "aggregate": aggregate,
    }


def build_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Embedding / Retrieval Encoder Sensitivity",
        "",
        f"- Runs used: {payload['runs_used']}",
        f"- Dense models requested: {', '.join(payload['dense_models_requested']) if payload['dense_models_requested'] else 'none'}",
        f"- Dense load failures: {len(payload['load_failures'])}",
        "",
        "| Encoder | Topics | Flat R@5 | Graph R@5 | ΔR@5 | Flat P@5 | Graph P@5 | Flat dens. | Graph dens. |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for enc, row in sorted(payload["aggregate"].items()):
        lines.append(
            f"| {enc} | {row['topic_count']} | "
            f"{row['flat_mean_recall_top5']:.3f} | {row['graph_mean_recall_top5']:.3f} | {row['mean_delta_recall_top5']:.3f} | "
            f"{row['flat_mean_precision_top5']:.3f} | {row['graph_mean_precision_top5']:.3f} | "
            f"{row['flat_mean_relation_density_top5']:.3f} | {row['graph_mean_relation_density_top5']:.3f} |"
        )
    if payload["load_failures"]:
        lines.extend(["", "## Load failures"])
        for row in payload["load_failures"][:20]:
            lines.append(f"- {row['topic']} / {row['encoder']}: `{row['error']}`")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay retrieval sensitivity over base encoders/rankers.")
    parser.add_argument(
        "--dense-model",
        action="append",
        default=[
            "sentence-transformers/all-MiniLM-L6-v2",
            "BAAI/bge-small-en-v1.5",
        ],
        help="SentenceTransformer model to load from local cache only; repeatable.",
    )
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_eval(args.dense_model)
    (out_dir / "embedding_retrieval_encoder_sensitivity.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "embedding_retrieval_encoder_sensitivity.md").write_text(
        build_markdown(payload),
        encoding="utf-8",
    )
    print(f"Wrote outputs to {out_dir}")
    print((out_dir / "embedding_retrieval_encoder_sensitivity.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
