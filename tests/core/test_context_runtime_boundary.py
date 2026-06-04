"""Assertions for context/runtime abstraction boundaries."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_context_import_does_not_require_adapter_instantiation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import gpd.adapters as adapters

    def _boom():
        raise AssertionError("iter_adapters should not be needed for gpd.core.context import")

    monkeypatch.setattr(adapters, "iter_adapters", _boom)
    sys.modules.pop("gpd.core.context", None)

    context = importlib.import_module("gpd.core.context")
    payload = context.init_new_project(tmp_path)

    assert payload["has_research_files"] is False
    assert payload["research_file_samples"] == []
