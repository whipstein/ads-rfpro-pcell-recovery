# ADS RFPro PCell Recovery

Current release: **1.11.0**. See [CHANGELOG.md](CHANGELOG.md) for release
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

Each production script accepts an ADS design identifier. Use `--lib` and
`--cell` once to provide defaults for abbreviated identifiers:

```text
diagnose_pcell_parameters.py [--lib LIBRARY] [--cell CELL]
    --design "LAYOUT_VIEW|CELL:LAYOUT_VIEW|LIBRARY:CELL:LAYOUT_VIEW"
    [--workspace /absolute/path/to/workspace_wrk]

refresh_rfpro_view.py [--lib LIBRARY] [--cell CELL]
    --design "RFPRO_VIEW|CELL:RFPRO_VIEW|LIBRARY:CELL:RFPRO_VIEW"
    [--workspace /absolute/path/to/workspace_wrk]

refresh_rfpro_view.py [--lib LIBRARY] [--cell CELL]
    --design "RFPRO_VIEW|CELL:RFPRO_VIEW|LIBRARY:CELL:RFPRO_VIEW"
    --rebuild-schema
    --source-design "[LIBRARY:[CELL:]]LAYOUT_VIEW"
    [--em-setup-design "[LIBRARY:[CELL:]]EM_SETUP_VIEW" |
     --substrate "[LIBRARY:]SUBSTRATE_NAME"]
    [--workspace /absolute/path/to/workspace_wrk]
    [--backup-dir /absolute/path/to/backups]
    [--yes]
```

The identifier resolution rules are:

| Input | Defaults used | Resolved form |
|---|---|---|
| `--design rfpro` | `--lib MY_LIB --cell MY_CELL` | `MY_LIB:MY_CELL:rfpro` |
| `--source-design OTHER_CELL:layout` | `--lib MY_LIB` | `MY_LIB:OTHER_CELL:layout` |
| `--em-setup-design OTHER_LIB:CELL:emSetup` | none | unchanged |
| `--substrate tech.subst` | `--lib MY_LIB` | `MY_LIB:tech.subst` |

Full identifiers remain supported and override the defaults for that option.
`--library` is an alias for `--lib`. Use `--workspace` when launching a fresh
ADS-bundled Python process. An identifier does not open its library by itself;
the library must belong to the active workspace. Omit `--workspace` only when
the script already executes in a process with the correct workspace open.

Use the normal refresh only when parameter names, types, order, and count are
unchanged. Use `--rebuild-schema` after adding, removing, renaming, reordering,
or changing the type of a parameter. Schema rebuild is intentionally explicit
because it replaces the RFPro view and may invalidate analyses or sweeps.
The rebuild normally reads the substrate directly from the existing RFPro
view's public `EmproSetup.design_refs`. It matches the RFPro design reference to
`--source-design` when possible. An active EM Setup is used only as a fallback.
Use `--em-setup-design` or `--substrate` only to override automatic discovery.

In the examples below, `python` means the Python executable bundled with the
same ADS installation that owns the workspace—not a system Python installation.

## Recovery procedure

### 1. Diagnose the layout PCell

Run the diagnostic with the source layout cellview:

```bash
python de_generated_scripts/diagnose_pcell_parameters.py \
  --lib "MY_LIB" \
  --cell "MY_CELL" \
  --design "layout"
```

For standalone ADS Python, provide the workspace:

```bash
python de_generated_scripts/diagnose_pcell_parameters.py \
  --lib "MY_LIB" \
  --cell "MY_CELL" \
  --design "layout" \
  --workspace "/absolute/path/to/workspace_wrk"
```

| Result | Meaning | Next action |
|---|---|---|
| Parameters are listed | The source is healthy and RFPro's auxiliary data may be stale | Refresh only the affected RFPro view first |
| PCell supermaster is true but its parameter list is empty | AEL PCell metadata was not committed | Reapply `EM > Component > Parameters...` and save |
| Layout is not a PCell supermaster | EM parameterization was not applied | Apply it through `EM > Component > Parameters...` and save |

### 2. Last resort: preserve and reset the global cache

Skip this step for the first refresh or schema-rebuild attempt. `.adsPcells` is
workspace-wide, so resetting it can make unrelated RFPro analyses appear stale
or unsimulated. Use this only after a targeted attempt fails and after all RFPro
work in the workspace is stopped. Exit ADS completely. These commands rename
`.adsPcells`; they do not delete it.

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

### 3A. Refresh value-only changes

Restart ADS but keep RFPro closed. Pass the existing RFPro cellview:

```bash
python de_generated_scripts/refresh_rfpro_view.py \
  --lib "MY_LIB" \
  --cell "MY_CELL" \
  --design "MY_RFPRO_VIEW"
```

For standalone ADS Python:

```bash
python de_generated_scripts/refresh_rfpro_view.py \
  --lib "MY_LIB" \
  --cell "MY_CELL" \
  --design "MY_RFPRO_VIEW" \
  --workspace "/absolute/path/to/workspace_wrk"
```

`update_empro_view()` rebuilds the RFPro
auxiliary data, including `.adsPcells`, `adsMultiTechData.json`, and `proj.ltd`.
Then open RFPro and inspect **Design Parameters**.

Do not repeat the normal refresh when the parameter schema changed; proceed to
the schema rebuild below.

### 3B. Rebuild after a parameter-schema change

Use this when parameters were added, removed, renamed, reordered, or changed in
type. Run this targeted rebuild before considering the global `.adsPcells`
reset in step 2. For the most deterministic result, leave ADS closed and launch
the script from VS Code with the ADS-bundled interpreter. `--workspace` lets the
script open the workspace itself:

```bash
python de_generated_scripts/refresh_rfpro_view.py \
  --lib "MY_LIB" \
  --cell "MY_CELL" \
  --design "MY_RFPRO_VIEW" \
  --source-design "layout" \
  --rebuild-schema \
  --workspace "/absolute/path/to/workspace_wrk"
```

Open ADS only after this command completes. This prevents a newly launched ADS
session from writing workspace RFPro/PCell state while the schema rebuild is in
progress. The included VS Code configuration **ADS: Rebuild RFPro parameter
schema** follows this standalone path.

Running inside a live ADS process is also supported: restart ADS, keep RFPro
closed, execute the script through the supported in-application path, and omit
`--workspace` because the correct workspace is already active.

The script validates that the source layout is a PCell supermaster with
top-level parameters. Before touching the RFPro view, it re-registers only the
specified source PCell from its saved `PCellInfo` and saves that supermaster.
This refreshes the in-process PCell registry used by RFPro while preserving the
AEL evaluator and its selected artwork arguments. The confirmation prompt
lists this source action as well as the RFPro replacement. It also reads the
layout and substrate references from the existing RFPro view and prints the
resolved substrate and its source in the rebuild plan.

If the existing RFPro setup cannot be read, the script tries the active EM
Setup automatically. To override both, select an EM Setup explicitly:

```bash
python de_generated_scripts/refresh_rfpro_view.py \
  --lib "MY_LIB" \
  --cell "MY_CELL" \
  --design "MY_RFPRO_VIEW" \
  --source-design "layout" \
  --em-setup-design "emSetup" \
  --rebuild-schema \
  --workspace "/absolute/path/to/workspace_wrk"
```

Or supply the substrate directly as a final override:

```bash
python de_generated_scripts/refresh_rfpro_view.py \
  --lib "MY_LIB" \
  --cell "MY_CELL" \
  --design "MY_RFPRO_VIEW" \
  --source-design "layout" \
  --substrate "tech.subst" \
  --rebuild-schema \
  --workspace "/absolute/path/to/workspace_wrk"
```

These options are mutually exclusive. The explicit EM Setup may be on a
different cell from the parameterized source layout. In multi-design RFPro
views, the script selects the reference matching `--source-design`. If no
reference matches, it proceeds only when all RFPro references use the same
substrate; otherwise an explicit override is required.

After confirmation the script:

1. Re-registers the specified source PCell before changing the RFPro view.
2. Copies the complete existing RFPro view to
   `WORKSPACE/.rfpro-pcell-recovery/view-backups/...`.
3. Adds `rfpro-recovery-manifest.json` to the backup with the source parameter
   names, ADS version, substrate, and whether it came from RFPro, EM Setup, or
   a command-line override.
4. Deletes the stale RFPro view through `Cell.delete_view()`.
5. Recreates it through `create_empro_view()` and performs one final
   `update_empro_view()` call.
6. Reopens the generated RFPro setup and verifies that it contains the exact
   requested source-layout and substrate reference before reporting success.

Use `--backup-dir` to place the backup elsewhere. Use `--yes` only after
reviewing the command; it skips the interactive confirmation. This operation
can discard RFPro analyses, sweeps, and view-local settings from the active
view. They remain in the preserved backup but may need manual recreation.

If a targeted rebuild still retains old generated geometry, the global reset
in step 2 remains the documented fallback. It affects every RFPro view because
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
- Treat `.adsPcells` reset as workspace-wide; do not use it while unrelated
  RFPro simulations or result reviews are active.
- Close RFPro before running `refresh_rfpro_view.py`.
- A schema rebuild replaces the active RFPro view; analyses, sweeps, and local
  view settings may need recreation. The previous view is copied first.
- APIs were checked against the portable ADS 2026 Update 2.1 reference. ADS was
  unavailable on the packaging machine, so final Qt startup must be tested on
  the target ADS installation.
- ADS 2024 Update 2 documented the `.adsPcells` workaround. ADS 2025 Update 1
  states that all top-level and hierarchical PCell parameter changes are
  supported. The explicit rebuild mode remains a recovery path when an existing
  RFPro view retains stale schema metadata.

## Keysight references

- [ADS 2024 Update 2 release notes](https://docs.keysight.com/spaces/flyingpdf/pdfpageexport.action?pageId=866288141)
- [ADS 2025 Update 1 release notes](https://docs.keysight.com/spaces/flyingpdf/pdfpageexport.action?pageId=907545782)
