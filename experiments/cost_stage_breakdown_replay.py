from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit
from experiments import review_response_audit as review
from experiments.semantic_evidence_gate_retrieval_eval import _semantic_label_index, _build_filtered_adjacency

OUTPUT_DIR = ROOT / "outputs" / "cost_stage_breakdown_replay_20260526"


def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sum_generation_seconds(run: audit.RunBundle) -> Dict[str, Any]:
    path = run.base_dir / "metrics" / "time_monitor.json"
    if not path.exists():
        return {
            "generation_seconds": 0.0,
            "table_seconds": 0.0,
            "visual_seconds": 0.0,
            "compile_seconds": 0.0,
            "available": False,
        }
    data = _load_json(path)
    def dur(name: str) -> float:
        row = data.get(name, {})
        return float(row.get("duration", 0.0) or 0.0)
    return {
        "generation_seconds": dur("generate content with reflection") + dur("generate content"),
        "table_seconds": dur("generate tabel") + dur("generate table"),
        "visual_seconds": dur("generate dynamic visuals"),
        "compile_seconds": dur("compile latex"),
        "available": True,
    }


def _sum_tokens_and_cost(run: audit.RunBundle) -> Dict[str, Any]:
    path = run.base_dir / "metrics" / "token_monitor.json"
    if not path.exists():
        return {"input_tokens": 0, "output_tokens": 0, "logged_cost": 0.0, "available": False}
    data = _load_json(path)
    input_tokens = 0
    output_tokens = 0
    logged_cost = 0.0
    for stage in data.values():
        if not isinstance(stage, dict):
            continue
        for row in stage.values():
            if not isinstance(row, dict):
                continue
            input_tokens += int(row.get("input_tokens", 0) or 0)
            output_tokens += int(row.get("output_tokens", 0) or 0)
            logged_cost += float(row.get("total_cost", 0.0) or 0.0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "logged_cost": logged_cost,
        "available": True,
    }


def _profile_graph_construction(run: audit.RunBundle) -> Tuple[float, Dict[str, Any]]:
    started = time.perf_counter()
    paper_ids = {audit.sanitize_key(p["id"]) for p in run.mekg.get("papers", [])}
    graph = nx.DiGraph()
    graph.add_nodes_from(paper_ids)
    skipped = 0
    for rel in run.mekg.get("relations", []):
        src = audit.sanitize_key(rel.get("source", ""))
        tgt = audit.sanitize_key(rel.get("target", ""))
        if src in paper_ids and tgt in paper_ids:
            graph.add_edge(src, tgt, type=rel.get("type", ""), confidence=rel.get("confidence", 0.5))
        else:
            skipped += 1
    # Compute a centrality vector because retrieval uses it; include it in local graph preparation.
    pagerank = nx.pagerank(graph) if graph.number_of_nodes() else {}
    elapsed = time.perf_counter() - started
    return elapsed, {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "skipped_relations": skipped,
        "pagerank_nodes": len(pagerank),
    }


def _profile_evidence_gate(run: audit.RunBundle, labels: Dict[tuple[str, str, str, str], str]) -> Tuple[float, Dict[str, Any]]:
    context = audit.build_retrieval_context(run)
    started = time.perf_counter()
    adjacency, pairs, counts = _build_filtered_adjacency(
        run,
        context["paper_map"],
        labels,
        "supported_or_partial_gate",
    )
    elapsed = time.perf_counter() - started
    return elapsed, {
        **counts,
        "adjacency_nodes": len(adjacency),
        "undirected_pairs": len(pairs),
    }


def _profile_retrieval(run: audit.RunBundle) -> Tuple[float, Dict[str, Any]]:
    target_info = review.collect_survey_reference_targets(run)
    target_ids = {audit.sanitize_key(pid) for pid in target_info["external_target_ids"]}
    context = audit.build_retrieval_context(run)
    papers = context["papers"]
    paper_map = context["paper_map"]
    idf = context["idf"]
    centrality = context["centrality"]
    adjacency, pairs = audit.build_adjacency(run, paper_map)
    graph_rank = audit.make_graph_ranker(papers, paper_map, idf, centrality, adjacency, max_hops=1)

    started = time.perf_counter()
    union_ids: List[str] = []
    sections = 0
    for section in run.outline.get("sections", []):
        title = section.get("title", "")
        if title in audit.SECTION_EXCLUDE_TITLES:
            continue
        sections += 1
        ranked = graph_rank(title, section.get("description", ""))[0]
        union_ids.extend([pid for pid, _ in ranked[:5]])
    elapsed = time.perf_counter() - started

    unique_ids = list(dict.fromkeys(union_ids))
    hits = set(unique_ids) & target_ids
    pair_total = 0
    linked = 0
    for i in range(len(unique_ids)):
        for j in range(i + 1, len(unique_ids)):
            pair_total += 1
            if tuple(sorted((unique_ids[i], unique_ids[j]))) in pairs:
                linked += 1
    return elapsed, {
        "sections_evaluated": sections,
        "unique_papers_top5": len(unique_ids),
        "external_target_size": len(target_ids),
        "hit_count_top5": len(hits),
        "external_proxy_recall_top5": len(hits) / len(target_ids) if target_ids else 0.0,
        "relation_density_top5": linked / pair_total if pair_total else 0.0,
    }


def build_profile() -> Dict[str, Any]:
    labels = _semantic_label_index()
    per_run: List[Dict[str, Any]] = []
    for run in audit.load_archived_runs():
        graph_seconds, graph_meta = _profile_graph_construction(run)
        gate_seconds, gate_meta = _profile_evidence_gate(run, labels)
        retrieval_seconds, retrieval_meta = _profile_retrieval(run)
        gen = _sum_generation_seconds(run)
        tok = _sum_tokens_and_cost(run)
        paper_count = len(run.mekg.get("papers", []))
        relation_count = len(run.mekg.get("relations", []))
        local_replay_seconds = graph_seconds + gate_seconds + retrieval_seconds
        generation_seconds = gen["generation_seconds"]
        per_run.append(
            {
                "run_id": run.run_id,
                "topic": run.label,
                "paper_count": paper_count,
                "relation_count": relation_count,
                "graph_construction_replay_seconds": graph_seconds,
                "graph_meta": graph_meta,
                "semantic_evidence_gate_replay_seconds": gate_seconds,
                "semantic_evidence_gate_meta": gate_meta,
                "retrieval_replay_seconds": retrieval_seconds,
                "retrieval_meta": retrieval_meta,
                "archived_generation_seconds": generation_seconds,
                "archived_generation_minutes": generation_seconds / 60.0,
                "archived_table_seconds": gen["table_seconds"],
                "archived_visual_seconds": gen["visual_seconds"],
                "archived_compile_seconds": gen["compile_seconds"],
                "token_and_cost": tok,
                "local_replay_seconds": local_replay_seconds,
                "local_replay_seconds_per_100_papers": local_replay_seconds / paper_count * 100.0 if paper_count else 0.0,
                "archived_generation_seconds_per_100_papers": generation_seconds / paper_count * 100.0 if paper_count else 0.0,
            }
        )

    aggregate = {
        "run_count": len(per_run),
        "mean_paper_count": _mean(row["paper_count"] for row in per_run),
        "mean_relation_count": _mean(row["relation_count"] for row in per_run),
        "mean_graph_construction_replay_seconds": _mean(row["graph_construction_replay_seconds"] for row in per_run),
        "mean_semantic_evidence_gate_replay_seconds": _mean(row["semantic_evidence_gate_replay_seconds"] for row in per_run),
        "mean_retrieval_replay_seconds": _mean(row["retrieval_replay_seconds"] for row in per_run),
        "mean_local_replay_seconds": _mean(row["local_replay_seconds"] for row in per_run),
        "mean_local_replay_seconds_per_100_papers": _mean(row["local_replay_seconds_per_100_papers"] for row in per_run),
        "mean_archived_generation_minutes": _mean(row["archived_generation_minutes"] for row in per_run),
        "mean_archived_generation_seconds_per_100_papers": _mean(row["archived_generation_seconds_per_100_papers"] for row in per_run),
        "mean_logged_cost": _mean(row["token_and_cost"]["logged_cost"] for row in per_run),
        "mean_input_tokens": _mean(row["token_and_cost"]["input_tokens"] for row in per_run),
        "mean_output_tokens": _mean(row["token_and_cost"]["output_tokens"] for row in per_run),
    }
    local = aggregate["mean_local_replay_seconds"]
    aggregate["local_replay_share"] = {
        "graph_construction": aggregate["mean_graph_construction_replay_seconds"] / local if local else 0.0,
        "semantic_evidence_gate": aggregate["mean_semantic_evidence_gate_replay_seconds"] / local if local else 0.0,
        "retrieval": aggregate["mean_retrieval_replay_seconds"] / local if local else 0.0,
    }
    return {
        "experiment_type": "cost_stage_breakdown_replay",
        "scope_note": (
            "Local CPU replay of graph preparation, semantic evidence-gate filtering, and retrieval over eight archived runs, "
            "combined with archived generation/token monitors. This does not re-run long-form generation and therefore isolates "
            "local diagnostic overhead from the saved generation-stage timers."
        ),
        "per_run": per_run,
        "aggregate": aggregate,
    }


def build_markdown(payload: Dict[str, Any]) -> str:
    agg = payload["aggregate"]
    lines = [
        "# Cost / Stage Breakdown Replay",
        "",
        f"- Runs: {agg['run_count']}",
        f"- Mean papers / relations: {agg['mean_paper_count']:.1f} / {agg['mean_relation_count']:.1f}",
        f"- Mean local replay seconds: {agg['mean_local_replay_seconds']:.3f}",
        f"- Mean archived generation minutes: {agg['mean_archived_generation_minutes']:.2f}",
        "",
        "| Stage | Mean seconds | Share of local replay |",
        "|---|---:|---:|",
        f"| Graph construction + PageRank replay | {agg['mean_graph_construction_replay_seconds']:.3f} | {agg['local_replay_share']['graph_construction']:.3f} |",
        f"| Semantic evidence gate replay | {agg['mean_semantic_evidence_gate_replay_seconds']:.3f} | {agg['local_replay_share']['semantic_evidence_gate']:.3f} |",
        f"| Graph retrieval replay | {agg['mean_retrieval_replay_seconds']:.3f} | {agg['local_replay_share']['retrieval']:.3f} |",
        "",
        "| Topic | Papers | Relations | Graph s | Gate s | Retrieval s | Archived generation min |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["per_run"]:
        lines.append(
            f"| {row['topic']} | {row['paper_count']} | {row['relation_count']} | "
            f"{row['graph_construction_replay_seconds']:.3f} | "
            f"{row['semantic_evidence_gate_replay_seconds']:.3f} | "
            f"{row['retrieval_replay_seconds']:.3f} | "
            f"{row['archived_generation_minutes']:.2f} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_profile()
    (OUTPUT_DIR / "cost_stage_breakdown_replay.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "cost_stage_breakdown_replay.md").write_text(
        build_markdown(payload),
        encoding="utf-8",
    )
    print(f"Wrote outputs to {OUTPUT_DIR}")
    print((OUTPUT_DIR / "cost_stage_breakdown_replay.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
