# Contributing

## Development setup

1. Open the repository root in VS Code.
2. Install the recommended **ADS Python Utilities** and Python extensions.
3. Use **ADS Python Utilities: Configure Python Interpreter Path** to select the
   interpreter bundled with the ADS release you intend to test.
4. Keep standalone ADS scripts in `de_generated_scripts/` and support tools in
   `scripts/`.

Do not add PySide6 or `keysight.ads` as PyPI requirements. They must come from
the target ADS installation so the Python bindings and native libraries remain
release-compatible.

## Validation

Before committing, run the VS Code task **Repo: static checks**. On the target
ADS machine, also validate:

```bash
python de_generated_scripts/diagnose_pcell_parameters.py \
  --lib "MY_LIB" --cell "MY_CELL" \
  --design "layout" \
  --workspace "/path/to/workspace_wrk"

python de_generated_scripts/refresh_rfpro_view.py \
  --lib "MY_LIB" --cell "MY_CELL" \
  --design "MY_RFPRO_VIEW" \
  --workspace "/path/to/workspace_wrk"

python scripts/inspect_adspcells_cache.py \
  --workspace "/path/to/workspace_wrk" \
  --source-design "MY_LIB:MY_CELL:layout" \
  --rfpro-design "MY_LIB:MY_CELL:MY_RFPRO_VIEW"
```

For generated-artwork or parameter-schema changes, validate the targeted
single-cell path from the live ADS Python Console:

```python
import runpy

runpy.run_path(
    r"/path/to/de_generated_scripts/refresh_rfpro_view.py"
)["main"]([
    "--lib", "MY_LIB", "--cell", "MY_CELL",
    "--design", "MY_RFPRO_VIEW",
    "--source-design", "layout",
    "--recompile-source-ael",
])
```

Confirm that it rejects an RFPro view pointing at an alias LCV, backs up the
source layout and both generated AEL files, and leaves the RFPro view itself in
place. Test both a no-op check and an intentionally changed parameter schema.
For the changed schema, verify that it prints both AEL reports, saves only the
specified source supermaster, reopens it read-only, and records the before/after
names in `source-update-manifest.json`. Force a failed validation and confirm
that the source is reverted before RFPro is updated. When `.adsPcells` exists,
confirm that it reports the exact cache path and does not claim the same-value
geometry was evicted.
The cache inspector must remain read-only. Validate exact/component matching,
large-file skip reporting, and the changed-during-scan warning with disposable
fixtures; never validate deletion against a working ADS cache.

With the affected view active, validate the importable runtime helper from the
RFPro/EMPro Python Console:

```python
import sys

sys.path.insert(0, r"C:\path\to\ads-rfpro-pcell-recovery")
from rfpro_pcell_recovery import refresh_active_rfpro_layout

print(refresh_active_rfpro_layout())
```

Confirm that it returns after RFPro repopulates the active layout's parameter
collection. Also confirm that an unavailable project, unavailable layout, or
empty result at timeout raises a descriptive exception. This is not a geometry
cache-eviction test: restored parameter names and old artwork behavior are
distinct outcomes.

If an in-place source synchronization does not populate the existing RFPro
view, validate the backed-up RFPro recreation fallback from the live ADS Python
Console with the owning workspace open:

```python
import runpy

runpy.run_path(
    r"/path/to/de_generated_scripts/refresh_rfpro_view.py"
)["main"]([
    "--lib", "MY_LIB", "--cell", "MY_CELL",
    "--design", "MY_RFPRO_VIEW",
    "--source-design", "layout",
    "--rebuild-schema",
])
```

Save and close the source layout and target RFPro view before running a schema
rebuild. Other RFPro simulations may remain open. Runtime success cannot be
established by syntax compilation alone because Qt and ADS native-library
loading happen on the target machine. Confirm that the rebuild plan lists the
expected source parameters and generated `itemdef.ael`/`artwork.ael` files.
Confirm that ADS reports successful targeted AEL recompilation and single-cell
`de_update_pcell_parameters()` synchronization before it recreates RFPro, then
inspect RFPro's Design Parameters tree.
Confirm that the rebuilt RFPro `DesignRef` still points to the exact original
source `LIBRARY:CELL:VIEW`. Do not add a source alias as a cache workaround;
that loses the component context needed to render the layout.

## API changes

Verify public `keysight.ads` APIs against the installed ADS package and Python
documentation for the release being targeted. Prefer
`from keysight.ads.de import db_uu as db` for layout database access and avoid
private APIs unless the dependency is explicitly documented.
