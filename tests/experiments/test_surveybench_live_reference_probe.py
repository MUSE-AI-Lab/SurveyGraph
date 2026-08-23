from pathlib import Path

from experiments import surveybench_live_reference_probe as probe


def test_compute_citation_coverage_filters_future_target_ids():
    benchmark_refs = {"2308.11432", "2309.07864", "2401.13649"}
    target_refs = ["2308.11432", "2309.07864", "2401.13649", "2501.99999"]

    summary = probe.compute_citation_coverage(target_refs, benchmark_refs)

    assert summary["valid_target_count"] == 2
    assert summary["matched_count"] == 2
    assert summary["coverage"] == 1.0
    assert "2401.13649" not in summary["matched_ids"]
    assert "2501.99999" not in summary["matched_ids"]


def test_extract_reference_ids_from_bib_recovers_arxiv_style_keys(tmp_path: Path):
    bib = tmp_path / "references.bib"
    bib.write_text(
        """@article{arXiv_2308.11432,\n title={A}\n}\n"""
        """@article{foo,\n title={B}\n}\n"""
        """@misc{arXiv:2309.07864v2,\n title={C}\n}\n""",
        encoding="utf-8",
    )

    ids = probe.extract_reference_ids_from_bib(bib)

    assert ids == ["2308.11432", "2309.07864"]


def test_build_archived_run_result_matches_known_archive_overlap():
    result = probe.build_archived_run_result(
        topic="LLM-based Multi-Agent",
        run_id="2025-12-23-1426_Large_Language_Model",
        run_label="Large Language Model Function Calling",
    )

    assert result["system"] == "SurveyGraph-archived-corpus"
    assert result["matched_count"] == 11
    assert result["valid_target_count"] == 55
    assert result["coverage"] == 0.2
