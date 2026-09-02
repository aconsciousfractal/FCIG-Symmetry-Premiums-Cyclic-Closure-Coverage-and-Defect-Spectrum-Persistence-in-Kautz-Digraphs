"""Explicit, sanitized Git binding for release-authoritative checks.

The trust anchor is the absolute Git executable supplied to
``runtime_bootstrap.py``.  Repository identity is derived from the expected
worktree's own ``.git`` marker before Git is invoked; ambient ``GIT_*`` state
has no authority.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from runtime_boundary import (
    trusted_git_executable,
    trusted_subprocess_environment,
)


SAFE_GIT_ENVIRONMENT = {
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_TERMINAL_PROMPT": "0",
}
SAFE_GIT_KEYS = frozenset(SAFE_GIT_ENVIRONMENT)


def safe_git_environment() -> dict[str, str]:
    """Return the minimal trusted host environment plus six fixed Git keys."""

    environment = trusted_subprocess_environment()
    environment.update(SAFE_GIT_ENVIRONMENT)
    observed = {
        key.upper() for key in environment if key.upper().startswith("GIT_")
    }
    if observed != SAFE_GIT_KEYS:
        raise RuntimeError(
            f"sanitized Git environment drift: {sorted(observed)}"
        )
    return environment


def _single_path_line(path: Path, *, label: str) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ValueError(f"cannot read {label}: {error}") from error
    if len(lines) != 1 or not lines[0].strip():
        raise ValueError(f"{label} must contain exactly one nonempty line")
    return lines[0].strip()


def expected_git_repository_paths(
    *, root: Path,
) -> tuple[Path, Path, Path, Path]:
    """Resolve worktree, Git dir, common dir and object dir without Git."""

    try:
        expected_root = root.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"cannot resolve expected repository root: {error}") from error
    if not expected_root.is_dir():
        raise ValueError("expected repository root is not a directory")

    marker = expected_root / ".git"
    if marker.is_symlink():
        raise ValueError("repository .git marker must not be a symlink")
    if marker.is_dir():
        git_dir = marker.resolve(strict=True)
    elif marker.is_file():
        line = _single_path_line(marker, label="repository .git marker")
        prefix = "gitdir:"
        if not line.lower().startswith(prefix):
            raise ValueError("repository .git marker lacks gitdir prefix")
        target_text = line[len(prefix):].strip()
        if not target_text:
            raise ValueError("repository .git marker has an empty gitdir")
        target = Path(target_text)
        if not target.is_absolute():
            target = expected_root / target
        try:
            git_dir = target.resolve(strict=True)
        except OSError as error:
            raise ValueError(f"cannot resolve repository gitdir: {error}") from error
        if not git_dir.is_dir():
            raise ValueError("repository gitdir is not a directory")
    else:
        raise ValueError("expected repository has no regular .git marker")

    common_marker = git_dir / "commondir"
    if common_marker.is_symlink():
        raise ValueError("Git commondir marker must not be a symlink")
    if common_marker.exists():
        if not common_marker.is_file():
            raise ValueError("Git commondir marker is not a regular file")
        common_text = _single_path_line(
            common_marker, label="Git commondir marker",
        )
        common_target = Path(common_text)
        if not common_target.is_absolute():
            common_target = git_dir / common_target
        try:
            common_dir = common_target.resolve(strict=True)
        except OSError as error:
            raise ValueError(f"cannot resolve Git common directory: {error}") from error
        if not common_dir.is_dir():
            raise ValueError("Git common directory is not a directory")
    else:
        common_dir = git_dir

    object_dir = common_dir / "objects"
    try:
        object_dir = object_dir.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"cannot resolve Git object directory: {error}") from error
    if not object_dir.is_dir():
        raise ValueError("Git object directory is not a directory")
    return expected_root, git_dir, common_dir, object_dir


def bound_git_command(args: list[str], *, root: Path) -> list[str]:
    """Bind one trusted Git executable to the repository derived above."""

    expected_root, git_dir, _common_dir, _object_dir = (
        expected_git_repository_paths(root=root)
    )
    return [
        str(trusted_git_executable()),
        "--no-replace-objects",
        f"--git-dir={git_dir}",
        f"--work-tree={expected_root}",
        *args,
    ]


def run_git(args: list[str], *, root: Path) -> subprocess.CompletedProcess[str]:
    expected_root, _git_dir, _common_dir, _object_dir = (
        expected_git_repository_paths(root=root)
    )
    return subprocess.run(
        bound_git_command(args, root=expected_root),
        cwd=expected_root,
        env=safe_git_environment(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )


def git_repository_safety_failures(*, root: Path) -> list[str]:
    """Prove worktree/Git/common/object identities and reject rewrites."""

    failures: list[str] = []
    try:
        expected_root, expected_git_dir, expected_common_dir, expected_object_dir = (
            expected_git_repository_paths(root=root)
        )
    except ValueError as error:
        return [str(error)]

    identity_queries = (
        (["rev-parse", "--show-toplevel"], expected_root, "worktree top-level"),
        (["rev-parse", "--absolute-git-dir"], expected_git_dir, "Git directory"),
        (
            ["rev-parse", "--path-format=absolute", "--git-common-dir"],
            expected_common_dir,
            "Git common directory",
        ),
        (
            ["rev-parse", "--path-format=absolute", "--git-path", "objects"],
            expected_object_dir,
            "Git object directory",
        ),
    )
    for arguments, expected, label in identity_queries:
        observed = run_git(arguments, root=expected_root)
        if observed.returncode:
            failures.append(
                f"cannot resolve bound {label}: {observed.stderr.strip()}"
            )
            continue
        raw_path = Path(observed.stdout.strip())
        if not raw_path.is_absolute():
            raw_path = expected_root / raw_path
        try:
            resolved = raw_path.resolve(strict=True)
        except OSError as error:
            failures.append(f"cannot canonicalize bound {label}: {error}")
            continue
        if resolved != expected:
            failures.append(
                f"bound {label} mismatch: expected {expected}, observed {resolved}"
            )

    replacements = run_git(
        ["for-each-ref", "--format=%(refname)", "refs/replace/"],
        root=expected_root,
    )
    if replacements.returncode:
        failures.append(
            "cannot inspect Git replacement refs: " + replacements.stderr.strip()
        )
    elif replacements.stdout.strip():
        failures.append(
            "Git replacement refs are forbidden: "
            + ", ".join(replacements.stdout.splitlines())
        )

    graft_path = expected_common_dir / "info" / "grafts"
    if os.path.lexists(graft_path):
        failures.append("Git info/grafts is forbidden for release validation")
    alternates_path = expected_object_dir / "info" / "alternates"
    if os.path.lexists(alternates_path):
        failures.append(
            "Git objects/info/alternates is forbidden for release validation"
        )
    return failures


def ensure_git_repository_safety(*, root: Path) -> None:
    failures = git_repository_safety_failures(root=root)
    if failures:
        raise AssertionError("; ".join(failures))


def git_output(root: Path, *arguments: str) -> str:
    result = run_git(list(arguments), root=root)
    if result.returncode:
        diagnostic = (result.stderr or result.stdout).strip()
        raise AssertionError(
            f"Git command failed ({' '.join(arguments)}): {diagnostic}"
        )
    return result.stdout.strip()
