"""Fast strictness assertions for the public surface contract loader."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import gpd.core.public_surface_contract as public_surface_contract

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "src/gpd/core/public_surface_contract.json"


def _load_contract_payload() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _load_schema_payload() -> dict[str, object]:
    schema_path = REPO_ROOT / "src/gpd/core/public_surface_contract_schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _bind_public_surface_contract_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, contract_payload: dict[str, object]
) -> None:
    (tmp_path / "public_surface_contract.json").write_text(json.dumps(contract_payload), encoding="utf-8")
    (tmp_path / "public_surface_contract_schema.json").write_text(json.dumps(_load_schema_payload()), encoding="utf-8")
    monkeypatch.setattr(public_surface_contract, "files", lambda _package: tmp_path)
    public_surface_contract.load_public_surface_contract.cache_clear()
    public_surface_contract.load_public_surface_contract_schema.cache_clear()


def test_fast_public_surface_contract_keeps_schema_v1_local_cli_commands_field() -> None:
    payload = _load_contract_payload()
    schema = _load_schema_payload()

    assert payload["schema_version"] == 1
    assert schema["schema_version"] == 1
    bridge_payload = payload["local_cli_bridge"]
    bridge_schema = schema["sections"]["local_cli_bridge"]
    assert bridge_schema["keys"][0] == "commands"

    named_commands = bridge_payload["named_commands"]
    ordered_keys = bridge_schema["named_commands"]["ordered_keys"]
    expected_commands = [named_commands[key] for key in ordered_keys]
    assert bridge_payload["commands"] == expected_commands

    public_surface_contract.load_public_surface_contract.cache_clear()
    try:
        contract = public_surface_contract.load_public_surface_contract()
        assert contract.local_cli_bridge.commands == tuple(expected_commands)
    finally:
        public_surface_contract.load_public_surface_contract.cache_clear()


def test_fast_public_surface_contract_rejects_schema_version_bool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _load_contract_payload()
    payload["schema_version"] = True
    _bind_public_surface_contract_files(tmp_path, monkeypatch, contract_payload=payload)

    try:
        with pytest.raises(ValueError, match=r"Unsupported public surface contract schema_version: True"):
            public_surface_contract.load_public_surface_contract()
    finally:
        public_surface_contract.load_public_surface_contract.cache_clear()
        public_surface_contract.load_public_surface_contract_schema.cache_clear()


def test_fast_public_surface_contract_rejects_drifted_bridge_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = copy.deepcopy(_load_contract_payload())
    bridge_payload = payload["local_cli_bridge"]
    bridge_payload["commands"] = list(reversed(bridge_payload["commands"]))
    _bind_public_surface_contract_files(tmp_path, monkeypatch, contract_payload=payload)

    try:
        with pytest.raises(
            ValueError,
            match=r"local_cli_bridge\.commands must equal local_cli_bridge\.named_commands ordered values",
        ):
            public_surface_contract.load_public_surface_contract()
    finally:
        public_surface_contract.load_public_surface_contract.cache_clear()
        public_surface_contract.load_public_surface_contract_schema.cache_clear()


def test_fast_public_surface_contract_rejects_duplicate_named_bridge_command_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = copy.deepcopy(_load_contract_payload())
    named_commands = payload["local_cli_bridge"]["named_commands"]
    named_commands["doctor"] = named_commands["help"]
    _bind_public_surface_contract_files(tmp_path, monkeypatch, contract_payload=payload)

    try:
        with pytest.raises(
            ValueError,
            match=r"local_cli_bridge\.named_commands must not contain duplicate command values",
        ):
            public_surface_contract.load_public_surface_contract()
    finally:
        public_surface_contract.load_public_surface_contract.cache_clear()
        public_surface_contract.load_public_surface_contract_schema.cache_clear()
