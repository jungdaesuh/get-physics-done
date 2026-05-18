"""Tests for the session goal feature (RES-932)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gpd.core.context import _normalize_session_goal_context
from gpd.core.state import (
    SessionGoal,
    state_clear_session_goal,
    state_set_session_goal,
)


def _read_state_json(cwd: Path) -> dict:
    return json.loads((cwd / "GPD" / "state.json").read_text(encoding="utf-8"))


class TestSessionGoalState:
    def test_set_persists_text_only_goal(self, tmp_path: Path, state_project_factory) -> None:
        cwd = state_project_factory(tmp_path)
        result = state_set_session_goal(cwd, "Find the quantum gravity model")

        assert result.updated is True
        stored = _read_state_json(cwd)
        # ResearchState normalization fills optional Nones for missing keys; the
        # text field is what matters and the optional fields default to None.
        assert stored["session_goal"]["text"] == "Find the quantum gravity model"
        assert stored["session_goal"]["budget"] is None
        assert stored["session_goal"]["deadline"] is None

    def test_set_persists_budget_and_deadline(self, tmp_path: Path, state_project_factory) -> None:
        cwd = state_project_factory(tmp_path)
        result = state_set_session_goal(
            cwd,
            "  Ship the paper  ",
            budget=" $50 ",
            deadline=" 2026-05-20 ",
        )

        assert result.updated is True
        stored = _read_state_json(cwd)
        assert stored["session_goal"] == {
            "text": "Ship the paper",
            "budget": "$50",
            "deadline": "2026-05-20",
        }

    def test_set_rejects_empty_text(self, tmp_path: Path, state_project_factory) -> None:
        cwd = state_project_factory(tmp_path)
        result = state_set_session_goal(cwd, "   ")

        assert result.updated is False
        # state.json must not get a persisted goal on rejection. The schema
        # normalizer may still surface `session_goal: None`, which is the
        # same as "no goal set" — never a populated object.
        stored = _read_state_json(cwd)
        assert stored.get("session_goal") is None

    def test_set_is_idempotent_when_value_matches(
        self, tmp_path: Path, state_project_factory
    ) -> None:
        cwd = state_project_factory(tmp_path)
        first = state_set_session_goal(cwd, "Ship the paper", budget="$50")
        second = state_set_session_goal(cwd, "Ship the paper", budget="$50")

        assert first.updated is True
        assert second.updated is False
        assert second.unchanged is True

    def test_clear_removes_persisted_goal(self, tmp_path: Path, state_project_factory) -> None:
        cwd = state_project_factory(tmp_path)
        state_set_session_goal(cwd, "Ship the paper")

        cleared = state_clear_session_goal(cwd)
        assert cleared.updated is True
        stored = _read_state_json(cwd)
        # `None` is a permitted stored value — context.normalize handles it.
        assert stored.get("session_goal") is None

    def test_clear_is_idempotent_when_no_goal_set(
        self, tmp_path: Path, state_project_factory
    ) -> None:
        cwd = state_project_factory(tmp_path)
        result = state_clear_session_goal(cwd)
        assert result.updated is False


class TestSessionGoalContext:
    """`_normalize_session_goal_context` is the bridge that surfaces the goal
    into every init bundle — pin its shape since downstream prompts key on
    `derived_session_goal*` field names."""

    def test_missing_state_returns_all_none(self) -> None:
        ctx = _normalize_session_goal_context({})
        assert ctx == {
            "derived_session_goal": None,
            "derived_session_goal_text": None,
            "derived_session_goal_budget": None,
            "derived_session_goal_deadline": None,
        }

    def test_invalid_goal_returns_all_none(self) -> None:
        ctx = _normalize_session_goal_context({"session_goal": {"unexpected": "shape"}})
        # SessionGoal.model_config has extra="forbid", so this normalizes to None.
        assert ctx["derived_session_goal"] is None
        assert ctx["derived_session_goal_text"] is None
        assert ctx["derived_session_goal_budget"] is None
        assert ctx["derived_session_goal_deadline"] is None

    def test_valid_goal_is_surfaced_flat_and_nested(self) -> None:
        ctx = _normalize_session_goal_context(
            {
                "session_goal": {
                    "text": "Find quantum gravity",
                    "budget": "$50",
                    "deadline": "2h",
                }
            }
        )
        assert ctx["derived_session_goal"] == {
            "text": "Find quantum gravity",
            "budget": "$50",
            "deadline": "2h",
        }
        assert ctx["derived_session_goal_text"] == "Find quantum gravity"
        assert ctx["derived_session_goal_budget"] == "$50"
        assert ctx["derived_session_goal_deadline"] == "2h"


class TestSessionGoalModel:
    def test_model_rejects_unknown_fields(self) -> None:
        # extra="forbid" — guards prompt consumers from picking up junk fields.
        with pytest.raises(ValueError):
            SessionGoal(text="x", unknown="oops")  # type: ignore[call-arg]

    def test_model_accepts_text_only(self) -> None:
        goal = SessionGoal(text="x")
        assert goal.text == "x"
        assert goal.budget is None
        assert goal.deadline is None
