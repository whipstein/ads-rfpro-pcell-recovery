"""Refresh the active RFPro layout from inside the RFPro/EMPro process.

The ADS-side ``refresh_rfpro_view.py`` script updates the RFPro view's files.
This module reloads the active RFPro project's parameter metadata and can pass
those formulas to the active layout's native geometry updater.

Import this module in the RFPro/EMPro Python console. It is not a standalone
ADS Python script and does not open or replace an RFPro project.
"""

from __future__ import annotations

import argparse
import math
import time
from collections.abc import Mapping, Sequence
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


def _active_project(empro: Any) -> Any:
    project = getattr(empro, "activeProject", None)
    if project is None:
        raise RuntimeError("RFPro/EMPro has no active project.")
    return project


def _active_layout(empro: Any) -> Any:
    project = _active_project(empro)

    layout = project.layout
    if layout is None:
        raise RuntimeError("The active RFPro/EMPro project has no layout.")
    return layout


def get_loaded_design_parameters() -> Any:
    """Return RFPro's currently loaded layout-design-parameter collection.

    ADS 2026 Update 2.1 does not expose this collection through a documented
    public Python property. The shipped ``LayoutWrapper._designParameters``
    implementation is therefore used only as the required runtime probe.
    """

    empro = _empro_module()
    layout = _active_layout(empro)
    return layout._designParameters()


def get_active_project_parameter_formulas(
    parameter_names: Sequence[str] | None = None,
) -> dict[str, str]:
    """Return formulas from RFPro's active-project parameter list.

    ``ParameterList.names()`` and ``ParameterList.formula(name)`` are the
    documented EMPro APIs used here. When *parameter_names* is omitted, every
    parameter currently loaded in the active project is returned. Supplying
    the RFPro PCell parameter names is safer when the project also contains
    unrelated global parameters.
    """

    empro = _empro_module()
    return _project_parameter_formulas(empro, parameter_names)


def _project_parameter_formulas(
    empro: Any,
    parameter_names: Sequence[str] | None = None,
) -> dict[str, str]:
    project = _active_project(empro)
    parameters = getattr(project, "parameters", None)
    names_method = getattr(parameters, "names", None)
    formula_method = getattr(parameters, "formula", None)
    if not callable(names_method) or not callable(formula_method):
        raise RuntimeError(
            "The active RFPro project does not expose the documented "
            "ParameterList.names() and ParameterList.formula() APIs."
        )

    available_names = [str(name) for name in names_method()]
    if parameter_names is None:
        selected_names = available_names
    else:
        requested_names = (
            (parameter_names,)
            if isinstance(parameter_names, str)
            else parameter_names
        )
        selected_names = []
        for name in requested_names:
            if not isinstance(name, str) or not name:
                raise ValueError(
                    "parameter_names must contain non-empty strings."
                )
            if name not in selected_names:
                selected_names.append(name)

        missing_names = [
            name for name in selected_names if name not in available_names
        ]
        if missing_names:
            raise RuntimeError(
                "RFPro's active-project parameter list does not contain: "
                + ", ".join(missing_names)
                + ". Available parameters: "
                + (", ".join(available_names) if available_names else "(none)")
            )

    if not selected_names:
        raise RuntimeError(
            "RFPro's active-project parameter list is empty. Open the affected "
            "RFPro view and its Design Parameters node before retrying."
        )

    return {name: str(formula_method(name)) for name in selected_names}


def _normalize_parameter_updates(
    updates: Mapping[str, str],
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for name, formula in updates.items():
        if not isinstance(name, str) or not name:
            raise ValueError("Parameter update names must be non-empty strings.")
        if not isinstance(formula, str) or not formula:
            raise ValueError(
                f"The update formula for parameter {name!r} must be a "
                "non-empty string."
            )
        normalized[name] = formula
    if not normalized:
        raise ValueError("At least one parameter update is required.")
    return normalized


def force_active_rfpro_geometry_update(
    parameter_names: Sequence[str] | None = None,
    *,
    updates: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Apply design parameters through the active layout's native updater.

    The update is restricted to the layout object in the active RFPro project.
    It does not call ``LayoutWrapper.refresh()``, replace the project, or clear
    the workspace-wide ``.adsPcells`` directory.

    By default, formulas are copied from the active project's documented
    ``ParameterList``. Pass *parameter_names* to select only the PCell
    parameters. Alternatively, pass an explicit ``updates`` mapping. The two
    input forms are mutually exclusive.

    ADS 2026 Update 2.1 exposes the required layout method only as the private
    ``_updateDesignParameters(Mapping[str, str])`` binding. Its returned status
    string is included verbatim in the report rather than interpreted.
    """

    if updates is not None and parameter_names is not None:
        raise ValueError(
            "Pass parameter_names or updates, not both."
        )

    empro = _empro_module()
    project = _active_project(empro)
    layout = _active_layout(empro)

    load_design_parameters = getattr(
        project,
        "_loadOaParametersFromDesignSpec",
        None,
    )
    if not callable(load_design_parameters):
        raise RuntimeError(
            "The active RFPro project does not expose the design-spec "
            "parameter loader used by ADS 2026 Update 2.1."
        )
    load_design_parameters()

    if updates is None:
        normalized_updates = _normalize_parameter_updates(
            _project_parameter_formulas(empro, parameter_names)
        )
    else:
        normalized_updates = _normalize_parameter_updates(updates)

    native_update = getattr(layout, "_updateDesignParameters", None)
    if not callable(native_update):
        raise RuntimeError(
            "The active RFPro layout does not expose "
            "_updateDesignParameters(Mapping[str, str])."
        )

    design_parameters_before = layout._designParameters()
    native_status = native_update(normalized_updates)

    gui = getattr(empro, "gui", None)
    process_events = getattr(gui, "processEvents", None)
    if callable(process_events):
        process_events()

    design_parameters_after = _active_layout(empro)._designParameters()
    return {
        "updates": dict(normalized_updates),
        "native_status": str(native_status),
        "design_parameters_before": design_parameters_before,
        "design_parameters_after": design_parameters_after,
    }


def refresh_active_rfpro_layout(
    timeout_seconds: float = 5.0,
    poll_interval_seconds: float = 0.05,
) -> Any:
    """Refresh the active RFPro layout and wait for parameters to reappear.

    ``LayoutWrapper.refresh()`` can leave ``layout._designParameters()`` empty
    even when the Design Parameters UI is populated. This function therefore
    invokes the design-spec parameter loader used by Keysight's shipped
    ``loadDesign()`` workflow, pumps RFPro's event loop, and verifies the
    documented active-project ``ParameterList`` instead of that private map.

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

    project = _active_project(empro)
    load_design_parameters = getattr(
        project,
        "_loadOaParametersFromDesignSpec",
        None,
    )
    if not callable(load_design_parameters):
        raise RuntimeError(
            "The active RFPro project does not expose the design-spec "
            "parameter loader used by ADS 2026 Update 2.1."
        )

    refresh()
    load_design_parameters()
    deadline = time.monotonic() + timeout_seconds

    while True:
        process_events()
        try:
            return _project_parameter_formulas(empro)
        except RuntimeError as error:
            if "parameter list is empty" not in str(error):
                raise

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval_seconds, remaining))

    raise RuntimeError(
        "RFPro refreshed the active layout and reloaded its OA design-spec "
        "parameters, but the active-project ParameterList remained empty for "
        f"{timeout_seconds:g} seconds."
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
    parser.add_argument(
        "--update-geometry",
        action="store_true",
        help=(
            "apply active-project parameter formulas through the active "
            "layout's native geometry updater instead of calling refresh()"
        ),
    )
    parser.add_argument(
        "--parameter",
        action="append",
        default=None,
        metavar="NAME",
        help=(
            "PCell parameter to pass to the native updater; repeat as needed. "
            "Without this option every active-project parameter is passed."
        ),
    )
    arguments = parser.parse_args(argv)

    if arguments.parameter and not arguments.update_geometry:
        parser.error("--parameter requires --update-geometry")

    if arguments.update_geometry:
        report = force_active_rfpro_geometry_update(arguments.parameter)
        print("RFPro active-layout geometry update submitted:")
        print(f"  updates={report['updates']!r}")
        print(f"  native_status={report['native_status']!r}")
        print(
            "  design_parameters_before="
            f"{report['design_parameters_before']!r}"
        )
        print(
            "  design_parameters_after="
            f"{report['design_parameters_after']!r}"
        )
        print(
            "The active layout was updated without clearing .adsPcells or "
            "replacing the RFPro project. Verify the displayed geometry "
            "before simulation."
        )
        return 0

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
