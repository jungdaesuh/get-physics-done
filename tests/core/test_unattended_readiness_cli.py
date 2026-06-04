"""CLI tests for validate unattended-readiness."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import gpd.cli as cli_module
import tests.helpers.cli as cli_helpers
from gpd.adapters import get_adapter, list_runtimes
from gpd.cli import app
from gpd.core.health import (
    CheckStatus,
    DoctorReport,
    HealthCheck,
    HealthSummary,
    UnattendedReadinessCheck,
    UnattendedReadinessResult,
)

runner = cli_helpers.StableCliRunner()


def test_validate_unattended_readiness_requires_runtime() -> None:
    result = runner.invoke(app, ["validate", "unattended-readiness"])

    assert result.exit_code != 0
    assert "--runtime" in cli_helpers.normalize_cli_output(result.output)


@dataclass(frozen=True)
class _UnattendedReadinessCase:
    argv: list[str]
    expected_exit: int
    doctor_report: DoctorReport
    permissions_payload: dict[str, object]
    expected_result: UnattendedReadinessResult
    expected_doctor_kwargs: dict[str, object]
    expected_permissions_kwargs: dict[str, object]
    expected_builder_kwargs: dict[str, object]
    detected_target: Path | None = None
    target_matches_global_call: tuple[str, str] | None = None


def _unattended_permissions_payload(runtime_name: str, target: Path) -> dict[str, object]:
    return {
        "runtime": runtime_name,
        "target": str(target),
        "autonomy": "balanced",
        "readiness": "ready",
        "ready": True,
        "readiness_message": "Runtime permissions are ready for unattended use.",
        "next_step": "",
        "status_scope": "config-only",
        "current_session_verified": False,
    }


def _unattended_result(
    runtime_name: str,
    *,
    install_scope: str,
    target: Path,
    passed: bool = True,
    live_executable_probes: bool = False,
    warnings: list[str] | None = None,
    check: UnattendedReadinessCheck | None = None,
    blocking_conditions: list[str] | None = None,
    next_step: str = "",
) -> UnattendedReadinessResult:
    return UnattendedReadinessResult(
        runtime=runtime_name,
        autonomy="balanced",
        install_scope=install_scope,
        target=str(target),
        readiness="ready",
        ready=True,
        passed=passed,
        readiness_message="Runtime permissions are ready for unattended use.",
        live_executable_probes=live_executable_probes,
        checks=[
            check
            or UnattendedReadinessCheck(
                name="permissions",
                passed=True,
                blocking=False,
                detail="Runtime permissions are ready for unattended use.",
            )
        ],
        blocking_conditions=list(blocking_conditions or []),
        warnings=list(warnings or []),
        next_step=next_step,
        status_scope="config-only",
        current_session_verified=False,
        validated_surface="runtime-surface-test",
    )


def _unattended_case(case_id: str, tmp_path: Path) -> _UnattendedReadinessCase:
    from gpd.specs import SPECS_DIR

    runtime_name = list_runtimes()[0]
    base_argv = ["--cwd", str(tmp_path), "--raw", "validate", "unattended-readiness", "--runtime", runtime_name]
    if case_id == "local":
        target = get_adapter(runtime_name).resolve_target_dir(False, tmp_path)
        scope = "local"
        target_dir_arg = None
        argv = [*base_argv, "--local"]
        doctor_report = DoctorReport(
            overall=CheckStatus.WARN,
            version="0.1.0",
            runtime=runtime_name,
            install_scope=scope,
            target=str(target),
            summary=HealthSummary(ok=1, warn=1, fail=0, total=2),
            checks=[
                HealthCheck(status=CheckStatus.OK, label="Runtime Launcher"),
                HealthCheck(status=CheckStatus.WARN, label="LaTeX Toolchain", warnings=["LaTeX toolchain is partial."]),
            ],
        )
        expected_result = _unattended_result(
            runtime_name, install_scope=scope, target=target, warnings=["LaTeX toolchain is partial."]
        )
        detected_target = None
        target_matches_global_call = None
        expected_exit = 0
        live_executable_probes = False
    elif case_id == "detected-global":
        target = tmp_path / "runtime-global-target"
        scope = "global"
        target_dir_arg = target
        argv = base_argv
        doctor_report = DoctorReport(
            overall=CheckStatus.OK,
            version="0.1.0",
            runtime=runtime_name,
            install_scope=scope,
            target=str(target),
            summary=HealthSummary(ok=2, warn=0, fail=0, total=2),
            checks=[
                HealthCheck(status=CheckStatus.OK, label="Runtime Launcher"),
                HealthCheck(status=CheckStatus.OK, label="Runtime Config Target"),
            ],
        )
        expected_result = _unattended_result(runtime_name, install_scope=scope, target=target)
        detected_target = target
        target_matches_global_call = None
        expected_exit = 0
        live_executable_probes = False
    elif case_id == "explicit-global-failure":
        target_dir = tmp_path / ".gpd-target"
        target = target_dir.resolve(strict=False)
        scope = "global"
        target_dir_arg = target
        argv = [*base_argv, "--target-dir", str(target_dir), "--live-executable-probes"]
        doctor_report = DoctorReport(
            overall=CheckStatus.FAIL,
            version="0.1.0",
            runtime=runtime_name,
            install_scope=scope,
            target=str(target),
            live_executable_probes=True,
            summary=HealthSummary(ok=0, warn=1, fail=1, total=2),
            checks=[
                HealthCheck(
                    status=CheckStatus.FAIL, label="Runtime Launcher", issues=["Runtime launcher not found on PATH"]
                ),
                HealthCheck(status=CheckStatus.WARN, label="LaTeX Toolchain", warnings=["LaTeX toolchain is partial."]),
            ],
        )
        expected_result = _unattended_result(
            runtime_name,
            install_scope=scope,
            target=target,
            passed=False,
            live_executable_probes=True,
            warnings=["LaTeX toolchain is partial."],
            check=UnattendedReadinessCheck(
                name="doctor",
                passed=False,
                blocking=True,
                detail="Runtime launcher not found on PATH",
            ),
            blocking_conditions=["Runtime launcher not found on PATH"],
            next_step="Inspect the runtime-specific doctor output before retrying unattended use.",
        )
        detected_target = None
        target_matches_global_call = (runtime_name, str(target_dir))
        expected_exit = 1
        live_executable_probes = True
    else:
        raise AssertionError(f"unknown unattended-readiness case: {case_id}")

    permissions_payload = _unattended_permissions_payload(runtime_name, target)
    expected_common = {
        "runtime": runtime_name,
        "autonomy": None,
        "install_scope": scope,
        "target_dir": target_dir_arg,
        "doctor_report": doctor_report,
        "permissions_payload": permissions_payload,
        "live_executable_probes": live_executable_probes,
        "validated_surface": "runtime-surface-test",
    }
    return _UnattendedReadinessCase(
        argv=argv,
        expected_exit=expected_exit,
        doctor_report=doctor_report,
        permissions_payload=permissions_payload,
        expected_result=expected_result,
        expected_doctor_kwargs={
            "specs_dir": SPECS_DIR,
            "version": None,
            "runtime": runtime_name,
            "install_scope": scope,
            "target_dir": target_dir_arg,
            "cwd": tmp_path,
            "live_executable_probes": live_executable_probes,
        },
        expected_permissions_kwargs={"runtime": runtime_name, "autonomy": None, "target_dir": str(target)},
        expected_builder_kwargs=expected_common,
        detected_target=detected_target,
        target_matches_global_call=target_matches_global_call,
    )


def _run_unattended_readiness_case(
    monkeypatch: pytest.MonkeyPatch,
    case: _UnattendedReadinessCase,
) -> dict[str, object]:
    captured: dict[str, object] = {}

    def fake_run_doctor(
        *,
        specs_dir: Path | None = None,
        version: str | None = None,
        runtime: str | None = None,
        install_scope: str | None = None,
        target_dir: str | Path | None = None,
        cwd: Path | None = None,
        live_executable_probes: bool = False,
    ) -> DoctorReport:
        captured["doctor_kwargs"] = {
            "specs_dir": specs_dir,
            "version": version,
            "runtime": runtime,
            "install_scope": install_scope,
            "target_dir": target_dir,
            "cwd": cwd,
            "live_executable_probes": live_executable_probes,
        }
        return case.doctor_report

    def fake_permissions_status_payload(
        *, runtime: str | None, autonomy: str | None, target_dir: str | None
    ) -> dict[str, object]:
        captured["permissions_kwargs"] = {"runtime": runtime, "autonomy": autonomy, "target_dir": target_dir}
        return case.permissions_payload

    def fake_build_unattended_readiness_result(**kwargs) -> UnattendedReadinessResult:
        captured["builder_kwargs"] = kwargs
        return case.expected_result

    monkeypatch.setattr("gpd.core.health.run_doctor", fake_run_doctor)
    monkeypatch.setattr("gpd.core.health.build_unattended_readiness_result", fake_build_unattended_readiness_result)
    monkeypatch.setattr(cli_module, "_permissions_status_payload", fake_permissions_status_payload)
    monkeypatch.setattr(cli_module, "_validated_runtime_surface", lambda cwd=None: "runtime-surface-test")

    if case.detected_target is not None:
        with patch(
            "gpd.hooks.runtime_detect.detect_runtime_install_target",
            return_value=SimpleNamespace(config_dir=case.detected_target, install_scope="global"),
        ):
            result = runner.invoke(app, case.argv)
    elif case.target_matches_global_call is not None:
        with patch("gpd.cli._target_dir_matches_global", return_value=True) as mock_matches_global:
            result = runner.invoke(app, case.argv)
        mock_matches_global.assert_called_once_with(
            *case.target_matches_global_call,
            action="validate unattended-readiness",
        )
    else:
        result = runner.invoke(app, case.argv)

    assert result.exit_code == case.expected_exit
    assert json.loads(result.output) == asdict(case.expected_result)
    return captured


@pytest.mark.parametrize("case_id", ["local", "detected-global", "explicit-global-failure"])
def test_validate_unattended_readiness_wires_runtime_scope_through_health_builder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case_id: str,
) -> None:
    case = _unattended_case(case_id, tmp_path)
    captured = _run_unattended_readiness_case(monkeypatch, case)

    assert captured["doctor_kwargs"] == case.expected_doctor_kwargs
    assert captured["permissions_kwargs"] == case.expected_permissions_kwargs
    assert captured["builder_kwargs"] == case.expected_builder_kwargs
