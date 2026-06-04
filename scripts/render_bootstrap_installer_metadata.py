"""Render the checked-in metadata consumed by the Node bootstrap installer."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parent.parent
    sys.path[:0] = [str(repo_root), str(repo_root / "src")]

from gpd._python_compat import (
    MIN_SUPPORTED_PYTHON,
    MIN_SUPPORTED_PYTHON_LABEL,
    PREFERRED_VERSIONED_PYTHON_MINORS,
    RECOMMENDED_PYTHON_VERSION,
)
from gpd.adapters.runtime_catalog import (
    GlobalConfigPolicy,
    RuntimeDescriptor,
    get_shared_install_metadata,
    iter_runtime_descriptors,
)
from gpd.core.public_surface_contract import PublicSurfaceContract, load_public_surface_contract
from scripts.generated_region_support import GeneratedRegionDiff, unified_diff_text, write_stale_check_result

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALLER_METADATA_PATH = REPO_ROOT / "src" / "gpd" / "bootstrap" / "installer_metadata.json"
SOURCE_PATHS = (
    Path("src/gpd/adapters/runtime_catalog.json"),
    Path("src/gpd/adapters/runtime_catalog_schema.json"),
    Path("src/gpd/core/public_surface_contract.json"),
    Path("src/gpd/core/public_surface_contract_schema.json"),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_hashes(*, repo_root: Path = REPO_ROOT) -> dict[str, str]:
    return {relative_path.as_posix(): _sha256(repo_root / relative_path) for relative_path in SOURCE_PATHS}


def _without_none(payload: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if value is not None}


def _global_config_payload(policy: GlobalConfigPolicy) -> dict[str, object]:
    return _without_none(asdict(policy))


def _python_version_payload(version: tuple[int, int]) -> dict[str, int]:
    major, minor = version
    return {"major": major, "minor": minor}


def _python_compatibility_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "minimum_supported_python": _python_version_payload(MIN_SUPPORTED_PYTHON),
        "minimum_supported_python_label": MIN_SUPPORTED_PYTHON_LABEL,
        "preferred_versioned_python_minors": list(PREFERRED_VERSIONED_PYTHON_MINORS),
        "recommended_python_version": _python_version_payload(RECOMMENDED_PYTHON_VERSION),
    }


def _runtime_payload(descriptor: RuntimeDescriptor) -> dict[str, object]:
    return {
        "runtime_name": descriptor.runtime_name,
        "display_name": descriptor.display_name,
        "priority": descriptor.priority,
        "config_dir_name": descriptor.config_dir_name,
        "install_flag": descriptor.install_flag,
        "launch_command": descriptor.launch_command,
        "selection_flags": list(descriptor.selection_flags),
        "selection_aliases": list(descriptor.selection_aliases),
        "command_prefix": descriptor.command_prefix,
        "public_command_surface_prefix": descriptor.public_command_surface_prefix,
        "installer_help_example_scope": descriptor.installer_help_example_scope,
        "global_config": _global_config_payload(descriptor.global_config),
    }


def _shared_install_metadata_payload() -> dict[str, object]:
    metadata = get_shared_install_metadata()
    return {
        "schemaVersion": 1,
        "bootstrapPackageName": metadata.bootstrap_package_name,
        "bootstrapCommand": metadata.bootstrap_command,
        "installRootDirName": metadata.install_root_dir_name,
        "manifestName": metadata.manifest_name,
        "patchesDirName": metadata.patches_dir_name,
    }


def _shared_public_surface_text(contract: PublicSurfaceContract) -> dict[str, object]:
    beginner = contract.beginner_onboarding
    bridge = contract.local_cli_bridge
    named_commands = bridge.named_commands
    settings = contract.post_start_settings
    resume_authority = contract.resume_authority
    recovery = contract.recovery_ladder

    return {
        "schemaVersion": 1,
        "beginnerHubUrl": beginner.hub_url,
        "beginnerPreflightRequirements": list(beginner.preflight_requirements),
        "beginnerCaveats": list(beginner.caveats),
        "beginnerStartupLadder": list(beginner.startup_ladder),
        "localCliBridgeCommands": list(named_commands.ordered()),
        "localCliBridge": {
            "doctorCommand": named_commands.doctor,
            "helpCommand": named_commands.help,
            "permissionsStatusCommand": named_commands.permissions_status,
            "permissionsSyncCommand": named_commands.permissions_sync,
            "resumeCommand": named_commands.resume,
            "resumeRecentCommand": named_commands.resume_recent,
            "observeExecutionCommand": named_commands.observe_execution,
            "costCommand": named_commands.cost,
            "presetsListCommand": named_commands.presets_list,
            "planPreflightCommand": named_commands.plan_preflight,
            "integrationsStatusWolframCommand": named_commands.integrations_status_wolfram,
            "terminalPhrase": bridge.terminal_phrase,
            "purposePhrase": bridge.purpose_phrase,
            "installLocalExample": bridge.install_local_example,
            "doctorLocalCommand": bridge.doctor_local_command,
            "doctorGlobalCommand": bridge.doctor_global_command,
            "validateCommandContextCommand": bridge.validate_command_context_command,
            "unattendedReadinessCommand": named_commands.unattended_readiness,
        },
        "resumeAuthority": {
            "durableAuthorityPhrase": resume_authority.durable_authority_phrase,
            "publicVocabularyIntro": resume_authority.public_vocabulary_intro,
            "publicFields": list(resume_authority.public_fields),
        },
        "recoveryLadder": {
            "title": recovery.title,
            "localSnapshotCommand": recovery.local_snapshot_command,
            "localSnapshotPhrase": recovery.local_snapshot_phrase,
            "crossWorkspaceCommand": recovery.cross_workspace_command,
            "crossWorkspacePhrase": recovery.cross_workspace_phrase,
            "resumePhrase": recovery.resume_phrase,
            "nextPhrase": recovery.next_phrase,
            "pausePhrase": recovery.pause_phrase,
        },
        "settingsCommandSentence": settings.primary_sentence,
        "settingsRecommendationSentence": settings.default_sentence,
    }


def build_installer_metadata(*, repo_root: Path = REPO_ROOT) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source_hashes": _source_hashes(repo_root=repo_root),
        "python_compatibility": _python_compatibility_payload(),
        "runtimes": [_runtime_payload(descriptor) for descriptor in iter_runtime_descriptors()],
        "shared_install_metadata": _shared_install_metadata_payload(),
        "shared_public_surface_text": _shared_public_surface_text(load_public_surface_contract()),
    }


def render_installer_metadata_text(*, repo_root: Path = REPO_ROOT) -> str:
    return json.dumps(build_installer_metadata(repo_root=repo_root), indent=2, ensure_ascii=True) + "\n"


def check_installer_metadata(
    *,
    path: Path = INSTALLER_METADATA_PATH,
    repo_root: Path = REPO_ROOT,
) -> tuple[GeneratedRegionDiff, ...]:
    expected = render_installer_metadata_text(repo_root=repo_root)
    try:
        actual = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        actual = ""
    if actual == expected:
        return ()
    return (
        GeneratedRegionDiff(
            path=path,
            block_id="installer-metadata",
            diff=unified_diff_text(expected, actual, path=path, block_id="installer-metadata"),
        ),
    )


def write_installer_metadata(*, path: Path = INSTALLER_METADATA_PATH, repo_root: Path = REPO_ROOT) -> bool:
    expected = render_installer_metadata_text(repo_root=repo_root)
    try:
        actual = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        actual = ""
    if actual == expected:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(expected, encoding="utf-8")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify generated bootstrap installer metadata without modifying files",
    )
    args = parser.parse_args(argv)

    if args.check:
        diffs = check_installer_metadata()
        if diffs:
            return write_stale_check_result(
                diffs,
                heading="Bootstrap installer metadata is stale.",
                regenerate_command="uv run python scripts/render_bootstrap_installer_metadata.py",
            )
        return 0

    if write_installer_metadata():
        print(INSTALLER_METADATA_PATH.relative_to(REPO_ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
