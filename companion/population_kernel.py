#!/usr/bin/env python3
"""Quotient-native population kernel for the six-letter Kautz census.

The module is deliberately standard-library-only.  It reconstructs the
binary rho-orbit constraint system, the C2 wr S3 action, source
representatives and stabilizers directly from the combinatorial definitions.
Importing it performs no enumeration; :mod:`verify_population` drives the
bounded search explicitly.
"""

from __future__ import annotations

import hashlib
import heapq
import itertools
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable, Sequence


Pair = tuple[int, int]
Word = tuple[int, int, int]
Permutation = tuple[int, ...]

TARGET_BLOCKS: tuple[tuple[int, int], ...] = ((0, 1), (2, 3), (4, 5))
TARGET_SIGMA: tuple[int, ...] = (1, 0, 3, 2, 5, 4)
TARGET_EDGES: tuple[tuple[int, int], ...] = ((0, 1), (0, 2), (1, 2))
Q4_SIGMA: tuple[int, ...] = (1, 0, 3, 2)
Q4_BLOCKS: tuple[frozenset[int], ...] = (frozenset((0, 1)), frozenset((2, 3)))

PAIR_STATE_RADIX = 36
RAW_SOURCE_TRIPLES = PAIR_STATE_RADIX**3
SOURCE_ORBITS = 987
TRIANGLE_DEPTH = 8
TARGET_ORBIT_COUNT = 75
TARGET_SELECTED_ORBITS = 43
TARGET_MAXIMUM_ARCS = 86
Q4_MAXIMUM_ARCS = 18
UNPRUNED_TREE_NODES_PER_REPRESENTATIVE = sum(3**depth for depth in range(TRIANGLE_DEPTH + 1))
UNPRUNED_NODES_PER_REPRESENTATIVE = 1 + UNPRUNED_TREE_NODES_PER_REPRESENTATIVE
UNPRUNED_TARGET_NODE_CEILING = SOURCE_ORBITS * UNPRUNED_NODES_PER_REPRESENTATIVE


class PopulationKernelError(RuntimeError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise PopulationKernelError(code)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


@lru_cache(maxsize=None)
def words(q: int) -> tuple[Word, ...]:
    return tuple(
        (x, y, z)
        for x in range(q)
        for y in range(q)
        for z in range(q)
        if x != y and y != z
    )


@lru_cache(maxsize=None)
def vertices(q: int) -> tuple[Pair, ...]:
    return tuple((x, y) for x in range(q) for y in range(q) if x != y)


def vertex_involution(vertex: Pair, sigma: Sequence[int]) -> Pair:
    return sigma[vertex[1]], sigma[vertex[0]]


def rho(word: Word, sigma: Sequence[int]) -> Word:
    x, y, z = word
    return sigma[z], sigma[y], sigma[x]


@lru_cache(maxsize=None)
def rho_orbits(q: int, sigma: tuple[int, ...]) -> tuple[tuple[Word, Word], ...]:
    quotient = {
        tuple(sorted((word, rho(word, sigma))))
        for word in words(q)
    }
    require(all(len(set(orbit)) == 2 for orbit in quotient), "POPULATION_NONFREE_RHO_ORBIT")
    return tuple(sorted(quotient))


def selected_words(mask: int, orbits: Sequence[Sequence[Word]]) -> frozenset[Word]:
    return frozenset(
        word
        for orbit_index, orbit in enumerate(orbits)
        if mask & (1 << orbit_index)
        for word in orbit
    )


def topological_order(q: int, selected: Iterable[Word]) -> tuple[Pair, ...]:
    selected_set = frozenset(selected)
    vertex_list = vertices(q)
    outgoing = {vertex: [] for vertex in vertex_list}
    indegree = {vertex: 0 for vertex in vertex_list}
    for x, y, z in selected_set:
        require((x, y) in outgoing and (y, z) in outgoing, "POPULATION_WORD_OUTSIDE_DIGRAPH")
        outgoing[x, y].append((y, z))
        indegree[y, z] += 1
    available = [vertex for vertex in vertex_list if indegree[vertex] == 0]
    heapq.heapify(available)
    order: list[Pair] = []
    while available:
        source = heapq.heappop(available)
        order.append(source)
        for target in sorted(outgoing[source]):
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(available, target)
    require(len(order) == len(vertex_list), "POPULATION_SELECTED_SET_NOT_DAG")
    return tuple(order)


def is_dag(q: int, selected: Iterable[Word]) -> bool:
    try:
        topological_order(q, selected)
    except PopulationKernelError as exc:
        if str(exc) == "POPULATION_SELECTED_SET_NOT_DAG":
            return False
        raise
    return True


def antisymmetric_maximal_witness(
    q: int,
    sigma: tuple[int, ...],
    selected: Iterable[Word],
    *,
    expected_maximum_arcs: int,
) -> dict[str, Any]:
    """Construct the maximality witness with no feasibility solve.

    If ``t`` is any topological rank of a rho-stable DAG, then
    ``h(v)=t(v)-t(j(v))`` is antisymmetric and increases on every selected
    arc.  At the known maximum cardinality, the positive-arc set cannot
    strictly contain the selected set, so it is equal to it.
    """

    selected_set = frozenset(selected)
    ambient = frozenset(words(q))
    require(selected_set <= ambient, "POPULATION_SELECTED_WORD_OUTSIDE_AMBIENT")
    require(len(selected_set) == expected_maximum_arcs, "POPULATION_NOT_MAXIMUM_CARDINALITY")
    require(
        {rho(word, sigma) for word in selected_set} == set(selected_set),
        "POPULATION_NOT_RHO_STABLE",
    )
    order = topological_order(q, selected_set)
    rank = {vertex: index for index, vertex in enumerate(order)}
    potential = {
        vertex: rank[vertex] - rank[vertex_involution(vertex, sigma)]
        for vertex in vertices(q)
    }
    require(
        all(
            potential[vertex_involution(vertex, sigma)] == -potential[vertex]
            for vertex in vertices(q)
        ),
        "POPULATION_POTENTIAL_NOT_ANTISYMMETRIC",
    )
    gaps = {
        word: potential[word[1:]] - potential[word[:2]]
        for word in words(q)
    }
    positive = frozenset(word for word, gap in gaps.items() if gap > 0)
    require(selected_set <= positive, "POPULATION_SELECTED_ARC_NOT_POSITIVE")
    require(positive == selected_set, "POPULATION_MAXIMALITY_POSITIVE_SUPERSET")
    zero_words = tuple(sorted(word for word, gap in gaps.items() if gap == 0))
    return {
        "schema": "kautz-symmetry-antisymmetric-maximal-witness-v1",
        "q": q,
        "selected_arcs": len(selected_set),
        "positive_arcs": len(positive),
        "zero_arcs": len(zero_words),
        "topological_order": [list(vertex) for vertex in order],
        "potential": [
            {"vertex": list(vertex), "value": potential[vertex]}
            for vertex in vertices(q)
        ],
        "zero_words": [list(word) for word in zero_words],
        "selected_words_sha256": sha256_value([list(word) for word in sorted(selected_set)]),
        "potential_sha256": sha256_value(
            [(list(vertex), potential[vertex]) for vertex in vertices(q)]
        ),
    }

@lru_cache(maxsize=1)
def local_q4_candidates() -> tuple[frozenset[Word], ...]:
    orbits = rho_orbits(4, Q4_SIGMA)
    require(len(orbits) == 18, "POPULATION_Q4_ORBIT_COUNT")
    variable_indices = []
    for index, orbit in enumerate(orbits):
        letters = set(orbit[0])
        if any(letters <= block for block in Q4_BLOCKS):
            continue
        variable_indices.append(index)
    require(len(variable_indices) == 16, "POPULATION_Q4_VARIABLE_ORBITS")
    candidates: list[frozenset[Word]] = []
    for chosen in itertools.combinations(variable_indices, 9):
        selected = frozenset(word for index in chosen for word in orbits[index])
        if is_dag(4, selected):
            candidates.append(selected)
    unique = tuple(sorted(set(candidates), key=lambda core: tuple(sorted(core))))
    require(len(unique) == PAIR_STATE_RADIX, "POPULATION_Q4_DIRECT_CENSUS")
    return unique


def q4_control_masks() -> set[int]:
    word_index = {word: index for index, word in enumerate(words(4))}
    return {
        sum(1 << word_index[word] for word in core)
        for core in local_q4_candidates()
    }


@lru_cache(maxsize=1)
def target_orbits() -> tuple[tuple[Word, Word], ...]:
    answer = rho_orbits(6, TARGET_SIGMA)
    require(len(answer) == TARGET_ORBIT_COUNT, "POPULATION_TARGET_ORBIT_COUNT")
    return answer


@lru_cache(maxsize=1)
def target_orbit_index() -> dict[Word, int]:
    return {
        word: orbit_index
        for orbit_index, orbit in enumerate(target_orbits())
        for word in orbit
    }


def map_local_word(word: Word, edge: tuple[int, int]) -> Word:
    left, right = edge
    mapping = {
        0: TARGET_BLOCKS[left][0],
        1: TARGET_BLOCKS[left][1],
        2: TARGET_BLOCKS[right][0],
        3: TARGET_BLOCKS[right][1],
    }
    return tuple(mapping[letter] for letter in word)  # type: ignore[return-value]


@lru_cache(maxsize=1)
def target_pair_candidate_masks() -> tuple[tuple[int, ...], ...]:
    orbit_index = target_orbit_index()
    per_edge: list[tuple[int, ...]] = []
    for edge in TARGET_EDGES:
        masks = {
            sum(
                1 << index
                for index in {orbit_index[map_local_word(word, edge)] for word in core}
            )
            for core in local_q4_candidates()
        }
        require(len(masks) == PAIR_STATE_RADIX, "POPULATION_PAIR_CANDIDATE_COUNT")
        require(all(mask.bit_count() == 9 for mask in masks), "POPULATION_PAIR_MASK_WEIGHT")
        per_edge.append(tuple(sorted(masks)))
    return tuple(per_edge)


@lru_cache(maxsize=1)
def target_triangle_groups() -> tuple[tuple[int, int, int], ...]:
    orbit_index = target_orbit_index()
    groups = []
    for r, s, t in itertools.product(range(2), repeat=3):
        a, b, c = TARGET_BLOCKS[0][r], TARGET_BLOCKS[1][s], TARGET_BLOCKS[2][t]
        cell = ((a, b, c), (b, c, a), (c, a, b))
        indices = tuple(sorted({orbit_index[word] for word in cell}))
        require(len(indices) == 3, "POPULATION_TRIANGLE_GROUP_SIZE")
        groups.append(indices)
    require(len(set(groups)) == TRIANGLE_DEPTH, "POPULATION_TRIANGLE_GROUP_COUNT")
    return tuple(groups)


def partition_audit() -> dict[str, Any]:
    pair_indices = {
        index
        for edge_masks in target_pair_candidate_masks()
        for mask in edge_masks
        for index in range(TARGET_ORBIT_COUNT)
        if mask & (1 << index)
    }
    triangle_indices = {index for group in target_triangle_groups() for index in group}
    internal_indices = set(range(TARGET_ORBIT_COUNT)) - pair_indices - triangle_indices
    require(len(pair_indices) == 48, "POPULATION_PAIR_PARTITION")
    require(len(triangle_indices) == 24, "POPULATION_TRIANGLE_PARTITION")
    require(len(internal_indices) == 3, "POPULATION_INTERNAL_PARTITION")
    require(not (pair_indices & triangle_indices), "POPULATION_PARTITION_OVERLAP")
    return {
        "pair_variable_orbits": 48,
        "triangle_variable_orbits": 24,
        "forced_zero_internal_orbits": 3,
        "forced_zero_internal_indices": sorted(internal_indices),
        "total_orbits": TARGET_ORBIT_COUNT,
    }


@lru_cache(maxsize=1)
def centralizer_group() -> tuple[Permutation, ...]:
    group = {
        tuple(
            2 * block_permutation[letter // 2]
            + ((letter % 2) ^ flips[letter // 2])
            for letter in range(6)
        )
        for block_permutation in itertools.permutations(range(3))
        for flips in itertools.product(range(2), repeat=3)
    }
    answer = tuple(sorted(group))
    require(len(answer) == 48, "POPULATION_CENTRALIZER_ORDER")
    require(
        all(
            permutation[TARGET_SIGMA[letter]] == TARGET_SIGMA[permutation[letter]]
            for permutation in answer
            for letter in range(6)
        ),
        "POPULATION_CENTRALIZER_COMMUTATION",
    )
    return answer


def transform_word(word: Word, permutation: Sequence[int]) -> Word:
    return tuple(permutation[letter] for letter in word)  # type: ignore[return-value]


@lru_cache(maxsize=1)
def orbit_bit_actions() -> tuple[tuple[int, ...], ...]:
    orbit_index = target_orbit_index()
    actions = []
    for permutation in centralizer_group():
        image = []
        for orbit in target_orbits():
            target_indices = {
                orbit_index[transform_word(word, permutation)]
                for word in orbit
            }
            require(len(target_indices) == 1, "POPULATION_RHO_ORBIT_SPLIT")
            image.append(next(iter(target_indices)))
        require(len(set(image)) == TARGET_ORBIT_COUNT, "POPULATION_BIT_ACTION_NOT_BIJECTIVE")
        actions.append(tuple(image))
    return tuple(actions)


def transform_mask(mask: int, bit_action: Sequence[int]) -> int:
    answer = 0
    remainder = mask
    while remainder:
        low_bit = remainder & -remainder
        source_index = low_bit.bit_length() - 1
        answer |= 1 << bit_action[source_index]
        remainder ^= low_bit
    return answer


@lru_cache(maxsize=1)
def base_masks() -> tuple[int, ...]:
    masks = tuple(
        first | second | third
        for first, second, third in itertools.product(*target_pair_candidate_masks())
    )
    require(len(masks) == RAW_SOURCE_TRIPLES, "POPULATION_BASE_MASK_COUNT")
    require(len(set(masks)) == RAW_SOURCE_TRIPLES, "POPULATION_BASE_MASK_UNIQUENESS")
    require(all(mask.bit_count() == 27 for mask in masks), "POPULATION_BASE_MASK_WEIGHT")
    return masks


@lru_cache(maxsize=1)
def base_mask_to_index() -> dict[int, int]:
    return {mask: index for index, mask in enumerate(base_masks())}


def apply_source_action(index: int, action_index: int) -> int:
    require(0 <= index < RAW_SOURCE_TRIPLES, "POPULATION_SOURCE_INDEX_RANGE")
    require(0 <= action_index < len(orbit_bit_actions()), "POPULATION_ACTION_INDEX_RANGE")
    image = transform_mask(base_masks()[index], orbit_bit_actions()[action_index])
    require(image in base_mask_to_index(), "POPULATION_BASE_ACTION_NOT_CLOSED")
    return base_mask_to_index()[image]


@dataclass(frozen=True)
class SourceOrbitRecord:
    representative: int
    members: tuple[int, ...]
    stabilizer_actions: tuple[int, ...]


@lru_cache(maxsize=1)
def source_orbit_records() -> tuple[SourceOrbitRecord, ...]:
    unseen = set(range(RAW_SOURCE_TRIPLES))
    records: list[SourceOrbitRecord] = []
    for seed in range(RAW_SOURCE_TRIPLES):
        if seed not in unseen:
            continue
        members = tuple(sorted({apply_source_action(seed, action) for action in range(48)}))
        representative = members[0]
        require(seed == representative, "POPULATION_SOURCE_ORBIT_SEED_NOT_MINIMUM")
        require(set(members) <= unseen, "POPULATION_SOURCE_ORBIT_OVERLAP")
        unseen.difference_update(members)
        stabilizer = tuple(
            action
            for action in range(48)
            if apply_source_action(representative, action) == representative
        )
        require(len(members) * len(stabilizer) == 48, "POPULATION_ORBIT_STABILIZER")
        records.append(SourceOrbitRecord(representative, members, stabilizer))
    require(not unseen, "POPULATION_SOURCE_PARTITION_INCOMPLETE")
    require(len(records) == SOURCE_ORBITS, "POPULATION_SOURCE_ORBIT_COUNT")
    return tuple(records)


@lru_cache(maxsize=1)
def source_record_by_representative() -> dict[int, SourceOrbitRecord]:
    return {record.representative: record for record in source_orbit_records()}


@lru_cache(maxsize=1)
def triangle_group_actions() -> tuple[tuple[int, ...], ...]:
    groups = target_triangle_groups()
    group_index = {frozenset(group): index for index, group in enumerate(groups)}
    actions = []
    for bit_action in orbit_bit_actions():
        image = []
        for group in groups:
            target = frozenset(bit_action[index] for index in group)
            require(target in group_index, "POPULATION_TRIANGLE_GROUP_ACTION_NOT_CLOSED")
            image.append(group_index[target])
        require(len(set(image)) == TRIANGLE_DEPTH, "POPULATION_TRIANGLE_GROUP_ACTION_NOT_BIJECTIVE")
        actions.append(tuple(image))
    return tuple(actions)


@lru_cache(maxsize=1)
def triangle_choice_actions() -> tuple[tuple[tuple[tuple[int, int], ...], ...], ...]:
    """Map ``(source group, omitted position)`` under every bit action."""

    groups = target_triangle_groups()
    answer = []
    for action_index, bit_action in enumerate(orbit_bit_actions()):
        group_rows = []
        for source_group, group in enumerate(groups):
            target_group = triangle_group_actions()[action_index][source_group]
            target = groups[target_group]
            choices = []
            for omitted in range(3):
                omitted_image = bit_action[group[omitted]]
                require(omitted_image in target, "POPULATION_OMITTED_IMAGE_OUTSIDE_GROUP")
                target_omitted = target.index(omitted_image)
                require(
                    transform_mask(triangle_addition(source_group, omitted), bit_action)
                    == triangle_addition(target_group, target_omitted),
                    "POPULATION_TRIANGLE_CHOICE_ACTION_MISMATCH",
                )
                choices.append((target_group, target_omitted))
            group_rows.append(tuple(choices))
        answer.append(tuple(group_rows))
    return tuple(answer)


def triangle_addition(depth: int, omitted: int) -> int:
    require(0 <= depth < TRIANGLE_DEPTH, "POPULATION_TRIANGLE_DEPTH_RANGE")
    require(omitted in (0, 1, 2), "POPULATION_OMITTED_RANGE")
    group = target_triangle_groups()[depth]
    return sum(1 << index for position, index in enumerate(group) if position != omitted)


def partial_mask(base_mask: int, code: Sequence[int]) -> int:
    require(len(code) <= TRIANGLE_DEPTH, "POPULATION_CODE_DEPTH")
    mask = base_mask
    for depth, omitted in enumerate(code):
        mask |= triangle_addition(depth, omitted)
    return mask


def prefix_preserving_stabilizer(
    stabilizer_actions: Sequence[int],
    depth: int,
) -> tuple[int, ...]:
    require(0 <= depth <= TRIANGLE_DEPTH, "POPULATION_PREFIX_DEPTH")
    domain = set(range(depth))
    answer = tuple(
        action
        for action in stabilizer_actions
        if {triangle_group_actions()[action][index] for index in domain} == domain
    )
    require(bool(answer), "POPULATION_PREFIX_STABILIZER_EMPTY")
    return answer


@lru_cache(maxsize=None)
def action_preserves_prefix_domain(action: int, depth: int) -> bool:
    require(0 <= action < len(orbit_bit_actions()), "POPULATION_ACTION_INDEX_RANGE")
    require(0 <= depth <= TRIANGLE_DEPTH, "POPULATION_PREFIX_DEPTH")
    domain = set(range(depth))
    return {triangle_group_actions()[action][index] for index in domain} == domain


def transform_prefix_code(code: Sequence[int], action: int) -> tuple[int, ...]:
    """Transport a prefix when ``action`` preserves its assigned domain."""

    depth = len(code)
    require(0 <= action < len(orbit_bit_actions()), "POPULATION_ACTION_INDEX_RANGE")
    require(
        action_preserves_prefix_domain(action, depth),
        "POPULATION_ACTION_DOES_NOT_PRESERVE_PREFIX_DOMAIN",
    )
    target = [-1] * depth
    for source_group, omitted in enumerate(code):
        require(omitted in (0, 1, 2), "POPULATION_OMITTED_RANGE")
        target_group, target_omitted = triangle_choice_actions()[action][source_group][omitted]
        require(target_group < depth, "POPULATION_PREFIX_TARGET_GROUP_RANGE")
        require(target[target_group] == -1, "POPULATION_PREFIX_TARGET_COLLISION")
        target[target_group] = target_omitted
    require(all(value >= 0 for value in target), "POPULATION_PREFIX_TARGET_INCOMPLETE")
    return tuple(target)


def is_canonical_prefix(
    representative: int,
    code: Sequence[int],
) -> bool:
    require(representative in source_record_by_representative(), "POPULATION_NOT_SOURCE_REPRESENTATIVE")
    record = source_record_by_representative()[representative]
    base = base_masks()[representative]
    candidate = partial_mask(base, code)
    subgroup = prefix_preserving_stabilizer(record.stabilizer_actions, len(code))
    images = tuple(
        partial_mask(base, transform_prefix_code(code, action))
        for action in subgroup
    )
    return candidate == min(images)


def is_canonical_leaf(
    representative: int,
    code: Sequence[int],
) -> bool:
    """Return whether a complete code is the global stabilizer minimum.

    Canonicality is intentionally applied only after all eight triangle
    groups have been assigned.  Local minima at intermediate depths do not
    define a canonical construction path and must never prune the search.
    """

    require(len(code) == TRIANGLE_DEPTH, "POPULATION_CANONICAL_LEAF_DEPTH")
    require(representative in source_record_by_representative(), "POPULATION_NOT_SOURCE_REPRESENTATIVE")
    record = source_record_by_representative()[representative]
    base = base_masks()[representative]
    candidate = partial_mask(base, code)
    images = tuple(
        partial_mask(base, transform_prefix_code(code, action))
        for action in record.stabilizer_actions
    )
    return candidate == min(images)


def legacy_prefix_path_survives(
    representative: int,
    code: Sequence[int],
) -> bool:
    """Model the rejected E31 prefix policy for a hostile mutation test."""

    require(len(code) == TRIANGLE_DEPTH, "POPULATION_LEGACY_PATH_DEPTH")
    return all(
        is_canonical_prefix(representative, code[:depth])
        for depth in range(TRIANGLE_DEPTH + 1)
    )


def source_orbit_audit() -> dict[str, Any]:
    records = source_orbit_records()
    orbit_histogram: dict[str, int] = {}
    stabilizer_histogram: dict[str, int] = {}
    for record in records:
        orbit_histogram[str(len(record.members))] = orbit_histogram.get(str(len(record.members)), 0) + 1
        stabilizer_histogram[str(len(record.stabilizer_actions))] = (
            stabilizer_histogram.get(str(len(record.stabilizer_actions)), 0) + 1
        )
    representatives = tuple(record.representative for record in records)
    return {
        "raw_source_triples": RAW_SOURCE_TRIPLES,
        "source_orbits": len(records),
        "orbit_size_histogram": dict(sorted(orbit_histogram.items(), key=lambda item: int(item[0]))),
        "stabilizer_order_histogram": dict(
            sorted(stabilizer_histogram.items(), key=lambda item: int(item[0]))
        ),
        "maximum_representative": max(representatives),
        "representatives_sha256": sha256_value(representatives),
        "partition_sha256": sha256_value(tuple(record.members for record in records)),
        "group_sha256": sha256_value(centralizer_group()),
        "bit_actions_sha256": sha256_value(orbit_bit_actions()),
        "unpruned_tree_nodes_per_representative": UNPRUNED_TREE_NODES_PER_REPRESENTATIVE,
        "unpruned_nodes_per_representative": UNPRUNED_NODES_PER_REPRESENTATIVE,
        "unpruned_target_node_ceiling": UNPRUNED_TARGET_NODE_CEILING,
    }
