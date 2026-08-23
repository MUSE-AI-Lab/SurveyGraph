from experiments import matched_simpler_graph_baseline_eval as baseline


EXPECTED_TOPICS = {
    "Document Visual Question Answering",
    "Text-to-SQL Agent",
    "Large Language Model Function Calling",
    "Memory in the Age of AI Agents",
}


def test_build_summary_structure():
    payload = baseline.build_summary()

    assert payload["experiment_type"] == "matched_simpler_graph_baseline_eval"
    assert payload["topic_count"] == 4
    assert len(payload["topics"]) == 4
    assert set(payload["matched_topics"]) == EXPECTED_TOPICS

    agg = payload["aggregate"]
    assert agg["flat_mean_external_proxy_recall_top5"] >= 0.0
    assert agg["simple_graph_mean_external_proxy_recall_top5"] >= 0.0
    assert agg["full_graph_mean_external_proxy_recall_top5"] >= 0.0
    assert agg["full_graph_mean_external_proxy_recall_top5"] >= agg["simple_graph_mean_external_proxy_recall_top5"]
    assert agg["simple_graph_mean_external_proxy_recall_top5"] >= agg["flat_mean_external_proxy_recall_top5"]
    assert agg["simple_graph_mean_relation_density_top5"] >= agg["flat_mean_relation_density_top5"]
    assert agg["full_graph_mean_relation_density_top5"] >= agg["flat_mean_relation_density_top5"]
    assert "paired_full_vs_simple_external_proxy_recall_top5" in agg
    assert "paired_full_vs_flat_external_proxy_recall_top5" in agg
    assert "paired_simple_vs_flat_external_proxy_recall_top5" in agg

    topic = payload["topics"][0]
    assert topic["topic"] in EXPECTED_TOPICS
    assert topic["external_proxy_target_size"] >= 3
    assert topic["flat"]["sections_evaluated"] >= 4
    assert topic["simple_graph"]["sections_evaluated"] >= 4
    assert topic["full_graph"]["sections_evaluated"] >= 4
    assert topic["flat"]["external_proxy_precision_top5"] >= 0.0
    assert topic["simple_graph"]["relation_density_top5"] >= 0.0
    assert topic["full_graph"]["unique_papers_top5"] >= 1
    assert "delta_vs_flat" in topic
    assert "delta_vs_simple_graph" in topic

