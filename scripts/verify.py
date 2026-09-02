#!/usr/bin/env python3
"""Aggregate exact scientific replay and release verification."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPANION = ROOT / "companion"
if str(COMPANION) not in sys.path:
    sys.path.insert(0, str(COMPANION))

from check_manifest import check_manifest  # noqa: E402
from check_release import check_release  # noqa: E402
import verify_bellman_bundle as bellman  # noqa: E402
import verify_facet_counterexample as facet  # noqa: E402
import verify_five_defect_witnesses as witnesses  # noqa: E402
import verify_population as population  # noqa: E402
import verify_rank_three_obstruction as rank_three  # noqa: E402
import verify_ten_relation_core as core  # noqa: E402


def canonical_sha256(value: object) -> str:
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    manifest = check_manifest()
    release = check_release()
    population_result = population.audit()
    bellman_result = bellman.audit()
    witness_result = witnesses.audit()
    rank_three_result = rank_three.audit()
    core_result = core.audit()
    facet_document = facet.load_json(facet.DEFAULT_CERTIFICATE)
    facet_result = facet.validate_certificate(facet_document)
    facet_hostile = facet.hostile_panel(facet_document)

    receipt = {
        "schema": "kautz-symmetry-public-replay-v1",
        "source_files": manifest["source_files"],
        "manifest_sha256": manifest["manifest_sha256"],
        "release": {
            "head": release["git"]["head"],
            "tree": release["git"]["tree"],
            "pdf_sha256": release["pdf"]["sha256"],
            "pdf_pages": release["pdf"]["pages"],
        },
        "population": {
            "source_orbits": population_result["source"]["source_orbits"],
            "representatives": population_result["enumeration"]["representative_masks"],
            "labelled_masks": population_result["enumeration"]["labelled_masks"],
            "labelled_masks_sha256": population_result["enumeration"]["labelled_masks_sha256"],
            "tracked_equal": population_result["posthoc_comparison"]["exact_set_equality"],
        },
        "bellman": {
            "works": bellman_result["works"],
            "tables": bellman_result["tables"],
            "masks": bellman_result["masks"],
            "histogram": {str(key): bellman_result["work_histogram"][key] for key in sorted(bellman_result["work_histogram"])},
            "prefix_states": bellman_result["prefix_states"],
            "suffix_states": bellman_result["suffix_states"],
            "hostile": bellman_result["hostile"],
        },
        "witnesses": witness_result,
        "rank_three": rank_three_result,
        "ten_relation_core": {
            "covered_works": core_result["covered_works"],
            "covered_members": core_result["covered_members"],
            "exact_defect_works": core_result["exact_defect_works"],
            "lower_bound": core_result["lower_bound"],
        },
        "facet": {
            "primary_jump": facet_result["primary_jump"],
            "secondary_jump": facet_result["secondary_jump"],
            "realized_neighbours": facet_result["realized_neighbours"],
            "hostile": facet_hostile["required"],
        },
    }
    receipt["canonical_sha256"] = canonical_sha256(receipt)
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
