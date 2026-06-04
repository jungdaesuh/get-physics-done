from __future__ import annotations

import re
from pathlib import Path

from gpd.core.strict_yaml import load_strict_yaml
from gpd.core.workflow_staging import (
    WORKFLOW_STAGE_MANIFEST_DIR,
    WORKFLOW_STAGE_MANIFEST_SUFFIX,
    load_workflow_stage_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_PATH = REPO_ROOT / "src" / "gpd" / "specs" / "references" / "orchestration" / "agent-module-loading.md"
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"

ALLOWED_MODULE_INIT_FIELDS = {
    "selected_module_ids",
    "module_load_manifest",
    "module_policy_summary",
}
DISALLOWED_MODULE_BODY_KEYS = {
    "module_body",
    "module_bodies",
    "module_content",
    "module_contents",
    "module_markdown",
    "module_text",
    "module_payload",
    "module_payloads",
    "rendered_module_body",
    "rendered_module_content",
}
FENCED_YAML_BLOCK_RE = re.compile(r"```(?:yaml|yml)\n(?P<body>.*?)```", flags=re.DOTALL)
EAGER_GPD_INCLUDE_RE = re.compile(r"@\{GPD_INSTALL_DIR\}/[^\s\"')]+")


def _agent_body(text: str) -> str:
    if text.startswith("---"):
        return text.split("---", 2)[2]
    return text


def _fenced_yaml_blocks(text: str) -> list[str]:
    return [match.group("body") for match in FENCED_YAML_BLOCK_RE.finditer(text)]


def _module_load_manifest_values(value: object) -> list[object]:
    manifests: list[object] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "module_load_manifest":
                manifests.append(child)
            manifests.extend(_module_load_manifest_values(child))
    elif isinstance(value, list):
        for child in value:
            manifests.extend(_module_load_manifest_values(child))
    return manifests


def _agent_module_manifest_blocks() -> list[tuple[Path, int, str, object]]:
    blocks: list[tuple[Path, int, str, object]] = []
    for agent_path in sorted(AGENTS_DIR.glob("*.md")):
        body = _agent_body(agent_path.read_text(encoding="utf-8"))
        for block_index, block in enumerate(_fenced_yaml_blocks(body), start=1):
            if "module_load_manifest:" not in block:
                continue
            parsed = load_strict_yaml(block)
            for manifest in _module_load_manifest_values(parsed):
                blocks.append((agent_path, block_index, block, manifest))
    return blocks


def _assert_staged_metadata_is_body_free(value: object, *, path: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            assert key_text not in DISALLOWED_MODULE_BODY_KEYS, path
            assert not (
                key_text.startswith("module_")
                and any(fragment in key_text for fragment in ("body", "content", "markdown", "text"))
            ), path
            _assert_staged_metadata_is_body_free(child, path=f"{path}.{key_text}")
        return

    if isinstance(value, list):
        for index, child in enumerate(value):
            _assert_staged_metadata_is_body_free(child, path=f"{path}[{index}]")
        return

    if isinstance(value, str):
        assert "\n" not in value, path


def test_agent_module_loading_reference_defines_stage_first_metadata_only_contract() -> None:
    text = REFERENCE_PATH.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())

    required_fragments = (
        "Stage first.",
        "`payload.staged_loading`",
        "`staged_loading.must_not_eager_load`",
        "`module_load_manifest`",
        "must not include module bodies",
        "`protocol_bundle_load_manifest`",
        "Selected protocol bundles are additive module sources",
        "Autonomy controls checkpoint and interruption pressure.",
    )

    for fragment in required_fragments:
        assert fragment in normalized_text


def test_stage_manifests_do_not_request_module_body_init_fields() -> None:
    offenders: dict[str, list[str]] = {}

    for manifest_path in sorted(WORKFLOW_STAGE_MANIFEST_DIR.glob(f"*{WORKFLOW_STAGE_MANIFEST_SUFFIX}")):
        workflow_id = manifest_path.name.removesuffix(WORKFLOW_STAGE_MANIFEST_SUFFIX)
        manifest = load_workflow_stage_manifest(workflow_id)
        for stage in manifest.stages:
            module_fields = [
                field
                for field in stage.required_init_fields
                if field.startswith("module_") or field.startswith("selected_module")
            ]
            unexpected_fields = sorted(set(module_fields) - ALLOWED_MODULE_INIT_FIELDS)
            if "module_policy_summary" in module_fields and "module_load_manifest" not in module_fields:
                unexpected_fields.append("module_policy_summary_without_module_load_manifest")
            if unexpected_fields:
                offenders[f"{workflow_id}:{stage.id}"] = unexpected_fields

    assert offenders == {}


def test_staged_loading_payloads_remain_metadata_only_and_module_body_free() -> None:
    for manifest_path in sorted(WORKFLOW_STAGE_MANIFEST_DIR.glob(f"*{WORKFLOW_STAGE_MANIFEST_SUFFIX}")):
        workflow_id = manifest_path.name.removesuffix(WORKFLOW_STAGE_MANIFEST_SUFFIX)
        manifest = load_workflow_stage_manifest(workflow_id)
        for stage_id in manifest.stage_ids():
            payload = manifest.staged_loading_payload(stage_id)
            _assert_staged_metadata_is_body_free(payload, path=f"{workflow_id}:{stage_id}")


def test_agent_module_load_manifest_mentions_use_parseable_yaml_blocks() -> None:
    offenders: dict[str, int] = {}

    for agent_path in sorted(AGENTS_DIR.glob("*.md")):
        body = _agent_body(agent_path.read_text(encoding="utf-8"))
        raw_manifest_mentions = body.count("module_load_manifest:")
        fenced_manifest_mentions = sum(block.count("module_load_manifest:") for block in _fenced_yaml_blocks(body))
        if raw_manifest_mentions != fenced_manifest_mentions:
            offenders[agent_path.name] = raw_manifest_mentions - fenced_manifest_mentions

    assert offenders == {}


def test_agent_module_load_manifest_blocks_remain_body_free() -> None:
    for agent_path, block_index, _block, manifest in _agent_module_manifest_blocks():
        _assert_staged_metadata_is_body_free(manifest, path=f"{agent_path.name}:yaml-block-{block_index}")


def test_agent_module_load_manifest_blocks_do_not_eager_include_module_paths() -> None:
    offenders: dict[str, list[str]] = {}

    for agent_path, block_index, block, _manifest in _agent_module_manifest_blocks():
        eager_paths = sorted(set(EAGER_GPD_INCLUDE_RE.findall(block)))
        if eager_paths:
            offenders[f"{agent_path.name}:yaml-block-{block_index}"] = eager_paths

    assert offenders == {}
