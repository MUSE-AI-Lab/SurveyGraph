from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "script_relpath",
    [
        "experiments/external_proxy_retrieval_replay.py",
        "experiments/external_proxy_relation_family_ablation.py",
        "experiments/matched_simpler_graph_baseline_eval.py",
        "experiments/paperreview_minimal_revision.py",
        "experiments/semantic_edge_stratified_protocol_audit.py",
    ],
)
def test_experiment_script_can_run_directly(script_relpath: str) -> None:
    script_path = ROOT / script_relpath
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, (
        f"{script_relpath} failed with code {result.returncode}\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )
