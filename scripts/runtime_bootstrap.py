"""Start a verifier inside an explicit, recorded Python/Git trust boundary.

Invoke this file with an absolute Python executable and ``-I -S -B``. It uses
only the standard library until the interpreter, Git executable and installed
dependency distributions have been identified. It then clears ambient
Python/Git state, constructs a minimal PATH, exposes a hash-bound runtime
context to child verifiers and executes one repository target.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import runpy
import stat
import subprocess
import sys
import sysconfig
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(os.path.abspath(os.fspath(Path(__file__)))).parents[1]
CONTEXT_KEY = "FCIG_HJELMSLEV_TRUSTED_RUNTIME_CONTEXT"
PRESERVED_KEYS = {
    "COMSPEC", "LANG", "LC_ALL", "LC_CTYPE", "PATHEXT", "SYSTEMROOT",
    "TEMP", "TMP", "TMPDIR", "TZ", "WINDIR", "SOURCE_DATE_EPOCH",
    "FORCE_SOURCE_DATE", "FCIG_HJELMSLEV_ISOLATED_REPLAY",
}
DEPENDENCIES = {
    "numpy": "2.5.1",
    "pypdf": "6.14.2",
    "sympy": "1.14.0",
    "mpmath": "1.3.0",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def distribution_identity(name: str, expected_version: str | None) -> dict:
    distribution = importlib.metadata.distribution(name)
    version = distribution.version
    if expected_version is not None and version != expected_version:
        raise SystemExit(
            f"FAIL trusted runtime: {name} version {version}, "
            f"expected {expected_version}"
        )
    rows = []
    files = distribution.files
    if not files:
        raise SystemExit(f"FAIL trusted runtime: {name} has no installed file list")
    for relative in sorted(files, key=lambda item: item.as_posix()):
        path = Path(distribution.locate_file(relative)).resolve(strict=True)
        if path.is_symlink() or not path.is_file():
            raise SystemExit(
                f"FAIL trusted runtime: non-regular distribution file {path}"
            )
        rows.append(
            f"{relative.as_posix()}\0{path.stat().st_size}\0{sha256(path)}\n"
        )
    content_sha256 = hashlib.sha256("".join(rows).encode("utf-8")).hexdigest()
    metadata_path = Path(distribution._path).resolve(strict=True)
    return {
        "name": name,
        "version": version,
        "metadata_path": str(metadata_path),
        "files": len(rows),
        "content_sha256": content_sha256,
    }


def minimal_environment(
    original: dict[str, str], *, python_executable: Path, git_executable: Path,
    context: dict,
) -> dict[str, str]:
    environment = {
        key: value
        for key, value in original.items()
        if key.upper() in PRESERVED_KEYS
    }
    system_root = environment.get("SYSTEMROOT") or environment.get("WINDIR")
    path_parts = [str(python_executable.parent), str(git_executable.parent)]
    if system_root:
        path_parts.append(str(Path(system_root) / "System32"))
    environment["PATH"] = os.pathsep.join(dict.fromkeys(path_parts))
    environment[CONTEXT_KEY] = json.dumps(
        context, sort_keys=True, separators=(",", ":"),
    )
    return environment


def write_transcript(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )


def main() -> None:
    try:
        root_stat = os.lstat(ROOT)
    except OSError as error:
        raise SystemExit(
            f"FAIL trusted runtime: cannot inspect repository root: {error}"
        ) from error
    if (
        stat.S_ISLNK(root_stat.st_mode)
        or getattr(root_stat, "st_file_attributes", 0) & 0x0400
    ):
        raise SystemExit(
            "FAIL trusted runtime: repository root cannot be a reparse point"
        )

    parser = argparse.ArgumentParser()
    parser.add_argument("--git-executable", required=True, type=Path)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--module")
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("target_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if bool(args.target) == bool(args.module):
        raise SystemExit("FAIL trusted runtime: select exactly one target or module")
    if args.target_args[:1] == ["--"]:
        args.target_args = args.target_args[1:]

    required_flags = {
        "isolated": sys.flags.isolated,
        "ignore_environment": sys.flags.ignore_environment,
        "no_site": sys.flags.no_site,
        "safe_path": sys.flags.safe_path,
    }
    if any(value != 1 for value in required_flags.values()):
        raise SystemExit(
            "FAIL trusted runtime: invoke absolute python with -I -S -B; "
            + json.dumps(required_flags, sort_keys=True)
        )

    python_executable = Path(sys.executable).resolve(strict=True)
    git_executable = args.git_executable
    if not git_executable.is_absolute():
        raise SystemExit("FAIL trusted runtime: Git executable must be absolute")
    git_executable = git_executable.resolve(strict=True)
    if not git_executable.is_file() or git_executable.is_symlink():
        raise SystemExit("FAIL trusted runtime: Git executable is not a regular file")

    purelib = Path(sysconfig.get_path("purelib")).resolve(strict=True)
    if not purelib.is_dir():
        raise SystemExit("FAIL trusted runtime: Python purelib is unavailable")
    sys.path.append(str(purelib))
    dependencies = {
        name: distribution_identity(name, version)
        for name, version in DEPENDENCIES.items()
    }

    original_environment = dict(os.environ)
    removed_keys = sorted(
        key for key in original_environment
        if key.upper().startswith(("PYTHON", "GIT_"))
    )
    provisional_context = {
        "schema": "fcig_hjelmslev_trusted_runtime_v1",
        "python": {
            "executable": str(python_executable),
            "sha256": sha256(python_executable),
            "version": sys.version,
            "flags": required_flags,
            "purelib": str(purelib),
        },
        "git": {
            "executable": str(git_executable),
            "sha256": sha256(git_executable),
        },
        "dependencies": dependencies,
    }
    clean_environment = minimal_environment(
        original_environment,
        python_executable=python_executable,
        git_executable=git_executable,
        context=provisional_context,
    )
    git_version = subprocess.run(
        [str(git_executable), "--version"],
        cwd=ROOT,
        env=clean_environment,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if git_version.returncode:
        raise SystemExit(
            "FAIL trusted runtime: absolute Git executable failed: "
            + git_version.stderr.strip()
        )
    provisional_context["git"]["version"] = git_version.stdout.strip()
    clean_environment = minimal_environment(
        original_environment,
        python_executable=python_executable,
        git_executable=git_executable,
        context=provisional_context,
    )
    os.environ.clear()
    os.environ.update(clean_environment)

    scripts = (ROOT / "scripts").resolve(strict=True)
    sys.path.insert(0, str(scripts))
    target_label: str
    if args.target:
        target = args.target
        if not target.is_absolute():
            target = ROOT / target
        target = target.resolve(strict=True)
        try:
            target.relative_to(ROOT)
        except ValueError as exc:
            raise SystemExit(
                "FAIL trusted runtime: target lies outside the package"
            ) from exc
        if target.suffix.lower() != ".py" or not target.is_file():
            raise SystemExit("FAIL trusted runtime: target must be a Python file")
        target_label = target.relative_to(ROOT).as_posix()
        target_sha256 = sha256(target)
    else:
        target = None
        target_label = f"module:{args.module}"
        target_sha256 = None

    transcript = {
        "schema": "fcig_hjelmslev_runtime_execution_transcript_v1",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": provisional_context,
        "ambient_python_git_keys_removed": removed_keys,
        "sanitized_path": os.environ["PATH"],
        "target": target_label,
        "target_sha256": target_sha256,
        "arguments": args.target_args,
        "status": "RUNNING",
        "exit_code": None,
    }
    exit_code = 0
    try:
        sys.argv = [target_label, *args.target_args]
        if target is not None:
            runpy.run_path(str(target), run_name="__main__")
        else:
            runpy.run_module(args.module, run_name="__main__", alter_sys=True)
    except SystemExit as exc:
        if exc.code is None:
            exit_code = 0
        elif isinstance(exc.code, int):
            exit_code = exc.code
        else:
            print(exc.code, file=sys.stderr)
            exit_code = 1
    except BaseException:
        exit_code = 1
        raise
    finally:
        transcript["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        transcript["exit_code"] = exit_code
        transcript["status"] = "PASS" if exit_code == 0 else "FAIL"
        if args.transcript:
            write_transcript(args.transcript.resolve(), transcript)
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
