from experiments import semantic_edge_stratified_protocol_audit as audit


def test_build_audit_structure():
    payload = audit.build_audit()

    assert payload["experiment_type"] == "semantic_edge_stratified_protocol_audit"
    assert payload["sample_count"] == 72
    assert payload["strata_per_relation"] == 3
    assert payload["samples_per_stratum"] == 8
    assert set(payload["confidence_buckets"]) == {"low", "mid", "high"}
    assert set(payload["by_relation"].keys()) == {"extends", "improves", "applies"}

    overall = payload["overall"]
    assert overall["total"] == payload["sample_count"]
    assert overall["supported"] + overall["partial"] + overall["unsupported"] == payload["sample_count"]
    assert 0.0 <= overall["supported_or_partial_rate"] <= 1.0

    for rel_type, row in payload["by_relation"].items():
        assert row["total"] == 24
        assert row["supported"] + row["partial"] + row["unsupported"] == 24
        assert row["matched_control_win_rate"] >= 0.0
        assert rel_type in {"extends", "improves", "applies"}

    for bucket, row in payload["by_confidence_bucket"].items():
        assert bucket in {"low", "mid", "high"}
        assert row["total"] == 24
        assert row["supported"] + row["partial"] + row["unsupported"] == 24

    assert payload["failure_mode_counts"]
    assert payload["samples"][0]["relation_type"] in {"extends", "improves", "applies"}
    assert payload["samples"][0]["confidence_bucket"] in {"low", "mid", "high"}
    assert payload["samples"][0]["protocol_label"] in {"supported", "partial", "unsupported"}
    assert "matched_control_delta" in payload["samples"][0]
    assert "source_title" in payload["samples"][0]
    assert "target_title" in payload["samples"][0]

