"""Refresh the active RFPro layout from inside the RFPro/EMPro process.

The ADS-side ``refresh_rfpro_view.py`` script updates the RFPro view's files.
This module gives the active RFPro GUI event loop time to ingest those files
and repopulate its in-memory design-parameter table.

Import this module in the RFPro/EMPro Python console. It is not a standalone
ADS Python script and does not open or replace an RFPro project.
"""

from __future__ import annotations

import argparse
import math
import time
from collections.abc import Sequence
from typing import Any


def _empro_module() -> Any:
    try:
        import empro
    except ImportError as error:
        raise RuntimeError(
            "The empro module is unavailable. Import this helper from the "
            "RFPro/EMPro Python console with the affected RFPro project active."
        ) from error
    return empro


def _active_layout(empro: Any) -> Any:
    project = getattr(empro, "activeProject", None)
    if project is None:
        raise RuntimeError("RFPro/EMPro has no active project.")

    layout = project.layout
    if layout is None:
        raise RuntimeError("The active RFPro/EMPro project has no layout.")
    return layout


def _parameter_count(parameters: Any) -> int:
    if parameters is None:
        return 0
    try:
        return len(parameters)
    except TypeError:
        return 1 if bool(parameters) else 0


def get_loaded_design_parameters() -> Any:
    """Return RFPro's currently loaded layout-design-parameter collection.

    ADS 2026 Update 2.1 does not expose this collection through a documented
    public Python property. The shipped ``LayoutWrapper._designParameters``
    implementation is therefore used only as the required runtime probe.
    """

    empro = _empro_module()
    layout = _active_layout(empro)
    return layout._designParameters()


def refresh_active_rfpro_layout(
    timeout_seconds: float = 5.0,
    poll_interval_seconds: float = 0.05,
) -> Any:
    """Refresh the active RFPro layout and wait for parameters to reappear.

    ``LayoutWrapper.refresh()`` returns before RFPro has necessarily processed
    the queued GUI work. This function pumps RFPro's event loop and returns the
    newly loaded parameter collection once it is non-empty.

    This operation does not reset ``.adsPcells``, replace the RFPro project, or
    prove that same-value PCell artwork was regenerated.
    """

    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be finite and greater than zero.")
    if not math.isfinite(poll_interval_seconds) or poll_interval_seconds <= 0:
        raise ValueError(
            "poll_interval_seconds must be finite and greater than zero."
        )

    empro = _empro_module()
    layout = _active_layout(empro)

    refresh = getattr(layout, "refresh", None)
    if not callable(refresh):
        raise RuntimeError(
            "The active layout does not expose LayoutWrapper.refresh()."
        )

    gui = getattr(empro, "gui", None)
    process_events = getattr(gui, "processEvents", None)
    if not callable(process_events):
        raise RuntimeError("RFPro/EMPro does not expose gui.processEvents().")

    refresh()
    deadline = time.monotonic() + timeout_seconds

    while True:
        process_events()
        layout = _active_layout(empro)
        parameters = layout._designParameters()
        if _parameter_count(parameters) > 0:
            return parameters

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval_seconds, remaining))

    raise RuntimeError(
        "RFPro refreshed the active layout, but its design parameters remained "
        f"empty for {timeout_seconds:g} seconds. Open Design Parameters once "
        "to determine whether this RFPro build requires a UI-triggered lazy load."
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the helper directly from an RFPro/EMPro Python environment."""

    parser = argparse.ArgumentParser(
        description=(
            "Refresh the active RFPro layout and wait for its in-memory design "
            "parameters to be repopulated."
        )
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--poll-interval", type=float, default=0.05)
    arguments = parser.parse_args(argv)

    parameters = refresh_active_rfpro_layout(
        timeout_seconds=arguments.timeout,
        poll_interval_seconds=arguments.poll_interval,
    )
    print(f"RFPro loaded design parameters: {parameters!r}")
    print(
        "Parameter metadata is loaded. This does not prove that cached PCell "
        "artwork for existing values was regenerated."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
