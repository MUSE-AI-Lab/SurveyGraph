import pytest

from experiments import matched_multi_topic_summary as multi


def test_build_summary_aggregates_four_topics():
    subset_payloads = [
        {
            "topic": "DocVQA",
            "surveygraph": {
                "outline_top_level_sections": 7,
                "outline_total_nodes": 34,
            },
            "scisage": {
                "top_level_sections": 3,
                "total_outline_nodes": 9,
                "latency_seconds": 117.16,
                "meets_requirements": True,
            },
        },
        {
            "topic": "Text-to-SQL Agent",
            "surveygraph": {
                "outline_top_level_sections": 7,
                "outline_total_nodes": 40,
            },
            "scisage": {
                "top_level_sections": 3,
                "total_outline_nodes": 9,
                "latency_seconds": 132.27,
                "meets_requirements": True,
            },
        },
        {
            "topic": "Large Language Model Function Calling",
            "surveygraph": {
                "outline_top_level_sections": 8,
                "outline_total_nodes": 34,
            },
            "scisage": {
                "top_level_sections": 3,
                "total_outline_nodes": 9,
                "latency_seconds": 138.29,
                "meets_requirements": True,
            },
        },
        {
            "topic": "Memory in the Age of AI Agents",
            "surveygraph": {
                "outline_top_level_sections": 7,
                "outline_total_nodes": 38,
            },
            "scisage": {
                "top_level_sections": 2,
                "total_outline_nodes": 4,
                "latency_seconds": 140.17,
                "meets_requirements": False,
            },
        },
    ]
    alignment_payloads = [
        {
            "topic": "DocVQA",
            "alignment": {
                "scisage_role_recall_against_sg": 0.5714285714,
                "missing_roles_in_scisage": ["motivation", "evaluation", "conclusion"],
            },
        },
        {
            "topic": "Text-to-SQL Agent",
            "alignment": {
                "scisage_role_recall_against_sg": 0.4285714286,
                "missing_roles_in_scisage": ["task_background", "motivation", "conclusion"],
            },
        },
        {
            "topic": "Large Language Model Function Calling",
            "alignment": {
                "scisage_role_recall_against_sg": 0.4285714286,
                "missing_roles_in_scisage": ["task_background", "motivation", "conclusion"],
            },
        },
        {
            "topic": "Memory in the Age of AI Agents",
            "alignment": {
                "scisage_role_recall_against_sg": 0.2857142857,
                "missing_roles_in_scisage": ["task_background", "motivation", "challenges", "conclusion"],
            },
        },
    ]

    payload = multi.build_multi_topic_summary(subset_payloads, alignment_payloads)

    assert payload["topic_count"] == 4
    assert payload["aggregate"]["surveygraph_mean_top_sections"] == 7.25
    assert payload["aggregate"]["scisage_mean_top_sections"] == 2.75
    assert payload["aggregate"]["scisage_mean_latency_seconds"] == pytest.approx(131.97, abs=1e-2)
    assert payload["aggregate"]["mean_role_recall"] == pytest.approx(0.429, abs=1e-3)
    assert payload["aggregate"]["meets_requirements_rate"] == pytest.approx(0.75, abs=1e-6)
    assert payload["aggregate"]["missing_role_counts"]["motivation"] == 4
    assert payload["aggregate"]["missing_role_counts"]["conclusion"] == 4
