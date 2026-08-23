from experiments import external_proxy_retrieval_replay as replay


def test_build_external_proxy_replay_summary_structure():
    payload = replay.build_external_proxy_retrieval_replay_summary()

    assert payload["experiment_type"] == "external_proxy_retrieval_replay"
    assert payload["topic_count"] == 2
    assert len(payload["topics"]) == 2
    assert payload["aggregate"]["flat_mean_external_proxy_recall_top5"] >= 0.0
    assert payload["aggregate"]["graph_mean_external_proxy_recall_top5"] >= 0.0
    assert "paired_graph_vs_flat_external_proxy_recall_top5" in payload["aggregate"]
    assert "paired_graph_vs_no_expansion_external_proxy_recall_top5" in payload["aggregate"]

    topic = payload["topics"][0]
    assert topic["topic"] in {"Document Visual Question Answering", "Text-to-SQL Agent"}
    assert topic["flat"]["sections_evaluated"] == 5
    assert topic["graph"]["sections_evaluated"] == 5
    assert topic["no_expansion"]["sections_evaluated"] == 5
    assert topic["flat"]["external_proxy_recall_top5"] >= 0.0
    assert topic["graph"]["external_proxy_recall_top5"] >= 0.0
    assert topic["graph"]["relation_density_top5"] >= 0.0
    assert topic["graph"]["unique_papers_top5"] >= 1
