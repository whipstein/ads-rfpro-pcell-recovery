"""Test automatic, scoped Qt startup without permanent environment changes."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def expected_plugin_name() -> str:
    if sys.platform.startswith("linux"):
        return "libqxcb.so"
    if sys.platform == "win32":
        return "qwindows.dll"
    if sys.platform == "darwin":
        return "libqcocoa.dylib"
    raise RuntimeError(f"Unsupported Qt platform: {sys.platform}")


def locate_plugin(pyside_file: Path) -> Path:
    from PySide6.QtCore import QCoreApplication, QLibraryInfo

    plugin_name = expected_plugin_name()
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
        for entry in os.environ.get(environment_name, "").split(os.pathsep):
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

    visited: list[Path] = []
    for root in fallback_roots:
        try:
            resolved_root = root.expanduser().resolve()
        except OSError:
            continue
        if not resolved_root.is_dir() or resolved_root in visited:
            continue
        visited.append(resolved_root)
        try:
            for match in resolved_root.rglob(plugin_name):
                if match.is_file():
                    return match
        except OSError:
            continue

    checked = [str(path / plugin_name) for path in directories]
    checked.extend(f"recursive: {root}" for root in visited)
    raise RuntimeError("Qt platform plugin not found. Searched:\n  " + "\n  ".join(checked))


def main() -> None:
    try:
        import PySide6
    except Exception as error:
        raise RuntimeError(
            f"PySide6 is unavailable in interpreter {sys.executable!r}."
        ) from error

    from PySide6.QtWidgets import QApplication

    pyside_file = Path(PySide6.__file__).resolve()
    application = QApplication.instance()
    owns_application = application is None
    plugin_file: Path | None = None
    restored = True

    if application is None:
        plugin_file = locate_plugin(pyside_file)
        if sys.platform.startswith("linux"):
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
                raise RuntimeError(
                    "Unresolved Qt dependencies:\n" + "\n".join(unresolved)
                )

            selected_platform = os.environ.get("QT_QPA_PLATFORM", "").lower()
            has_display = bool(
                os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
            )
            if not has_display and selected_platform not in {"offscreen", "minimal"}:
                raise RuntimeError("No DISPLAY or WAYLAND_DISPLAY is available.")

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

    plugin_description = (
        str(plugin_file)
        if plugin_file is not None
        else "already loaded by ADS; search path unchanged"
    )
    print(f"executable={sys.executable}")
    print(f"PySide6.__file__={pyside_file}")
    print(f"platform_plugin={plugin_description}")
    print(f"platform_name={application.platformName()}")
    print(f"QApplication={'created' if owns_application else 'reused'}")
    print(f"environment_restored={restored}")
    print("result=QApplication startup succeeded")

    if owns_application:
        application.quit()


if __name__ == "__main__":
    main()
