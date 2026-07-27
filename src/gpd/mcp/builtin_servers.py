"""Tombstone keys for GPD's removed built-in MCP servers.

GPD no longer ships or installs built-in MCP servers — every capability they
exposed is reachable through the ``gpd`` CLI (``gpd verify``, ``gpd refs``,
``gpd convention``, ``gpd pattern``, ``gpd state``) or by reading the installed
prompt/reference files directly.

These key names survive for exactly one reason: install, upgrade, and uninstall
must be able to scrub stale ``gpd-*`` entries that earlier GPD releases wrote
into runtime MCP configs. Nothing may add a name here, and nothing may launch
a process from one.

Opt-in managed integrations are *not* listed here; their live server keys are
owned by :mod:`gpd.mcp.managed_integrations`.
"""

from __future__ import annotations

# Legacy runtime-config entry names written by GPD releases that shipped
# built-in MCP servers. Retained only so install/uninstall can remove them.
GPD_MCP_SERVER_KEYS = frozenset(
    {
        "gpd-conventions",
        "gpd-errors",
        "gpd-patterns",
        "gpd-protocols",
        "gpd-skills",
        "gpd-state",
        "gpd-verification",
        "gpd-arxiv",
    }
)

__all__ = ["GPD_MCP_SERVER_KEYS"]
