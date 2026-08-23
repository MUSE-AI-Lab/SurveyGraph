from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from experiments.matched_generation_quality_audit import (
    aggregate_comparison,
    build_markdown,
    validate_matched_runs,
)


def _mekg(ids: list[str], relation_count: int) -> dict:
    return {
        "papers": [{"id": paper_id} for paper_id in ids],
        "relations": [{"source": "a", "target": "b"} for _ in range(relation_count)],
    }


class MatchedGenerationQualityAuditTest(unittest.TestCase):
    def test_validate_matched_runs_requires_same_corpus_and_flat_zero_relations(self) -> None:
        summary = validate_matched_runs(
            _mekg(["p1", "p2"], relation_count=3),
            _mekg(["p2", "p1"], relation_count=0),
            full_section_count=7,
            flat_section_count=7,
        )
        self.assertEqual(
            summary,
            {
                "paper_count": 2,
                "same_paper_ids": True,
                "full_relation_count": 3,
                "flat_relation_count": 0,
                "full_section_count": 7,
                "flat_section_count": 7,
            },
        )

        with self.assertRaisesRegex(ValueError, "same paper corpus"):
            validate_matched_runs(
                _mekg(["p1"], relation_count=3),
                _mekg(["p2"], relation_count=0),
                full_section_count=7,
                flat_section_count=7,
            )


    def test_cli_can_start_from_outside_project_root(self) -> None:
        script = Path(__file__).resolve().parents[2] / "experiments" / "matched_generation_quality_audit.py"
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run(
                [sys.executable, str(script), "--help"],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("matched SurveyGraph-vs-flat", result.stdout)
    def test_markdown_marks_same_numerator_small_section_alignment_as_directional(self) -> None:
        payload = {
            "comparison": [
                {
                    "key": "section_alignment",
                    "label": "Section alignment",
                    "full_count": 3,
                    "full_total": 4,
                    "full_rate": 0.75,
                    "flat_count": 3,
                    "flat_total": 5,
                    "flat_rate": 0.60,
                    "delta_percentage_points": 15.0,
                },
                {
                    "key": "citation_grounding",
                    "label": "Citation grounding",
                    "full_count": 49,
                    "full_total": 55,
                    "full_rate": 49 / 55,
                    "flat_count": 44,
                    "flat_total": 51,
                    "flat_rate": 44 / 51,
                    "delta_percentage_points": 2.816,
                },
            ]
        }
        markdown = build_markdown(payload)
        self.assertIn("| Section alignment | 75.0% (3/4) | 60.0% (3/5) | directional |", markdown)
        self.assertIn("| Citation grounding | 89.1% (49/55) | 86.3% (44/51) | +2.8 pp |", markdown)

    def test_aggregate_comparison_uses_run_specific_denominators_and_deltas(self) -> None:
        grounding = {
            "per_run": [
                {"run_id": "full", "sample_count": 20, "anchored": 10, "partial_anchor": 6},
                {"run_id": "flat", "sample_count": 20, "anchored": 8, "partial_anchor": 5},
            ]
        }
        contrast = {
            "samples": [
                *[{"run_id": "full", "cited_beats_hard_negative": True} for _ in range(13)],
                *[{"run_id": "full", "cited_beats_hard_negative": False} for _ in range(7)],
                *[{"run_id": "flat", "cited_beats_hard_negative": True} for _ in range(11)],
                *[{"run_id": "flat", "cited_beats_hard_negative": False} for _ in range(9)],
            ]
        }
        alignment = {
            "per_run": [
                {
                    "run_id": "full",
                    "section_count": 7,
                    "uncited_section_count": 0,
                    "bucket_counts": {"aligned": 4, "partially_aligned": 2},
                },
                {
                    "run_id": "flat",
                    "section_count": 7,
                    "uncited_section_count": 1,
                    "bucket_counts": {"aligned": 3, "partially_aligned": 1},
                },
            ]
        }

        rows = aggregate_comparison(grounding, contrast, alignment, "full", "flat")
        by_key = {row["key"]: row for row in rows}

        self.assertEqual(by_key["citation_grounding"]["full_count"], 16)
        self.assertEqual(by_key["citation_grounding"]["flat_count"], 13)
        self.assertAlmostEqual(by_key["citation_grounding"]["delta_percentage_points"], 15.0)
        self.assertAlmostEqual(by_key["hard_negative"]["delta_percentage_points"], 10.0)
        self.assertAlmostEqual(by_key["section_alignment"]["delta_percentage_points"], 28.5714286)
        self.assertEqual(by_key["uncited_sections"]["full_value"], 0)
        self.assertEqual(by_key["uncited_sections"]["flat_value"], 1)
        self.assertEqual(by_key["uncited_sections"]["delta"], -1)


if __name__ == "__main__":
    unittest.main()


