#!/usr/bin/env python3
"""Verify the complete six-letter Bellman certificate bundle.

The checker imports no scientific project module.  It reconstructs 1,759
canonical closures from the shipped source masks, verifies all 83,736
mask-to-work memberships by centralizer expansion, checks two independent
Bellman recurrences and concrete optimum orders, and only then derives the
defect spectrum.
"""

from __future__ import annotations

import copy
import functools
import gzip
import hashlib
import itertools
import json
import struct
import sys
import zipfile
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "companion/data/bellman_tables.ksbellman"
METADATA = ROOT / "companion/data/bellman_bundle_metadata.json"
MASK_ROWS = ROOT / "companion/data/mask_memberships.jsonl.gz"

# Filled only after deterministic materialization.  These constants make a
# bundle/metadata substitution fail even outside the higher-level manifest.
EXPECTED_BUNDLE = (15_203_390, "c4695820ffc1b84606d9f006edd4f66c77028b6823e6b2f780ffc3bdf1a9b2fa")
EXPECTED_METADATA = (1_155, "444815e8795ca38a62e2c3aa6d9355df31316645d5ec8e44702c9492857e5e36")
EXPECTED_MASK_ROWS = (3_065_801, "e5c8c617c2bd9d9205d536c02274855cfba6192e3c8aacb92cbbc0cb5969dd09")

SIGMA = (1, 0, 3, 2, 5, 4)
WORK_PREFIX = b"kautz-symmetry-work-v1\x00"
CLOSURE_MAGIC = b"KSCLOS1\x00"
TABLE_MAGIC = b"KSBELL1\x00"
TABLE_HEADER = struct.Struct(">8sBBBBI32s32s")
TABLE_RECORD = struct.Struct(">IB")
ROUTES = {1: "PREFIX_IDEAL_DP_V2", 2: "REMOVABLE_SUFFIX_DP_V2"}
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ZIP_MODE = 0o100644 << 16
HEX = frozenset("0123456789abcdef")
RESULT_KEYS = {
    "bad_cell_keys",
    "closure_sha256",
    "defect",
    "optimal_topological_order",
    "optimum_score",
    "q",
    "reachable_dynamic_program_states",
    "route",
    "schema",
    "table_bytes",
    "table_file_sha256",
    "table_payload_sha256",
    "work_id",
}


class BellmanVerificationError(RuntimeError):
    """Fail-closed portable evidence or Bellman verification error."""


def need(condition: bool, code: str) -> None:
    if not condition:
        raise BellmanVerificationError(code)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_path(path: Path, expected: tuple[int, str], code: str) -> Path:
    size, digest = expected
    need(path.is_file(), f"{code}_MISSING")
    need(size > 0 and digest != "TO_BE_FILLED", f"{code}_EXPECTED_PLACEHOLDER")
    need(path.stat().st_size == size, f"{code}_BYTES")
    need(sha256_path(path) == digest, f"{code}_SHA256")
    return path


def read_metadata() -> dict[str, Any]:
    path = checked_path(METADATA, EXPECTED_METADATA, "METADATA")
    document = json.loads(path.read_text(encoding="utf-8"))
    need(isinstance(document, dict), "METADATA_OBJECT")
    need(
        set(document)
        == {
            "schema",
            "coordinate",
            "bundle",
            "memberships",
            "summary",
            "provenance_boundary",
        },
        "METADATA_KEYS",
    )
    need(
        document["schema"] == "kautz-symmetry-bellman-bundle-metadata-v1",
        "METADATA_SCHEMA",
    )
    need(document["bundle"]["bytes"] == EXPECTED_BUNDLE[0], "METADATA_BUNDLE_BYTES")
    need(document["bundle"]["sha256"] == EXPECTED_BUNDLE[1], "METADATA_BUNDLE_SHA256")
    need(document["memberships"]["bytes"] == EXPECTED_MASK_ROWS[0], "METADATA_MASK_BYTES")
    need(document["memberships"]["sha256"] == EXPECTED_MASK_ROWS[1], "METADATA_MASK_SHA256")
    return document


@functools.lru_cache(maxsize=1)
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


@functools.lru_cache(maxsize=1)
def orbit_bit_actions() -> tuple[tuple[int, ...], ...]:
    """Return the 48 induced permutations of the 75 mask coordinates."""

    orbits = word_orbits()
    orbit_index = {
        word: position
        for position, orbit in enumerate(orbits)
        for word in orbit
    }
    result: list[tuple[int, ...]] = []
    for action in centralizer():
        bit_action = tuple(
            orbit_index[tuple(action[symbol] for symbol in orbit[0])]
            for orbit in orbits
        )
        need(
            tuple(sorted(bit_action)) == tuple(range(len(orbits))),
            "MASK_ACTION_PERMUTATION",
        )
        result.append(bit_action)
    need(len(set(result)) == 48, "MASK_ACTION_FAITHFUL")
    return tuple(result)


def transform_mask(mask: int, bit_action: Sequence[int]) -> int:
    need(0 <= mask < 1 << 75 and mask.bit_count() == 43, "MASK_TRANSFORM_DOMAIN")
    need(len(bit_action) == 75, "MASK_TRANSFORM_ACTION")
    transformed = 0
    pending = mask
    while pending:
        bit = pending & -pending
        pending ^= bit
        transformed |= 1 << bit_action[bit.bit_length() - 1]
    need(transformed.bit_count() == 43, "MASK_TRANSFORM_WEIGHT")
    return transformed


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
    need(isinstance(mask_key, str) and len(mask_key) == 19 and set(mask_key) <= HEX, "MASK_KEY")
    mask = int(mask_key, 16)
    need(mask < 1 << 75 and mask.bit_count() == 43, "MASK_WEIGHT")
    verts = vertices()
    index = {vertex: position for position, vertex in enumerate(verts)}
    reach = [0] * 30
    for orbit_index, orbit in enumerate(word_orbits()):
        if mask & (1 << orbit_index):
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


def read_tracked_memberships() -> tuple[dict[str, str], dict[str, str], Counter[str]]:
    path = checked_path(MASK_ROWS, EXPECTED_MASK_ROWS, "MASK_ROWS")
    representatives: dict[str, str] = {}
    multiplicities: Counter[str] = Counter()
    observed: dict[str, str] = {}
    with gzip.open(path, "rb") as stream:
        for number, raw in enumerate(stream, 1):
            need(raw.endswith(b"\n"), f"MASK_NEWLINE:{number}")
            row = json.loads(raw)
            need(
                isinstance(row, dict)
                and set(row)
                == {
                    "labelled_multiplicity",
                    "mask_key",
                    "s3_orbit_signature",
                    "signature",
                    "work_id",
                },
                f"MASK_KEYS:{number}",
            )
            need(canonical_bytes(row) == raw, f"MASK_CANONICAL:{number}")
            work_id = row["work_id"]
            mask_key = row["mask_key"]
            need(
                isinstance(work_id, str)
                and len(work_id) == 64
                and set(work_id) <= HEX,
                f"MASK_WORK_ID:{number}",
            )
            need(
                row["labelled_multiplicity"] == 1 and mask_key not in observed,
                f"MASK_ID:{number}",
            )
            closure_from_mask(mask_key)
            observed[mask_key] = work_id
            representatives.setdefault(work_id, mask_key)
            multiplicities[work_id] += 1
    need(len(observed) == 83_736 and len(representatives) == 1_759, "MASK_COUNTS")
    return observed, representatives, multiplicities


def expanded_memberships(representatives: dict[str, str]) -> dict[str, str]:
    """Expand one authenticated representative per work under all 48 actions."""

    expected: dict[str, str] = {}
    actions = orbit_bit_actions()
    for work_id, mask_key in sorted(representatives.items()):
        mask = int(mask_key, 16)
        orbit = {transform_mask(mask, action) for action in actions}
        need(len(orbit) in (24, 48), f"MASK_ORBIT_SIZE:{work_id}")
        for image in orbit:
            image_key = f"{image:019x}"
            need(image_key not in expected, f"MASK_ORBIT_OVERLAP:{image_key}")
            expected[image_key] = work_id
    need(len(expected) == 83_736, "MASK_EXPANDED_COUNT")
    return expected


def verify_membership_map(observed: dict[str, str], expected: dict[str, str]) -> None:
    need(set(observed) == set(expected), "MASK_MEMBERSHIP_DOMAIN")
    for mask_key in sorted(expected):
        need(
            observed[mask_key] == expected[mask_key],
            f"MASK_WORK_MEMBERSHIP:{mask_key}",
        )


def tracked_closures() -> tuple[dict[str, bytes], Counter[str]]:
    observed, representatives, multiplicities = read_tracked_memberships()
    closures: dict[str, bytes] = {}
    for work_id, mask_key in sorted(representatives.items()):
        reach = closure_from_mask(mask_key)
        canonical = min(
            encode_reach(transform_reach(reach, action)) for action in centralizer()
        )
        need(sha256_bytes(WORK_PREFIX + canonical) == work_id, f"MASK_WORK:{work_id}")
        closures[work_id] = canonical
    expected = expanded_memberships(representatives)
    verify_membership_map(observed, expected)
    need(Counter(expected.values()) == multiplicities, "MASK_MEMBERSHIP_MULTIPLICITIES")
    need(
        Counter(multiplicities.values()) == Counter({24: 29, 48: 1_730}),
        "MASK_ORBIT_SIZE_HISTOGRAM",
    )
    return closures, multiplicities


def parse_closure(data: bytes) -> tuple[int, tuple[int, ...]]:
    need(isinstance(data, bytes) and data[:8] == CLOSURE_MAGIC, "CLOSURE_MAGIC")
    need(len(data) >= 10, "CLOSURE_SHORT")
    q, n = data[8], data[9]
    need(2 <= q <= 6 and n == q * (q - 1), "CLOSURE_DIMENSION")
    payload = data[10:]
    need(len(payload) == (n * n + 7) // 8, "CLOSURE_LENGTH")
    rows = [0] * n
    for source in range(n):
        for target in range(n):
            position = source * n + target
            if payload[position // 8] & (1 << (7 - position % 8)):
                rows[source] |= 1 << target
    for source in range(n):
        need(not rows[source] & (1 << source), "CLOSURE_LOOP")
        for middle in range(n):
            if rows[source] & (1 << middle):
                need(rows[middle] & ~rows[source] == 0, "CLOSURE_TRANSITIVITY")
    return q, tuple(rows)


def parse_table(data: bytes, closure: bytes) -> tuple[str, int, dict[int, int]]:
    need(len(data) >= TABLE_HEADER.size, "TABLE_SHORT")
    magic, version, route_code, q, record_size, count, closure_hash, body_hash = TABLE_HEADER.unpack(
        data[: TABLE_HEADER.size]
    )
    need(magic == TABLE_MAGIC and version == 1, "TABLE_HEADER")
    need(route_code in ROUTES and record_size == TABLE_RECORD.size, "TABLE_ROUTE_OR_RECORD")
    closure_q, _ = parse_closure(closure)
    need(q == closure_q, "TABLE_Q")
    need(closure_hash == hashlib.sha256(closure).digest(), "TABLE_CLOSURE_HASH")
    body = data[TABLE_HEADER.size :]
    need(len(body) == count * TABLE_RECORD.size, "TABLE_LENGTH")
    need(hashlib.sha256(body).digest() == body_hash, "TABLE_BODY_HASH")
    values: dict[int, int] = {}
    previous = -1
    for offset in range(0, len(body), TABLE_RECORD.size):
        mask, value = TABLE_RECORD.unpack(body[offset : offset + TABLE_RECORD.size])
        need(mask > previous, "TABLE_SORT_OR_DUPLICATE")
        previous = mask
        values[mask] = value
    need(len(values) == count and count > 0, "TABLE_COUNT")
    return ROUTES[route_code], q, values


def ambient_predecessors(q: int) -> tuple[int, ...]:
    verts = tuple((x, y) for x in range(q) for y in range(q) if x != y)
    index = {vertex: position for position, vertex in enumerate(verts)}
    incoming = [0] * len(verts)
    for x in range(q):
        for y in range(q):
            if x != y:
                for z in range(q):
                    if y != z:
                        incoming[index[y, z]] |= 1 << index[x, y]
    return tuple(incoming)


def predecessors(reach: Sequence[int]) -> tuple[int, ...]:
    incoming = [0] * len(reach)
    for source, targets in enumerate(reach):
        pending = targets
        while pending:
            bit = pending & -pending
            pending ^= bit
            incoming[bit.bit_length() - 1] |= 1 << source
    return tuple(incoming)


def is_ideal(mask: int, incoming: Sequence[int]) -> bool:
    pending = mask
    while pending:
        bit = pending & -pending
        pending ^= bit
        if incoming[bit.bit_length() - 1] & ~mask:
            return False
    return True


def verify_prefix(values: dict[int, int], q: int, reach: Sequence[int]) -> int:
    n = q * (q - 1)
    full = (1 << n) - 1
    incoming = predecessors(reach)
    ambient = ambient_predecessors(q)
    need(0 in values and full in values and values[full] == 0, "PREFIX_BOUNDARY")
    for mask, recorded in values.items():
        need(0 <= mask <= full and is_ideal(mask, incoming), "PREFIX_NONIDEAL")
        if mask == full:
            continue
        choices: list[int] = []
        missing = full ^ mask
        while missing:
            bit = missing & -missing
            missing ^= bit
            vertex = bit.bit_length() - 1
            if incoming[vertex] & ~mask:
                continue
            target = mask | bit
            need(target in values, "PREFIX_MISSING_STATE")
            choices.append((ambient[vertex] & mask).bit_count() + values[target])
        need(choices and recorded == max(choices), "PREFIX_BELLMAN")
    return values[0]


def verify_suffix(values: dict[int, int], q: int, reach: Sequence[int]) -> int:
    n = q * (q - 1)
    full = (1 << n) - 1
    incoming = predecessors(reach)
    ambient = ambient_predecessors(q)
    need(0 in values and full in values and values[0] == 0, "SUFFIX_BOUNDARY")
    for remaining, recorded in values.items():
        need(0 <= remaining <= full and is_ideal(remaining, incoming), "SUFFIX_NONIDEAL")
        if remaining == 0:
            continue
        choices: list[int] = []
        pending = remaining
        while pending:
            bit = pending & -pending
            pending ^= bit
            vertex = bit.bit_length() - 1
            if reach[vertex] & remaining:
                continue
            earlier = remaining ^ bit
            need(earlier in values, "SUFFIX_MISSING_STATE")
            choices.append(values[earlier] + (ambient[vertex] & earlier).bit_count())
        need(choices and recorded == max(choices), "SUFFIX_BELLMAN")
    return values[full]


def score_and_bad(q: int, order: object) -> tuple[int, list[str], tuple[int, ...]]:
    verts = tuple((x, y) for x in range(q) for y in range(q) if x != y)
    need(isinstance(order, list) and len(order) == len(verts) and len(set(order)) == len(order), "ORDER_SHAPE")
    parsed: list[tuple[int, int]] = []
    for token in order:
        need(isinstance(token, str) and len(token) == 2 and token.isdigit(), "ORDER_TOKEN")
        vertex = int(token[0]), int(token[1])
        need(vertex in verts, "ORDER_VERTEX")
        parsed.append(vertex)
    need(set(parsed) == set(verts), "ORDER_DOMAIN")
    rank = {vertex: position for position, vertex in enumerate(parsed)}
    vertex_index = {vertex: position for position, vertex in enumerate(verts)}
    score = 0
    for x in range(q):
        for y in range(q):
            if x != y:
                for z in range(q):
                    if y != z:
                        score += rank[x, y] < rank[y, z]
    bad: list[str] = []
    for a, b, c in itertools.combinations(range(q), 3):
        positive = ((a, b, c), (b, c, a), (c, a, b))
        negative = ((a, c, b), (c, b, a), (b, a, c))
        for sign, cell in (("+", positive), ("-", negative)):
            forward = sum(rank[x, y] < rank[y, z] for x, y, z in cell)
            need(forward in (1, 2), "TRIANGLE_SCORE")
            if forward == 1:
                bad.append(f"T:{a}{b}{c}:{sign}")
    return score, bad, tuple(vertex_index[vertex] for vertex in parsed)


def ordinary_optimum(q: int) -> int:
    return q * (q - 1) // 2 + 4 * (q * (q - 1) * (q - 2) // 6)


def verify_certificate(closure: bytes, result: dict[str, Any], table: bytes) -> dict[str, int | str]:
    q, reach = parse_closure(closure)
    route, table_q, values = parse_table(table, closure)
    need(table_q == q and len(values) <= 25_000_000, "STATE_CAP")
    optimum = verify_prefix(values, q, reach) if route == ROUTES[1] else verify_suffix(values, q, reach)
    need(isinstance(result, dict) and set(result) == RESULT_KEYS, "RESULT_KEYS")
    need(result["schema"] == "kautz-symmetry-bellman-result-v1", "RESULT_SCHEMA")
    need(result["route"] == route and result["q"] == q, "RESULT_ROUTE_Q")
    work_id = sha256_bytes(WORK_PREFIX + closure)
    need(result["work_id"] == work_id, "RESULT_WORK")
    need(result["closure_sha256"] == sha256_bytes(closure), "RESULT_CLOSURE")
    need(result["table_file_sha256"] == sha256_bytes(table), "RESULT_TABLE_FILE")
    need(result["table_payload_sha256"] == sha256_bytes(table[TABLE_HEADER.size :]), "RESULT_TABLE_PAYLOAD")
    need(result["table_bytes"] == len(table), "RESULT_TABLE_BYTES")
    need(result["reachable_dynamic_program_states"] == len(values), "RESULT_STATES")
    need(result["optimum_score"] == optimum, "RESULT_OPTIMUM")
    score, bad, order_indices = score_and_bad(q, result["optimal_topological_order"])
    need(score == optimum, "RESULT_ORDER_SCORE")
    rank = {vertex: position for position, vertex in enumerate(order_indices)}
    for source, targets in enumerate(reach):
        pending = targets
        while pending:
            bit = pending & -pending
            pending ^= bit
            need(rank[source] < rank[bit.bit_length() - 1], "RESULT_ORDER_PRECEDENCE")
    defect = ordinary_optimum(q) - optimum
    need(result["defect"] == defect, "RESULT_DEFECT")
    need(result["bad_cell_keys"] == bad and len(bad) == defect, "RESULT_BAD_CELLS")
    return {"route": route, "optimum": optimum, "defect": defect, "states": len(values)}


def verify_pair(
    closure: bytes,
    prefix_result: dict[str, Any],
    prefix_table: bytes,
    suffix_result: dict[str, Any],
    suffix_table: bytes,
) -> dict[str, int]:
    first = verify_certificate(closure, prefix_result, prefix_table)
    second = verify_certificate(closure, suffix_result, suffix_table)
    need(first["route"] == ROUTES[1] and second["route"] == ROUTES[2], "PAIR_ROUTES")
    need(prefix_table != suffix_table, "PAIR_TABLE_ALIAS")
    need(first["optimum"] == second["optimum"], "PAIR_OPTIMUM")
    need(first["defect"] == second["defect"], "PAIR_DEFECT")
    return {
        "defect": int(first["defect"]),
        "optimum": int(first["optimum"]),
        "prefix_states": int(first["states"]),
        "suffix_states": int(second["states"]),
    }


def read_bundle() -> tuple[dict[str, dict[str, Any]], dict[str, bytes]]:
    path = checked_path(BUNDLE, EXPECTED_BUNDLE, "BUNDLE")
    payloads: dict[str, bytes] = {}
    with zipfile.ZipFile(path, "r") as bundle:
        need(bundle.comment == b"" and bundle.testzip() is None, "ZIP_CONTAINER")
        infos = bundle.infolist()
        names = [info.filename for info in infos]
        need(names == sorted(names) and len(names) == len(set(names)), "ZIP_ORDER_OR_DUPLICATE")
        for info in infos:
            pure = PurePosixPath(info.filename)
            need(not pure.is_absolute() and ".." not in pure.parts and "\\" not in info.filename, "ZIP_PATH")
            need(info.date_time == ZIP_TIMESTAMP, f"ZIP_TIMESTAMP:{info.filename}")
            need(info.compress_type == zipfile.ZIP_STORED, f"ZIP_METHOD:{info.filename}")
            need(info.create_system == 3 and info.external_attr == ZIP_MODE, f"ZIP_MODE:{info.filename}")
            need(info.extra == b"" and info.comment == b"", f"ZIP_METADATA:{info.filename}")
            payloads[info.filename] = bundle.read(info)
    need("works.jsonl" in payloads, "ZIP_WORKS")
    works: dict[str, dict[str, Any]] = {}
    prior = ""
    for number, raw in enumerate(payloads["works.jsonl"].splitlines(keepends=True), 1):
        need(raw.endswith(b"\n"), f"WORK_NEWLINE:{number}")
        row = json.loads(raw)
        need(
            isinstance(row, dict)
            and set(row) == {"closure_hex", "prefix_result", "suffix_result", "work_id"},
            f"WORK_KEYS:{number}",
        )
        need(canonical_bytes(row) == raw, f"WORK_CANONICAL:{number}")
        work_id = row["work_id"]
        need(isinstance(work_id, str) and len(work_id) == 64 and set(work_id) <= HEX, f"WORK_ID:{number}")
        need(work_id > prior and work_id not in works, f"WORK_ORDER:{number}")
        bytes.fromhex(row["closure_hex"])
        works[work_id] = row
        prior = work_id
    need(len(works) == 1_759, "WORK_COUNT")
    expected_names = {"works.jsonl"}
    for work_id in works:
        expected_names.add(f"prefix/{work_id}.bin")
        expected_names.add(f"suffix/{work_id}.bin")
    need(set(payloads) == expected_names and len(payloads) == 3_519, "ZIP_ENTRY_SET")
    return works, payloads


def mutate_resealed_value(table: bytes) -> bytes:
    fields = list(TABLE_HEADER.unpack(table[: TABLE_HEADER.size]))
    body = bytearray(table[TABLE_HEADER.size :])
    need(len(body) >= TABLE_RECORD.size, "MUTATION_BODY")
    body[4] = (body[4] + 1) % 256
    fields[7] = hashlib.sha256(body).digest()
    return TABLE_HEADER.pack(*fields) + bytes(body)


def mutate_remove_state(table: bytes) -> bytes:
    fields = list(TABLE_HEADER.unpack(table[: TABLE_HEADER.size]))
    body = table[TABLE_HEADER.size :]
    need(len(body) >= 2 * TABLE_RECORD.size, "MUTATION_STATES")
    body = body[:TABLE_RECORD.size] + body[2 * TABLE_RECORD.size :]
    fields[5] -= 1
    fields[7] = hashlib.sha256(body).digest()
    return TABLE_HEADER.pack(*fields) + body


def rejected(call: Callable[[], object]) -> bool:
    try:
        call()
    except (BellmanVerificationError, KeyError, TypeError, ValueError):
        return True
    return False


def hostile_panel(
    closure: bytes,
    prefix_result: dict[str, Any],
    prefix_table: bytes,
    suffix_result: dict[str, Any],
    suffix_table: bytes,
) -> int:
    mutations: list[Callable[[], object]] = []

    def changed_result(key: str, value: object) -> dict[str, Any]:
        row = copy.deepcopy(prefix_result)
        row[key] = value
        return row

    mutations.append(lambda: verify_certificate(closure[:-1] + bytes((closure[-1] ^ 1,)), prefix_result, prefix_table))
    mutations.append(lambda: verify_certificate(closure, changed_result("defect", prefix_result["defect"] + 1), prefix_table))
    mutations.append(lambda: verify_certificate(closure, changed_result("optimum_score", prefix_result["optimum_score"] + 1), prefix_table))
    mutations.append(lambda: verify_certificate(closure, changed_result("optimal_topological_order", list(reversed(prefix_result["optimal_topological_order"]))), prefix_table))
    mutations.append(lambda: verify_certificate(closure, changed_result("bad_cell_keys", []), prefix_table))
    mutations.append(lambda: verify_certificate(closure, changed_result("table_file_sha256", "0" * 64), prefix_table))
    mutations.append(lambda: verify_certificate(closure, changed_result("reachable_dynamic_program_states", 0), prefix_table))
    mutations.append(lambda: verify_certificate(closure, prefix_result, b"X" + prefix_table[1:]))
    mutations.append(lambda: verify_certificate(closure, prefix_result, prefix_table[:20] + bytes((prefix_table[20] ^ 1,)) + prefix_table[21:]))
    mutations.append(lambda: verify_certificate(closure, prefix_result, prefix_table[:-1] + bytes((prefix_table[-1] ^ 1,))))
    mutations.append(lambda: verify_certificate(closure, prefix_result, mutate_resealed_value(prefix_table)))
    mutations.append(lambda: verify_certificate(closure, prefix_result, mutate_remove_state(prefix_table)))
    need(all(rejected(mutation) for mutation in mutations), "HOSTILE_PANEL")
    need(
        not rejected(lambda: verify_pair(closure, prefix_result, prefix_table, suffix_result, suffix_table)),
        "HOSTILE_POSITIVE_CONTROL",
    )
    return len(mutations)


def audit() -> dict[str, Any]:
    metadata = read_metadata()
    closures, multiplicities = tracked_closures()
    works, payloads = read_bundle()
    need(set(works) == set(closures), "COMPLETE_WORK_SET")

    histogram: Counter[int] = Counter()
    mask_histogram: Counter[int] = Counter()
    prefix_states = 0
    suffix_states = 0
    first_control: tuple[bytes, dict[str, Any], bytes, dict[str, Any], bytes] | None = None
    for work_id in sorted(works):
        row = works[work_id]
        closure = bytes.fromhex(row["closure_hex"])
        need(closure == closures[work_id], f"TRACKED_CLOSURE:{work_id}")
        need(sha256_bytes(WORK_PREFIX + closure) == work_id, f"BUNDLE_WORK:{work_id}")
        prefix_table = payloads[f"prefix/{work_id}.bin"]
        suffix_table = payloads[f"suffix/{work_id}.bin"]
        result = verify_pair(
            closure,
            row["prefix_result"],
            prefix_table,
            row["suffix_result"],
            suffix_table,
        )
        defect = result["defect"]
        histogram[defect] += 1
        mask_histogram[defect] += multiplicities[work_id]
        prefix_states += result["prefix_states"]
        suffix_states += result["suffix_states"]
        if first_control is None:
            first_control = (
                closure,
                row["prefix_result"],
                prefix_table,
                row["suffix_result"],
                suffix_table,
            )

    expected_work = Counter({0: 445, 1: 555, 2: 420, 3: 297, 4: 42})
    expected_masks = Counter({0: 20_976, 1: 26_640, 2: 19_896, 3: 14_208, 4: 2_016})
    need(histogram == expected_work, "WORK_HISTOGRAM")
    need(mask_histogram == expected_masks, "MASK_HISTOGRAM")
    need(prefix_states == suffix_states == 1_093_156, "STATE_TOTALS")
    summary = metadata["summary"]
    need(summary["work_defect_histogram"] == {str(key): histogram[key] for key in sorted(histogram)}, "METADATA_WORK_HISTOGRAM")
    need(summary["work_count"] == 1_759 and metadata["bundle"]["tables"] == 3_518, "METADATA_COUNTS")
    need(metadata["bundle"]["entries"] == 3_519 and summary["mask_count"] == 83_736, "METADATA_POPULATION")
    need(summary["prefix_states"] == prefix_states and summary["suffix_states"] == suffix_states, "METADATA_STATES")
    need(first_control is not None, "HOSTILE_CONTROL_MISSING")
    hostile = hostile_panel(*first_control)
    return {
        "entries": len(payloads),
        "hostile": hostile,
        "masks": sum(mask_histogram.values()),
        "prefix_states": prefix_states,
        "suffix_states": suffix_states,
        "tables": 2 * len(works),
        "work_histogram": histogram,
        "works": len(works),
    }


def main() -> int:
    result = audit()
    histogram = ",".join(f"{key}:{result['work_histogram'][key]}" for key in sorted(result["work_histogram"]))
    print(
        "BELLMAN_BUNDLE_PASS "
        f"works={result['works']} tables={result['tables']} entries={result['entries']} "
        f"masks={result['masks']} prefix_states={result['prefix_states']} "
        f"suffix_states={result['suffix_states']} hist={histogram} hostile={result['hostile']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BellmanVerificationError, OSError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"BELLMAN_BUNDLE_FAIL {exc}", file=sys.stderr)
        raise SystemExit(1)
