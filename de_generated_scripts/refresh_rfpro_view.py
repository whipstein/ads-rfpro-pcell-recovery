"""Refresh an existing RFPro view from its ADS source layout.

This self-contained script prepares the ADS native-library loader before
importing emtools and applies a scoped Qt platform-plugin redirect only when it
must create its own QApplication. An application owned by ADS is reused without
restarting it. The RFPro design is identified as library:cell:view. Close RFPro
before running the file.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
from pathlib import Path


_ADS_NATIVE_REEXEC_MARKER = "_RFPRO_EMVIEWS_LOADER_REEXEC"


def _is_ads_root(path: Path) -> bool:
    return (
        (path / "tools" / "python" / "packages" / "keysight" / "ads").is_dir()
        or (path / "doc" / "python").is_dir()
    )


def _resolve_ads_root() -> Path:
    """Resolve ADS from HPEESOF_DIR or the ADS-bundled interpreter."""

    candidates: list[Path] = []
    configured_root = os.environ.get("HPEESOF_DIR")
    if configured_root:
        candidates.append(Path(configured_root))

    executable = Path(sys.executable).resolve()
    for ancestor in executable.parents:
        if ancestor.name.lower() == "tools":
            candidates.append(ancestor.parent)
            break

    checked: list[str] = []
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if str(resolved) not in checked:
            checked.append(str(resolved))
        if _is_ads_root(resolved):
            # The ADS emtools package itself requires HPEESOF_DIR. Setting it
            # here affects only this process (and the one-time exec below).
            os.environ["HPEESOF_DIR"] = str(resolved)
            return resolved

    details = ", ".join(checked) if checked else "no candidates"
    raise RuntimeError(
        "Could not resolve the ADS installation needed by emtools. Run this "
        "script with the ADS-bundled Python interpreter. "
        f"Checked: {details}."
    )


def _locate_emviews_library(ads_root: Path) -> Path:
    """Locate the installed native library required by keysight.ads.emtools."""

    library_name = "libemViewsPlugin.so"
    preferred = (
        ads_root / "lib" / "linux_x86_64" / library_name,
        ads_root / "lib" / library_name,
        ads_root / "bin" / library_name,
        ads_root / "tools" / "python" / "lib" / library_name,
    )
    for candidate in preferred:
        if candidate.is_file():
            return candidate.resolve()

    matches: list[Path] = []
    for search_root in (ads_root / "lib", ads_root / "bin", ads_root / "tools"):
        if not search_root.is_dir():
            continue
        try:
            matches.extend(
                path
                for path in search_root.rglob(library_name)
                if path.is_file()
            )
        except OSError:
            continue

    if matches:
        return min(
            (path.resolve() for path in matches),
            key=lambda path: (len(path.parts), str(path)),
        )

    raise RuntimeError(
        f"{library_name} was not found under the ADS installation {ads_root}. "
        "Repair or complete the ADS EM/RFPro installation."
    )


def _loader_directories(ads_root: Path, library_file: Path) -> list[Path]:
    candidates = (
        library_file.parent,
        ads_root / "bin",
        ads_root / "lib" / "linux_x86_64",
        ads_root / "lib",
        ads_root / "tools" / "python" / "lib",
    )
    directories: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_dir() and resolved not in directories:
            directories.append(resolved)
    return directories


def _normalized_loader_entries(value: str) -> set[str]:
    entries: set[str] = set()
    for raw_entry in value.split(os.pathsep):
        if not raw_entry:
            continue
        try:
            entries.add(str(Path(raw_entry).expanduser().resolve()))
        except OSError:
            entries.add(raw_entry)
    return entries


def _ads_application_is_running() -> bool:
    """Check for a live host without creating a Qt application."""

    try:
        from PySide6.QtCore import QCoreApplication
    except Exception:
        return False
    return QCoreApplication.instance() is not None


def _prepare_ads_native_runtime() -> tuple[Path | None, str, bool]:
    """Prepare Linux loader state before importing the emtools extension."""

    if not sys.platform.startswith("linux"):
        return None, "not required on this platform", False

    ads_root = _resolve_ads_root()
    library_file = _locate_emviews_library(ads_root)
    directories = _loader_directories(ads_root, library_file)
    previous_value = os.environ.get("LD_LIBRARY_PATH", "")
    current_entries = _normalized_loader_entries(previous_value)
    missing_directories = [
        directory
        for directory in directories
        if str(directory) not in current_entries
    ]
    was_reexecuted = os.environ.pop(_ADS_NATIVE_REEXEC_MARKER, None) == "1"

    if not missing_directories:
        mode = (
            "automatic process-local loader-path restart"
            if was_reexecuted
            else "available in the existing loader path"
        )
        return library_file, mode, False

    if _ads_application_is_running():
        # Replacing the current process would terminate a live ADS session.
        # The exact library is instead preloaded after keysight.ads.de is ready.
        return library_file, "preloaded into the live ADS process", True

    if was_reexecuted:
        raise RuntimeError(
            "The one-time ADS native-library restart did not preserve its "
            "loader path. Launch with the ADS-bundled Python interpreter."
        )

    inherited_entries = [entry for entry in previous_value.split(os.pathsep) if entry]
    new_entries = [str(directory) for directory in directories]
    for entry in inherited_entries:
        if entry not in new_entries:
            new_entries.append(entry)

    environment = os.environ.copy()
    environment["LD_LIBRARY_PATH"] = os.pathsep.join(new_entries)
    environment[_ADS_NATIVE_REEXEC_MARKER] = "1"
    os.execve(sys.executable, [sys.executable, *sys.argv], environment)
    raise AssertionError("os.execve returned unexpectedly")


def _unresolved_native_dependencies(library_file: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["ldd", str(library_file)],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    return [
        line.strip()
        for line in (result.stdout + result.stderr).splitlines()
        if "not found" in line
    ]


def _preload_emviews_library(library_file: Path) -> object:
    try:
        return ctypes.CDLL(
            str(library_file),
            mode=getattr(os, "RTLD_GLOBAL", ctypes.DEFAULT_MODE),
        )
    except OSError as error:
        unresolved = _unresolved_native_dependencies(library_file)
        details = "\n  ".join(unresolved) if unresolved else str(error)
        raise RuntimeError(
            f"ADS found {library_file}, but it could not be loaded into the "
            f"live process:\n  {details}"
        ) from error


(
    ADS_EMVIEWS_LIBRARY_FILE,
    ADS_NATIVE_RUNTIME_MODE,
    ADS_NATIVE_PRELOAD_REQUIRED,
) = _prepare_ads_native_runtime()


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

ADS_EMVIEWS_LIBRARY_HANDLE = None
if ADS_NATIVE_PRELOAD_REQUIRED:
    if ADS_EMVIEWS_LIBRARY_FILE is None:
        raise RuntimeError(
            "Internal error: ADS native library path is unavailable."
        )
    # Keep the handle alive for the complete RFPro operation.
    ADS_EMVIEWS_LIBRARY_HANDLE = _preload_emviews_library(
        ADS_EMVIEWS_LIBRARY_FILE
    )

try:
    from keysight.ads import emtools
except ImportError as error:
    if sys.platform.startswith("linux") and "libemViewsPlugin.so" in str(error):
        unresolved = (
            _unresolved_native_dependencies(ADS_EMVIEWS_LIBRARY_FILE)
            if ADS_EMVIEWS_LIBRARY_FILE is not None
            else []
        )
        details = "\n  ".join(unresolved) if unresolved else str(error)
        raise RuntimeError(
            "keysight.ads.emtools still could not load its native ADS runtime "
            f"after automatic discovery:\n  {details}"
        ) from error
    raise


def _design_argument(value: str) -> str:
    parts = [part.strip() for part in value.split(":")]
    if len(parts) != 3 or any(not part for part in parts):
        raise argparse.ArgumentTypeError(
            '--design must be exactly "library:cell:view"'
        )
    return ":".join(parts)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh an existing ADS RFPro view.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--design",
        required=True,
        type=_design_argument,
        metavar="LIB:CELL:VIEW",
        help="existing ADS RFPro view identifier",
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
    if ADS_EMVIEWS_LIBRARY_FILE is not None:
        print(f"ADS EM Views library: {ADS_EMVIEWS_LIBRARY_FILE}")
    print(f"ADS native runtime: {ADS_NATIVE_RUNTIME_MODE}")


def main() -> None:
    arguments = _parse_arguments()
    library, cell, view = arguments.design.split(":")
    rfpro_lcv = (library, cell, view)
    _print_qt_runtime()
    workspace = _open_workspace_if_requested(arguments.workspace)
    if not de.library_is_open(library):
        raise RuntimeError(
            f"Library {library!r} from --design {arguments.design!r} is not open. "
            "Run inside ADS with the correct workspace open, or pass --workspace "
            "with the workspace that defines this library."
        )

    print(f"Refreshing RFPro view {arguments.design} ...")
    emtools.update_empro_view(rfpro_lcv)
    print("Refresh completed. Open RFPro and inspect Design Parameters.")

    # Keep a standalone-opened workspace alive until the refresh has finished.
    _ = workspace


if __name__ == "__main__":
    main()
