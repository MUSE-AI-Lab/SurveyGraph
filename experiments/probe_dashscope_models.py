import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List
import sys

from openai import OpenAI

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.lib.config_utils import (
    ensure_dir,
    load_experiment_config,
    model_catalog,
    normalize_openai_base_url,
    output_json,
    timestamp_slug,
)


def _safe_delta_fields(delta: Any) -> Dict[str, Any]:
    fields = {}
    for name in ["role", "content", "reasoning_content"]:
        try:
            value = getattr(delta, name, None)
        except Exception:
            value = None
        if value not in (None, ""):
            fields[name] = value
    return fields


def probe_one_model(client: OpenAI, model_name: str, enable_thinking: bool, prompt: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "model": model_name,
        "enable_thinking": enable_thinking,
        "non_stream": {},
        "stream": {}
    }

    extra_body = {"enable_thinking": True} if enable_thinking else None

    start = time.time()
    try:
        kwargs = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
        }
        if extra_body:
            kwargs["extra_body"] = extra_body
        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message if resp.choices else None
        result["non_stream"] = {
            "ok": True,
            "latency_sec": round(time.time() - start, 3),
            "has_choices": bool(resp.choices),
            "content_preview": (getattr(msg, "content", "") or "")[:300],
            "reasoning_preview": (getattr(msg, "reasoning_content", "") or "")[:300],
            "finish_reason": getattr(resp.choices[0], "finish_reason", None) if resp.choices else None,
            "usage": getattr(resp, "usage", None).model_dump() if getattr(resp, "usage", None) else None,
        }
    except Exception as e:
        result["non_stream"] = {
            "ok": False,
            "latency_sec": round(time.time() - start, 3),
            "error": repr(e),
        }

    start = time.time()
    first_chunks: List[Dict[str, Any]] = []
    stream_reasoning_parts: List[str] = []
    stream_content_parts: List[str] = []
    stream_choice_counts: List[int] = []
    try:
        kwargs = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        if extra_body:
            kwargs["extra_body"] = extra_body
        stream = client.chat.completions.create(**kwargs)
        chunk_count = 0
        for chunk in stream:
            chunk_count += 1
            choices = getattr(chunk, "choices", []) or []
            stream_choice_counts.append(len(choices))
            if chunk_count <= 5:
                first_chunks.append({
                    "chunk_index": chunk_count,
                    "choice_count": len(choices),
                    "delta_fields": _safe_delta_fields(choices[0].delta) if choices else {},
                })
            if not choices:
                continue
            delta = choices[0].delta
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                stream_reasoning_parts.append(reasoning)
            content = getattr(delta, "content", None)
            if content:
                stream_content_parts.append(content)

        result["stream"] = {
            "ok": True,
            "latency_sec": round(time.time() - start, 3),
            "chunk_count": chunk_count,
            "first_chunks": first_chunks,
            "choice_counts": stream_choice_counts[:20],
            "reasoning_preview": "".join(stream_reasoning_parts)[:500],
            "content_preview": "".join(stream_content_parts)[:500],
            "supports_reasoning_content": bool("".join(stream_reasoning_parts)),
        }
    except Exception as e:
        result["stream"] = {
            "ok": False,
            "latency_sec": round(time.time() - start, 3),
            "error": repr(e),
            "first_chunks": first_chunks,
        }

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe DashScope-compatible models used by SurveyGraph experiments")
    parser.add_argument("--config", type=str, default=None, help="实验配置 JSON 路径")
    parser.add_argument("--prompt", type=str, default="请用两句话介绍你自己，并说明你是否支持学术综述生成。", help="探测提示词")
    parser.add_argument("--output-dir", type=str, default=None, help="输出目录")
    args = parser.parse_args()

    config = load_experiment_config(args.config)
    catalog = model_catalog(config)
    base_url = normalize_openai_base_url(config["REMOTE_URL"])
    client = OpenAI(api_key=config["TOKEN"], base_url=base_url)

    output_dir = Path(args.output_dir) if args.output_dir else Path("outputs") / "model_probe" / timestamp_slug()
    ensure_dir(output_dir)

    results = []
    for item in catalog:
        model_name = item["name"]
        enable_thinking = bool(item.get("enable_thinking", False))
        print(f"[probe] {model_name} (thinking={enable_thinking})")
        results.append(probe_one_model(client, model_name, enable_thinking, args.prompt))

    payload = {
        "config_path": config["_config_path"],
        "base_url": base_url,
        "prompt": args.prompt,
        "results": results,
    }
    output_json(output_dir / "probe_results.json", payload)
    print(f"[done] probe results saved to {output_dir / 'probe_results.json'}")


if __name__ == "__main__":
    main()
