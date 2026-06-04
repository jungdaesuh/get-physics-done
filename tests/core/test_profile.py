from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from gpd.core.profile import (
    AuthorProfile,
    Profile,
    ProfileError,
    load_profile,
    profile_path,
    save_profile,
)


class TestProfilePathResolution:
    def test_prefers_explicit_data_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        explicit = tmp_path / "explicit-data"
        monkeypatch.setenv("GPD_DATA_DIR", str(tmp_path / "ignored"))
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        assert profile_path(explicit) == explicit / "profile.json"

    def test_uses_data_dir_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        data_dir = tmp_path / "data"
        monkeypatch.setenv("GPD_DATA_DIR", str(data_dir))
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        assert profile_path() == data_dir / "profile.json"

    def test_defaults_to_home_gpd_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.delenv("GPD_DATA_DIR", raising=False)
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        assert profile_path() == fake_home / ".gpd" / "profile.json"


class TestLoadProfileMissingOrEmpty:
    def test_returns_empty_when_file_missing(self, tmp_path: Path) -> None:
        loaded = load_profile(tmp_path)

        assert loaded == Profile()
        assert loaded.authors == []
        assert loaded.schema_version == 1

    def test_returns_empty_on_invalid_json(self, tmp_path: Path) -> None:
        (tmp_path / "profile.json").write_text("{ not valid json", encoding="utf-8")

        loaded = load_profile(tmp_path)

        assert loaded.authors == []

    def test_returns_empty_when_root_is_not_object(self, tmp_path: Path) -> None:
        (tmp_path / "profile.json").write_text('["array-root-not-allowed"]', encoding="utf-8")

        loaded = load_profile(tmp_path)

        assert loaded.authors == []

    def test_returns_empty_on_schema_validation_failure(self, tmp_path: Path) -> None:
        # author missing required name
        (tmp_path / "profile.json").write_text(
            json.dumps({"schema_version": 1, "authors": [{"affiliations": []}]}),
            encoding="utf-8",
        )

        loaded = load_profile(tmp_path)

        assert loaded.authors == []

    def test_returns_empty_on_future_schema_version(self, tmp_path: Path) -> None:
        (tmp_path / "profile.json").write_text(
            json.dumps({"schema_version": 99, "authors": []}),
            encoding="utf-8",
        )

        loaded = load_profile(tmp_path)

        # Future-version files don't crash callers; they fall back to empty.
        assert loaded.authors == []


class TestSaveProfileRoundTrip:
    def test_round_trip_minimal_author(self, tmp_path: Path) -> None:
        profile = Profile(
            authors=[AuthorProfile(name="Alex Maloney-Mendelsohn")],
        )

        save_profile(profile, tmp_path)
        loaded = load_profile(tmp_path)

        assert loaded.authors == [AuthorProfile(name="Alex Maloney-Mendelsohn")]
        assert loaded.schema_version == 1

    def test_round_trip_full_author(self, tmp_path: Path) -> None:
        profile = Profile(
            authors=[
                AuthorProfile(
                    name="Alex Maloney-Mendelsohn",
                    affiliations=["Physical Superintelligence PBC", "MIT"],
                    email="alex@psi.inc",
                    orcid="0000-0002-1825-0097",
                ),
            ],
        )

        save_profile(profile, tmp_path)
        loaded = load_profile(tmp_path)

        assert loaded == profile

    def test_round_trip_multi_author(self, tmp_path: Path) -> None:
        profile = Profile(
            authors=[
                AuthorProfile(name="Alex", affiliations=["PSI"]),
                AuthorProfile(name="Cameron", affiliations=["PSI"]),
            ],
        )

        save_profile(profile, tmp_path)
        loaded = load_profile(tmp_path)

        assert [a.name for a in loaded.authors] == ["Alex", "Cameron"]

    def test_save_creates_parent_dir(self, tmp_path: Path) -> None:
        nested = tmp_path / "does" / "not" / "exist"
        profile = Profile(authors=[AuthorProfile(name="Alex")])

        path = save_profile(profile, nested)

        assert path == nested / "profile.json"
        assert path.exists()

    def test_save_is_atomic_overwrite(self, tmp_path: Path) -> None:
        first = Profile(authors=[AuthorProfile(name="Alex")])
        second = Profile(authors=[AuthorProfile(name="Cameron")])

        save_profile(first, tmp_path)
        save_profile(second, tmp_path)

        loaded = load_profile(tmp_path)
        assert loaded.authors == [AuthorProfile(name="Cameron")]


class TestSaveProfileValidation:
    def test_rejects_non_profile_input(self, tmp_path: Path) -> None:
        with pytest.raises(ProfileError):
            save_profile({"schema_version": 1, "authors": []}, tmp_path)  # type: ignore[arg-type]


class TestAuthorProfileValidation:
    def test_name_is_required(self) -> None:
        with pytest.raises(ValidationError):
            AuthorProfile(name="")

    def test_name_stripped(self) -> None:
        author = AuthorProfile(name="  Alex  ")
        assert author.name == "Alex"

    def test_affiliations_strip_empties(self) -> None:
        author = AuthorProfile(name="Alex", affiliations=["PSI", "", "  ", "MIT"])
        assert author.affiliations == ["PSI", "MIT"]

    def test_optional_strings_default_empty(self) -> None:
        author = AuthorProfile(name="Alex")
        assert author.email == ""
        assert author.orcid == ""
