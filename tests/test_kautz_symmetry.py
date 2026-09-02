from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "companion"))

import population_kernel as kernel  # noqa: E402
import verify_bellman_bundle as bellman  # noqa: E402
import verify_facet_counterexample as facet  # noqa: E402
import verify_five_defect_witnesses as witnesses  # noqa: E402
import verify_ten_relation_core as core  # noqa: E402


def test_five_witnesses_and_mutations() -> None:
    result = witnesses.audit()
    assert result == {"witnesses": 5, "state_total": 5520, "mutations": 5}


def test_facet_certificate_and_hostile_panel() -> None:
    document = facet.load_json(facet.DEFAULT_CERTIFICATE)
    result = facet.validate_certificate(document)
    assert result["primary_jump"] == result["secondary_jump"] == 3
    assert result["jump_histogram"] == {"0": 13, "1": 4, "2": 4, "3": 2}
    assert facet.hostile_panel(document)["required"] == 15
    corrupted = copy.deepcopy(document)
    corrupted["logical_consequence"]["global_maximum_jump_determined"] = True
    with pytest.raises(ValueError):
        facet.validate_certificate(corrupted)


def test_population_constants_and_centralizer() -> None:
    assert kernel.PAIR_STATE_RADIX == 36
    assert kernel.RAW_SOURCE_TRIPLES == 46_656
    assert kernel.SOURCE_ORBITS == 987
    assert len(kernel.centralizer_group()) == 48


def test_one_bellman_pair_replays() -> None:
    works, payloads = bellman.read_bundle()
    assert len(works) == 1_759
    work_id = min(works)
    row = works[work_id]
    result = bellman.verify_pair(
        bytes.fromhex(row["closure_hex"]),
        row["prefix_result"], payloads[f"prefix/{work_id}.bin"],
        row["suffix_result"], payloads[f"suffix/{work_id}.bin"],
    )
    assert result["defect"] in {0, 1, 2, 3, 4}


def test_human_ten_relation_bound() -> None:
    lower, components = core.verify_human_core()
    assert lower == 4
    assert components == (2, 1, 1)
