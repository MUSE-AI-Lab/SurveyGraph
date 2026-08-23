from experiments import citation_semantic_support_probe as probe


def test_citation_semantic_support_probe_builds_summary():
    payload = probe.build_probe(max_samples=40)
    assert payload["experiment_type"] == "citation_semantic_support_probe"
    assert payload["sample_count"] == 40
    assert "overall" in payload
    assert 0.0 <= payload["overall"]["mean_max_semantic_similarity"] <= 1.0
    assert 0.0 <= payload["overall"]["semantic_supported_or_partial_rate"] <= 1.0
    assert payload["overall"]["lexical_anchored_or_partial_rate"] >= 0.0
    assert "negative_control" in payload
    assert 0.0 <= payload["negative_control"]["cited_beats_hard_negative_rate"] <= 1.0
    assert payload["encoder"]
    assert payload["samples"][0]["semantic_label"] in {"semantic_supported", "semantic_partial", "semantic_weak"}
    assert "hard_negative_max_similarity" in payload["samples"][0]
    assert "cited_minus_hard_negative_margin" in payload["samples"][0]


def test_citation_semantic_support_probe_reports_label_cross_tab():
    payload = probe.build_probe(max_samples=60)
    crosstab = payload["lexical_vs_semantic_crosstab"]
    assert crosstab
    assert any(label in crosstab for label in ["anchored", "partial_anchor", "weak_or_missing_anchor"])
    assert "by_lexical_label" in payload
    for row in payload["by_lexical_label"].values():
        assert "cited_beats_hard_negative_rate" in row
