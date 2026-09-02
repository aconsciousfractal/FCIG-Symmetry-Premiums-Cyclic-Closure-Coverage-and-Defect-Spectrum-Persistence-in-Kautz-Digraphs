# Reproducibility boundary

## What the released software recomputes

- `36 -> 46,656 -> 987 -> 54,078 -> 1,759 -> 83,736`: local states, source
  triples, source orbits, search nodes, representative masks, and labelled
  masks;
- exact equality between the reconstructed 83,736-mask set and the shipped
  membership rows;
- every mask-to-class assignment by centralizer expansion;
- 3,518 opposed Bellman tables, explicit optimal orders, and the class/mask
  defect histograms
  `445,555,420,297,42` and `20,976,26,640,19,896,14,208,2,016`;
- one exact finite witness for each defect `0,1,2,3,4`;
- the domain profile of the four-letter rank-three control (ten cover
  relations, exactly two Kautz arcs and eight non-Kautz covers), all 99,000
  linear extensions, its 176 attained bad-cell sets, and its unique minimal
  three-cell obstruction;
- all 24 ten-relation-core classes and all 1,152 labelled members;
- the two exact jump-three facet counterexamples and the 90-flip bounded panel.

All scientific checkers use the Python standard library. pypdf and pytest are
needed only for release inspection and tests. The standard-library bootstrap
parses `requirements.lock` and refuses to run unless its complete distribution
and version map is identical to the lock.

## Independence qualification

Population reconstruction is independent of the frozen population data and
is label-independent, but it uses the released quotient-native enumeration
kernel. It is not represented as a second independently designed enumerator.
The tracked mask rows are opened only after reconstruction and are used for an
exact post-hoc set and assignment comparison.

The Bellman checker authenticates and recomputes every shipped table; it does
not access a historical SQLite database or a private custody chain. The
ten-relation checker discovers occurrences before verifying their optimum
scores and does not use a stored defect-label oracle.

## What the software does not establish

The package does not computationally prove the all-parameter premium,
coverage, extension, monotonicity, or obstruction-clutter theorems. Those are
written arguments in the manuscript. Nor does it compute the global
six-letter facet graph, settle novelty, close unavailable literature, or
settle tightness of the forced-cell/matching bound inside the Kautz
predecessor-DAG subclass.

`MANIFEST_SHA256.txt` authenticates the environment-independent source and
data surface. `RELEASE_SHA256.txt` additionally authenticates the committed
PDF. Binary files are ordinary Git blobs and are explicitly excluded from LFS
filters.
