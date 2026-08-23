from types import SimpleNamespace

from experiments import surveybench_query_expansion_probe as probe


def paper(arxiv_id, title="T"):
    return SimpleNamespace(arxiv_id=arxiv_id, paper_id=f"arXiv:{arxiv_id}", title=title)


def test_merge_variant_results_deduplicates_and_respects_budget():
    variant_results = {
        "main": [paper("2401.00001", "A"), paper("2401.00002", "B")],
        "alt": [paper("2401.00002", "B again"), paper("2401.00003", "C")],
    }

    selected = probe.merge_variant_results(
        variant_results,
        variant_weights={"main": 1.0, "alt": 0.5},
        target_count=2,
    )

    assert [item["arxiv_id"] for item in selected] == ["2401.00001", "2401.00002"]
    assert selected[0]["query_hits"] == ["main"]
    assert selected[1]["query_hits"] == ["main", "alt"]


def test_build_comparison_row_uses_shared_overlap_rule():
    benchmark_refs = {
        "2305.11171": {},
        "2307.03109": {},
        "2402.14865": {},
    }
    expanded_ids = ["2305.11171", "2307.03109", "2501.00001"]
    exact_ids = ["2305.11171", "2307.03109", "2501.00001"]

    row = probe.build_comparison_row(
        topic="Evaluation of Large Language Models",
        benchmark_refs=benchmark_refs,
        expanded_refs=expanded_ids,
        exact_refs=exact_ids,
        expanded_raw_count=5,
        exact_raw_count=4,
    )

    assert row["expanded"]["valid_target_count"] == 2
    assert row["expanded"]["matched_count"] == 2
    assert row["expanded"]["coverage"] == 1.0
    assert row["exact"]["valid_target_count"] == 2
    assert row["exact"]["matched_count"] == 2
    assert row["coverage_delta"] == 0.0


def test_summarize_rows_reports_matched_budget_delta():
    rows = [
        {"topic": "A", "coverage_delta": 0.2, "expanded": {"coverage": 0.5, "matched_count": 2}, "exact": {"coverage": 0.3, "matched_count": 1}},
        {"topic": "B", "coverage_delta": -0.1, "expanded": {"coverage": 0.2, "matched_count": 1}, "exact": {"coverage": 0.3, "matched_count": 2}},
    ]

    agg = probe.summarize_rows(rows)

    assert agg["topic_count"] == 2
    assert agg["topics_expanded_better"] == 1
    assert agg["topics_exact_better"] == 1
    assert agg["mean_coverage_delta"] == 0.05
    assert agg["mean_expanded_coverage"] == 0.35
    assert agg["mean_exact_coverage"] == 0.3
