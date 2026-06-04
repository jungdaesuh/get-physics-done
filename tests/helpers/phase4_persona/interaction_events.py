"""Class-only fake interaction events for provider-free persona behavior tests."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields

_NO_SIGNAL_CLASSES = frozenset({"", "none", "not_applicable", "unknown"})
_STOP_CLASSES = frozenset({"abort", "review_stop", "stop", "stopped_before_dispatch", "user_abort_stops_dispatch"})
_QUESTION_CLASSES = frozenset(
    {
        "alignment_answer_required",
        "ask_user",
        "ask_user_alignment",
        "ask_user_answer_missing",
        "closeout_offer_next",
        "question",
        "schema_repair_request",
        "single_question",
    }
)
_COMMAND_ACTION_CLASSES = frozenset(
    {
        "command_hint",
        "concrete_command",
        "execute_command",
        "immediate_command",
        "next_up_command",
        "run_command",
        "runtime_command",
        "runtime_verify_work",
        "verify_work",
    }
)
_BOUNDED_RESUME_CLASSES = frozenset(
    {
        "bounded_resume",
        "bounded_segment_resume",
        "continuation_preserved",
        "gpd_resume_work",
        "resume_work",
    }
)
_RAW_RELOAD_CLASSES = frozenset(
    {
        "provider_runtime_reload_visible",
        "raw_init_visible",
        "raw_reload_instruction_visible",
        "raw_stage_field_access_visible",
        "stage_field_access_raw_visible",
    }
)
_HANDLE_CLASSES = frozenset(
    {
        "artifact_handle_selected",
        "handle_before_content",
        "handle_first",
        "handle_selected",
        "reference_handle_selected",
        "selected_handle",
    }
)
_SELECTION_CLASSES = _HANDLE_CLASSES | frozenset(
    {
        "artifact_selected",
        "choice_selected",
        "reference_selected",
        "selection_made",
        "select_reference",
    }
)
_CONTENT_CLASSES = frozenset(
    {
        "content_before_handle",
        "content_before_selection",
        "content_first",
        "content_loaded",
        "full_content_loaded",
        "hydrated_before_selection",
        "hydrated_content",
        "reference_content_loaded",
    }
)
_BAD_HYDRATION_CLASSES = frozenset(
    {
        "content_before_handle",
        "content_before_selection",
        "content_first",
        "hydrated_before_selection",
    }
)
_TURN_COUNT_FIELDS = (
    "speaker_class",
    "intent_class",
    "action_class",
    "question_bucket_class",
    "schema_surface_class",
    "physics_progress_class",
    "stop_class",
    "reload_surface_class",
    "artifact_handle_class",
    "content_hydration_class",
)
_GENERIC_EVENT_FIELDS = (
    "behavior_bucket_class",
    "user_answer_class",
    "gate_class",
    "autonomy_class",
    "tangent_decision_class",
    "active_resume_kind_class",
    "advisory_resume_class",
)


@dataclass(frozen=True, slots=True)
class FakePersonaTurn:
    """One sanitized interaction turn represented only by class tokens."""

    turn_index: int
    speaker_class: str
    intent_class: str
    action_class: str
    question_bucket_class: str = "none"
    schema_surface_class: str = "none"
    physics_progress_class: str = "none"
    stop_class: str = "not_applicable"
    reload_surface_class: str = "none"
    artifact_handle_class: str = "not_applicable"
    content_hydration_class: str = "none"

    def __post_init__(self) -> None:
        if self.turn_index < 0:
            raise ValueError("turn_index must be non-negative")
        for field in fields(self):
            if field.name == "turn_index":
                continue
            _assert_class_token(getattr(self, field.name), field.name)


@dataclass(frozen=True, slots=True)
class FakePersonaTrace:
    """A provider-free fake trace with no raw prompts, replies, or tool output."""

    row_id: str
    persona_class: str
    prompt_variant_class: str
    turns: tuple[FakePersonaTurn, ...]

    def __post_init__(self) -> None:
        _assert_class_token(self.row_id, "row_id")
        _assert_class_token(self.persona_class, "persona_class")
        _assert_class_token(self.prompt_variant_class, "prompt_variant_class")
        object.__setattr__(self, "turns", tuple(self.turns))
        turn_indexes = tuple(turn.turn_index for turn in self.turns)
        if len(set(turn_indexes)) != len(turn_indexes):
            raise ValueError("FakePersonaTrace turn indexes must be unique")


def event_class_counts(event: object | None) -> Mapping[str, int]:
    """Count all visible class tokens in a fake trace or simple class event."""

    turns = _sorted_turns(event)
    if turns:
        counts: Counter[str] = Counter()
        for turn in turns:
            for field_name in _TURN_COUNT_FIELDS:
                token = _turn_token(turn, field_name)
                if _has_signal(token):
                    counts[token] += 1
        return dict(sorted(counts.items()))

    raw_counts = _get(event, "event_class_counts")
    if isinstance(raw_counts, Mapping):
        return _sanitized_count_map(raw_counts)

    counts = Counter()
    for field_name in _GENERIC_EVENT_FIELDS:
        token = _normalize_token(_get(event, field_name))
        if _has_signal(token):
            counts[token] += 1
    for token in _tokens(_get(event, "question_bucket_classes")):
        if _has_signal(token):
            counts[token] += 1
    return dict(sorted(counts.items()))


def question_bucket_counts(event: object | None) -> Mapping[str, int]:
    """Count repeated user-question bucket classes without storing question text."""

    turns = _sorted_turns(event)
    if turns:
        counts = Counter(
            token for token in (_turn_token(turn, "question_bucket_class") for turn in turns) if _has_signal(token)
        )
        return dict(sorted(counts.items()))

    raw_counts = _get(event, "question_bucket_counts")
    if isinstance(raw_counts, Mapping):
        return _sanitized_count_map(raw_counts)

    buckets = _tokens(_get(event, "question_bucket_classes"))
    if buckets:
        counts = Counter(token for token in buckets if _has_signal(token))
        return dict(sorted(counts.items()))

    event_counts = _get(event, "event_class_counts")
    if isinstance(event_counts, Mapping):
        return {
            key: count
            for key, count in _sanitized_count_map(event_counts).items()
            if "question" in key or "ask_user" in key
        }
    return {}


def physics_progress_count(event: object | None) -> int:
    """Count turns that make class-only physics or research progress."""

    return _count_turn_field(event, "physics_progress_class")


def schema_surface_count(event: object | None) -> int:
    """Count turns that expose schema, reload, or repair ceremony classes."""

    return _count_turn_field(event, "schema_surface_class")


def conversation_turn_count(event: object | None) -> int:
    """Count fake class-only turns."""

    return len(_sorted_turns(event))


def raw_reload_leakage_count(event: object | None) -> int:
    """Count class tokens that represent user-visible raw reload mechanics."""

    turns = _sorted_turns(event)
    if turns:
        count = 0
        for turn in turns:
            for token in (
                _turn_token(turn, "reload_surface_class"),
                _turn_token(turn, "schema_surface_class"),
                _turn_token(turn, "action_class"),
            ):
                if _is_raw_reload_token(token):
                    count += 1
        return count
    return sum(count for token, count in event_class_counts(event).items() if _is_raw_reload_token(token))


def content_hydration_before_selection_count(event: object | None) -> int:
    """Count class-only content hydration before a handle or selection signal."""

    turns = _sorted_turns(event)
    if not turns:
        return sum(
            count
            for token, count in event_class_counts(event).items()
            if token in _BAD_HYDRATION_CLASSES or token in {"content_hydration_before_selection"}
        )

    selection_indexes = [
        turn.turn_index
        for turn in turns
        if _turn_token(turn, "artifact_handle_class") in _SELECTION_CLASSES
        or _turn_token(turn, "action_class") in _SELECTION_CLASSES
    ]
    first_selection_index = min(selection_indexes) if selection_indexes else None
    count = 0
    for turn in turns:
        content_tokens = (
            _turn_token(turn, "content_hydration_class"),
            _turn_token(turn, "artifact_handle_class"),
        )
        has_content = any(token in _CONTENT_CLASSES for token in content_tokens)
        explicit_bad = any(token in _BAD_HYDRATION_CLASSES for token in content_tokens)
        before_selection = first_selection_index is None or turn.turn_index < first_selection_index
        if explicit_bad or (has_content and before_selection):
            count += 1
    return count


def first_useful_action_class(event: object | None) -> str:
    """Classify the first useful persona action without storing its text."""

    turns = _sorted_turns(event)
    if not turns:
        return "not_applicable"

    question_count = 0
    for position, turn in enumerate(turns):
        action = _turn_token(turn, "action_class")
        question = _turn_token(turn, "question_bucket_class")
        physics = _turn_token(turn, "physics_progress_class")
        stop = _turn_token(turn, "stop_class")
        if stop in _STOP_CLASSES or action in _STOP_CLASSES:
            return "safe_stop" if stop_integrity_class(event) == "stopped_cleanly" else "delayed"
        if action in _BOUNDED_RESUME_CLASSES or physics in _BOUNDED_RESUME_CLASSES:
            return "bounded_resume" if position == 0 else "delayed"
        if action in _COMMAND_ACTION_CLASSES or _has_signal(physics):
            return "immediate_command" if position == 0 else "delayed"
        if action in _QUESTION_CLASSES or question in _QUESTION_CLASSES or _has_signal(question):
            question_count += 1

    if question_count == 1:
        return "single_question"
    return "missing"


def stop_integrity_class(event: object | None) -> str:
    """Classify whether a stop/abort class actually stopped subsequent work."""

    turns = _sorted_turns(event)
    if not turns:
        return "not_applicable"
    stop_positions: list[int] = []
    for position, turn in enumerate(turns):
        stop = _turn_token(turn, "stop_class")
        action = _turn_token(turn, "action_class")
        if stop == "ambiguous_stop":
            return "ambiguous_stop"
        if stop in _STOP_CLASSES or action in _STOP_CLASSES:
            stop_positions.append(position)
    if not stop_positions:
        return "not_applicable"

    first_stop_position = min(stop_positions)
    for turn in turns[first_stop_position + 1 :]:
        if _turn_has_post_stop_activity(turn):
            return "post_stop_activity"
    return "stopped_cleanly"


def physics_to_schema_ratio_class(event: object | None) -> str:
    """Classify progress versus schema ceremony in a class-only trace."""

    if event is None:
        return "not_applicable"
    progress_count = physics_progress_count(event)
    schema_count = schema_surface_count(event)
    if progress_count == 0 and schema_count == 0:
        return "no_progress" if conversation_turn_count(event) else "not_applicable"
    if progress_count == 0:
        return "schema_dominant"
    if schema_count == 0 or progress_count > schema_count:
        return "progress_dominant"
    if progress_count == schema_count:
        return "balanced"
    return "schema_dominant"


def artifact_handle_first_class(event: object | None) -> str:
    """Classify whether artifact/reference handles appear before full content."""

    turns = _sorted_turns(event)
    if not turns:
        return "not_applicable"

    handle_indexes: list[int] = []
    content_indexes: list[int] = []
    for turn in turns:
        handle = _turn_token(turn, "artifact_handle_class")
        hydration = _turn_token(turn, "content_hydration_class")
        if handle in {"content_before_handle", "content_first"}:
            return "content_before_handle"
        if handle in _HANDLE_CLASSES:
            handle_indexes.append(turn.turn_index)
        if hydration in _CONTENT_CLASSES or handle in _CONTENT_CLASSES:
            content_indexes.append(turn.turn_index)

    if not handle_indexes and not content_indexes:
        return "not_applicable"
    if handle_indexes and not content_indexes:
        return "handle_before_content"
    if content_indexes and not handle_indexes:
        return "missing_handle"
    return "handle_before_content" if min(handle_indexes) <= min(content_indexes) else "content_before_handle"


def _count_turn_field(event: object | None, field_name: str) -> int:
    return sum(1 for turn in _sorted_turns(event) if _has_signal(_turn_token(turn, field_name)))


def _turn_has_post_stop_activity(turn: FakePersonaTurn) -> bool:
    for field_name in (
        "action_class",
        "schema_surface_class",
        "physics_progress_class",
        "reload_surface_class",
        "content_hydration_class",
    ):
        token = _turn_token(turn, field_name)
        if _has_signal(token) and token not in _STOP_CLASSES:
            return True
    return False


def _is_raw_reload_token(token: str) -> bool:
    return token in _RAW_RELOAD_CLASSES or "raw_reload" in token or "provider_runtime_reload" in token


def _sorted_turns(event: object | None) -> tuple[FakePersonaTurn, ...]:
    raw_turns = _get(event, "turns")
    if raw_turns is None or isinstance(raw_turns, (str, bytes, Mapping)):
        return ()
    if not isinstance(raw_turns, Iterable):
        return ()
    turns = tuple(turn for turn in raw_turns if isinstance(turn, FakePersonaTurn))
    return tuple(sorted(turns, key=lambda turn: turn.turn_index))


def _turn_token(turn: FakePersonaTurn, field_name: str) -> str:
    return _normalize_token(getattr(turn, field_name))


def _tokens(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        token = _normalize_token(value)
        return (token,) if token else ()
    if isinstance(value, Mapping):
        return tuple(_normalize_token(key) for key in value)
    if isinstance(value, Iterable):
        return tuple(_normalize_token(item) for item in value if _normalize_token(item))
    token = _normalize_token(value)
    return (token,) if token else ()


def _sanitized_count_map(value: Mapping[object, object]) -> dict[str, int]:
    return {
        token: max(0, int(count))
        for raw_token, count in value.items()
        if (token := _normalize_token(raw_token)) and _has_signal(token)
    }


def _has_signal(token: str) -> bool:
    return token not in _NO_SIGNAL_CLASSES


def _get(value: object | None, name: str, default: object | None = None) -> object | None:
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _normalize_token(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().replace("-", "_").replace(":", "_")


def _assert_class_token(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty class token")
    if value != value.strip() or any(character.isspace() for character in value) or "/" in value or "\\" in value:
        raise ValueError(f"{field_name} must be a class token, not raw text or a path")


__all__ = [
    "FakePersonaTrace",
    "FakePersonaTurn",
    "artifact_handle_first_class",
    "content_hydration_before_selection_count",
    "conversation_turn_count",
    "event_class_counts",
    "first_useful_action_class",
    "physics_progress_count",
    "physics_to_schema_ratio_class",
    "question_bucket_counts",
    "raw_reload_leakage_count",
    "schema_surface_count",
    "stop_integrity_class",
]
