from experiments import graphrag_lite_sensitivity_sweep as sweep


def test_graphrag_lite_sweep_reports_multiple_settings():
    payload = sweep.build_sweep(neighbor_values=(3, 5), min_similarity_values=(0.05, 0.10))
    assert payload["experiment_type"] == "graphrag_lite_sensitivity_sweep"
    assert payload["run_count"] >= 4
    assert payload["setting_count"] == 4
    assert len(payload["settings"]) == 4
    assert payload["flat_baseline"]["mean_recall_top5"] >= 0.0
    for row in payload["settings"]:
        assert row["topic_count"] == payload["run_count"]
        assert row["top_neighbors"] in {3, 5}
        assert row["min_similarity"] in {0.05, 0.10}
        assert 0.0 <= row["mean_recall_top5"] <= 1.0
        assert 0.0 <= row["mean_precision_top5"] <= 1.0
        assert 0.0 <= row["mean_mekg_density_top5"] <= 1.0
        assert row["mean_active_relations"] > 0
    assert payload["best_by_recall"]["mean_recall_top5"] >= 0.0
    assert payload["recommended_balanced"]["mean_recall_top5"] >= 0.0
