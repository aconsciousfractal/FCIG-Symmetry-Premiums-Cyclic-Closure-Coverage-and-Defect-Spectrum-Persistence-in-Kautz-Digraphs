#!/usr/bin/env python3
"""Reconstruct the complete six-letter maximum-mask population.

The shipped membership table is opened only after a label-independent replay
with the quotient-native population kernel.  Agreement is therefore a
post-hoc exact-set check, not an enumeration oracle.  The replay reuses the
published kernel and is not represented as a second implementation.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
COMPANION = ROOT / "companion"
if str(COMPANION) not in sys.path:
    sys.path.insert(0, str(COMPANION))

import population_kernel as kernel


TRACKED_MASK_ROWS = ROOT / "companion/data/mask_memberships.jsonl.gz"
EXPECTED_REPRESENTATIVE_DIGEST = (
    "615926170123e3a5e1cf455ca6e595c8abc2a07c678861c1053d0162d8c6cac9"
)
EXPECTED_LABELLED_DIGEST = (
    "d19f1930b48b69dbda7b92f7c0b80da950f760161a5d288f6552016708725044"
)
EXPECTED_SOURCE_AUDIT = {
    "raw_source_triples": 46656,
    "source_orbits": 987,
    "orbit_size_histogram": {"16": 9, "24": 18, "48": 960},
    "stabilizer_order_histogram": {"1": 960, "2": 18, "3": 9},
    "maximum_representative": 7213,
    "representatives_sha256": (
        "07cb699b43938c4c31df976bcff8b1ec44211fd1fec4b2080086f3006de97815"
    ),
    "partition_sha256": (
        "f1677cfc3697711eff83489247c009146ab5b50a781ec1498582c6cab76d8ab1"
    ),
    "group_sha256": (
        "b853a0f7adec2ab9b2b7b077743597aed8058452aa26b59c0cd9b16125c223c3"
    ),
    "bit_actions_sha256": (
        "a6e6d790b63435720ee8b1f993ff4a04be95d104f377efe3273229352012cda1"
    ),
}


class PopulationAuditError(RuntimeError):
    """Fail-closed population-enumeration or custody error."""


def need(condition: bool, code: str) -> None:
    if not condition:
        raise PopulationAuditError(code)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def mask_set_sha256(masks: Iterable[int]) -> str:
    digest = hashlib.sha256()
    for mask in sorted(masks):
        digest.update(f"{mask:019x}\n".encode("ascii"))
    return digest.hexdigest()


def _expected_structural_zero_words() -> set[tuple[int, int, int]]:
    return {
        word
        for orbit_index in kernel.partition_audit()["forced_zero_internal_indices"]
        for word in kernel.target_orbits()[orbit_index]
    }


def enumerate_population() -> dict[str, Any]:
    """Enumerate quotient representatives, then expand the full labelled set."""

    source_audit = kernel.source_orbit_audit()
    for key, expected in EXPECTED_SOURCE_AUDIT.items():
        need(source_audit.get(key) == expected, f"SOURCE_AUDIT:{key}")

    representative_masks: set[int] = set()
    source_representatives_with_masks = 0
    labelled_source_triples_with_masks = 0
    search_nodes = 0
    expected_zero_words = _expected_structural_zero_words()

    for record in kernel.source_orbit_records():
        base = kernel.base_masks()[record.representative]
        search_nodes += 1
        local_masks: set[int] = set()
        if kernel.is_dag(6, kernel.selected_words(base, kernel.target_orbits())):
            stack: list[tuple[int, tuple[int, ...], int]] = [(0, (), base)]
            while stack:
                depth, code, mask = stack.pop()
                search_nodes += 1
                need(
                    search_nodes <= kernel.UNPRUNED_TARGET_NODE_CEILING,
                    "SEARCH_NODE_CEILING",
                )
                if depth == kernel.TRIANGLE_DEPTH and not kernel.is_canonical_leaf(
                    record.representative, code
                ):
                    continue
                if not kernel.is_dag(
                    6, kernel.selected_words(mask, kernel.target_orbits())
                ):
                    continue
                if depth == kernel.TRIANGLE_DEPTH:
                    need(
                        mask.bit_count() == kernel.TARGET_SELECTED_ORBITS,
                        "REPRESENTATIVE_MASK_WEIGHT",
                    )
                    witness = kernel.antisymmetric_maximal_witness(
                        6,
                        kernel.TARGET_SIGMA,
                        kernel.selected_words(mask, kernel.target_orbits()),
                        expected_maximum_arcs=kernel.TARGET_MAXIMUM_ARCS,
                    )
                    need(
                        {tuple(word) for word in witness["zero_words"]}
                        == expected_zero_words,
                        "NONSTRUCTURAL_ZERO_GAP",
                    )
                    need(mask not in local_masks, "LOCAL_REPRESENTATIVE_DUPLICATE")
                    local_masks.add(mask)
                    continue
                for omitted in reversed(range(3)):
                    stack.append(
                        (
                            depth + 1,
                            code + (omitted,),
                            mask | kernel.triangle_addition(depth, omitted),
                        )
                    )

        if local_masks:
            source_representatives_with_masks += 1
            labelled_source_triples_with_masks += len(record.members)
        need(
            representative_masks.isdisjoint(local_masks),
            "GLOBAL_REPRESENTATIVE_DUPLICATE",
        )
        representative_masks.update(local_masks)

    need(search_nodes == 54078, "SEARCH_NODE_COUNT")
    need(source_representatives_with_masks == 417, "SOURCE_REPRESENTATIVES_WITH_MASKS")
    need(labelled_source_triples_with_masks == 19624, "LABELLED_SOURCE_TRIPLES_WITH_MASKS")
    need(len(representative_masks) == 1759, "REPRESENTATIVE_MASK_COUNT")
    representative_digest = mask_set_sha256(representative_masks)
    need(
        representative_digest == EXPECTED_REPRESENTATIVE_DIGEST,
        f"REPRESENTATIVE_MASK_DIGEST:{representative_digest}",
    )

    labelled_masks: set[int] = set()
    orbit_size_histogram: Counter[str] = Counter()
    actions = kernel.orbit_bit_actions()
    for mask in representative_masks:
        orbit = {kernel.transform_mask(mask, action) for action in actions}
        need(len(orbit) in (24, 48), "LABELLED_MASK_ORBIT_SIZE")
        orbit_size_histogram[str(len(orbit))] += 1
        need(labelled_masks.isdisjoint(orbit), "LABELLED_ORBIT_OVERLAP")
        labelled_masks.update(orbit)

    need(dict(sorted(orbit_size_histogram.items())) == {"24": 29, "48": 1730}, "LABELLED_ORBIT_HISTOGRAM")
    need(len(labelled_masks) == 83736, "LABELLED_MASK_COUNT")
    need(all(mask.bit_count() == 43 for mask in labelled_masks), "LABELLED_MASK_WEIGHT")
    labelled_digest = mask_set_sha256(labelled_masks)
    need(
        labelled_digest == EXPECTED_LABELLED_DIGEST,
        f"LABELLED_MASK_DIGEST:{labelled_digest}",
    )
    return {
        "source_audit": source_audit,
        "search_nodes": search_nodes,
        "source_representatives_with_masks": source_representatives_with_masks,
        "labelled_source_triples_with_masks": labelled_source_triples_with_masks,
        "representative_masks": representative_masks,
        "representative_masks_sha256": representative_digest,
        "labelled_masks": labelled_masks,
        "labelled_masks_sha256": labelled_digest,
        "labelled_orbit_size_histogram": dict(sorted(orbit_size_histogram.items())),
    }


def read_tracked_mask_keys(
    path: Path,
    *,
    expected_count: int = 83736,
) -> set[int]:
    """Read a tracked comparison set; this function never drives enumeration."""

    need(path.is_file(), "TRACKED_MASK_ROWS_MISSING")
    masks: set[int] = set()
    with gzip.open(path, "rb") as stream:
        for number, raw in enumerate(stream, 1):
            need(raw.endswith(b"\n"), f"TRACKED_LINE_END:{number}")
            try:
                row = json.loads(raw)
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise PopulationAuditError(f"TRACKED_JSON:{number}") from exc
            need(
                isinstance(row, dict) and canonical_bytes(row) == raw,
                f"TRACKED_CANONICAL:{number}",
            )
            key = row.get("mask_key")
            need(
                isinstance(key, str)
                and len(key) == 19
                and key == key.lower()
                and all(character in "0123456789abcdef" for character in key),
                f"TRACKED_MASK_KEY:{number}",
            )
            mask = int(key, 16)
            need(mask < (1 << 75) and mask.bit_count() == 43, f"TRACKED_MASK_DOMAIN:{number}")
            need(mask not in masks, f"TRACKED_MASK_DUPLICATE:{number}")
            masks.add(mask)
    need(len(masks) == expected_count, "TRACKED_MASK_COUNT")
    return masks


def build_summary(population: dict[str, Any], tracked_masks: set[int]) -> dict[str, Any]:
    need(tracked_masks == population["labelled_masks"], "TRACKED_MASK_SET_MISMATCH")
    summary: dict[str, Any] = {
        "schema": "kautz-symmetry-population-replay-v1",
        "coordinate": {"m": 3, "f": 0, "q": 6, "involution": "(01)(23)(45)"},
        "method": {
            "standard_library_only": True,
            "label_independent_reconstruction": True,
            "published_population_kernel_reused": True,
            "second_kernel_implementation": False,
            "stored_population_used_as_enumeration_input": False,
            "tracked_population_opened_only_after_enumeration": True,
        },
        "source": {
            "q4_local_states": kernel.PAIR_STATE_RADIX,
            "raw_source_triples": kernel.RAW_SOURCE_TRIPLES,
            "source_orbits": kernel.SOURCE_ORBITS,
            "centralizer_order": len(kernel.centralizer_group()),
            "source_representatives_with_masks": population[
                "source_representatives_with_masks"
            ],
            "labelled_source_triples_with_masks": population[
                "labelled_source_triples_with_masks"
            ],
        },
        "enumeration": {
            "search_nodes": population["search_nodes"],
            "representative_masks": len(population["representative_masks"]),
            "representative_masks_sha256": population[
                "representative_masks_sha256"
            ],
            "labelled_masks": len(population["labelled_masks"]),
            "labelled_masks_sha256": population["labelled_masks_sha256"],
            "labelled_orbit_size_histogram": population[
                "labelled_orbit_size_histogram"
            ],
            "mask_bits": 75,
            "selected_orbits_per_mask": 43,
            "selected_arcs_per_mask": 86,
        },
        "posthoc_comparison": {
            "path": TRACKED_MASK_ROWS.relative_to(ROOT).as_posix(),
            "tracked_masks": len(tracked_masks),
            "tracked_masks_sha256": mask_set_sha256(tracked_masks),
            "exact_set_equality": True,
        },
        "status": "PASS",
    }
    return {**summary, "canonical_sha256": canonical_sha256(summary)}


def audit(
    *,
    tracked_path: Path = TRACKED_MASK_ROWS,
) -> dict[str, Any]:
    # Order matters: enumerate first, inspect the shipped comparison set second.
    population = enumerate_population()
    tracked_masks = read_tracked_mask_keys(tracked_path)
    return build_summary(population, tracked_masks)


def main() -> int:
    try:
        receipt = audit()
    except (OSError, PopulationAuditError, kernel.PopulationKernelError) as exc:
        print(f"POPULATION_REPLAY_FAIL {exc}", file=sys.stderr)
        return 1
    enumeration = receipt["enumeration"]
    source = receipt["source"]
    print(
        "POPULATION_REPLAY_PASS "
        f"q4_states={source['q4_local_states']} "
        f"source_triples={source['raw_source_triples']} "
        f"source_orbits={source['source_orbits']} "
        f"search_nodes={enumeration['search_nodes']} "
        f"representative_masks={enumeration['representative_masks']} "
        f"labelled_masks={enumeration['labelled_masks']} "
        f"digest={enumeration['labelled_masks_sha256']} tracked_equal=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
