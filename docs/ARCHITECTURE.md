# Architecture

TressIR separates perception/interpretation from deterministic geometry.

## Layers

```text
External human / VLM interpretation
            │
            ├── trace.v1      single connected contour interpretation
            └── structure.v1  multi-part structure + overlap declarations
            │
            ▼
Canonical sheet.v4 profiles
            │
            ├── 2D boundary + named anchors
            ├── compact depth field
            ├── shell / edge thickness
            ├── ridge guides
            └── provenance/history
            │
            ▼
Deterministic mesh generator
            │
            ▼
Blender candidate object
            │
            ├── parametric edits
            ├── owned Surface Deform / Lattice guides
            └── mesh/depth-order checks
            │
            ▼
Production acceptance
            │
            ├── reconstructability verification
            ├── evaluated mesh hash
            ├── immutable revision JSON + checksum
            └── active manifest / optional blend checkpoint
```

## Why an intermediate representation?

A general-purpose LLM can often describe visible structure more reliably than it can author thousands of low-level mesh coordinates while simultaneously maintaining topology, curvature, editability, and scene state.

TressIR therefore narrows the action space to hair-specific semantic controls and lets deterministic code own triangulation, shell construction, validation, and reconstruction.

## Trace and structure workflows

`trace.py` compiles an authored contour interpretation to a canonical profile and produces a review overlay. Generation verifies the source image, trace document, and reviewed profile fingerprints before using that exact profile.

`structure.py` extends the same idea to multiple independently editable parts. Each part must have an explicit role, explicit estimated depth with a reason, explicit ridge declaration, and a surface note. Overlap relations are declared separately and checked on a finite projected grid.

## Depth field

The current compact field models:

- section center X;
- section center Y;
- positive half-depth;
- section rotation.

The field uses a clamped cubic B-spline. Smooth fitting includes a curvature penalty; robust reweighting reduces sensitivity to noisy measurements. Half-depth is fit in log space to preserve positivity. Section rotation is unwrapped with π-period semantics.

The representation deliberately rejects sections too close to the singular orientation of its graph-like parameterization rather than allowing numerical blow-up.

## Production assets

A saved revision is accepted only if the serialized parameters and supported owned guides can reconstruct the evaluated geometry. Direct unrecorded vertex edits, shape keys, weighted vertex groups, or unsupported enabled modifiers cause the acceptance step to refuse a false reconstructability claim.

Revision files are immutable and checksummed. The active manifest is replaced atomically.
