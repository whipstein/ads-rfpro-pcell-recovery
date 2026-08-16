# ADS RFPro PCell Recovery

Current release: **1.15.0**. See [CHANGELOG.md](CHANGELOG.md) for release
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
ADS-bundled Python process for diagnosis or a value-only refresh. A schema
rebuild must run inside the live ADS application with the owning workspace
already open, and therefore rejects `--workspace`. An identifier does not open
its library by itself; the library must belong to the active workspace.

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
reset in step 2. A schema rebuild must execute inside the live ADS application.
Standalone automation does not provide application AEL functions such as
`api_create_palette_item` or
`db_add_design_opened_in_window_callback`. Messages that those functions or
their `.atf` files are unavailable do not mean those files should be manually
loaded; they mean the workspace was opened in the wrong execution context.

Open the owning workspace in ADS. Save and close the parameterized source
layout and the target RFPro view. Other RFPro views and simulations may remain
open. Then run this from the **ADS Python Console**, changing the repository
path and argument values:

```python
import runpy

runpy.run_path(
    r"/absolute/path/to/ads-rfpro-pcell-recovery/de_generated_scripts/refresh_rfpro_view.py"
)["main"]([
    "--lib", "MY_LIB",
    "--cell", "MY_CELL",
    "--design", "MY_RFPRO_VIEW",
    "--source-design", "layout",
    "--rebuild-schema",
])
```

This is the same command-line interface expressed as an argument list; library,
cell, and view names are not variables inside the script. Do not include
`--workspace`, because the workspace is already open in the live ADS process.
The standalone VS Code rebuild configurations were removed to prevent launching
the recovery in the wrong context. The included **ADS DE: Attach on port 8765**
configuration remains available when the ADS debugger is enabled.

The ADS Python Console may not provide an interactive terminal. Run once
without `--yes` to print and review the rebuild plan; if it reports that
interactive confirmation is unavailable, append `"--yes"` to the argument
list and run it again.

If an older package run already reported that re-registration changed the
schema, open the source layout first, reapply the intended definitions through
**EM > Component > Parameters...**, verify **File > Customize PCell**, save, and
close that layout. Version 1.12 saved before detecting the mismatch; version
1.13 reverted the mismatch. Version 1.14 removes PCell re-registration entirely.
Version 1.15 adds targeted recompilation and live-library reload of the
generated AEL component files before RFPro is recreated.

The script validates that the source layout is a PCell supermaster with
top-level parameters using read-only access. It does not call
`PCellInfo.make_pcell()`: that API converts a design into a PCell supermaster
and is not a registration-refresh operation. The source layout database, AEL
source text, and selected parameters are not modified. The script does replace
the source cell's generated `itemdef.atf` and `artwork.atf` after preserving
both the `.ael` and old `.atf` files in the RFPro backup. It loads
`itemdef.ael` and `artwork.ael` through ADS in the source library vocabulary,
which forces ADS to compile and register the same AEL Macro PCell code that
RFPro consumes. The script reads the layout and substrate references from the
existing RFPro view and prints the resolved substrate and its source in the
rebuild plan.

If the existing RFPro setup cannot be read, the script tries the active EM
Setup automatically. To override both, select an EM Setup explicitly:

```python
# Add these entries to the main([...]) argument list:
"--em-setup-design", "emSetup",
```

Or supply the substrate directly as a final override:

```python
# Add these entries to the main([...]) argument list:
"--substrate", "tech.subst",
```

These options are mutually exclusive. The explicit EM Setup may be on a
different cell from the parameterized source layout. In multi-design RFPro
views, the script selects the reference matching `--source-design`. If no
reference matches, it proceeds only when all RFPro references use the same
substrate; otherwise an explicit override is required.

After confirmation the script:

1. Validates the specified source PCell and locates its generated
   `itemdef.ael` and `artwork.ael` files.
2. Copies the complete existing RFPro view to
   `WORKSPACE/.rfpro-pcell-recovery/view-backups/...`.
3. Copies the generated `.ael` and existing `.atf` files into the backup's
   `source-ael/` directory and adds `rfpro-recovery-manifest.json`.
4. Transactionally recompiles and reloads only those generated files in the
   live source-library AEL vocabulary. A compile/load failure restores the old
   `.atf` files and leaves RFPro untouched.
5. Rechecks that the PCell generator and parameter list are unchanged, then
   deletes the stale RFPro view through `Cell.delete_view()`.
6. Recreates it through `create_empro_view()` and performs one final
   `update_empro_view()` call.
7. Reopens the generated RFPro setup and verifies that it contains the exact
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
- For a schema rebuild, save and close the source layout and target RFPro view;
  unrelated RFPro simulations may remain open.
- A schema rebuild replaces only the source cell's generated `itemdef.atf` and
  `artwork.atf`; their prior versions are copied into the RFPro backup first.
  It does not clear the workspace-wide `.adsPcells` directory.
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
