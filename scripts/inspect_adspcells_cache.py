"""Inspect an ADS workspace PCell cache without modifying it.

The .adsPcells format is not part of the public ADS Python API. This utility
therefore performs a conservative, read-only inventory. It searches paths and
file contents for exact source-layout and RFPro LCV identifiers and reports
whether files changed while they were being scanned. It never recommends or
performs deletion.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class Identity:
    label: str
    lcv: tuple[str, str, str]

    @property
    def text(self) -> str:
        return ":".join(self.lcv)


@dataclass
class ScanResult:
    path: Path
    size: int
    modified: str
    magic: str
    exact_matches: set[str]
    component_matches: dict[str, set[str]]
    changed_during_scan: bool
    error: str | None = None


def _lcv_argument(value: str) -> tuple[str, str, str]:
    parts = value.split(":")
    if len(parts) != 3 or not all(parts):
        raise argparse.ArgumentTypeError(
            f"expected LIB:CELL:VIEW, received {value!r}"
        )
    return parts[0], parts[1], parts[2]


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only inventory of .adsPcells records associated with one "
            "source layout and RFPro view."
        )
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="ADS workspace containing de_sim.cfg and .adsPcells",
    )
    parser.add_argument(
        "--source-design",
        type=_lcv_argument,
        required=True,
        metavar="LIB:CELL:VIEW",
        help="original parameterized layout LCV",
    )
    parser.add_argument(
        "--rfpro-design",
        type=_lcv_argument,
        required=True,
        metavar="LIB:CELL:VIEW",
        help="affected RFPro view LCV",
    )
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="also print every cache file, including files with no identifier match",
    )
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=512 * 1024 * 1024,
        help="skip content scanning above this size; use 0 for no limit",
    )
    arguments = parser.parse_args()
    if arguments.max_file_bytes < 0:
        parser.error("--max-file-bytes must be zero or positive")
    return arguments


def _exact_text_forms(identity: Identity) -> set[str]:
    library, cell, view = identity.lcv
    return {
        f"{library}:{cell}:{view}",
        f"{library}::{cell}::{view}",
        f"{library}:::{cell}:::{view}",
        f"{library}/{cell}/{view}",
        f"{library}\\{cell}\\{view}",
    }


def _encoded_patterns(text: str) -> set[bytes]:
    return {
        text.encode("utf-8"),
        text.encode("utf-16-le"),
        text.encode("utf-16-be"),
    }


def _identity_patterns(
    identities: list[Identity],
) -> tuple[dict[bytes, set[tuple[str, str]]], int]:
    patterns: dict[bytes, set[tuple[str, str]]] = {}
    maximum_length = 1
    for identity in identities:
        for text in _exact_text_forms(identity):
            for pattern in _encoded_patterns(text):
                patterns.setdefault(pattern, set()).add(
                    (identity.label, "exact")
                )
                maximum_length = max(maximum_length, len(pattern))
        for component_name, text in zip(
            ("library", "cell", "view"), identity.lcv
        ):
            for pattern in _encoded_patterns(text):
                patterns.setdefault(pattern, set()).add(
                    (identity.label, component_name)
                )
                maximum_length = max(maximum_length, len(pattern))
    return patterns, maximum_length


def _scan_file(
    path: Path,
    cache_root: Path,
    identities: list[Identity],
    patterns: dict[bytes, set[tuple[str, str]]],
    maximum_pattern_length: int,
    max_file_bytes: int,
) -> ScanResult:
    relative = path.relative_to(cache_root)
    before = path.stat()
    modified = datetime.fromtimestamp(before.st_mtime).astimezone().isoformat()
    exact_matches: set[str] = set()
    component_matches = {identity.label: set() for identity in identities}

    relative_text = relative.as_posix()
    for identity in identities:
        if any(form in relative_text for form in _exact_text_forms(identity)):
            exact_matches.add(identity.label)
        for component_name, value in zip(
            ("library", "cell", "view"), identity.lcv
        ):
            if value in relative_text:
                component_matches[identity.label].add(component_name)

    magic = ""
    if max_file_bytes and before.st_size > max_file_bytes:
        return ScanResult(
            path=relative,
            size=before.st_size,
            modified=modified,
            magic=magic,
            exact_matches=exact_matches,
            component_matches=component_matches,
            changed_during_scan=False,
            error=(
                f"content scan skipped: size exceeds --max-file-bytes "
                f"({max_file_bytes})"
            ),
        )

    overlap = max(0, maximum_pattern_length - 1)
    tail = b""
    try:
        with path.open("rb") as stream:
            first = stream.read(min(_CHUNK_SIZE, before.st_size))
            magic = first[:16].hex()
            chunk = first
            while chunk:
                data = tail + chunk
                for pattern, signals in patterns.items():
                    if pattern not in data:
                        continue
                    for label, match_kind in signals:
                        if match_kind == "exact":
                            exact_matches.add(label)
                        else:
                            component_matches[label].add(match_kind)
                tail = data[-overlap:] if overlap else b""
                chunk = stream.read(_CHUNK_SIZE)
    except OSError as error:
        return ScanResult(
            path=relative,
            size=before.st_size,
            modified=modified,
            magic=magic,
            exact_matches=exact_matches,
            component_matches=component_matches,
            changed_during_scan=False,
            error=f"content scan failed: {error}",
        )

    after = path.stat()
    changed = (
        after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
    )
    return ScanResult(
        path=relative,
        size=after.st_size,
        modified=modified,
        magic=magic,
        exact_matches=exact_matches,
        component_matches=component_matches,
        changed_during_scan=changed,
    )


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{size} B"


def _print_result(result: ScanResult) -> None:
    signals: list[str] = []
    if result.exact_matches:
        signals.append("exact=" + ",".join(sorted(result.exact_matches)))
    for label, components in result.component_matches.items():
        if components:
            signals.append(
                f"{label}-components=" + ",".join(sorted(components))
            )
    if result.changed_during_scan:
        signals.append("CHANGED_DURING_SCAN")
    if result.error:
        signals.append(result.error)
    signal_text = "; ".join(signals) if signals else "no identifier match"
    print(f"  {result.path}")
    print(
        f"    size={_format_size(result.size)} modified={result.modified} "
        f"magic={result.magic or '(empty)'}"
    )
    print(f"    signals={signal_text}")


def main() -> None:
    arguments = _parse_arguments()
    workspace = arguments.workspace.expanduser().resolve()
    if not workspace.is_dir() or not (workspace / "de_sim.cfg").is_file():
        raise SystemExit(
            f"Not an ADS workspace containing de_sim.cfg: {workspace}"
        )

    cache_root = workspace / ".adsPcells"
    if not cache_root.is_dir():
        raise SystemExit(f"No .adsPcells directory exists: {cache_root}")

    identities = [
        Identity("source", arguments.source_design),
        Identity("rfpro", arguments.rfpro_design),
    ]
    patterns, maximum_pattern_length = _identity_patterns(identities)
    paths = sorted(
        path
        for path in cache_root.rglob("*")
        if path.is_file() and not path.is_symlink()
    )

    print("Read-only ADS PCell cache inventory")
    print(f"  Workspace: {workspace}")
    print(f"  Cache: {cache_root}")
    print(f"  Source: {identities[0].text}")
    print(f"  RFPro: {identities[1].text}")
    print(f"  Files: {len(paths)}")

    results: list[ScanResult] = []
    for path in paths:
        try:
            result = _scan_file(
                path,
                cache_root,
                identities,
                patterns,
                maximum_pattern_length,
                arguments.max_file_bytes,
            )
        except OSError as error:
            relative = path.relative_to(cache_root)
            result = ScanResult(
                path=relative,
                size=0,
                modified="unknown",
                magic="",
                exact_matches=set(),
                component_matches={identity.label: set() for identity in identities},
                changed_during_scan=False,
                error=f"metadata scan failed: {error}",
            )
        results.append(result)

    exact = [result for result in results if result.exact_matches]
    component_candidates = [
        result
        for result in results
        if not result.exact_matches
        and any(
            len(components) >= 2
            for components in result.component_matches.values()
        )
    ]
    unstable = [result for result in results if result.changed_during_scan]
    errors = [result for result in results if result.error]

    print(f"Exact-LCV matching files: {len(exact)}")
    for result in exact:
        _print_result(result)
    print(f"Component-only candidate files: {len(component_candidates)}")
    for result in component_candidates:
        _print_result(result)

    if arguments.inventory:
        printed = {result.path for result in exact + component_candidates}
        print("Remaining cache files:")
        for result in results:
            if result.path not in printed:
                _print_result(result)

    print("Scan summary:")
    print(f"  total_files={len(results)}")
    print(f"  exact_lcv_files={len(exact)}")
    print(f"  component_candidate_files={len(component_candidates)}")
    print(f"  changed_during_scan={len(unstable)}")
    print(f"  scan_errors_or_skips={len(errors)}")
    print(
        "RESULT: Nothing was modified. Do not delete any reported file. "
        "Provide this complete output before attempting targeted eviction."
    )


if __name__ == "__main__":
    main()
