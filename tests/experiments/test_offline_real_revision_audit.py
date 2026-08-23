from experiments import offline_real_revision_audit as audit


def _load_first_run():
    item = audit.ARCHIVED_RUNS[0]
    base = audit.ROOT / "outputs" / item["id"]
    return audit.RunBundle(
        run_id=item["id"],
        label=item["label"],
        base_dir=base,
        mekg=audit.load_json(base / "mekg" / "mekg_data.json"),
        outline=audit.load_json(base / "outline.json"),
    )


def test_core_score_weight_sensitivity_audit_structure():
    run = _load_first_run()
    summary = audit.run_core_score_weight_sensitivity_audit([run])

    assert summary["experiment_type"] == "core_score_weight_sensitivity_audit"
    assert summary["aggregate"]["citation_signal_nonzero_runs"] == 0
    assert summary["aggregate"]["variant_overlap_vs_base"]["degree_heavy"]["mean"] <= 10
    assert summary["per_run"][0]["elbow_count"] >= 10


def test_relation_family_ablation_structure():
    run = _load_first_run()
    summary = audit.run_relation_family_ablation([run])

    assert summary["experiment_type"] == "relation_family_ablation"
    assert "full" in summary["aggregate"]
    assert "semantic_only" in summary["pairwise_vs_full"]
    assert summary["aggregate"]["full"]["core_paper_recall"]["mean"] >= 0
    assert summary["per_run"][0]["variants"]["full"]["active_relation_count"] > 0


def test_retrieval_budget_sweep_structure():
    run = _load_first_run()
    summary = audit.run_retrieval_budget_sweep([run], budgets=(3, 5, 7))

    assert summary["experiment_type"] == "retrieval_budget_sweep"
    assert summary["budgets"] == [3, 5, 7]
    assert set(summary["aggregate"].keys()) == {"3", "5", "7"}
    assert summary["aggregate"]["5"]["core_paper_recall"]["graph_mean"] >= 0
    assert summary["per_run"][0]["budgets"]["5"]["graph"]["sections_evaluated"] > 0


def test_confidence_threshold_sweep_structure():
    run = _load_first_run()
    summary = audit.run_confidence_threshold_sweep([run], thresholds=(0.5, 0.7, 0.9))

    assert summary["experiment_type"] == "relation_confidence_threshold_sweep"
    assert summary["thresholds"] == [0.5, 0.7, 0.9]
    assert set(summary["aggregate"].keys()) == {"0.5", "0.7", "0.9"}
    assert summary["aggregate"]["0.7"]["active_relation_share_mean"] <= 1.0
    assert summary["per_run"][0]["thresholds"]["0.9"]["graph"]["sections_evaluated"] > 0


def test_artifact_dedup_robustness_audit_structure():
    summary = audit.run_artifact_dedup_robustness_audit()

    assert summary["experiment_type"] == "artifact_dedup_robustness_audit"
    assert summary["rows_found"] >= summary["unique_hash_rows"]
    assert summary["duplicate_group_count"] >= 1
    assert "SurveyForge" in summary["systems"]
    assert summary["systems"]["SurveyForge"]["original_count"] >= summary["systems"]["SurveyForge"]["dedup_count"]


def test_artifact_structure_proxy_robustness_audit_structure():
    summary = audit.run_artifact_structure_proxy_robustness_audit()

    assert summary["experiment_type"] == "artifact_structure_proxy_robustness_audit"
    assert summary["rows_found"] == 50
    assert summary["rows_with_toc"] == 47
    assert summary["toc_heading_exact_match_rate"] == 1.0
    assert summary["heading_count_mismatch_rows"] == 1
    assert summary["systems"]["SurveyForge"]["toc_heading_exact_match_rate"] == 1.0
    assert summary["systems"]["AutoSurvey"]["references_heading_rate"] == 0.0


def test_artifact_length_normalized_proxy_audit_structure():
    summary = audit.run_artifact_length_normalized_proxy_audit()

    assert summary["experiment_type"] == "artifact_length_normalized_proxy_audit"
    assert summary["rows_found"] == 50
    assert summary["dedup_rows"] == 46
    assert "ARISE" in summary["systems"]
    assert "SurveyX" in summary["systems"]
    assert summary["systems"]["ARISE"]["editable_artifact_rate"] == 1.0
    assert summary["systems"]["SurveyForge"]["editable_artifact_rate"] == 0.0
    assert summary["systems"]["AutoSurvey"]["heading_density_per_10k_words_median"] == 0.0
    assert summary["surveygraph_fresh_combined"]["count"] == 2
    assert summary["surveygraph_fresh_combined"]["editable_artifact_rate"] == 1.0


def test_manual_spot_audit_expanded_structure():
    runs = [_load_first_run()]
    summary = audit.run_manual_spot_audit(runs)

    assert summary["experiment_type"] == "manual_citation_support_spot_audit"
    assert summary["overall"]["total"] == 24
    assert summary["overall"]["supported_or_partial_rate"] > 0.5
    assert summary["aggregate"]["extends"]["total"] == 8
    assert summary["aggregate"]["improves"]["total"] == 8
    assert summary["aggregate"]["applies"]["total"] == 8
    assert "issue_tag_counts" in summary
    assert summary["weak_case_total"] == 16
    assert summary["failure_mode_counts"]["topical_overlap_without_explicit_lineage"] == 11
    assert summary["failure_mode_counts"]["target_role_mismatch"] == 3
    assert summary["failure_mode_counts"]["cross_task_mismatch"] == 1
    assert summary["failure_mode_counts"]["temporal_reversal"] == 1
    assert summary["samples"][0]["confidence"] >= 0.0
    assert "temporal_ok" in summary["samples"][0]
    assert "issue_tag" in summary["samples"][0]


def test_archived_input_integrity_audit_structure():
    run = _load_first_run()
    summary = audit.run_archived_input_integrity_audit([run])

    assert summary["experiment_type"] == "archived_input_integrity_audit"
    assert summary["aggregate"]["total_runs"] == 1
    assert summary["aggregate"]["total_papers"] == 200
    assert summary["aggregate"]["total_relations"] > 0
    assert summary["aggregate"]["paper_missing_field_counts"]["title"] == 0
    assert summary["aggregate"]["paper_missing_field_counts"]["abstract"] == 0
    assert summary["aggregate"]["paper_missing_field_counts"]["category"] == 0
    assert summary["aggregate"]["paper_missing_field_counts"]["subcategory"] == 0
    assert summary["aggregate"]["paper_missing_field_counts"]["year"] == 0
    assert summary["aggregate"]["paper_missing_field_counts"]["source"] == 0
    assert summary["aggregate"]["relation_missing_field_counts"]["source"] == 0
    assert summary["aggregate"]["relation_missing_field_counts"]["target"] == 0
    assert summary["aggregate"]["relation_missing_field_counts"]["type"] == 0
    assert summary["aggregate"]["relation_missing_field_counts"]["confidence"] == 0
    assert summary["aggregate"]["exact_title_duplicate_rows"] == 0
    assert summary["aggregate"]["normalized_title_duplicate_rows"] == 0
    assert summary["aggregate"]["unresolved_relation_source_count"] == 0
    assert summary["aggregate"]["unresolved_relation_target_count"] == 0
    assert summary["aggregate"]["confidence_min"] >= 0.0
    assert summary["aggregate"]["confidence_max"] <= 1.0
    assert "arxiv" in summary["aggregate"]["source_counts"]


def test_markdown_report_lists_all_semantic_edge_rows():
    runs = [_load_first_run()]
    graph_summary = audit.run_graph_retrieval_diagnostic(runs)
    budget_sweep_summary = audit.run_retrieval_budget_sweep(runs)
    confidence_sweep_summary = audit.run_confidence_threshold_sweep(runs)
    relation_family_summary = audit.run_relation_family_ablation(runs)
    core_score_summary = audit.run_core_score_weight_sensitivity_audit(runs)
    input_integrity_summary = {
        "aggregate": {
            "total_runs": 1,
            "total_papers": 200,
            "total_relations": 2284,
            "paper_missing_field_counts": {"title": 0, "abstract": 0, "category": 0, "subcategory": 0, "year": 0, "source": 0},
            "relation_missing_field_counts": {"source": 0, "target": 0, "type": 0, "confidence": 0},
            "exact_title_duplicate_rows": 0,
            "normalized_title_duplicate_rows": 0,
            "unresolved_relation_source_count": 0,
            "unresolved_relation_target_count": 0,
            "confidence_min": 0.4,
            "confidence_mean": 0.8,
            "confidence_max": 1.0,
        }
    }
    edge_summary = audit.run_edge_audit(runs)
    edge_confidence_profile = audit.run_edge_confidence_profile(runs)
    runtime_summary = {
        "archived_full_runs": {"summary": {"total_minutes_mean": 0, "total_minutes_median": 0, "total_minutes_min": 0, "total_minutes_max": 0, "stage_share_mean": {}}},
        "fresh_low_cost_runs": [],
        "scisage_outline_partial": {"latency_seconds": 0, "top_level_sections": 0, "total_outline_nodes": 0},
    }
    artifact_dedup_summary = {
        "rows_found": 0,
        "duplicate_group_count": 0,
        "duplicate_row_count": 0,
        "systems": {},
    }
    artifact_structure_summary = {
        "rows_found": 0,
        "rows_with_toc": 0,
        "toc_heading_exact_match_rate": 0.0,
        "references_heading_rate": 0.0,
        "systems": {},
    }
    artifact_length_normalized_summary = {
        "rows_found": 0,
        "dedup_rows": 0,
        "systems": {
            "ARISE": {
                "count": 0,
                "heading_density_per_10k_words_median": 0.0,
                "table_figure_density_per_10k_words_median": 0.0,
                "editable_artifact_rate": 0.0,
            }
        },
        "surveygraph_fresh_combined": {
            "count": 0,
            "heading_density_per_10k_words_median": 0.0,
            "table_figure_density_per_10k_words_median": 0.0,
            "editable_artifact_rate": 0.0,
        },
    }
    spot_audit_summary = {
        "run_id": "demo",
        "overall": {"supported": 8, "partial": 11, "unsupported": 5, "total": 24},
        "supported_or_partial_rate": 19 / 24,
        "weak_case_total": 16,
        "failure_mode_counts": {
            "topical_overlap_without_explicit_lineage": 11,
            "target_role_mismatch": 3,
            "cross_task_mismatch": 1,
            "temporal_reversal": 1,
        },
        "aggregate": {},
    }

    report = audit.build_markdown_report(
        graph_summary,
        budget_sweep_summary,
        confidence_sweep_summary,
        relation_family_summary,
        core_score_summary,
        input_integrity_summary,
        edge_summary,
        edge_confidence_profile,
        runtime_summary,
        artifact_dedup_summary,
        artifact_structure_summary,
        artifact_length_normalized_summary,
        spot_audit_summary,
    )

    semantic_section = report.split("## 6. MEKG Semantic-Edge Consistency Audit", 1)[1].split("## 7. Runtime / Cost Summary", 1)[0]
    assert semantic_section.count("| extends |") == 1
    assert semantic_section.count("| improves |") == 1
    assert semantic_section.count("| applies |") == 1
    assert "Confidence-Stratified Semantic-Edge Profile" in semantic_section
    assert "zero within-run exact or normalized title duplicates" in report
    assert "24 sampled semantic edges" in report
    assert "topical-overlap without explicit lineage" in report


def test_generated_citation_support_spot_audit_structure():
    summary = audit.run_generated_citation_support_spot_audit()

    assert summary["experiment_type"] == "generated_citation_support_spot_audit"
    assert summary["run_id"] == audit.GENERATED_CITATION_SPOT_AUDIT_RUN_ID
    assert summary["overall"]["total"] == 12
    assert 0.0 <= summary["supported_or_partial_rate"] <= 1.0
    assert summary["samples"][0]["citation_key"].startswith("arXiv_")
    assert len(summary["samples"][0]["sentence"]) > 40
    assert summary["samples"][0]["paper_title"]
    assert summary["samples"][0]["label"] in {"supported", "partial", "unsupported"}
    assert summary["samples"][0]["issue_tag"]
    assert summary["samples"][0]["rationale"]


def test_markdown_report_includes_generated_citation_support_block():
    run = _load_first_run()
    graph_summary = audit.run_graph_retrieval_diagnostic([run])
    budget_sweep_summary = audit.run_retrieval_budget_sweep([run])
    confidence_sweep_summary = audit.run_confidence_threshold_sweep([run])
    relation_family_summary = audit.run_relation_family_ablation([run])
    core_score_summary = audit.run_core_score_weight_sensitivity_audit([run])
    input_integrity_summary = {
        "aggregate": {
            "total_runs": 1,
            "total_papers": 200,
            "total_relations": 2284,
            "paper_missing_field_counts": {"title": 0, "abstract": 0, "category": 0, "subcategory": 0, "year": 0, "source": 0},
            "relation_missing_field_counts": {"source": 0, "target": 0, "type": 0, "confidence": 0},
            "exact_title_duplicate_rows": 0,
            "normalized_title_duplicate_rows": 0,
            "unresolved_relation_source_count": 0,
            "unresolved_relation_target_count": 0,
            "confidence_min": 0.4,
            "confidence_mean": 0.8,
            "confidence_max": 1.0,
        }
    }
    edge_summary = audit.run_edge_audit([run])
    edge_confidence_profile = audit.run_edge_confidence_profile([run])
    runtime_summary = {
        "archived_full_runs": {"summary": {"total_minutes_mean": 0, "total_minutes_median": 0, "total_minutes_min": 0, "total_minutes_max": 0, "stage_share_mean": {}}},
        "fresh_low_cost_runs": [],
        "scisage_outline_partial": {"latency_seconds": 0, "top_level_sections": 0, "total_outline_nodes": 0},
    }
    artifact_dedup_summary = {
        "rows_found": 0,
        "duplicate_group_count": 0,
        "duplicate_row_count": 0,
        "systems": {},
    }
    artifact_structure_summary = {
        "rows_found": 0,
        "rows_with_toc": 0,
        "toc_heading_exact_match_rate": 0.0,
        "references_heading_rate": 0.0,
        "systems": {},
    }
    artifact_length_normalized_summary = {
        "rows_found": 0,
        "dedup_rows": 0,
        "systems": {
            "ARISE": {
                "count": 0,
                "citation_density_per_1k_words_median": 0.0,
                "heading_density_per_10k_words_median": 0.0,
                "table_figure_density_per_10k_words_median": 0.0,
                "editable_artifact_rate": 0.0,
            }
        },
        "surveygraph_fresh_combined": {
            "count": 0,
            "citation_density_per_1k_words_median": 0.0,
            "heading_density_per_10k_words_median": 0.0,
            "table_figure_density_per_10k_words_median": 0.0,
            "editable_artifact_rate": 0.0,
        },
    }
    spot_audit_summary = {
        "run_id": "demo",
        "overall": {"supported": 8, "partial": 11, "unsupported": 5, "total": 24},
        "supported_or_partial_rate": 19 / 24,
        "weak_case_total": 16,
        "failure_mode_counts": {
            "topical_overlap_without_explicit_lineage": 11,
            "target_role_mismatch": 3,
            "cross_task_mismatch": 1,
            "temporal_reversal": 1,
        },
        "aggregate": {},
    }
    generated_spot_audit_summary = {
        "run_id": "20251224_204059_d990305f",
        "overall": {"supported": 8, "partial": 3, "unsupported": 1, "total": 12},
        "supported_or_partial_rate": 11 / 12,
        "issue_tag_counts": {
            "well_supported": 8,
            "temporal_trend_overgeneralization": 1,
            "detail_not_evident_in_abstract": 2,
            "formalization_not_in_source": 1,
        },
    }

    report = audit.build_markdown_report(
        graph_summary,
        budget_sweep_summary,
        confidence_sweep_summary,
        relation_family_summary,
        core_score_summary,
        input_integrity_summary,
        edge_summary,
        edge_confidence_profile,
        runtime_summary,
        artifact_dedup_summary,
        artifact_structure_summary,
        artifact_length_normalized_summary,
        spot_audit_summary,
        generated_spot_audit_summary,
    )

    assert "## 12. Generated-Survey Citation-Support Spot Audit" in report
    assert "12 sampled single-citation body sentences" in report
    assert "Supported-or-partial rate" in report
    assert "formalization not in source" in report


def test_exact_paired_sign_flip_test_known_values():
    summary = audit.exact_paired_sign_flip_test([1.0, 2.0, 3.0])

    assert summary["sample_size"] == 3
    assert summary["nonzero_pairs"] == 3
    assert summary["observed_mean_delta"] == 2.0
    assert summary["observed_median_delta"] == 2.0
    assert summary["positive_pairs"] == 3
    assert summary["negative_pairs"] == 0
    assert summary["one_sided_p_greater"] == 0.125
    assert summary["two_sided_p"] == 0.25


def test_graph_retrieval_diagnostic_reports_paired_significance():
    run = _load_first_run()
    summary = audit.run_graph_retrieval_diagnostic([run])

    assert "paired_significance" in summary
    assert "core_paper_recall" in summary["paired_significance"]
    assert "relation_density" in summary["paired_significance"]
    core = summary["paired_significance"]["core_paper_recall"]
    assert core["sample_size"] == 1
    assert 0.0 <= core["one_sided_p_greater"] <= 1.0
    assert 0.0 <= core["two_sided_p"] <= 1.0


def test_graph_retrieval_diagnostic_reports_signal_component_ablation():
    run = _load_first_run()
    summary = audit.run_graph_retrieval_diagnostic([run])

    assert "signal_component_ablation" in summary
    ablation = summary["signal_component_ablation"]
    assert "aggregate" in ablation
    assert "pairwise_vs_full" in ablation
    assert "full" in ablation["aggregate"]
    assert "no_expansion" in ablation["aggregate"]
    assert "flat" in ablation["pairwise_vs_full"]
    assert "core_paper_recall" in ablation["aggregate"]["full"]
    assert ablation["aggregate"]["full"]["core_paper_recall"]["mean"] >= 0.0


def test_markdown_report_includes_paired_significance_block():
    run = _load_first_run()
    graph_summary = audit.run_graph_retrieval_diagnostic([run])
    budget_sweep_summary = audit.run_retrieval_budget_sweep([run])
    confidence_sweep_summary = audit.run_confidence_threshold_sweep([run])
    relation_family_summary = audit.run_relation_family_ablation([run])
    core_score_summary = audit.run_core_score_weight_sensitivity_audit([run])
    input_integrity_summary = {
        "aggregate": {
            "total_runs": 1,
            "total_papers": 200,
            "total_relations": 2284,
            "paper_missing_field_counts": {"title": 0, "abstract": 0, "category": 0, "subcategory": 0, "year": 0, "source": 0},
            "relation_missing_field_counts": {"source": 0, "target": 0, "type": 0, "confidence": 0},
            "exact_title_duplicate_rows": 0,
            "normalized_title_duplicate_rows": 0,
            "unresolved_relation_source_count": 0,
            "unresolved_relation_target_count": 0,
            "confidence_min": 0.4,
            "confidence_mean": 0.8,
            "confidence_max": 1.0,
        }
    }
    edge_summary = audit.run_edge_audit([run])
    edge_confidence_profile = audit.run_edge_confidence_profile([run])
    runtime_summary = {
        "archived_full_runs": {"summary": {"total_minutes_mean": 0, "total_minutes_median": 0, "total_minutes_min": 0, "total_minutes_max": 0, "stage_share_mean": {}}},
        "fresh_low_cost_runs": [],
        "scisage_outline_partial": {"latency_seconds": 0, "top_level_sections": 0, "total_outline_nodes": 0},
    }
    artifact_dedup_summary = {
        "rows_found": 0,
        "duplicate_group_count": 0,
        "duplicate_row_count": 0,
        "systems": {},
    }
    artifact_structure_summary = {
        "rows_found": 0,
        "rows_with_toc": 0,
        "toc_heading_exact_match_rate": 0.0,
        "references_heading_rate": 0.0,
        "systems": {},
    }
    artifact_length_normalized_summary = {
        "rows_found": 0,
        "dedup_rows": 0,
        "systems": {
            "ARISE": {
                "count": 0,
                "citation_density_per_1k_words_median": 0.0,
                "heading_density_per_10k_words_median": 0.0,
                "table_figure_density_per_10k_words_median": 0.0,
                "editable_artifact_rate": 0.0,
            }
        },
        "surveygraph_fresh_combined": {
            "count": 0,
            "citation_density_per_1k_words_median": 0.0,
            "heading_density_per_10k_words_median": 0.0,
            "table_figure_density_per_10k_words_median": 0.0,
            "editable_artifact_rate": 0.0,
        },
    }
    spot_audit_summary = {
        "run_id": "demo",
        "overall": {"supported": 8, "partial": 11, "unsupported": 5, "total": 24},
        "supported_or_partial_rate": 19 / 24,
        "weak_case_total": 16,
        "failure_mode_counts": {
            "topical_overlap_without_explicit_lineage": 11,
            "target_role_mismatch": 3,
            "cross_task_mismatch": 1,
            "temporal_reversal": 1,
        },
        "aggregate": {},
    }

    report = audit.build_markdown_report(
        graph_summary,
        budget_sweep_summary,
        confidence_sweep_summary,
        relation_family_summary,
        core_score_summary,
        input_integrity_summary,
        edge_summary,
        edge_confidence_profile,
        runtime_summary,
        artifact_dedup_summary,
        artifact_structure_summary,
        artifact_length_normalized_summary,
        spot_audit_summary,
    )

    assert "### Paired Sign-Flip Summary" in report
    assert "### Signal-Component Ablation" in report
    assert "## 10. Length-Normalized Artifact Proxy Audit" in report
    assert "| No expansion |" in report
    assert "| Core-paper recall |" in report
    assert "| Average PageRank |" in report
    assert "One-sided p (>0)" in report
    assert "Two-sided p" in report
