from experiments import citation_evidence_contrast_probe as probe


def test_citation_evidence_contrast_probe_builds_summary():
    payload = probe.build_probe(max_samples=40)
    assert payload["experiment_type"] == "citation_evidence_contrast_probe"
    assert payload["sample_count"] > 0
    assert payload["sample_count"] <= 40
    assert payload["matched_evidence_count"] == payload["sample_count"]
    assert 0.0 <= payload["overall"]["cited_beats_hard_negative_rate"] <= 1.0
    assert -1.0 <= payload["overall"]["mean_cited_minus_negative_margin"] <= 1.0
    assert payload["overall"]["mean_cited_evidence_similarity"] >= 0.0
    first = payload["samples"][0]
    assert "cited_evidence_similarity" in first
    assert "hard_negative_evidence_similarity" in first
    assert "cited_minus_hard_negative_margin" in first


def test_citation_evidence_contrast_probe_groups_by_lexical_label():
    payload = probe.build_probe(max_samples=80)
    assert payload["by_lexical_label"]
    for row in payload["by_lexical_label"].values():
        assert "count" in row
        assert "cited_beats_hard_negative_rate" in row
        assert 0.0 <= row["cited_beats_hard_negative_rate"] <= 1.0
