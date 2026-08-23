from experiments import extended_external_proxy_gate_eval as gate
from experiments import expanded_claim_citation_audit as claim
from experiments import retrieval_quality_cost_tradeoff as qcost
from experiments import section_reference_alignment_audit as align


def test_extended_gate_eval_covers_seven_runs_and_core_modes():
    payload = gate.build_eval()
    assert payload["experiment_type"] == "extended_external_proxy_gate_eval"
    assert payload["run_count"] == 7
    assert {"flat", "structural_only", "semantic_only", "full", "supported_or_partial_gate", "supported_only_gate"}.issubset(payload["modes"])
    agg = payload["aggregate"]
    assert agg["supported_or_partial_gate"]["mean_recall_top5"] >= 0.0
    assert agg["supported_or_partial_gate"]["mean_semantic_dropped"] > 0
    assert agg["semantic_only"]["mean_active_relations"] > 0
    assert "paired_supported_or_partial_vs_full_recall" in payload


def test_expanded_claim_citation_audit_covers_archived_runs():
    payload = claim.build_audit(sample_per_run=12)
    assert payload["experiment_type"] == "expanded_claim_citation_audit"
    assert payload["run_count"] == 8
    assert payload["overall"]["sample_count"] >= 80
    assert 0.0 <= payload["overall"]["anchored_or_partial_rate"] <= 1.0
    assert payload["overall"]["single_citation_count"] + payload["overall"]["multi_citation_count"] == payload["overall"]["sample_count"]
    first = payload["samples"][0]
    assert first["citation_keys"]
    assert first["label"] in {"anchored", "partial_anchor", "weak_or_missing_anchor"}


def test_quality_cost_tradeoff_has_retrieval_variants():
    payload = qcost.build_tradeoff()
    assert payload["experiment_type"] == "retrieval_quality_cost_tradeoff"
    assert payload["run_count"] == 7
    variants = payload["aggregate"]
    assert {"flat", "structural_only", "full", "supported_or_partial_gate"}.issubset(variants)
    assert variants["flat"]["mean_active_relations"] == 0
    assert variants["supported_or_partial_gate"]["mean_retrieval_seconds"] >= 0.0
    assert variants["supported_or_partial_gate"]["mean_semantic_dropped"] > 0


def test_section_reference_alignment_audit_reports_grounding():
    payload = align.build_audit()
    assert payload["experiment_type"] == "section_reference_alignment_audit"
    assert payload["run_count"] == 8
    assert payload["overall"]["section_count"] > 20
    assert 0.0 <= payload["overall"]["mean_alignment_precision"] <= 1.0
    assert 0.0 <= payload["overall"]["uncited_section_rate"] <= 1.0
    assert payload["per_run"][0]["section_count"] > 0
