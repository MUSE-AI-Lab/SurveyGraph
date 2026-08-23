from experiments import matched_quality_graph_mini_benchmark as bench


def test_matched_quality_graph_mini_benchmark_builds_summary():
    payload = bench.build_benchmark()
    assert payload["experiment_type"] == "matched_quality_graph_mini_benchmark"
    assert payload["run_count"] >= 4
    assert payload["top_k_per_section"] == 5
    expected = {
        "flat",
        "bibliometric_rrf",
        "tfidf_graphrag_lite",
        "surveygraph_full_mekg",
        "safe_fusion_full_mekg",
        "safe_fusion_biblio_tfidf",
        "safe_fusion_biblio_mekg",
    }
    assert expected.issubset(payload["aggregate"])
    for name in expected:
        row = payload["aggregate"][name]
        assert row["topic_count"] == payload["run_count"]
        assert 0.0 <= row["mean_recall_top5"] <= 1.0
        assert 0.0 <= row["mean_precision_top5"] <= 1.0
        assert 0.0 <= row["mean_section_evidence_alignment"] <= 1.0
        assert 0.0 <= row["mean_duplicate_rate_top5"] <= 1.0
        assert row["mean_retrieval_seconds"] >= 0.0


def test_matched_quality_graph_mini_benchmark_has_pairwise_recall_and_alignment():
    payload = bench.build_benchmark()
    assert "bibliometric_rrf_vs_flat_recall" in payload["pairwise"]
    assert "safe_fusion_biblio_mekg_vs_flat_alignment" in payload["pairwise"]
    for result in payload["pairwise"].values():
        assert {"sample_size", "positive_pairs", "negative_pairs", "two_sided_p"}.issubset(result)
