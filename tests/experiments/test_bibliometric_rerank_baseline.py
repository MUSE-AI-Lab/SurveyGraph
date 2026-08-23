from experiments import bibliometric_rerank_baseline as bib


def test_bibliometric_rerank_baseline_builds_summary():
    payload = bib.build_eval()
    assert payload["experiment_type"] == "bibliometric_rerank_baseline"
    assert payload["run_count"] >= 4
    assert payload["top_k_per_section"] == 5
    assert "aggregate" in payload
    expected = {
        "flat",
        "openalex_quality_only",
        "bibliometric_rerank_top20",
        "flat_plus_quality",
        "lexical_biblio_rrf",
    }
    assert expected.issubset(payload["aggregate"])
    for name in expected:
        row = payload["aggregate"][name]
        assert row["topic_count"] == payload["run_count"]
        assert 0.0 <= row["mean_recall_top5"] <= 1.0
        assert 0.0 <= row["mean_precision_top5"] <= 1.0
        assert 0.0 <= row["mean_relation_density_top5"] <= 1.0
        assert row["mean_retrieval_seconds"] >= 0.0


def test_bibliometric_rerank_records_openalex_coverage_and_pairwise_tests():
    payload = bib.build_eval()
    assert payload["per_topic"]
    assert payload["pairwise"]
    for topic in payload["per_topic"]:
        assert 0.0 <= topic["openalex_title_match_rate"] <= 1.0
        assert 0.0 <= topic["openalex_nonzero_citation_rate"] <= 1.0
    assert "bibliometric_rerank_top20_vs_flat_recall" in payload["pairwise"]
