"""Prompt diagnostics coverage through the public production API."""

from __future__ import annotations

import ast
import importlib
import json
import textwrap
from pathlib import Path

from gpd import registry
from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.core.workflow_staging import load_workflow_stage_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_DIAGNOSTICS_PATH = REPO_ROOT / "src" / "gpd" / "core" / "prompt_diagnostics.py"
PROMPT_MARKDOWN_SCAN_PATH = REPO_ROOT / "src" / "gpd" / "core" / "prompt_markdown_scan.py"
STAGE_PROMPT_DIAGNOSTICS_PATH = REPO_ROOT / "src" / "gpd" / "core" / "stage_prompt_diagnostics.py"
PROMPT_DIAGNOSTICS_TOTAL_LOC_CAP = 3_450
PROMPT_DIAGNOSTICS_SPLIT_FACADE_LOC_CAP = 1_100
PROMPT_DIAGNOSTICS_SUPPORT_MODULE_LOC_CAP = 850
STAGE_PROMPT_DIAGNOSTICS_LOC_CAP = 1_275
COMPACT_ONLY_MANIFEST_KEYS = {
    "authority_groups",
    "cold_authority_policy",
    "derived_init_field_rules",
    "must_not_eager_load_groups",
    "required_init_field_groups",
    "stage_defaults",
}


def _diagnostics():
    return importlib.import_module("gpd.core.prompt_diagnostics")


def _non_native_runtime_name() -> str:
    return next(
        descriptor.runtime_name for descriptor in iter_runtime_descriptors() if not descriptor.native_include_support
    )


def _write(root: Path, relative_path: str, content: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    return path


def _report(repo_root: Path, **kwargs):
    options = {
        "surfaces": ("command", "agent", "workflow"),
        "runtime_names": (),
        "include_tests": False,
        "include_runtime_projections": True,
    }
    options.update(kwargs)
    return _diagnostics().build_prompt_surface_report(repo_root, **options)


def _relative_report_path(raw_path: str) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        return path.relative_to(REPO_ROOT).as_posix()
    return path.as_posix()


def _stage_by_id(payload: dict[str, object], stage_id: str) -> dict[str, object]:
    diagnostics = payload["stage_diagnostics"]
    assert isinstance(diagnostics, list)
    assert len(diagnostics) == 1
    stages = diagnostics[0]["stages"]
    return next(stage for stage in stages if stage["stage_id"] == stage_id)


def _source_line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _assert_no_compact_manifest_keys(value: object) -> None:
    if isinstance(value, dict):
        leaked_keys = sorted(COMPACT_ONLY_MANIFEST_KEYS & set(value))
        assert leaked_keys == []
        for child in value.values():
            _assert_no_compact_manifest_keys(child)
        return
    if isinstance(value, list):
        for child in value:
            _assert_no_compact_manifest_keys(child)


def _frontmatter_from_markdown(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0] == "---"
    end_index = lines.index("---", 1)
    return "\n".join(lines[1:end_index]) + "\n"


def _extract_markdown_heading_section(text: str, heading: str) -> str:
    marker = f"## {heading}\n"
    start = text.index(marker)
    next_heading = text.find("\n## ", start + len(marker))
    if next_heading == -1:
        return text[start:].rstrip("\r\n")
    return text[start:next_heading].rstrip("\r\n")


def _write_repeated_residue_probe_project(root: Path) -> dict[str, int]:
    router_body = "Router alpha.\nRouter beta.\nRouter gamma.\n"
    bootstrap_body = "Bootstrap active body.\n"
    finalize_body = "Finalize active body.\n"
    _write(
        root,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        @{GPD_INSTALL_DIR}/workflows/probe-router.md
        """,
    )
    _write(root, "src/gpd/specs/workflows/probe-router.md", router_body)
    _write(root, "src/gpd/specs/workflows/probe-bootstrap.md", bootstrap_body)
    _write(root, "src/gpd/specs/workflows/probe-finalize.md", finalize_body)
    _write(
        root,
        "src/gpd/specs/workflows/probe-stage-manifest.json",
        """
        {
          "schema_version": 1,
          "workflow_id": "probe",
          "stages": [
            {
              "id": "session_router",
              "order": 1,
              "purpose": "Route into the staged workflow.",
              "mode_paths": ["workflows/probe-router.md"],
              "required_init_fields": [],
              "loaded_authorities": ["workflows/probe-router.md"],
              "conditional_authorities": [],
              "must_not_eager_load": [],
              "allowed_tools": [],
              "writes_allowed": [],
              "produced_state": [],
              "next_stages": ["phase_bootstrap"],
              "checkpoints": []
            },
            {
              "id": "phase_bootstrap",
              "order": 2,
              "purpose": "Bootstrap the selected phase without reloading the router.",
              "mode_paths": ["workflows/probe-bootstrap.md"],
              "required_init_fields": [],
              "loaded_authorities": ["workflows/probe-bootstrap.md"],
              "conditional_authorities": [],
              "must_not_eager_load": ["workflows/probe-router.md"],
              "allowed_tools": [],
              "writes_allowed": [],
              "produced_state": [],
              "next_stages": ["phase_finalize"],
              "checkpoints": []
            },
            {
              "id": "phase_finalize",
              "order": 3,
              "purpose": "Finalize the selected phase without reloading the router.",
              "mode_paths": ["workflows/probe-finalize.md"],
              "required_init_fields": [],
              "loaded_authorities": ["workflows/probe-finalize.md"],
              "conditional_authorities": [],
              "must_not_eager_load": ["workflows/probe-router.md"],
              "allowed_tools": [],
              "writes_allowed": [],
              "produced_state": [],
              "next_stages": [],
              "checkpoints": []
            }
          ]
        }
        """,
    )
    return {
        "router_chars": len(router_body),
        "router_lines": len(router_body.splitlines()),
        "occurrences": 2,
    }


def test_report_includes_registered_command_agent_and_workflow_sources() -> None:
    report = _report(REPO_ROOT, runtime_names=())

    actual_paths_by_kind: dict[str, set[str]] = {}
    for item in report.items:
        actual_paths_by_kind.setdefault(item.kind, set()).add(_relative_report_path(item.path))

    expected_command_paths = {f"src/gpd/commands/{name}.md" for name in registry.list_commands()}
    expected_agent_paths = {f"src/gpd/agents/{name}.md" for name in registry.list_agents()}
    expected_workflow_paths = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted((REPO_ROOT / "src" / "gpd" / "specs" / "workflows").glob("*.md"))
    }

    assert expected_command_paths <= actual_paths_by_kind.get("command", set())
    assert expected_agent_paths <= actual_paths_by_kind.get("agent", set())
    assert expected_workflow_paths <= actual_paths_by_kind.get("workflow", set())


def test_report_to_dict_exposes_stable_public_shape(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        Probe body.
        """,
    )

    report = _report(tmp_path, surfaces=("command",), runtime_names=())
    payload = _diagnostics().report_to_dict(report)

    assert payload["schema_version"] == report.schema_version
    assert isinstance(payload["totals"], dict)
    assert isinstance(payload["items"], list)
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["name"] == "probe"
    assert item["runtime_projection"] == []
    assert item["review_contract_frontload_section_count"] == 0
    assert item["review_contract_frontload_line_count"] == 0
    assert item["review_contract_frontload_char_count"] == 0
    assert payload["totals"]["review_contract_frontload_section_count"] == 0
    assert payload["totals"]["review_contract_frontload_line_count"] == 0
    assert payload["totals"]["review_contract_frontload_char_count"] == 0
    assert payload["totals"]["stage_mechanics_prose_count"] == 0
    assert payload["totals"]["stage_mechanics_prose_by_kind"] == {"command": 0, "agent": 0, "workflow": 0}
    assert payload["stage_mechanics_prose_mentions"] == []
    assert payload["runtime_top_prompts"] == {}
    assert payload["stage_diagnostics"] == []
    stage_totals = payload["totals"]["stage_diagnostics"]
    missing_manifest_fields = sorted(
        {
            "manifest_must_not_duplicate_entry_count",
            "manifest_must_not_duplicate_stage_count",
            "manifest_must_not_duplicate_authority_count",
        }
        - set(stage_totals)
    )
    assert missing_manifest_fields == [], (
        f"stage diagnostics missing Phase 1 manifest duplicate totals: {missing_manifest_fields}"
    )
    assert stage_totals["manifest_must_not_duplicate_entry_count"] == 0
    assert stage_totals["manifest_must_not_duplicate_stage_count"] == 0
    assert stage_totals["manifest_must_not_duplicate_authority_count"] == 0
    assert payload["manifest_must_not_duplicate_entries"] == []
    assert payload["invalid_gpd_return_examples"] == []
    assert payload["invalid_frontmatter_examples"] == []
    assert payload["disallowed_return_field_mentions"] == []
    assert payload["forbidden_child_return_synthesis_mentions"] == []
    assert payload["exact_assertion_diagnostics"]["schema_version"] == "exact_assertions.v1"
    assert payload["exact_assertion_diagnostics"]["totals"]["exact_assertion_count"] == 0


def test_report_measures_review_contract_frontload_from_rendered_visibility(tmp_path: Path) -> None:
    command_path = _write(
        tmp_path,
        "src/gpd/commands/probe-review.md",
        """
        ---
        name: gpd:probe-review
        description: Probe review command
        review-contract:
          schema_version: 1
          review_mode: review
          required_outputs:
            - GPD/review/probe-review.json
          required_evidence:
            - target artifact
          blocking_conditions:
            - missing target artifact
          preflight_checks:
            - command_context
          stage_artifacts:
            - GPD/review/probe-review.json
        ---
        Probe review body.
        """,
    )

    frontmatter = _frontmatter_from_markdown(command_path)
    visibility = registry.render_command_visibility_sections_from_frontmatter(
        frontmatter,
        command_name="probe-review",
    )
    expected_section = _extract_markdown_heading_section(visibility, "Review Contract")

    payload = _diagnostics().report_to_dict(_report(tmp_path, surfaces=("command",), runtime_names=()))
    item = payload["items"][0]

    assert item["review_contract_frontload_section_count"] == 1
    assert item["review_contract_frontload_line_count"] == len(expected_section.splitlines())
    assert item["review_contract_frontload_char_count"] == len(expected_section)
    assert payload["totals"]["review_contract_frontload_section_count"] == 1
    assert payload["totals"]["review_contract_frontload_line_count"] == item["review_contract_frontload_line_count"]
    assert payload["totals"]["review_contract_frontload_char_count"] == item["review_contract_frontload_char_count"]
    assert payload["totals"]["by_kind"]["command"]["review_contract_frontload_section_count"] == 1
    assert payload["totals"]["by_kind"]["agent"]["review_contract_frontload_section_count"] == 0
    assert payload["totals"]["by_kind"]["workflow"]["review_contract_frontload_section_count"] == 0


def test_stage_mechanics_prose_mentions_are_reported_by_category_and_kind(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        Call `gpd --raw init probe --stage bootstrap` before loading the active stage.
        Use `gpd --raw stage field-access probe bootstrap --style instruction` for field access.
        """,
    )
    _write(
        tmp_path,
        "src/gpd/specs/workflows/probe/bootstrap.md",
        """
        Read only `staged_loading.required_init_fields`; ignore stale staged-init values from older stages.
        After each staged reload, follow only `staged_loading.eager_authorities` for the active stage.
        """,
    )

    payload = _diagnostics().report_to_dict(
        _report(tmp_path, surfaces=("command", "workflow"), runtime_names=()),
        top=20,
    )
    totals = payload["totals"]

    assert totals["stage_mechanics_prose_count"] == len(payload["stage_mechanics_prose_mentions"])
    assert totals["stage_mechanics_prose_by_kind"] == {"command": 2, "agent": 0, "workflow": 2}
    category_totals = totals["stage_mechanics_prose_by_category"]
    for category in (
        "staged_init_command",
        "field_access_instruction",
        "selected_field_gate",
        "stale_payload_rejection",
        "stage_reload_transition",
        "eager_authority_follow",
    ):
        assert category_totals[category] >= 1

    rows = payload["stage_mechanics_prose_mentions"]
    assert {row["severity"] for row in rows} == {"info"}
    assert all({"path", "line", "categories", "snippet"} <= set(row) for row in rows)
    assert any(row["path"].endswith("src/gpd/commands/probe.md") for row in rows)
    assert any(row["path"].endswith("src/gpd/specs/workflows/probe/bootstrap.md") for row in rows)


def test_stage_diagnostics_report_manifest_must_not_duplicates_even_when_loader_rejects(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        @{GPD_INSTALL_DIR}/workflows/probe.md
        """,
    )
    _write(tmp_path, "src/gpd/specs/workflows/probe.md", "Probe body.\n")
    _write(tmp_path, "src/gpd/specs/workflows/later.md", "Later-stage body.\n")
    _write(tmp_path, "src/gpd/specs/templates/deferred.md", "Deferred body.\n")
    _write(
        tmp_path,
        "src/gpd/specs/workflows/probe-stage-manifest.json",
        """
        {
          "schema_version": 1,
          "workflow_id": "probe",
          "stages": [
            {
              "id": "bootstrap",
              "order": 1,
              "purpose": "Load the probe bootstrap.",
              "mode_paths": ["workflows/probe.md"],
              "required_init_fields": [],
              "loaded_authorities": ["workflows/probe.md"],
              "conditional_authorities": [],
              "must_not_eager_load": [
                "templates/deferred.md",
                " templates/deferred.md ",
                "workflows/later.md"
              ],
              "allowed_tools": [],
              "writes_allowed": [],
              "produced_state": [],
              "next_stages": [],
              "checkpoints": []
            }
          ]
        }
        """,
    )

    payload = _diagnostics().report_to_dict(_report(tmp_path, surfaces=("command",), runtime_names=()))

    assert payload["stage_diagnostics"] == []
    assert any("must_not_eager_load must not contain duplicate entries" in warning for warning in payload["warnings"])
    rows = payload["manifest_must_not_duplicate_entries"]
    assert len(rows) == 1, "duplicate manifest diagnostics should survive strict loader rejection"
    row = rows[0]
    assert row["workflow_id"] == "probe"
    assert row["stage_id"] == "bootstrap"
    assert row["field_name"] == "must_not_eager_load"
    assert row["raw_entry_count"] == 3
    assert row["effective_unique_entry_count"] == 2
    assert row["duplicate_entry_count"] == 1
    assert row["duplicate_entries"] == [
        {
            "value": "templates/deferred.md",
            "raw_occurrence_count": 2,
            "first_index": 0,
            "duplicate_indexes": [1],
        }
    ]
    assert payload["totals"]["stage_diagnostics"]["manifest_must_not_duplicate_entry_count"] == 1
    assert payload["totals"]["stage_diagnostics"]["manifest_must_not_duplicate_stage_count"] == 1
    assert payload["totals"]["stage_diagnostics"]["manifest_must_not_duplicate_authority_count"] == 1


def test_compact_autonomous_manifest_keys_do_not_enter_staged_loading_payloads() -> None:
    manifest_path = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "autonomous-stage-manifest.json"
    source_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert {"stage_defaults", "cold_authority_policy"} <= set(source_payload)

    manifest = load_workflow_stage_manifest("autonomous")
    for stage_id in manifest.stage_ids():
        staged_loading = manifest.staged_loading_payload(stage_id)

        _assert_no_compact_manifest_keys(staged_loading)
        assert "required_init_fields" in staged_loading
        assert "must_not_eager_load" in staged_loading
        assert "eager_authorities" in staged_loading


def test_stage_diagnostics_detect_transitive_eager_loading_violations(tmp_path: Path) -> None:
    runtime_name = _non_native_runtime_name()
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        @{GPD_INSTALL_DIR}/workflows/probe.md
        """,
    )
    _write(
        tmp_path,
        "src/gpd/specs/workflows/probe.md",
        """
        ---
        name: probe
        ---
        Stage bootstrap body.
        @{GPD_INSTALL_DIR}/templates/deferred.md
        """,
    )
    _write(tmp_path, "src/gpd/specs/templates/deferred.md", "Deferred authority body.\n")
    _write(
        tmp_path,
        "src/gpd/specs/workflows/probe-stage-manifest.json",
        """
        {
          "schema_version": 1,
          "workflow_id": "probe",
          "stages": [
            {
              "id": "bootstrap",
              "order": 1,
              "purpose": "Load the probe bootstrap.",
              "mode_paths": ["workflows/probe.md"],
              "required_init_fields": [],
              "loaded_authorities": ["workflows/probe.md"],
              "conditional_authorities": [
                {"when": "need_deferred", "authorities": ["templates/deferred.md"]}
              ],
              "must_not_eager_load": ["templates/deferred.md"],
              "allowed_tools": [],
              "writes_allowed": [],
              "produced_state": [],
              "next_stages": [],
              "checkpoints": []
            }
          ]
        }
        """,
    )

    payload = _diagnostics().report_to_dict(
        _report(tmp_path, surfaces=("command",), runtime_names=(runtime_name,)),
    )

    stage = payload["stage_diagnostics"][0]["stages"][0]
    assert stage["eager_authorities"] == ["workflows/probe.md"]
    assert stage["lazy_authorities"] == ["templates/deferred.md"]
    assert "templates/deferred.md" in stage["eager_authority_metrics"][0]["transitive_include_authorities"]
    violation_sources = {violation["violation_source"] for violation in stage["must_not_eager_load_violations"]}
    assert {"first_turn_transitive_include", "stage_eager_transitive_include"} <= violation_sources
    assert payload["totals"]["stage_diagnostics"]["must_not_eager_load_violation_count"] == len(
        stage["must_not_eager_load_violations"]
    )
    assert payload["stage_diagnostics"][0]["runtime_projection"][0]["runtime"] == runtime_name


def test_stage_diagnostics_classifies_prior_stage_first_turn_residue_without_counting_violation(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        @{GPD_INSTALL_DIR}/workflows/probe-router.md
        """,
    )
    _write(tmp_path, "src/gpd/specs/workflows/probe-router.md", "Router body.\n")
    _write(tmp_path, "src/gpd/specs/workflows/probe-bootstrap.md", "Bootstrap body.\n")
    _write(
        tmp_path,
        "src/gpd/specs/workflows/probe-stage-manifest.json",
        """
        {
          "schema_version": 1,
          "workflow_id": "probe",
          "stages": [
            {
              "id": "session_router",
              "order": 1,
              "purpose": "Route into the staged workflow.",
              "mode_paths": ["workflows/probe-router.md"],
              "required_init_fields": [],
              "loaded_authorities": ["workflows/probe-router.md"],
              "conditional_authorities": [],
              "must_not_eager_load": [],
              "allowed_tools": [],
              "writes_allowed": [],
              "produced_state": [],
              "next_stages": ["phase_bootstrap"],
              "checkpoints": []
            },
            {
              "id": "phase_bootstrap",
              "order": 2,
              "purpose": "Bootstrap the selected phase without reloading the router.",
              "mode_paths": ["workflows/probe-bootstrap.md"],
              "required_init_fields": [],
              "loaded_authorities": ["workflows/probe-bootstrap.md"],
              "conditional_authorities": [],
              "must_not_eager_load": ["workflows/probe-router.md"],
              "allowed_tools": [],
              "writes_allowed": [],
              "produced_state": [],
              "next_stages": [],
              "checkpoints": []
            }
          ]
        }
        """,
    )

    payload = _diagnostics().report_to_dict(_report(tmp_path, surfaces=("command",), runtime_names=()))

    bootstrap = _stage_by_id(payload, "phase_bootstrap")
    residue_metrics = bootstrap["prior_stage_residue_authority_metrics"]
    assert bootstrap["must_not_eager_load_violations"] == []
    assert [metric["authority"] for metric in residue_metrics] == ["workflows/probe-router.md"]
    assert residue_metrics[0]["violation_source"] == "prior_stage_residue"
    assert residue_metrics[0]["eager_via"] == ["workflows/probe-router.md"]
    assert payload["totals"]["stage_diagnostics"]["must_not_eager_load_violation_count"] == 0
    assert payload["totals"]["stage_diagnostics"]["prior_stage_residue_count"] == 1


def test_stage_diagnostics_measures_repeated_prior_stage_residue_chars_and_lines(
    tmp_path: Path,
) -> None:
    expected = _write_repeated_residue_probe_project(tmp_path)

    payload = _diagnostics().report_to_dict(_report(tmp_path, surfaces=("command",), runtime_names=()), top=1)

    bootstrap = _stage_by_id(payload, "phase_bootstrap")
    finalize = _stage_by_id(payload, "phase_finalize")
    for stage in (bootstrap, finalize):
        assert stage["must_not_eager_load_violations"] == []
        assert stage["prior_stage_residue_char_count"] == expected["router_chars"]
        assert stage["prior_stage_residue_line_count"] == expected["router_lines"]
        assert stage["must_not_eager_load_prior_stage_residue_count"] == 1
        [residue_metric] = stage["prior_stage_residue_authority_metrics"]
        assert residue_metric["authority"] == "workflows/probe-router.md"
        assert residue_metric["expanded_char_count"] == expected["router_chars"]
        assert residue_metric["expanded_line_count"] == expected["router_lines"]
        assert residue_metric["first_turn_chain_count"] == 1
        assert residue_metric["eager_via"] == ["workflows/probe-router.md"]

    stage_totals = payload["totals"]["stage_diagnostics"]
    assert stage_totals["must_not_eager_load_violation_count"] == 0
    assert stage_totals["prior_stage_residue_count"] == expected["occurrences"]
    assert stage_totals["prior_stage_residue_char_count"] == expected["router_chars"] * expected["occurrences"]
    assert stage_totals["prior_stage_residue_line_count"] == expected["router_lines"] * expected["occurrences"]
    assert stage_totals["repeated_prior_stage_residue_authority_count"] == 1
    assert stage_totals["repeated_prior_stage_residue_occurrence_count"] == expected["occurrences"]
    assert stage_totals["repeated_prior_stage_residue_char_count"] == (
        expected["router_chars"] * expected["occurrences"]
    )
    assert stage_totals["repeated_prior_stage_residue_line_count"] == (
        expected["router_lines"] * expected["occurrences"]
    )


def test_report_to_dict_exposes_repeated_prior_stage_residue_rows(tmp_path: Path) -> None:
    expected = _write_repeated_residue_probe_project(tmp_path)

    payload = _diagnostics().report_to_dict(_report(tmp_path, surfaces=("command",), runtime_names=()), top=1)

    residue_rows = payload["repeated_prior_stage_residue_rows"]
    assert isinstance(residue_rows, list)
    assert len(residue_rows) == 1
    [row] = residue_rows
    assert {
        "authority",
        "occurrence_count",
        "workflow_count",
        "stage_count",
        "expanded_char_count",
        "expanded_line_count",
        "first_turn_chain_count",
        "transitive_include_count",
        "workflows",
        "stages",
        "eager_via",
    } <= set(row)
    assert row["authority"] == "workflows/probe-router.md"
    assert row["occurrence_count"] == expected["occurrences"]
    assert row["workflow_count"] == 1
    assert row["stage_count"] == expected["occurrences"]
    assert row["expanded_char_count"] == expected["router_chars"] * expected["occurrences"]
    assert row["expanded_line_count"] == expected["router_lines"] * expected["occurrences"]
    assert row["first_turn_chain_count"] == expected["occurrences"]
    assert row["transitive_include_count"] == 0
    assert row["workflows"] == ["probe"]
    assert row["stages"] == ["probe.phase_bootstrap", "probe.phase_finalize"]
    assert row["eager_via"] == ["workflows/probe-router.md"]


def test_stage_diagnostics_exposes_conditional_authority_bucket_and_metrics(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        @{GPD_INSTALL_DIR}/workflows/probe.md
        """,
    )
    _write(tmp_path, "src/gpd/specs/workflows/probe.md", "Probe body.\n")
    _write(tmp_path, "src/gpd/specs/references/deep-dive.md", "Deep dive authority.\n")
    _write(tmp_path, "src/gpd/specs/templates/deferred.md", "Deferred body.\n")
    _write(
        tmp_path,
        "src/gpd/specs/workflows/probe-stage-manifest.json",
        """
        {
          "schema_version": 1,
          "workflow_id": "probe",
          "stages": [
            {
              "id": "bootstrap",
              "order": 1,
              "purpose": "Load the probe bootstrap.",
              "mode_paths": ["workflows/probe.md"],
              "required_init_fields": [],
              "loaded_authorities": ["workflows/probe.md"],
              "conditional_authorities": [
                {"when": "need_deep_dive", "authorities": ["references/deep-dive.md"]}
              ],
              "must_not_eager_load": ["templates/deferred.md"],
              "allowed_tools": [],
              "writes_allowed": [],
              "produced_state": [],
              "next_stages": [],
              "checkpoints": []
            }
          ]
        }
        """,
    )

    payload = _diagnostics().report_to_dict(_report(tmp_path, surfaces=("command",), runtime_names=()))

    stage = _stage_by_id(payload, "bootstrap")
    assert stage["conditional_authorities"] == [{"when": "need_deep_dive", "authorities": ["references/deep-dive.md"]}]
    assert [metric["authority"] for metric in stage["conditional_authority_metrics"]] == ["references/deep-dive.md"]
    assert stage["conditional_char_count"] == stage["conditional_authority_metrics"][0]["expanded_char_count"]
    assert "references/deep-dive.md" not in stage["eager_authorities"]

    bucket_rows = stage["authority_bucket_metrics"]
    conditional_rows = [
        row for row in bucket_rows if row["bucket"] == "conditional" and row["authority"] == "references/deep-dive.md"
    ]
    assert conditional_rows
    assert {row["bucket"] for row in bucket_rows} >= {"first_turn_active", "stage_eager", "conditional", "lazy"}


def test_stage_init_field_pressure_rows_classify_likely_bulky_fields(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        @{GPD_INSTALL_DIR}/workflows/probe.md
        """,
    )
    _write(tmp_path, "src/gpd/specs/workflows/probe.md", "Probe body.\n")
    _write(
        tmp_path,
        "src/gpd/specs/workflows/probe-stage-manifest.json",
        """
        {
          "schema_version": 1,
          "workflow_id": "probe",
          "stages": [
            {
              "id": "bootstrap",
              "order": 1,
              "purpose": "Load the probe bootstrap.",
              "mode_paths": ["workflows/probe.md"],
              "required_init_fields": [
                "workspace_root",
                "phase_context",
                "project_contract",
                "revision_report",
                "schema_bridge",
                "reference_artifacts",
                "reference_artifacts_content",
                "state_content"
              ],
              "loaded_authorities": ["workflows/probe.md"],
              "conditional_authorities": [],
              "must_not_eager_load": [],
              "allowed_tools": [],
              "writes_allowed": [],
              "produced_state": [],
              "next_stages": [],
              "checkpoints": []
            }
          ]
        }
        """,
    )

    payload = _diagnostics().report_to_dict(_report(tmp_path, surfaces=("command",), runtime_names=()))

    rows = [
        row
        for row in payload["stage_init_field_diagnostics"]
        if row["workflow_id"] == "probe" and row["stage_id"] == "bootstrap"
    ]
    rows_by_field = {row["field_name"]: row for row in rows}
    likely_bulky_fields = {
        "phase_context",
        "project_contract",
        "revision_report",
        "schema_bridge",
        "reference_artifacts",
        "reference_artifacts_content",
        "state_content",
    }
    assert set(rows_by_field) == likely_bulky_fields | {"workspace_root"}
    assert all(rows_by_field[field]["field_pressure_class"] == "likely_bulky" for field in likely_bulky_fields)
    assert rows_by_field["workspace_root"]["field_pressure_class"] == "ordinary"
    assert rows_by_field["project_contract"]["field_kind_guess"] == "contract"
    assert rows_by_field["schema_bridge"]["field_kind_guess"] == "schema_bridge"
    assert rows_by_field["reference_artifacts_content"]["field_kind_guess"] == "content"
    assert rows_by_field["state_content"]["field_kind_guess"] == "content"
    content_rows = [row for row in rows if row["field_kind_guess"] == "content"]
    assert {row["field_name"] for row in content_rows} == {"reference_artifacts_content", "state_content"}
    assert payload["totals"]["stage_diagnostics"]["selected_init_content_field_count"] == len(content_rows)
    assert {row["selection_count"] for row in rows} == {1}
    assert {row["required_init_field_count"] for row in rows} == {8}
    assert {row["likely_bulky_field_count"] for row in rows} == {7}


def test_stage_diagnostics_uses_workflow_staging_group_validation_for_local_sources(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/quick.md",
        """
        ---
        name: gpd:quick
        description: Quick command
        ---
        @{GPD_INSTALL_DIR}/workflows/quick.md
        """,
    )
    _write(tmp_path, "src/gpd/specs/workflows/quick.md", "Quick bootstrap body.\n")
    _write(
        tmp_path,
        "src/gpd/specs/workflows/quick-stage-manifest.json",
        """
        {
          "schema_version": 1,
          "workflow_id": "quick",
          "required_init_field_groups": {
            "reference_runtime": [
              "selected_protocol_bundle_ids",
              "protocol_bundle_count",
              "protocol_bundle_context",
              "not_a_quick_field"
            ]
          },
          "stages": [
            {
              "id": "bootstrap",
              "order": 1,
              "purpose": "Load local quick bootstrap.",
              "mode_paths": ["workflows/quick.md"],
              "required_init_field_groups": ["reference_runtime"],
              "required_init_fields": [],
              "loaded_authorities": ["workflows/quick.md"],
              "conditional_authorities": [],
              "must_not_eager_load": [],
              "allowed_tools": [],
              "writes_allowed": [],
              "produced_state": [],
              "next_stages": [],
              "checkpoints": []
            }
          ]
        }
        """,
    )

    payload = _diagnostics().report_to_dict(_report(tmp_path, surfaces=("command",), runtime_names=()))

    assert payload["stage_diagnostics"] == []
    assert any("unknown field name" in warning and "not_a_quick_field" in warning for warning in payload["warnings"])


def test_report_detects_invalid_schema_and_forbidden_child_return_synthesis(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/specs/workflows/probe.md",
        """
        ---
        name: probe
        ---
        The parent may synthesize the child gpd_return if the spawned agent forgets it.

        ```yaml
        gpd_return:
          status: completed
          files_written: []
          issues: []
          next_actions: []
          bogus_child_field: true
        ```

        ```markdown
        ---
        phase: "01"
        status: maybe
        contract_results: []
        ---
        ```
        """,
    )

    payload = _diagnostics().report_to_dict(_report(tmp_path, surfaces=("workflow",), runtime_names=()))

    assert payload["invalid_gpd_return_examples"]
    assert any(
        "Unknown gpd_return top-level field(s): bogus_child_field" in error
        for error in payload["invalid_gpd_return_examples"][0]["errors"]
    )
    assert payload["invalid_frontmatter_examples"]
    assert payload["disallowed_return_field_mentions"]
    assert payload["forbidden_child_return_synthesis_mentions"]
    assert payload["items"][0]["visible_schema_example_count"] >= 2


def test_return_field_mentions_use_registry_helpers(monkeypatch) -> None:
    scanners = importlib.import_module("gpd.core.prompt_diagnostics_scanners")
    calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_return_field_source(field: str, *, base_fields):
        calls.append((field, tuple(base_fields)))
        if field == "registry_extension":
            return "extension"
        return "unknown"

    def fake_known_return_field_names(base_fields):
        calls.append(("known_fields", tuple(base_fields)))
        return frozenset({"registry_extension"})

    monkeypatch.setattr(scanners, "return_field_source", fake_return_field_source)
    monkeypatch.setattr(scanners, "known_return_field_names", fake_known_return_field_names)

    mentions = scanners._scan_return_field_mentions(
        """
        Use gpd_return.registry_extension.
        Use gpd_return.registry_extensoin.
        """,
        "probe.md",
    )
    extension = next(mention for mention in mentions if mention.field == "registry_extension")
    typo = next(mention for mention in mentions if mention.field == "registry_extensoin")

    assert extension.allowed
    assert extension.allowed_source == "extension"
    assert extension.severity == "info"
    assert typo.allowed is False
    assert typo.allowed_source == "unknown"
    assert typo.severity == "error"
    assert typo.suggestion == "registry_extension"
    assert all("status" in base_fields for _field, base_fields in calls)


def test_return_field_mentions_classify_known_extension_and_unknown_polarity() -> None:
    scanners = importlib.import_module("gpd.core.prompt_diagnostics_scanners")

    mentions = scanners._scan_return_field_mentions(
        """
        Use gpd_return.confidence.
        Use gpd_return.file_written.
        Do not use gpd_return.file_written.
        """,
        "probe.md",
    )
    extension = next(mention for mention in mentions if mention.field == "confidence")
    positive_unknown = next(
        mention for mention in mentions if mention.field == "file_written" and mention.polarity == "positive"
    )
    negative_unknown = next(
        mention for mention in mentions if mention.field == "file_written" and mention.polarity == "negative"
    )

    assert extension.allowed
    assert extension.allowed_source == "extension"
    assert extension.severity == "info"
    assert positive_unknown.allowed is False
    assert positive_unknown.severity == "error"
    assert positive_unknown.suggestion == "files_written"
    assert negative_unknown.allowed is False
    assert negative_unknown.severity == "warn"
    assert positive_unknown in scanners._disallowed_return_field_mentions(mentions)
    assert negative_unknown not in scanners._disallowed_return_field_mentions(mentions)


def test_include_counting_ignores_fenced_code_and_runtime_projection_covers_runtimes(tmp_path: Path) -> None:
    runtime_name = _non_native_runtime_name()
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        @{GPD_INSTALL_DIR}/workflows/probe.md

        ```bash
        @{GPD_INSTALL_DIR}/workflows/ignored.md
        ```
        """,
    )
    _write(tmp_path, "src/gpd/specs/workflows/probe.md", "Included body.\n")
    _write(tmp_path, "src/gpd/specs/workflows/ignored.md", "Ignored body.\n")

    payload = _diagnostics().report_to_dict(
        _report(tmp_path, surfaces=("command",), runtime_names=(runtime_name,)),
    )

    item = payload["items"][0]
    assert item["raw_include_count"] == 1
    assert item["expanded_include_count"] == 1
    projection = item["runtime_projection"][0]
    assert projection["runtime"] == runtime_name
    assert projection["line_count"] >= 1
    assert projection["char_count"] >= projection["expanded_char_count"]
    assert payload["runtime_top_prompts"][runtime_name][0]["name"] == "probe"


def test_exact_assertion_diagnostics_and_taxonomy_usage_are_additive(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_prompt_contracts.py",
        """
        from tests.assertion_taxonomy_support import (
            assert_fragments,
            assert_prompt_contracts,
            machine_exact,
            public_exact,
            semantic_anchor,
        )

        PROMPT = "Quick Start\\ngpd_return:\\nstable semantic anchor\\n"

        def test_prompt_contracts():
            assert "gpd_return:" in PROMPT
            assert "Quick Start" in PROMPT
            assert "the exact old sentence is gone forever" not in PROMPT
            assert_prompt_contracts(
                PROMPT,
                machine_exact("schema", "gpd_return:"),
                public_exact("help", "Quick Start"),
                semantic_anchor("meaning", "stable semantic anchor"),
            )
            assert_fragments(PROMPT, semantic_anchor("direct fragment", "stable semantic anchor"))
        """,
    )

    exactness = _diagnostics().report_to_dict(_report(tmp_path, include_tests=True))["exact_assertion_diagnostics"]
    usage = exactness["taxonomy_helper_usage"]

    assert exactness["totals"]["exact_assertion_count"] >= 2
    assert exactness["totals"]["public_ux_exact_assertions"] >= 1
    assert usage["totals"]["assert_prompt_contracts"] == 1
    assert usage["totals"]["machine_exact"] == 1
    assert usage["totals"]["public_exact"] == 1
    assert usage["totals"]["semantic_anchor"] == 2


def test_renderers_include_actionable_sections(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        Probe body with gpd_return.status and a STOP gate.
        """,
    )

    diagnostics = _diagnostics()
    report = _report(tmp_path, surfaces=("command",), runtime_names=(_non_native_runtime_name(),))
    markdown = diagnostics.render_prompt_surface_markdown(report, top=1)
    table = diagnostics.render_prompt_surface_table(report, top=1)

    assert "Prompt Surface Diagnostics" in markdown
    assert "Runtime Projection Totals" in markdown
    assert "kind" in table
    assert "runtime top prompts" in table


def test_prompt_diagnostics_facade_reexports_split_symbols_by_identity() -> None:
    diagnostics = _diagnostics()
    types = importlib.import_module("gpd.core.prompt_diagnostics_types")
    renderers = importlib.import_module("gpd.core.prompt_diagnostics_renderers")
    scanners = importlib.import_module("gpd.core.prompt_diagnostics_scanners")

    pairs = (
        (types, types.PromptSource.__name__),
        (types, types.PromptSurfaceReport.__name__),
        (types, types.RuntimeProjectionMetric.__name__),
        (renderers, renderers.report_to_dict.__name__),
        (renderers, renderers.render_prompt_surface_markdown.__name__),
        (renderers, renderers.render_prompt_surface_table.__name__),
        (scanners, scanners._inspect_visible_schema_examples.__name__),
        (scanners, scanners._scan_return_field_mentions.__name__),
        (scanners, scanners._count_shell_fences.__name__),
    )
    public_names = set(diagnostics.__all__)

    for module, name in pairs:
        assert getattr(diagnostics, name) is getattr(module, name)
        if not name.startswith("_"):
            assert name in public_names


def test_prompt_diagnostics_facade_no_longer_defines_split_bodies() -> None:
    diagnostics = _diagnostics()
    types = importlib.import_module("gpd.core.prompt_diagnostics_types")
    renderers = importlib.import_module("gpd.core.prompt_diagnostics_renderers")
    scanners = importlib.import_module("gpd.core.prompt_diagnostics_scanners")
    tree = ast.parse(PROMPT_DIAGNOSTICS_PATH.read_text(encoding="utf-8"))
    facade_definitions = {
        node.name for node in tree.body if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    }
    split_definitions = {
        types.PromptSource.__name__,
        types.PromptSurfaceItem.__name__,
        types.PromptSurfaceReport.__name__,
        renderers.report_to_dict.__name__,
        renderers.render_prompt_surface_markdown.__name__,
        renderers.render_prompt_surface_table.__name__,
        scanners._inspect_visible_schema_examples.__name__,
        scanners._scan_return_field_mentions.__name__,
        scanners._scan_forbidden_child_return_synthesis_mentions.__name__,
        scanners._count_shell_parsing_lines.__name__,
    }

    assert facade_definitions.isdisjoint(split_definitions), facade_definitions & split_definitions
    assert diagnostics.report_to_dict is renderers.report_to_dict


def test_production_prompt_diagnostics_does_not_import_from_tests() -> None:
    source = PROMPT_DIAGNOSTICS_PATH.read_text(encoding="utf-8")

    assert "from tests" not in source
    assert "import tests" not in source


def test_prompt_diagnostics_modules_stay_small_enough_for_phase_7_split() -> None:
    module_paths = sorted(
        {
            PROMPT_MARKDOWN_SCAN_PATH,
            *PROMPT_DIAGNOSTICS_PATH.parent.glob("prompt_diagnostics*.py"),
            *PROMPT_DIAGNOSTICS_PATH.parent.glob("prompt_*_diagnostics.py"),
        }
    )
    loc_by_module = {path.name: _source_line_count(path) for path in module_paths}
    support_module_loc = {
        name: line_count for name, line_count in loc_by_module.items() if name != PROMPT_DIAGNOSTICS_PATH.name
    }

    assert PROMPT_DIAGNOSTICS_PATH.name in loc_by_module
    assert sum(loc_by_module.values()) <= PROMPT_DIAGNOSTICS_TOTAL_LOC_CAP, loc_by_module

    if support_module_loc:
        assert loc_by_module[PROMPT_DIAGNOSTICS_PATH.name] <= PROMPT_DIAGNOSTICS_SPLIT_FACADE_LOC_CAP, loc_by_module
        assert all(
            line_count <= PROMPT_DIAGNOSTICS_SUPPORT_MODULE_LOC_CAP for line_count in support_module_loc.values()
        ), support_module_loc

    stage_prompt_diagnostics_loc = _source_line_count(STAGE_PROMPT_DIAGNOSTICS_PATH)
    assert stage_prompt_diagnostics_loc <= STAGE_PROMPT_DIAGNOSTICS_LOC_CAP, {
        STAGE_PROMPT_DIAGNOSTICS_PATH.name: stage_prompt_diagnostics_loc
    }


def test_prompt_diagnostics_does_not_define_local_stage_manifest_parser() -> None:
    source = PROMPT_DIAGNOSTICS_PATH.read_text(encoding="utf-8")

    assert "_load_local_source_stage_manifest" not in source
    assert "_manifest_string_list" not in source


def test_prompt_diagnostics_does_not_define_semantic_duplicate_compat_aliases() -> None:
    source = PROMPT_DIAGNOSTICS_PATH.read_text(encoding="utf-8")
    private_prefix = "_"

    forbidden = (
        "def " + private_prefix + "semantic_duplicate_invariant_groups",
        "def " + private_prefix + "status_handling_terms",
        "scan"
        + private_prefix
        + "semantic_duplicate_invariant_groups as "
        + private_prefix
        + "scan"
        + private_prefix
        + "semantic_duplicate_invariant_groups",
        "semantic"
        + private_prefix
        + "example_limit as "
        + private_prefix
        + "semantic"
        + private_prefix
        + "example_limit",
        "status"
        + private_prefix
        + "handling_terms as "
        + private_prefix
        + "semantic"
        + private_prefix
        + "status"
        + private_prefix
        + "handling_terms",
    )

    for term in forbidden:
        assert term not in source
