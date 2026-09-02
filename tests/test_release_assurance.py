from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pypdf.generic import DictionaryObject, NameObject


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_manifest  # noqa: E402
import check_release  # noqa: E402


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


def test_lfs_pointer_and_private_marker_rejected() -> None:
    with pytest.raises(AssertionError):
        check_release.scan_private(
            "mutation", b"version https://git-lfs.github.com/spec/v1\n",
        )
    private = ("P" + "63").encode("ascii")
    with pytest.raises(AssertionError):
        check_release.scan_private("mutation", private)


def test_active_pdf_dictionary_rejected() -> None:
    active = DictionaryObject({NameObject("/JavaScript"): DictionaryObject()})
    with pytest.raises(AssertionError):
        check_release.walk_pdf(active, set())
