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
```

When the parameter schema changes, validate the backed-up rebuild path from the
live ADS Python Console with the owning workspace open:

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
loading happen on the target machine. Confirm that the rebuild output shows
identical expected entries under `Stored PCell schema before` and `Stored PCell
schema after`, then inspect RFPro's Design Parameters tree.

## API changes

Verify public `keysight.ads` APIs against the installed ADS package and Python
documentation for the release being targeted. Prefer
`from keysight.ads.de import db_uu as db` for layout database access and avoid
private APIs unless the dependency is explicitly documented.
