"""Report the Qt/PySide6 runtime selected by the failing script launcher."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path


QT_ENV_NAMES = (
    "HPEESOF_DIR",
    "QT_QPA_PLATFORM",
    "QT_QPA_PLATFORM_PLUGIN_PATH",
    "QT_PLUGIN_PATH",
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "LD_LIBRARY_PATH",
    "PYTHONPATH",
)


def expected_plugin_name() -> str:
    if sys.platform.startswith("linux"):
        return "libqxcb.so"
    if sys.platform == "win32":
        return "qwindows.dll"
    if sys.platform == "darwin":
        return "libqcocoa.dylib"
    return ""


def unique_existing_roots(paths: list[Path]) -> list[Path]:
    roots: list[Path] = []
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    return roots


def find_plugins(roots: list[Path], filename: str) -> list[Path]:
    matches: list[Path] = []
    if not filename:
        return matches
    for root in roots:
        try:
            for match in root.rglob(filename):
                if match not in matches:
                    matches.append(match)
                if len(matches) >= 30:
                    return matches
        except OSError as error:
            print(f"search_warning[{root}]={error}")
    return matches


def main() -> int:
    print(f"executable={sys.executable}")
    print(f"sys.prefix={sys.prefix}")
    print(f"python={sys.version.split()[0]}")
    print(f"platform={platform.platform()}")
    for name in QT_ENV_NAMES:
        print(f"env.{name}={os.environ.get(name)!r}")

    try:
        import PySide6
    except Exception as error:
        print(f"pyside6_import_error={error!r}")
        return 2

    pyside_root = Path(PySide6.__file__).resolve().parent
    print(f"PySide6.__file__={PySide6.__file__}")

    try:
        from PySide6.QtCore import QCoreApplication, QLibraryInfo

        print(
            "qt.library_plugins_path="
            f"{QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)!r}"
        )
        print(f"qt.library_paths={QCoreApplication.libraryPaths()!r}")
    except Exception as error:
        print(f"qtcore_diagnostic_error={error!r}")

    roots = [pyside_root, Path(sys.prefix)]
    hpeesof_dir = os.environ.get("HPEESOF_DIR")
    if hpeesof_dir:
        roots.append(Path(hpeesof_dir))
    roots = unique_existing_roots(roots)
    print("search_roots=" + os.pathsep.join(str(root) for root in roots))

    filename = expected_plugin_name()
    matches = find_plugins(roots, filename)
    print(f"expected_platform_plugin={filename!r}")
    for match in matches:
        print(f"platform_plugin={match}")

    if not matches:
        print("result=expected platform plugin was not found")
        return 3

    if sys.platform.startswith("linux"):
        ldd = subprocess.run(
            ["ldd", str(matches[0])],
            check=False,
            capture_output=True,
            text=True,
        )
        print(f"ldd_returncode={ldd.returncode}")
        unresolved = [
            line.strip()
            for line in ldd.stdout.splitlines()
            if "not found" in line
        ]
        for line in unresolved:
            print(f"unresolved_dependency={line}")
        if unresolved:
            print("result=plugin exists but has unresolved shared libraries")
            return 4

    print("result=platform plugin exists; test QApplication under this launcher")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
