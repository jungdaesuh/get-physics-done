"""Shared stage-authority assertions for prompt wiring tests."""

from __future__ import annotations

from gpd import registry

PUBLICATION_RESPONSE_WRITER_HANDOFF_AUTHORITY = "references/publication/publication-response-writer-handoff.md"
PUBLICATION_ROUND_ARTIFACTS_AUTHORITY = "references/publication/publication-review-round-artifacts.md"


def assert_loaded_authorities(command_name: str, stage_id: str, *authorities: str) -> None:
    staged_loading = registry.get_command(command_name).staged_loading

    assert staged_loading is not None
    loaded = tuple(staged_loading.stage(stage_id).loaded_authorities)
    missing = [authority for authority in authorities if authority not in loaded]
    assert not missing, f"{command_name}:{stage_id} missing loaded authorities: {missing}"


def assert_conditional_authorities(command_name: str, stage_id: str, when: str, *authorities: str) -> None:
    staged_loading = registry.get_command(command_name).staged_loading

    assert staged_loading is not None
    loaded = next(
        (
            tuple(conditional.authorities)
            for conditional in staged_loading.stage(stage_id).conditional_authorities
            if conditional.when == when
        ),
        (),
    )
    missing = [authority for authority in authorities if authority not in loaded]
    assert not missing, f"{command_name}:{stage_id}:{when} missing conditional authorities: {missing}"


def assert_write_paper_publication_review_authorities() -> None:
    assert_loaded_authorities("write-paper", "publication_review", PUBLICATION_ROUND_ARTIFACTS_AUTHORITY)
    assert_conditional_authorities(
        "write-paper",
        "publication_review",
        "response_pair_authoring",
        PUBLICATION_RESPONSE_WRITER_HANDOFF_AUTHORITY,
    )
