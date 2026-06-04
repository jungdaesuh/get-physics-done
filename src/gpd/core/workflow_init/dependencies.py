"""Dependency bundle for workflow init builders.

The builders in this package intentionally do not import ``gpd.core.context``.
The context facade supplies the current helper aliases at call time so existing
monkeypatch-based compatibility tests continue to exercise the public facade.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ResolveModel(Protocol):
    def __call__(
        self,
        cwd: Path,
        agent_type: str,
        _config: Mapping[str, object] | None = None,
        runtime: str | None = None,
    ) -> str | None:
        ...


class ReferenceRuntimeBuilder(Protocol):
    def __call__(
        self,
        cwd: Path,
        *,
        include_artifact_content: bool = True,
        include_protocol_context: bool = True,
        include_active_reference_context: bool = True,
        persist_manuscript_proof_review_manifest: bool = False,
    ) -> dict[str, object]:
        ...


LoadConfig = Callable[[Path], Mapping[str, object]]
PathExists = Callable[[Path, str], bool]
DetectPlatform = Callable[[Path], str]
StateExists = Callable[[Path], bool]
OptionalStateGuidance = Callable[[Path], str | None]
PathResolver = Callable[[Path], Path]
ContextBuilder = Callable[[Path], dict[str, object]]
StagedReferenceRuntimeBuilder = Callable[[Path, set[str] | frozenset[str]], dict[str, object]]
FileReader = Callable[[Path], object]


@dataclass(frozen=True, slots=True)
class WorkflowInitDependencies:
    load_config: LoadConfig
    resolve_model: ResolveModel
    path_exists: PathExists
    detect_platform: DetectPlatform
    state_exists: StateExists
    backup_only_state_guidance: OptionalStateGuidance
    resolve_project_scoped_cwd: PathResolver
    build_reference_runtime_context: ReferenceRuntimeBuilder
    build_staged_reference_runtime_context: StagedReferenceRuntimeBuilder
    build_state_memory_runtime_context: ContextBuilder
    build_structured_state_runtime_context: ContextBuilder
    build_new_project_contract_runtime_context: ContextBuilder
    read_file_truncated: FileReader


__all__ = [
    "WorkflowInitDependencies",
]
