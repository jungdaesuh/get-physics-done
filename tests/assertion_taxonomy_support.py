"""Test-only assertion taxonomy helpers for prompt and surface contracts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from tests.markdown_test_support import (
    extract_markdown_section as extract_markdown_section_text,
)
from tests.markdown_test_support import (
    extract_marker_range as extract_marker_range_text,
)

__all__ = [
    "AssertionKind",
    "AssertionTaxonomyError",
    "FragmentAssertion",
    "FragmentMode",
    "MarkerScope",
    "MatchMode",
    "assert_fragments",
    "assert_prompt_contracts",
    "checkpoint_stop_boundary",
    "fail_closed_before_writes",
    "forbidden_duplicate",
    "fragment_count",
    "fresh_artifact_required",
    "handle_before_content",
    "machine_exact",
    "marker_range",
    "no_synthesized_child_return",
    "public_exact",
    "runtime_label_native",
    "schema_averse_first_useful_action",
    "semantic_anchor",
    "semantic_concept",
]


class AssertionKind(StrEnum):
    """Assertion classes used by test authors."""

    MACHINE_EXACT = "machine_exact"
    PUBLIC_EXACT = "public_exact"
    SEMANTIC_ANCHOR = "semantic_anchor"
    FORBIDDEN_DUPLICATE = "forbidden_duplicate"


class FragmentMode(StrEnum):
    """Fragment matching modes for text assertions."""

    ALL = "all"
    ANY = "any"
    ORDERED = "ordered"
    ABSENT = "absent"
    COUNT = "count"


class MatchMode(StrEnum):
    """Text normalization modes for fragment comparisons."""

    EXACT = "exact"
    NORMALIZED = "normalized"
    CASEFOLD_NORMALIZED = "casefold_normalized"


class AssertionTaxonomyError(AssertionError):
    """Assertion failure with taxonomy metadata in the message."""


@dataclass(frozen=True, slots=True)
class MarkerScope:
    """A text region beginning at ``start`` and ending before ``end``."""

    start: str
    end: str | None = None

    def __post_init__(self) -> None:
        if not self.start:
            raise ValueError("Marker scope requires a non-empty start marker")
        if self.end == "":
            raise ValueError("Marker scope end marker must be non-empty when provided")


@dataclass(frozen=True, slots=True)
class FragmentAssertion:
    """One scoped text assertion with taxonomy metadata."""

    kind: AssertionKind
    label: str
    fragments: tuple[str, ...]
    mode: FragmentMode = FragmentMode.ALL
    match: MatchMode = MatchMode.EXACT
    owner: str | None = None
    rationale: str | None = None
    section: str | None = None
    markers: MarkerScope | None = None
    expected_count: int | None = None
    max_count: int | None = None
    context: str | None = None

    def __post_init__(self) -> None:
        kind = AssertionKind(self.kind)
        mode = FragmentMode(self.mode)
        match = MatchMode(self.match)
        fragments = tuple(self.fragments)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "match", match)
        object.__setattr__(self, "fragments", fragments)

        if not self.label.strip():
            raise ValueError("Assertion label must be non-empty")
        if not fragments or any(fragment == "" for fragment in fragments):
            raise ValueError("Fragment assertions require at least one non-empty fragment")
        if match is not MatchMode.EXACT and any(_match_text(fragment, match) == "" for fragment in fragments):
            raise ValueError("Normalized fragment assertions require at least one non-whitespace character")
        if mode is FragmentMode.COUNT:
            if (self.expected_count is None) == (self.max_count is None):
                raise ValueError("Count fragment assertions require exactly one of expected_count or max_count")
            if self.expected_count is not None and self.expected_count < 0:
                raise ValueError("expected_count must be non-negative")
            if self.max_count is not None and self.max_count < 0:
                raise ValueError("max_count must be non-negative")
        elif self.expected_count is not None or self.max_count is not None:
            raise ValueError("expected_count and max_count are only valid with FragmentMode.COUNT")
        if kind is AssertionKind.FORBIDDEN_DUPLICATE and mode is not FragmentMode.COUNT:
            raise ValueError("Forbidden-duplicate assertions use FragmentMode.COUNT")

    def check(self, text: str) -> None:
        """Assert this fragment contract against ``text``."""

        assert_fragments(text, self)


FragmentInput = str | Sequence[str]
MarkerInput = MarkerScope | tuple[str, str | None] | tuple[str]


def marker_range(start: str, end: str | None = None) -> MarkerScope:
    """Return a marker range for scoped fragment checks."""

    return MarkerScope(start=start, end=end)


def machine_exact(
    label: str,
    fragments: FragmentInput,
    *,
    owner: str | None = None,
    rationale: str | None = None,
    mode: FragmentMode | str = FragmentMode.ALL,
    match: MatchMode | str = MatchMode.EXACT,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> FragmentAssertion:
    """Build a machine-exact assertion."""

    return _fragment_assertion(
        AssertionKind.MACHINE_EXACT,
        label,
        fragments,
        mode=mode,
        match=match,
        owner=owner,
        rationale=rationale,
        section=section,
        markers=markers,
        context=context,
    )


def public_exact(
    label: str,
    fragments: FragmentInput,
    *,
    owner: str | None = None,
    rationale: str | None = None,
    mode: FragmentMode | str = FragmentMode.ALL,
    match: MatchMode | str = MatchMode.EXACT,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> FragmentAssertion:
    """Build a public-exact assertion."""

    return _fragment_assertion(
        AssertionKind.PUBLIC_EXACT,
        label,
        fragments,
        mode=mode,
        match=match,
        owner=owner,
        rationale=rationale,
        section=section,
        markers=markers,
        context=context,
    )


def semantic_anchor(
    label: str,
    fragments: FragmentInput,
    *,
    mode: FragmentMode | str = FragmentMode.ALL,
    match: MatchMode | str = MatchMode.EXACT,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> FragmentAssertion:
    """Build a semantic-anchor assertion for non-exact wording contracts."""

    return _fragment_assertion(
        AssertionKind.SEMANTIC_ANCHOR,
        label,
        fragments,
        mode=mode,
        match=match,
        section=section,
        markers=markers,
        context=context,
    )


def semantic_concept(
    label: str,
    *,
    required: FragmentInput | None = None,
    forbidden: FragmentInput | None = None,
    match: MatchMode | str = MatchMode.CASEFOLD_NORMALIZED,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> tuple[FragmentAssertion, ...]:
    """Build grouped semantic assertions with required anchors and stale negatives."""

    if not label.strip():
        raise ValueError("Semantic concept label must be non-empty")

    required_fragments = _normalize_optional_fragments(required)
    forbidden_fragments = _normalize_optional_fragments(forbidden)
    if not required_fragments and not forbidden_fragments:
        raise ValueError("Semantic concept requires at least one required or forbidden fragment")

    assertions: list[FragmentAssertion] = []
    if required_fragments:
        assertions.append(
            _fragment_assertion(
                AssertionKind.SEMANTIC_ANCHOR,
                f"{label} required anchors",
                required_fragments,
                match=match,
                section=section,
                markers=markers,
                context=context,
            )
        )
    if forbidden_fragments:
        assertions.append(
            _fragment_assertion(
                AssertionKind.FORBIDDEN_DUPLICATE,
                f"{label} forbidden stale fragments",
                forbidden_fragments,
                mode=FragmentMode.COUNT,
                match=match,
                max_count=0,
                section=section,
                markers=markers,
                context=context,
            )
        )
    return tuple(assertions)


def fail_closed_before_writes(
    blocker_anchor: str,
    write_anchor: str,
    *,
    safe_stop_anchor: str | None = None,
    forbidden: FragmentInput | None = None,
    machine_fragments: FragmentInput | None = None,
    public_fragments: FragmentInput | None = None,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> tuple[FragmentAssertion, ...]:
    """Build a semantic pack for surfacing a blocker before mutation routes."""

    assertions = [
        semantic_anchor(
            "fail_closed_before_writes blocker before write route",
            (blocker_anchor, write_anchor),
            mode=FragmentMode.ORDERED,
            match=MatchMode.CASEFOLD_NORMALIZED,
            section=section,
            markers=markers,
            context=context,
        )
    ]
    _extend_semantic_concept(
        assertions,
        "fail_closed_before_writes",
        required=safe_stop_anchor,
        forbidden=forbidden,
        section=section,
        markers=markers,
        context=context,
    )
    _append_machine_exact(assertions, "fail_closed_before_writes machine anchors", machine_fragments, section, markers)
    _append_public_exact(assertions, "fail_closed_before_writes public anchors", public_fragments, section, markers)
    return tuple(assertions)


def fresh_artifact_required(
    artifact_paths: FragmentInput,
    freshness_anchor: str,
    *,
    files_written_field: str | None = None,
    status: str | None = None,
    freshness_marker: str | None = None,
    cli_flags: FragmentInput | None = None,
    required: FragmentInput | None = None,
    forbidden: FragmentInput | None = None,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> tuple[FragmentAssertion, ...]:
    """Build a pack for fresh artifact gates while keeping paths and flags exact."""

    assertions = [
        machine_exact(
            "fresh_artifact_required artifact paths",
            artifact_paths,
            section=section,
            markers=markers,
            context=context,
        )
    ]
    _append_machine_exact(
        assertions,
        "fresh_artifact_required machine contract",
        _fragment_tuple(files_written_field, status, freshness_marker, cli_flags),
        section,
        markers,
    )
    assertions.extend(
        semantic_concept(
            "fresh_artifact_required",
            required=_fragment_tuple(freshness_anchor, required),
            forbidden=forbidden,
            section=section,
            markers=markers,
            context=context,
        )
    )
    return tuple(assertions)


def no_synthesized_child_return(
    child_return_field: str,
    rejection_anchor: str,
    *,
    schema_fields: FragmentInput | None = None,
    required: FragmentInput | None = None,
    forbidden: FragmentInput | None = None,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> tuple[FragmentAssertion, ...]:
    """Build a pack for child-return provenance without weakening schema literals."""

    assertions = [
        machine_exact(
            "no_synthesized_child_return schema fields",
            _fragment_tuple(child_return_field, schema_fields),
            section=section,
            markers=markers,
            context=context,
        )
    ]
    assertions.extend(
        semantic_concept(
            "no_synthesized_child_return",
            required=_fragment_tuple(rejection_anchor, required),
            forbidden=forbidden,
            section=section,
            markers=markers,
            context=context,
        )
    )
    return tuple(assertions)


def handle_before_content(
    handle_field: str,
    content_field: str,
    *,
    behavior_anchor: str | None = None,
    required: FragmentInput | None = None,
    forbidden: FragmentInput | None = None,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> tuple[FragmentAssertion, ...]:
    """Build a pack for handle-first staged-init or behavior contracts."""

    assertions = [
        machine_exact(
            "handle_before_content field order",
            (handle_field, content_field),
            mode=FragmentMode.ORDERED,
            section=section,
            markers=markers,
            context=context,
        )
    ]
    _extend_semantic_concept(
        assertions,
        "handle_before_content",
        required=_fragment_tuple(behavior_anchor, required),
        forbidden=forbidden,
        section=section,
        markers=markers,
        context=context,
    )
    return tuple(assertions)


def runtime_label_native(
    runtime_label: str,
    native_rule_anchor: str,
    *,
    command_labels: FragmentInput | None = None,
    source_labels: FragmentInput | None = None,
    wrong_runtime_labels: FragmentInput | None = None,
    required: FragmentInput | None = None,
    forbidden: FragmentInput | None = None,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> tuple[FragmentAssertion, ...]:
    """Build a pack for native runtime labels while keeping visible labels exact."""

    assertions = [
        public_exact(
            "runtime_label_native visible labels",
            _fragment_tuple(runtime_label, command_labels, source_labels),
            section=section,
            markers=markers,
            context=context,
        )
    ]
    _append_public_exact(
        assertions,
        "runtime_label_native wrong labels absent",
        wrong_runtime_labels,
        section,
        markers,
        mode=FragmentMode.ABSENT,
    )
    assertions.extend(
        semantic_concept(
            "runtime_label_native",
            required=_fragment_tuple(native_rule_anchor, required),
            forbidden=forbidden,
            section=section,
            markers=markers,
            context=context,
        )
    )
    return tuple(assertions)


def checkpoint_stop_boundary(
    checkpoint_status: str,
    stop_anchor: str,
    *,
    bounded_fields: FragmentInput | None = None,
    resume_command: str | None = None,
    machine_fragments: FragmentInput | None = None,
    public_fragments: FragmentInput | None = None,
    required: FragmentInput | None = None,
    forbidden: FragmentInput | None = None,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> tuple[FragmentAssertion, ...]:
    """Build a pack for one-shot checkpoint stop and resume boundaries."""

    assertions = [
        machine_exact(
            "checkpoint_stop_boundary machine contract",
            _fragment_tuple(checkpoint_status, bounded_fields, machine_fragments),
            section=section,
            markers=markers,
            context=context,
        )
    ]
    _append_public_exact(
        assertions,
        "checkpoint_stop_boundary public continuation",
        _fragment_tuple(resume_command, public_fragments),
        section,
        markers,
    )
    assertions.extend(
        semantic_concept(
            "checkpoint_stop_boundary",
            required=_fragment_tuple(stop_anchor, required),
            forbidden=forbidden,
            section=section,
            markers=markers,
            context=context,
        )
    )
    return tuple(assertions)


def schema_averse_first_useful_action(
    useful_action_anchor: str,
    schema_anchor: str,
    *,
    metric_keys: FragmentInput | None = None,
    allowed_classes: FragmentInput | None = None,
    required: FragmentInput | None = None,
    forbidden: FragmentInput | None = None,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> tuple[FragmentAssertion, ...]:
    """Build a pack for useful action before schema-heavy interaction."""

    assertions = [
        semantic_anchor(
            "schema_averse_first_useful_action useful before schema",
            (useful_action_anchor, schema_anchor),
            mode=FragmentMode.ORDERED,
            match=MatchMode.CASEFOLD_NORMALIZED,
            section=section,
            markers=markers,
            context=context,
        )
    ]
    _append_machine_exact(
        assertions,
        "schema_averse_first_useful_action metric contract",
        _fragment_tuple(metric_keys, allowed_classes),
        section,
        markers,
    )
    _extend_semantic_concept(
        assertions,
        "schema_averse_first_useful_action",
        required=required,
        forbidden=forbidden,
        section=section,
        markers=markers,
        context=context,
    )
    return tuple(assertions)


def fragment_count(
    label: str,
    fragments: FragmentInput,
    *,
    expected_count: int,
    match: MatchMode | str = MatchMode.EXACT,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> FragmentAssertion:
    """Build a semantic-anchor count assertion."""

    return _fragment_assertion(
        AssertionKind.SEMANTIC_ANCHOR,
        label,
        fragments,
        mode=FragmentMode.COUNT,
        match=match,
        expected_count=expected_count,
        section=section,
        markers=markers,
        context=context,
    )


def forbidden_duplicate(
    label: str,
    fragment: str,
    *,
    max_count: int = 1,
    match: MatchMode | str = MatchMode.EXACT,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> FragmentAssertion:
    """Build an assertion that a fragment does not appear more than ``max_count`` times."""

    return _fragment_assertion(
        AssertionKind.FORBIDDEN_DUPLICATE,
        label,
        fragment,
        mode=FragmentMode.COUNT,
        match=match,
        max_count=max_count,
        section=section,
        markers=markers,
        context=context,
    )


def assert_prompt_contracts(text: str, *assertions: FragmentAssertion) -> None:
    """Assert prompt fragment contracts against text."""

    for assertion in assertions:
        if not isinstance(assertion, FragmentAssertion):
            raise TypeError(f"assert_prompt_contracts expected FragmentAssertion, got {type(assertion).__name__}")
        assertion.check(text)


def assert_fragments(text: str, assertion: FragmentAssertion) -> None:
    """Assert a fragment assertion against text."""

    scoped_text, context = _scope_text(text, assertion)
    mode = assertion.mode
    match = assertion.match
    match_detail = _match_detail(assertion)
    haystack = _match_text(scoped_text, match)
    fragments = tuple((fragment, _match_text(fragment, match)) for fragment in assertion.fragments)

    if mode is FragmentMode.ALL:
        for fragment, needle in fragments:
            if needle not in haystack:
                _raise_failure(
                    assertion, context, f"missing fragment={fragment!r}", f"mode={mode.value}", *match_detail
                )
        return

    if mode is FragmentMode.ANY:
        if not any(needle in haystack for _fragment, needle in fragments):
            _raise_failure(
                assertion,
                context,
                "missing any fragment from group=" + repr(assertion.fragments),
                f"mode={mode.value}",
                *match_detail,
            )
        return

    if mode is FragmentMode.ORDERED:
        offset = 0
        previous_fragment = "<start>"
        for fragment, needle in fragments:
            index = haystack.find(needle, offset)
            if index == -1:
                _raise_failure(
                    assertion,
                    context,
                    f"missing fragment={fragment!r}",
                    f"after fragment={previous_fragment!r}",
                    f"mode={mode.value}",
                    *match_detail,
                )
            offset = index + len(needle)
            previous_fragment = fragment
        return

    if mode is FragmentMode.ABSENT:
        for fragment, needle in fragments:
            count = haystack.count(needle)
            if count:
                _raise_failure(
                    assertion,
                    context,
                    f"forbidden fragment={fragment!r}",
                    f"count={count}",
                    f"mode={mode.value}",
                    *match_detail,
                )
        return

    if mode is FragmentMode.COUNT:
        for fragment, needle in fragments:
            observed = haystack.count(needle)
            if assertion.expected_count is not None and observed != assertion.expected_count:
                _raise_failure(
                    assertion,
                    context,
                    f"fragment={fragment!r}",
                    f"observed_count={observed}",
                    f"expected_count={assertion.expected_count}",
                    f"mode={mode.value}",
                    *match_detail,
                )
            if assertion.max_count is not None and observed > assertion.max_count:
                fragment_label = (
                    "duplicate fragment" if assertion.kind is AssertionKind.FORBIDDEN_DUPLICATE else "fragment"
                )
                _raise_failure(
                    assertion,
                    context,
                    f"{fragment_label}={fragment!r}",
                    f"observed_count={observed}",
                    f"max_count={assertion.max_count}",
                    f"mode={mode.value}",
                    *match_detail,
                )
        return

    raise AssertionError(f"Unhandled fragment mode: {mode.value}")


def _fragment_assertion(
    kind: AssertionKind,
    label: str,
    fragments: FragmentInput,
    *,
    mode: FragmentMode | str = FragmentMode.ALL,
    match: MatchMode | str = MatchMode.EXACT,
    owner: str | None = None,
    rationale: str | None = None,
    section: str | None = None,
    markers: MarkerInput | None = None,
    expected_count: int | None = None,
    max_count: int | None = None,
    context: str | None = None,
) -> FragmentAssertion:
    return FragmentAssertion(
        kind=kind,
        label=label,
        fragments=_normalize_fragments(fragments),
        mode=FragmentMode(mode),
        match=MatchMode(match),
        owner=owner,
        rationale=rationale,
        section=section,
        markers=_coerce_marker_scope(markers),
        expected_count=expected_count,
        max_count=max_count,
        context=context,
    )


def _normalize_fragments(fragments: FragmentInput) -> tuple[str, ...]:
    if isinstance(fragments, str):
        return (fragments,)
    return tuple(fragments)


def _normalize_optional_fragments(fragments: FragmentInput | None) -> tuple[str, ...]:
    if fragments is None:
        return ()
    return _normalize_fragments(fragments)


def _fragment_tuple(*groups: FragmentInput | None) -> tuple[str, ...]:
    fragments: list[str] = []
    for group in groups:
        fragments.extend(_normalize_optional_fragments(group))
    return tuple(fragments)


def _append_machine_exact(
    assertions: list[FragmentAssertion],
    label: str,
    fragments: FragmentInput | None,
    section: str | None,
    markers: MarkerInput | None,
    *,
    mode: FragmentMode | str = FragmentMode.ALL,
) -> None:
    normalized = _normalize_optional_fragments(fragments)
    if normalized:
        assertions.append(machine_exact(label, normalized, mode=mode, section=section, markers=markers))


def _append_public_exact(
    assertions: list[FragmentAssertion],
    label: str,
    fragments: FragmentInput | None,
    section: str | None,
    markers: MarkerInput | None,
    *,
    mode: FragmentMode | str = FragmentMode.ALL,
) -> None:
    normalized = _normalize_optional_fragments(fragments)
    if normalized:
        assertions.append(public_exact(label, normalized, mode=mode, section=section, markers=markers))


def _extend_semantic_concept(
    assertions: list[FragmentAssertion],
    label: str,
    *,
    required: FragmentInput | None,
    forbidden: FragmentInput | None,
    section: str | None,
    markers: MarkerInput | None,
    context: str | None,
) -> None:
    required_fragments = _normalize_optional_fragments(required)
    forbidden_fragments = _normalize_optional_fragments(forbidden)
    if required_fragments or forbidden_fragments:
        assertions.extend(
            semantic_concept(
                label,
                required=required_fragments,
                forbidden=forbidden_fragments,
                section=section,
                markers=markers,
                context=context,
            )
        )


def _coerce_marker_scope(markers: MarkerInput | None) -> MarkerScope | None:
    if markers is None or isinstance(markers, MarkerScope):
        return markers
    if len(markers) not in {1, 2}:
        raise ValueError("Marker tuple scopes require one start marker or a start/end pair")
    if len(markers) == 1:
        return MarkerScope(start=markers[0])
    return MarkerScope(start=markers[0], end=markers[1])


def _scope_text(text: str, assertion: FragmentAssertion) -> tuple[str, str]:
    scoped_text = text
    contexts = [assertion.context or "full text"]

    if assertion.section is not None:
        scoped_text = _extract_markdown_section(scoped_text, assertion.section, assertion)
        contexts.append(f"section {assertion.section!r}")

    if assertion.markers is not None:
        scoped_text = _extract_marker_range(scoped_text, assertion.markers, assertion, " / ".join(contexts))
        end_marker = assertion.markers.end if assertion.markers.end is not None else "<end>"
        contexts.append(f"markers {assertion.markers.start!r}..{end_marker!r}")

    return scoped_text, " / ".join(contexts)


def _match_text(text: str, match: MatchMode) -> str:
    if match is MatchMode.EXACT:
        return text
    normalized = " ".join(text.split())
    if match is MatchMode.NORMALIZED:
        return normalized
    if match is MatchMode.CASEFOLD_NORMALIZED:
        return normalized.casefold()
    raise AssertionError(f"Unhandled match mode: {match.value}")


def _match_detail(assertion: FragmentAssertion) -> tuple[str, ...]:
    if assertion.match is MatchMode.EXACT:
        return ()
    return (f"match={assertion.match.value}",)


def _extract_markdown_section(text: str, section: str, assertion: FragmentAssertion) -> str:
    context = assertion.context or "full text"
    try:
        return extract_markdown_section_text(text, section, context=context, include_heading=True)
    except AssertionError as exc:
        _raise_failure(assertion, context, f"section scope failed: {exc}")


def _extract_marker_range(
    text: str,
    markers: MarkerScope,
    assertion: FragmentAssertion,
    context: str,
) -> str:
    try:
        return extract_marker_range_text(text, markers.start, markers.end, context=context)
    except AssertionError as exc:
        _raise_failure(assertion, context, f"marker scope failed: {exc}")


def _raise_failure(assertion: FragmentAssertion, context: str, *details: str) -> None:
    lines = [
        "Assertion taxonomy failure:",
        f"kind={assertion.kind.value}",
        f"label={assertion.label}",
        f"context={context}",
        *details,
    ]
    if assertion.owner is not None:
        lines.append(f"owner={assertion.owner}")
    if assertion.rationale is not None:
        lines.append(f"rationale={assertion.rationale}")
    raise AssertionTaxonomyError("\n".join(lines))
