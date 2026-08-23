from pathlib import Path
import json

from experiments import matched_baseline_subset_eval as mb


def test_build_summary_contains_core_fields():
    payload = mb.build_matched_summary(topic_label="Document Visual Question Answering")
    assert payload["topic"] == "Document Visual Question Answering"
    assert payload["matched_setup"]["backend_family"] == "DashScope-compatible OpenAI"
    assert payload["surveygraph"]["external_core_proxy_recall_top20"] >= 0.0
    assert payload["surveygraph"]["graph_core_recall_top5"] >= 0.0
    assert payload["scisage"]["top_level_sections"] >= 1
    assert payload["scisage"]["total_outline_nodes"] >= payload["scisage"]["top_level_sections"]


def test_build_summary_supports_custom_scisage_result_path(tmp_path: Path):
    fake_scisage = {
        "user_query": "Text-to-SQL Agent",
        "artifact_stats": {
            "top_level_sections": 3,
            "total_outline_nodes": 9,
        },
        "runtime": {
            "latency_seconds": 12.34,
        },
        "backend": {
            "model": "qwen3.6-plus",
        },
        "quality_gate": {
            "meets_requirements": True,
        },
    }
    result_path = tmp_path / "scisage_result.json"
    result_path.write_text(json.dumps(fake_scisage), encoding="utf-8")

    payload = mb.build_matched_summary(
        topic_label="Text-to-SQL Agent",
        scisage_result_path=result_path,
    )

    assert payload["topic"] == "Text-to-SQL Agent"
    assert payload["surveygraph"]["external_core_proxy_target_size"] == 5
    assert payload["scisage"]["query"] == "Text-to-SQL Agent"
    assert payload["scisage"]["latency_seconds"] == 12.34


def test_resolve_cli_args_supports_custom_topic_result_and_output_dir():
    topic, result_path, output_dir = mb.resolve_cli_args(
        [
            "matched_baseline_subset_eval.py",
            "Text-to-SQL Agent",
            "outputs/custom_scisage/result.json",
            "outputs/custom_subset_eval",
        ]
    )

    assert topic == "Text-to-SQL Agent"
    assert result_path.name == "result.json"
    assert output_dir.name == "custom_subset_eval"
