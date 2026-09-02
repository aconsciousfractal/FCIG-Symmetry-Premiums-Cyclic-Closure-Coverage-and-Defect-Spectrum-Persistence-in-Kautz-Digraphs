# Reproducing the package

## Supported environment

- CPython 3.12, 3.13, or 3.14 on x86-64 Windows or Linux;
- packages and hashes from `requirements.lock`;
- Git 2.39 or newer;
- LuaLaTeX, BibTeX, and latexmk for the paper;
- Poppler and pypdf 6.14.2 for independent PDF inspection.

The scientific checkers are standard-library only. Package installation is
needed for pytest and PDF/release inspection and may access the package index;
the replay itself is offline.

## Install

```bash
python -m pip install --require-hashes -r requirements.lock
```

## Exact replay

PowerShell:

```powershell
$PythonAbsolute = (Get-Command python).Source
$GitAbsolute = (Get-Command git).Source
& $PythonAbsolute -I -S -B scripts/runtime_bootstrap.py `
  --git-executable $GitAbsolute --target scripts/verify.py
& $PythonAbsolute -I -S -B -O scripts/runtime_bootstrap.py `
  --git-executable $GitAbsolute --target scripts/verify.py
```

POSIX:

```bash
PYTHON_ABSOLUTE=$(python -I -S -c 'import sys; print(sys.executable)')
GIT_ABSOLUTE=$(command -v git)
"$PYTHON_ABSOLUTE" -I -S -B scripts/runtime_bootstrap.py \
  --git-executable "$GIT_ABSOLUTE" --target scripts/verify.py
"$PYTHON_ABSOLUTE" -I -S -B -O scripts/runtime_bootstrap.py \
  --git-executable "$GIT_ABSOLUTE" --target scripts/verify.py
```

Both commands must end with `PASS`. The verifier is bound to the current
clean Git tree, accepts ordinary Git history, and writes no result file.

For transparent direct replay, the six lanes are:

```bash
python -B companion/verify_five_defect_witnesses.py
python -B companion/verify_population.py
python -B companion/verify_bellman_bundle.py
python -B companion/verify_rank_three_obstruction.py
python -B companion/verify_ten_relation_core.py
python -B companion/verify_facet_counterexample.py
```

Repeat with `python -B -O` to confirm optimization-safe validation. The
population and Bellman lanes are intentionally sequential because both read
the multi-megabyte finite package.

## Hostile tests

```bash
python -I -S -B scripts/runtime_bootstrap.py --git-executable git \
  --module pytest -- -q -p no:cacheprovider \
  --basetemp /tmp/kautz-symmetry-pytest \
  tests/test_kautz_symmetry.py tests/test_release_assurance.py
```

An optimized pytest run is a compatibility smoke test only; ordinary Python
`assert` statements in test bodies are intentionally removed by `-O`.

## Integrity layers

```bash
python -I -S -B scripts/runtime_bootstrap.py --git-executable git --target scripts/check_manifest.py
python -I -S -B scripts/runtime_bootstrap.py --git-executable git --target scripts/check_release.py
```

`MANIFEST_SHA256.txt` covers every environment-independent public file except
itself, `RELEASE_SHA256.txt`, and the compiled PDF. The release manifest pins
the source manifest and title-named PDF. The release checker rejects undeclared
files, symlinks/reparse points, LFS pointers or filters, private production
residue, unsafe PDF content, object-store redirection, and a dirty checkout.

## Deterministic paper build

Run from `paper/` on Windows:

```powershell
$env:SOURCE_DATE_EPOCH = "1788307200"
$env:FORCE_SOURCE_DATE = "1"
$Stem = "Symmetry-Premiums-Cyclic-Closure-Coverage-and-Defect-Spectrum-Persistence-in-Kautz-Digraphs"
lualatex -interaction=nonstopmode -halt-on-error -file-line-error "-jobname=$Stem" main.tex
bibtex $Stem
lualatex -interaction=nonstopmode -halt-on-error -file-line-error "-jobname=$Stem" main.tex
lualatex -interaction=nonstopmode -halt-on-error -file-line-error "-jobname=$Stem" main.tex
```

On POSIX:

```bash
SOURCE_DATE_EPOCH=1788307200 FORCE_SOURCE_DATE=1 \
latexmk -lualatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex
```

Build in two clean temporary copies and require byte equality. Then inspect
every rendered page, font, link, metadata field, and extracted-text page. The
committed output is:

`paper/Symmetry-Premiums-Cyclic-Closure-Coverage-and-Defect-Spectrum-Persistence-in-Kautz-Digraphs.pdf`

## Clean-clone verification

Clone the exact candidate into a fresh temporary directory, install the locked
environment, run both aggregate replays and the hostile suite, build twice,
compare PDF bytes and semantics, and require `git status --porcelain` to remain
empty. No remote, push, tag, release, preprint, or submission is created by
these instructions.

## Limits

The finite replay certifies the released census and examples. It does not
replace the manuscript's all-parameter proofs, compute the global facet graph,
or establish novelty, priority, exhaustive source coverage, or PDF/UA
conformance.
