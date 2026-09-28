# Symmetry premiums and defect spectra in Kautz digraphs

**Author:** Oleksiy Babanskyy

**ORCID:** [0009-0001-6176-6208](https://orcid.org/0009-0001-6176-6208)

This is the single public manuscript and reproducibility repository for
*Symmetry Premiums, Cyclic-Closure Coverage, and Defect-Spectrum Persistence
in Kautz Digraphs*.

## Main results

For a letter involution of type `2^m 1^f` acting on length-three Kautz words
by reverse complementation, the paper proves:

- the invariant feedback-vertex optimum has premium exactly `m^2` over the
  ordinary optimum;
- in the nonidentity domain, every invariant optimum is the cyclic closure of
  an ordinary optimum exactly for `m=1`; for `m>=2`, closure-generated and
  non-closure-generated optima coexist;
- the proved spectrum inclusion is `D_(r,0) subset D_(m,f)` for
  `m>=r>=1` and `f>=0`: moving blocks are added before fixed letters;
- the exact six-letter base spectrum is `{0,1,2,3,4}`, so all five defects
  persist for every `m>=3` and `f>=0`;
- for arbitrary acyclic precedence relations on the line-digraph vertices,
  defect is the transversal number of a minimal-obstruction clutter;
- the forced-cell-plus-matching lower bound can fail to be exact in that
  broader domain, as shown by a non-Kautz rank-three precedence poset;
- a ten-relation precedence core explains 24 of the 42 defect-four classes in
  the six-letter census.

The finite facet diagnostic proves only that the maximum jump is **at least
three**: it gives two exact adjacent pairs with jumps three in a bounded panel.
It does not compute the full six-letter facet graph or its global maximum.

## Verify

Install the hash-locked inspection environment, then run the exact replay:

```bash
python -m pip install --require-hashes -r requirements.lock
GIT_ABSOLUTE="$(command -v git)"
python -I -S -B scripts/runtime_bootstrap.py --git-executable "$GIT_ABSOLUTE" --target scripts/verify.py
python -I -S -B -O scripts/runtime_bootstrap.py --git-executable "$GIT_ABSOLUTE" --target scripts/verify.py
```

The bootstrap parses `requirements.lock` using only the standard library and
rejects any mismatch between the locked distributions and the runtime
dependency contract before executing a verifier.

The verifier checks the manifest and release surface, independently rebuilds
the finite population, validates all 3,518 opposed Bellman tables and all
83,736 mask-to-class assignments, verifies the five spectrum witnesses,
certifies that the four-letter rank-three control is a broader precedence
poset rather than a Kautz predecessor DAG, finds its unique obstruction and
the 24 ten-relation-core classes, and reconstructs the exact facet
counterexamples. It writes no scientific result file.

The committed paper is
`paper/Symmetry-Premiums-Cyclic-Closure-Coverage-and-Defect-Spectrum-Persistence-in-Kautz-Digraphs.pdf`.
See [REPRODUCE.md](REPRODUCE.md) for clean-clone replay and deterministic PDF
build instructions.

## Repository map

| Path | Purpose |
|---|---|
| `paper/` | manuscript source, bibliography, and committed PDF |
| `companion/` | exact standard-library reconstruction and verification code |
| `companion/data/` | finite certificates and ordinary-Git binary bundle |
| `scripts/` | manifest, release, runtime, and aggregate verification |
| `tests/` | focused scientific and hostile release tests |
| `docs/` | claim, source, and reproducibility boundaries |

## Scientific and bibliographic boundary

The analytic proofs remain in the manuscript; finite checkers do not replace
them. Two potentially relevant 2015/2016 Kautz sources were available only
through catalog or issue metadata, not full text. Accordingly, this repository
makes no novelty, priority, or exhaustive-literature claim. It also makes no
claim that the defect spectrum is always an interval or bounded above by four.
The nonexact rank-three control does not settle whether the
forced-cell-plus-matching bound is always tight for Kautz predecessor DAGs.

Related earlier work by the same author concerns literal
reverse-complement-invariant **ordinary** minimum decycling sets in q-ary de
Bruijn graphs. It is cited and explicitly separated in the manuscript; it is
not a second paper produced by this repository.

## AI assistance and verification

AI assistance was used in this research project. The public manuscript does
not record the original-development model names, versions, or attribution of
individual proof steps. OpenAI Codex assisted the pre-submission mathematical
review, computational replays and editorial preparation. These checks do not
constitute independent specialist review or proof-assistant verification.
The author remains responsible for the mathematical claims.

## Licence

Companion code and repository documentation are MIT-licensed. The manuscript
source and compiled paper are available under CC BY 4.0, with copyright
retained by the author. See [LICENSE_SCOPE.md](LICENSE_SCOPE.md)
and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
