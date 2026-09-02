#!/usr/bin/env python3
"""Regenerate the closed source and release SHA-256 manifests."""

from __future__ import annotations

from pathlib import Path

from check_manifest import (
    EXCLUDED_FROM_SOURCE,
    MANIFEST_NAME,
    PDF_NAME,
    RELEASE_NAME,
    ROOT,
    repository_files,
    sha256,
)


def write_manifest(path: Path, rows: list[tuple[str, str]]) -> None:
    path.write_text(
        "".join(f"{digest}  {relative}\n" for digest, relative in rows),
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    files = repository_files(ROOT)
    if PDF_NAME not in files:
        raise SystemExit(f"cannot update manifests; missing={PDF_NAME}")
    sources = sorted(files - EXCLUDED_FROM_SOURCE)
    write_manifest(
        ROOT / MANIFEST_NAME,
        [(sha256(ROOT / relative), relative) for relative in sources],
    )
    release_paths = sorted((MANIFEST_NAME, PDF_NAME))
    write_manifest(
        ROOT / RELEASE_NAME,
        [(sha256(ROOT / relative), relative) for relative in release_paths],
    )
    print(
        f"MANIFESTS_UPDATED sources={len(sources)} "
        f"manifest={sha256(ROOT / MANIFEST_NAME)} pdf={sha256(ROOT / PDF_NAME)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
