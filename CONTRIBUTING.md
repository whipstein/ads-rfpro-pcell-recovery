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

When the parameter schema changes, also validate the backed-up rebuild path:

```bash
python de_generated_scripts/refresh_rfpro_view.py \
  --lib "MY_LIB" --cell "MY_CELL" \
  --design "MY_RFPRO_VIEW" \
  --source-design "layout" \
  --rebuild-schema \
  --workspace "/path/to/workspace_wrk"
```

Close RFPro before running the refresh. Runtime success cannot be established
by syntax compilation alone because Qt and ADS native-library loading happen on
the target machine. Confirm that the rebuild output shows identical expected
parameter names under `Stored PCell parameters after`, then inspect RFPro's
Design Parameters tree.

## API changes

Verify public `keysight.ads` APIs against the installed ADS package and Python
documentation for the release being targeted. Prefer
`from keysight.ads.de import db_uu as db` for layout database access and avoid
private APIs unless the dependency is explicitly documented.
