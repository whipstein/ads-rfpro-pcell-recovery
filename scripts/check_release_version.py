"""Verify that distributable release labels agree with VERSION."""

from __future__ import annotations

import re
from pathlib import Path


_ROOT = Path(__file__).resolve().parent.parent


def _require_match(path: Path, pattern: str, label: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(pattern, text, flags=re.MULTILINE)
    if match is None:
        raise RuntimeError(f"Could not find {label} in {path}.")
    return match.group(1)


def main() -> None:
    version = (_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if re.fullmatch(r"\d+\.\d+\.\d+", version) is None:
        raise RuntimeError(f"VERSION is not a semantic release: {version!r}.")

    readme_version = _require_match(
        _ROOT / "README.md",
        r"^Current release: \*\*(\d+\.\d+\.\d+)\*\*\.",
        "the current release label",
    )
    changelog_version = _require_match(
        _ROOT / "CHANGELOG.md",
        r"^## (\d+\.\d+\.\d+) - \d{4}-\d{2}-\d{2}$",
        "the newest changelog release",
    )
    mismatches = {
        "README.md": readme_version,
        "CHANGELOG.md": changelog_version,
    }
    incorrect = {
        name: found for name, found in mismatches.items() if found != version
    }
    if incorrect:
        details = ", ".join(
            f"{name}={found}" for name, found in incorrect.items()
        )
        raise RuntimeError(f"Release version mismatch: VERSION={version}, {details}.")

    print(f"Release version labels agree: {version}")


if __name__ == "__main__":
    main()
