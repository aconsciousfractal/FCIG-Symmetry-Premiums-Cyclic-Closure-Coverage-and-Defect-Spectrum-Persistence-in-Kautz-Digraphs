"""Helpers shared by verifiers running under ``runtime_bootstrap.py``."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_REL = "scripts/runtime_bootstrap.py"
CONTEXT_KEY = "FCIG_HJELMSLEV_TRUSTED_RUNTIME_CONTEXT"
BASE_ENVIRONMENT_KEYS = {
    "COMSPEC", "LANG", "LC_ALL", "LC_CTYPE", "PATH", "PATHEXT",
    "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "TZ", "WINDIR",
    "SOURCE_DATE_EPOCH", "FORCE_SOURCE_DATE",
    "FCIG_HJELMSLEV_ISOLATED_REPLAY",
    CONTEXT_KEY,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def trusted_runtime_context() -> dict:
    required_flags = (
        sys.flags.isolated, sys.flags.ignore_environment,
        sys.flags.no_site, sys.flags.safe_path,
    )
    if required_flags != (1, 1, 1, 1):
        raise RuntimeError(
            "release-authoritative verification requires absolute Python "
            "with -I -S -B through scripts/runtime_bootstrap.py"
        )
    raw = os.environ.get(CONTEXT_KEY)
    if not raw:
        raise RuntimeError("trusted runtime context is missing")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError("trusted runtime context is invalid JSON") from exc
    if data.get("schema") != "fcig_hjelmslev_trusted_runtime_v1":
        raise RuntimeError("trusted runtime context has the wrong schema")

    python = data.get("python", {})
    executable = Path(sys.executable).resolve(strict=True)
    if (
        python.get("executable") != str(executable)
        or python.get("sha256") != sha256(executable)
    ):
        raise RuntimeError("Python executable identity does not match runtime context")
    git = data.get("git", {})
    git_path = Path(git.get("executable", ""))
    if (
        not git_path.is_absolute()
        or not git_path.is_file()
        or git_path.is_symlink()
        or git.get("sha256") != sha256(git_path)
    ):
        raise RuntimeError("Git executable identity does not match runtime context")
    return data


def require_trusted_runtime() -> None:
    trusted_runtime_context()


def trusted_git_executable() -> Path:
    return Path(trusted_runtime_context()["git"]["executable"])


def trusted_subprocess_environment(
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    require_trusted_runtime()
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in BASE_ENVIRONMENT_KEYS
    }
    if extra:
        environment.update({key: str(value) for key, value in extra.items()})
    return environment


def isolated_python_command(
    target: Path | str,
    args: list[str] | tuple[str, ...] = (),
    *,
    package_root: Path = ROOT,
    optimize: int | None = None,
) -> list[str]:
    context = trusted_runtime_context()
    root = package_root.resolve(strict=True)
    bootstrap = (root / BOOTSTRAP_REL).resolve(strict=True)
    target_path = Path(target)
    if not target_path.is_absolute():
        target_path = root / target_path
    target_path = target_path.resolve(strict=True)
    command = [context["python"]["executable"], "-I", "-S", "-B"]
    level = sys.flags.optimize if optimize is None else optimize
    if level:
        command.append("-" + "O" * level)
    command.extend([
        str(bootstrap),
        "--git-executable", context["git"]["executable"],
        "--target", str(target_path),
        "--",
        *args,
    ])
    return command


def isolated_python_module_command(
    module: str,
    args: list[str] | tuple[str, ...] = (),
    *,
    package_root: Path = ROOT,
    optimize: int | None = None,
) -> list[str]:
    context = trusted_runtime_context()
    root = package_root.resolve(strict=True)
    bootstrap = (root / BOOTSTRAP_REL).resolve(strict=True)
    command = [context["python"]["executable"], "-I", "-S", "-B"]
    level = sys.flags.optimize if optimize is None else optimize
    if level:
        command.append("-" + "O" * level)
    command.extend([
        str(bootstrap),
        "--git-executable", context["git"]["executable"],
        "--module", module,
        "--",
        *args,
    ])
    return command


def isolated_portable_python_command(
    portable: list[str] | tuple[str, ...],
    *,
    package_root: Path = ROOT,
) -> list[str]:
    if not portable or portable[0].lower() not in {"python", "python3"}:
        raise ValueError("portable command must begin with python")
    tokens = list(portable[1:])
    optimize = 0
    cursor = 0
    while cursor < len(tokens):
        token = tokens[cursor]
        if token == "-B":
            cursor += 1
        elif token in {"-O", "-OO"}:
            optimize = len(token) - 1
            cursor += 1
        elif token == "-X":
            if cursor + 1 >= len(tokens):
                raise ValueError("portable -X option lacks its value")
            cursor += 2
        else:
            break
    remaining = tokens[cursor:]
    if not remaining:
        raise ValueError("portable command lacks a target")
    if remaining[0] == "-m":
        if len(remaining) < 2:
            raise ValueError("portable module command lacks its module")
        return isolated_python_module_command(
            remaining[1], remaining[2:],
            package_root=package_root, optimize=optimize,
        )
    if remaining[0].startswith("-"):
        raise ValueError(f"unsupported portable Python option: {remaining[0]}")
    return isolated_python_command(
        remaining[0], remaining[1:],
        package_root=package_root, optimize=optimize,
    )


def trusted_git_command(args: list[str] | tuple[str, ...]) -> list[str]:
    return [str(trusted_git_executable()), *args]


def neutralized_runtime_command(
    command: list[str] | tuple[str, ...], *, package_root: Path = ROOT,
) -> list[str]:
    """Return a portable record of an exact trusted-runtime invocation.

    Executable and checkout identities remain bound separately by hashes.  A
    detached receipt must not disclose author-machine paths merely to show how
    the target was launched.
    """
    context = trusted_runtime_context()
    python_executable = str(Path(context["python"]["executable"]).resolve())
    git_executable = str(Path(context["git"]["executable"]).resolve())
    root = package_root.resolve(strict=True)
    neutralized = []
    for token in command:
        if token == python_executable:
            neutralized.append("<ABSOLUTE_PYTHON>")
            continue
        if token == git_executable:
            neutralized.append("<ABSOLUTE_GIT>")
            continue
        candidate = Path(token)
        if candidate.is_absolute():
            try:
                neutralized.append(candidate.resolve().relative_to(root).as_posix())
            except (OSError, ValueError):
                neutralized.append("<ABSOLUTE_EXTERNAL_PATH>")
            continue
        neutralized.append(token.replace("\\", "/"))
    return neutralized


def runtime_public_identity() -> dict:
    context = trusted_runtime_context()
    python = {
        **context["python"],
        "executable": "<ABSOLUTE_PYTHON>",
        "purelib": "<PYTHON_PURELIB>",
    }
    git = {
        **context["git"],
        "executable": "<ABSOLUTE_GIT>",
    }
    dependencies = {}
    for name, record in context["dependencies"].items():
        public_record = {
            key: value for key, value in record.items() if key != "metadata_path"
        }
        public_record["metadata_locator"] = (
            "<PYTHON_PURELIB>/" + Path(record["metadata_path"]).name
        )
        dependencies[name] = public_record
    return {
        "path_policy": (
            "Machine-local paths are neutralized; executable and dependency "
            "content identities remain hash-bound."
        ),
        "python": python,
        "git": git,
        "dependencies": dependencies,
        "bootstrap": {
            "path": BOOTSTRAP_REL,
            "sha256": sha256(ROOT / BOOTSTRAP_REL),
        },
    }
