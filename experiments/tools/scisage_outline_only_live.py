#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Low-cost live partial baseline for SciSage:
- reuse SciSage's native outline-generation code path;
- avoid full paper generation / section writing / RAG;
- patch the model backend to DashScope OpenAI-compatible endpoint;
- run only the minimal outline + reflection path.
"""

from __future__ import annotations

import json
import importlib
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[2]
SCISAGE_CORE = ROOT / "refer" / "SciSage-main" / "core"
OUTPUT_DIR = ROOT / "outputs" / "scisage_outline_only_live_20260524"
CONFIG_PATH = ROOT / "experiments" / "configs" / "dashscope_models.local.json"
DEFAULT_QUERY = "automated survey generation systems and frameworks"


def ensure_langchain_pydantic_v1_shim() -> None:
    """Register a minimal compatibility shim for old LangChain imports on newer environments."""
    try:
        importlib.import_module("langchain_core.pydantic_v1")
        return
    except ModuleNotFoundError:
        pass

    try:
        import pydantic.v1 as pydantic_v1
    except ModuleNotFoundError:
        import pydantic as pydantic_v1

    shim = ModuleType("langchain_core.pydantic_v1")
    for attr in ("BaseModel", "Field", "root_validator", "validator", "Extra"):
        if hasattr(pydantic_v1, attr):
            setattr(shim, attr, getattr(pydantic_v1, attr))
    sys.modules["langchain_core.pydantic_v1"] = shim


def ensure_langchain_schema_shim() -> None:
    """Register a minimal compatibility shim for deprecated langchain.schema import paths."""
    try:
        importlib.import_module("langchain.schema")
        return
    except ModuleNotFoundError:
        pass

    from langchain_core.output_parsers import StrOutputParser

    shim = ModuleType("langchain.schema")
    shim.StrOutputParser = StrOutputParser
    sys.modules["langchain.schema"] = shim


def load_dashscope_config() -> Dict[str, Any]:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {
        "api_key": cfg["TOKEN"],
        "base_url": cfg["REMOTE_URL"].replace("/chat/completions", ""),
        "model": cfg.get("DEFAULT_CHATAGENT_MODEL", "qwen3.6-plus"),
    }


def outline_to_markdown(section: Dict[str, Any], depth: int = 1) -> List[str]:
    prefix = "#" * min(depth + 1, 6)
    lines = [f"{prefix} {section['title']}"]
    for point in section.get("key_points") or []:
        lines.append(f"- {point}")
    for subsection in section.get("subsections") or []:
        lines.extend(outline_to_markdown(subsection, depth + 1))
    return lines


def count_outline_nodes(section: Dict[str, Any]) -> int:
    total = 1
    for subsection in section.get("subsections") or []:
        total += count_outline_nodes(subsection)
    return total


def resolve_cli_args(argv: List[str]) -> tuple[str, Path]:
    query = argv[1] if len(argv) > 1 else DEFAULT_QUERY
    output_dir = Path(argv[2]) if len(argv) > 2 else OUTPUT_DIR
    return query, output_dir


def main() -> int:
    user_query, output_dir = resolve_cli_args(sys.argv)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir

    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now().isoformat(timespec="seconds")

    cfg = load_dashscope_config()
    output_json = output_dir / "scisage_outline_live_result.json"
    output_md = output_dir / "scisage_outline_live_outline.md"
    output_audit = output_dir / "scisage_outline_live_audit.json"

    sys.path.insert(0, str(SCISAGE_CORE))
    ensure_langchain_pydantic_v1_shim()
    ensure_langchain_schema_shim()

    try:
        from langchain_openai import ChatOpenAI

        import model_factory
        import paper_outline_opt

        live_llm = ChatOpenAI(
            model=cfg["model"],
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            temperature=0.3,
            max_tokens=4096,
        )

        # Patch SciSage to use the DashScope-backed chat model for the minimal outline path.
        model_factory.llm_map["Qwen3-8B"] = live_llm
        paper_outline_opt.llm_map["Qwen3-8B"] = live_llm
        paper_outline_opt.default_llm = live_llm
        paper_outline_opt.OUTLINE_GENERAOR_MODELS = ["Qwen3-8B"]
        paper_outline_opt.MODEL_GEN_QUERY = "Qwen3-8B"

        research_field = paper_outline_opt.QueryIntent(
            research_field="Computer Science",
            paper_type="survey",
            topic=user_query,
            explanation="Manual low-cost setting for outline-only live baseline test.",
        )

        state = paper_outline_opt.State(
            user_query=user_query,
            research_field=research_field,
            max_reflections=1,
            max_sections=3,
            min_depth=1,
        )

        t0 = time.time()
        state = paper_outline_opt.generate_outlines(state)
        state = paper_outline_opt.synthesize_outlines(state)
        state = paper_outline_opt.reflection(state)
        decision = paper_outline_opt.should_continue_improvement(state)
        if decision == "improve":
            state = paper_outline_opt.improve_outline(state)
            state = paper_outline_opt.reflection(state)
            decision = paper_outline_opt.should_continue_improvement(state)
        state = paper_outline_opt.finalize_outline(state)
        latency = round(time.time() - t0, 2)

        if state.final_outline is None:
            raise RuntimeError("SciSage outline generation returned no final_outline")

        final_outline = state.final_outline.model_dump()
        top_level_sections = len(final_outline.get("sections", []))
        total_outline_nodes = sum(
            count_outline_nodes(section) for section in final_outline.get("sections", [])
        )

        result = {
            "status": "success",
            "experiment_type": "SciSage outline-only live partial baseline",
            "source": "refer/SciSage-main/core/paper_outline_opt.py",
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "user_query": user_query,
            "backend": {
                "provider": "DashScope OpenAI-compatible",
                "model": cfg["model"],
                "base_url": cfg["base_url"],
            },
            "runtime": {
                "latency_seconds": latency,
                "max_reflections": 1,
                "max_sections": 3,
                "min_depth": 1,
            },
            "quality_gate": {
                "reflection_count": state.reflection_count,
                "meets_requirements": (
                    state.reflection_result.meets_requirements
                    if state.reflection_result
                    else None
                ),
                "reflection_reasons": (
                    state.reflection_result.reasons
                    if state.reflection_result and state.reflection_result.reasons
                    else []
                ),
                "final_decision": decision,
            },
            "artifact_stats": {
                "top_level_sections": top_level_sections,
                "total_outline_nodes": total_outline_nodes,
            },
            "final_outline": final_outline,
        }

        output_json.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        md_lines = [
            "# SciSage Outline-Only Live Partial Baseline",
            "",
            f"- Query: `{user_query}`",
            f"- Model: `{cfg['model']}`",
            f"- Latency: `{latency}s`",
            f"- Reflection count: `{state.reflection_count}`",
            f"- Meets requirements: `{result['quality_gate']['meets_requirements']}`",
            f"- Final decision: `{decision}`",
            "",
            f"# {final_outline['title']}",
            "",
            final_outline.get("abstract", ""),
            "",
        ]
        for section in final_outline.get("sections", []):
            md_lines.extend(outline_to_markdown(section, depth=1))
            md_lines.append("")
        output_md.write_text("\n".join(md_lines), encoding="utf-8")

        audit = {
            "status": "success",
            "scope_note": "Live partial baseline only; no full paper generation or RAG section writing executed.",
            "artifacts": [
                str(output_json.relative_to(ROOT)),
                str(output_md.relative_to(ROOT)),
            ],
        }
        output_audit.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print(f"SUCCESS {output_json}")
        print(f"SUCCESS {output_md}")
        return 0

    except Exception as exc:
        failure = {
            "status": "failed",
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "experiment_type": "SciSage outline-only live partial baseline",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        output_audit.write_text(
            json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"FAILED {output_audit}")
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
