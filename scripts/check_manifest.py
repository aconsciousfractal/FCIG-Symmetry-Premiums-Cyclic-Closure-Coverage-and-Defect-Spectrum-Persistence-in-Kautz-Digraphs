#!/usr/bin/env python3
"""Fail-closed verification of the environment-independent source manifest."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "MANIFEST_SHA256.txt"
RELEASE_NAME = "RELEASE_SHA256.txt"
PDF_NAME = (
    "paper/Symmetry-Premiums-Cyclic-Closure-Coverage-and-Defect-Spectrum-"
    "Persistence-in-Kautz-Digraphs.pdf"
)
EXCLUDED_FROM_SOURCE = {MANIFEST_NAME, RELEASE_NAME, PDF_NAME}
REQUIRED_PATHS = {
    ".gitattributes",
    ".github/workflows/verify.yml",
    ".gitignore",
    "ACCESSIBILITY.md",
    "CITATION.cff",
    "LICENSE",
    "LICENSE_SCOPE.md",
    "README.md",
    "README_REVIEWER.md",
    "REPRODUCE.md",
    "THIRD_PARTY_NOTICES.md",
    "companion/data/bellman_bundle_metadata.json",
    "companion/data/bellman_tables.ksbellman",
    "companion/data/facet_counterexample.json",
    "companion/data/five_defect_witnesses.json",
    "companion/data/mask_memberships.jsonl.gz",
    "companion/population_kernel.py",
    "companion/verify_bellman_bundle.py",
    "companion/verify_facet_counterexample.py",
    "companion/verify_five_defect_witnesses.py",
    "companion/verify_population.py",
    "companion/verify_rank_three_obstruction.py",
    "companion/verify_ten_relation_core.py",
    "docs/PUBLIC_CLAIM_BOUNDARY.md",
    "docs/REPRODUCIBILITY_BOUNDARY.md",
    "docs/SOURCE_AND_ATTRIBUTION.md",
    "paper/latexmkrc",
    "paper/main.tex",
    "paper/references.bib",
    "requirements.lock",
    "requirements.txt",
    "scripts/check_manifest.py",
    "scripts/check_release.py",
    "scripts/git_boundary.py",
    "scripts/runtime_bootstrap.py",
    "scripts/runtime_boundary.py",
    "scripts/update_manifests.py",
    "scripts/verify.py",
    "tests/test_kautz_symmetry.py",
    "tests/test_release_assurance.py",
}
LINE_RE = re.compile(r"^([0-9a-f]{64})  ([^\x00-\x1f]+)$")


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def safe_relative(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        value == path.as_posix()
        and not path.is_absolute()
        and value not in {"", "."}
        and all(part not in {"", ".", ".."} for part in path.parts)
        and "\\" not in value
        and not value.startswith(".git/")
    )


def _is_reparse(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    flag = getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & flag)


def repository_files(root: Path = ROOT) -> set[str]:
    resolved = root.resolve(strict=True)
    if not resolved.is_dir() or resolved.is_symlink() or _is_reparse(resolved):
        raise AssertionError("repository root must be a regular directory")
    files: set[str] = set()
    pending = [resolved]
    while pending:
        directory = pending.pop()
        for entry in os.scandir(directory):
            path = Path(entry.path)
            relative = path.relative_to(resolved).as_posix()
            if relative == ".git":
                continue
            if entry.is_symlink() or _is_reparse(path):
                raise AssertionError(f"symlink or reparse point: {relative}")
            if entry.is_dir(follow_symlinks=False):
                pending.append(path)
            elif entry.is_file(follow_symlinks=False):
                if not safe_relative(relative):
                    raise AssertionError(f"unsafe repository path: {relative}")
                files.add(relative)
            else:
                raise AssertionError(f"non-regular repository entry: {relative}")
    return files


def parse_manifest(root: Path = ROOT) -> list[tuple[str, str]]:
    path = root / MANIFEST_NAME
    if not path.is_file():
        raise AssertionError("source manifest is missing")
    rows: list[tuple[str, str]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = LINE_RE.fullmatch(line)
        if match is None or not safe_relative(match.group(2)):
            raise AssertionError(f"malformed source manifest line {number}")
        rows.append((match.group(1), match.group(2)))
    paths = [relative for _, relative in rows]
    if not rows or paths != sorted(paths) or len(paths) != len(set(paths)):
        raise AssertionError("source manifest must be nonempty, sorted, and unique")
    return rows


def check_manifest(root: Path = ROOT) -> dict[str, object]:
    files = repository_files(root)
    if not EXCLUDED_FROM_SOURCE <= files:
        raise AssertionError("release surface is incomplete")
    rows = parse_manifest(root)
    declared = {relative for _, relative in rows}
    expected = files - EXCLUDED_FROM_SOURCE
    if declared != expected:
        raise AssertionError(
            f"manifest coverage drift: missing={sorted(expected-declared)}, "
            f"extra={sorted(declared-expected)}"
        )
    if not REQUIRED_PATHS <= declared:
        raise AssertionError(f"required public files missing: {sorted(REQUIRED_PATHS-declared)}")
    for expected_digest, relative in rows:
        if sha256(root / relative) != expected_digest:
            raise AssertionError(f"source hash mismatch: {relative}")
    return {
        "source_files": len(rows),
        "repository_files": len(files),
        "manifest_sha256": sha256(root / MANIFEST_NAME),
        "paths": tuple(relative for _, relative in rows),
    }


def main() -> int:
    result = check_manifest()
    print(
        "MANIFEST_PASS "
        f"sources={result['source_files']} files={result['repository_files']} "
        f"sha256={result['manifest_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
