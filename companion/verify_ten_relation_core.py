#!/usr/bin/env python3
"""Discover and certify the ten-relation four-defect core.

The ten-relation core is tested on every reconstructed work orbit before any
stored defect label is consulted.  The resulting 24 work classes are then
proved to have exact defect four by combining the human lower-bound lemma with
explicit topological orders checked directly from the Bellman bundle.
"""

from __future__ import annotations

import functools
import gzip
import hashlib
import itertools
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
MASK_ROWS = ROOT / "companion/data/mask_memberships.jsonl.gz"
BUNDLE = ROOT / "companion/data/bellman_tables.ksbellman"

EXPECTED = {
    "masks": (MASK_ROWS, 3_065_801, "e5c8c617c2bd9d9205d536c02274855cfba6192e3c8aacb92cbbc0cb5969dd09"),
    "bundle": (BUNDLE, 15_203_390, "c4695820ffc1b84606d9f006edd4f66c77028b6823e6b2f780ffc3bdf1a9b2fa"),
}
SIGMA = (1, 0, 3, 2, 5, 4)
CLOSURE_MAGIC = b"KSCLOS1\x00"
HEX = frozenset("0123456789abcdef")
WORK_PREFIX = b"kautz-symmetry-work-v1\x00"

# A relation ((a,b),(c,d)) means that predecessor vertex ab precedes cd.
CORE = (
    ((0, 2), (1, 0)),
    ((1, 0), (2, 1)),
    ((0, 3), (1, 0)),
    ((1, 0), (3, 1)),
    ((4, 0), (5, 4)),
    ((5, 4), (1, 5)),
    ((4, 1), (0, 5)),
    ((2, 4), (3, 2)),
    ((3, 2), (5, 3)),
    ((2, 5), (4, 3)),
)
CELLS = {
    "T:012:-": (((0, 2), (2, 1)), ((2, 1), (1, 0)), ((1, 0), (0, 2))),
    "T:013:-": (((0, 3), (3, 1)), ((3, 1), (1, 0)), ((1, 0), (0, 3))),
    "T:045:-": (((0, 5), (5, 4)), ((5, 4), (4, 0)), ((4, 0), (0, 5))),
    "T:145:-": (((1, 5), (5, 4)), ((5, 4), (4, 1)), ((4, 1), (1, 5))),
    "T:234:-": (((2, 4), (4, 3)), ((4, 3), (3, 2)), ((3, 2), (2, 4))),
    "T:235:-": (((2, 5), (5, 3)), ((5, 3), (3, 2)), ((3, 2), (2, 5))),
}
COMPONENTS = (
    (CORE[:4], ("T:012:-", "T:013:-")),
    (CORE[4:7], ("T:045:-", "T:145:-")),
    (CORE[7:], ("T:234:-", "T:235:-")),
)


class TenRelationVerificationError(RuntimeError):
    """Fail-closed portable occurrence or order-certificate error."""


def need(condition: bool, code: str) -> None:
    if not condition:
        raise TenRelationVerificationError(code)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_path(name: str) -> Path:
    path, size, digest = EXPECTED[name]
    need(path.is_file(), f"INPUT_MISSING:{name}")
    need(path.stat().st_size == size, f"INPUT_BYTES:{name}")
    need(sha256_path(path) == digest, f"INPUT_SHA256:{name}")
    return path


def vertices() -> tuple[tuple[int, int], ...]:
    return tuple((x, y) for x in range(6) for y in range(6) if x != y)


@functools.lru_cache(maxsize=1)
def word_orbits() -> tuple[tuple[tuple[int, int, int], ...], ...]:
    words = (
        (x, y, z)
        for x in range(6)
        for y in range(6)
        for z in range(6)
        if x != y and y != z
    )

    def rho(word: tuple[int, int, int]) -> tuple[int, int, int]:
        x, y, z = word
        return SIGMA[z], SIGMA[y], SIGMA[x]

    result = tuple(sorted({tuple(sorted((word, rho(word)))) for word in words}))
    need(len(result) == 75 and all(len(orbit) == 2 for orbit in result), "WORD_ORBITS")
    return result


@functools.lru_cache(maxsize=1)
def centralizer() -> tuple[tuple[int, ...], ...]:
    result = tuple(
        action
        for action in itertools.permutations(range(6))
        if all(action[SIGMA[x]] == SIGMA[action[x]] for x in range(6))
    )
    need(len(result) == 48 and result[0] == tuple(range(6)), "CENTRALIZER")
    return result


def encode_reach(reach: Sequence[int]) -> bytes:
    need(len(reach) == 30, "ENCODE_DIMENSION")
    body = bytearray((30 * 30 + 7) // 8)
    for source, targets in enumerate(reach):
        pending = targets
        while pending:
            bit = pending & -pending
            pending ^= bit
            target = bit.bit_length() - 1
            position = source * 30 + target
            body[position // 8] |= 1 << (7 - position % 8)
    return CLOSURE_MAGIC + bytes((6, 30)) + bytes(body)


def closure_from_mask(mask_key: str) -> tuple[int, ...]:
    need(
        isinstance(mask_key, str)
        and len(mask_key) == 19
        and set(mask_key) <= HEX,
        "MASK_KEY",
    )
    mask = int(mask_key, 16)
    need(mask < 1 << 75 and mask.bit_count() == 43, "MASK_WEIGHT")
    verts = vertices()
    index = {vertex: position for position, vertex in enumerate(verts)}
    reach = [0] * 30
    for orbit_index, orbit in enumerate(word_orbits()):
        if not mask & (1 << orbit_index):
            continue
        for x, y, z in orbit:
            reach[index[x, y]] |= 1 << index[y, z]
    for pivot in range(30):
        pivot_bit = 1 << pivot
        for source in range(30):
            if reach[source] & pivot_bit:
                reach[source] |= reach[pivot]
    need(all(not targets & (1 << source) for source, targets in enumerate(reach)), "MASK_DAG")
    return tuple(reach)


def transform_reach(reach: Sequence[int], action: Sequence[int]) -> tuple[int, ...]:
    verts = vertices()
    index = {vertex: position for position, vertex in enumerate(verts)}
    transformed = [0] * 30
    for source, targets in enumerate(reach):
        left = verts[source]
        new_source = index[action[left[0]], action[left[1]]]
        pending = targets
        while pending:
            bit = pending & -pending
            pending ^= bit
            right = verts[bit.bit_length() - 1]
            transformed[new_source] |= 1 << index[action[right[0]], action[right[1]]]
    return tuple(transformed)


def canonical_work_id(reach: Sequence[int]) -> str:
    canonical = canonical_closure(reach)
    return hashlib.sha256(WORK_PREFIX + canonical).hexdigest()


def canonical_closure(reach: Sequence[int]) -> bytes:
    return min(encode_reach(transform_reach(reach, action)) for action in centralizer())


def relation_mask(reach: Sequence[int], action: Sequence[int]) -> int:
    index = {vertex: position for position, vertex in enumerate(vertices())}
    result = 0
    for number, ((a, b), (c, d)) in enumerate(CORE):
        left = index[action[a], action[b]]
        right = index[action[c], action[d]]
        if reach[left] & (1 << right):
            result |= 1 << number
    return result


def read_masks() -> tuple[dict[str, str], Counter[str]]:
    path = checked_path("masks")
    expected_keys = {
        "labelled_multiplicity",
        "mask_key",
        "s3_orbit_signature",
        "signature",
        "work_id",
    }
    counts: Counter[str] = Counter()
    representatives: dict[str, str] = {}
    seen: set[str] = set()
    with gzip.open(path, "rb") as stream:
        for number, raw in enumerate(stream, 1):
            need(raw.endswith(b"\n"), f"MASK_NEWLINE:{number}")
            row = json.loads(raw)
            need(isinstance(row, dict) and set(row) == expected_keys, f"MASK_KEYS:{number}")
            need(canonical_bytes(row) == raw, f"MASK_CANONICAL:{number}")
            work_id = row["work_id"]
            mask_key = row["mask_key"]
            need(
                isinstance(work_id, str)
                and len(work_id) == 64
                and set(work_id) <= HEX,
                f"MASK_WORK:{number}",
            )
            need(row["labelled_multiplicity"] == 1, f"MASK_MULTIPLICITY:{number}")
            need(
                isinstance(mask_key, str)
                and len(mask_key) == 19
                and set(mask_key) <= HEX
                and mask_key not in seen,
                f"MASK_ID:{number}",
            )
            value = int(mask_key, 16)
            need(value < 1 << 75 and value.bit_count() == 43, f"MASK_WEIGHT:{number}")
            seen.add(mask_key)
            counts[work_id] += 1
            representatives.setdefault(work_id, mask_key)
    need(len(seen) == 83_736, "MASK_COUNT")
    need(len(representatives) == 1_759, "REPRESENTATIVE_COUNT")
    need(
        Counter(counts.values()) == Counter({24: 29, 48: 1_730}),
        "MASK_ORBIT_SIZE_HISTOGRAM",
    )
    return representatives, counts


def read_covered_masks(covered: set[str]) -> list[tuple[str, str]]:
    """Select members only after the core has discovered the covered works."""

    path = checked_path("masks")
    result: list[tuple[str, str]] = []
    with gzip.open(path, "rb") as stream:
        for number, raw in enumerate(stream, 1):
            row = json.loads(raw)
            if row["work_id"] in covered:
                need(row["s3_orbit_signature"] == [0, 0, 0], f"COVERED_SIGNATURE:{number}")
                result.append((row["mask_key"], row["work_id"]))
    need(len(result) == 1_152, "COVERED_MASK_COUNT")
    return result


def minimum_bad(
    relations: Sequence[tuple[tuple[int, int], tuple[int, int]]],
    cell_keys: Sequence[str],
) -> int:
    local_vertices = sorted(
        {vertex for relation in relations for vertex in relation}
        | {
            vertex
            for key in cell_keys
            for comparison in CELLS[key]
            for vertex in comparison
        }
    )
    optimum = 99
    for order in itertools.permutations(local_vertices):
        position = {vertex: index for index, vertex in enumerate(order)}
        if any(position[left] >= position[right] for left, right in relations):
            continue
        bad = sum(
            sum(position[left] < position[right] for left, right in CELLS[key]) == 1
            for key in cell_keys
        )
        optimum = min(optimum, bad)
    need(optimum < 99, "ORDER_EXTENSION")
    return optimum


def verify_human_core() -> tuple[int, tuple[int, ...]]:
    minima: list[int] = []
    for relations, cell_keys in COMPONENTS:
        optimum = minimum_bad(relations, cell_keys)
        minima.append(optimum)
        for index in range(len(relations)):
            reduced = relations[:index] + relations[index + 1 :]
            need(minimum_bad(reduced, cell_keys) < optimum, "CORE_COMPONENT_MINIMALITY")
    need(minima == [2, 1, 1], "CORE_TWO_PLUS_ONE_PLUS_ONE")
    return sum(minima), tuple(minima)


def relation_text(relation: tuple[tuple[int, int], tuple[int, int]]) -> str:
    (a, b), (c, d) = relation
    return f"{a}{b}<{c}{d}"


def decode_closure(data: bytes) -> tuple[int, ...]:
    need(data[:10] == CLOSURE_MAGIC + bytes((6, 30)), "BUNDLE_CLOSURE_HEADER")
    payload = data[10:]
    need(len(payload) == (30 * 30 + 7) // 8, "BUNDLE_CLOSURE_LENGTH")
    reach = [0] * 30
    for source in range(30):
        for target in range(30):
            position = source * 30 + target
            if payload[position // 8] & (1 << (7 - position % 8)):
                reach[source] |= 1 << target
    need(all(not targets & (1 << source) for source, targets in enumerate(reach)), "BUNDLE_CLOSURE_LOOP")
    return tuple(reach)


def read_bundle_orders() -> dict[str, tuple[bytes, object, object]]:
    """Read only closures and explicit orders; stored defect labels are ignored."""

    path = checked_path("bundle")
    result: dict[str, tuple[bytes, object, object]] = {}
    with zipfile.ZipFile(path, "r") as bundle:
        need(bundle.testzip() is None and "works.jsonl" in bundle.namelist(), "BUNDLE_CONTAINER")
        raw_rows = bundle.read("works.jsonl").splitlines(keepends=True)
    for number, raw in enumerate(raw_rows, 1):
        need(raw.endswith(b"\n"), f"BUNDLE_ROW_NEWLINE:{number}")
        row = json.loads(raw)
        need(
            isinstance(row, dict)
            and set(row) == {"closure_hex", "prefix_result", "suffix_result", "work_id"}
            and canonical_bytes(row) == raw,
            f"BUNDLE_ROW:{number}",
        )
        work_id = row["work_id"]
        need(isinstance(work_id, str) and len(work_id) == 64 and set(work_id) <= HEX, f"BUNDLE_WORK_ID:{number}")
        need(work_id not in result, f"BUNDLE_DUPLICATE:{number}")
        try:
            closure = bytes.fromhex(row["closure_hex"])
            prefix_order = row["prefix_result"]["optimal_topological_order"]
            suffix_order = row["suffix_result"]["optimal_topological_order"]
        except (KeyError, TypeError, ValueError) as exc:
            raise TenRelationVerificationError(f"BUNDLE_ORDER:{number}") from exc
        need(hashlib.sha256(WORK_PREFIX + closure).hexdigest() == work_id, f"BUNDLE_WORK_BINDING:{number}")
        result[work_id] = closure, prefix_order, suffix_order
    need(len(result) == 1_759, "BUNDLE_WORK_COUNT")
    return result


def checked_order_defect(reach: Sequence[int], order: object) -> tuple[int, int]:
    """Check one explicit order and derive its score loss without stored labels."""

    verts = vertices()
    need(isinstance(order, list) and len(order) == 30 and len(set(order)) == 30, "ORDER_SHAPE")
    parsed: list[tuple[int, int]] = []
    for token in order:
        need(isinstance(token, str) and len(token) == 2 and token.isdigit(), "ORDER_TOKEN")
        vertex = int(token[0]), int(token[1])
        need(vertex in verts, "ORDER_VERTEX")
        parsed.append(vertex)
    need(set(parsed) == set(verts), "ORDER_DOMAIN")
    rank = {vertex: position for position, vertex in enumerate(parsed)}
    index = {vertex: position for position, vertex in enumerate(verts)}
    for source, targets in enumerate(reach):
        pending = targets
        while pending:
            bit = pending & -pending
            pending ^= bit
            need(rank[verts[source]] < rank[verts[bit.bit_length() - 1]], "ORDER_PRECEDENCE")

    score = 0
    for x in range(6):
        for y in range(6):
            if x != y:
                for z in range(6):
                    if y != z:
                        score += rank[x, y] < rank[y, z]
    bad = 0
    for a, b, c in itertools.combinations(range(6), 3):
        for cell in (
            ((a, b, c), (b, c, a), (c, a, b)),
            ((a, c, b), (c, b, a), (b, a, c)),
        ):
            forward = sum(rank[x, y] < rank[y, z] for x, y, z in cell)
            need(forward in (1, 2), "ORDER_TRIANGLE_SCORE")
            bad += forward == 1
    ordinary = 6 * 5 // 2 + 4 * (6 * 5 * 4 // 6)
    need(ordinary - score == bad, "ORDER_SCORE_IDENTITY")
    need(len(index) == 30, "ORDER_VERTEX_INDEX")
    return score, bad


def certify_exact_defect_four(covered_closures: dict[str, bytes], lower_bound: int) -> int:
    bundle = read_bundle_orders()
    need(lower_bound == 4, "EXACT_LOWER_BOUND")
    for work_id, canonical in sorted(covered_closures.items()):
        need(work_id in bundle, f"EXACT_BUNDLE_WORK:{work_id}")
        stored_closure, prefix_order, suffix_order = bundle[work_id]
        need(stored_closure == canonical, f"EXACT_CLOSURE:{work_id}")
        reach = decode_closure(canonical)
        for route, order in (("prefix", prefix_order), ("suffix", suffix_order)):
            score, defect = checked_order_defect(reach, order)
            need(score == 91 and defect == lower_bound, f"EXACT_ORDER:{route}:{work_id}")
    return len(covered_closures)


def audit() -> dict[str, Any]:
    representatives, membership_counts = read_masks()

    full = (1 << len(CORE)) - 1
    covered: set[str] = set()
    covered_closures: dict[str, bytes] = {}
    unique_work_actions = 0
    for work_id, mask_key in sorted(representatives.items()):
        reach = closure_from_mask(mask_key)
        need(canonical_work_id(reach) == work_id, f"WORK_ID:{work_id}")
        hits = [index for index, action in enumerate(centralizer()) if relation_mask(reach, action) == full]
        if hits:
            covered.add(work_id)
            covered_closures[work_id] = canonical_closure(reach)
            unique_work_actions += len(hits) == 1
    need(len(covered) == 24, "DISCOVERED_WORK_COUNT")
    need(sum(membership_counts[work_id] for work_id in covered) == 1_152, "DISCOVERED_MEMBER_COUNT")
    need(unique_work_actions == 24, "UNIQUE_WORK_ACTIONS")

    target_masks = read_covered_masks(covered)
    unique_member_actions = 0
    for mask_key, work_id in target_masks:
        reach = closure_from_mask(mask_key)
        hits = sum(relation_mask(reach, action) == full for action in centralizer())
        need(hits == 1, f"TARGET_UNIQUE_ACTION:{mask_key}")
        unique_member_actions += 1

    lower_bound, component_minima = verify_human_core()
    exact_defect_works = certify_exact_defect_four(covered_closures, lower_bound)

    return {
        "status": "PASS",
        "works": len(representatives),
        "masks": sum(membership_counts.values()),
        "covered_works": len(covered),
        "covered_members": unique_member_actions,
        "exact_defect_works": exact_defect_works,
        "component_minima": component_minima,
        "lower_bound": lower_bound,
        "relations": [relation_text(relation) for relation in CORE],
    }


def main() -> int:
    result = audit()
    print(
        "TEN_RELATION_CORE_PASS "
        f"works={result['works']} masks={result['masks']} "
        f"covered_works={result['covered_works']} covered_members={result['covered_members']} "
        f"exact_defect4={result['exact_defect_works']} "
        f"core={'+'.join(map(str, result['component_minima']))}={result['lower_bound']} oracle_free=true"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TenRelationVerificationError as exc:
        print(f"TEN_RELATION_CORE_FAIL {exc}", file=sys.stderr)
        raise SystemExit(1)
