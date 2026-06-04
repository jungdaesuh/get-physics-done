from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from gpd._python_compat import (
    MIN_SUPPORTED_PYTHON,
    MIN_SUPPORTED_PYTHON_LABEL,
    PREFERRED_VERSIONED_PYTHON_MINORS,
    RECOMMENDED_PYTHON_VERSION,
)
from gpd.adapters.runtime_catalog import get_shared_install_metadata, iter_runtime_descriptors
from gpd.core.public_surface_contract import load_public_surface_contract
from scripts.render_bootstrap_installer_metadata import (
    INSTALLER_METADATA_PATH,
    REPO_ROOT,
    SOURCE_PATHS,
    build_installer_metadata,
    check_installer_metadata,
)


def _load_metadata() -> dict[str, object]:
    return json.loads(INSTALLER_METADATA_PATH.read_text(encoding="utf-8"))


def test_bootstrap_installer_metadata_is_current() -> None:
    metadata = _load_metadata()

    assert check_installer_metadata() == ()
    assert metadata == build_installer_metadata()
    assert list(metadata) == [
        "schema_version",
        "source_hashes",
        "python_compatibility",
        "runtimes",
        "shared_install_metadata",
        "shared_public_surface_text",
    ]
    assert metadata["schema_version"] == 1


def test_bootstrap_installer_python_compatibility_metadata_matches_source_of_truth() -> None:
    metadata = _load_metadata()

    assert metadata["python_compatibility"] == {
        "schema_version": 1,
        "minimum_supported_python": {
            "major": MIN_SUPPORTED_PYTHON[0],
            "minor": MIN_SUPPORTED_PYTHON[1],
        },
        "minimum_supported_python_label": MIN_SUPPORTED_PYTHON_LABEL,
        "preferred_versioned_python_minors": list(PREFERRED_VERSIONED_PYTHON_MINORS),
        "recommended_python_version": {
            "major": RECOMMENDED_PYTHON_VERSION[0],
            "minor": RECOMMENDED_PYTHON_VERSION[1],
        },
    }


def test_bootstrap_installer_metadata_source_hashes_match_checked_in_sources() -> None:
    metadata = _load_metadata()
    source_hashes = metadata["source_hashes"]

    assert isinstance(source_hashes, dict)
    assert tuple(source_hashes) == tuple(path.as_posix() for path in SOURCE_PATHS)
    for relative_path in SOURCE_PATHS:
        digest = hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest()
        assert source_hashes[relative_path.as_posix()] == digest


def test_bootstrap_installer_runtime_metadata_contains_only_node_consumed_fields() -> None:
    metadata = _load_metadata()
    runtimes = metadata["runtimes"]
    descriptors = iter_runtime_descriptors()
    expected_keys = {
        "runtime_name",
        "display_name",
        "priority",
        "config_dir_name",
        "install_flag",
        "launch_command",
        "selection_flags",
        "selection_aliases",
        "command_prefix",
        "public_command_surface_prefix",
        "installer_help_example_scope",
        "global_config",
    }
    excluded_keys = {
        "adapter_module",
        "adapter_class",
        "activation_env_vars",
        "capabilities",
        "hook_payload",
        "managed_install_surface",
        "manifest_file_prefixes",
        "manifest_metadata_list_policies",
        "native_include_support",
        "agent_prompt_uses_dollar_templates",
        "validated_command_surface",
    }

    assert isinstance(runtimes, list)
    assert [runtime["runtime_name"] for runtime in runtimes] == [descriptor.runtime_name for descriptor in descriptors]
    for runtime_payload, descriptor in zip(runtimes, descriptors, strict=True):
        assert set(runtime_payload) == expected_keys
        assert set(runtime_payload).isdisjoint(excluded_keys)
        assert runtime_payload["display_name"] == descriptor.display_name
        assert runtime_payload["priority"] == descriptor.priority
        assert runtime_payload["config_dir_name"] == descriptor.config_dir_name
        assert runtime_payload["install_flag"] == descriptor.install_flag
        assert runtime_payload["launch_command"] == descriptor.launch_command
        assert runtime_payload["selection_flags"] == list(descriptor.selection_flags)
        assert runtime_payload["selection_aliases"] == list(descriptor.selection_aliases)
        assert runtime_payload["command_prefix"] == descriptor.command_prefix
        assert runtime_payload["public_command_surface_prefix"] == descriptor.public_command_surface_prefix
        assert runtime_payload["installer_help_example_scope"] == descriptor.installer_help_example_scope
        assert runtime_payload["global_config"] == {
            key: value for key, value in asdict(descriptor.global_config).items() if value is not None
        }


def test_bootstrap_installer_shared_install_metadata_matches_node_loader_shape() -> None:
    metadata = _load_metadata()
    install_metadata = metadata["shared_install_metadata"]
    shared_install = get_shared_install_metadata()

    assert list(install_metadata) == [
        "schemaVersion",
        "bootstrapPackageName",
        "bootstrapCommand",
        "installRootDirName",
        "manifestName",
        "patchesDirName",
    ]
    assert install_metadata == {
        "schemaVersion": 1,
        "bootstrapPackageName": shared_install.bootstrap_package_name,
        "bootstrapCommand": shared_install.bootstrap_command,
        "installRootDirName": shared_install.install_root_dir_name,
        "manifestName": shared_install.manifest_name,
        "patchesDirName": shared_install.patches_dir_name,
    }

def test_bootstrap_installer_public_surface_text_matches_node_loader_shape() -> None:
    metadata = _load_metadata()
    public_surface_text = metadata["shared_public_surface_text"]
    contract = load_public_surface_contract()
    beginner = contract.beginner_onboarding
    bridge = contract.local_cli_bridge
    named_commands = bridge.named_commands
    settings = contract.post_start_settings
    resume_authority = contract.resume_authority
    recovery = contract.recovery_ladder

    assert list(public_surface_text) == [
        "schemaVersion",
        "beginnerHubUrl",
        "beginnerPreflightRequirements",
        "beginnerCaveats",
        "beginnerStartupLadder",
        "localCliBridgeCommands",
        "localCliBridge",
        "resumeAuthority",
        "recoveryLadder",
        "settingsCommandSentence",
        "settingsRecommendationSentence",
    ]
    assert public_surface_text == {
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
