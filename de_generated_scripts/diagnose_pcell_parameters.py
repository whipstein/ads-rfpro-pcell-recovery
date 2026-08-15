"""Inspect PCell parameters in an ADS source layout.

This self-contained script applies a scoped Qt platform-plugin redirect only
when it must create its own QApplication. A QApplication owned by ADS is reused
without changing the environment. The design is identified as library:cell:view.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _expected_qt_platform_plugin() -> str:
    if sys.platform.startswith("linux"):
        return "libqxcb.so"
    if sys.platform == "win32":
        return "qwindows.dll"
    if sys.platform == "darwin":
        return "libqcocoa.dylib"
    raise RuntimeError(f"Unsupported Qt platform: {sys.platform}")


def _locate_qt_platform_plugin(pyside_file: Path) -> Path:
    """Ask Qt for its plugin roots, then search ADS roots as a fallback."""

    from PySide6.QtCore import QCoreApplication, QLibraryInfo

    plugin_name = _expected_qt_platform_plugin()
    directories: list[Path] = []

    def add_directory(path: Path) -> None:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            return
        if resolved not in directories:
            directories.append(resolved)

    def add_plugin_root(path: Path) -> None:
        add_directory(path)
        if path.name != "platforms":
            add_directory(path / "platforms")

    qt_plugins_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)
    if qt_plugins_path:
        add_plugin_root(Path(qt_plugins_path))

    for library_path in QCoreApplication.libraryPaths():
        if library_path:
            add_plugin_root(Path(library_path))

    pyside_root = pyside_file.parent
    add_directory(pyside_root / "plugins" / "platforms")
    add_directory(pyside_root / "Qt" / "plugins" / "platforms")

    for environment_name in ("QT_QPA_PLATFORM_PLUGIN_PATH", "QT_PLUGIN_PATH"):
        value = os.environ.get(environment_name, "")
        for entry in value.split(os.pathsep):
            if entry:
                add_plugin_root(Path(entry))

    for directory in directories:
        plugin_file = directory / plugin_name
        if plugin_file.is_file():
            return plugin_file

    fallback_roots = [pyside_root, Path(sys.prefix)]
    for ancestor in Path(sys.executable).resolve().parents:
        if ancestor.name.lower() == "tools":
            fallback_roots.append(ancestor.parent)
            break
    hpeesof_dir = os.environ.get("HPEESOF_DIR")
    if hpeesof_dir:
        fallback_roots.append(Path(hpeesof_dir))

    searched_roots: list[Path] = []
    for root in fallback_roots:
        try:
            resolved_root = root.expanduser().resolve()
        except OSError:
            continue
        if not resolved_root.is_dir() or resolved_root in searched_roots:
            continue
        searched_roots.append(resolved_root)
        try:
            for match in resolved_root.rglob(plugin_name):
                if match.is_file():
                    return match
        except OSError:
            continue

    checked = [str(path / plugin_name) for path in directories]
    checked.extend(f"recursive: {root}" for root in searched_roots)
    details = "\n  ".join(checked) if checked else "(no valid search roots)"
    raise RuntimeError(
        f"Qt platform plugin {plugin_name!r} was not found automatically.\n"
        f"PySide6: {pyside_file}\nSearched:\n  {details}\n"
        "Run scripts/diagnose_qt.py using this exact interpreter."
    )


def _validate_linux_plugin(plugin_file: Path) -> None:
    if not sys.platform.startswith("linux"):
        return

    dependency_check = subprocess.run(
        ["ldd", str(plugin_file)],
        check=False,
        capture_output=True,
        text=True,
    )
    unresolved = [
        line.strip()
        for line in dependency_check.stdout.splitlines()
        if "not found" in line
    ]
    if unresolved:
        details = "\n  ".join(unresolved)
        raise RuntimeError(
            f"Qt found {plugin_file}, but required libraries are missing:\n"
            f"  {details}"
        )


def _create_or_reuse_qapplication() -> tuple[Path, Path | None, object, bool, bool]:
    """Create Qt with a temporary path redirect, or reuse ADS-owned Qt."""

    try:
        import PySide6
    except Exception as error:
        raise RuntimeError(
            "PySide6 could not be imported. Run this file with the "
            f"ADS-bundled Python interpreter, not {sys.executable!r}."
        ) from error

    from PySide6.QtWidgets import QApplication

    pyside_file = Path(PySide6.__file__).resolve()
    application = QApplication.instance()
    if application is not None:
        return pyside_file, None, application, False, True

    plugin_file = _locate_qt_platform_plugin(pyside_file)
    _validate_linux_plugin(plugin_file)

    if sys.platform.startswith("linux"):
        selected_platform = os.environ.get("QT_QPA_PLATFORM", "").lower()
        has_display = bool(
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        )
        if not has_display and selected_platform not in {"offscreen", "minimal"}:
            raise RuntimeError(
                "No DISPLAY or WAYLAND_DISPLAY is available for graphical ADS. "
                "Launch from a graphical session. This script does not force "
                "QT_QPA_PLATFORM=offscreen."
            )

    variable = "QT_QPA_PLATFORM_PLUGIN_PATH"
    was_set = variable in os.environ
    previous = os.environ.get(variable)
    os.environ[variable] = str(plugin_file.parent)
    try:
        application = QApplication([])
    finally:
        if was_set:
            os.environ[variable] = previous if previous is not None else ""
        else:
            os.environ.pop(variable, None)

    restored = (
        os.environ.get(variable) == previous
        if was_set
        else variable not in os.environ
    )
    return pyside_file, plugin_file, application, True, restored


(
    QT_PYSIDE_FILE,
    QT_PLATFORM_PLUGIN_FILE,
    QT_APPLICATION,
    QT_APPLICATION_WAS_CREATED,
    QT_ENVIRONMENT_WAS_RESTORED,
) = _create_or_reuse_qapplication()

import keysight.ads.de as de
from keysight.ads.de import db_uu as db


def _design_argument(value: str) -> str:
    parts = [part.strip() for part in value.split(":")]
    if len(parts) != 3 or any(not part for part in parts):
        raise argparse.ArgumentTypeError(
            '--design must be exactly "library:cell:view"'
        )
    return ":".join(parts)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect ADS PCell parameters in a source layout.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--design",
        required=True,
        type=_design_argument,
        metavar="LIB:CELL:VIEW",
        help="ADS source layout identifier",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="ADS workspace path; required for standalone execution",
    )
    return parser.parse_args()


def _open_workspace_if_requested(workspace_path: Path | None) -> object | None:
    if workspace_path is None:
        return None

    resolved = workspace_path.expanduser().resolve()
    if not (resolved / "de_sim.cfg").is_file() or not (resolved / "data").is_dir():
        raise ValueError(
            f"Not an ADS workspace containing de_sim.cfg and data: {resolved}"
        )
    print(f"Opening ADS workspace: {resolved}")
    return de.open_workspace(resolved)


def _parameter_pairs(parameters: object) -> list[tuple[str, object]]:
    return [(parameter.name, parameter.value) for parameter in parameters]


def _print_qt_runtime() -> None:
    ownership = "created by this script" if QT_APPLICATION_WAS_CREATED else "reused from ADS"
    plugin_description = (
        str(QT_PLATFORM_PLUGIN_FILE)
        if QT_PLATFORM_PLUGIN_FILE is not None
        else "already loaded by ADS; search path unchanged"
    )
    print(f"Python executable: {sys.executable}")
    print(f"PySide6 package: {QT_PYSIDE_FILE}")
    print(f"Qt platform plugin: {plugin_description}")
    print(f"Qt platform name: {QT_APPLICATION.platformName()}")
    print(f"QApplication: {ownership}")
    print(f"Qt environment restored: {QT_ENVIRONMENT_WAS_RESTORED}")


def main() -> None:
    arguments = _parse_arguments()
    library, _cell, _view = arguments.design.split(":")
    _print_qt_runtime()
    workspace = _open_workspace_if_requested(arguments.workspace)
    if not de.library_is_open(library):
        raise RuntimeError(
            f"Library {library!r} from --design {arguments.design!r} is not open. "
            "Run inside ADS with the correct workspace open, or pass --workspace "
            "with the workspace that defines this library."
        )

    design = db.open_design(arguments.design, "ReadOnly")
    top_level_parameters = _parameter_pairs(design.pcell_parameters)

    print(f"Layout: {arguments.design}")
    print(f"PCell supermaster: {design.is_supermaster}")
    print(f"Top-level PCell parameters ({len(top_level_parameters)}):")
    for name, value in top_level_parameters:
        print(f"  {name} = {value}")

    pcell_instance_count = 0
    print("Direct PCell instances:")
    for instance in design.instances:
        if not instance.is_pcell:
            continue
        pcell_instance_count += 1
        parameters = _parameter_pairs(instance.pcell_parameters)
        master = f"{instance.model_library_name}:{instance.model_cell_name}"
        print(
            f"  {instance.name}: master={master}, "
            f"type={instance.pcell_type}, parameters={len(parameters)}"
        )
        for name, value in parameters:
            print(f"    {name} = {value}")

    if pcell_instance_count == 0:
        print("  (none in the immediate layout level)")

    if design.is_supermaster and top_level_parameters:
        print("RESULT: The source layout exposes top-level PCell parameters.")
        print("NEXT: Reset .adsPcells, then update the RFPro view.")
    elif design.is_supermaster:
        print("RESULT: The PCell exists, but its top-level parameter list is empty.")
        print("NEXT: Reapply EM > Component > Parameters..., save, and rerun.")
    else:
        print("RESULT: The layout is not a PCell supermaster.")
        print("NEXT: Apply EM > Component > Parameters..., save, and rerun.")

    # Keep a standalone-opened workspace alive until all database access ends.
    _ = workspace


if __name__ == "__main__":
    main()
