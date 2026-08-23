from experiments import graphrag_lite_matched_baseline as lite


def test_graphrag_lite_baseline_builds_matched_summary():
    payload = lite.build_eval()
    assert payload["experiment_type"] == "graphrag_lite_matched_baseline"
    assert payload["run_count"] >= 4
    assert "aggregate" in payload
    expected = {"flat", "tfidf_knn_lite_graph", "structural_graph", "full_mekg", "safe_fusion_full"}
    assert expected.issubset(payload["aggregate"])
    for name in expected:
        row = payload["aggregate"][name]
        assert row["topic_count"] == payload["run_count"]
        assert 0.0 <= row["mean_recall_top5"] <= 1.0
        assert 0.0 <= row["mean_precision_top5"] <= 1.0
        assert 0.0 <= row["mean_relation_density_top5"] <= 1.0
    assert payload["aggregate"]["tfidf_knn_lite_graph"]["mean_active_relations"] > 0
    assert payload["aggregate"]["flat"]["mean_active_relations"] == 0


def test_graphrag_lite_baseline_records_pairwise_tests():
    payload = lite.build_eval()
    pairwise = payload["pairwise"]
    assert "full_mekg_vs_tfidf_knn_lite_graph_recall" in pairwise
    assert "safe_fusion_full_vs_flat_recall" in pairwise
    for result in pairwise.values():
        assert {"sample_size", "positive_pairs", "negative_pairs", "one_sided_p_greater"}.issubset(result)
