#!/usr/bin/env python3
"""Fail-closed verification of the public repository and committed PDF."""

from __future__ import annotations

import gzip
import re
import zipfile
from pathlib import Path
from typing import Any

from check_manifest import (
    MANIFEST_NAME,
    PDF_NAME,
    RELEASE_NAME,
    ROOT,
    check_manifest,
    repository_files,
    safe_relative,
    sha256,
)
from git_boundary import ensure_git_repository_safety, git_output


PUBLIC_URL = (
    "https://github.com/aconsciousfractal/FCIG-Symmetry-Premiums-Cyclic-"
    "Closure-Coverage-and-Defect-Spectrum-Persistence-in-Kautz-Digraphs"
)
PDF_TITLE = (
    "Symmetry premiums, cyclic-closure coverage, and defect-spectrum "
    "persistence in Kautz digraphs"
)
TEXT_SUFFIXES = {
    ".py", ".md", ".tex", ".bib", ".cff", ".txt", ".yml", ".yaml",
    ".json", ".lock", "",
}
PRIVATE_MARKERS = (
    "P" + "63",
    "M" + "R3",
    "D" + "S1",
    "K4_U_" + "RS",
    "paper_" + "projects",
    "G:" + "\\Repositories\\HAN",
    "/root/" + "papp",
)
LFS_PREFIX = b"version https://git-lfs.github.com/spec/v1"
RELEASE_RE = re.compile(r"^([0-9a-f]{64})  ([^\x00-\x1f]+)$")


def need(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def parse_release() -> list[tuple[str, str]]:
    path = ROOT / RELEASE_NAME
    need(path.is_file(), "release manifest is missing")
    rows: list[tuple[str, str]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = RELEASE_RE.fullmatch(line)
        need(match is not None, f"malformed release manifest line {number}")
        relative = match.group(2)
        need(safe_relative(relative), f"unsafe release path: {relative}")
        rows.append((match.group(1), relative))
    paths = [relative for _, relative in rows]
    need(paths == sorted(paths) and len(paths) == len(set(paths)), "release manifest order")
    need(set(paths) == {MANIFEST_NAME, PDF_NAME}, "release manifest surface")
    for digest, relative in rows:
        need(sha256(ROOT / relative) == digest, f"release hash mismatch: {relative}")
    return rows


def scan_private(label: str, payload: bytes) -> None:
    lowered = payload.lower()
    for marker in PRIVATE_MARKERS:
        need(marker.lower().encode("utf-8") not in lowered, f"private marker in {label}: {marker}")
    need(LFS_PREFIX not in payload[:256], f"LFS pointer in {label}")


def check_hygiene(files: set[str]) -> dict[str, int]:
    text_files = 0
    for relative in sorted(files):
        path = ROOT / relative
        payload = path.read_bytes()
        need(not payload.startswith(LFS_PREFIX), f"LFS pointer: {relative}")
        suffix = path.suffix.lower()
        if relative == "LICENSE" or suffix in TEXT_SUFFIXES:
            text_files += 1
            try:
                payload.decode("utf-8")
            except UnicodeDecodeError as error:
                raise AssertionError(f"non-UTF-8 public text: {relative}") from error
            scan_private(relative, payload)
    membership = gzip.decompress((ROOT / "companion/data/mask_memberships.jsonl.gz").read_bytes())
    scan_private("decompressed mask memberships", membership)
    with zipfile.ZipFile(ROOT / "companion/data/bellman_tables.ksbellman") as archive:
        names = archive.namelist()
        need(len(names) == 3519 and len(names) == len(set(names)), "bundle member census")
        scan_private("bundle member names", "\n".join(names).encode("utf-8"))
        for name in names:
            payload = archive.read(name)
            if name.endswith(".json") or len(payload) < 512:
                scan_private(f"bundle member {name}", payload)
    return {"text_files": text_files, "bundle_members": 3519}


def dereference(value: Any) -> Any:
    getter = getattr(value, "get_object", None)
    return getter() if getter is not None else value


def walk_pdf(value: Any, seen: set[tuple[int, int]]) -> None:
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

    if isinstance(value, IndirectObject):
        key = (value.idnum, value.generation)
        if key in seen:
            return
        seen.add(key)
        walk_pdf(value.get_object(), seen)
        return
    if isinstance(value, DictionaryObject):
        keys = {str(key) for key in value.keys()}
        forbidden = keys & {
            "/AA", "/JavaScript", "/JS", "/Launch",
            "/EmbeddedFiles", "/AcroForm", "/XFA", "/RichMedia",
        }
        need(not forbidden, f"forbidden PDF key: {sorted(forbidden)}")
        subtype = str(value.get("/Subtype", ""))
        need(subtype not in {"/FileAttachment", "/Movie", "/Sound", "/Screen", "/3D", "/Widget"}, f"forbidden PDF subtype: {subtype}")
        action = str(value.get("/S", ""))
        need(action not in {"/JavaScript", "/Launch", "/GoToR", "/SubmitForm", "/ImportData"}, f"forbidden PDF action: {action}")
        if action == "/URI":
            uri = str(value.get("/URI", ""))
            need(uri.startswith(("https://", "http://", "mailto:")), f"unsafe PDF URI: {uri}")
        for child in value.values():
            walk_pdf(child, seen)
    elif isinstance(value, ArrayObject):
        for child in value:
            walk_pdf(child, seen)


def embedded_font_count(reader: Any) -> int:
    count = 0
    checked: set[str] = set()
    for page in reader.pages:
        resources = dereference(page.get("/Resources", {}))
        fonts = dereference(resources.get("/Font", {})) if resources else {}
        for name, reference in fonts.items():
            font = dereference(reference)
            identity = str(getattr(reference, "idnum", name)) + str(font.get("/BaseFont", ""))
            if identity in checked:
                continue
            checked.add(identity)
            subtype = str(font.get("/Subtype", ""))
            if subtype == "/Type3":
                count += 1
                continue
            if subtype == "/Type0":
                descendants = dereference(font.get("/DescendantFonts", []))
                need(bool(descendants), f"Type0 font lacks descendants: {name}")
                font = dereference(descendants[0])
            descriptor = dereference(font.get("/FontDescriptor"))
            need(descriptor is not None, f"font descriptor missing: {name}")
            need(any(key in descriptor for key in ("/FontFile", "/FontFile2", "/FontFile3")), f"unembedded font: {name}")
            count += 1
    need(count > 0, "PDF has no checked fonts")
    return count


def check_pdf() -> dict[str, object]:
    from pypdf import PdfReader

    path = ROOT / PDF_NAME
    payload = path.read_bytes()
    need(payload.startswith(b"%PDF-"), "missing PDF header")
    need(payload.rstrip().endswith(b"%%EOF"), "missing terminal PDF EOF")
    need(payload.count(b"%%EOF") == 1, "multiple PDF EOF markers")
    scan_private(PDF_NAME, payload)
    reader = PdfReader(str(path), strict=True)
    need(not reader.is_encrypted, "encrypted PDF")
    need(len(reader.pages) >= 10, "unexpectedly short manuscript")
    root = dereference(reader.trailer["/Root"])
    need(str(root.get("/Lang", "")) == "en-US", "PDF language must be en-US")
    need("/EmbeddedFiles" not in dereference(root.get("/Names", {})), "PDF attachments")
    if "/OpenAction" in root:
        action = dereference(root["/OpenAction"])
        need(
            isinstance(action, dict)
            and str(action.get("/S", "")) == "/GoTo"
            and "/D" in action,
            "unsafe PDF OpenAction",
        )
    walk_pdf(root, set())
    for number, page in enumerate(reader.pages, 1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        need(abs(width - 595.276) < 1.0 and abs(height - 841.890) < 1.0, f"non-A4 page {number}")
    metadata = reader.metadata or {}
    need(str(metadata.get("/Title", "")) == PDF_TITLE, "PDF title metadata")
    need(str(metadata.get("/Author", "")) == "Oleksiy Babanskyy", "PDF author metadata")
    keywords = str(metadata.get("/Keywords", ""))
    need("Kautz digraphs" in keywords and "defect spectrum" in keywords, "PDF keyword metadata")
    page_texts = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(page_texts)
    normalized = re.sub(r"\s+", " ", text)
    compact = re.sub(r"\s+", "", text)
    for phrase in (
        "Symmetry premiums, cyclic-closure coverage",
        "Oleksiy Babanskyy",
        "Keywords:",
        "MSC 2020:",
        "no claim of bibliographic priority or source completeness",
    ):
        need(phrase in normalized, f"PDF visible text missing: {phrase}")
    need(re.sub(r"\s+", "", PUBLIC_URL) in compact, "PDF repository URL")
    scan_private("PDF extracted text", text.encode("utf-8"))
    fonts = embedded_font_count(reader)
    return {"pages": len(reader.pages), "fonts": fonts, "sha256": sha256(path)}


def check_metadata() -> None:
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    for marker in (
        'title: "Symmetry Premiums, Cyclic-Closure Coverage, and Defect-Spectrum Persistence in Kautz Digraphs"',
        'version: "1.0.0"',
        'given-names: Oleksiy',
        'family-names: Babanskyy',
        f'repository-code: "{PUBLIC_URL}"',
    ):
        need(marker in citation, f"CITATION metadata missing: {marker}")


def check_git(files: set[str]) -> dict[str, str]:
    ensure_git_repository_safety(root=ROOT)
    top = Path(git_output(ROOT, "rev-parse", "--show-toplevel")).resolve(strict=True)
    need(top == ROOT.resolve(strict=True), "repository root is not Git top-level")
    need(not git_output(ROOT, "status", "--porcelain=v1", "--untracked-files=all"), "dirty checkout")
    tracked_raw = git_output(ROOT, "ls-files", "-z")
    tracked = {item for item in tracked_raw.split("\0") if item}
    need(tracked == files, f"tracked path drift: missing={sorted(files-tracked)}, extra={sorted(tracked-files)}")
    need(git_output(ROOT, "fsck", "--full", "--no-dangling").strip() == "", "Git object connectivity")
    for relative in sorted(files):
        worktree_hash = git_output(ROOT, "hash-object", "--", relative)
        tree_hash = git_output(ROOT, "rev-parse", f"HEAD:{relative}")
        need(worktree_hash == tree_hash, f"HEAD/worktree blob drift: {relative}")
    for relative in (PDF_NAME, "companion/data/mask_memberships.jsonl.gz", "companion/data/bellman_tables.ksbellman"):
        attributes = git_output(ROOT, "check-attr", "filter", "diff", "merge", "--", relative)
        need("filter: unset" in attributes, f"active filter on binary: {relative}")
        need("diff: unset" in attributes and "merge: unset" in attributes, f"binary attributes drift: {relative}")
    return {
        "head": git_output(ROOT, "rev-parse", "HEAD"),
        "tree": git_output(ROOT, "rev-parse", "HEAD^{tree}"),
    }


def check_release() -> dict[str, object]:
    source = check_manifest()
    parse_release()
    files = repository_files(ROOT)
    hygiene = check_hygiene(files)
    check_metadata()
    pdf = check_pdf()
    git = check_git(files)
    return {"source": source, "hygiene": hygiene, "pdf": pdf, "git": git}


def main() -> int:
    result = check_release()
    print(
        "RELEASE_PASS "
        f"files={result['source']['repository_files']} "
        f"pages={result['pdf']['pages']} fonts={result['pdf']['fonts']} "
        f"head={result['git']['head']} pdf={result['pdf']['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
