# Open research questions

The geometry backend reduces one part of the problem to explicit parameters. The remaining hard problem is recovering the right structure from incomplete visual evidence.

## 2D → structure

- When is one visible region a single sheet, and when is it several overlapping parts?
- How should hidden boundaries be represented when several interpretations are plausible?
- How should monocular depth uncertainty remain explicit instead of collapsing immediately to one number?
- How can front/side/multi-view evidence be reconciled without access to the original mesh?

## Representation

- When should a sheet be replaced by a sweep, strand bundle, or another primitive?
- Can root junctions share attachment/tangent constraints without losing independent editability?
- Can parameter density adapt around roots, tips, bends, and overlap regions while remaining compact?

## Agent evaluation

A useful benchmark should control:

- target asset and reference views;
- model/operator;
- tool access;
- prompt/context;
- interaction/iteration budget;
- human feedback;
- stopping criteria.

The important comparison is not merely visual attractiveness but whether a structured representation changes the class of geometry a general-purpose agent can reliably author.

## Contributions

Experiments do not have to agree with the current representation. Negative results, alternative decompositions, and reproducible failure cases are valuable contributions.
