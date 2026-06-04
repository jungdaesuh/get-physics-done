"""Tests for assertion taxonomy support helpers."""

from __future__ import annotations

import pytest

from tests.assertion_taxonomy_support import (
    AssertionKind,
    AssertionTaxonomyError,
    FragmentMode,
    MatchMode,
    assert_prompt_contracts,
    checkpoint_stop_boundary,
    fail_closed_before_writes,
    forbidden_duplicate,
    fragment_count,
    fresh_artifact_required,
    handle_before_content,
    machine_exact,
    marker_range,
    no_synthesized_child_return,
    public_exact,
    runtime_label_native,
    schema_averse_first_useful_action,
    semantic_anchor,
    semantic_concept,
)

SAMPLE_TEXT = """# Surface
outside-only legacy phrase

## Machine Contract
BEGIN MACHINE
alpha token
beta token
gamma token
repeat warning
repeat warning
END MACHINE

## Public Contract
first public phrase
second public phrase
"""


def test_assertion_taxonomy_values_are_stable_contract() -> None:
    assert tuple(kind.value for kind in AssertionKind) == (
        "machine_exact",
        "public_exact",
        "semantic_anchor",
        "forbidden_duplicate",
    )
    assert tuple(mode.value for mode in FragmentMode) == ("all", "any", "ordered", "absent", "count")
    assert tuple(match.value for match in MatchMode) == ("exact", "normalized", "casefold_normalized")


def test_exact_assertion_constructors_accept_optional_metadata() -> None:
    machine_exact("schema field", "gpd_return:").check("gpd_return: {}")

    assertion = public_exact(
        "public help wording",
        "first public phrase",
        owner="cli-help",
        rationale="documented public CLI output",
        section="## Public Contract",
    )

    assert assertion.kind is AssertionKind.PUBLIC_EXACT
    assert assertion.owner == "cli-help"
    assertion.check(SAMPLE_TEXT)


def test_fragment_modes_cover_all_any_ordered_absent_and_count_with_scopes() -> None:
    scoped_markers = marker_range("BEGIN MACHINE", "END MACHINE")

    semantic_anchor(
        "machine anchors",
        ("alpha token", "beta token"),
        mode=FragmentMode.ALL,
        section="## Machine Contract",
        markers=scoped_markers,
    ).check(SAMPLE_TEXT)
    semantic_anchor(
        "alternate public wording",
        ("missing public phrase", "second public phrase"),
        mode=FragmentMode.ANY,
        section="Public Contract",
    ).check(SAMPLE_TEXT)
    machine_exact(
        "ordered machine fields",
        ("alpha token", "beta token", "gamma token"),
        owner="state-schema",
        rationale="machine parser consumes this field order",
        mode=FragmentMode.ORDERED,
        section="Machine Contract",
        markers=("BEGIN MACHINE", "END MACHINE"),
    ).check(SAMPLE_TEXT)
    semantic_anchor(
        "marker scope excludes outside phrase",
        "outside-only legacy phrase",
        mode=FragmentMode.ABSENT,
        section="Machine Contract",
        markers=scoped_markers,
    ).check(SAMPLE_TEXT)
    fragment_count(
        "single gamma",
        "gamma token",
        expected_count=1,
        section="Machine Contract",
        markers=scoped_markers,
    ).check(SAMPLE_TEXT)


def test_match_modes_keep_exact_default_and_allow_explicit_normalization() -> None:
    text = "The lifecycle\n  keeps plan checkpoints."

    with pytest.raises(AssertionTaxonomyError) as exact_exc_info:
        semantic_anchor("default exact anchor", "lifecycle keeps plan checkpoints").check(text)

    assert "missing fragment='lifecycle keeps plan checkpoints'" in str(exact_exc_info.value)
    assert "match=normalized" not in str(exact_exc_info.value)

    semantic_anchor(
        "normalized anchor",
        "lifecycle keeps plan checkpoints",
        match=MatchMode.NORMALIZED,
    ).check(text)

    with pytest.raises(AssertionTaxonomyError) as normalized_exc_info:
        semantic_anchor(
            "normalized remains case-sensitive",
            "the lifecycle keeps plan checkpoints",
            match=MatchMode.NORMALIZED,
        ).check(text)

    assert "match=normalized" in str(normalized_exc_info.value)

    semantic_anchor(
        "casefold normalized anchor",
        "the lifecycle keeps plan checkpoints",
        match=MatchMode.CASEFOLD_NORMALIZED,
    ).check(text)


def test_semantic_concept_groups_required_anchors_and_forbidden_stale_fragments() -> None:
    assertions = semantic_concept(
        "machine concept",
        required=("ALPHA TOKEN", "beta token"),
        forbidden=("outside-only legacy phrase", "retired stale phrase"),
        section="Machine Contract",
        markers=marker_range("BEGIN MACHINE", "END MACHINE"),
    )

    assert tuple(assertion.kind for assertion in assertions) == (
        AssertionKind.SEMANTIC_ANCHOR,
        AssertionKind.FORBIDDEN_DUPLICATE,
    )
    assert all(assertion.match is MatchMode.CASEFOLD_NORMALIZED for assertion in assertions)
    assert_prompt_contracts(SAMPLE_TEXT, *assertions)


def test_semantic_concept_failure_preserves_required_and_forbidden_failure_details() -> None:
    required = semantic_concept("required concept", required="missing semantic anchor")
    with pytest.raises(AssertionTaxonomyError) as required_exc_info:
        assert_prompt_contracts(SAMPLE_TEXT, *required)

    required_message = str(required_exc_info.value)
    assert "kind=semantic_anchor" in required_message
    assert "label=required concept required anchors" in required_message
    assert "missing fragment='missing semantic anchor'" in required_message

    forbidden = semantic_concept(
        "forbidden concept",
        forbidden="repeat warning",
        section="Machine Contract",
        markers=("BEGIN MACHINE", "END MACHINE"),
    )
    with pytest.raises(AssertionTaxonomyError) as forbidden_exc_info:
        assert_prompt_contracts(SAMPLE_TEXT, *forbidden)

    forbidden_message = str(forbidden_exc_info.value)
    assert "kind=forbidden_duplicate" in forbidden_message
    assert "label=forbidden concept forbidden stale fragments" in forbidden_message
    assert "duplicate fragment='repeat warning'" in forbidden_message
    assert "max_count=0" in forbidden_message


def test_semantic_concept_rejects_empty_concepts() -> None:
    with pytest.raises(ValueError, match="requires at least one required or forbidden fragment"):
        semantic_concept("empty concept")


def test_phase8_concept_pack_helpers_keep_domain_tokens_exact() -> None:
    text = """
Dirty worktree blocker
Fail closed before files_modified write route
recovery command: gpd status
gpd_return.files_written
status: completed
artifacts/phase1/result.json
fresh-after marker flex-pass10-marker-123
validator flag --fresh-after
Do not synthesize child return; retry child worker.
gpd_return
continuation_update.bounded_segment.resume_file
reference_artifact_files
reference_artifacts_content
handle first behavior
Runtime label: Show /gpd:start as native labels;
source label gpd:start
checkpoint
stop immediately after returning checkpoint; resume with gpd resume-work
first useful action
schema fields after action
first_useful_action_class
immediate_command
"""

    assertions = (
        *fail_closed_before_writes(
            "Dirty worktree blocker",
            "files_modified write route",
            safe_stop_anchor="Fail closed",
            public_fragments="gpd status",
        ),
        *fresh_artifact_required(
            "artifacts/phase1/result.json",
            "fresh-after marker",
            files_written_field="gpd_return.files_written",
            status="completed",
            freshness_marker="flex-pass10-marker-123",
            cli_flags="--fresh-after",
        ),
        *no_synthesized_child_return(
            "gpd_return",
            "Do not synthesize child return",
            required="retry child worker",
            forbidden="parent-authored success",
        ),
        *handle_before_content(
            "reference_artifact_files",
            "reference_artifacts_content",
            behavior_anchor="handle first behavior",
        ),
        *runtime_label_native(
            "/gpd:start",
            "native labels",
            command_labels="gpd:start",
            wrong_runtime_labels="$gpd-start",
        ),
        *checkpoint_stop_boundary(
            "checkpoint",
            "stop immediately",
            bounded_fields="continuation_update.bounded_segment.resume_file",
            resume_command="gpd resume-work",
        ),
        *schema_averse_first_useful_action(
            "first useful action",
            "schema fields",
            metric_keys="first_useful_action_class",
            allowed_classes="immediate_command",
        ),
    )

    assert_prompt_contracts(text, *assertions)
    assert any(
        assertion.kind is AssertionKind.MACHINE_EXACT and "artifacts/phase1/result.json" in assertion.fragments
        for assertion in assertions
    )
    assert any(
        assertion.kind is AssertionKind.PUBLIC_EXACT and "/gpd:start" in assertion.fragments
        for assertion in assertions
    )
    assert any(
        assertion.label == "handle_before_content field order" and assertion.mode is FragmentMode.ORDERED
        for assertion in assertions
    )


def test_phase8_runtime_label_helper_keeps_wrong_labels_public_exact_absent() -> None:
    assertions = runtime_label_native(
        "/gpd:resume-work",
        "native labels",
        command_labels="/gpd:progress",
        wrong_runtime_labels=("$gpd-resume-work", "/gpd:set-profile"),
    )

    wrong_label_assertion = next(
        assertion for assertion in assertions if assertion.label == "runtime_label_native wrong labels absent"
    )

    assert wrong_label_assertion.kind is AssertionKind.PUBLIC_EXACT
    assert wrong_label_assertion.mode is FragmentMode.ABSENT
    assert wrong_label_assertion.fragments == ("$gpd-resume-work", "/gpd:set-profile")


def test_phase8_concept_pack_helpers_reject_empty_domain_anchors() -> None:
    with pytest.raises(ValueError, match="at least one non-empty fragment"):
        fail_closed_before_writes("", "write route")

    with pytest.raises(ValueError, match="at least one non-empty fragment"):
        fresh_artifact_required((), "fresh marker")


def test_match_modes_apply_to_ordered_absent_and_count_modes() -> None:
    text = """First
stage

SECOND   stage

Repeat
 warning
repeat warning
"""

    semantic_anchor(
        "casefold normalized ordered anchors",
        ("first stage", "second stage"),
        mode=FragmentMode.ORDERED,
        match=MatchMode.CASEFOLD_NORMALIZED,
    ).check(text)
    fragment_count(
        "casefold normalized duplicate count",
        "repeat warning",
        expected_count=2,
        match=MatchMode.CASEFOLD_NORMALIZED,
    ).check(text)

    with pytest.raises(AssertionTaxonomyError) as exc_info:
        semantic_anchor(
            "casefold normalized absence",
            "second stage",
            mode=FragmentMode.ABSENT,
            match="casefold_normalized",
        ).check(text)

    message = str(exc_info.value)
    assert "forbidden fragment='second stage'" in message
    assert "match=casefold_normalized" in message


def test_assert_prompt_contracts_uses_fence_aware_section_scopes() -> None:
    text = """# Surface

```markdown
## Machine Contract
fenced-only phrase
```

## Machine Contract
real phrase
"""

    assert_prompt_contracts(
        text,
        semantic_anchor("real section", "real phrase", section="Machine Contract"),
        semantic_anchor(
            "fenced section excluded", "fenced-only phrase", mode=FragmentMode.ABSENT, section="## Machine Contract"
        ),
    )


def test_missing_fragment_failure_names_kind_label_context_and_fragment() -> None:
    assertion = semantic_anchor("required public anchor", "missing phrase", section="## Public Contract")

    with pytest.raises(AssertionTaxonomyError) as exc_info:
        assertion.check(SAMPLE_TEXT)

    message = str(exc_info.value)
    assert "kind=semantic_anchor" in message
    assert "label=required public anchor" in message
    assert "context=full text / section '## Public Contract'" in message
    assert "missing fragment='missing phrase'" in message


def test_forbidden_duplicate_failure_names_duplicate_fragment() -> None:
    assertion = forbidden_duplicate(
        "no duplicate machine warning",
        "repeat warning",
        section="Machine Contract",
        markers=marker_range("BEGIN MACHINE", "END MACHINE"),
    )

    with pytest.raises(AssertionTaxonomyError) as exc_info:
        assertion.check(SAMPLE_TEXT)

    message = str(exc_info.value)
    assert "kind=forbidden_duplicate" in message
    assert "label=no duplicate machine warning" in message
    assert "duplicate fragment='repeat warning'" in message
    assert "observed_count=2" in message
    assert "max_count=1" in message
