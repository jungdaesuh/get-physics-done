"""User author-profile helpers.

The profile holds the user's preferred byline + affiliations so paper drafts
do not require re-entering that information on every run. It lives outside
any single project at ``~/.gpd/profile.json`` (or ``$GPD_DATA_DIR/profile.json``)
and is read by the paper-writer skill when populating the per-paper config.

The file is advisory only: a missing or malformed profile falls back silently
to the existing per-paper prompt flow. There is no migration of existing
per-paper ``authors[]`` — those continue to work untouched.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic import ValidationError as PydanticValidationError

from gpd.core.constants import (
    ENV_DATA_DIR,
    HOME_DATA_DIR_NAME,
    PROFILE_FILENAME,
)
from gpd.core.utils import atomic_write, file_lock, safe_read_file

__all__ = [
    "AuthorProfile",
    "Profile",
    "ProfileError",
    "load_profile",
    "profile_path",
    "save_profile",
]


logger = logging.getLogger(__name__)


class ProfileError(ValueError):
    """Raised when a profile file is structurally invalid (not for missing files)."""


class AuthorProfile(BaseModel):
    """One author entry: at minimum a non-empty name.

    ``affiliations`` is a list because real papers carry dual-affiliations
    (e.g. university + national lab); supporting ``0..n`` here avoids a v2
    schema migration when users with multiple affiliations show up.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    affiliations: list[str] = Field(default_factory=list)
    email: str = ""
    orcid: str = ""

    @field_validator("name", mode="before")
    @classmethod
    def _name_required(cls, value: object) -> str:
        if value is None:
            raise ValueError("author name is required")
        if not isinstance(value, str):
            raise ValueError("author name must be a string")
        text = value.strip()
        if not text:
            raise ValueError("author name must not be empty")
        return text

    @field_validator("affiliations", mode="before")
    @classmethod
    def _normalize_affiliations(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("affiliations must be a list of strings")
        cleaned: list[str] = []
        for entry in value:
            if entry is None:
                continue
            if not isinstance(entry, str):
                raise ValueError("affiliations must be a list of strings")
            text = entry.strip()
            if text:
                cleaned.append(text)
        return cleaned

    @field_validator("email", "orcid", mode="before")
    @classmethod
    def _normalize_optional_string(cls, value: object) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("must be a string")
        return value.strip()


class Profile(BaseModel):
    """Top-level profile schema. ``authors`` may be empty when the user has
    not yet filled in their byline; callers treat that as "no preference"."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    schema_version: int = 1
    authors: list[AuthorProfile] = Field(default_factory=list)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _check_schema_version(cls, value: object) -> int:
        if value is None:
            return 1
        if type(value) is not int:
            raise ValueError("schema_version must be an integer")
        if value < 1:
            raise ValueError("schema_version must be >= 1")
        # Reject future-version files rather than silently lose unknown fields.
        if value > 1:
            raise ValueError(
                f"profile.json schema_version={value} is newer than this build supports (max=1)"
            )
        return value


def _data_root(explicit_data_dir: Path | None = None) -> Path:
    """Resolve the GPD data root with the same precedence as recent_projects_root.

    Precedence: explicit > ``GPD_DATA_DIR`` env > ``~/.gpd``.
    """
    if explicit_data_dir is not None:
        return explicit_data_dir.expanduser()
    env_dir = os.environ.get(ENV_DATA_DIR, "").strip()
    if env_dir:
        return Path(env_dir).expanduser()
    return Path.home() / HOME_DATA_DIR_NAME


def profile_path(data_root: Path | None = None) -> Path:
    """Return the ``profile.json`` path under the resolved data root."""
    return _data_root(data_root) / PROFILE_FILENAME


def load_profile(data_root: Path | None = None) -> Profile:
    """Read the profile from disk.

    Returns an empty ``Profile`` when the file is missing or malformed.
    A malformed file is logged as a warning so a partial save by another
    process (e.g. the desktop Settings UI mid-write) doesn't crash callers.
    """
    path = profile_path(data_root)
    raw = safe_read_file(path)
    if raw is None:
        return Profile()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("profile.json at %s is not valid JSON; ignoring invalid profile", path)
        return Profile()
    if not isinstance(data, dict):
        logger.warning("profile.json at %s is not a JSON object; ignoring", path)
        return Profile()
    try:
        return Profile.model_validate(data)
    except PydanticValidationError:
        logger.warning(
            "profile.json at %s failed schema validation; ignoring invalid profile", path
        )
        return Profile()


def save_profile(profile: Profile, data_root: Path | None = None) -> Path:
    """Persist the profile atomically under a file lock.

    Returns the path written. Creates the data root directory if needed.
    On POSIX, enforces mode ``0o600`` on the written file because the profile
    holds personal identifiers (name, email, ORCID, affiliations) that should
    not be group/world-readable by default. Windows file ACLs are left to the
    OS defaults; ``os.chmod`` would be a no-op there.
    """
    if not isinstance(profile, Profile):
        raise ProfileError("save_profile requires a Profile instance")
    path = profile_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        atomic_write(path, profile.model_dump_json(indent=2) + "\n")
    if os.name == "posix":
        try:
            path.chmod(0o600)
        except OSError:
            logger.warning("profile.json at %s: could not enforce 0o600 permissions", path)
    return path
