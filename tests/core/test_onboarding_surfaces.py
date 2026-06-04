from __future__ import annotations

import copy
import dataclasses
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from gpd.adapters import iter_runtime_descriptors
from gpd.adapters.install_utils import expand_at_includes
from gpd.command_labels import validated_public_command_prefix
from gpd.core import onboarding_surfaces as onboarding_surfaces_module
from gpd.core import public_surface_contract as public_surface_contract_module
from gpd.core.onboarding_surfaces import (
    BeginnerRuntimeSurface,
    beginner_onboarding_hub_url,
    beginner_runtime_surface,
    beginner_runtime_surfaces,
    beginner_startup_ladder_text,
)
from gpd.core.public_surface_contract import (
    beginner_onboarding_caveats,
    beginner_preflight_requirements,
    load_public_surface_contract,
    local_cli_bridge_note,
    local_cli_doctor_command,
    local_cli_help_command,
    local_cli_permissions_sync_command,
    local_cli_unattended_readiness_command,
    recovery_cross_workspace_command,
    recovery_local_snapshot_command,
    resume_authority_contract,
    resume_authority_fields,
)
from tests import doc_surface_contracts as doc_surface_contracts_module
from tests.assertion_taxonomy_support import FragmentMode, MatchMode, semantic_anchor
from tests.workflow_authority_support import workflow_authority_text


@pytest.fixture(autouse=True)
def _clear_public_surface_contract_caches() -> Iterator[None]:
    load_public_surface_contract.cache_clear()
    doc_surface_contracts_module._public_surface_contract_payload.cache_clear()
    yield
    load_public_surface_contract.cache_clear()
    doc_surface_contracts_module._public_surface_contract_payload.cache_clear()


def _public_surface_contract_files(contract_path: Path, schema_path: Path) -> object:
    class _FakeFiles:
        def __init__(self, contract_path: Path, schema_path: Path) -> None:
            self._contract_path = contract_path
            self._schema_path = schema_path

        def joinpath(self, name: str) -> Path:
            if name == "public_surface_contract.json":
                return self._contract_path
            if name == "public_surface_contract_schema.json":
                return self._schema_path
            raise AssertionError(f"Unexpected public surface contract resource: {name}")

    return _FakeFiles(contract_path, schema_path)


def _load_public_surface_contract_with_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: dict[str, object],
    schema_payload: dict[str, object] | None = None,
) -> None:
    contract_path = tmp_path / "public_surface_contract.json"
    schema_path = tmp_path / "public_surface_contract_schema.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")
    schema_payload = schema_payload or json.loads(
        (
            Path(public_surface_contract_module.__file__).resolve().with_name("public_surface_contract_schema.json")
        ).read_text(encoding="utf-8")
    )
    schema_path.write_text(json.dumps(schema_payload), encoding="utf-8")
    monkeypatch.setattr(
        public_surface_contract_module,
        "files",
        lambda package: _public_surface_contract_files(contract_path, schema_path),
    )
    load_public_surface_contract.cache_clear()


def _expected_beginner_runtime_surface(descriptor: object) -> BeginnerRuntimeSurface:
    public_prefix = validated_public_command_prefix(descriptor)
    return BeginnerRuntimeSurface(
        runtime_name=descriptor.runtime_name,
        display_name=descriptor.display_name,
        install_flag=descriptor.install_flag,
        launch_command=descriptor.launch_command,
        help_command=f"{public_prefix}help",
        start_command=f"{public_prefix}start",
        tour_command=f"{public_prefix}tour",
        new_project_command=f"{public_prefix}new-project",
        new_project_minimal_command=f"{public_prefix}new-project --minimal",
        map_research_command=f"{public_prefix}map-research",
        resume_work_command=f"{public_prefix}resume-work",
        settings_command=f"{public_prefix}settings",
    )


def _assert_anchor(text: str, label: str, fragments: tuple[str, ...] | str) -> None:
    semantic_anchor(label, fragments, match=MatchMode.CASEFOLD_NORMALIZED).check(text)


def _assert_absent(text: str, label: str, fragments: tuple[str, ...] | str) -> None:
    semantic_anchor(
        label,
        fragments,
        mode=FragmentMode.ABSENT,
        match=MatchMode.CASEFOLD_NORMALIZED,
    ).check(text)


def test_beginner_onboarding_surface_contract_exposes_hub_and_ladder() -> None:
    preflight = beginner_preflight_requirements()
    caveats = beginner_onboarding_caveats()

    assert beginner_onboarding_hub_url() == "https://github.com/psi-oss/get-physics-done/tree/main/docs"
    assert "blob/main" not in beginner_onboarding_hub_url()
    assert beginner_startup_ladder_text() == "`help -> start -> tour -> new-project / map-research -> resume-work`"
    assert len(preflight) == 3
    assert len(caveats) == 5
    _assert_anchor(
        "\n".join(preflight),
        "beginner preflight requirements",
        ("supported runtime", "normal terminal", "Node.js 20+", "Python 3.11+", "`venv`"),
    )
    _assert_anchor(
        "\n".join(caveats),
        "beginner onboarding caveats",
        (
            "not a standalone app",
            "does not install your runtime",
            "model access",
            "billing",
            "API credits",
            "beginner path",
            "not the full reference",
            "evidence",
            "references",
            "artifacts",
            "not invent",
        ),
    )


def test_beginner_startup_ladder_stays_separate_from_deeper_recovery_follow_ups() -> None:
    startup_ladder = beginner_startup_ladder_text()

    assert startup_ladder.endswith("resume-work`")
    _assert_absent(
        startup_ladder,
        "beginner startup ladder excludes deeper recovery and readiness details",
        ("suggest-next", "pause-work", "Node", "Python", "--local", "standalone", "billing"),
    )


def test_public_surface_contract_rejects_recovery_ladder_command_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = json.loads(
        Path(public_surface_contract_module.__file__).with_name("public_surface_contract.json").read_text()
    )
    payload["recovery_ladder"]["local_snapshot_command"] = payload["local_cli_bridge"]["named_commands"]["help"]
    _load_public_surface_contract_with_payload(monkeypatch, tmp_path, payload)

    with pytest.raises(
        ValueError,
        match="recovery_ladder\\.local_snapshot_command must equal local_cli_bridge\\.named_commands\\.resume",
    ):
        load_public_surface_contract()


@pytest.mark.parametrize(
    ("field_name", "command_fragment"),
    [
        ("install_local_example", "gpd install <runtime> --local"),
        ("doctor_local_command", "gpd doctor --runtime <runtime> --local"),
        ("doctor_global_command", "gpd doctor --runtime <runtime> --global"),
        ("validate_command_context_command", "gpd validate command-context <name>"),
    ],
)
def test_public_surface_contract_loader_rejects_local_cli_bridge_command_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field_name: str,
    command_fragment: str,
) -> None:
    payload = json.loads(
        Path(public_surface_contract_module.__file__)
        .resolve()
        .with_name("public_surface_contract.json")
        .read_text(encoding="utf-8")
    )
    payload["local_cli_bridge"][field_name] = f"{command_fragment} --drifted"
    _load_public_surface_contract_with_payload(monkeypatch, tmp_path, payload)

    with pytest.raises(ValueError, match=r"local_cli_bridge\.[a-z_]+ must equal"):
        load_public_surface_contract()


def test_beginner_runtime_surfaces_follow_runtime_catalog() -> None:
    surfaces = beginner_runtime_surfaces()
    descriptors = iter_runtime_descriptors()

    assert tuple(surface.runtime_name for surface in surfaces) == tuple(
        descriptor.runtime_name for descriptor in descriptors
    )

    for descriptor, surface in zip(descriptors, surfaces, strict=True):
        assert surface == _expected_beginner_runtime_surface(descriptor)


def test_beginner_runtime_surface_single_lookup_matches_bulk_surface() -> None:
    for surface in beginner_runtime_surfaces():
        assert beginner_runtime_surface(surface.runtime_name) == surface


def test_beginner_runtime_surface_accepts_display_names_and_aliases() -> None:
    for descriptor in iter_runtime_descriptors():
        assert beginner_runtime_surface(descriptor.display_name) == _expected_beginner_runtime_surface(descriptor)
        assert beginner_runtime_surface(descriptor.selection_aliases[0]) == _expected_beginner_runtime_surface(
            descriptor
        )


def test_beginner_runtime_surface_single_lookup_uses_descriptor_public_surface_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_name = iter_runtime_descriptors()[0].runtime_name
    descriptor = SimpleNamespace(
        runtime_name=runtime_name,
        display_name="Descriptor Display",
        install_flag="--descriptor",
        launch_command="descriptor-launch",
        command_prefix="/adapter:",
        public_command_surface_prefix="/public:",
    )

    def _boom() -> tuple[object, ...]:
        raise AssertionError("single runtime lookup should not scan the runtime catalog")

    def _get_runtime_descriptor(name: str) -> object:
        assert name == runtime_name
        return descriptor

    monkeypatch.setattr(onboarding_surfaces_module, "iter_runtime_descriptors", _boom)
    monkeypatch.setattr(onboarding_surfaces_module, "get_runtime_descriptor", _get_runtime_descriptor)

    surface = onboarding_surfaces_module.beginner_runtime_surface(runtime_name)

    assert surface == BeginnerRuntimeSurface(
        runtime_name=runtime_name,
        display_name="Descriptor Display",
        install_flag="--descriptor",
        launch_command="descriptor-launch",
        help_command="/public:help",
        start_command="/public:start",
        tour_command="/public:tour",
        new_project_command="/public:new-project",
        new_project_minimal_command="/public:new-project --minimal",
        map_research_command="/public:map-research",
        resume_work_command="/public:resume-work",
        settings_command="/public:settings",
    )


def test_beginner_runtime_surface_requires_descriptor_public_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_name = iter_runtime_descriptors()[0].runtime_name
    descriptor = SimpleNamespace(
        runtime_name=runtime_name,
        display_name="Descriptor Display",
        install_flag="--descriptor",
        launch_command="descriptor-launch",
        command_prefix="/adapter:",
        public_command_surface_prefix="",
    )

    monkeypatch.setattr(onboarding_surfaces_module, "get_runtime_descriptor", lambda name: descriptor)

    with pytest.raises(ValueError, match="missing a public command surface prefix"):
        onboarding_surfaces_module.beginner_runtime_surface(runtime_name)


def test_resume_authority_contract_exposes_full_validated_surface() -> None:
    contract = resume_authority_contract()

    assert "canonical continuation fields" in contract.public_vocabulary_intro.casefold()
    assert contract.public_fields == resume_authority_fields()
    assert not hasattr(contract, "top_level_boundary_phrase")
    assert not hasattr(contract, "compat_surface")
    assert not hasattr(contract, "session_mirror")
    assert not hasattr(contract, "compatibility_phrase")


def test_resume_authority_helper_rejects_extraneous_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_section = {
        "durable_authority_phrase": "`state.json.continuation` is the durable authority",
        "public_vocabulary_intro": "Canonical continuation fields define the public resume vocabulary",
        "public_fields": [
            "active_resume_kind",
            "active_resume_origin",
            "active_resume_pointer",
        ],
        "compat_surface": "unexpected extra key",
        "session_mirror": "unexpected extra key",
        "compatibility_phrase": "unexpected extra key",
    }

    monkeypatch.setattr(doc_surface_contracts_module, "_contract_section", lambda name: dict(fake_section))

    with pytest.raises(AssertionError):
        doc_surface_contracts_module._resume_authority_contract()


def test_public_surface_contract_loader_rejects_additive_keys(monkeypatch, tmp_path: Path) -> None:
    canonical_path = Path(__file__).resolve().parents[2] / "src" / "gpd" / "core" / "public_surface_contract.json"
    canonical_payload = json.loads(canonical_path.read_text(encoding="utf-8"))
    additive_payload = copy.deepcopy(canonical_payload)
    additive_payload["legacy_note"] = "unexpected"

    _load_public_surface_contract_with_payload(monkeypatch, tmp_path, additive_payload)
    with pytest.raises(ValueError, match=r"public_surface_contract contains unknown key\(s\): legacy_note"):
        load_public_surface_contract()
    load_public_surface_contract.cache_clear()


def test_public_surface_contract_loader_rejects_schema_key_drift_after_cache_clear_without_fresh_import_hack(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    canonical_payload = json.loads(
        (Path(public_surface_contract_module.__file__).resolve().with_name("public_surface_contract.json")).read_text(
            encoding="utf-8"
        )
    )
    canonical_schema = json.loads(
        (
            Path(public_surface_contract_module.__file__).resolve().with_name("public_surface_contract_schema.json")
        ).read_text(encoding="utf-8")
    )
    refreshed_payload = copy.deepcopy(canonical_payload)
    refreshed_schema = copy.deepcopy(canonical_schema)
    refreshed_payload["beginner_onboarding"]["legacy_note"] = "unexpected"
    refreshed_schema["sections"]["beginner_onboarding"]["keys"].append("legacy_note")

    _load_public_surface_contract_with_payload(
        monkeypatch,
        tmp_path,
        refreshed_payload,
        refreshed_schema,
    )

    with pytest.raises(
        ValueError,
        match=(
            r"public_surface_contract_schema\.sections\.beginner_onboarding\.keys must exactly match "
            r"the code-supported contract fields"
        ),
    ):
        load_public_surface_contract()
    load_public_surface_contract.cache_clear()


def test_public_surface_contract_schema_keeps_v1_local_cli_command_values_for_external_consumers() -> None:
    schema = json.loads(
        (
            Path(public_surface_contract_module.__file__).resolve().with_name("public_surface_contract_schema.json")
        ).read_text(encoding="utf-8")
    )

    local_cli_bridge_schema = schema["sections"]["local_cli_bridge"]
    assert local_cli_bridge_schema["keys"][0] == "commands"


def test_public_surface_contract_bridge_commands_match_named_command_order() -> None:
    canonical_payload = json.loads(
        (Path(public_surface_contract_module.__file__).resolve().with_name("public_surface_contract.json")).read_text(
            encoding="utf-8"
        )
    )
    canonical_schema = json.loads(
        (
            Path(public_surface_contract_module.__file__).resolve().with_name("public_surface_contract_schema.json")
        ).read_text(encoding="utf-8")
    )
    ordered_keys = canonical_schema["sections"]["local_cli_bridge"]["named_commands"]["ordered_keys"]
    expected_commands = tuple(canonical_payload["local_cli_bridge"]["named_commands"][key] for key in ordered_keys)

    contract = load_public_surface_contract()

    assert tuple(canonical_payload["local_cli_bridge"]["commands"]) == expected_commands
    assert contract.local_cli_bridge.commands == expected_commands
    assert contract.local_cli_bridge.commands == contract.local_cli_bridge.named_commands.ordered()


@pytest.mark.parametrize(
    ("section_name", "expected_message"),
    [
        ("beginner_onboarding", r"beginner_onboarding contains unknown key\(s\): legacy_note"),
        ("local_cli_bridge", r"local_cli_bridge contains unknown key\(s\): legacy_note"),
        ("post_start_settings", r"post_start_settings contains unknown key\(s\): legacy_note"),
        ("resume_authority", r"resume_authority contains unknown key\(s\): legacy_note"),
        ("recovery_ladder", r"recovery_ladder contains unknown key\(s\): legacy_note"),
    ],
)
def test_public_surface_contract_loader_rejects_section_additive_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    section_name: str,
    expected_message: str,
) -> None:
    canonical_path = Path(__file__).resolve().parents[2] / "src" / "gpd" / "core" / "public_surface_contract.json"
    canonical_payload = json.loads(canonical_path.read_text(encoding="utf-8"))
    additive_payload = copy.deepcopy(canonical_payload)
    additive_payload[section_name]["legacy_note"] = "unexpected"

    _load_public_surface_contract_with_payload(monkeypatch, tmp_path, additive_payload)
    with pytest.raises(ValueError, match=expected_message):
        load_public_surface_contract()
    load_public_surface_contract.cache_clear()


def test_public_surface_contract_bridge_note_surfaces_runtime_readiness_and_plan_validation() -> None:
    note = local_cli_bridge_note()
    commands = public_surface_contract_module.local_cli_bridge_commands()

    assert public_surface_contract_module.local_cli_bridge_purpose_phrase() in note
    assert "gpd doctor --runtime <runtime> --local" not in note
    assert "gpd doctor --runtime <runtime> --global" not in note
    assert "gpd validate plan-preflight <PLAN.md>" not in note
    assert "gpd validate plan-preflight <PLAN.md>" in commands
    assert public_surface_contract_module.local_cli_unattended_readiness_command() in commands
    assert public_surface_contract_module.local_cli_doctor_local_command() == "gpd doctor --runtime <runtime> --local"
    assert public_surface_contract_module.local_cli_doctor_global_command() == "gpd doctor --runtime <runtime> --global"
    assert "gpd validate plan-preflight <PLAN.md>" in public_surface_contract_module.local_cli_plan_preflight_command()
    assert (
        public_surface_contract_module.local_cli_validate_command_context_command()
        == "gpd validate command-context <name>"
    )


def test_public_surface_contract_loader_normalizes_whitespace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    canonical_path = Path(__file__).resolve().parents[2] / "src" / "gpd" / "core" / "public_surface_contract.json"
    canonical_payload = json.loads(canonical_path.read_text(encoding="utf-8"))
    noisy_payload = copy.deepcopy(canonical_payload)

    noisy_payload["beginner_onboarding"]["hub_url"] = f"  {canonical_payload['beginner_onboarding']['hub_url']}  "
    noisy_payload["beginner_onboarding"]["startup_ladder"] = [
        f"  {canonical_payload['beginner_onboarding']['startup_ladder'][0]}  ",
        *canonical_payload["beginner_onboarding"]["startup_ladder"][1:],
    ]
    noisy_payload["local_cli_bridge"]["named_commands"]["help"] = (
        f"  {canonical_payload['local_cli_bridge']['named_commands']['help']}  "
    )
    noisy_payload["local_cli_bridge"]["named_commands"]["doctor"] = (
        f"  {canonical_payload['local_cli_bridge']['named_commands']['doctor']}  "
    )
    noisy_payload["post_start_settings"]["primary_sentence"] = (
        f"  {canonical_payload['post_start_settings']['primary_sentence']}  "
    )
    noisy_payload["resume_authority"]["public_fields"] = [
        canonical_payload["resume_authority"]["public_fields"][0],
        f"  {canonical_payload['resume_authority']['public_fields'][1]}  ",
        *canonical_payload["resume_authority"]["public_fields"][2:],
    ]
    noisy_payload["recovery_ladder"]["title"] = f"  {canonical_payload['recovery_ladder']['title']}  "

    _load_public_surface_contract_with_payload(monkeypatch, tmp_path, noisy_payload)
    contract = load_public_surface_contract()

    assert contract.beginner_onboarding.hub_url == canonical_payload["beginner_onboarding"]["hub_url"]
    assert contract.beginner_onboarding.startup_ladder == tuple(
        canonical_payload["beginner_onboarding"]["startup_ladder"]
    )
    assert contract.local_cli_bridge.commands == contract.local_cli_bridge.named_commands.ordered()
    assert (
        contract.local_cli_bridge.named_commands.help == canonical_payload["local_cli_bridge"]["named_commands"]["help"]
    )
    assert (
        contract.local_cli_bridge.named_commands.doctor
        == canonical_payload["local_cli_bridge"]["named_commands"]["doctor"]
    )
    assert contract.post_start_settings.primary_sentence == canonical_payload["post_start_settings"]["primary_sentence"]
    assert contract.resume_authority.public_fields == tuple(canonical_payload["resume_authority"]["public_fields"])
    assert contract.recovery_ladder.title == canonical_payload["recovery_ladder"]["title"]
    load_public_surface_contract.cache_clear()


def test_public_surface_contract_loader_rejects_duplicate_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    canonical_path = Path(__file__).resolve().parents[2] / "src" / "gpd" / "core" / "public_surface_contract.json"
    canonical_payload = json.loads(canonical_path.read_text(encoding="utf-8"))
    duplicate_payload = copy.deepcopy(canonical_payload)
    duplicate_payload["local_cli_bridge"]["named_commands"]["doctor"] = canonical_payload["local_cli_bridge"][
        "named_commands"
    ]["help"]

    _load_public_surface_contract_with_payload(monkeypatch, tmp_path, duplicate_payload)
    with pytest.raises(ValueError, match=r"local_cli_bridge\.named_commands must not contain duplicate command values"):
        load_public_surface_contract()

    load_public_surface_contract.cache_clear()


def test_public_surface_contract_loader_rejects_missing_required_fields(monkeypatch, tmp_path: Path) -> None:
    canonical_path = Path(__file__).resolve().parents[2] / "src" / "gpd" / "core" / "public_surface_contract.json"
    canonical_payload = json.loads(canonical_path.read_text(encoding="utf-8"))
    missing_payload = copy.deepcopy(canonical_payload)
    del missing_payload["resume_authority"]["public_vocabulary_intro"]

    _load_public_surface_contract_with_payload(monkeypatch, tmp_path, missing_payload)
    with pytest.raises(ValueError, match=r"resume_authority is missing required key\(s\): public_vocabulary_intro"):
        load_public_surface_contract()

    load_public_surface_contract.cache_clear()


def test_public_surface_contract_loader_rejects_invalid_required_field_types(monkeypatch, tmp_path: Path) -> None:
    canonical_path = Path(__file__).resolve().parents[2] / "src" / "gpd" / "core" / "public_surface_contract.json"
    canonical_payload = json.loads(canonical_path.read_text(encoding="utf-8"))
    invalid_payload = copy.deepcopy(canonical_payload)
    invalid_payload["resume_authority"]["public_fields"] = "unexpected"

    _load_public_surface_contract_with_payload(monkeypatch, tmp_path, invalid_payload)
    with pytest.raises(ValueError, match=r"resume_authority\.public_fields must be a non-empty list"):
        load_public_surface_contract()

    load_public_surface_contract.cache_clear()


def test_public_surface_contract_loader_rejects_boolean_schema_version(monkeypatch, tmp_path: Path) -> None:
    canonical_path = Path(__file__).resolve().parents[2] / "src" / "gpd" / "core" / "public_surface_contract.json"
    canonical_payload = json.loads(canonical_path.read_text(encoding="utf-8"))
    canonical_payload["schema_version"] = True
    _load_public_surface_contract_with_payload(monkeypatch, tmp_path, canonical_payload)
    load_public_surface_contract.cache_clear()

    with pytest.raises(ValueError, match=r"Unsupported public surface contract schema_version: True"):
        load_public_surface_contract()

    load_public_surface_contract.cache_clear()


def test_doc_surface_contract_helpers_read_runtime_normalized_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = public_surface_contract_module.PublicSurfaceContract(
        beginner_onboarding=public_surface_contract_module.BeginnerOnboardingContract(
            hub_url="https://example.com/hub",
            preflight_requirements=("Preflight A",),
            caveats=("Caveat A",),
            startup_ladder=("help", "start"),
        ),
        local_cli_bridge=public_surface_contract_module.LocalCliBridgeContract(
            named_commands=public_surface_contract_module.LocalCliNamedCommandsContract(
                help="gpd --help",
                doctor="gpd doctor",
                unattended_readiness="gpd validate unattended-readiness --runtime <runtime> --autonomy balanced",
                permissions_status="gpd permissions status --runtime <runtime> --autonomy balanced",
                permissions_sync="gpd permissions sync --runtime <runtime> --autonomy balanced",
                resume="gpd resume",
                resume_recent="gpd resume --recent",
                observe_execution="gpd observe execution",
                cost="gpd cost",
                presets_list="gpd presets list",
                plan_preflight="gpd validate plan-preflight <PLAN.md>",
                integrations_status_wolfram="gpd integrations status wolfram",
            ),
            terminal_phrase="in your normal terminal",
            purpose_phrase="workspace diagnostics",
            install_local_example="gpd install <runtime> --local",
            doctor_local_command="gpd doctor --runtime <runtime> --local",
            doctor_global_command="gpd doctor --runtime <runtime> --global",
            validate_command_context_command="gpd validate command-context <name>",
        ),
        post_start_settings=public_surface_contract_module.PostStartSettingsContract(
            primary_sentence="Run settings after start.",
            default_sentence="Balanced defaults apply.",
        ),
        resume_authority=public_surface_contract_module.ResumeAuthorityContract(
            durable_authority_phrase="Durable authority phrase",
            public_vocabulary_intro="Public vocabulary intro",
            public_fields=("resume_file",),
        ),
        recovery_ladder=public_surface_contract_module.RecoveryLadderContract(
            title="Recovery ladder title",
            local_snapshot_command="gpd resume",
            local_snapshot_phrase="local snapshot",
            cross_workspace_command="resume --recent",
            cross_workspace_phrase="pick another workspace",
            resume_phrase="continue with resume-work",
            next_phrase="check suggest-next",
            pause_phrase="fresh continuation breadcrumbs",
        ),
    )
    monkeypatch.setattr(doc_surface_contracts_module, "load_public_surface_contract", lambda: contract)
    monkeypatch.setattr(public_surface_contract_module, "load_public_surface_contract", lambda: contract)
    doc_surface_contracts_module._public_surface_contract_payload.cache_clear()

    assert doc_surface_contracts_module.beginner_preflight_requirements() == ("Preflight A",)
    assert doc_surface_contracts_module.beginner_onboarding_caveats() == ("Caveat A",)
    assert doc_surface_contracts_module.beginner_startup_ladder_text() == "`help -> start`"
    assert doc_surface_contracts_module.resume_authority_public_vocabulary_intro() == "Public vocabulary intro"
    assert local_cli_help_command() == "gpd --help"
    assert local_cli_doctor_command() == "gpd doctor"
    assert doc_surface_contracts_module.DOCTOR_RUNTIME_SCOPE_RE.search(
        public_surface_contract_module.local_cli_doctor_local_command()
    )
    assert doc_surface_contracts_module.DOCTOR_RUNTIME_SCOPE_RE.search(
        public_surface_contract_module.local_cli_doctor_global_command()
    )
    assert (
        local_cli_unattended_readiness_command()
        == "gpd validate unattended-readiness --runtime <runtime> --autonomy balanced"
    )
    assert local_cli_permissions_sync_command() == "gpd permissions sync --runtime <runtime> --autonomy balanced"
    assert public_surface_contract_module.local_cli_plan_preflight_command() == "gpd validate plan-preflight <PLAN.md>"
    assert recovery_local_snapshot_command() == "gpd resume"
    assert recovery_cross_workspace_command() == "resume --recent"
    assert public_surface_contract_module.local_cli_bridge_purpose_phrase() == "workspace diagnostics"
    bridge_note = local_cli_bridge_note()
    _assert_anchor(
        bridge_note,
        "local CLI bridge note composes dynamic command and purpose",
        ("gpd --help", "normal terminal", "broader local CLI surface", "workspace diagnostics"),
    )
    assert public_surface_contract_module.local_cli_bridge_purpose_phrase() in bridge_note
    assert public_surface_contract_module.local_cli_plan_preflight_command() not in bridge_note
    assert public_surface_contract_module.local_cli_install_local_example_command() == "gpd install <runtime> --local"
    assert (
        public_surface_contract_module.local_cli_validate_command_context_command()
        == "gpd validate command-context <name>"
    )

    doc_surface_contracts_module._public_surface_contract_payload.cache_clear()


def test_doc_surface_contract_helpers_refresh_dynamic_command_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = public_surface_contract_module.PublicSurfaceContract(
        beginner_onboarding=public_surface_contract_module.BeginnerOnboardingContract(
            hub_url="./docs/dynamic.md",
            preflight_requirements=("Dynamic preflight",),
            caveats=("Dynamic caveat",),
            startup_ladder=("help", "start"),
        ),
        local_cli_bridge=public_surface_contract_module.LocalCliBridgeContract(
            named_commands=public_surface_contract_module.LocalCliNamedCommandsContract(
                help="gpd help dynamic",
                doctor="gpd doctor dynamic",
                unattended_readiness="gpd validate dynamic-unattended --runtime <runtime> --autonomy balanced",
                permissions_status="gpd permissions status dynamic --runtime <runtime> --autonomy balanced",
                permissions_sync="gpd permissions sync dynamic --runtime <runtime> --autonomy balanced",
                resume="gpd resume dynamic",
                resume_recent="gpd resume dynamic --recent",
                observe_execution="gpd observe dynamic",
                cost="gpd cost dynamic",
                presets_list="gpd presets dynamic",
                plan_preflight="gpd validate dynamic-plan <PLAN.md>",
                integrations_status_wolfram="gpd integrations status dynamic-wolfram",
            ),
            terminal_phrase="from your normal terminal",
            purpose_phrase="dynamic diagnostics",
            install_local_example="gpd install dynamic --local",
            doctor_local_command="gpd doctor dynamic --runtime <runtime> --local",
            doctor_global_command="gpd doctor dynamic --runtime <runtime> --global",
            validate_command_context_command="gpd validate dynamic-context <name>",
        ),
        post_start_settings=public_surface_contract_module.PostStartSettingsContract(
            primary_sentence="Use settings later.",
            default_sentence="Balanced stays recommended.",
        ),
        resume_authority=public_surface_contract_module.ResumeAuthorityContract(
            durable_authority_phrase="Durable authority",
            public_vocabulary_intro="Visible vocabulary",
            public_fields=("resume_file",),
        ),
        recovery_ladder=public_surface_contract_module.RecoveryLadderContract(
            title="Dynamic recovery ladder",
            local_snapshot_command="gpd resume dynamic",
            local_snapshot_phrase="inspect the current workspace",
            cross_workspace_command="gpd resume dynamic --recent",
            cross_workspace_phrase="find another workspace",
            resume_phrase="continue with resume-work",
            next_phrase="use suggest-next for the fastest next action",
            pause_phrase="a continuation handoff artifact",
        ),
    )
    monkeypatch.setattr(doc_surface_contracts_module, "load_public_surface_contract", lambda: contract)
    monkeypatch.setattr(public_surface_contract_module, "load_public_surface_contract", lambda: contract)
    doc_surface_contracts_module._public_surface_contract_payload.cache_clear()

    doc_surface_contracts_module.assert_unattended_readiness_contract(
        "\n".join(
            (
                contract.local_cli_bridge.named_commands.unattended_readiness,
                contract.local_cli_bridge.named_commands.permissions_status,
                contract.local_cli_bridge.named_commands.permissions_sync,
                contract.local_cli_bridge.named_commands.doctor,
                "Runtime permissions are runtime-owned approval/alignment only.",
            )
        )
    )
    assert doc_surface_contracts_module.DOCTOR_RUNTIME_SCOPE_RE.search(contract.local_cli_bridge.doctor_local_command)
    assert doc_surface_contracts_module.DOCTOR_RUNTIME_SCOPE_RE.search(contract.local_cli_bridge.doctor_global_command)
    doc_surface_contracts_module.assert_runtime_reset_rediscovery_contract(
        "\n".join(
            (
                contract.recovery_ladder.local_snapshot_command,
                contract.recovery_ladder.cross_workspace_command,
                "reset the runtime to a fresh context window",
                "use your normal terminal before reopening the runtime",
                "do not treat the fresh context reset as project recovery",
            )
        )
    )


def test_doc_surface_contract_payload_cache_clear_refreshes_after_source_swap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_contract = public_surface_contract_module.load_public_surface_contract()
    first_contract = dataclasses.replace(
        base_contract,
        beginner_onboarding=dataclasses.replace(
            base_contract.beginner_onboarding,
            preflight_requirements=("First preflight",),
        ),
    )
    second_contract = dataclasses.replace(
        base_contract,
        beginner_onboarding=dataclasses.replace(
            base_contract.beginner_onboarding,
            preflight_requirements=("Second preflight",),
        ),
    )

    monkeypatch.setattr(doc_surface_contracts_module, "load_public_surface_contract", lambda: first_contract)
    doc_surface_contracts_module._public_surface_contract_payload.cache_clear()
    assert doc_surface_contracts_module.beginner_preflight_requirements() == ("First preflight",)

    monkeypatch.setattr(doc_surface_contracts_module, "load_public_surface_contract", lambda: second_contract)
    assert doc_surface_contracts_module.beginner_preflight_requirements() == ("First preflight",)

    doc_surface_contracts_module._public_surface_contract_payload.cache_clear()
    assert doc_surface_contracts_module.beginner_preflight_requirements() == ("Second preflight",)


def test_onboarding_boundary_reference_stays_internal_to_start_and_tour() -> None:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    boundary_reference = "@{GPD_INSTALL_DIR}/references/shared/onboarding-command-boundaries.md"
    boundary_concepts = (
        "start",
        "chooser/router",
        "tour",
        "read-only explainer",
        "help",
        "reference/index surface",
        "settings",
        "after first successful startup",
        "not an autopilot",
        "verify",
        "redirect",
    )

    _assert_anchor(
        (repo_root / "README.md").read_text(encoding="utf-8"),
        "README preserves supervised execution posture",
        ("GPD", "not an autopilot", "verify", "redirect", "Supervised", "Balanced"),
    )

    internal_workflows = (
        "src/gpd/specs/workflows/start.md",
        "src/gpd/specs/workflows/tour.md",
    )
    for rel in internal_workflows:
        raw = (repo_root / rel).read_text(encoding="utf-8")
        expanded = expand_at_includes(raw, repo_root / "src/gpd", "/runtime/")
        assert boundary_reference in raw
        _assert_anchor(expanded, f"{rel} expands shared onboarding boundary concepts", boundary_concepts)
        if rel.endswith("tour.md"):
            assert expanded.count("help -> start -> tour") == 1

    public_workflows = (
        "src/gpd/specs/workflows/help.md",
        "src/gpd/specs/workflows/settings.md",
    )
    for rel in public_workflows:
        raw = (repo_root / rel).read_text(encoding="utf-8")
        expanded = expand_at_includes(raw, repo_root / "src/gpd", "/runtime/")
        assert boundary_reference not in raw
        _assert_absent(
            expanded,
            f"{rel} excludes internal onboarding boundary reference prose",
            (
                "Keep the beginner boundaries stable",
                "`start` is the chooser/router",
                "`settings` belongs after first successful startup",
            ),
        )


def test_workflow_interactive_choice_fallback_is_single_sourced() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    fallback_ref = "@{GPD_INSTALL_DIR}/references/shared/interactive-choice-fallback.md"
    workflow_surfaces = (
        ("src/gpd/specs/workflows/start.md", None),
        ("src/gpd/specs/workflows/new-project.md", "new-project"),
        ("src/gpd/specs/workflows/settings.md", None),
    )

    for rel, staged_name in workflow_surfaces:
        raw = (repo_root / rel).read_text(encoding="utf-8")
        authority_text = (
            workflow_authority_text(repo_root / "src/gpd/specs/workflows", staged_name)
            if staged_name is not None
            else raw
        )
        expanded = expand_at_includes(authority_text, repo_root / "src/gpd", "/runtime/")
        if staged_name is None:
            assert fallback_ref in raw
        _assert_anchor(
            expanded,
            f"{rel} preserves interactive choice fallback meaning",
            (
                "ask_user",
                "structured choices",
                "wait for a structured reply",
                "plain text",
                "same option labels",
                "freeform response",
                "Do not duplicate the same question",
            ),
        )
        _assert_absent(
            raw,
            f"{rel} avoids stale platform-specific fallback prose",
            ("Platform note", "If `ask_user` is available", "If `ask_user` is not available"),
        )


def test_quick_workflow_uses_freeform_prompt_without_choice_fallback() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    raw = (repo_root / "src/gpd/specs/workflows/quick.md").read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/references/shared/interactive-choice-fallback.md" not in raw
    _assert_anchor(
        raw,
        "quick workflow keeps inherently freeform prompt boundary",
        ("Ask ONE question inline", "freeform", "NOT ask_user", "no fixed option labels to preserve"),
    )
    assert "ask_user(" not in raw
    _assert_absent(raw, "quick workflow avoids structured-choice fallback branch", "If `ask_user` is not available")
