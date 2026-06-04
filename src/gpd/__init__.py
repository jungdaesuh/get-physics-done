"""GPD -- Get Physics Done: unified physics research orchestration."""

from gpd._python_compat import require_supported_python

require_supported_python()

from gpd.version import __version__  # noqa: E402

__all__ = ["__version__"]
