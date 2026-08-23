import pytest

from experiments import matched_outline_alignment_eval as align


def test_build_alignment_payload_reports_role_recall_and_missing_roles():
    surveygraph_outline = {
        "sections": [
            {"title": "Introduction"},
            {"title": "Background and Problem Formulation"},
            {"title": "How DocVQA? Technical Workflow and Paradigms"},
            {"title": "Benchmarks and Evaluation"},
            {"title": "Challenges and Future Directions"},
            {"title": "Conclusion"},
        ]
    }
    scisage_result = {
        "final_outline": {
            "sections": [
                {"title": "Foundations and Task Formulation in DocVQA"},
                {"title": "Architectural Paradigms and Methodological Advances"},
                {"title": "Critical Challenges and Future Research Frontiers"},
            ]
        }
    }

    payload = align.build_alignment_payload(
        "Document Visual Question Answering",
        surveygraph_outline,
        scisage_result,
    )

    alignment = payload["alignment"]
    assert alignment["surveygraph_unique_role_count"] == 6
    assert alignment["scisage_unique_role_count"] == 4
    assert alignment["role_order_lcs"] == 4
    assert alignment["scisage_role_recall_against_sg"] == pytest.approx(4 / 6)
    assert alignment["missing_roles_in_scisage"] == ["evaluation", "conclusion"]
    assert alignment["shared_roles_in_order"] == [
        "intro_scope",
        "task_background",
        "methods",
        "challenges",
    ]


def test_build_alignment_for_topic_supports_custom_scisage_result_path(tmp_path):
    fake_scisage = {
        "final_outline": {
            "sections": [
                {"title": "Foundations and Scope of Text-to-SQL Agents"},
                {"title": "Methodological Advances and Architectures"},
                {"title": "Evaluation, Challenges, and Future Directions"},
            ]
        }
    }
    result_path = tmp_path / "scisage_alignment.json"
    result_path.write_text(__import__("json").dumps(fake_scisage), encoding="utf-8")

    payload = align.build_alignment_for_topic(
        "Text-to-SQL Agent",
        result_path,
    )

    assert payload["topic"] == "Text-to-SQL Agent"
    assert payload["alignment"]["surveygraph_unique_role_count"] >= 6
    assert payload["alignment"]["scisage_unique_role_count"] >= 3
    assert payload["alignment"]["role_order_lcs"] >= 3


def test_resolve_cli_args_supports_custom_topic_result_and_output_dir():
    topic, result_path, output_dir = align.resolve_cli_args(
        [
            "matched_outline_alignment_eval.py",
            "Text-to-SQL Agent",
            "outputs/custom_scisage/result.json",
            "outputs/custom_alignment_eval",
        ]
    )

    assert topic == "Text-to-SQL Agent"
    assert result_path.name == "result.json"
    assert output_dir.name == "custom_alignment_eval"
