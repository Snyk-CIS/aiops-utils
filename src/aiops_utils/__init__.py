"""Top-level package for Snyk’s AI Operation Utilities.

This namespace exposes:
• aiops_utils.retrievers
and provides a semantic version string in __version__.
"""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from typing import Final

# ---------------------------------------------------------------------------#
# Version
# ---------------------------------------------------------------------------#
try:
    __version__: str = _pkg_version("aiops-utils")
except PackageNotFoundError:  # when metadata not available (e.g., running from source)
    __version__ = "0.0.0.dev0"

# ---------------------------------------------------------------------------#
# Sub-packages
# ---------------------------------------------------------------------------#
for _sub in ("retrievers",):
    try:
        import_module(f".{_sub}", __name__)
    except ModuleNotFoundError:  # pragma: no cover
        pass

__all__: Final = [
    "retrievers",
    "__version__",
]
