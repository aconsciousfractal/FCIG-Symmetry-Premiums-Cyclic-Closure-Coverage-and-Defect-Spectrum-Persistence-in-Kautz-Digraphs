# Reviewer quickstart

This package has one manuscript and one public repository. It separates
written proofs, exact finite computations, and release integrity.

## 1. Exact replay

```bash
python -m pip install --require-hashes -r requirements.lock
GIT_ABSOLUTE="$(command -v git)"
python -I -S -B scripts/runtime_bootstrap.py --git-executable "$GIT_ABSOLUTE" --target scripts/verify.py
python -I -S -B -O scripts/runtime_bootstrap.py --git-executable "$GIT_ABSOLUTE" --target scripts/verify.py
```

Both runs must end in `PASS`. The optimized replay checks that validation does
not disappear under `python -O`. Before either run, the bootstrap requires
exact equality between its dependency contract and `requirements.lock`.

## 2. Focused hostile tests

```bash
GIT_ABSOLUTE="$(command -v git)"
python -I -S -B scripts/runtime_bootstrap.py --git-executable "$GIT_ABSOLUTE" --module pytest -- \
  -q -p no:cacheprovider --basetemp /tmp/kautz-symmetry-pytest \
  tests/test_kautz_symmetry.py tests/test_release_assurance.py
```

The suite attacks corrupted witnesses, wrong facet endpoints, altered
histograms and rank-three relations, undeclared files, LFS pointers, absolute
workspace paths, staging residue, unsafe PDF content, and Git/object-store
redirection.

## 3. Mathematical spine

1. ordinary Kautz feedback-number substrate;
2. invariant cell-transversal count and premium `m^2`;
3. sharp-potential construction and extension by blocks/fixed letters;
4. cyclic-closure coverage criterion;
5. monotonicity of defect spectra;
6. exact base census and five witnesses at `(m,f)=(3,0)`;
7. obstruction-clutter equality for arbitrary acyclic precedence relations
   and the forced-cell/matching bound;
8. ten-relation defect-four core and bounded facet counterexamples.

Scrutinize especially the distinction between invariant optima and literal
invariant ordinary optima, the scope of the closure-coverage theorem, and the
fact that the facet panel is bounded rather than global.

## 4. Computation boundary

- `verify_population.py` enumerates the population before opening the shipped
  mask rows and then requires exact set equality.
- `verify_bellman_bundle.py` expands all classes and validates every one of the
  83,736 membership assignments plus all opposed dynamic-programming tables.
- `verify_five_defect_witnesses.py` proves the five finite attainments.
- `verify_rank_three_obstruction.py` verifies that the ten generators are
  covers with exactly eight non-Kautz covers, enumerates the 99,000
  four-letter linear extensions, and recovers the unique minimal rank-three
  obstruction in the broader precedence-poset domain.
- `verify_ten_relation_core.py` discovers the 24 classes without reading a
  stored defect-label oracle, then verifies exact defect four.
- `verify_facet_counterexample.py` rebuilds the 75 forms, 54 walls, two exact
  jump-three edges, and the 90-flip bounded panel.

These checks certify finite statements. They do not prove the all-parameter
analytic theorems or settle novelty.

## 5. Explicit nonclaims

- no equality of all later defect spectra;
- no universal upper bound four;
- no interval-spectrum theorem;
- no full six-letter facet graph or global maximum jump;
- no conclusion that the forced-cell/matching bound fails, or is always
  tight, within the Kautz predecessor-DAG subclass;
- no novelty, priority, or exhaustive-source conclusion;
- no PDF/UA conformance claim.

See `docs/PUBLIC_CLAIM_BOUNDARY.md`, `docs/SOURCE_AND_ATTRIBUTION.md`, and
`docs/REPRODUCIBILITY_BOUNDARY.md` for the exact boundaries.
