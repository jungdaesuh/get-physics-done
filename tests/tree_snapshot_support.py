"""Small filesystem tree snapshots for non-mutation acceptance tests."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TreeEntry:
    kind: str
    fingerprint: str


TreeSnapshot = dict[str, TreeEntry]


def snapshot_tree(root: Path) -> TreeSnapshot:
    """Return relative path -> kind/hash for the current tree under root."""

    entries: TreeSnapshot = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            entries[relative] = TreeEntry("symlink", os.readlink(path))
        elif path.is_dir():
            entries[relative] = TreeEntry("dir", "")
        elif path.is_file():
            entries[relative] = TreeEntry("file", hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            entries[relative] = TreeEntry("other", "")
    return entries


def assert_tree_unchanged(root: Path, before: TreeSnapshot, *, context: str) -> None:
    after = snapshot_tree(root)
    if after == before:
        return

    before_paths = set(before)
    after_paths = set(after)
    added = sorted(after_paths - before_paths)
    removed = sorted(before_paths - after_paths)
    changed = sorted(path for path in before_paths & after_paths if before[path] != after[path])
    raise AssertionError(
        f"{context} mutated {root}: added={added!r}, removed={removed!r}, changed={changed!r}"
    )
