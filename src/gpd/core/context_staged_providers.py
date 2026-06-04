"""Small provider factories for staged context assembly."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from gpd.core.staged_init_assembly import StagedInitAssemblyContext, StagedInitProvider

ContextPayloadBuilder = Callable[[], Mapping[str, object]]
AssemblyPayloadBuilder = Callable[[StagedInitAssemblyContext], Mapping[str, object]]
FieldPayloadBuilder = Callable[[frozenset[str]], Mapping[str, object]]
ScalarBuilder = Callable[[], object]
FileReader = Callable[[Path], object]


def context_provider(
    name: str,
    trigger_fields: Iterable[str],
    build_context: ContextPayloadBuilder,
) -> StagedInitProvider:
    """Return a provider whose payload builder does not need assembly metadata."""

    return StagedInitProvider(
        name,
        frozenset(trigger_fields),
        lambda _assembly_context: build_context(),
    )


def assembly_context_provider(
    name: str,
    trigger_fields: Iterable[str],
    build_context: AssemblyPayloadBuilder,
) -> StagedInitProvider:
    """Return a provider whose payload builder needs full assembly metadata."""

    return StagedInitProvider(name, frozenset(trigger_fields), build_context)


def selected_fields_provider(
    name: str,
    trigger_fields: Iterable[str],
    selectable_fields: Iterable[str],
    build_selected_fields: FieldPayloadBuilder,
) -> StagedInitProvider:
    """Return a provider that receives only requested fields from one field family."""

    selected_field_set = frozenset(selectable_fields)
    return StagedInitProvider(
        name,
        frozenset(trigger_fields),
        lambda assembly_context: build_selected_fields(assembly_context.required_fields & selected_field_set),
    )


def scalar_field_provider(field: str, build_value: ScalarBuilder, *, name: str | None = None) -> StagedInitProvider:
    """Return a one-field provider for deferred scalar values."""

    return StagedInitProvider(
        name or field,
        frozenset({field}),
        lambda _assembly_context: {field: build_value()},
    )


def reference_or_contract_provider(
    *,
    reference_fields: Iterable[str],
    contract_fields: Iterable[str],
    build_reference: FieldPayloadBuilder,
    build_contract: ContextPayloadBuilder,
    name: str = "reference_or_contract",
) -> StagedInitProvider:
    """Return the common staged reference provider with contract fallback."""

    reference_field_set = frozenset(reference_fields)
    contract_field_set = frozenset(contract_fields)

    def build(assembly_context: StagedInitAssemblyContext) -> Mapping[str, object]:
        selected_reference_fields = assembly_context.required_fields & reference_field_set
        if selected_reference_fields:
            return build_reference(selected_reference_fields)
        return build_contract()

    return StagedInitProvider(name, reference_field_set | contract_field_set, build)


def build_selected_file_context(
    cwd: Path,
    selected_fields: Iterable[str],
    field_paths: Mapping[str, str | Path],
    read_file: FileReader,
) -> dict[str, object]:
    """Read requested files from a field-to-project-relative-path mapping."""

    selected_field_set = frozenset(selected_fields)
    payload: dict[str, object] = {}
    for field, relative_path in field_paths.items():
        if field not in selected_field_set:
            continue
        path = Path(relative_path)
        payload[field] = read_file(path if path.is_absolute() else cwd / path)
    return payload


def file_context_provider(
    trigger_fields: Iterable[str],
    *,
    cwd: Path,
    field_paths: Mapping[str, str | Path],
    read_file: FileReader,
    name: str = "file_content",
) -> StagedInitProvider:
    """Return a selected file-content provider."""

    field_set = frozenset(trigger_fields)
    return selected_fields_provider(
        name,
        field_set,
        field_set,
        lambda selected_fields: build_selected_file_context(cwd, selected_fields, field_paths, read_file),
    )


def schema_bridge_provider(
    trigger_fields: Iterable[str],
    *,
    phase_info: Mapping[str, object] | None,
    missing_phase_message: str,
    bridge_builders: Mapping[str, ScalarBuilder],
    name: str = "schema_bridges",
) -> StagedInitProvider:
    """Return a provider for schema bridge payloads that require a resolved phase."""

    bridge_builder_items = tuple(bridge_builders.items())

    def build(assembly_context: StagedInitAssemblyContext) -> Mapping[str, object]:
        if phase_info is None:
            raise ValueError(missing_phase_message)
        return {
            field: build_bridge()
            for field, build_bridge in bridge_builder_items
            if field in assembly_context.required_fields
        }

    return StagedInitProvider(name, frozenset(trigger_fields), build)


__all__ = [
    "assembly_context_provider",
    "build_selected_file_context",
    "context_provider",
    "file_context_provider",
    "reference_or_contract_provider",
    "scalar_field_provider",
    "schema_bridge_provider",
    "selected_fields_provider",
]
