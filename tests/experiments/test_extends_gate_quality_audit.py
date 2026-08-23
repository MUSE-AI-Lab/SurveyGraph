from experiments.extends_gate_quality_audit import summarize_extends


def test_role_pruning_improves_protocol_supported_or_partial_rate():
    rows = [
        {"relation_type": "extends", "protocol_label": "supported", "target_role_ok": True, "temporal_ok": True, "confidence": 0.9},
        {"relation_type": "extends", "protocol_label": "partial", "target_role_ok": True, "temporal_ok": True, "confidence": 0.7},
        {"relation_type": "extends", "protocol_label": "unsupported", "target_role_ok": False, "temporal_ok": True, "confidence": 0.9},
        {"relation_type": "improves", "protocol_label": "unsupported", "target_role_ok": True, "temporal_ok": True, "confidence": 0.9},
    ]

    summary = summarize_extends(rows, confidence_threshold=0.8)

    assert summary["raw"] == {"supported_or_partial": 2, "total": 3, "rate": 2 / 3}
    assert summary["role_compatible"] == {"supported_or_partial": 2, "total": 2, "rate": 1.0}
    assert summary["strict_combined"] == {"supported_or_partial": 1, "total": 1, "rate": 1.0}
