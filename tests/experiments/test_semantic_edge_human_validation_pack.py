from experiments import semantic_edge_human_validation_pack as pack


def test_semantic_edge_human_validation_pack_builds_unfilled_annotation_package():
    payload = pack.build_pack()
    assert payload["experiment_type"] == "semantic_edge_human_validation_pack"
    assert payload["human_labels_completed"] is False
    assert payload["summary"]["sample_count"] > 0
    assert payload["summary"]["sample_count"] <= 108
    assert set(payload["summary"]["by_relation"]) == {"extends", "improves", "applies"}
    first = payload["sample"][0]
    assert "sample_id" in first
    assert "protocol_label" in first
    assert "source_abstract" in first
    assert "target_abstract" in first


def test_semantic_edge_human_validation_annotation_rows_keep_human_fields_blank():
    payload = pack.build_pack()
    rows = pack._annotation_csv_rows(payload["sample"])
    assert rows
    for field in [
        "human_relation_correct",
        "human_direction_correct",
        "human_evidence_support",
        "human_keep_edge",
        "annotator_id",
    ]:
        assert rows[0][field] == ""
