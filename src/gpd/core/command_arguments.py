"""Shared shell-like command argument helpers for registry preflights."""

from __future__ import annotations

import os
import shlex
from collections.abc import Callable
from pathlib import Path

from gpd.core.artifact_text import DIGEST_KNOWLEDGE_SOURCE_SUFFIXES
from gpd.core.arxiv_source_download import normalize_arxiv_id
from gpd.core.utils import normalize_ascii_slug
from gpd.core.write_paper_intake import has_write_paper_external_authoring_intake

_DIGEST_KNOWLEDGE_PATH_SUFFIXES = DIGEST_KNOWLEDGE_SOURCE_SUFFIXES


def _split_command_arguments(arguments: str | None) -> list[str]:
    """Split a raw command argument string into shell-like tokens."""

    if not arguments:
        return []
    try:
        return shlex.split(arguments)
    except ValueError:
        return arguments.split()


def _flag_values(arguments: str | None, *flags: str) -> list[str]:
    """Return non-empty values supplied to one or more long flags."""

    tokens = _split_command_arguments(arguments)
    values: list[str] = []
    skip_next = False
    flag_set = set(flags)

    for index, token in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        if token == "--":
            break
        if token in flag_set:
            skip_next = True
            if index + 1 >= len(tokens):
                continue
            next_token = tokens[index + 1].strip()
            if next_token and not next_token.startswith("-"):
                values.append(next_token)
            continue
        matched_flag = next((flag for flag in flags if token.startswith(f"{flag}=")), None)
        if matched_flag is None:
            continue
        value = token.partition("=")[2].strip()
        if value:
            values.append(value)

    return values


def _has_flag_value(tokens: list[str], flag: str) -> bool:
    """Return True when ``flag`` is present with a non-empty value."""

    for index, token in enumerate(tokens):
        if token == flag:
            if index + 1 < len(tokens):
                next_token = tokens[index + 1]
                if next_token and (not next_token.startswith("-") or _looks_like_negative_cli_value(next_token)):
                    return True
        elif token.startswith(f"{flag}="):
            return bool(token.partition("=")[2].strip())
    return False


def _looks_like_negative_cli_value(token: str) -> bool:
    """Return True for numeric CLI values that start with '-' but are not options."""

    return len(token) > 1 and token[0] == "-" and (token[1].isdigit() or token[1] == ".")


def _positional_tokens(arguments: str | None, *, flags_with_values: tuple[str, ...] = ()) -> list[str]:
    """Extract positional tokens after removing known long-option/value pairs."""

    tokens = _split_command_arguments(arguments)
    positionals: list[str] = []
    skip_next = False
    value_flags = set(flags_with_values)

    for index, token in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        if token == "--":
            return positionals + tokens[index + 1 :]
        if token in value_flags:
            skip_next = True
            continue
        if any(token.startswith(f"{flag}=") for flag in value_flags):
            continue
        if token.startswith("--"):
            continue
        positionals.append(token)

    return positionals


def _has_discover_explicit_inputs(arguments: str | None) -> bool:
    """Discover standalone mode needs either a phase number or a topic."""

    return bool(_positional_tokens(arguments, flags_with_values=("--depth", "-d")))


def _has_simple_positional_inputs(arguments: str | None) -> bool:
    """Generic detector for commands satisfied by any positional topic/target."""

    return bool(_positional_tokens(arguments))


def _has_sensitivity_explicit_inputs(arguments: str | None) -> bool:
    """Sensitivity analysis standalone mode requires both target and parameter list."""

    tokens = _split_command_arguments(arguments)
    return _has_flag_value(tokens, "--target") and _has_flag_value(tokens, "--params")


def _looks_like_parameter_sweep_anchor_token(token: str) -> bool:
    """Return True for a standalone/current-workspace parameter-sweep compute anchor."""

    if not token or token.startswith("-"):
        return False
    if token.isdigit():
        return False
    if token.startswith(("./", "../", "~/", "/", "@")):
        return True
    if os.sep in token or (os.altsep is not None and os.altsep in token):
        return True
    if Path(token).suffix:
        return True
    return any(character.isalpha() for character in token)


def _has_parameter_sweep_explicit_inputs(arguments: str | None) -> bool:
    """Parameter-sweep standalone mode needs param/range flags plus a non-phase compute anchor."""

    tokens = _split_command_arguments(arguments)
    if not (_has_flag_value(tokens, "--param") and _has_flag_value(tokens, "--range")):
        return False
    positionals = _positional_tokens(arguments, flags_with_values=("--param", "--range"))
    return any(_looks_like_parameter_sweep_anchor_token(token) for token in positionals)


def _looks_like_digest_knowledge_topic_token(token: str) -> bool:
    """Return True for a non-empty topic-like token."""

    if not token or token.startswith("-"):
        return False
    if _looks_like_digest_knowledge_path_token(token) or _looks_like_digest_knowledge_arxiv_token(token):
        return False
    return any(character.isalpha() for character in token)


def _looks_like_digest_knowledge_path_token(token: str) -> bool:
    """Return True for a token that looks like an explicit path input."""

    if not token or token.startswith("-"):
        return False
    if token.startswith(("./", "../", "~/", "/", "@")):
        return True
    if os.sep in token or (os.altsep is not None and os.altsep in token):
        return True
    return Path(token).suffix.lower() in _DIGEST_KNOWLEDGE_PATH_SUFFIXES


def _looks_like_digest_knowledge_arxiv_token(token: str) -> bool:
    """Return True for a token that normalizes as an arXiv identifier."""

    if not token or token.startswith("-"):
        return False
    try:
        normalize_arxiv_id(token)
    except ValueError:
        return False
    return True


def _looks_like_review_knowledge_id_token(token: str) -> bool:
    """Return True for a canonical knowledge identifier token."""

    if not token or token.startswith("-") or not token.startswith("K-"):
        return False
    slug = token[2:]
    return bool(slug) and normalize_ascii_slug(slug) == slug


def _looks_like_review_knowledge_path_token(token: str) -> bool:
    """Return True for an explicit knowledge-document path token."""

    if not token or token.startswith("-"):
        return False
    if not _looks_like_digest_knowledge_path_token(token):
        return False
    path = Path(token)
    if not (
        path.suffix.lower() == ".md"
        and path.stem.startswith("K-")
        and normalize_ascii_slug(path.stem[2:]) == path.stem[2:]
    ):
        return False

    normalized_parts = [part for part in path.as_posix().split("/") if part not in {"", "."}]
    if path.is_absolute():
        return len(normalized_parts) >= 3 and normalized_parts[-3:-1] == ["GPD", "knowledge"]
    return len(normalized_parts) >= 3 and normalized_parts[:2] == ["GPD", "knowledge"]


def _has_digest_knowledge_explicit_inputs(arguments: str | None) -> bool:
    """Digest-knowledge standalone mode needs an explicit topic, path, or arXiv input."""

    tokens = _split_command_arguments(arguments)
    return any(
        _looks_like_digest_knowledge_topic_token(token)
        or _looks_like_digest_knowledge_path_token(token)
        or _looks_like_digest_knowledge_arxiv_token(token)
        for token in tokens
    )


def _has_review_knowledge_explicit_inputs(arguments: str | None) -> bool:
    """Review-knowledge standalone mode needs an explicit knowledge path or canonical knowledge id."""

    tokens = _split_command_arguments(arguments)
    return any(
        _looks_like_review_knowledge_path_token(token) or _looks_like_review_knowledge_id_token(token)
        for token in tokens
    )


def _has_write_paper_external_authoring_intake(arguments: str | None) -> bool:
    """Return whether ``gpd:write-paper`` received an explicit ``--intake`` flag."""

    return has_write_paper_external_authoring_intake(arguments)


_PROJECT_AWARE_EXPLICIT_INPUT_PREDICATES: dict[str, Callable[[str | None], bool]] = {
    "gpd:compare-experiment": _has_simple_positional_inputs,
    "gpd:compare-results": _has_simple_positional_inputs,
    "gpd:derive-equation": _has_simple_positional_inputs,
    "gpd:dimensional-analysis": _has_simple_positional_inputs,
    "gpd:discover": _has_discover_explicit_inputs,
    "gpd:explain": _has_simple_positional_inputs,
    "gpd:digest-knowledge": _has_digest_knowledge_explicit_inputs,
    "gpd:review-knowledge": _has_review_knowledge_explicit_inputs,
    "gpd:limiting-cases": _has_simple_positional_inputs,
    "gpd:literature-review": _has_simple_positional_inputs,
    "gpd:numerical-convergence": _has_simple_positional_inputs,
    "gpd:parameter-sweep": _has_parameter_sweep_explicit_inputs,
    "gpd:sensitivity-analysis": _has_sensitivity_explicit_inputs,
    "gpd:write-paper": _has_write_paper_external_authoring_intake,
}
