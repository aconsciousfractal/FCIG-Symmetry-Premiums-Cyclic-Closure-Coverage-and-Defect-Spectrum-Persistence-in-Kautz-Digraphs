#!/usr/bin/env python3
"""Reconstruct the four-letter rank-three bad-cell obstruction exactly."""

from __future__ import annotations

import itertools
import json
from collections import Counter
from collections.abc import Sequence


Pair = tuple[int, int]
Relation = tuple[Pair, Pair]
Cell = tuple[str, tuple[Relation, ...]]

RELATIONS: tuple[Relation, ...] = (
    ((0, 1), (1, 3)),
    ((0, 3), (2, 0)),
    ((0, 3), (3, 2)),
    ((1, 0), (3, 1)),
    ((1, 2), (0, 1)),
    ((2, 0), (2, 3)),
    ((2, 1), (3, 2)),
    ((3, 1), (2, 0)),
    ((3, 2), (0, 2)),
    ((3, 2), (3, 0)),
)
EXPECTED_OBSTRUCTION = frozenset(("T:+:012", "T:-:023", "T:-:123"))


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def is_kautz_arc(relation: Relation) -> bool:
    left, right = relation
    return left[1] == right[0]


def has_alternate_path(
    relations: Sequence[Relation], omitted: Relation,
) -> bool:
    source, target = omitted
    adjacency: dict[Pair, list[Pair]] = {}
    for relation in relations:
        if relation == omitted:
            continue
        left, right = relation
        adjacency.setdefault(left, []).append(right)
    stack = [source]
    seen = {source}
    while stack:
        vertex = stack.pop()
        for successor in adjacency.get(vertex, ()):
            if successor == target:
                return True
            if successor not in seen:
                seen.add(successor)
                stack.append(successor)
    return False


def relation_domain_profile(relations: Sequence[Relation]) -> dict[str, object]:
    need(len(relations) == len(set(relations)), "duplicate base relation")
    covers = sum(not has_alternate_path(relations, relation) for relation in relations)
    kautz_arcs = sum(is_kautz_arc(relation) for relation in relations)
    non_kautz_covers = sum(
        not is_kautz_arc(relation) and not has_alternate_path(relations, relation)
        for relation in relations
    )
    need(covers == 10, "the ten displayed relations must all be covers")
    need(kautz_arcs == 2, "Kautz-arc cover count mismatch")
    need(non_kautz_covers == 8, "non-Kautz cover count mismatch")
    return {
        "domain": "arbitrary_precedence_poset_not_kautz_predecessor_dag",
        "generating_covers": covers,
        "kautz_arc_covers": kautz_arcs,
        "non_kautz_covers": non_kautz_covers,
    }


def oriented_cells(q: int = 4) -> tuple[Cell, ...]:
    cells: list[Cell] = []
    for a, b, c in itertools.combinations(range(q), 3):
        cells.append(
            (
                f"T:+:{a}{b}{c}",
                (((a, b), (b, c)), ((b, c), (c, a)), ((c, a), (a, b))),
            )
        )
        cells.append(
            (
                f"T:-:{a}{b}{c}",
                (((a, c), (c, b)), ((c, b), (b, a)), ((b, a), (a, c))),
            )
        )
    return tuple(cells)


def bad_cell_set(order: Sequence[Pair], cells: Sequence[Cell]) -> frozenset[str]:
    position = {vertex: index for index, vertex in enumerate(order)}
    bad: set[str] = set()
    for name, comparisons in cells:
        forward = sum(position[left] < position[right] for left, right in comparisons)
        need(forward in (1, 2), "a directed triangle must score one or two")
        if forward == 1:
            bad.add(name)
    return frozenset(bad)


def enumerate_bad_sets(relations: Sequence[Relation]) -> Counter[frozenset[str]]:
    vertices = tuple((a, b) for a in range(4) for b in range(4) if a != b)
    index = {vertex: position for position, vertex in enumerate(vertices)}
    predecessors = [0] * len(vertices)
    for left, right in relations:
        need(left in index and right in index and left != right, "invalid base relation")
        predecessors[index[right]] |= 1 << index[left]

    all_mask = (1 << len(vertices)) - 1
    cells = oriented_cells()
    histogram: Counter[frozenset[str]] = Counter()
    order: list[Pair] = []

    def visit(placed: int) -> None:
        if placed == all_mask:
            histogram[bad_cell_set(order, cells)] += 1
            return
        for position, vertex in enumerate(vertices):
            bit = 1 << position
            if placed & bit or predecessors[position] & ~placed:
                continue
            order.append(vertex)
            visit(placed | bit)
            order.pop()

    visit(0)
    return histogram


def minimal_infeasible_subsets(
    histogram: Counter[frozenset[str]], names: Sequence[str]
) -> tuple[frozenset[str], ...]:
    infeasible: list[frozenset[str]] = []
    for size in range(len(names) + 1):
        for values in itertools.combinations(names, size):
            subset = frozenset(values)
            if all(not subset.isdisjoint(bad) for bad in histogram):
                infeasible.append(subset)
    return tuple(
        subset
        for subset in infeasible
        if not any(other < subset for other in infeasible)
    )


def audit(relations: Sequence[Relation] = RELATIONS) -> dict[str, object]:
    domain = relation_domain_profile(relations)
    histogram = enumerate_bad_sets(relations)
    total = sum(histogram.values())
    one_bad = sum(count for bad, count in histogram.items() if len(bad) == 1)
    need(total == 99_000, "linear-extension count mismatch")
    need(one_bad == 162, "one-bad-cell extension count mismatch")
    need(len(histogram) == 176, "bad-cell support count mismatch")
    need(histogram and min(map(len, histogram)) == 1, "minimum defect mismatch")

    names = tuple(name for name, _ in oriented_cells())
    forced = tuple(name for name in names if all(name in bad for bad in histogram))
    incompatible = tuple(
        (left, right)
        for left, right in itertools.combinations(names, 2)
        if all(left in bad or right in bad for bad in histogram)
    )
    need(not forced, "forced-cell set is not empty")
    need(not incompatible, "pairwise incompatibility graph is not empty")

    minimal = minimal_infeasible_subsets(histogram, names)
    need(minimal == (EXPECTED_OBSTRUCTION,), "minimal obstruction mismatch")
    return {
        **domain,
        "linear_extensions": total,
        "one_bad_extensions": one_bad,
        "distinct_bad_sets": len(histogram),
        "minimum_bad_cells": min(map(len, histogram)),
        "forced_cells": len(forced),
        "incompatibility_edges": len(incompatible),
        "minimal_obstruction": sorted(EXPECTED_OBSTRUCTION),
    }


def main() -> int:
    result = audit()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    print(
        "RANK_THREE_PASS "
        f"extensions={result['linear_extensions']} "
        f"bad_sets={result['distinct_bad_sets']} "
        f"minimal={len(result['minimal_obstruction'])} "
        f"non_kautz_covers={result['non_kautz_covers']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
