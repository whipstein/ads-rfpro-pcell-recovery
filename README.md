# ADS RFPro PCell Recovery

Current release: **1.7.0**. See [CHANGELOG.md](CHANGELOG.md) for release
history.

This package diagnoses and refreshes RFPro parameters created with
`EM > Component > Parameters...`. Both production Python scripts include the
required Qt setup directly—no helper import and no user-level Qt environment
changes are required.

An **AEL Macro PCell is expected** for this workflow. Do not convert it to a
Python PCell or recreate its parameters in `File > Customize PCell`.

## Files

```text
ads-rfpro-pcell-recovery/
├── .github/workflows/static-checks.yml
├── .vscode/
│   ├── extensions.json
│   ├── launch.json
│   ├── settings.json
│   └── tasks.json
├── CHANGELOG.md
├── CONTRIBUTING.md
├── README.md
├── VERSION
├── de_generated_scripts/
│   ├── diagnose_pcell_parameters.py
│   └── refresh_rfpro_view.py
└── scripts/
    ├── diagnose_qt.py
    ├── Reset-AdsPcellsCache.ps1
    ├── reset_adspcells_cache.sh
    └── test_qt_startup.py
```

## Development in VS Code

Open the repository root in VS Code. Accept the recommended extensions, then
run **ADS Python Utilities: Configure Python Interpreter Path** from the Command
Palette and select the Python interpreter from the ADS installation being
tested:

- Linux: `$HPEESOF_DIR/tools/python/bin/python3`
- Windows: `%HPEESOF_DIR%\tools\python\python.exe`

The repository includes launch configurations for both production scripts and
for attaching to the ADS Design Environment debugger on port 8765. It also
includes a **Repo: static checks** task. Static checks can run without ADS, but
runtime validation must use the ADS-bundled interpreter or a supported live ADS
execution path.

Do not install a separate PySide6 into the ADS interpreter. The scripts locate
and use the Qt and ADS native runtime shipped with the selected ADS release.

Production scripts:

- [`diagnose_pcell_parameters.py`](de_generated_scripts/diagnose_pcell_parameters.py)
- [`refresh_rfpro_view.py`](de_generated_scripts/refresh_rfpro_view.py)

Support scripts:

- [`diagnose_qt.py`](scripts/diagnose_qt.py)
- [`test_qt_startup.py`](scripts/test_qt_startup.py)
- [`Reset-AdsPcellsCache.ps1`](scripts/Reset-AdsPcellsCache.ps1)
- [`reset_adspcells_cache.sh`](scripts/reset_adspcells_cache.sh)

## Integrated Qt method

Each production script performs the following before importing `keysight.ads`:

1. Imports PySide6 and checks immediately whether ADS already owns a
   `QApplication`.
2. If ADS owns the application, reuses it without searching for a plugin and
   without changing the environment or Qt library paths.
3. For a script-owned application, queries Qt's authoritative
   `QLibraryInfo` plugin root and `QCoreApplication.libraryPaths()`.
4. It then checks the two standard PySide6-relative plugin locations and any
   valid existing Qt plugin paths.
5. If those locations do not contain the matching `qwindows.dll`,
   `libqxcb.so`, or `libqcocoa.dylib`, it automatically searches the active
   PySide6 directory, `sys.prefix`, the ADS root inferred from a
   `.../tools/python...` interpreter, and `HPEESOF_DIR` when available.
6. On Linux, reports unresolved `ldd` dependencies before Qt can abort.
7. Temporarily redirects
   `QT_QPA_PLATFORM_PLUGIN_PATH` only during `QApplication([])` construction.
8. Restores the exact previous environment state in `finally`, including an
   originally unset or empty value.
9. Keeps the application object alive for the entire ADS operation.
10. Prints the interpreter, PySide6 path, plugin file, Qt platform, application
   ownership, and environment-restoration result.

The scripts do not require `ADS_QT_PLATFORM_PLUGIN_PATH`, shell exports,
registry changes, launcher edits, or a second PySide6 installation. They also
do not force `QT_QPA_PLATFORM=offscreen` for graphical ADS workflows.

## Integrated ADS native-library method

On Linux, `refresh_rfpro_view.py` prepares the compiled ADS EM Tools runtime
before importing `keysight.ads.emtools`:

1. Validates `HPEESOF_DIR`, or infers the ADS root from the bundled Python
   interpreter and sets `HPEESOF_DIR` only inside the script process.
2. Finds the installed `libemViewsPlugin.so`, preferring the standard ADS
   library locations and then searching the validated ADS installation.
3. Builds a loader path from the library's actual parent plus the existing ADS
   `bin`, `lib/linux_x86_64`, `lib`, and `tools/python/lib` directories.
4. For a standalone process, restarts the same script exactly once with that
   process-local `LD_LIBRARY_PATH`. It does not modify the launching shell,
   profile, or system configuration.
5. When a Qt application already exists, it never replaces the live ADS
   process. It imports Design Environment first and preloads the exact native
   library with global symbol visibility before importing EM Tools.
6. Keeps any preload handle alive through the complete refresh and reports the
   selected native library and setup mode.
7. If a transitive library is still absent, includes unresolved `ldd` entries
   in the Python error instead of returning only a generic import failure.

## Command-line interface

Each production script accepts one required ADS design identifier. Quote it so
the shell passes the complete `library:cell:view` value unchanged.

```text
diagnose_pcell_parameters.py --design "LIBRARY:CELL:LAYOUT_VIEW"
    [--workspace /absolute/path/to/workspace_wrk]

refresh_rfpro_view.py --design "LIBRARY:CELL:RFPRO_VIEW"
    [--workspace /absolute/path/to/workspace_wrk]
```

`--design` must have exactly three non-empty colon-separated fields. Use
`--workspace` when launching a fresh ADS-bundled Python process. The design
string identifies a cellview but does not open its library by itself; the
library must belong to the active workspace. Omit `--workspace` only when the
script already executes in a process with the correct ADS workspace open.

In the examples below, `python` means the Python executable bundled with the
same ADS installation that owns the workspace—not a system Python installation.

## Recovery procedure

### 1. Diagnose the layout PCell

Run the diagnostic with the source layout cellview:

```bash
python diagnose_pcell_parameters.py --design "MY_LIB:MY_CELL:layout"
```

For standalone ADS Python, provide the workspace:

```bash
python diagnose_pcell_parameters.py --design "MY_LIB:MY_CELL:layout" \
  --workspace "/absolute/path/to/workspace_wrk"
```

| Result | Meaning | Next action |
|---|---|---|
| Parameters are listed | The source is healthy and RFPro's cache is stale | Reset `.adsPcells`, then refresh RFPro |
| PCell supermaster is true but its parameter list is empty | AEL PCell metadata was not committed | Reapply `EM > Component > Parameters...` and save |
| Layout is not a PCell supermaster | EM parameterization was not applied | Apply it through `EM > Component > Parameters...` and save |

### 2. Preserve the stale cache

Exit ADS completely. These commands rename `.adsPcells`; they do not delete it.

Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
./scripts/Reset-AdsPcellsCache.ps1 -WorkspacePath "C:\path\to\workspace_wrk"
```

macOS/Linux:

```bash
chmod +x scripts/reset_adspcells_cache.sh
./scripts/reset_adspcells_cache.sh "/path/to/workspace_wrk"
```

### 3. Refresh RFPro

Restart ADS but keep RFPro closed. Pass the existing RFPro cellview:

```bash
python refresh_rfpro_view.py --design "MY_LIB:MY_CELL:MY_RFPRO_VIEW"
```

For standalone ADS Python:

```bash
python refresh_rfpro_view.py --design "MY_LIB:MY_CELL:MY_RFPRO_VIEW" \
  --workspace "/absolute/path/to/workspace_wrk"
```

`update_empro_view()` rebuilds the RFPro
auxiliary data, including `.adsPcells`, `adsMultiTechData.json`, and `proj.ltd`.
Then open RFPro and inspect **Design Parameters**.

Deleting and recreating only the RFPro cellview is insufficient because
`.adsPcells` resides at the workspace root.

## Qt validation

If the integrated scripts still report a Qt error, run these with the exact
interpreter and launch environment used for the RFPro scripts.

Windows:

```powershell
& "$env:HPEESOF_DIR\tools\python\python.exe" scripts\diagnose_qt.py
& "$env:HPEESOF_DIR\tools\python\python.exe" scripts\test_qt_startup.py
```

Linux:

```bash
"$HPEESOF_DIR/tools/python/bin/python3" scripts/diagnose_qt.py
"$HPEESOF_DIR/tools/python/bin/python3" scripts/test_qt_startup.py
```

- `pyside6_import_error` indicates the wrong interpreter or incomplete ADS
  Python environment.
- A missing platform binary after the automatic Qt/ADS search requires
  correcting the interpreter or repairing the ADS runtime.
- `unresolved_dependency` identifies a native Linux library required by
  `libqxcb.so`.
- A missing `DISPLAY` or `WAYLAND_DISPLAY` requires a usable graphical session;
  the scripts do not conceal it with offscreen mode.

## Safety and compatibility

- Close ADS before renaming `.adsPcells`.
- Close RFPro before running `refresh_rfpro_view.py`.
- Existing sweeps may need recreation when parameter names change.
- APIs were checked against the portable ADS 2026 Update 2.1 reference. ADS was
  unavailable on the packaging machine, so final Qt startup must be tested on
  the target ADS installation.
- ADS 2024 Update 2 documented the `.adsPcells` workaround. ADS 2025 Update 1
  added broader support for top-level and hierarchical PCell changes.

## Keysight references

- [ADS 2024 Update 2 release notes](https://docs.keysight.com/spaces/flyingpdf/pdfpageexport.action?pageId=866288141)
- [ADS 2025 Update 1 release notes](https://docs.keysight.com/spaces/flyingpdf/pdfpageexport.action?pageId=907545782)
