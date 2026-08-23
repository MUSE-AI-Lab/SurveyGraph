import argparse
import json
from pathlib import Path
from typing import Any, Dict, List
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.lib.config_utils import (
    ensure_dir,
    get_profile_env,
    load_experiment_config,
    output_json,
    slugify,
)


def ablation_runs(config: Dict[str, Any], profile_name: str) -> List[Dict[str, Any]]:
    topics = config.get("TOPICS", ["Large Language Model Function Calling"])
    max_papers = int(config.get("MAX_PAPERS", 50))
    year_start = int(config.get("YEAR_START", 2020))
    year_end = int(config.get("YEAR_END", 2026))

    toggles = [
        {"name": "full", "args": []},
        {"name": "no_reflection", "args": ["--no-reflection"]},
        {"name": "no_hybrid_outline", "args": ["--no-hybrid-outline"]},
        {"name": "no_global_reflector", "args": ["--no-global-reflector"]},
        {"name": "no_evolutionary", "args": ["--no-evolutionary-analyzer"]},
        {"name": "no_critic_no_refine", "args": ["--no_critic", "--no_refine"]},
    ]

    runs = []
    profile_env = get_profile_env(config, profile_name)
    for topic in topics:
        for toggle in toggles:
            runs.append({
                "name": f"{profile_name}_ablation_{toggle['name']}_{topic}",
                "command": [
                    "python",
                    "tasks/mekg_run.py",
                    "--topic", topic,
                    "--max_papers", str(max_papers),
                    "--year_start", str(year_start),
                    "--year_end", str(year_end),
                ] + toggle["args"],
                "env": profile_env,
                "timeout_sec": 21600
            })
    return runs


def surveygraph_smoke_runs(config: Dict[str, Any], profile_name: str) -> List[Dict[str, Any]]:
    profile_env = get_profile_env(config, profile_name)
    smoke_env = {
        **profile_env,
        # smoke 目标是“稳定走通关键链路”，不是最终公平评测。
        # 真实探测表明属性抽取 prompt 在完整 PDF 下会逼近 / 超过 120s 默认超时；
        # 将 md_text 限制到 10k tokens 后，可把单次响应延迟拉回更稳的范围。
        "MD_TEXT_LENGTH": "10000",
        # 当前百炼文本模型可稳定完成文本 / 表格 / TikZ 视觉链路，
        # 但 AI image generation 会因返回格式不含 image URL 而长时间重试。
        # smoke 先关闭 AI images，优先验证主链路能否完整收尾。
        "ENABLE_AI_IMAGES": "false",
    }
    pdf_candidates = [
        Path("refer/2506.12689v2.pdf"),
        Path("refer/2510.07733v2.pdf"),
        Path("refer/2511.17689v1.pdf"),
    ]
    runs = []
    for pdf in pdf_candidates:
        if not pdf.exists():
            continue
        topic = pdf.stem
        uploaded_files_json = json.dumps([str(pdf.resolve().as_posix())], ensure_ascii=False)
        runs.append({
            "name": f"{profile_name}_smoke_{topic}",
            "command": [
                "python",
                "tasks/mekg_run.py",
                "--topic", topic,
                "--max_papers", "5",
                "--no-arxiv",
                "--no-memgraph",
                "--uploaded-files", uploaded_files_json,
                "--no-evaluation",
                "--no-reflection",
                "--no_critic",
                "--no_refine",
                "--no-hybrid-outline",
                "--no-global-reflector",
                "--no-evolutionary-analyzer",
            ],
            "env": smoke_env,
            "timeout_sec": 7200
        })
    return runs


def eval_replay_runs(config: Dict[str, Any], fast: bool = False) -> List[Dict[str, Any]]:
    eval_model = str(config.get("EVAL_TEXT_MODEL", "MiniMax-M2.5"))
    outputs_root = Path("outputs")
    runs = []
    for task_dir in outputs_root.iterdir():
        if not task_dir.is_dir() or task_dir.name.startswith("."):
            continue
        mekg = task_dir / "mekg" / "mekg_data.json"
        survey = task_dir / "latex" / "survey.tex"
        outline = task_dir / "outline.json"
        if not mekg.exists() or not survey.exists():
            continue
        label = slugify(task_dir.name)
        flags = ["--fast"] if fast else ["--single-model", "--verbose"]
        runs.append({
            "name": f"eval_replay_{label}",
            "command": [
                "python",
                "-m",
                "evaluation.main",
                "--mekg-data", str(mekg),
                "--survey-path", str(survey),
                "--outline", str(outline),
            ] + flags,
            "env": {
                "DEFAULT_CHATAGENT_MODEL": eval_model,
                "ADVANCED_CHATAGENT_MODEL": eval_model,
                "EVAL_TEXT_MODEL": eval_model
            },
            "timeout_sec": 10800
        })
    return runs


def baseline_smoke_runs(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    # 目标是“尽快判断能否启动与卡在哪”，而不是现在就宣称完整公平复现。
    runs = [
        {
            "name": "surveyforge_smoke",
            "command": [
                "python",
                "experiments/tools/baseline_smoke.py",
                "--system", "surveyforge"
            ],
            "env": {},
            "timeout_sec": 3600
        },
        {
            "name": "scisage_smoke",
            "command": [
                "python",
                "experiments/tools/baseline_smoke.py",
                "--system", "scisage"
            ],
            "env": {},
            "timeout_sec": 3600
        },
        {
            "name": "arise_smoke",
            "command": [
                "python",
                "experiments/tools/baseline_smoke.py",
                "--system", "arise"
            ],
            "env": {},
            "timeout_sec": 3600
        }
    ]
    return runs


def build_manifest(suite_name: str, runs: List[Dict[str, Any]], max_parallel: int) -> Dict[str, Any]:
    return {
        "suite_name": suite_name,
        "max_parallel": max_parallel,
        "runs": runs
    }


def slice_manifest(manifest: Dict[str, Any], suite_name: str, run_limit: int, max_parallel: int | None = None) -> Dict[str, Any]:
    return {
        "suite_name": suite_name,
        "max_parallel": max_parallel if max_parallel is not None else min(manifest.get("max_parallel", 1), run_limit),
        "runs": manifest.get("runs", [])[:run_limit]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build experiment manifests for SurveyGraph")
    parser.add_argument("--config", type=str, default=None, help="实验配置 JSON 路径")
    parser.add_argument("--output-dir", type=str, default="experiments/manifests", help="manifest 输出目录")
    args = parser.parse_args()

    config = load_experiment_config(args.config)
    output_dir = ensure_dir(Path(args.output_dir))

    ablation_qwen_manifest = build_manifest("ablation_qwen_suite", ablation_runs(config, "stable_qwen"), max_parallel=2)
    ablation_glm_manifest = build_manifest("ablation_glm_suite", ablation_runs(config, "stable_glm"), max_parallel=2)
    ablation_deepseek_manifest = build_manifest("ablation_deepseek_suite", ablation_runs(config, "stable_deepseek"), max_parallel=2)
    surveygraph_smoke_qwen_manifest = build_manifest("surveygraph_smoke_qwen_suite", surveygraph_smoke_runs(config, "stable_qwen"), max_parallel=1)
    eval_replay_fast_manifest = build_manifest("eval_replay_fast_suite", eval_replay_runs(config, fast=True), max_parallel=2)
    eval_replay_manifest = build_manifest("eval_replay_suite", eval_replay_runs(config, fast=False), max_parallel=1)
    baseline_smoke_manifest = build_manifest("baseline_smoke_suite", baseline_smoke_runs(config), max_parallel=3)

    surveygraph_smoke_glm_manifest = build_manifest("surveygraph_smoke_glm_suite", surveygraph_smoke_runs(config, "stable_glm"), max_parallel=1)
    surveygraph_smoke_deepseek_manifest = build_manifest("surveygraph_smoke_deepseek_suite", surveygraph_smoke_runs(config, "stable_deepseek"), max_parallel=1)

    manifests = {
        "ablation_qwen_suite.generated.json": ablation_qwen_manifest,
        "ablation_glm_suite.generated.json": ablation_glm_manifest,
        "ablation_deepseek_suite.generated.json": ablation_deepseek_manifest,
        "surveygraph_smoke_qwen_suite.generated.json": surveygraph_smoke_qwen_manifest,
        "surveygraph_smoke_qwen_one.generated.json": slice_manifest(
            surveygraph_smoke_qwen_manifest,
            suite_name="surveygraph_smoke_qwen_one",
            run_limit=1,
            max_parallel=1,
        ),
        "surveygraph_smoke_glm_suite.generated.json": surveygraph_smoke_glm_manifest,
        "surveygraph_smoke_glm_one.generated.json": slice_manifest(
            surveygraph_smoke_glm_manifest,
            suite_name="surveygraph_smoke_glm_one",
            run_limit=1,
            max_parallel=1,
        ),
        "surveygraph_smoke_deepseek_suite.generated.json": surveygraph_smoke_deepseek_manifest,
        "surveygraph_smoke_deepseek_one.generated.json": slice_manifest(
            surveygraph_smoke_deepseek_manifest,
            suite_name="surveygraph_smoke_deepseek_one",
            run_limit=1,
            max_parallel=1,
        ),
        "eval_replay_fast_suite.generated.json": eval_replay_fast_manifest,
        "eval_replay_fast_two.generated.json": slice_manifest(
            eval_replay_fast_manifest,
            suite_name="eval_replay_fast_two",
            run_limit=2,
            max_parallel=2,
        ),
        "eval_replay_suite.generated.json": eval_replay_manifest,
        "baseline_smoke_suite.generated.json": baseline_smoke_manifest,
    }

    for filename, payload in manifests.items():
        output_json(output_dir / filename, payload)
        print(f"[built] {output_dir / filename}")


if __name__ == "__main__":
    main()
