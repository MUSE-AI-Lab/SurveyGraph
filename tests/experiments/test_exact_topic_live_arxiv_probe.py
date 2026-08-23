from experiments import exact_topic_live_arxiv_probe as probe


def test_build_row_uses_surveybench_overlap_rule():
    benchmark_refs = {
        "2305.11171": {},
        "2307.03109": {},
        "2402.14865": {},
    }
    row = probe.build_row(
        topic="Evaluation of Large Language Models",
        raw_count=4,
        source_ref_ids=["2305.11171", "2307.03109", "2402.14865", "2501.00001"],
        benchmark_refs=benchmark_refs,
    )

    assert row["topic"] == "Evaluation of Large Language Models"
    assert row["raw_count"] == 4
    assert row["valid_target_count"] == 2
    assert row["matched_count"] == 2
    assert row["coverage"] == 1.0


def test_summarize_rows_computes_aggregate_fields():
    rows = [
        {"topic": "A", "raw_count": 30, "valid_target_count": 10, "matched_count": 4, "coverage": 0.4},
        {"topic": "B", "raw_count": 0, "valid_target_count": 0, "matched_count": 0, "coverage": 0.0},
        {"topic": "C", "raw_count": 15, "valid_target_count": 5, "matched_count": 1, "coverage": 0.2},
    ]

    agg = probe.summarize_rows(rows)

    assert agg["topic_count"] == 3
    assert agg["topics_with_nonzero_results"] == 2
    assert agg["mean_coverage"] == 0.2
    assert agg["median_coverage"] == 0.2
    assert agg["mean_valid_target_count"] == 5
    assert agg["mean_matched_count"] == (4 + 0 + 1) / 3
