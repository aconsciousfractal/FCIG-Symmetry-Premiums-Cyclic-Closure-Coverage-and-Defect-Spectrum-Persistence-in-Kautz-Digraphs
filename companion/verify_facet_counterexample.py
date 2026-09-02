#!/usr/bin/env python3
"""Rebuild and verify the published exact facet counterexample.

The checker uses only the Python standard library.  It reconstructs the
75 orbit forms, 54 primitive walls, exact facet crossing, exact
order-constrained defects, and cyclic-chain lower certificates from first
principles.
"""

from __future__ import annotations

import argparse
import copy
import functools
import hashlib
import heapq
import itertools
import json
import math
import re
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CERTIFICATE = ROOT / "companion/data/facet_counterexample.json"

Q = 6
SIGMA = (1, 0, 3, 2, 5, 4)
ORDINARY_OPTIMUM = 95
HOSTILE_NAMES = (
    "REJECT_WRONG_SOURCE_MASK",
    "REJECT_WRONG_TARGET_MASK",
    "REJECT_WRONG_WALL",
    "REJECT_SINGLE_BIT_PSEUDO_FLIP",
    "REJECT_NON_BALANCED_WALL",
    "REJECT_NON_DAG_ENDPOINT",
    "REJECT_WRONG_SOURCE_DEFECT",
    "REJECT_WRONG_TARGET_DEFECT",
    "REJECT_CORRUPTED_OPTIMAL_ORDER",
    "REJECT_MISSING_FORCED_CELL",
    "REJECT_COMPATIBLE_PAIR_AS_OBSTRUCTION",
    "REJECT_OVERLAPPING_LOWER_CERTIFICATE",
    "REJECT_PANEL_COUNT_DRIFT",
    "REJECT_JUMP_HISTOGRAM_DRIFT",
    "REJECT_GLOBAL_MAXIMUM_JUMP_CLAIM",
)


def need(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def unsigned(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "canonical_sha256"}


def seal(row: dict[str, Any]) -> dict[str, Any]:
    row["canonical_sha256"] = digest(unsigned(row))
    return row


def validate_seal(row: dict[str, Any], code: str) -> None:
    need(row.get("canonical_sha256") == digest(unsigned(row)), code)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    need(isinstance(value, dict), f"FACET_JSON_OBJECT:{path.name}")
    return value


def vertices() -> tuple[tuple[int, int], ...]:
    return tuple((x, y) for x in range(Q) for y in range(Q) if x != y)


def words() -> tuple[tuple[int, int, int], ...]:
    return tuple((x, y, z) for x in range(Q) for y in range(Q) for z in range(Q) if x != y and y != z)


def j_vertex(vertex: tuple[int, int]) -> tuple[int, int]:
    return SIGMA[vertex[1]], SIGMA[vertex[0]]


def rho_word(word: tuple[int, int, int]) -> tuple[int, int, int]:
    return SIGMA[word[2]], SIGMA[word[1]], SIGMA[word[0]]


@functools.lru_cache(maxsize=1)
def orbit_order() -> tuple[tuple[tuple[int, int, int], tuple[int, int, int]], ...]:
    answer = tuple(sorted({tuple(sorted((word, rho_word(word)))) for word in words()}))
    need(len(answer) == 75 and all(len(set(orbit)) == 2 for orbit in answer), "FACET_ORBITS")
    return answer


def basis_data() -> tuple[tuple[tuple[int, int], ...], dict[tuple[int, int], tuple[int, ...]]]:
    reps = tuple(sorted({min(vertex, j_vertex(vertex)) for vertex in vertices() if vertex != j_vertex(vertex)}))
    position = {vertex: index for index, vertex in enumerate(reps)}
    coefficients: dict[tuple[int, int], tuple[int, ...]] = {}
    for vertex in vertices():
        mate = j_vertex(vertex)
        if mate == vertex:
            coefficients[vertex] = (0,) * len(reps)
        else:
            representative = min(vertex, mate)
            sign = 1 if vertex == representative else -1
            coefficients[vertex] = tuple(sign if index == position[representative] else 0 for index in range(len(reps)))
    need(len(reps) == 12, "FACET_BASIS")
    return reps, coefficients


def exact_rank(rows: Iterable[Sequence[int]]) -> int:
    matrix = [[Fraction(value) for value in row] for row in rows]
    if not matrix:
        return 0
    pivot = 0
    for column in range(len(matrix[0])):
        source = next((row for row in range(pivot, len(matrix)) if matrix[row][column]), None)
        if source is None:
            continue
        matrix[pivot], matrix[source] = matrix[source], matrix[pivot]
        scale = matrix[pivot][column]
        matrix[pivot] = [value / scale for value in matrix[pivot]]
        for row in range(len(matrix)):
            if row == pivot or not matrix[row][column]:
                continue
            factor = matrix[row][column]
            matrix[row] = [left - factor * right for left, right in zip(matrix[row], matrix[pivot], strict=True)]
        pivot += 1
        if pivot == len(matrix):
            break
    return pivot


def primitive(vector: tuple[int, ...]) -> tuple[tuple[int, ...], int, int] | None:
    if not any(vector):
        return None
    divisor = math.gcd(*(abs(value) for value in vector))
    reduced = tuple(value // divisor for value in vector)
    orientation = 1 if next(value for value in reduced if value) > 0 else -1
    normal = reduced if orientation == 1 else tuple(-value for value in reduced)
    return normal, orientation, divisor


def wall_identifier(normal: Sequence[int]) -> str:
    return "W:" + digest(list(normal))[:24]


@functools.lru_cache(maxsize=1)
def catalogue() -> dict[str, Any]:
    reps, coefficients = basis_data()
    vectors = []
    for orbit in orbit_order():
        values = [tuple(right - left for left, right in zip(coefficients[x, y], coefficients[y, z], strict=True)) for x, y, z in orbit]
        need(values[0] == values[1], "FACET_RHO_FORM")
        vectors.append(values[0])
    classes: dict[tuple[int, ...], list[dict[str, int]]] = defaultdict(list)
    zero_indices = []
    for index, vector in enumerate(vectors):
        item = primitive(vector)
        if item is None:
            zero_indices.append(index)
        else:
            normal, orientation, magnitude = item
            classes[normal].append({"form_index": index, "orientation": orientation, "magnitude": magnitude})
    walls = []
    for normal in sorted(classes):
        members = tuple(sorted(classes[normal], key=lambda row: row["form_index"]))
        walls.append({
            "id": wall_identifier(normal),
            "normal": normal,
            "members": members,
            "sharp_preserving": sum(row["orientation"] == 1 for row in members) == sum(row["orientation"] == -1 for row in members),
        })
    need(zero_indices == [0, 48, 72], "FACET_ZEROS")
    need(len(walls) == 54 and exact_rank(wall["normal"] for wall in walls) == 12, "FACET_WALLS")
    need(sum(wall["sharp_preserving"] for wall in walls) == 18, "FACET_BALANCED")
    return {
        "reps": reps,
        "vectors": tuple(vectors),
        "zero_indices": tuple(zero_indices),
        "walls": tuple(walls),
        "wall_by_id": {wall["id"]: wall for wall in walls},
        "orbits": orbit_order(),
    }


def parse_mask(key: str) -> int:
    need(isinstance(key, str) and re.fullmatch(r"[0-9a-f]{19}", key) is not None, "FACET_MASK_SYNTAX")
    mask = int(key, 16)
    need(mask < 1 << 75 and mask.bit_count() == 43, "FACET_MASK_DOMAIN")
    need(all(not mask & (1 << index) for index in catalogue()["zero_indices"]), "FACET_ZERO_BIT")
    return mask


def mask_key(mask: int) -> str:
    return f"{mask:019x}"


def signs_from_mask(mask: int) -> tuple[int, ...]:
    zero = set(catalogue()["zero_indices"])
    return tuple(0 if index in zero else (1 if mask & (1 << index) else -1) for index in range(75))


def selected_words(mask: int) -> frozenset[tuple[int, int, int]]:
    return frozenset(word for index, orbit in enumerate(orbit_order()) if mask & (1 << index) for word in orbit)


def topological_order(selected: Iterable[tuple[int, int, int]]) -> tuple[tuple[int, int], ...]:
    outgoing = {vertex: [] for vertex in vertices()}
    indegree = {vertex: 0 for vertex in vertices()}
    for x, y, z in selected:
        outgoing[x, y].append((y, z))
        indegree[y, z] += 1
    available = [vertex for vertex in vertices() if indegree[vertex] == 0]
    heapq.heapify(available)
    order = []
    while available:
        source = heapq.heappop(available)
        order.append(source)
        for target in sorted(outgoing[source]):
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(available, target)
    need(len(order) == 30, "FACET_NOT_DAG")
    return tuple(order)


def is_dag(mask: int) -> bool:
    try:
        topological_order(selected_words(mask))
    except ValueError as exc:
        if str(exc) == "FACET_NOT_DAG":
            return False
        raise
    return True


def bad_cells(order: Sequence[tuple[int, int]]) -> list[str]:
    rank = {vertex: index for index, vertex in enumerate(order)}
    need(len(rank) == 30 and set(rank) == set(vertices()), "FACET_ORDER_DOMAIN")
    answer = []
    for a, b, c in itertools.combinations(range(Q), 3):
        for suffix, cell in (
            ("+", ((a, b, c), (b, c, a), (c, a, b))),
            ("-", ((a, c, b), (c, b, a), (b, a, c))),
        ):
            forward = sum(rank[x, y] < rank[y, z] for x, y, z in cell)
            need(forward in (1, 2), "FACET_TRIANGLE_SCORE")
            if forward == 1:
                answer.append(f"T:{a}{b}{c}:{suffix}")
    return answer


def order_score(order: Sequence[tuple[int, int]]) -> int:
    rank = {vertex: index for index, vertex in enumerate(order)}
    return sum(rank[x, y] < rank[y, z] for x, y, z in words())


def parse_order(values: Any) -> tuple[tuple[int, int], ...]:
    need(isinstance(values, list) and len(values) == 30, "FACET_ORDER_LENGTH")
    order = []
    for value in values:
        need(isinstance(value, str) and re.fullmatch(r"[0-5]{2}", value) is not None and value[0] != value[1], "FACET_ORDER_SYNTAX")
        order.append((int(value[0]), int(value[1])))
    need(len(set(order)) == 30 and set(order) == set(vertices()), "FACET_ORDER_PERMUTATION")
    return tuple(order)


def validate_topological(order: Sequence[tuple[int, int]], mask: int) -> None:
    rank = {vertex: index for index, vertex in enumerate(order)}
    need(all(rank[x, y] < rank[y, z] for x, y, z in selected_words(mask)), "FACET_ORDER_NOT_TOPOLOGICAL")


@functools.lru_cache(maxsize=None)
def exact_optimum(mask: int) -> dict[str, Any]:
    selected = selected_words(mask)
    need(len(selected) == 86, "FACET_CORE_SIZE")
    vertex_list = vertices()
    index = {vertex: position for position, vertex in enumerate(vertex_list)}
    full = (1 << 30) - 1
    prerequisites = [0] * 30
    ambient_in = [0] * 30
    for x, y, z in selected:
        prerequisites[index[y, z]] |= 1 << index[x, y]
    for x, y, z in words():
        ambient_in[index[y, z]] |= 1 << index[x, y]
    choices: dict[int, int] = {}

    @functools.lru_cache(maxsize=None)
    def solve(prefix_mask: int) -> int:
        if prefix_mask == full:
            return 0
        best = -1
        best_vertex = -1
        pending = full ^ prefix_mask
        while pending:
            bit = pending & -pending
            pending ^= bit
            vertex = bit.bit_length() - 1
            if prerequisites[vertex] & ~prefix_mask:
                continue
            candidate = (ambient_in[vertex] & prefix_mask).bit_count() + solve(prefix_mask | bit)
            if candidate > best or (candidate == best and (best_vertex < 0 or vertex < best_vertex)):
                best, best_vertex = candidate, vertex
        need(best_vertex >= 0, "FACET_DP_NO_EXTENSION")
        choices[prefix_mask] = best_vertex
        return best

    optimum = solve(0)
    order_indices = []
    state = 0
    while state != full:
        vertex = choices[state]
        order_indices.append(vertex)
        state |= 1 << vertex
    order = tuple(vertex_list[index_value] for index_value in order_indices)
    validate_topological(order, mask)
    observed_bad = bad_cells(order)
    need(optimum == order_score(order) and len(observed_bad) == ORDINARY_OPTIMUM - optimum, "FACET_DP_RECONSTRUCTION")
    return {"optimum_score": optimum, "defect": ORDINARY_OPTIMUM - optimum, "order": order, "bad_cells": observed_bad}


def dot(left: Sequence[int | Fraction], right: Sequence[int | Fraction]) -> Fraction:
    return sum((Fraction(x) * Fraction(y) for x, y in zip(left, right, strict=True)), Fraction(0))


def fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def deterministic_witness(mask: int) -> tuple[tuple[tuple[int, int], ...], tuple[int, ...]]:
    order = topological_order(selected_words(mask))
    rank = {vertex: index for index, vertex in enumerate(order)}
    potential = {vertex: rank[vertex] - rank[j_vertex(vertex)] for vertex in vertices()}
    basis = tuple(potential[vertex] for vertex in catalogue()["reps"])
    computed_signs = []
    for index, vector in enumerate(catalogue()["vectors"]):
        value = dot(vector, basis)
        if index in catalogue()["zero_indices"]:
            need(value == 0, "FACET_STRUCTURAL_ZERO")
            computed_signs.append(0)
        else:
            need(value != 0, "FACET_WITNESS_ON_WALL")
            computed_signs.append(1 if value > 0 else -1)
    need(tuple(computed_signs) == signs_from_mask(mask), "FACET_WITNESS_SIGNS")
    return order, basis


def expected_wall_record(wall: dict[str, Any]) -> dict[str, Any]:
    members = []
    flat = []
    for member in wall["members"]:
        orbit = orbit_order()[member["form_index"]]
        flat.extend(orbit)
        members.append({
            "form_index": member["form_index"],
            "orientation": member["orientation"],
            "words": ["".join(map(str, word)) for word in orbit],
        })
    return {
        "wall_id": wall["id"],
        "normal": list(wall["normal"]),
        "members": members,
        "kind": "PAIRED_DIGON_REVERSAL" if all(word[0] == word[2] for word in flat) else "COMPLEMENTARY_FOUR_LETTER_PATH_EXCHANGE",
    }


def flip_mask(mask: int, wall: dict[str, Any]) -> int:
    return mask ^ sum(1 << member["form_index"] for member in wall["members"])


def is_acyclic_relations(edges: Iterable[tuple[tuple[int, int], tuple[int, int]]]) -> bool:
    outgoing = {vertex: set() for vertex in vertices()}
    indegree = {vertex: 0 for vertex in vertices()}
    for left, right in edges:
        if right not in outgoing[left]:
            outgoing[left].add(right)
            indegree[right] += 1
    available = [vertex for vertex in vertices() if indegree[vertex] == 0]
    heapq.heapify(available)
    visited = 0
    while available:
        source = heapq.heappop(available)
        visited += 1
        for target in sorted(outgoing[source]):
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(available, target)
    return visited == 30


@functools.lru_cache(maxsize=1)
def triangle_cells() -> dict[str, tuple[tuple[int, int], tuple[int, int], tuple[int, int]]]:
    answer = {}
    for a, b, c in itertools.combinations(range(Q), 3):
        answer[f"T:{a}{b}{c}:+"] = ((a, b), (b, c), (c, a))
        answer[f"T:{a}{b}{c}:-"] = ((a, c), (c, b), (b, a))
    return answer


def cyclic_chains(cell: Sequence[tuple[int, int]]) -> tuple[tuple[tuple[tuple[int, int], tuple[int, int]], ...], ...]:
    x, y, z = cell
    return (((x, y), (y, z)), ((y, z), (z, x)), ((z, x), (x, y)))


@functools.lru_cache(maxsize=None)
def simultaneously_good(mask: int, selected_tuple: tuple[str, ...]) -> bool:
    selected = tuple(sorted(selected_tuple))
    need(len(selected) == len(set(selected)) and set(selected) <= set(triangle_cells()), "FACET_CELL_SELECTION")
    base = tuple(((x, y), (y, z)) for x, y, z in selected_words(mask))

    def search(position: int, edges: tuple[tuple[tuple[int, int], tuple[int, int]], ...]) -> bool:
        if position == len(selected):
            return True
        for chain in cyclic_chains(triangle_cells()[selected[position]]):
            candidate = tuple(sorted(set(edges) | set(chain)))
            if is_acyclic_relations(candidate) and search(position + 1, candidate):
                return True
        return False

    return search(0, base)


def directed_cycle(edges: Iterable[tuple[tuple[int, int], tuple[int, int]]]) -> list[str]:
    outgoing = {vertex: [] for vertex in vertices()}
    for left, right in sorted(set(edges)):
        outgoing[left].append(right)
    state = {vertex: 0 for vertex in outgoing}
    stack: list[tuple[int, int]] = []
    position: dict[tuple[int, int], int] = {}

    def visit(vertex: tuple[int, int]) -> list[tuple[int, int]] | None:
        state[vertex] = 1
        position[vertex] = len(stack)
        stack.append(vertex)
        for target in sorted(outgoing[vertex]):
            if state[target] == 0:
                result = visit(target)
                if result is not None:
                    return result
            elif state[target] == 1:
                return stack[position[target]:] + [target]
        stack.pop()
        position.pop(vertex)
        state[vertex] = 2
        return None

    for vertex in sorted(outgoing):
        if state[vertex] == 0:
            result = visit(vertex)
            if result is not None:
                return [f"{left}{right}" for left, right in result]
    raise ValueError("FACET_EXPECTED_CYCLE")


def cyclic_choice_obstruction(mask: int, selected: Sequence[str]) -> dict[str, Any]:
    base = tuple(((x, y), (y, z)) for x, y, z in selected_words(mask))
    alternatives = []
    families = [cyclic_chains(triangle_cells()[cell]) for cell in selected]
    for choices in itertools.product(*families):
        added = tuple(edge for chain in choices for edge in chain)
        candidate = tuple(sorted(set(base) | set(added)))
        need(not is_acyclic_relations(candidate), "FACET_EXPECTED_INFEASIBILITY")
        alternatives.append({
            "chain_choices": [
                [[f"{left[0]}{left[1]}", f"{right[0]}{right[1]}"] for left, right in chain]
                for chain in choices
            ],
            "directed_cycle": directed_cycle(candidate),
        })
    return {"cell_selection": list(selected), "alternatives": alternatives}


def validate_optimizer(row: dict[str, Any], mask: int, expected: dict[str, Any]) -> None:
    need(set(row) == {"optimizer", "optimum_score", "defect", "optimal_topological_order", "bad_cell_keys", "dynamic_program_table_sha256", "reachable_dynamic_program_states"}, "FACET_OPTIMIZER_FIELDS")
    need(row["optimizer"] in {"PREFIX_IDEAL_DP", "REMOVABLE_SUFFIX_DP"}, "FACET_OPTIMIZER_NAME")
    need(row["optimum_score"] == expected["optimum_score"] and row["defect"] == expected["defect"], "FACET_OPTIMIZER_VALUE")
    order = parse_order(row["optimal_topological_order"])
    validate_topological(order, mask)
    need(order_score(order) == expected["optimum_score"], "FACET_OPTIMIZER_ORDER_SCORE")
    need(row["bad_cell_keys"] == bad_cells(order) and len(row["bad_cell_keys"]) == expected["defect"], "FACET_OPTIMIZER_BAD_CELLS")
    need(isinstance(row["dynamic_program_table_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", row["dynamic_program_table_sha256"]) is not None, "FACET_OPTIMIZER_TABLE_HASH")
    need(type(row["reachable_dynamic_program_states"]) is int and row["reachable_dynamic_program_states"] > 0, "FACET_OPTIMIZER_STATES")


def validate_lower(row: dict[str, Any], mask: int, forced: Sequence[str], pairs: Sequence[Sequence[str]]) -> None:
    need(set(row) == {"route", "forced_checks", "pair_checks", "cyclic_choice_obstructions", "sound_lower_bound", "certificate_cells_disjoint"}, "FACET_LOWER_FIELDS")
    need(row["route"] == "CYCLIC_CHAIN_DAG_FEASIBILITY" and row["certificate_cells_disjoint"] is True, "FACET_LOWER_ROUTE")
    need(row["forced_checks"] == [{"cell": cell, "simultaneously_good": False} for cell in forced], "FACET_FORCED_ROWS")
    need(row["pair_checks"] == [{"cells": list(pair), "simultaneously_good": False} for pair in pairs], "FACET_PAIR_ROWS")
    used: set[str] = set()
    for cell in forced:
        need(cell not in used and not simultaneously_good(mask, (cell,)), "FACET_FORCED_VALIDITY")
        used.add(cell)
    for pair in pairs:
        need(len(pair) == 2 and not (set(pair) & used), "FACET_LOWER_DISJOINT")
        need(not simultaneously_good(mask, tuple(pair)), "FACET_PAIR_VALIDITY")
        used.update(pair)
    expected_obstructions = [cyclic_choice_obstruction(mask, [cell]) for cell in forced] + [cyclic_choice_obstruction(mask, list(pair)) for pair in pairs]
    need(row["cyclic_choice_obstructions"] == expected_obstructions, "FACET_CYCLIC_CHOICE_WITNESSES")
    need(row["sound_lower_bound"] == len(forced) + len(pairs), "FACET_LOWER_VALUE")


def validate_facet(row: dict[str, Any], source_mask: int, target_mask: int, wall: dict[str, Any]) -> None:
    expected_fields = {"source_witness_basis_values", "target_witness_basis_values", "changed_form_indices", "active_wall_ids", "ambient_dimension", "arrangement_rank", "crossing_point", "relative_codimension", "source_wall_value", "target_wall_value"}
    need(set(row) == expected_fields, "FACET_FACET_FIELDS")
    _, source_basis = deterministic_witness(source_mask)
    _, target_basis = deterministic_witness(target_mask)
    need(row["source_witness_basis_values"] == list(source_basis) and row["target_witness_basis_values"] == list(target_basis), "FACET_FACET_WITNESSES")
    changed = sorted(index for index in range(75) if bool(source_mask & (1 << index)) != bool(target_mask & (1 << index)))
    need(changed == row["changed_form_indices"] == sorted(member["form_index"] for member in wall["members"]), "FACET_FACET_CHANGED")
    left_value = dot(wall["normal"], source_basis)
    right_value = dot(wall["normal"], target_basis)
    need(left_value * right_value < 0, "FACET_FACET_SIDES")
    denominator = left_value - right_value
    point = tuple((-right_value * left + left_value * right) / denominator for left, right in zip(source_basis, target_basis, strict=True))
    active = [candidate["id"] for candidate in catalogue()["walls"] if dot(candidate["normal"], point) == 0]
    need(active == [wall["id"]] == row["active_wall_ids"], "FACET_FACET_ACTIVE")
    need(row["ambient_dimension"] == 12 and row["arrangement_rank"] == 12 and row["relative_codimension"] == 1, "FACET_FACET_DIMENSION")
    need(row["crossing_point"] == [fraction_text(value) for value in point], "FACET_FACET_POINT")
    need(row["source_wall_value"] == fraction_text(left_value) and row["target_wall_value"] == fraction_text(right_value), "FACET_FACET_VALUES")


def validate_counterexample(row: dict[str, Any], name: str, specification: dict[str, Any]) -> None:
    need(set(row) == {"name", "source_mask", "target_mask", "wall", "facet_certificate", "source", "target", "absolute_defect_jump"}, "FACET_COUNTEREXAMPLE_FIELDS")
    need(row["name"] == name and row["source_mask"] == specification["source_mask"] and row["target_mask"] == specification["target_mask"], "FACET_COUNTEREXAMPLE_ID")
    source_mask, target_mask = parse_mask(row["source_mask"]), parse_mask(row["target_mask"])
    wall = catalogue()["wall_by_id"].get(specification["wall_id"])
    need(wall is not None and wall["sharp_preserving"], "FACET_COUNTEREXAMPLE_WALL")
    need(row["wall"] == expected_wall_record(wall), "FACET_COUNTEREXAMPLE_WALL_RECORD")
    need(flip_mask(source_mask, wall) == target_mask and is_dag(source_mask) and is_dag(target_mask), "FACET_COUNTEREXAMPLE_EDGE")
    validate_facet(row["facet_certificate"], source_mask, target_mask, wall)
    for side_name, mask, defect in (("source", source_mask, specification["source_defect"]), ("target", target_mask, specification["target_defect"])):
        side = row[side_name]
        need(set(side) == {"exact_defect", "optimizers", "lower_certificate", "topological_witness"}, "FACET_SIDE_FIELDS")
        expected = exact_optimum(mask)
        need(side["exact_defect"] == defect == expected["defect"], "FACET_SIDE_DEFECT")
        need(set(side["optimizers"]) == {"prefix", "suffix"}, "FACET_OPPOSED_KEYS")
        validate_optimizer(side["optimizers"]["prefix"], mask, expected)
        validate_optimizer(side["optimizers"]["suffix"], mask, expected)
        witness_order = tuple(tuple(vertex) for vertex in side["topological_witness"])
        need(witness_order == topological_order(selected_words(mask)), "FACET_TOPO_WITNESS")
        validate_lower(
            side["lower_certificate"], mask,
            specification.get(f"{side_name}_forced_cells", []),
            specification.get(f"{side_name}_incompatible_pairs", []),
        )
        need(side["lower_certificate"]["sound_lower_bound"] <= defect, "FACET_LOWER_SOUND")
    need(row["absolute_defect_jump"] == abs(specification["source_defect"] - specification["target_defect"]) == 3, "FACET_JUMP")


def expected_panel(seed_masks: Sequence[dict[str, Any]]) -> dict[str, Any]:
    walls = [wall for wall in catalogue()["walls"] if wall["sharp_preserving"]]
    entries = []
    for seed in seed_masks:
        source_mask = parse_mask(seed["mask"])
        source_defect = exact_optimum(source_mask)["defect"]
        need(source_defect == seed["defect"], "FACET_SEED_DEFECT")
        for wall in walls:
            target_mask = flip_mask(source_mask, wall)
            if not is_dag(target_mask):
                continue
            target_defect = exact_optimum(target_mask)["defect"]
            entries.append({
                "source_mask": seed["mask"], "target_mask": mask_key(target_mask), "wall_id": wall["id"],
                "source_defect": source_defect, "target_defect": target_defect,
                "absolute_jump": abs(source_defect - target_defect),
            })
    entries.sort(key=lambda item: (item["source_mask"], item["wall_id"], item["target_mask"]))
    histogram = {str(jump): sum(item["absolute_jump"] == jump for item in entries) for jump in sorted({item["absolute_jump"] for item in entries})}
    return {
        "seed_count": 5, "balanced_walls_per_seed": 18, "candidate_attempts": 90,
        "realized_neighbours": len(entries), "non_dag_flips": 90 - len(entries),
        "jump_histogram": histogram, "maximum_observed_jump": max(item["absolute_jump"] for item in entries),
        "entries": entries,
    }


def validate_certificate(certificate: dict[str, Any]) -> dict[str, Any]:
    expected_keys = {
        "schema", "coordinate", "seed_masks", "counterexample_specifications",
        "balanced_wall_structure", "bounded_panel", "counterexamples",
        "logical_consequence", "resource_measurement",
    }
    need(set(certificate) == expected_keys, "FACET_CERTIFICATE_FIELDS")
    need(certificate["schema"] == "kautz-symmetry-facet-counterexample-v1", "FACET_CERTIFICATE_SCHEMA")
    need(certificate["coordinate"] == {"q": 6, "m": 3, "f": 0, "sigma": [1, 0, 3, 2, 5, 4]}, "FACET_COORDINATE")
    seed_masks = certificate["seed_masks"]
    need(isinstance(seed_masks, list) and len(seed_masks) == 5, "FACET_SEED_MASKS")
    balanced = [wall for wall in catalogue()["walls"] if wall["sharp_preserving"]]
    expected_structure = {
        "balanced_wall_count": 18,
        "kind_histogram": {"COMPLEMENTARY_FOUR_LETTER_PATH_EXCHANGE": 12, "PAIRED_DIGON_REVERSAL": 6},
        "walls": [expected_wall_record(wall) for wall in balanced],
    }
    need(certificate["balanced_wall_structure"] == expected_structure, "FACET_WALL_STRUCTURE")
    panel = expected_panel(seed_masks)
    need(certificate["bounded_panel"] == panel, "FACET_PANEL")
    specifications = certificate["counterexample_specifications"]
    need(set(specifications) == {"primary", "secondary"}, "FACET_SPECIFICATION_KEYS")
    need(set(certificate["counterexamples"]) == {"primary", "secondary"}, "FACET_COUNTEREXAMPLE_KEYS")
    for name, specification in specifications.items():
        validate_counterexample(certificate["counterexamples"][name], name, specification)
    need(certificate["logical_consequence"] == {
        "one_lipschitz_refuted": True, "global_maximum_jump_lower_bound": 3,
        "global_maximum_jump_determined": False, "interval_spectrum_route_via_one_lipschitz_available": False,
    }, "FACET_LOGICAL_CONSEQUENCE")
    need(certificate["resource_measurement"] == {
        "seed_masks": 5, "balanced_flip_attempts": 90,
        "realized_neighbours": 23, "opposed_optimizers": True,
        "node_pair_comparisons": 0,
    }, "FACET_RESOURCES")
    return {
        "balanced_walls": 18, "panel_attempts": 90, "realized_neighbours": 23,
        "jump_histogram": panel["jump_histogram"], "primary_jump": 3, "secondary_jump": 3,
        "one_lipschitz_refuted": True,
    }


def hostile_panel(certificate: dict[str, Any]) -> dict[str, Any]:
    rejected = []

    def add(name: str, mutation: Any) -> None:
        candidate = copy.deepcopy(certificate)
        mutation(candidate)
        try:
            validate_certificate(candidate)
        except (ValueError, KeyError, TypeError, IndexError):
            rejected.append(name)
            return
        raise ValueError(f"FACET_HOSTILE_ACCEPTED:{name}")

    specifications = certificate["counterexample_specifications"]
    add(HOSTILE_NAMES[0], lambda row: row["counterexamples"]["primary"].__setitem__("source_mask", certificate["seed_masks"][1]["mask"]))
    add(HOSTILE_NAMES[1], lambda row: row["counterexamples"]["primary"].__setitem__("target_mask", certificate["seed_masks"][1]["mask"]))
    other_balanced = next(wall for wall in catalogue()["walls"] if wall["sharp_preserving"] and wall["id"] != specifications["primary"]["wall_id"])
    add(HOSTILE_NAMES[2], lambda row: row["counterexamples"]["primary"].__setitem__("wall", expected_wall_record(other_balanced)))
    add(HOSTILE_NAMES[3], lambda row: row["counterexamples"]["primary"].__setitem__("target_mask", mask_key(parse_mask(row["counterexamples"]["primary"]["source_mask"]) ^ (1 << 55))))
    nonbalanced = next(wall for wall in catalogue()["walls"] if not wall["sharp_preserving"])
    add(HOSTILE_NAMES[4], lambda row: row["counterexamples"]["primary"].__setitem__("wall", expected_wall_record(nonbalanced)))
    seed0 = parse_mask(certificate["seed_masks"][0]["mask"])
    nondagt = next(flip_mask(seed0, wall) for wall in catalogue()["walls"] if wall["sharp_preserving"] and not is_dag(flip_mask(seed0, wall)))
    add(HOSTILE_NAMES[5], lambda row: row["counterexamples"]["primary"].__setitem__("target_mask", mask_key(nondagt)))
    add(HOSTILE_NAMES[6], lambda row: row["counterexamples"]["primary"]["source"].__setitem__("exact_defect", 1))
    add(HOSTILE_NAMES[7], lambda row: row["counterexamples"]["primary"]["target"].__setitem__("exact_defect", 2))
    add(HOSTILE_NAMES[8], lambda row: row["counterexamples"]["primary"]["target"]["optimizers"]["prefix"]["optimal_topological_order"].reverse())
    add(HOSTILE_NAMES[9], lambda row: row["counterexamples"]["primary"]["target"]["lower_certificate"]["forced_checks"].pop())
    primary_target = parse_mask(specifications["primary"]["target_mask"])
    compatible = next(pair for pair in itertools.combinations(sorted(triangle_cells()), 2) if simultaneously_good(primary_target, tuple(pair)))
    add(HOSTILE_NAMES[10], lambda row: row["counterexamples"]["primary"]["target"]["lower_certificate"].__setitem__("pair_checks", [{"cells": list(compatible), "simultaneously_good": False}]))
    overlapping = [specifications["primary"]["target_forced_cells"][0], "T:245:-"]
    add(HOSTILE_NAMES[11], lambda row: row["counterexamples"]["primary"]["target"]["lower_certificate"].__setitem__("pair_checks", [{"cells": overlapping, "simultaneously_good": False}]))
    add(HOSTILE_NAMES[12], lambda row: row["bounded_panel"].__setitem__("realized_neighbours", 24))
    add(HOSTILE_NAMES[13], lambda row: row["bounded_panel"]["jump_histogram"].__setitem__("3", 1))
    add(HOSTILE_NAMES[14], lambda row: row["logical_consequence"].__setitem__("global_maximum_jump_determined", True))
    need(tuple(rejected) == HOSTILE_NAMES, "FACET_HOSTILE_ORDER")
    return {"required": len(HOSTILE_NAMES), "rejected": rejected}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--certificate", type=Path, default=DEFAULT_CERTIFICATE)
    args = parser.parse_args()
    certificate = load_json(args.certificate)
    summary = validate_certificate(certificate)
    hostile = hostile_panel(certificate)
    print(
        "FACET_COUNTEREXAMPLE_PASS "
        f"primary_jump={summary['primary_jump']} "
        f"secondary_jump={summary['secondary_jump']} "
        f"realized_neighbours={summary['realized_neighbours']} "
        f"hostile={hostile['required']} "
        f"sha256={file_digest(args.certificate)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
