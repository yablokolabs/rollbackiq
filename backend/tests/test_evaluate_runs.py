"""Tests for the repeated-run evaluation summary.

The summary is the source of the success rate and the false-positive count in
the evaluation document, so the cases that matter are the ones that could
inflate those numbers: a run that never produced a verification, a run the
verifier refused, and a healthy control on which the detector fired.

The run directories are built from the artifacts of a real recorded run.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
RECORDED_RUN = REPO_ROOT / "evidence" / "demo-run"


def _load_script():
    spec = importlib.util.spec_from_file_location("evaluate_runs", SCRIPTS / "evaluate_runs.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["evaluate_runs"] = module
    spec.loader.exec_module(module)
    return module


def _recorded_run(root: Path, name: str, exit_code: int = 0) -> Path:
    target = root / name
    shutil.copytree(RECORDED_RUN, target)
    (target / "run.json").write_text(json.dumps({"exit_code": exit_code, "wall_seconds": 31.5}))
    return target


def _control(root: Path, name: str, triggered: bool) -> Path:
    target = root / name
    target.mkdir()
    (target / "ci-detection.json").write_text(json.dumps({"triggered": triggered, "windows": []}))
    (target / "run.json").write_text(json.dumps({"exit_code": 0 if triggered else 1, "wall_seconds": 9.0}))
    return target


def test_a_recorded_recovery_counts_as_one_success_with_its_measured_values(tmp_path):
    _recorded_run(tmp_path, "run-1")

    summary = _load_script().summarise(tmp_path)

    lifecycle = summary["lifecycle"]
    assert lifecycle["runs"] == 1
    assert lifecycle["recovered"] == 1
    assert lifecycle["failed"] == []
    recorded = json.loads((RECORDED_RUN / "ci-detection.json").read_text())
    assert lifecycle["per_run"][0]["p95_ratio_at_detection"] == recorded["p95_ratio"]
    assert lifecycle["per_run"][0]["rollback_to_verified_seconds"] > 0


def test_a_run_without_a_verification_is_a_failure_not_a_success(tmp_path):
    _recorded_run(tmp_path, "run-1")
    broken = _recorded_run(tmp_path, "run-2", exit_code=1)
    (broken / "verification.json").unlink()

    lifecycle = _load_script().summarise(tmp_path)["lifecycle"]

    assert lifecycle["runs"] == 2
    assert lifecycle["recovered"] == 1
    assert lifecycle["success_rate"] == 0.5
    assert [failure["run"] for failure in lifecycle["failed"]] == ["run-2"]
    assert "verification.json" in lifecycle["failed"][0]["reason"]


def test_a_refused_verification_is_a_failure_and_keeps_the_verifier_reasons(tmp_path):
    refused = _recorded_run(tmp_path, "run-1", exit_code=1)
    record = json.loads((refused / "verification.json").read_text())
    record["result"]["recovered"] = False
    record["result"]["reasons"] = ["stabilization window 1.1s is shorter than 3.0s"]
    (refused / "verification.json").write_text(json.dumps(record))

    lifecycle = _load_script().summarise(tmp_path)["lifecycle"]

    assert lifecycle["recovered"] == 0
    assert "stabilization window" in lifecycle["failed"][0]["reason"]


def test_a_recovery_from_a_non_independent_window_is_not_counted(tmp_path):
    run = _recorded_run(tmp_path, "run-1")
    record = json.loads((run / "verification.json").read_text())
    record["result"]["independent"] = False
    (run / "verification.json").write_text(json.dumps(record))

    lifecycle = _load_script().summarise(tmp_path)["lifecycle"]

    assert lifecycle["recovered"] == 0
    assert "independent" in lifecycle["failed"][0]["reason"]


def test_a_detection_on_a_healthy_control_is_a_false_positive(tmp_path):
    _control(tmp_path, "control-1", triggered=False)
    _control(tmp_path, "control-2", triggered=True)

    controls = _load_script().summarise(tmp_path)["controls"]

    assert controls["runs"] == 2
    assert controls["false_positives"] == 1


def test_a_control_without_a_detection_record_is_inconclusive_not_clean(tmp_path):
    _control(tmp_path, "control-1", triggered=False)
    empty = tmp_path / "control-2"
    empty.mkdir()

    controls = _load_script().summarise(tmp_path)["controls"]

    assert controls["runs"] == 2
    assert controls["false_positives"] == 0
    assert controls["inconclusive"] == ["control-2"]
