from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pypdf.generic import DictionaryObject, NameObject


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_manifest  # noqa: E402
import check_release  # noqa: E402
import runtime_bootstrap  # noqa: E402


def test_manifest_and_release_surface() -> None:
    source = check_manifest.check_manifest()
    release = check_release.check_release()
    assert source["source_files"] >= 35
    assert release["pdf"]["pages"] >= 10


@pytest.mark.parametrize(
    "path, expected",
    [
        ("paper/main.tex", True),
        ("../paper/main.tex", False),
        ("/paper/main.tex", False),
        ("paper\\main.tex", False),
        (".git/config", False),
    ],
)
def test_manifest_path_boundary(path: str, expected: bool) -> None:
    assert check_manifest.safe_relative(path) is expected


def test_lfs_pointer_and_absolute_paths_rejected() -> None:
    with pytest.raises(AssertionError):
        check_release.scan_private(
            "mutation", b"version https://git-lfs.github.com/spec/v1\n",
        )
    separator = chr(92)
    windows_path = (
        "C" + ":" + separator + "private-workspace" + separator + "artifact"
    ).encode("ascii")
    with pytest.raises(AssertionError):
        check_release.scan_private("mutation", windows_path)
    unix_path = ("/" + "root" + "/private-workspace/artifact").encode("ascii")
    with pytest.raises(AssertionError):
        check_release.scan_private("mutation", unix_path)
    with pytest.raises(AssertionError):
        check_release.check_hygiene({"reports/staging.txt"})


def test_active_pdf_dictionary_rejected() -> None:
    active = DictionaryObject({NameObject("/JavaScript"): DictionaryObject()})
    with pytest.raises(AssertionError):
        check_release.walk_pdf(active, set())


def test_bootstrap_and_lock_have_exact_dependency_parity(tmp_path: Path) -> None:
    assert runtime_bootstrap.require_lock_parity() == runtime_bootstrap.DEPENDENCIES
    drift = tmp_path / "requirements.lock"
    drift.write_text(
        "pytest==0.0.0 \\\n"
        "    --hash=sha256:" + "0" * 64 + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="dependency drift"):
        runtime_bootstrap.require_lock_parity(drift)


def test_runtime_boundary_contains_no_foreign_project_identifiers() -> None:
    combined = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8").lower()
        for relative in ("scripts/runtime_bootstrap.py", "scripts/runtime_boundary.py")
    )
    assert "hjelmslev" not in combined
    for undeclared in ("numpy", "sympy", "mpmath"):
        assert undeclared not in combined
