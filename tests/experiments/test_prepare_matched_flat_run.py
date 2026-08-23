from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.prepare_matched_flat_run import prepare_flat_run


class PrepareMatchedFlatRunTest(unittest.TestCase):
    def test_prepare_flat_run_removes_graph_inputs_and_preserves_corpus_outline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            target = root / "target"
            (source / "mekg").mkdir(parents=True)
            (source / "papers").mkdir()
            (source / "mekg" / "mekg_data.json").write_text(
                json.dumps(
                    {
                        "topic": "Topic",
                        "papers_count": 1,
                        "relations_count": 1,
                        "categories": {"Core": {"Method": 1}},
                        "taxonomy": [{"category": "Core"}],
                        "classification_stats": {"total": 1},
                        "papers": [
                            {
                                "id": "arXiv:1",
                                "title": "Paper",
                                "category": "Core",
                                "subcategory": "Method",
                            }
                        ],
                        "relations": [{"source": "a", "target": "b"}],
                    }
                ),
                encoding="utf-8",
            )
            (source / "papers" / "arXiv_1.json").write_text(
                json.dumps(
                    {
                        "id": "arXiv:1",
                        "title": "Paper",
                        "path": str(source / "papers" / "arXiv_1.json"),
                        "attri": {
                            "background": "kept",
                            "mekg_category": "Core",
                            "mekg_subcategory": "Method",
                            "mekg_relations": [{"target": "x"}],
                        },
                        "mount_outline": [{"section number": "2"}],
                    }
                ),
                encoding="utf-8",
            )
            outline = {"title": "Survey", "topic": "Topic", "sections": [{"number": str(i)} for i in range(1, 8)]}
            (source / "outline.json").write_text(json.dumps(outline), encoding="utf-8")
            (source / "outlines.json").write_text(json.dumps(outline), encoding="utf-8")
            (source / "task_config.json").write_text(
                json.dumps({"task_id": "source", "topic": "Topic", "year_start": 2020, "year_end": 2026, "max_papers": 30}),
                encoding="utf-8",
            )

            manifest = prepare_flat_run(source, target, target_task_id="flat")

            mekg = json.loads((target / "mekg" / "mekg_data.json").read_text(encoding="utf-8"))
            paper = json.loads((target / "papers" / "arXiv_1.json").read_text(encoding="utf-8"))
            checkpoint = json.loads((target / "checkpoint.json").read_text(encoding="utf-8"))
            config = json.loads((target / "task_config.json").read_text(encoding="utf-8"))

            self.assertEqual(mekg["relations"], [])
            self.assertEqual(mekg["relations_count"], 0)
            self.assertIsNone(mekg["papers"][0]["category"])
            self.assertIsNone(mekg["papers"][0]["subcategory"])
            self.assertEqual(paper["attri"]["background"], "kept")
            self.assertNotIn("mekg_category", paper["attri"])
            self.assertNotIn("mekg_subcategory", paper["attri"])
            self.assertNotIn("mekg_relations", paper["attri"])
            self.assertNotIn("mount_outline", paper)
            self.assertEqual(Path(paper["path"]), target / "papers" / "arXiv_1.json")
            self.assertEqual(checkpoint["step_name"], "PAPERS_RECLASSIFIED")
            self.assertEqual(checkpoint["papers_count"], 1)
            self.assertEqual(checkpoint["relations_count"], 0)
            self.assertEqual(checkpoint["sections_count"], 7)
            self.assertEqual(config["task_id"], "flat")
            self.assertEqual(config["max_papers"], 1)
            self.assertTrue((target / "outline.json").exists())
            self.assertTrue((target / "outlines.json").exists())
            self.assertTrue((target / "logs").is_dir())
            self.assertEqual(manifest["controlled_factors"][0], "same paper corpus")


if __name__ == "__main__":
    unittest.main()
