from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from gpd.adapters import get_adapter, iter_runtime_descriptors
from gpd.core.public_surface_contract import beginner_onboarding_hub_url
from gpd.core.surface_phrases import recovery_ladder_note
from scripts.render_bootstrap_installer_metadata import build_installer_metadata
from tests.doc_surface_contracts import (
    assert_install_summary_runtime_follow_up_contract,
    assert_recovery_ladder_contract,
)
from tests.lifecycle_contract_test_support import (
    assert_forbidden_contract as _assert_forbidden,
)
from tests.lifecycle_contract_test_support import (
    assert_machine_contract as _assert_machine,
)
from tests.lifecycle_contract_test_support import (
    assert_public_contract as _assert_public,
)
from tests.runtime_test_support import PRIMARY_RUNTIME, runtime_install_flag, runtime_with_multiword_alias

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_JSON = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
PYPROJECT = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
PACKAGE_VERSION = str(PACKAGE_JSON["version"])
PYTHON_PACKAGE_VERSION = str(PACKAGE_JSON["gpdPythonVersion"])

REPO_GIT_URL = str(PACKAGE_JSON["repository"]["url"]).removeprefix("git+").rstrip("/")
if not REPO_GIT_URL.endswith(".git"):
    REPO_GIT_URL = f"{REPO_GIT_URL}.git"
REPO_BASE_URL = REPO_GIT_URL.removesuffix(".git")

PYPI_SPEC = f"get-physics-done=={PYTHON_PACKAGE_VERSION}"
TAG_ARCHIVE_SPEC = f"{REPO_BASE_URL}/archive/refs/tags/v{PYTHON_PACKAGE_VERSION}.tar.gz"
MAIN_ARCHIVE_SPEC = f"{REPO_BASE_URL}/archive/refs/heads/main.tar.gz"
TAG_HTTPS_GIT_SPEC = f"git+{REPO_GIT_URL}@v{PYTHON_PACKAGE_VERSION}"
MAIN_HTTPS_GIT_SPEC = f"git+{REPO_GIT_URL}@main"
_RUNTIME_DESCRIPTORS = iter_runtime_descriptors()
_RUNTIME_ADAPTERS = {
    descriptor.runtime_name: get_adapter(descriptor.runtime_name) for descriptor in _RUNTIME_DESCRIPTORS
}
_RUNTIME_NAMES = tuple(descriptor.runtime_name for descriptor in _RUNTIME_DESCRIPTORS)
_RUNTIME_INSTALL_FLAGS = tuple(descriptor.install_flag for descriptor in _RUNTIME_DESCRIPTORS)
_RUNTIME_DISPLAY_NAMES = {name: adapter.display_name for name, adapter in _RUNTIME_ADAPTERS.items()}
_RUNTIME_LAUNCH_COMMANDS = {name: adapter.launch_command for name, adapter in _RUNTIME_ADAPTERS.items()}
_RUNTIME_CONFIG_DIR_NAMES = {name: adapter.config_dir_name for name, adapter in _RUNTIME_ADAPTERS.items()}
_RUNTIME_HELP_COMMANDS = {name: adapter.help_command for name, adapter in _RUNTIME_ADAPTERS.items()}
_RUNTIME_START_COMMANDS = {name: adapter.format_command("start") for name, adapter in _RUNTIME_ADAPTERS.items()}
_RUNTIME_TOUR_COMMANDS = {name: adapter.format_command("tour") for name, adapter in _RUNTIME_ADAPTERS.items()}
_RUNTIME_MAP_RESEARCH_COMMANDS = {name: adapter.map_research_command for name, adapter in _RUNTIME_ADAPTERS.items()}
_RUNTIME_RESUME_WORK_COMMANDS = {
    name: adapter.format_command("resume-work") for name, adapter in _RUNTIME_ADAPTERS.items()
}
_RUNTIME_SUGGEST_NEXT_COMMANDS = {
    name: adapter.format_command("suggest-next") for name, adapter in _RUNTIME_ADAPTERS.items()
}
_RUNTIME_PAUSE_WORK_COMMANDS = {
    name: adapter.format_command("pause-work") for name, adapter in _RUNTIME_ADAPTERS.items()
}
_RUNTIME_HELP_EXAMPLE_DESCRIPTORS = tuple(
    descriptor for descriptor in _RUNTIME_DESCRIPTORS if descriptor.installer_help_example_scope is not None
)
_RUNTIME_DESCRIPTORS_WITH_GLOBAL_ENV_OVERRIDE = tuple(
    descriptor
    for descriptor in _RUNTIME_DESCRIPTORS
    if descriptor.global_config.env_var or descriptor.global_config.env_dir_var or descriptor.global_config.env_file_var
)
_CODEX_RUNTIME_NAME = PRIMARY_RUNTIME
_CLAUDE_RUNTIME_NAME, _CLAUDE_RUNTIME_ALIAS = runtime_with_multiword_alias(exclude=(_CODEX_RUNTIME_NAME,))
_OPENCODE_RUNTIME_NAME, _OPENCODE_RUNTIME_ALIAS = runtime_with_multiword_alias(
    exclude=(_CODEX_RUNTIME_NAME, _CLAUDE_RUNTIME_NAME)
)
_BEGINNER_ONBOARDING_HUB_URL = beginner_onboarding_hub_url()
_CODEX_INSTALL_FLAG = runtime_install_flag(_CODEX_RUNTIME_NAME)
_CLAUDE_INSTALL_FLAG = runtime_install_flag(_CLAUDE_RUNTIME_NAME)
_RUNTIME_RECOVERY_LADDER_TEMPLATE = recovery_ladder_note(
    resume_work_phrase="{resume_work}",
    suggest_next_phrase="{suggest_next}",
    pause_work_phrase="{pause_work}",
)
_BOOTSTRAP_INSTALLER_METADATA_JSON_ENV = "GPD_BOOTSTRAP_TEST_INSTALLER_METADATA_JSON"
MANAGED_HOME_DIRNAME = ".gpd"
_BOOTSTRAP_INSTALLER_METADATA_PAYLOAD = build_installer_metadata()
_BOOTSTRAP_INSTALLER_METADATA_ENV = {
    _BOOTSTRAP_INSTALLER_METADATA_JSON_ENV: json.dumps(
        _BOOTSTRAP_INSTALLER_METADATA_PAYLOAD,
        sort_keys=True,
        separators=(",", ":"),
    )
}


def _render_runtime_recovery_ladder(runtime: str) -> str:
    return _RUNTIME_RECOVERY_LADDER_TEMPLATE.format(
        resume_work=f"`{_RUNTIME_RESUME_WORK_COMMANDS[runtime]}`",
        suggest_next=f"`{_RUNTIME_SUGGEST_NEXT_COMMANDS[runtime]}`",
        pause_work=f"`{_RUNTIME_PAUSE_WORK_COMMANDS[runtime]}`",
    )


def _assert_single_runtime_next_steps(output: str, runtime: str) -> None:
    ordered_patterns = (
        re.escape("After install"),
        re.escape(f"Docs hub: {_BEGINNER_ONBOARDING_HUB_URL}"),
        re.escape(
            f"Next: open {_RUNTIME_DISPLAY_NAMES[runtime]} in this folder, then run {_RUNTIME_START_COMMANDS[runtime]}."
        ),
        re.escape("Diagnostics: use gpd --help for local diagnostics and later setup."),
    )
    cursor = 0
    for pattern in ordered_patterns:
        match = re.search(pattern, output[cursor:], re.S)
        assert match, output
        cursor += match.end()

    _assert_install_summary_semantic_contract(
        output,
    )
    assert "Runtime surface:" not in output
    assert "First-run order" not in output
    assert "Recovery ladder:" not in output
    assert _RUNTIME_HELP_COMMANDS[runtime] not in output
    assert _RUNTIME_TOUR_COMMANDS[runtime] not in output
    assert _RUNTIME_MAP_RESEARCH_COMMANDS[runtime] not in output
    assert _RUNTIME_RESUME_WORK_COMMANDS[runtime] not in output
    assert _RUNTIME_SUGGEST_NEXT_COMMANDS[runtime] not in output
    assert _RUNTIME_PAUSE_WORK_COMMANDS[runtime] not in output


def _assert_multi_runtime_next_steps_line(output: str, runtime: str) -> None:
    pattern = re.compile(
        rf"- {re.escape(_RUNTIME_DISPLAY_NAMES[runtime])}: "
        rf"{re.escape(_RUNTIME_START_COMMANDS[runtime])}",
        re.S,
    )
    assert pattern.search(output), output
    assert _RUNTIME_HELP_COMMANDS[runtime] not in output
    assert _RUNTIME_TOUR_COMMANDS[runtime] not in output
    assert _RUNTIME_MAP_RESEARCH_COMMANDS[runtime] not in output
    assert _RUNTIME_RESUME_WORK_COMMANDS[runtime] not in output


def _assert_install_summary_semantic_contract(
    output: str,
    *,
    runtime_help_fragments: tuple[str, ...] = (),
) -> None:
    assert_install_summary_runtime_follow_up_contract(output, runtime_help_fragments=runtime_help_fragments)


def _assert_bootstrap_concise_after_install_guidance(output: str) -> None:
    assert "Startup checklist" not in output
    assert "Beginner Onboarding Hub:" not in output
    assert output.count("After install") == 1
    assert "First-run order" not in output
    assert "Recovery ladder:" not in output
    assert f"Docs hub: {_BEGINNER_ONBOARDING_HUB_URL}" in output
    assert "Runtime surface:" not in output
    assert "Diagnostics: use gpd --help for local diagnostics and later setup." in output


def _assert_single_runtime_bootstrap_concise_line(output: str, runtime: str) -> None:
    assert (
        f"Next: open {_RUNTIME_DISPLAY_NAMES[runtime]} in this folder, then run {_RUNTIME_START_COMMANDS[runtime]}."
    ) in output


def _assert_multi_runtime_bootstrap_concise_lines(output: str, runtimes: tuple[str, ...]) -> None:
    assert "Next: choose a runtime and run its GPD start command:" in output
    for runtime in runtimes:
        assert (f"- {_RUNTIME_DISPLAY_NAMES[runtime]}: {_RUNTIME_START_COMMANDS[runtime]}") in output


def _assert_in_order(content: str, fragments: tuple[str, ...]) -> None:
    positions = [content.index(fragment) for fragment in fragments]
    assert positions == sorted(positions)


def test_version_consistency():
    """Release metadata and the bootstrap's Python pin must match."""
    assert PACKAGE_VERSION == PYTHON_PACKAGE_VERSION == str(PYPROJECT["project"]["version"])


def test_runtime_recovery_ladder_template_stays_in_sync_with_shared_surface_phrase() -> None:
    for runtime in _RUNTIME_NAMES:
        ladder_note = _render_runtime_recovery_ladder(runtime)

        assert ladder_note == recovery_ladder_note(
            resume_work_phrase=f"`{_RUNTIME_RESUME_WORK_COMMANDS[runtime]}`",
            suggest_next_phrase=f"`{_RUNTIME_SUGGEST_NEXT_COMMANDS[runtime]}`",
            pause_work_phrase=f"`{_RUNTIME_PAUSE_WORK_COMMANDS[runtime]}`",
        )
        assert_recovery_ladder_contract(
            ladder_note,
            resume_work_fragments=(f"`{_RUNTIME_RESUME_WORK_COMMANDS[runtime]}`",),
            suggest_next_fragments=(f"`{_RUNTIME_SUGGEST_NEXT_COMMANDS[runtime]}`",),
            pause_work_fragments=(f"`{_RUNTIME_PAUSE_WORK_COMMANDS[runtime]}`",),
        )


def _write_fake_launcher(script_path: Path, command_name: str) -> None:
    script = f"""#!{sys.executable}
import sys

if sys.argv[1:] == ["--version"]:
    print({command_name!r} + " 1.0.0")

raise SystemExit(0)
"""
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script, encoding="utf-8")
    script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_fake_python(script_path: Path, log_path: Path, version_text: str = "Python 3.13.2") -> None:
    script = f"""#!{sys.executable}
import json
import os
import pathlib
import shutil
import stat
import sys

LOG_PATH = pathlib.Path({str(log_path)!r})
FAIL_PYPI = os.environ.get("FAKE_PIP_FAIL_PYPI") == "1"
FAIL_TAG_ARCHIVE = os.environ.get("FAKE_PIP_FAIL_TAG_ARCHIVE") == "1"
FAIL_BRANCH_ARCHIVE = os.environ.get("FAKE_PIP_FAIL_BRANCH_ARCHIVE") == "1"
FAIL_TAG_GIT = os.environ.get("FAKE_PIP_FAIL_TAG_GIT") == "1"
FAIL_MAIN_GIT = os.environ.get("FAKE_PIP_FAIL_MAIN_GIT") == "1"
EMIT_PIP_SUCCESS_NOISE = os.environ.get("FAKE_PIP_SUCCESS_NOISE") == "1"
FAIL_RUNTIME_INSTALL_RUNTIMES = {{
    token.strip().lower()
    for token in os.environ.get("FAKE_RUNTIME_INSTALL_FAIL_RUNTIMES", "").split(",")
    if token.strip()
}}
INCOMPLETE_TARGET_RUNTIMES = {{
    token.strip().lower()
    for token in os.environ.get("FAKE_INCOMPLETE_TARGET_RUNTIMES", "").split(",")
    if token.strip()
}}
PYPI_SPEC = {PYPI_SPEC!r}
TAG_ARCHIVE_SPEC = {TAG_ARCHIVE_SPEC!r}
MAIN_ARCHIVE_SPEC = {MAIN_ARCHIVE_SPEC!r}
TAG_HTTPS_GIT_SPEC = {TAG_HTTPS_GIT_SPEC!r}
MAIN_HTTPS_GIT_SPEC = {MAIN_HTTPS_GIT_SPEC!r}
RUNTIME_LABELS = {_RUNTIME_DISPLAY_NAMES!r}
LAUNCH_COMMANDS = {_RUNTIME_LAUNCH_COMMANDS!r}
CONFIG_DIR_NAMES = {_RUNTIME_CONFIG_DIR_NAMES!r}
HELP_COMMANDS = {_RUNTIME_HELP_COMMANDS!r}
START_COMMANDS = {_RUNTIME_START_COMMANDS!r}
TOUR_COMMANDS = {_RUNTIME_TOUR_COMMANDS!r}
MAP_RESEARCH_COMMANDS = {_RUNTIME_MAP_RESEARCH_COMMANDS!r}
RESUME_WORK_COMMANDS = {_RUNTIME_RESUME_WORK_COMMANDS!r}
SUGGEST_NEXT_COMMANDS = {_RUNTIME_SUGGEST_NEXT_COMMANDS!r}
PAUSE_WORK_COMMANDS = {_RUNTIME_PAUSE_WORK_COMMANDS!r}
ALL_RUNTIMES = {_RUNTIME_NAMES!r}


def format_runtime_list(runtimes: list[str]) -> str:
    labels = [RUNTIME_LABELS[runtime] for runtime in runtimes]
    if not labels:
        return "no runtimes"
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{{labels[0]}} and {{labels[1]}}"
    return f"{{', '.join(labels[:-1])}}, and {{labels[-1]}}"


def selected_runtimes(argv: list[str]) -> list[str]:
    if "--all" in argv:
        return list(ALL_RUNTIMES)
    runtimes = [arg for arg in argv if arg in RUNTIME_LABELS]
    runtime_override = option_value(argv, "--runtime")
    if runtime_override and runtime_override in RUNTIME_LABELS:
        runtimes.append(runtime_override)
    return list(dict.fromkeys(runtimes))


def selected_scope(argv: list[str]) -> str:
    return "global" if "--global" in argv else "local"


def recovery_ladder_for_runtime(runtime: str) -> str:
    return {_RUNTIME_RECOVERY_LADDER_TEMPLATE!r}.format(
        resume_work=f"`{{RESUME_WORK_COMMANDS[runtime]}}`",
        suggest_next=f"`{{SUGGEST_NEXT_COMMANDS[runtime]}}`",
        pause_work=f"`{{PAUSE_WORK_COMMANDS[runtime]}}`",
    )


def option_value(argv: list[str], flag: str) -> str | None:
    try:
        index = argv.index(flag)
    except ValueError:
        return None
    if index + 1 >= len(argv):
        return None
    return argv[index + 1]


def nearest_existing_ancestor(path: pathlib.Path) -> pathlib.Path:
    candidate = path.expanduser().resolve()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def doctor_target(runtime: str, scope: str, explicit_target: str | None) -> pathlib.Path:
    if explicit_target:
        return pathlib.Path(explicit_target).expanduser().resolve()
    if scope == "global":
        return pathlib.Path(os.path.expanduser("~")).resolve() / CONFIG_DIR_NAMES[runtime]
    return pathlib.Path.cwd().resolve() / CONFIG_DIR_NAMES[runtime]


def doctor_check_runtime_launcher(runtime: str) -> dict[str, object]:
    launch_command = LAUNCH_COMMANDS[runtime]
    launch_executable = launch_command.split()[0] if launch_command.split() else launch_command
    launcher_path = shutil.which(launch_executable) if launch_executable else None
    issues = [] if launcher_path else [f"{{launch_executable or launch_command}} not found on PATH"]
    warnings = [] if launcher_path else [f"Install or expose {{RUNTIME_LABELS[runtime]}} before running GPD there."]
    return {{
        "status": "ok" if launcher_path else "fail",
        "label": "Runtime Launcher",
        "details": {{
            "runtime": runtime,
            "display_name": RUNTIME_LABELS[runtime],
            "launch_command": launch_command,
            "launch_executable": launch_executable or None,
            "launcher_path": launcher_path,
        }},
        "issues": issues,
        "warnings": warnings,
    }}


def doctor_check_runtime_target(target: pathlib.Path) -> dict[str, object]:
    resolved = target.expanduser().resolve()
    runtime = os.environ.get("FAKE_CURRENT_DOCTOR_RUNTIME", "")
    details: dict[str, object] = {{
        "target": str(resolved),
        "exists": resolved.exists(),
    }}
    issues: list[str] = []
    warnings: list[str] = []

    if runtime.lower() in INCOMPLETE_TARGET_RUNTIMES:
        details["install_state"] = "owned_incomplete"
        issues.append(f"{{resolved}} contains an incomplete owned GPD install")
        return {{
            "status": "fail",
            "label": "Runtime Config Target",
            "details": details,
            "issues": issues,
            "warnings": warnings,
        }}

    if resolved.exists() and not resolved.is_dir():
        issues.append(f"{{resolved}} exists but is not a directory")
        details["probe_dir"] = str(resolved)
        return {{
            "status": "fail",
            "label": "Runtime Config Target",
            "details": details,
            "issues": issues,
            "warnings": warnings,
        }}

    probe_dir = resolved if resolved.exists() else nearest_existing_ancestor(resolved.parent)
    details["probe_dir"] = str(probe_dir)
    if not probe_dir.exists():
        issues.append(f"No existing parent directory found for {{resolved}}")
    elif not probe_dir.is_dir():
        issues.append(f"{{probe_dir}} is not a directory")
    elif not os.access(probe_dir, os.W_OK | os.X_OK):
        issues.append(f"{{probe_dir}} is not writable")
    elif not resolved.exists():
        warnings.append(f"{{resolved}} does not exist yet; GPD will create it during install.")

    return {{
        "status": "fail" if issues else "ok",
        "label": "Runtime Config Target",
        "details": details,
        "issues": issues,
        "warnings": warnings,
    }}


def doctor_check_provider_auth(runtime: str, target: pathlib.Path) -> dict[str, object]:
    launch_command = LAUNCH_COMMANDS[runtime]
    return {{
        "status": "ok",
        "label": "Provider/Auth Guidance",
        "details": {{
            "runtime": runtime,
            "launch_command": launch_command,
            "target": str(target.expanduser().resolve()),
            "verification": "manual",
        }},
        "issues": [],
        "warnings": [
            (
                f"GPD does not verify provider credentials automatically for {{runtime}}. "
                f"Launch `{{launch_command}}` once and confirm your account or API provider is configured."
            )
        ],
    }}


def doctor_report(argv: list[str]) -> dict[str, object]:
    runtime = option_value(argv, "--runtime")
    os.environ["FAKE_CURRENT_DOCTOR_RUNTIME"] = runtime or ""
    scope = selected_scope(argv)
    target = doctor_target(runtime, scope, option_value(argv, "--target-dir"))
    checks = [
        {{
            "status": "ok",
            "label": "Python Runtime",
            "details": {{
                "version": {version_text!r}.replace("Python ", ""),
                "venv_available": True,
                "active_virtualenv": "venv" in pathlib.Path(sys.argv[0]).parts,
                "python_executable": sys.executable,
            }},
            "issues": [],
            "warnings": [],
        }},
        {{
            "status": "ok",
            "label": "Package Imports",
            "details": {{"modules_checked": 4}},
            "issues": [],
            "warnings": [],
        }},
        doctor_check_runtime_launcher(runtime),
        doctor_check_runtime_target(target),
        {{
            "status": "ok",
            "label": "Bootstrap Network Access",
            "details": {{"skipped": True, "reason": "disabled by GPD_BOOTSTRAP_DISABLE_NETWORK_PROBES"}},
            "issues": [],
            "warnings": [],
        }},
        doctor_check_provider_auth(runtime, target),
    ]
    ok_count = sum(1 for check in checks if check["status"] == "ok")
    warn_count = sum(1 for check in checks if check["status"] == "warn")
    fail_count = sum(1 for check in checks if check["status"] == "fail")
    overall = "fail" if fail_count > 0 else "warn" if warn_count > 0 else "ok"
    return {{
        "overall": overall,
        "version": {PYTHON_PACKAGE_VERSION!r},
        "mode": "runtime-readiness",
        "runtime": runtime,
        "install_scope": scope,
        "target": str(target),
        "summary": {{
            "ok": ok_count,
            "warn": warn_count,
            "fail": fail_count,
            "total": len(checks),
        }},
        "checks": checks,
    }}


def record() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {{
        "argv": sys.argv[1:],
        "exe": sys.argv[0],
        "managed": "venv" in pathlib.Path(sys.argv[0]).parts,
    }}
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\\n")


def write_managed_python(target: pathlib.Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(pathlib.Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


args = sys.argv[1:]

if args == ["--version"]:
    print({version_text!r})
    record()
    raise SystemExit(0)

if args == ["-m", "venv", "--help"]:
    print("usage: venv")
    record()
    raise SystemExit(0)

if args[:2] == ["-m", "venv"] and len(args) == 3:
    target = pathlib.Path(args[2])
    bin_dir = target / ("Scripts" if os.name == "nt" else "bin")
    for name in ("python", "python3"):
        write_managed_python(bin_dir / name)
    record()
    raise SystemExit(0)

if args == ["-m", "pip", "--version"] and "venv" not in pathlib.Path(sys.argv[0]).parts:
    record()
    raise SystemExit(1)

if args == ["-m", "pip", "--version"]:
    print("pip 26.0 from managed environment")
    record()
    raise SystemExit(0)

if args == ["-m", "ensurepip", "--upgrade"]:
    record()
    raise SystemExit(0)

if args[:4] == ["-m", "pip", "install", "--upgrade"]:
    target = args[-1]
    if FAIL_PYPI and target == PYPI_SPEC:
        record()
        sys.stderr.write("ERROR: No matching distribution found for get-physics-done\\n")
        raise SystemExit(1)
    if FAIL_TAG_ARCHIVE and target == TAG_ARCHIVE_SPEC:
        record()
        sys.stderr.write("ERROR: HTTP error 404 while getting tagged archive\\n")
        raise SystemExit(1)
    if FAIL_BRANCH_ARCHIVE and target == MAIN_ARCHIVE_SPEC:
        record()
        sys.stderr.write("ERROR: HTTP error 404 while getting branch archive\\n")
        raise SystemExit(1)
    if FAIL_TAG_GIT and target == TAG_HTTPS_GIT_SPEC:
        record()
        sys.stderr.write(f"ERROR: git checkout could not find tag v{PYTHON_PACKAGE_VERSION}\\n")
        raise SystemExit(1)
    if FAIL_MAIN_GIT and target == MAIN_HTTPS_GIT_SPEC:
        record()
        sys.stderr.write("ERROR: git checkout could not resolve branch main\\n")
        raise SystemExit(1)
    if EMIT_PIP_SUCCESS_NOISE:
        print("Requirement already satisfied: noisy-package==1.0.0")
    record()
    raise SystemExit(0)

if args[:4] == ["-m", "gpd.cli", "--raw", "doctor"]:
    print(json.dumps(doctor_report(args)))
    record()
    raise SystemExit(0)

if args[:3] == ["-m", "gpd.cli", "install"]:
    runtimes = selected_runtimes(args)
    scope = selected_scope(args)
    failed_runtimes = [runtime for runtime in runtimes if runtime.lower() in FAIL_RUNTIME_INSTALL_RUNTIMES]
    installed_runtimes = [runtime for runtime in runtimes if runtime not in failed_runtimes]
    if os.environ.get("GPD_BOOTSTRAP_EMBEDDED_INSTALL") != "1":
        print(f"GPD v{PYTHON_PACKAGE_VERSION} - Get Physics Done")
        print("© 2026 Physical Superintelligence PBC (PSI)")
        if "--skip-readiness-check" in args:
            print(f"Runtime readiness preflight for: {{format_runtime_list(runtimes)}}")
            for runtime in runtimes:
                print(f"- {{RUNTIME_LABELS[runtime]}}: readiness check skipped.")
    print(f"Installing GPD ({{scope}}) for: {{format_runtime_list(runtimes)}}")
    for runtime in installed_runtimes:
        print(f"✓ {{RUNTIME_LABELS[runtime]}}")
    for runtime in failed_runtimes:
        print(f"✗ {{RUNTIME_LABELS[runtime]}}: simulated install failure")
    print("Install Summary")
    if failed_runtimes:
        print("Install failures:")
        for runtime in failed_runtimes:
            print(f"- {{RUNTIME_LABELS[runtime]}} ({{runtime}}): simulated install failure")
        record()
        raise SystemExit(1)
    print("After install")
    print(f"Docs hub: {_BEGINNER_ONBOARDING_HUB_URL}")
    if len(installed_runtimes) == 1:
        runtime = installed_runtimes[0]
        print(
            f"Next: open {{RUNTIME_LABELS[runtime]}} in this folder, then run {{START_COMMANDS[runtime]}}."
        )
    else:
        print("Next: choose a runtime and run its GPD start command:")
        for runtime in installed_runtimes:
            print(
                f"- {{RUNTIME_LABELS[runtime]}}: "
                f"{{START_COMMANDS[runtime]}}"
            )
    print("Diagnostics: use gpd --help for local diagnostics and later setup.")
    record()
    raise SystemExit(0)

if args[:3] == ["-m", "gpd.cli", "uninstall"]:
    if "--yes" not in args and "--force" not in args and "-y" not in args:
        sys.stderr.write("uninstall confirmation prompt would block without --yes\\n")
        record()
        raise SystemExit(2)
    print("runtime uninstall ok")
    record()
    raise SystemExit(0)

record()
raise SystemExit(0)
"""
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script, encoding="utf-8")
    script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _run_bootstrap_with_fake_python(
    tmp_path: Path,
    *,
    installer_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    metadata_payload: dict[str, object] | None = None,
    python_versions: dict[str, str] | None = None,
    precreate_managed_version: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    node_path = shutil.which("node")
    if node_path is None:
        raise RuntimeError("node is required for bootstrap installer tests")

    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir(parents=True)
    local_bin = home / ".local" / "bin"
    log_path = tmp_path / "python-log.jsonl"

    versions = {
        "python3.13": "Python 3.13.2",
        "python3.12": "Python 3.12.9",
        "python3.11": "Python 3.11.9",
        "python3": "Python 3.13.2",
        "python": "Python 3.13.2",
    }
    if python_versions:
        versions.update(python_versions)

    for name, version_text in versions.items():
        _write_fake_python(fake_bin / name, log_path, version_text)

    missing_launchers = {
        token.strip().lower()
        for token in (extra_env or {}).get("FAKE_MISSING_LAUNCHERS", "").split(",")
        if token.strip()
    }
    for runtime in _RUNTIME_NAMES:
        launch_command = _RUNTIME_LAUNCH_COMMANDS[runtime]
        if runtime.lower() in missing_launchers or launch_command.lower() in missing_launchers:
            continue
        launch_executable = launch_command.split()[0] if launch_command.split() else launch_command
        _write_fake_launcher(fake_bin / launch_executable, launch_executable)

    if precreate_managed_version is not None:
        managed_bin = home / MANAGED_HOME_DIRNAME / "venv" / "bin"
        for name in ("python", "python3"):
            _write_fake_python(managed_bin / name, log_path, precreate_managed_version)

    env = {key: value for key, value in os.environ.items() if not key.startswith("FAKE_PIP_")}
    env["HOME"] = str(home)
    env.pop("GPD_HOME", None)
    env["GPD_BOOTSTRAP_DISABLE_NETWORK_PROBES"] = "1"
    env["PATH"] = os.pathsep.join([str(local_bin), str(fake_bin)])
    env.update(_BOOTSTRAP_INSTALLER_METADATA_ENV)
    if metadata_payload is not None:
        env[_BOOTSTRAP_INSTALLER_METADATA_JSON_ENV] = json.dumps(
            metadata_payload,
            sort_keys=True,
            separators=(",", ":"),
        )
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        [node_path, "bin/install.js", *(installer_args or [_CODEX_INSTALL_FLAG, "--local"])],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    return result, home, log_path


def _run_node_contract_validation(
    script: str,
    *,
    metadata_payload: dict[str, object] | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    node_path = shutil.which("node")
    if node_path is None:
        raise RuntimeError("node is required for bootstrap installer tests")

    env = os.environ.copy()
    env.update(_BOOTSTRAP_INSTALLER_METADATA_ENV)
    if metadata_payload is not None:
        env[_BOOTSTRAP_INSTALLER_METADATA_JSON_ENV] = json.dumps(
            metadata_payload,
            sort_keys=True,
            separators=(",", ":"),
        )
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        [node_path, "-e", script],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_bootstrap_installer_consumes_generated_metadata_without_python() -> None:
    runtime_names = [descriptor.runtime_name for descriptor in _RUNTIME_DESCRIPTORS]
    runtime_labels = [descriptor.display_name for descriptor in _RUNTIME_DESCRIPTORS]
    first_alias = next(alias for descriptor in _RUNTIME_DESCRIPTORS for alias in descriptor.selection_aliases)
    alias_runtime = next(
        descriptor.runtime_name for descriptor in _RUNTIME_DESCRIPTORS if first_alias in descriptor.selection_aliases
    )
    shared_text = _BOOTSTRAP_INSTALLER_METADATA_PAYLOAD["shared_public_surface_text"]
    assert isinstance(shared_text, dict)
    local_cli_bridge = shared_text["localCliBridge"]
    assert isinstance(local_cli_bridge, dict)
    shared_install = _BOOTSTRAP_INSTALLER_METADATA_PAYLOAD["shared_install_metadata"]
    assert isinstance(shared_install, dict)
    result = _run_node_contract_validation(
        f"""
const assert = require("node:assert/strict");
const installer = require("./bin/install.js");

const sharedInstall = installer.loadSharedInstallMetadata();
assert.equal(sharedInstall.bootstrapCommand, {shared_install["bootstrapCommand"]!r});
assert.equal(sharedInstall.manifestName, {shared_install["manifestName"]!r});

const sharedText = installer.loadSharedPublicSurfaceText();
assert.equal(sharedText.localCliBridge.helpCommand, {local_cli_bridge["helpCommand"]!r});
assert.equal(sharedText.beginnerHubUrl, {_BEGINNER_ONBOARDING_HUB_URL!r});

const menu = installer.runtimeSelectionMenuEntries({{ allowAll: false }});
assert.deepEqual(menu.map((entry) => entry.details[0]), {runtime_names!r});
assert.deepEqual(menu.map((entry) => entry.label), {runtime_labels!r});
assert.deepEqual(installer.resolveRuntimeSelectionChoice({first_alias!r}), {{ runtimes: [{alias_runtime!r}] }});
"""
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_bootstrap_installer_metadata_validator_rejects_bad_envelope_and_hash_drift() -> None:
    metadata_json = json.dumps(_BOOTSTRAP_INSTALLER_METADATA_PAYLOAD)
    result = _run_node_contract_validation(
        f"""
const assert = require("node:assert/strict");
const {{ validateBootstrapInstallerMetadata }} = require("./bin/install.js");
const metadata = {metadata_json};

assert.doesNotThrow(() => validateBootstrapInstallerMetadata(metadata));

const badSchemaVersion = JSON.parse(JSON.stringify(metadata));
badSchemaVersion.schema_version = true;
assert.throws(
  () => validateBootstrapInstallerMetadata(badSchemaVersion),
  /Unsupported bootstrap installer metadata schema_version/
);

const missingPublicSurface = JSON.parse(JSON.stringify(metadata));
delete missingPublicSurface.shared_public_surface_text;
assert.throws(
  () => validateBootstrapInstallerMetadata(missingPublicSurface),
  /bootstrap installer metadata is missing required key\\(s\\): shared_public_surface_text/
);

const missingSharedInstall = JSON.parse(JSON.stringify(metadata));
delete missingSharedInstall.shared_install_metadata;
assert.throws(
  () => validateBootstrapInstallerMetadata(missingSharedInstall),
  /bootstrap installer metadata is missing required key\\(s\\): shared_install_metadata/
);

const hashDrift = JSON.parse(JSON.stringify(metadata));
hashDrift.source_hashes["src/gpd/adapters/runtime_catalog.json"] = "0".repeat(64);
assert.throws(
  () => validateBootstrapInstallerMetadata(hashDrift),
  /bootstrap installer metadata source hash mismatch for src\\/gpd\\/adapters\\/runtime_catalog\\.json/
);
"""
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_bootstrap_installer_metadata_validator_checks_runtime_consumed_fields() -> None:
    metadata_json = json.dumps(_BOOTSTRAP_INSTALLER_METADATA_PAYLOAD)
    result = _run_node_contract_validation(
        f"""
const assert = require("node:assert/strict");
const {{ validateBootstrapInstallerMetadata }} = require("./bin/install.js");
const metadata = {metadata_json};

const duplicateInstallFlag = JSON.parse(JSON.stringify(metadata));
duplicateInstallFlag.runtimes[1].install_flag = duplicateInstallFlag.runtimes[0].install_flag;
assert.throws(
  () => validateBootstrapInstallerMetadata(duplicateInstallFlag),
  /bootstrap installer metadata\\.runtimes contains duplicate install_flag/
);

const badEnvVar = JSON.parse(JSON.stringify(metadata));
badEnvVar.runtimes[0].global_config.env_var = "BAD=1";
assert.throws(
  () => validateBootstrapInstallerMetadata(badEnvVar),
  /bootstrap installer metadata\\.runtimes\\[0\\]\\.global_config\\.env_var must be an environment variable name/
);

const missingConfigDir = JSON.parse(JSON.stringify(metadata));
delete missingConfigDir.runtimes[0].config_dir_name;
assert.throws(
  () => validateBootstrapInstallerMetadata(missingConfigDir),
  /bootstrap installer metadata\\.runtimes\\[0\\] is missing required key\\(s\\): config_dir_name/
);
"""
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_bootstrap_installer_metadata_validator_checks_python_compatibility_fields() -> None:
    result = _run_node_contract_validation(
        r"""
const assert = require("node:assert/strict");
const { validateBootstrapInstallerMetadata } = require("./bin/install.js");
const metadata = JSON.parse(process.env.GPD_BOOTSTRAP_TEST_INSTALLER_METADATA_JSON);

const cases = [
  [
    "unknown key",
    (candidate) => { candidate.python_compatibility.extraUnexpectedKey = true; },
    /bootstrap installer metadata\.python_compatibility contains unknown key\(s\): extraUnexpectedKey/,
  ],
  [
    "missing floor",
    (candidate) => { delete candidate.python_compatibility.minimum_supported_python; },
    /bootstrap installer metadata\.python_compatibility is missing required key\(s\): minimum_supported_python/,
  ],
  [
    "bad label",
    (candidate) => { candidate.python_compatibility.minimum_supported_python_label = "3.10"; },
    /bootstrap installer metadata\.python_compatibility\.minimum_supported_python_label must match minimum_supported_python/,
  ],
  [
    "duplicate preferred minor",
    (candidate) => { candidate.python_compatibility.preferred_versioned_python_minors = [13, 13, 11]; },
    /bootstrap installer metadata\.python_compatibility\.preferred_versioned_python_minors must not contain duplicate values/,
  ],
  [
    "unsupported preferred minor",
    (candidate) => { candidate.python_compatibility.preferred_versioned_python_minors = [10, 12, 11]; },
    /bootstrap installer metadata\.python_compatibility\.preferred_versioned_python_minors\[0\] must be >= minimum_supported_python\.minor/,
  ],
  [
    "recommended mismatch",
    (candidate) => { candidate.python_compatibility.recommended_python_version.minor = 12; },
    /bootstrap installer metadata\.python_compatibility\.recommended_python_version\.minor must match the first preferred_versioned_python_minors entry/,
  ],
];

for (const [label, mutate, expectedError] of cases) {
  const candidate = JSON.parse(JSON.stringify(metadata));
  mutate(candidate);
  assert.throws(
    () => validateBootstrapInstallerMetadata(candidate),
    expectedError,
    `${label} metadata should reject invalid Python compatibility`
  );
}
"""
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_bootstrap_installer_metadata_validator_checks_shared_install_metadata() -> None:
    result = _run_node_contract_validation(
        r"""
const assert = require("node:assert/strict");
const { validateBootstrapInstallerMetadata } = require("./bin/install.js");
const metadata = JSON.parse(process.env.GPD_BOOTSTRAP_TEST_INSTALLER_METADATA_JSON);

const cases = [
  [
    "unknown key",
    (candidate) => { candidate.shared_install_metadata.extraUnexpectedKey = "unexpected"; },
    /bootstrap installer metadata\.shared_install_metadata contains unknown key\(s\): extraUnexpectedKey/,
  ],
  [
    "bad package name",
    (candidate) => { candidate.shared_install_metadata.bootstrapPackageName = "Bad Package"; },
    /bootstrap installer metadata\.shared_install_metadata\.bootstrapPackageName must be a lowercase npm package name/,
  ],
  [
    "unsafe install root",
    (candidate) => { candidate.shared_install_metadata.installRootDirName = "../get-physics-done"; },
    /bootstrap installer metadata\.shared_install_metadata\.installRootDirName must be a safe relative path segment without traversal/,
  ],
  [
    "unsafe manifest name",
    (candidate) => { candidate.shared_install_metadata.manifestName = "/tmp/gpd-file-manifest.json"; },
    /bootstrap installer metadata\.shared_install_metadata\.manifestName must be a safe relative path segment without traversal/,
  ],
];

for (const [label, mutate, expectedError] of cases) {
  const candidate = JSON.parse(JSON.stringify(metadata));
  mutate(candidate);
  assert.throws(
    () => validateBootstrapInstallerMetadata(candidate),
    expectedError,
    `${label} metadata should reject invalid shared install metadata`
  );
}

const commandMismatch = JSON.parse(JSON.stringify(metadata));
commandMismatch.shared_install_metadata.bootstrapCommand = "npx -y other-package";
assert.throws(
  () => validateBootstrapInstallerMetadata(commandMismatch),
  (err) => err.message.includes(
    `bootstrap installer metadata.shared_install_metadata.bootstrapCommand must be ${JSON.stringify(metadata.shared_install_metadata.bootstrapCommand)}`
  ),
  "command/package mismatch metadata should reject invalid shared install metadata"
);
"""
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_bootstrap_installer_metadata_validator_rejects_shared_surface_unknown_keys() -> None:
    result = _run_node_contract_validation(
        r"""
const assert = require("node:assert/strict");
const { validateBootstrapInstallerMetadata } = require("./bin/install.js");
const metadata = JSON.parse(process.env.GPD_BOOTSTRAP_TEST_INSTALLER_METADATA_JSON);

const cases = [
  [
    "shared top level",
    (candidate) => { candidate.shared_public_surface_text.extraUnexpectedKey = "unexpected"; },
    /bootstrap installer metadata\.shared_public_surface_text contains unknown key\(s\): extraUnexpectedKey/,
  ],
  [
    "local CLI bridge",
    (candidate) => { candidate.shared_public_surface_text.localCliBridge.extraUnexpectedKey = "unexpected"; },
    /bootstrap installer metadata\.shared_public_surface_text\.localCliBridge contains unknown key\(s\): extraUnexpectedKey/,
  ],
  [
    "resume authority",
    (candidate) => { candidate.shared_public_surface_text.resumeAuthority.extraUnexpectedKey = "unexpected"; },
    /bootstrap installer metadata\.shared_public_surface_text\.resumeAuthority contains unknown key\(s\): extraUnexpectedKey/,
  ],
  [
    "recovery ladder",
    (candidate) => { candidate.shared_public_surface_text.recoveryLadder.extraUnexpectedKey = "unexpected"; },
    /bootstrap installer metadata\.shared_public_surface_text\.recoveryLadder contains unknown key\(s\): extraUnexpectedKey/,
  ],
];

for (const [label, mutate, expectedError] of cases) {
  const candidate = JSON.parse(JSON.stringify(metadata));
  mutate(candidate);
  assert.throws(
    () => validateBootstrapInstallerMetadata(candidate),
    expectedError,
    `${label} metadata should reject unknown keys`
  );
}
"""
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_bootstrap_public_surface_text_is_loaded_from_generated_metadata() -> None:
    metadata_payload = json.loads(json.dumps(_BOOTSTRAP_INSTALLER_METADATA_PAYLOAD))
    shared_text = metadata_payload["shared_public_surface_text"]
    assert isinstance(shared_text, dict)
    shared_text["beginnerHubUrl"] = "https://example.invalid/generated-bootstrap"
    local_bridge = shared_text["localCliBridge"]
    assert isinstance(local_bridge, dict)
    local_bridge["helpCommand"] = "gpd generated-help"

    result = _run_node_contract_validation(
        r"""
const assert = require("node:assert/strict");
const { loadSharedPublicSurfaceText } = require("./bin/install.js");
const sharedText = loadSharedPublicSurfaceText();
assert.equal(sharedText.beginnerHubUrl, "https://example.invalid/generated-bootstrap");
assert.equal(sharedText.localCliBridge.helpCommand, "gpd generated-help");
""",
        metadata_payload=metadata_payload,
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_help_and_usage_use_generated_shared_install_command() -> None:
    metadata_payload = json.loads(json.dumps(_BOOTSTRAP_INSTALLER_METADATA_PAYLOAD))
    shared_install = metadata_payload["shared_install_metadata"]
    assert isinstance(shared_install, dict)
    shared_install["bootstrapPackageName"] = "gpd-bootstrap-test"
    shared_install["bootstrapCommand"] = "npx -y gpd-bootstrap-test"

    node_path = shutil.which("node")
    assert node_path is not None
    env = os.environ.copy()
    env[_BOOTSTRAP_INSTALLER_METADATA_JSON_ENV] = json.dumps(
        metadata_payload,
        sort_keys=True,
        separators=(",", ":"),
    )

    help_result = subprocess.run(
        [node_path, "bin/install.js", "--help"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert help_result.returncode == 0, f"{help_result.stdout}\n{help_result.stderr}"
    assert "npx -y gpd-bootstrap-test [install|uninstall] [options]" in help_result.stdout
    assert "npx -y get-physics-done" not in help_result.stdout

    error_result = subprocess.run(
        [node_path, "bin/install.js", "--bogus"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert error_result.returncode == 1
    assert "Run npx -y gpd-bootstrap-test --help for usage." in error_result.stderr
    assert "npx -y get-physics-done" not in error_result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_target_dir_selection_menu_requires_one_runtime() -> None:
    result = _run_node_contract_validation(
        r"""
const assert = require("node:assert/strict");
const { resolveRuntimeSelectionChoice, runtimeSelectionMenuEntries } = require("./bin/install.js");
const catalog = require("./src/gpd/adapters/runtime_catalog.json");

assert.ok(runtimeSelectionMenuEntries().some((entry) => entry.label === "All runtimes"));
assert.ok(!runtimeSelectionMenuEntries({ allowAll: false }).some((entry) => entry.label === "All runtimes"));
assert.equal(resolveRuntimeSelectionChoice("all").runtimes.length, catalog.length);
assert.deepEqual(
  resolveRuntimeSelectionChoice("all", { allowAll: false }),
  { error: "Select exactly one runtime when using --target-dir." }
);
assert.deepEqual(
  resolveRuntimeSelectionChoice(String(catalog.length + 1), { allowAll: false }),
  { error: "Select exactly one runtime when using --target-dir." }
);
"""
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_rejects_all_with_explicit_runtime_flag_before_python(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=["--all", _CODEX_INSTALL_FLAG, "--local"],
    )

    assert result.returncode == 1
    assert "Cannot combine explicit runtimes with --all for install" in result.stderr
    assert not log_path.exists()


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_uninstall_rejects_all_with_explicit_runtime_token_before_python(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=["uninstall", "all", _CODEX_RUNTIME_NAME, "--local"],
    )

    assert result.returncode == 1
    assert "Cannot combine explicit runtimes with --all for uninstall" in result.stderr
    assert not log_path.exists()


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
@pytest.mark.parametrize(
    ("installer_args", "expected_error"),
    (
        ([_CODEX_INSTALL_FLAG, "--local", "--bogus"], "Unknown bootstrap option: --bogus."),
        (["install", _CODEX_RUNTIME_NAME, "bogus", "--local"], "Unexpected bootstrap argument: bogus."),
    ),
)
def test_bootstrap_rejects_unknown_or_unconsumed_argument_before_python(
    tmp_path: Path,
    installer_args: list[str],
    expected_error: str,
) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(tmp_path, installer_args=installer_args)
    shared_install = _BOOTSTRAP_INSTALLER_METADATA_PAYLOAD["shared_install_metadata"]
    assert isinstance(shared_install, dict)

    assert result.returncode == 1
    assert expected_error in result.stderr
    assert f"Run {shared_install['bootstrapCommand']} --help for usage." in result.stderr
    assert not log_path.exists()


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_help_uses_catalog_driven_example_runtimes() -> None:
    node_path = shutil.which("node")
    assert node_path is not None

    result = subprocess.run(
        [node_path, "bin/install.js", "--help"],
        cwd=REPO_ROOT,
        env={**os.environ, **_BOOTSTRAP_INSTALLER_METADATA_ENV},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    shared_install = _BOOTSTRAP_INSTALLER_METADATA_PAYLOAD["shared_install_metadata"]
    assert isinstance(shared_install, dict)
    assert f"{shared_install['bootstrapCommand']} [install|uninstall] [options]" in result.stdout
    plain_stdout = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    longest_runtime_flags, longest_runtime_display_name = max(
        (
            (
                ", ".join(dict.fromkeys((descriptor.install_flag, *descriptor.selection_flags))),
                descriptor.display_name,
            )
            for descriptor in _RUNTIME_DESCRIPTORS
        ),
        key=lambda row: len(row[0]),
    )
    assert f"{longest_runtime_flags} Select {longest_runtime_display_name} only" in plain_stdout
    assert f"{longest_runtime_flags}Select" not in plain_stdout
    for descriptor in _RUNTIME_HELP_EXAMPLE_DESCRIPTORS:
        assert f"# Install for {descriptor.display_name} {descriptor.installer_help_example_scope}" in result.stdout
    _assert_in_order(
        result.stdout,
        (
            "PyPI pinned release",
            "tagged GitHub fallback",
            "latest unreleased GitHub main source",
        ),
    )
    _assert_public(
        result.stdout,
        "bootstrap help public installer guidance",
        f"Beginner path: {_BEGINNER_ONBOARDING_HUB_URL}",
        "Runtime surface: run the selected runtime's help command",
        "Override the runtime config directory; defaults to local scope unless the path resolves to that runtime's "
        "canonical global config dir",
        "first-run order is `help -> start -> tour -> new-project / map-research -> resume-work`",
    )
    _assert_machine(
        result.stdout,
        "bootstrap help unattended readiness command",
        "`gpd validate unattended-readiness --runtime <runtime> --autonomy <mode>`",
    )
    _assert_forbidden(
        result.stdout,
        "bootstrap help stale onboarding and source text",
        "First-run order:",
        "Open your runtime, run its help command first",
        "Supervised autonomy (`supervised`) is the default",
        "Opt into Balanced autonomy (`balanced`)",
        "Workflow presets:",
        "Recommended unattended default: Balanced",
        "matching tagged GitHub source",
        'startsWith("$")',
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_installer_enforces_node_20_floor() -> None:
    result = _run_node_contract_validation(
        r"""
const assert = require("node:assert/strict");
const { ensureSupportedNodeVersion, nodeMajorVersion } = require("./bin/install.js");

assert.equal(nodeMajorVersion("20.0.0"), 20);
assert.equal(nodeMajorVersion("v24.1.0"), 24);
assert.doesNotThrow(() => ensureSupportedNodeVersion("20.0.0"));
assert.doesNotThrow(() => ensureSupportedNodeVersion("24.1.0"));
assert.throws(() => ensureSupportedNodeVersion("19.9.0"), /Node\.js 20\+ is required/);
assert.throws(() => ensureSupportedNodeVersion("not-a-version"), /Node\.js 20\+ is required/);
"""
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_uses_managed_virtualenv_and_skips_host_pip(tmp_path: Path) -> None:
    result, home, log_path = _run_bootstrap_with_fake_python(tmp_path)

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

    assert any(entry["argv"] == ["-m", "venv", "--help"] for entry in entries)
    assert any(
        entry["argv"][:2] == ["-m", "venv"]
        and entry["argv"][-1].replace("\\", "/").endswith(f"/{MANAGED_HOME_DIRNAME}/venv")
        for entry in entries
    )

    base_pip_calls = [entry for entry in entries if not entry["managed"] and entry["argv"][:2] == ["-m", "pip"]]
    assert base_pip_calls == []

    managed_pip_installs = [
        entry for entry in entries if entry["managed"] and entry["argv"][:4] == ["-m", "pip", "install", "--upgrade"]
    ]
    assert len(managed_pip_installs) == 1
    assert "--quiet" in managed_pip_installs[0]["argv"]
    assert managed_pip_installs[0]["argv"][-1] == PYPI_SPEC

    managed_runtime_installs = [
        entry
        for entry in entries
        if entry["managed"]
        and entry["argv"]
        == [
            "-m",
            "gpd.cli",
            "install",
            _CODEX_RUNTIME_NAME,
            "--local",
            "--skip-readiness-check",
        ]
    ]
    assert len(managed_runtime_installs) == 1
    managed_runtime_doctor = [
        entry
        for entry in entries
        if entry["managed"]
        and entry["argv"] == ["-m", "gpd.cli", "--raw", "doctor", "--runtime", _CODEX_RUNTIME_NAME, "--local"]
    ]
    assert len(managed_runtime_doctor) == 1
    doctor_index = next(
        index
        for index, entry in enumerate(entries)
        if entry["managed"]
        and entry["argv"] == ["-m", "gpd.cli", "--raw", "doctor", "--runtime", _CODEX_RUNTIME_NAME, "--local"]
    )
    install_index = next(
        index
        for index, entry in enumerate(entries)
        if entry["managed"]
        and entry["argv"]
        == [
            "-m",
            "gpd.cli",
            "install",
            _CODEX_RUNTIME_NAME,
            "--local",
            "--skip-readiness-check",
        ]
    )
    assert doctor_index < install_index

    assert (home / MANAGED_HOME_DIRNAME / "venv" / "bin" / "python").exists()
    assert f"GPD v{PACKAGE_VERSION} - Get Physics Done" in result.stdout
    assert result.stdout.count(f"GPD v{PACKAGE_VERSION} - Get Physics Done") == 1
    assert "© 2026 Physical Superintelligence PBC (PSI)" in result.stdout
    assert "readiness check skipped" not in result.stdout
    assert f"Installing GPD (local) for: {_RUNTIME_DISPLAY_NAMES[_CODEX_RUNTIME_NAME]}" in result.stdout
    assert "Runtime launcher/target preflight" in result.stdout
    assert (
        f"Runtime launcher/target preflight passed for {_RUNTIME_DISPLAY_NAMES[_CODEX_RUNTIME_NAME]}" in result.stdout
    )
    assert "GPD does not verify provider credentials automatically" in result.stdout
    combined_output = result.stdout + result.stderr
    assert f"`gpd doctor --runtime {_CODEX_RUNTIME_NAME} --local`" in combined_output
    assert "`gpd validate unattended-readiness`" not in combined_output
    assert "`gpd validate unattended-readiness --runtime <runtime> --autonomy <mode>`" not in combined_output
    assert "Install Summary" in result.stdout
    assert "Startup checklist" not in result.stdout
    assert "Beginner Onboarding Hub:" not in result.stdout
    assert _BEGINNER_ONBOARDING_HUB_URL in result.stdout
    _assert_single_runtime_next_steps(result.stdout, _CODEX_RUNTIME_NAME)
    _assert_bootstrap_concise_after_install_guidance(result.stdout)
    _assert_single_runtime_bootstrap_concise_line(result.stdout, _CODEX_RUNTIME_NAME)
    assert f"Installing GPD for {_RUNTIME_DISPLAY_NAMES[_CODEX_RUNTIME_NAME]} (local)..." not in result.stdout
    assert f"Installed GPD for {_RUNTIME_DISPLAY_NAMES[_CODEX_RUNTIME_NAME]} (local)." not in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_fake_python_harness_ignores_ambient_fake_pip_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_PIP_FAIL_PYPI", "1")

    result, _home, _log_path = _run_bootstrap_with_fake_python(tmp_path)

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_uninstall_routes_to_runtime_uninstall(tmp_path: Path) -> None:
    result, home, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=["--uninstall", _CODEX_INSTALL_FLAG, "--local"],
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

    assert any(entry["argv"] == ["-m", "venv", "--help"] for entry in entries)
    assert any(
        entry["argv"][:2] == ["-m", "venv"]
        and entry["argv"][-1].replace("\\", "/").endswith(f"/{MANAGED_HOME_DIRNAME}/venv")
        for entry in entries
    )

    managed_pip_installs = [
        entry for entry in entries if entry["managed"] and entry["argv"][:4] == ["-m", "pip", "install", "--upgrade"]
    ]
    assert len(managed_pip_installs) == 1
    assert managed_pip_installs[0]["argv"][-1] == PYPI_SPEC

    managed_runtime_uninstalls = [
        entry
        for entry in entries
        if entry["managed"] and entry["argv"] == ["-m", "gpd.cli", "uninstall", _CODEX_RUNTIME_NAME, "--local", "--yes"]
    ]
    assert len(managed_runtime_uninstalls) == 1
    managed_runtime_doctor = [
        entry for entry in entries if entry["managed"] and entry["argv"][:4] == ["-m", "gpd.cli", "--raw", "doctor"]
    ]
    assert managed_runtime_doctor == []

    assert (home / MANAGED_HOME_DIRNAME / "venv" / "bin" / "python").exists()
    assert (
        f"Preparing managed GPD CLI from PyPI (get-physics-done=={PYTHON_PACKAGE_VERSION}) into the managed environment..."
        in result.stdout
    )
    assert "Runtime launcher/target preflight" not in result.stdout
    assert f"Uninstalling GPD from {_RUNTIME_DISPLAY_NAMES[_CODEX_RUNTIME_NAME]} (local)..." in result.stdout
    assert "runtime uninstall ok" in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_uninstall_reuses_existing_managed_cli_without_package_install(tmp_path: Path) -> None:
    result, home, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=["--uninstall", _CODEX_INSTALL_FLAG, "--local"],
        precreate_managed_version="Python 3.13.2",
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_pip_installs = [
        entry for entry in entries if entry["managed"] and entry["argv"][:4] == ["-m", "pip", "install", "--upgrade"]
    ]
    managed_runtime_uninstalls = [
        entry
        for entry in entries
        if entry["managed"] and entry["argv"] == ["-m", "gpd.cli", "uninstall", _CODEX_RUNTIME_NAME, "--local", "--yes"]
    ]
    venv_creates = [
        entry for entry in entries if entry["argv"][:2] == ["-m", "venv"] and entry["argv"] != ["-m", "venv", "--help"]
    ]

    assert managed_pip_installs == []
    assert len(managed_runtime_uninstalls) == 1
    assert venv_creates == []
    assert (home / MANAGED_HOME_DIRNAME / "venv" / "bin" / "python").exists()
    assert "Trying existing managed GPD CLI for uninstall..." in result.stdout
    assert "Preparing managed GPD CLI from PyPI" not in result.stdout
    assert "runtime uninstall ok" in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_uninstall_subcommand_alias_routes_to_runtime_uninstall(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=["uninstall", "--all", "--local"],
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_runtime_uninstalls = [
        entry
        for entry in entries
        if entry["managed"] and entry["argv"] == ["-m", "gpd.cli", "uninstall", "--all", "--local", "--yes"]
    ]

    assert len(managed_runtime_uninstalls) == 1
    for runtime in _RUNTIME_NAMES:
        assert _RUNTIME_DISPLAY_NAMES[runtime] in result.stdout
    assert "runtime uninstall ok" in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_supports_all_runtime_uninstall_in_one_pass(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=["--uninstall", "--all", "--global"],
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_runtime_uninstalls = [
        entry
        for entry in entries
        if entry["managed"] and entry["argv"] == ["-m", "gpd.cli", "uninstall", "--all", "--global", "--yes"]
    ]

    assert len(managed_runtime_uninstalls) == 1
    for runtime in _RUNTIME_NAMES:
        assert _RUNTIME_DISPLAY_NAMES[runtime] in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_install_requires_explicit_runtime_non_interactively(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=["--local"],
    )

    assert result.returncode == 1
    assert "Specify a runtime with" in result.stderr
    assert "when running non-interactively." in result.stderr
    for flag in _RUNTIME_INSTALL_FLAGS:
        assert flag in result.stderr
    assert not log_path.exists()


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_install_requires_explicit_scope_non_interactively(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=[_CODEX_INSTALL_FLAG],
    )

    assert result.returncode == 1
    assert "Specify --global or --local when running non-interactively." in result.stderr
    assert not log_path.exists()


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_install_blocks_when_selected_runtime_launcher_is_missing(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        extra_env={"FAKE_MISSING_LAUNCHERS": _CODEX_RUNTIME_NAME},
    )

    assert result.returncode == 1

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_pip_installs = [
        entry for entry in entries if entry["managed"] and entry["argv"][:4] == ["-m", "pip", "install", "--upgrade"]
    ]
    assert len(managed_pip_installs) == 1

    managed_runtime_doctor = [
        entry
        for entry in entries
        if entry["managed"]
        and entry["argv"] == ["-m", "gpd.cli", "--raw", "doctor", "--runtime", _CODEX_RUNTIME_NAME, "--local"]
    ]
    assert len(managed_runtime_doctor) == 1
    managed_runtime_installs = [
        entry for entry in entries if entry["managed"] and entry["argv"][:3] == ["-m", "gpd.cli", "install"]
    ]
    assert managed_runtime_installs == []
    assert "Runtime launcher/target preflight failed." in result.stderr
    assert (
        f"{_RUNTIME_DISPLAY_NAMES[_CODEX_RUNTIME_NAME]}: Runtime Launcher: "
        f"{_RUNTIME_LAUNCH_COMMANDS[_CODEX_RUNTIME_NAME]} not found on PATH"
    ) in result.stderr
    combined_output = result.stdout + result.stderr
    assert f"`gpd doctor --runtime {_CODEX_RUNTIME_NAME} --local`" in combined_output


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_install_blocks_when_target_dir_is_not_writable(tmp_path: Path) -> None:
    protected_parent = tmp_path / "protected"
    protected_parent.mkdir()
    protected_parent.chmod(0o555)
    target_dir = protected_parent / _RUNTIME_ADAPTERS[_CODEX_RUNTIME_NAME].config_dir_name

    try:
        result, _, log_path = _run_bootstrap_with_fake_python(
            tmp_path,
            installer_args=[_CODEX_INSTALL_FLAG, "--local", "--target-dir", str(target_dir)],
        )
    finally:
        protected_parent.chmod(0o755)

    assert result.returncode == 1

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_pip_installs = [
        entry for entry in entries if entry["managed"] and entry["argv"][:4] == ["-m", "pip", "install", "--upgrade"]
    ]
    assert len(managed_pip_installs) == 1

    managed_runtime_doctor = [
        entry
        for entry in entries
        if entry["managed"]
        and entry["argv"]
        == [
            "-m",
            "gpd.cli",
            "--raw",
            "doctor",
            "--runtime",
            _CODEX_RUNTIME_NAME,
            "--local",
            "--target-dir",
            str(target_dir),
        ]
    ]
    assert len(managed_runtime_doctor) == 1
    managed_runtime_installs = [
        entry for entry in entries if entry["managed"] and entry["argv"][:3] == ["-m", "gpd.cli", "install"]
    ]
    assert managed_runtime_installs == []
    assert "Runtime launcher/target preflight failed." in result.stderr
    assert f"{_RUNTIME_DISPLAY_NAMES[_CODEX_RUNTIME_NAME]}: Runtime Config Target:" in result.stderr
    assert "is not writable" in result.stderr


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_install_repairs_selected_runtime_incomplete_target(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        extra_env={"FAKE_INCOMPLETE_TARGET_RUNTIMES": _CODEX_RUNTIME_NAME},
    )

    assert result.returncode == 0, result.stderr

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_runtime_doctor = [
        entry
        for entry in entries
        if entry["managed"]
        and entry["argv"] == ["-m", "gpd.cli", "--raw", "doctor", "--runtime", _CODEX_RUNTIME_NAME, "--local"]
    ]
    managed_runtime_installs = [
        entry for entry in entries if entry["managed"] and entry["argv"][:3] == ["-m", "gpd.cli", "install"]
    ]
    assert len(managed_runtime_doctor) == 1
    assert len(managed_runtime_installs) == 1
    combined_output = result.stdout + result.stderr
    assert "Runtime launcher/target preflight failed." not in combined_output
    assert (
        f"Runtime launcher/target preflight passed for {_RUNTIME_DISPLAY_NAMES[_CODEX_RUNTIME_NAME]}" in combined_output
    )
    assert "launcher/target preflight passed with advisories" not in combined_output
    assert "incomplete owned GPD install" in combined_output


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_uninstall_requires_explicit_runtime_non_interactively(tmp_path: Path) -> None:
    result, _, _ = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=["--uninstall", "--local"],
    )

    assert result.returncode == 1
    assert "Specify a runtime with" in result.stderr
    assert "or use --all when running --uninstall non-interactively." in result.stderr
    for flag in _RUNTIME_INSTALL_FLAGS:
        assert flag in result.stderr


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_uninstall_requires_explicit_scope_non_interactively(tmp_path: Path) -> None:
    result, _, _ = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=["--uninstall", _CODEX_INSTALL_FLAG],
    )

    assert result.returncode == 1
    assert "Specify --global or --local when running --uninstall non-interactively." in result.stderr


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_uninstall_rejects_reinstall_flag(tmp_path: Path) -> None:
    result, _, _ = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=["--uninstall", _CODEX_INSTALL_FLAG, "--local", "--reinstall"],
    )

    assert result.returncode == 1
    assert "Cannot combine --uninstall with --reinstall." in result.stderr


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_rejects_reinstall_and_upgrade_together(tmp_path: Path) -> None:
    result, _, _ = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=[_CODEX_INSTALL_FLAG, "--local", "--reinstall", "--upgrade"],
    )

    assert result.returncode == 1
    assert "Cannot combine --reinstall with --upgrade." in result.stderr


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_hides_successful_pip_chatter(tmp_path: Path) -> None:
    result, _, _ = _run_bootstrap_with_fake_python(
        tmp_path,
        extra_env={"FAKE_PIP_SUCCESS_NOISE": "1"},
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "Requirement already satisfied: noisy-package==1.0.0" not in result.stdout
    assert "Install Summary" in result.stdout
    assert f"Installed GPD for {_RUNTIME_DISPLAY_NAMES[_CODEX_RUNTIME_NAME]} (local)." not in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_does_not_add_after_install_guidance_when_python_install_fails(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=["--all", "--global"],
        extra_env={"FAKE_RUNTIME_INSTALL_FAIL_RUNTIMES": _CLAUDE_RUNTIME_NAME},
    )

    assert result.returncode == 1
    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_runtime_installs = [
        entry
        for entry in entries
        if entry["managed"]
        and entry["argv"] == ["-m", "gpd.cli", "install", "--all", "--global", "--skip-readiness-check"]
    ]
    assert len(managed_runtime_installs) == 1
    _assert_public(
        result.stdout,
        "bootstrap runtime install failure summary",
        "Install failures:",
    )
    _assert_public(
        result.stderr,
        "bootstrap runtime install failure stderr",
        "Installation failed. Check the output above for details.",
    )
    _assert_forbidden(
        result.stdout,
        "bootstrap no after-install guidance on install failure",
        "After install",
        f"Beginner path: {_BEGINNER_ONBOARDING_HUB_URL}",
        f"Docs hub: {_BEGINNER_ONBOARDING_HUB_URL}",
        "Diagnostics: use gpd --help for local diagnostics and later setup.",
    )


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_forwards_target_dir_to_runtime_install(tmp_path: Path) -> None:
    target_dir = tmp_path / "custom target" / _RUNTIME_ADAPTERS[_CODEX_RUNTIME_NAME].config_dir_name
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=[_CODEX_INSTALL_FLAG, "--target-dir", str(target_dir)],
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_runtime_installs = [
        entry
        for entry in entries
        if entry["managed"]
        and entry["argv"]
        == [
            "-m",
            "gpd.cli",
            "install",
            _CODEX_RUNTIME_NAME,
            "--local",
            "--target-dir",
            str(target_dir),
            "--skip-readiness-check",
        ]
    ]
    assert len(managed_runtime_installs) == 1
    managed_runtime_doctor = [
        entry
        for entry in entries
        if entry["managed"]
        and entry["argv"]
        == [
            "-m",
            "gpd.cli",
            "--raw",
            "doctor",
            "--runtime",
            _CODEX_RUNTIME_NAME,
            "--local",
            "--target-dir",
            str(target_dir),
        ]
    ]
    assert len(managed_runtime_doctor) == 1


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_preserves_global_scope_for_canonical_global_target_dir(tmp_path: Path) -> None:
    home = tmp_path / "home"
    target_dir = home / _RUNTIME_ADAPTERS[_CODEX_RUNTIME_NAME].config_dir_name
    result, _home, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=[_CODEX_INSTALL_FLAG, "--target-dir", str(target_dir)],
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_runtime_installs = [
        entry
        for entry in entries
        if entry["managed"]
        and entry["argv"]
        == [
            "-m",
            "gpd.cli",
            "install",
            _CODEX_RUNTIME_NAME,
            "--global",
            "--target-dir",
            str(target_dir),
            "--skip-readiness-check",
        ]
    ]

    assert len(managed_runtime_installs) == 1
    managed_runtime_doctor = [
        entry
        for entry in entries
        if entry["managed"]
        and entry["argv"]
        == [
            "-m",
            "gpd.cli",
            "--raw",
            "doctor",
            "--runtime",
            _CODEX_RUNTIME_NAME,
            "--global",
            "--target-dir",
            str(target_dir),
        ]
    ]
    assert len(managed_runtime_doctor) == 1
    assert f"Installing GPD (global) for: {_RUNTIME_DISPLAY_NAMES[_CODEX_RUNTIME_NAME]}" in result.stdout


@pytest.mark.parametrize(
    "descriptor",
    _RUNTIME_DESCRIPTORS_WITH_GLOBAL_ENV_OVERRIDE,
    ids=[descriptor.runtime_name for descriptor in _RUNTIME_DESCRIPTORS_WITH_GLOBAL_ENV_OVERRIDE],
)
@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_preserves_global_scope_for_home_target_when_runtime_env_points_elsewhere(
    tmp_path: Path,
    descriptor,
) -> None:
    home = tmp_path / "home"
    target_dir = home / descriptor.global_config.home_subpath
    env_var = (
        descriptor.global_config.env_var
        or descriptor.global_config.env_dir_var
        or descriptor.global_config.env_file_var
    )
    assert env_var is not None
    env_target = tmp_path / "runtime-env-override" / descriptor.config_dir_name
    env_value = str(env_target / "config.json") if env_var == descriptor.global_config.env_file_var else str(env_target)
    result, _home, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=[descriptor.install_flag, "--target-dir", str(target_dir)],
        extra_env={env_var: env_value},
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_runtime_installs = [
        entry
        for entry in entries
        if entry["managed"]
        and entry["argv"]
        == [
            "-m",
            "gpd.cli",
            "install",
            descriptor.runtime_name,
            "--global",
            "--target-dir",
            str(target_dir),
            "--skip-readiness-check",
        ]
    ]
    assert len(managed_runtime_installs) == 1
    managed_runtime_doctor = [
        entry
        for entry in entries
        if entry["managed"]
        and entry["argv"]
        == [
            "-m",
            "gpd.cli",
            "--raw",
            "doctor",
            "--runtime",
            descriptor.runtime_name,
            "--global",
            "--target-dir",
            str(target_dir),
        ]
    ]
    assert len(managed_runtime_doctor) == 1
    assert f"Installing GPD (global) for: {descriptor.display_name}" in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_requires_explicit_runtime_with_target_dir_non_interactively(tmp_path: Path) -> None:
    target_dir = tmp_path / "custom target"
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=["--target-dir", str(target_dir)],
    )

    assert result.returncode == 1
    _assert_public(
        result.stderr,
        "bootstrap target-dir requires one runtime",
        "Specify exactly one runtime with",
        "when using --target-dir non-interactively.",
    )
    for flag in _RUNTIME_INSTALL_FLAGS:
        assert flag in result.stderr
    assert not log_path.exists()


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_rejects_target_dir_with_all_runtimes(tmp_path: Path) -> None:
    target_dir = tmp_path / "custom target"
    result, _, _ = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=["--all", "--target-dir", str(target_dir)],
    )

    assert result.returncode == 1
    assert "--target-dir" in result.stderr
    assert "--all" in result.stderr
    assert "exactly one runtime" in result.stderr


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_reinstall_force_reinstalls_matching_release(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=[_CODEX_INSTALL_FLAG, "--local", "--reinstall"],
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_pip_installs = [
        entry for entry in entries if entry["managed"] and entry["argv"][:4] == ["-m", "pip", "install", "--upgrade"]
    ]

    assert len(managed_pip_installs) == 1
    assert "--force-reinstall" in managed_pip_installs[0]["argv"]
    assert managed_pip_installs[0]["argv"][-1] == PYPI_SPEC
    assert (
        f"Reinstalling GPD from PyPI (get-physics-done=={PYTHON_PACKAGE_VERSION}) into the managed environment..."
        in result.stdout
    )


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_upgrade_prefers_latest_main_source(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=[_CLAUDE_INSTALL_FLAG, "--local", "--upgrade"],
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_pip_installs = [
        entry for entry in entries if entry["managed"] and entry["argv"][:4] == ["-m", "pip", "install", "--upgrade"]
    ]

    assert len(managed_pip_installs) == 1
    assert "--force-reinstall" in managed_pip_installs[0]["argv"]
    assert "--no-cache-dir" in managed_pip_installs[0]["argv"]
    assert managed_pip_installs[0]["argv"][-1] == MAIN_ARCHIVE_SPEC
    assert "Upgrading GPD from the latest GitHub main branch into the managed environment..." in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_upgrade_falls_back_to_main_git_checkout(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=[_CLAUDE_INSTALL_FLAG, "--local", "--upgrade"],
        extra_env={"FAKE_PIP_FAIL_BRANCH_ARCHIVE": "1"},
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_pip_targets = [
        entry["argv"][-1]
        for entry in entries
        if entry["managed"] and entry["argv"][:4] == ["-m", "pip", "install", "--upgrade"]
    ]

    assert managed_pip_targets == [
        MAIN_ARCHIVE_SPEC,
        MAIN_HTTPS_GIT_SPEC,
    ]
    _assert_public(
        result.stdout,
        "bootstrap main archive fallback message",
        "current main branch source archive failed. Falling back to HTTPS git checkout of main...",
    )


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_upgrade_prefers_preflighted_git_checkout_when_archive_is_inaccessible(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=[_CLAUDE_INSTALL_FLAG, "--local", "--upgrade"],
        extra_env={
            "GPD_BOOTSTRAP_TEST_PROBES": json.dumps(
                {
                    MAIN_ARCHIVE_SPEC: {
                        "availability": "unavailable",
                        "reason": "HTTP 404",
                    },
                    MAIN_HTTPS_GIT_SPEC: {
                        "availability": "available",
                        "reason": "git ls-remote succeeded",
                    },
                }
            ),
        },
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_pip_targets = [
        entry["argv"][-1]
        for entry in entries
        if entry["managed"] and entry["argv"][:4] == ["-m", "pip", "install", "--upgrade"]
    ]

    assert managed_pip_targets == [MAIN_HTTPS_GIT_SPEC]
    _assert_public(
        result.stdout,
        "bootstrap preflighted main git checkout fallback",
        "Detected that current main branch source archive is unavailable: HTTP 404.",
        "Using HTTPS git checkout of main for the main-branch upgrade.",
    )
    _assert_forbidden(
        result.stderr,
        "bootstrap no raw HTTP branch archive error",
        "HTTP error 404 while getting branch archive",
    )
    _assert_forbidden(
        result.stdout,
        "bootstrap no unpreflighted main archive fallback wording",
        "current main branch source archive failed. Falling back to HTTPS git checkout of main...",
    )


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_upgrade_fails_closed_without_falling_back_to_release_sources(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        installer_args=[_CLAUDE_INSTALL_FLAG, "--local", "--upgrade"],
        extra_env={
            "FAKE_PIP_FAIL_BRANCH_ARCHIVE": "1",
            "FAKE_PIP_FAIL_MAIN_GIT": "1",
        },
    )

    assert result.returncode == 1

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_pip_targets = [
        entry["argv"][-1]
        for entry in entries
        if entry["managed"] and entry["argv"][:4] == ["-m", "pip", "install", "--upgrade"]
    ]
    managed_runtime_installs = [
        entry for entry in entries if entry["managed"] and entry["argv"][:3] == ["-m", "gpd.cli", "install"]
    ]

    assert managed_pip_targets == [
        MAIN_ARCHIVE_SPEC,
        MAIN_HTTPS_GIT_SPEC,
    ]
    assert TAG_ARCHIVE_SPEC not in managed_pip_targets
    assert TAG_HTTPS_GIT_SPEC not in managed_pip_targets
    assert managed_runtime_installs == []
    _assert_public(result.stderr, "bootstrap main git checkout failure", "git checkout could not resolve branch main")
    assert (
        f"Failed to install GPD v{PYTHON_PACKAGE_VERSION} from the latest unreleased GitHub main source."
        in result.stderr
    )


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_supports_all_runtime_install_in_one_pass(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(tmp_path, installer_args=["--all", "--global"])

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_runtime_installs = [
        entry
        for entry in entries
        if entry["managed"]
        and entry["argv"] == ["-m", "gpd.cli", "install", "--all", "--global", "--skip-readiness-check"]
    ]

    assert len(managed_runtime_installs) == 1
    for runtime in _RUNTIME_NAMES:
        assert _RUNTIME_DISPLAY_NAMES[runtime] in result.stdout
    assert "Install Summary" in result.stdout
    assert "Startup checklist" not in result.stdout
    assert "Beginner Onboarding Hub:" not in result.stdout
    assert _BEGINNER_ONBOARDING_HUB_URL in result.stdout
    for runtime in _RUNTIME_NAMES:
        _assert_multi_runtime_next_steps_line(result.stdout, runtime)
    _assert_bootstrap_concise_after_install_guidance(result.stdout)
    _assert_multi_runtime_bootstrap_concise_lines(result.stdout, _RUNTIME_NAMES)
    _assert_install_summary_semantic_contract(result.stdout)


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_falls_back_to_tag_git_when_tag_archive_install_fails(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        extra_env={"FAKE_PIP_FAIL_PYPI": "1", "FAKE_PIP_FAIL_TAG_ARCHIVE": "1"},
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_pip_targets = [
        entry["argv"][-1]
        for entry in entries
        if entry["managed"] and entry["argv"][:4] == ["-m", "pip", "install", "--upgrade"]
    ]

    assert managed_pip_targets == [
        PYPI_SPEC,
        TAG_ARCHIVE_SPEC,
        TAG_HTTPS_GIT_SPEC,
    ]
    _assert_public(
        result.stdout,
        "bootstrap PyPI fallback to GitHub source",
        "PyPI install failed. Falling back to GitHub source...",
    )
    assert (
        f"GitHub source archive for v{PYTHON_PACKAGE_VERSION} failed. Falling back to HTTPS git checkout for v{PYTHON_PACKAGE_VERSION}..."
        in result.stdout
    )


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_prefers_preflighted_tag_git_candidate_when_tag_archive_is_inaccessible(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        extra_env={
            "FAKE_PIP_FAIL_PYPI": "1",
            "GPD_BOOTSTRAP_TEST_PROBES": json.dumps(
                {
                    TAG_ARCHIVE_SPEC: {
                        "availability": "unavailable",
                        "reason": "HTTP 404",
                    },
                    TAG_HTTPS_GIT_SPEC: {
                        "availability": "available",
                        "reason": "git ls-remote succeeded",
                    },
                }
            ),
        },
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_pip_targets = [
        entry["argv"][-1]
        for entry in entries
        if entry["managed"] and entry["argv"][:4] == ["-m", "pip", "install", "--upgrade"]
    ]

    assert managed_pip_targets == [PYPI_SPEC, TAG_HTTPS_GIT_SPEC]
    combined_output = result.stdout + result.stderr
    _assert_public(
        combined_output,
        "bootstrap preflighted tag git PyPI fallback",
        "PyPI install failed. Falling back to GitHub source...",
    )
    assert (
        f"Detected that GitHub source archive for v{PYTHON_PACKAGE_VERSION} is unavailable: HTTP 404."
        in combined_output
    )
    assert (
        f"Installing GPD from HTTPS git checkout for v{PYTHON_PACKAGE_VERSION} into the managed environment..."
        in combined_output
    )


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_release_install_fails_closed_without_falling_back_to_main_sources(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        extra_env={
            "FAKE_PIP_FAIL_PYPI": "1",
            "GPD_BOOTSTRAP_TEST_PROBES": json.dumps(
                {
                    TAG_ARCHIVE_SPEC: {
                        "availability": "unavailable",
                        "reason": "HTTP 404",
                    },
                    TAG_HTTPS_GIT_SPEC: {
                        "availability": "unavailable",
                        "reason": f"tag v{PYTHON_PACKAGE_VERSION} is not published",
                    },
                    MAIN_HTTPS_GIT_SPEC: {
                        "availability": "available",
                        "reason": "git ls-remote succeeded",
                    },
                }
            ),
        },
    )

    assert result.returncode == 1

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_pip_targets = [
        entry["argv"][-1]
        for entry in entries
        if entry["managed"] and entry["argv"][:4] == ["-m", "pip", "install", "--upgrade"]
    ]

    assert managed_pip_targets == [PYPI_SPEC]
    assert (
        f"Failed to install GPD v{PYTHON_PACKAGE_VERSION} from the PyPI pinned release or tagged GitHub release sources."
        in result.stderr
    )


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_fails_closed_when_probes_mark_all_public_sources_unavailable(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        extra_env={
            "FAKE_PIP_FAIL_PYPI": "1",
            "GPD_BOOTSTRAP_TEST_PROBES": json.dumps(
                {
                    TAG_ARCHIVE_SPEC: {
                        "availability": "unavailable",
                        "reason": "HTTP 404",
                    },
                    TAG_HTTPS_GIT_SPEC: {
                        "availability": "unavailable",
                        "reason": "git exit 2",
                    },
                    MAIN_HTTPS_GIT_SPEC: {
                        "availability": "available",
                        "reason": "git ls-remote succeeded",
                    },
                }
            ),
        },
    )

    assert result.returncode == 1

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_pip_targets = [
        entry["argv"][-1]
        for entry in entries
        if entry["managed"] and entry["argv"][:4] == ["-m", "pip", "install", "--upgrade"]
    ]

    assert managed_pip_targets == [PYPI_SPEC]
    assert f"Failed to install GPD v{PYTHON_PACKAGE_VERSION}" in result.stderr


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_fails_closed_when_all_release_sources_fail(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        extra_env={
            "FAKE_PIP_FAIL_PYPI": "1",
            "FAKE_PIP_FAIL_TAG_ARCHIVE": "1",
            "FAKE_PIP_FAIL_TAG_GIT": "1",
        },
    )

    assert result.returncode == 1

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    managed_pip_targets = [
        entry["argv"][-1]
        for entry in entries
        if entry["managed"] and entry["argv"][:4] == ["-m", "pip", "install", "--upgrade"]
    ]

    assert managed_pip_targets == [
        PYPI_SPEC,
        TAG_ARCHIVE_SPEC,
        TAG_HTTPS_GIT_SPEC,
    ]
    _assert_forbidden(result.stdout, "bootstrap release failure no main fallback", "current main branch source archive")
    assert (
        f"Failed to install GPD v{PYTHON_PACKAGE_VERSION} from the PyPI pinned release or tagged GitHub release sources."
        in result.stderr
    )
    _assert_forbidden(
        result.stderr,
        "bootstrap release failure hides raw pip resolver noise",
        "Could not find a version that satisfies the requirement",
    )


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_prefers_versioned_python_when_generic_alias_is_newer(tmp_path: Path) -> None:
    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        python_versions={
            "python3": "Python 3.14.3",
            "python": "Python 3.14.3",
            "python3.13": "Python 3.13.2",
        },
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    venv_creations = [
        entry for entry in entries if entry["argv"][:2] == ["-m", "venv"] and entry["argv"] != ["-m", "venv", "--help"]
    ]

    assert len(venv_creations) == 1
    assert venv_creations[0]["exe"].endswith("python3.13")
    assert "Found Python 3.13.2" in result.stdout
    assert "Found Python 3.14.3" not in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_preferred_interpreter_selection_comes_from_generated_metadata(tmp_path: Path) -> None:
    metadata_payload = json.loads(json.dumps(_BOOTSTRAP_INSTALLER_METADATA_PAYLOAD))
    python_compatibility = metadata_payload["python_compatibility"]
    assert isinstance(python_compatibility, dict)
    minimum_supported_python = python_compatibility["minimum_supported_python"]
    assert isinstance(minimum_supported_python, dict)
    assert minimum_supported_python["major"] == 3
    python_compatibility["preferred_versioned_python_minors"] = [12, 13, minimum_supported_python["minor"]]
    python_compatibility["recommended_python_version"] = {"major": 3, "minor": 12}

    result, _, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        metadata_payload=metadata_payload,
        python_versions={
            "python3.13": "Python 3.13.2",
            "python3.12": "Python 3.12.9",
            "python3": "Python 3.13.2",
            "python": "Python 3.13.2",
        },
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    venv_creations = [
        entry for entry in entries if entry["argv"][:2] == ["-m", "venv"] and entry["argv"] != ["-m", "venv", "--help"]
    ]

    assert len(venv_creations) == 1
    assert venv_creations[0]["exe"].endswith("python3.12")
    assert "Found Python 3.12.9" in result.stdout
    assert "Found Python 3.13.2" not in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="bootstrap installer harness uses POSIX-style fake Python shims")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bootstrap installer tests")
def test_bootstrap_recreates_managed_env_when_selected_minor_changes(tmp_path: Path) -> None:
    result, home, log_path = _run_bootstrap_with_fake_python(
        tmp_path,
        python_versions={
            "python3": "Python 3.14.3",
            "python": "Python 3.14.3",
            "python3.13": "Python 3.13.2",
        },
        precreate_managed_version="Python 3.14.3",
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    venv_creations = [
        entry for entry in entries if entry["argv"][:2] == ["-m", "venv"] and entry["argv"] != ["-m", "venv", "--help"]
    ]

    assert len(venv_creations) == 1
    assert venv_creations[0]["exe"].endswith("python3.13")
    assert "switching to Python 3.13.2" in result.stdout
    assert (home / MANAGED_HOME_DIRNAME / "venv" / "bin" / "python").exists()
