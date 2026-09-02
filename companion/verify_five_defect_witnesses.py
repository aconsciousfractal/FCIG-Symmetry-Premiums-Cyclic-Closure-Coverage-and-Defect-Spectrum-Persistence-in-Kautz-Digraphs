#!/usr/bin/env python3
"""Verify one explicit six-letter certificate for each defect 0 through 4."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMPANION = ROOT / "companion"
if str(COMPANION) not in sys.path:
    sys.path.insert(0, str(COMPANION))

import verify_bellman_bundle as bellman


WITNESSES = ROOT / "companion/data/five_defect_witnesses.json"


class WitnessVerificationError(RuntimeError):
    pass


def need(condition: bool, code: str) -> None:
    if not condition:
        raise WitnessVerificationError(code)


def load_document(path: Path = WITNESSES) -> dict[str, Any]:
    need(path.is_file(), "WITNESS_FILE_MISSING")
    value = json.loads(path.read_text(encoding="utf-8"))
    need(isinstance(value, dict), "WITNESS_DOCUMENT")
    return value


def validate_document(
    document: dict[str, Any],
    works: dict[str, dict[str, Any]],
    payloads: dict[str, bytes],
) -> dict[str, Any]:
    need(
        set(document) == {"schema", "coordinate", "selection_rule", "witnesses"},
        "WITNESS_TOP_KEYS",
    )
    need(
        document["schema"] == "kautz-symmetry-five-defect-witnesses-v1",
        "WITNESS_SCHEMA",
    )
    need(
        document["coordinate"]
        == {"m": 3, "f": 0, "q": 6, "involution": "(01)(23)(45)"},
        "WITNESS_COORDINATE",
    )
    rows = document["witnesses"]
    need(isinstance(rows, list) and len(rows) == 5, "WITNESS_COUNT")
    need([row.get("defect") for row in rows] == list(range(5)), "WITNESS_DEFECT_ORDER")

    state_total = 0
    for row in rows:
        need(
            isinstance(row, dict)
            and set(row) == {"defect", "work_id", "closure_sha256", "prefix", "suffix"},
            "WITNESS_KEYS",
        )
        work_id = row["work_id"]
        need(work_id in works, "WITNESS_WORK_ID")
        source = works[work_id]
        closure = bytes.fromhex(source["closure_hex"])
        prefix_table = payloads[f"prefix/{work_id}.bin"]
        suffix_table = payloads[f"suffix/{work_id}.bin"]
        result = bellman.verify_pair(
            closure,
            source["prefix_result"],
            prefix_table,
            source["suffix_result"],
            suffix_table,
        )
        need(result["defect"] == row["defect"], "WITNESS_DEFECT")
        need(
            source["prefix_result"]["closure_sha256"] == row["closure_sha256"],
            "WITNESS_CLOSURE",
        )
        for side in ("prefix", "suffix"):
            projected = {
                "route": source[f"{side}_result"]["route"],
                "optimum_score": source[f"{side}_result"]["optimum_score"],
                "bad_cell_keys": source[f"{side}_result"]["bad_cell_keys"],
                "optimal_topological_order": source[f"{side}_result"][
                    "optimal_topological_order"
                ],
            }
            need(row[side] == projected, f"WITNESS_{side.upper()}")
        state_total += result["prefix_states"] + result["suffix_states"]
    return {"witnesses": len(rows), "state_total": state_total}


def rejected(
    document: dict[str, Any],
    works: dict[str, dict[str, Any]],
    payloads: dict[str, bytes],
) -> bool:
    try:
        validate_document(document, works, payloads)
    except (WitnessVerificationError, bellman.BellmanVerificationError, KeyError, TypeError):
        return True
    return False


def audit() -> dict[str, Any]:
    document = load_document()
    works, payloads = bellman.read_bundle()
    result = validate_document(document, works, payloads)

    mutations: list[dict[str, Any]] = []
    for mutator in (
        lambda row: row.update(defect=1),
        lambda row: row.update(work_id="0" * 64),
        lambda row: row.update(closure_sha256="0" * 64),
        lambda row: row["prefix"].update(bad_cell_keys=["T:012:+"]),
        lambda row: row["suffix"].update(optimal_topological_order=[]),
    ):
        changed = copy.deepcopy(document)
        mutator(changed["witnesses"][0])
        mutations.append(changed)
    need(all(rejected(row, works, payloads) for row in mutations), "WITNESS_MUTATIONS")
    return {**result, "mutations": len(mutations)}


def main() -> int:
    result = audit()
    print(
        "FIVE_DEFECT_WITNESSES_PASS "
        f"witnesses={result['witnesses']} states={result['state_total']} "
        f"hostile={result['mutations']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, WitnessVerificationError) as exc:
        print(f"FIVE_DEFECT_WITNESSES_FAIL {exc}", file=sys.stderr)
        raise SystemExit(1)
