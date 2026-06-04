"""Tests for install and unattended-readiness support helpers."""

from __future__ import annotations

from pathlib import Path

from gpd.core.health import (
    CheckStatus,
    DoctorReport,
    HealthCheck,
    HealthSummary,
    UnattendedReadinessCheck,
    UnattendedReadinessResult,
)
from gpd.core.install_readiness_support import (
    build_unattended_readiness,
    doctor_advisory_messages,
    doctor_blocker_messages,
    run_install_readiness_preflight,
)
from tests.runtime_test_support import PRIMARY_RUNTIME, runtime_target_dir


def _doctor_report(*, overall: CheckStatus, checks: list[HealthCheck]) -> DoctorReport:
    return DoctorReport(
        overall=overall,
        mode="runtime-readiness",
        summary=HealthSummary(
            ok=sum(1 for check in checks if check.status == CheckStatus.OK),
            warn=sum(1 for check in checks if check.status == CheckStatus.WARN),
            fail=sum(1 for check in checks if check.status == CheckStatus.FAIL),
            total=len(checks),
        ),
        checks=checks,
    )


def test_doctor_message_extractors_dedupe_and_fallback_to_labels() -> None:
    report = _doctor_report(
        overall=CheckStatus.FAIL,
        checks=[
            HealthCheck(status=CheckStatus.FAIL, label="Runtime Launcher", issues=["missing launcher"]),
            HealthCheck(status=CheckStatus.FAIL, label="Runtime Launcher", issues=["missing launcher"]),
            HealthCheck(status=CheckStatus.FAIL, label="Runtime Config Target"),
            HealthCheck(status=CheckStatus.WARN, label="LaTeX", warnings=["partial tex", "partial tex"]),
        ],
    )

    assert doctor_blocker_messages(report) == [
        "missing launcher",
        "Runtime Config Target: readiness check failed.",
    ]
    assert doctor_advisory_messages(report) == ["partial tex"]


def test_run_install_readiness_preflight_treats_same_runtime_incomplete_target_as_advisory(
    tmp_path: Path,
) -> None:
    runtime_name = PRIMARY_RUNTIME
    report = _doctor_report(
        overall=CheckStatus.FAIL,
        checks=[
            HealthCheck(
                status=CheckStatus.FAIL,
                label="Runtime Config Target",
                issues=["Install target is incomplete."],
                details={
                    "install_state": "owned_incomplete",
                    "target_assessment": {
                        "manifest_runtime": runtime_name,
                        "expected_runtime": runtime_name,
                    },
                },
            )
        ],
    )

    failures, advisories = run_install_readiness_preflight(
        [runtime_name],
        install_scope="local",
        target_dir=runtime_target_dir(tmp_path, runtime_name),
        cwd=tmp_path,
        specs_dir=tmp_path / "specs",
        run_doctor=lambda **kwargs: report,
    )

    assert failures == []
    assert advisories == {runtime_name: ["Install target is incomplete."]}


def test_build_unattended_readiness_uses_detected_install_target_and_injected_surface(
    tmp_path: Path,
) -> None:
    runtime_name = PRIMARY_RUNTIME
    detected_target = tmp_path / "detected-global"
    doctor_report = _doctor_report(
        overall=CheckStatus.OK,
        checks=[HealthCheck(status=CheckStatus.OK, label="Runtime Launcher")],
    )
    expected_result = UnattendedReadinessResult(
        runtime=runtime_name,
        autonomy="balanced",
        install_scope="global",
        target=str(detected_target),
        readiness="ready",
        ready=True,
        passed=True,
        readiness_message="ready",
        live_executable_probes=True,
        checks=[UnattendedReadinessCheck(name="permissions", passed=True, blocking=False, detail="ready")],
        blocking_conditions=[],
        warnings=[],
        next_step="",
        status_scope="config-only",
        current_session_verified=False,
        validated_surface="runtime-surface-test",
    )
    captured: dict[str, object] = {}

    def fake_run_doctor(**kwargs):
        captured["doctor"] = kwargs
        return doctor_report

    def fake_permissions_status_payload(**kwargs):
        captured["permissions"] = kwargs
        return {
            "runtime": runtime_name,
            "target": str(detected_target),
            "autonomy": "balanced",
            "readiness": "ready",
            "ready": True,
            "readiness_message": "ready",
            "status_scope": "config-only",
            "current_session_verified": False,
        }

    def fake_build_unattended_readiness_result(**kwargs):
        captured["builder"] = kwargs
        return expected_result

    result = build_unattended_readiness(
        runtime=runtime_name,
        autonomy="balanced",
        global_install=False,
        local_install=False,
        target_dir=None,
        live_executable_probes=True,
        cwd=tmp_path,
        normalize_runtime_selection=lambda runtimes, **kwargs: list(runtimes),
        validated_surface="runtime-surface-test",
        specs_dir=tmp_path / "specs",
        resolve_detected_runtime_target_func=lambda runtime, cwd: (detected_target, "global"),
        run_doctor=fake_run_doctor,
        permissions_status_payload_func=fake_permissions_status_payload,
        build_unattended_readiness_result=fake_build_unattended_readiness_result,
    )

    assert result is expected_result
    assert captured["doctor"]["install_scope"] == "global"
    assert captured["doctor"]["target_dir"] == detected_target
    assert captured["doctor"]["live_executable_probes"] is True
    assert captured["permissions"]["target_dir"] == str(detected_target)
    assert captured["builder"]["validated_surface"] == "runtime-surface-test"
