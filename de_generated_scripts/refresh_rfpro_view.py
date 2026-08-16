"""Refresh an existing RFPro view from its ADS source layout.

This self-contained script prepares the ADS native-library loader before
importing emtools and applies a scoped Qt platform-plugin redirect only when it
must create its own QApplication. An application owned by ADS is reused without
restarting it. Designs may be fully qualified or may reuse the command-line
library and cell defaults. Schema rebuilds must execute in the live ADS
application. Save and close the source layout and target RFPro view first.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
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
from keysight.ads.de import db_uu as db

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


def _name_argument(value: str) -> str:
    name = value.strip()
    if not name or ":" in name:
        raise argparse.ArgumentTypeError("must be one non-empty name")
    return name


def _design_argument(value: str) -> str:
    parts = [part.strip() for part in value.split(":")]
    if len(parts) not in (1, 2, 3) or any(not part for part in parts):
        raise argparse.ArgumentTypeError(
            'must be "view", "cell:view", or "library:cell:view"'
        )
    return ":".join(parts)


def _substrate_argument(value: str) -> str:
    parts = [part.strip() for part in value.split(":")]
    if len(parts) not in (1, 2) or any(not part for part in parts):
        raise argparse.ArgumentTypeError(
            'must be "substrate" or "library:substrate"'
        )
    return ":".join(parts)


def _resolve_design_argument(
    parser: argparse.ArgumentParser,
    option: str,
    value: str,
    default_library: str | None,
    default_cell: str | None,
) -> str:
    parts = value.split(":")
    if len(parts) == 3:
        return value
    if len(parts) == 2:
        if default_library is None:
            parser.error(
                f'{option} {value!r} omits the library; pass --lib or use '
                '"LIB:CELL:VIEW"'
            )
        return f"{default_library}:{value}"
    if default_library is None or default_cell is None:
        missing = []
        if default_library is None:
            missing.append("--lib")
        if default_cell is None:
            missing.append("--cell")
        parser.error(
            f'{option} {value!r} contains only a view; pass '
            f'{" and ".join(missing)} or use "LIB:CELL:VIEW"'
        )
    return f"{default_library}:{default_cell}:{value}"


def _resolve_substrate_argument(
    parser: argparse.ArgumentParser,
    value: str,
    default_library: str | None,
) -> str:
    if ":" in value:
        return value
    if default_library is None:
        parser.error(
            f'--substrate {value!r} omits the library; pass --lib or use '
            '"LIB:SUBSTRATE"'
        )
    return f"{default_library}:{value}"


def _parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh an existing ADS RFPro view, or rebuild it after a PCell "
            "parameter-schema change."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--lib",
        "--library",
        dest="library",
        type=_name_argument,
        metavar="LIB",
        help="default library for abbreviated design and substrate identifiers",
    )
    parser.add_argument(
        "--cell",
        type=_name_argument,
        metavar="CELL",
        help="default cell for design identifiers containing only a view",
    )
    parser.add_argument(
        "--design",
        required=True,
        type=_design_argument,
        metavar="[LIB:[CELL:]]VIEW",
        help="existing ADS RFPro view identifier; may use --lib and --cell",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="ADS workspace path; required for standalone execution",
    )
    parser.add_argument(
        "--rebuild-schema",
        action="store_true",
        help=(
            "back up, delete, and recreate the RFPro view after parameters "
            "were added, removed, renamed, reordered, or changed in type"
        ),
    )
    parser.add_argument(
        "--source-design",
        type=_design_argument,
        metavar="[LIB:[CELL:]]VIEW",
        help=(
            "parameterized source layout; required with --rebuild-schema and "
            "may use --lib and --cell"
        ),
    )
    substrate_source = parser.add_mutually_exclusive_group()
    substrate_source.add_argument(
        "--em-setup-design",
        type=_design_argument,
        metavar="[LIB:[CELL:]]VIEW",
        help=(
            "exact EM Setup cellview from which to override the substrate read "
            "from the existing RFPro view"
        ),
    )
    substrate_source.add_argument(
        "--substrate",
        type=_substrate_argument,
        metavar="[LIB:]SUBSTRATE",
        help=(
            "substrate library and name to use as a final override; normally "
            "read from the existing RFPro view"
        ),
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        help=(
            "schema-rebuild backup root; defaults to "
            "WORKSPACE/.rfpro-pcell-recovery/view-backups"
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the interactive REBUILD confirmation",
    )
    arguments = parser.parse_args(argv)
    if arguments.rebuild_schema and arguments.source_design is None:
        parser.error("--source-design is required with --rebuild-schema")
    if arguments.backup_dir is not None and not arguments.rebuild_schema:
        parser.error("--backup-dir is only valid with --rebuild-schema")
    if arguments.yes and not arguments.rebuild_schema:
        parser.error("--yes is only valid with --rebuild-schema")
    if arguments.em_setup_design is not None and not arguments.rebuild_schema:
        parser.error("--em-setup-design is only valid with --rebuild-schema")
    if arguments.substrate is not None and not arguments.rebuild_schema:
        parser.error("--substrate is only valid with --rebuild-schema")

    arguments.design = _resolve_design_argument(
        parser,
        "--design",
        arguments.design,
        arguments.library,
        arguments.cell,
    )
    if arguments.source_design is not None:
        arguments.source_design = _resolve_design_argument(
            parser,
            "--source-design",
            arguments.source_design,
            arguments.library,
            arguments.cell,
        )
    if arguments.em_setup_design is not None:
        arguments.em_setup_design = _resolve_design_argument(
            parser,
            "--em-setup-design",
            arguments.em_setup_design,
            arguments.library,
            arguments.cell,
        )
    if arguments.substrate is not None:
        arguments.substrate = _resolve_substrate_argument(
            parser,
            arguments.substrate,
            arguments.library,
        )
    return arguments


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


def _package_version() -> str:
    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        version = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown (VERSION file not found)"
    return version or "unknown (VERSION file is empty)"


def _print_qt_runtime() -> None:
    ownership = "created by this script" if QT_APPLICATION_WAS_CREATED else "reused from ADS"
    plugin_description = (
        str(QT_PLATFORM_PLUGIN_FILE)
        if QT_PLATFORM_PLUGIN_FILE is not None
        else "already loaded by ADS; search path unchanged"
    )
    print(f"RFPro recovery package: {_package_version()}")
    print(f"Python executable: {sys.executable}")
    print(f"PySide6 package: {QT_PYSIDE_FILE}")
    print(f"Qt platform plugin: {plugin_description}")
    print(f"Qt platform name: {QT_APPLICATION.platformName()}")
    print(f"QApplication: {ownership}")
    print(f"Qt environment restored: {QT_ENVIRONMENT_WAS_RESTORED}")
    if ADS_EMVIEWS_LIBRARY_FILE is not None:
        print(f"ADS EM Views library: {ADS_EMVIEWS_LIBRARY_FILE}")
    print(f"ADS native runtime: {ADS_NATIVE_RUNTIME_MODE}")
    print(f"ADS product: {de.product_version()}")
    print(f"EM Tools: {emtools.version()}")


def _require_open_library(library_name: str, design_name: str) -> object:
    if not de.library_is_open(library_name):
        raise RuntimeError(
            f"Library {library_name!r} from {design_name!r} is not open. "
            "Run inside ADS with the correct workspace open, or pass --workspace "
            "with the workspace that defines this library."
        )
    return de.Library.get(library_name)


def _pcell_parameter_names(design: db.Design) -> list[str]:
    return [parameter.name for parameter in design.pcell_parameters]


def _require_design_closed_in_window(design_name: str) -> None:
    """Require a stable, saved source layout for read-only validation."""

    from keysight.ads.de import app

    expected = tuple(design_name.split(":"))
    open_windows: list[str] = []
    for window_type in (
        app.WindowType.SCHEMATIC_WINDOW,
        app.WindowType.LAYOUT_WINDOW,
        app.WindowType.SYMBOL_WINDOW,
    ):
        for window in app.find_windows_by_type(window_type):
            try:
                window_design = app.get_design_in_uu_from_window(window)
            except Exception:
                continue
            actual = (
                window_design.lib_name,
                window_design.cell_name,
                window_design.view_name,
            )
            if actual == expected:
                open_windows.append(window.title)

    if open_windows:
        titles = ", ".join(repr(title) for title in open_windows)
        raise RuntimeError(
            f"Source layout {design_name!r} is open in ADS ({titles}). Save "
            "and close only that source layout, then rerun the command. Other "
            "RFPro views and simulations may remain open."
        )


def _read_source_parameter_names(source_design: str) -> list[str]:
    design = db.open_design(source_design, de.db.DesignMode.READ_ONLY)
    if not design.is_supermaster:
        raise RuntimeError(
            f"Source layout {source_design!r} is not a PCell supermaster. "
            "Apply EM > Component > Parameters..., save the layout, and retry."
        )

    parameter_names = _pcell_parameter_names(design)
    if not parameter_names:
        raise RuntimeError(
            f"Source layout {source_design!r} has no top-level PCell parameters. "
            "Reapply EM > Component > Parameters..., save the layout, and retry."
        )
    return parameter_names


def _design_ref_tuple(
    design_ref: object,
    attribute_name: str,
    expected_length: int,
) -> tuple[str, ...]:
    try:
        value = getattr(design_ref, attribute_name)
        if callable(value):
            value = value()
        parts = tuple(str(part) for part in value)
    except (AttributeError, TypeError) as error:
        raise RuntimeError(
            f"RFPro DesignRef has no usable {attribute_name!r} value."
        ) from error
    if len(parts) != expected_length or not all(parts):
        raise RuntimeError(
            f"RFPro DesignRef returned invalid {attribute_name}: {parts!r}."
        )
    return parts


def _read_rfpro_substrate(
    rfpro_lcv: tuple[str, str, str],
    source_lcv: tuple[str, str, str],
) -> tuple[tuple[str, str], tuple[str, str, str]]:
    setup = emtools.EmproSetup(rfpro_lcv)
    tool = str(setup.tool).strip().lower()
    if tool != "rfpro":
        raise RuntimeError(
            f"{':'.join(rfpro_lcv)!r} is an {setup.tool!r} EM view, not RFPro."
        )

    design_refs = setup.design_refs
    if not isinstance(design_refs, dict) or not design_refs:
        raise RuntimeError(
            f"RFPro view {':'.join(rfpro_lcv)!r} contains no design references."
        )

    references: list[
        tuple[tuple[str, str, str], tuple[str, str]]
    ] = []
    for design_ref in design_refs.values():
        layout = _design_ref_tuple(design_ref, "layout", 3)
        substrate = _design_ref_tuple(design_ref, "substrate", 2)
        references.append(
            (
                (layout[0], layout[1], layout[2]),
                (substrate[0], substrate[1]),
            )
        )

    matching = [reference for reference in references if reference[0] == source_lcv]
    candidates = matching if matching else references
    unique_substrates = {reference[1] for reference in candidates}
    if len(unique_substrates) != 1:
        details = ", ".join(
            f"{':'.join(layout)} -> {substrate[0]}:{substrate[1]}"
            for layout, substrate in candidates
        )
        raise RuntimeError(
            "The existing RFPro view contains multiple applicable substrates; "
            f"cannot choose safely: {details}."
        )

    substrate_ls = next(iter(unique_substrates))
    referenced_layout = next(
        layout for layout, substrate in candidates if substrate == substrate_ls
    )
    _require_open_library(substrate_ls[0], ":".join(substrate_ls))
    return substrate_ls, referenced_layout


def _verify_rebuilt_rfpro_reference(
    rfpro_lcv: tuple[str, str, str],
    source_lcv: tuple[str, str, str],
    expected_substrate: tuple[str, str],
) -> None:
    """Verify the public RFPro setup points to the requested source exactly."""

    setup = emtools.EmproSetup(rfpro_lcv)
    design_refs = setup.design_refs
    if not isinstance(design_refs, dict) or not design_refs:
        raise RuntimeError(
            f"Rebuilt RFPro view {':'.join(rfpro_lcv)!r} has no design references."
        )

    references: list[
        tuple[tuple[str, str, str], tuple[str, str]]
    ] = []
    for design_ref in design_refs.values():
        layout_parts = _design_ref_tuple(design_ref, "layout", 3)
        substrate_parts = _design_ref_tuple(design_ref, "substrate", 2)
        references.append(
            (
                (layout_parts[0], layout_parts[1], layout_parts[2]),
                (substrate_parts[0], substrate_parts[1]),
            )
        )

    if (source_lcv, expected_substrate) not in references:
        details = ", ".join(
            f"{':'.join(layout)} -> {substrate[0]}:{substrate[1]}"
            for layout, substrate in references
        )
        raise RuntimeError(
            "The rebuilt RFPro setup does not contain the requested source "
            f"and substrate pair. Found: {details}."
        )

    print("Rebuilt RFPro design reference verified:")
    print(f"  Layout: {':'.join(source_lcv)}")
    print(f"  Substrate: {expected_substrate[0]}:{expected_substrate[1]}")


def _discover_rebuild_inputs(
    rfpro_lcv: tuple[str, str, str],
    source_design: str,
    emsetup_design: str | None,
    explicit_substrate: str | None,
) -> tuple[
    tuple[str, str, str],
    str | None,
    tuple[str, str],
    str,
    list[str],
]:
    source_library, source_cell_name, source_view_name = source_design.split(":")
    source_lcv = (source_library, source_cell_name, source_view_name)
    library = _require_open_library(source_library, source_design)
    if not library.cell_exists(source_cell_name):
        raise RuntimeError(f"Source cell does not exist: {source_design!r}.")

    cell = library.cell(source_cell_name)
    if not cell.view_exists(source_view_name):
        raise RuntimeError(f"Source layout does not exist: {source_design!r}.")

    parameter_names = _read_source_parameter_names(source_design)

    if explicit_substrate is not None:
        substrate_library, substrate_name = explicit_substrate.split(":")
        _require_open_library(substrate_library, explicit_substrate)
        substrate_ls = (substrate_library, substrate_name)
        return (
            source_lcv,
            None,
            substrate_ls,
            "command-line --substrate override",
            parameter_names,
        )

    if emsetup_design is None:
        try:
            substrate_ls, referenced_layout = _read_rfpro_substrate(
                rfpro_lcv,
                source_lcv,
            )
            return (
                source_lcv,
                None,
                substrate_ls,
                (
                    f"existing RFPro view {':'.join(rfpro_lcv)} "
                    f"(layout reference {':'.join(referenced_layout)})"
                ),
                parameter_names,
            )
        except Exception as rfpro_error:
            try:
                emsetup_view_name = emtools.find_emsetup_view_name(source_lcv)
            except RuntimeError as emsetup_error:
                raise RuntimeError(
                    "Could not obtain a substrate from either the existing "
                    f"RFPro view or an active EM Setup for {source_design!r}. "
                    "No RFPro view was changed. "
                    f"RFPro setup: {rfpro_error} "
                    f"EM Setup: {emsetup_error} "
                    "Pass --em-setup-design to select an EM Setup explicitly, "
                    "or use --substrate as a final override."
                ) from emsetup_error
        emsetup_lcv = (
            source_library,
            source_cell_name,
            emsetup_view_name,
        )
        emsetup_design = ":".join(emsetup_lcv)
    else:
        emsetup_library, emsetup_cell_name, emsetup_view_name = (
            emsetup_design.split(":")
        )
        emsetup_lcv = (
            emsetup_library,
            emsetup_cell_name,
            emsetup_view_name,
        )

    emsetup_library = _require_open_library(emsetup_lcv[0], emsetup_design)
    if not emsetup_library.cell_exists(emsetup_lcv[1]):
        raise RuntimeError(f"EM Setup cell does not exist: {emsetup_design!r}.")
    emsetup_cell = emsetup_library.cell(emsetup_lcv[1])
    if not emsetup_cell.view_exists(emsetup_lcv[2]):
        raise RuntimeError(
            f"EM Setup view does not exist: {emsetup_design!r}."
        )

    substrate = emtools.get_substrate_info(emsetup_lcv)
    if len(substrate) != 2 or not all(substrate):
        raise RuntimeError(
            f"ADS returned invalid substrate information for {emsetup_design!r}: "
            f"{substrate!r}."
        )
    substrate_ls = (str(substrate[0]), str(substrate[1]))
    return (
        source_lcv,
        emsetup_design,
        substrate_ls,
        f"EM Setup {emsetup_design}",
        parameter_names,
    )


def _safe_path_component(value: str) -> str:
    safe_value = "".join(
        character if character.isalnum() or character in "-_." else "_"
        for character in value
    )
    return safe_value or "unnamed"


def _planned_backup_path(
    rfpro_lcv: tuple[str, str, str], backup_root: Path | None
) -> Path:
    if backup_root is None:
        root = (
            de.active_workspace().path
            / ".rfpro-pcell-recovery"
            / "view-backups"
        )
    else:
        root = backup_root.expanduser().resolve()

    library, cell, view = rfpro_lcv
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    return (
        root
        / _safe_path_component(library)
        / _safe_path_component(cell)
        / f"{_safe_path_component(view)}-{timestamp}"
    )


def _confirm_schema_rebuild(
    rfpro_design: str,
    source_design: str,
    source_view_path: Path,
    backup_path: Path,
    emsetup_design: str | None,
    substrate_ls: tuple[str, str],
    substrate_source: str,
    parameter_names: list[str],
    assume_yes: bool,
) -> None:
    print("Schema rebuild requested.")
    print(f"  RFPro view: {rfpro_design}")
    print(f"  Source layout: {source_design}")
    print(f"  Existing view path: {source_view_path}")
    print(f"  Backup destination: {backup_path}")
    print(f"  EM Setup: {emsetup_design or 'not used'}")
    print(f"  Substrate: {substrate_ls[0]}:{substrate_ls[1]}")
    print(f"  Substrate source: {substrate_source}")
    print(f"  New source parameters ({len(parameter_names)}):")
    for name in parameter_names:
        print(f"    {name}")
    print("  Source action: read-only validation; the layout will not be modified")
    print("  RFPro analyses, sweeps, and local view settings may need recreation.")

    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise RuntimeError(
            "Interactive confirmation is unavailable. Re-run with --yes after "
            "reviewing the rebuild plan."
        )
    confirmation = input("Type REBUILD to continue: ")
    if confirmation != "REBUILD":
        raise RuntimeError("Schema rebuild cancelled; nothing was changed.")


def _write_backup_manifest(
    backup_path: Path,
    rfpro_design: str,
    source_design: str,
    emsetup_design: str | None,
    substrate_ls: tuple[str, str],
    substrate_source: str,
    parameter_names: list[str],
) -> None:
    manifest = {
        "created": datetime.now().astimezone().isoformat(),
        "ads_product": de.product_version(),
        "emtools": emtools.version(),
        "rfpro_design": rfpro_design,
        "source_design": source_design,
        "emsetup_design": emsetup_design,
        "emsetup_view": (
            emsetup_design.split(":")[2] if emsetup_design is not None else None
        ),
        "substrate": list(substrate_ls),
        "substrate_source": substrate_source,
        "source_parameters": parameter_names,
    }
    manifest_path = backup_path / "rfpro-recovery-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _rebuild_rfpro_schema(
    rfpro_lcv: tuple[str, str, str],
    rfpro_design: str,
    source_design: str,
    emsetup_design: str | None,
    explicit_substrate: str | None,
    backup_root: Path | None,
    assume_yes: bool,
) -> None:
    library_name, cell_name, view_name = rfpro_lcv
    library = _require_open_library(library_name, rfpro_design)
    if not library.is_writable:
        raise RuntimeError(
            f"Library {library_name!r} is read-only; the RFPro view cannot be rebuilt."
        )
    if not library.cell_exists(cell_name):
        raise RuntimeError(f"RFPro cell does not exist: {rfpro_design!r}.")

    cell = library.cell(cell_name)
    if not cell.view_exists(view_name):
        raise RuntimeError(f"RFPro view does not exist: {rfpro_design!r}.")
    old_view_path = cell.view(view_name).path
    if not old_view_path.is_dir():
        raise RuntimeError(
            f"RFPro view path is not a directory: {old_view_path}."
        )

    _require_design_closed_in_window(source_design)

    (
        source_lcv,
        resolved_emsetup_design,
        substrate_ls,
        substrate_source,
        parameter_names,
    ) = _discover_rebuild_inputs(
        rfpro_lcv,
        source_design,
        emsetup_design,
        explicit_substrate,
    )
    backup_path = _planned_backup_path(rfpro_lcv, backup_root)
    _confirm_schema_rebuild(
        rfpro_design,
        source_design,
        old_view_path,
        backup_path,
        resolved_emsetup_design,
        substrate_ls,
        substrate_source,
        parameter_names,
        assume_yes,
    )

    # Do not call PCellInfo.make_pcell() here. It is a conversion API that
    # derives a new PCell schema from the item definition; it is not a registry
    # refresh and can replace an EM Component parameter selection.
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(old_view_path, backup_path)
    _write_backup_manifest(
        backup_path,
        rfpro_design,
        source_design,
        resolved_emsetup_design,
        substrate_ls,
        substrate_source,
        parameter_names,
    )
    print(f"Existing RFPro view preserved at: {backup_path}")

    cell.delete_view(view_name)
    if cell.view_exists(view_name):
        raise RuntimeError(
            f"ADS did not remove {rfpro_design!r}; backup is at {backup_path}."
        )

    try:
        emtools.create_empro_view(
            rfpro_lcv,
            "rfpro",
            source_lcv,
            substrate_ls,
        )
        emtools.update_empro_view(rfpro_lcv)
        _verify_rebuilt_rfpro_reference(
            rfpro_lcv,
            source_lcv,
            substrate_ls,
        )
    except Exception as error:
        raise RuntimeError(
            f"RFPro recreation failed after the original view was backed up. "
            f"Preserved view: {backup_path}"
        ) from error

    if not cell.view_exists(view_name):
        raise RuntimeError(
            f"ADS reported no RFPro view after recreation: {rfpro_design!r}. "
            f"Preserved view: {backup_path}"
        )

    print("Schema rebuild and final auxiliary-file refresh completed.")
    print("The source PCell was validated without modifying its definition.")
    print(f"Previous RFPro view backup: {backup_path}")
    print("Open RFPro and verify Design Parameters before recreating any sweeps.")


def main(argv: list[str] | None = None) -> None:
    arguments = _parse_arguments(argv)
    library, cell, view = arguments.design.split(":")
    rfpro_lcv = (library, cell, view)
    _print_qt_runtime()

    if arguments.rebuild_schema and not de.is_pde_app():
        raise RuntimeError(
            "--rebuild-schema must run inside the live ADS application. This "
            "workspace loads application-only AEL functions such as "
            "api_create_palette_item and "
            "db_add_design_opened_in_window_callback; they are intentionally "
            "unavailable in standalone automation. No workspace or design "
            "was opened. Run main([...]) from the ADS Python Console and omit "
            "--workspace."
        )
    if arguments.rebuild_schema and arguments.workspace is not None:
        raise RuntimeError(
            "Do not pass --workspace with --rebuild-schema inside ADS. Open "
            "the owning workspace in ADS first, then run main([...]) against "
            "that live session."
        )

    workspace = _open_workspace_if_requested(arguments.workspace)
    _require_open_library(library, arguments.design)

    if arguments.rebuild_schema:
        assert arguments.source_design is not None
        _rebuild_rfpro_schema(
            rfpro_lcv,
            arguments.design,
            arguments.source_design,
            arguments.em_setup_design,
            arguments.substrate,
            arguments.backup_dir,
            arguments.yes,
        )
    else:
        print(f"Refreshing RFPro view {arguments.design} ...")
        emtools.update_empro_view(rfpro_lcv)
        print("Refresh completed. Open RFPro and inspect Design Parameters.")
        print(
            "If parameter names, types, order, or count changed, use "
            "--rebuild-schema instead of repeating this update."
        )

    # Keep a standalone-opened workspace alive until the refresh has finished.
    _ = workspace


if __name__ == "__main__":
    main()
