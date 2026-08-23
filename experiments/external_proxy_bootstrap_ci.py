"""
Bootstrap confidence intervals + paired test for the external-proxy retrieval replay.

Reviewers (and our own read) flagged that the matched external-proxy replay reports
point means over a handful of topics with no interval. This script re-runs the same
offline diagnostic over all archived runs with a usable survey-reference proxy, then
adds (i) topic-level bootstrap 95% CIs for flat / structural / full-typed mean recall,
precision, and relation density, and (ii) the exact paired sign-flip test for the
full-vs-flat recall delta. It reuses the existing offline rankers, makes no API calls,
and does not modify the original replay script.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import offline_real_revision_audit as audit
from experiments import review_response_audit as review
from experiments import external_proxy_retrieval_replay as replay

N_BOOT = 10000
SEED = 20260714  # fixed seed: replays must be reproducible, no wall-clock randomness


def _lcg(seed):
    """Deterministic linear congruential generator (numpy-free, reproducible)."""
    state = seed & 0xFFFFFFFF
    while True:
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        yield state / 0x7FFFFFFF


def bootstrap_ci(values, rng, n_boot=N_BOOT):
    """Percentile bootstrap 95% CI for the mean of a per-topic value list."""
    n = len(values)
    if n == 0:
        return (0.0, 0.0, 0.0)
    means = []
    for _ in range(n_boot):
        resample = [values[int(next(rng) * n) % n] for _ in range(n)]
        means.append(sum(resample) / n)
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[int(0.975 * n_boot)]
    return (sum(values) / n, lo, hi)


def per_topic_metrics():
    """Compute flat / graph / no-expansion metrics for every archived run with a proxy."""
    rows = []
    for run in audit.load_archived_runs():
        target_info = review.collect_survey_reference_targets(run)
        target_ids = {audit.sanitize_key(pid) for pid in target_info["external_target_ids"]}
        if len(target_ids) < 3:  # same >=3 usable-target rule as the appendix proxy
            continue
        context = audit.build_retrieval_context(run)
        papers = context["papers"]
        paper_map = context["paper_map"]
        idf = context["idf"]
        centrality = context["centrality"]
        adjacency, undirected_pairs = audit.build_adjacency(run, paper_map)

        flat_rank = audit.make_flat_ranker(papers, idf)
        graph_rank = audit.make_graph_ranker(papers, paper_map, idf, centrality, adjacency, max_hops=1)
        noexp_rank = audit.make_graph_ranker(papers, paper_map, idf, centrality, adjacency, max_hops=0)

        flat = replay._evaluate_ranker(run, flat_rank, context, undirected_pairs, target_ids)
        graph = replay._evaluate_ranker(
            run, lambda t, d: graph_rank(t, d)[0], context, undirected_pairs, target_ids
        )
        noexp = replay._evaluate_ranker(
            run, lambda t, d: noexp_rank(t, d)[0], context, undirected_pairs, target_ids
        )
        rows.append({"topic": run.label, "flat": flat, "graph": graph, "no_expansion": noexp})
    return rows


def main():
    rows = per_topic_metrics()
    rng = _lcg(SEED)

    def col(variant, metric):
        return [r[variant][metric] for r in rows]

    metrics = [
        ("external_proxy_recall_top5", "Mean recall@5"),
        ("external_proxy_precision_top5", "Mean precision@5"),
        ("relation_density_top5", "Mean relation density"),
    ]
    variants = [("flat", "Flat"), ("no_expansion", "Structural (0-hop)"), ("graph", "Full typed (1-hop)")]

    print(f"Topics with usable survey-reference proxy: {len(rows)}")
    for r in rows:
        print(f"  - {r['topic']}: flat R@5={r['flat']['external_proxy_recall_top5']:.3f} "
              f"full R@5={r['graph']['external_proxy_recall_top5']:.3f}")
    print()

    out = {"n_topics": len(rows), "n_bootstrap": N_BOOT, "seed": SEED, "topics": rows, "ci": {}}
    for mkey, mlabel in metrics:
        print(f"=== {mlabel} (bootstrap 95% CI over {len(rows)} topics) ===")
        for vkey, vlabel in variants:
            vals = col(vkey, mkey)
            # fresh rng stream per cell for reproducibility independent of call order
            point, lo, hi = bootstrap_ci(vals, _lcg(SEED + hash(mkey + vkey) % 9973))
            out["ci"][f"{vkey}:{mkey}"] = {"point": point, "lo": lo, "hi": hi}
            print(f"  {vlabel:22s} {point:.3f}  [{lo:.3f}, {hi:.3f}]")
        print()

    # Paired full-vs-flat recall
    deltas = [g - f for g, f in zip(col("graph", "external_proxy_recall_top5"),
                                    col("flat", "external_proxy_recall_top5"))]
    test = audit.exact_paired_sign_flip_test(deltas)
    out["paired_full_vs_flat_recall"] = test
    print("=== Paired full-typed vs flat recall@5 (exact sign-flip test) ===")
    print(f"  mean delta = {sum(deltas)/len(deltas):+.3f}")
    print(f"  {json.dumps(test)}")

    outdir = ROOT / "outputs" / "external_proxy_bootstrap_ci_20260714"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "bootstrap_ci_summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSummary written to: {outdir / 'bootstrap_ci_summary.json'}")


if __name__ == "__main__":
    main()
