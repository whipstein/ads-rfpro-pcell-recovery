"""Compatibility entry point for the importable RFPro runtime helper."""

from __future__ import annotations

import sys
from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from rfpro_pcell_recovery.runtime import (  # noqa: E402
    get_loaded_design_parameters,
    main,
    refresh_active_rfpro_layout,
)

__all__ = [
    "get_loaded_design_parameters",
    "refresh_active_rfpro_layout",
]


if __name__ == "__main__":
    raise SystemExit(main())
