# Changelog

All notable changes to this project are documented here.

## 1.12.0 - 2026-08-16

- Re-register only the specified source PCell supermaster, using its existing
  public `PCellInfo`, before RFPro serializes its generated cache.
- Preserve the existing AEL evaluator and selected artwork arguments while
  refreshing the in-process PCell registration.
- Print item-definition, selected-artwork, and stored PCell parameter schemas
  so an empty RFPro tree cannot be mistaken for a healthy source handoff.
- Verify that the rebuilt RFPro setup contains the exact requested source
  layout and substrate pair before reporting completion.
- Keep the targeted registration step ahead of RFPro backup and replacement;
  failures leave the existing RFPro view untouched.

## 1.11.0 - 2026-08-16

- Read the substrate automatically from the existing RFPro view through the
  public `EmproSetup.design_refs` API.
- Match multi-design RFPro references to `--source-design`; refuse ambiguous
  conflicting substrates instead of guessing.
- Retain active EM Setup discovery as a fallback and keep `--substrate` and
  `--em-setup-design` as explicit overrides.
- Record and display the substrate source before replacing the RFPro view.

## 1.10.0 - 2026-08-16

- Add `--lib` (`--library`) and `--cell` defaults to both production scripts.
- Allow design inputs as `VIEW`, `CELL:VIEW`, or `LIB:CELL:VIEW`, filling only
  omitted fields from the defaults.
- Allow `--substrate NAME` to reuse `--lib`, while retaining
  `--substrate LIB:NAME`.
- Update VS Code launch configurations to prompt once for library and cell.

## 1.9.0 - 2026-08-16

- Add `--em-setup-design "LIB:CELL:VIEW"` so a rebuild can use an EM Setup
  that is not active on the parameterized source layout.
- Add `--substrate "LIB:SUBSTRATE"` to bypass EM Setup discovery when the
  existing RFPro substrate is already known.
- Fail before backing up or replacing the RFPro view when automatic EM Setup
  discovery fails, with commands for both supported fallbacks.
- Make targeted refresh/rebuild the default documented workflow and identify
  `.adsPcells` reset as a workspace-wide last resort.

## 1.8.0 - 2026-08-16

- Separate value-only refreshes from destructive PCell parameter-schema
  rebuilds.
- Add `--rebuild-schema` with required `--source-design` input.
- Validate the source layout's top-level PCell parameters before changing the
  RFPro view.
- Discover the active EM Setup and substrate through public EM Tools APIs.
- Preserve the complete existing RFPro view and a JSON manifest before using
  the public ADS delete/create APIs.
- Print ADS and EM Tools versions in every refresh run.

## 1.7.0 - 2026-08-15

- Automatically locate `libemViewsPlugin.so` on Linux before importing ADS EM
  Tools.
- Add a one-time process-local loader restart for standalone execution.
- Preload the native library without replacing a live ADS process.
- Report unresolved native dependencies using `ldd` output.

## 1.6.0 - 2026-08-14

- Replace separate library, cell, and view arguments with the required
  `--design "library:cell:view"` interface.
- Add workspace and open-library validation before accessing a cellview.

## 1.5.0 - 2026-08-14

- Move design identification from variables inside the scripts to command-line
  arguments.
- Retain optional standalone workspace opening through `--workspace`.

## 1.4.0 - 2026-08-14

- Integrate automatic cross-platform Qt platform-plugin discovery into both
  production scripts.
- Preserve and restore the pre-existing Qt environment when creating a script-
  owned application.
