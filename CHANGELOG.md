# Changelog

All notable changes to this project are documented here.

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
