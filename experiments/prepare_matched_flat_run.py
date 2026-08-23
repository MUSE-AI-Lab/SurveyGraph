from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _section_count(outline: Dict[str, Any]) -> int:
    sections = outline.get("sections") or []
    return len(sections) if isinstance(sections, list) else 0


def prepare_flat_run(source: Path, target: Path, *, target_task_id: str) -> Dict[str, Any]:
    source = source.resolve()
    target = target.resolve()
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Target directory is not empty: {target}")

    mekg_path = source / "mekg" / "mekg_data.json"
    outline_path = source / "outline.json"
    outlines_path = source / "outlines.json"
    config_path = source / "task_config.json"
    papers_dir = source / "papers"
    for required in (mekg_path, outline_path, outlines_path, config_path, papers_dir):
        if not required.exists():
            raise FileNotFoundError(required)

    mekg = _read_json(mekg_path)
    outline = _read_json(outline_path)
    config = _read_json(config_path)
    paper_files = sorted(papers_dir.glob("*.json"))
    if not paper_files:
        raise ValueError("Source run has no paper JSON files")

    target.mkdir(parents=True, exist_ok=True)
    (target / "mekg").mkdir()
    (target / "papers").mkdir()
    (target / "logs").mkdir()

    mekg["relations"] = []
    mekg["relations_count"] = 0
    for paper in mekg.get("papers", []):
        paper["category"] = None
        paper["subcategory"] = None
    _write_json(target / "mekg" / "mekg_data.json", mekg)

    for source_paper in paper_files:
        paper = _read_json(source_paper)
        attri = paper.get("attri")
        if isinstance(attri, dict):
            for key in ("mekg_category", "mekg_subcategory", "mekg_relations"):
                attri.pop(key, None)
        paper.pop("mount_outline", None)
        target_paper = target / "papers" / source_paper.name
        paper["path"] = str(target_paper)
        _write_json(target_paper, paper)

    shutil.copy2(outline_path, target / "outline.json")
    shutil.copy2(outlines_path, target / "outlines.json")

    paper_count = len(paper_files)
    section_count = _section_count(outline)
    config["task_id"] = target_task_id
    config["max_papers"] = paper_count
    _write_json(target / "task_config.json", config)
    _write_json(
        target / "checkpoint.json",
        {
            "step": 3,
            "step_name": "PAPERS_RECLASSIFIED",
            "timestamp": datetime.now().isoformat(),
            "task_id": target_task_id,
            "topic": config.get("topic", mekg.get("topic", "")),
            "papers_count": paper_count,
            "relations_count": 0,
            "sections_count": section_count,
        },
    )

    manifest = {
        "experiment": "matched_flat_generation_baseline",
        "created_at": datetime.now().astimezone().isoformat(),
        "source_run": str(source),
        "output_run": str(target),
        "controlled_factors": [
            "same paper corpus",
            "same backend within topic",
            "same top-down outline",
            "same generation and reflection settings",
        ],
        "removed_graph_inputs": [
            "all MEKG relations",
            "paper category and subcategory assignments",
            "paper-level MEKG attributes",
            "existing section mounts",
        ],
        "paper_count": paper_count,
        "relation_count": 0,
        "section_count": section_count,
    }
    _write_json(target / "flat_baseline_manifest.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a matched flat generation run from a completed source run.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = prepare_flat_run(args.source, args.target, target_task_id=args.task_id)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
