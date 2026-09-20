# Validation scope

TressIR development includes executable checks for geometry generation, parameter fitting, scene-state safety, and production recovery.

## Confirmed classes of checks in the private development workspace

### Geometry

- 2-, 3-, and 5-tip connected outlines generate closed shells in the tested fixtures.
- Named 2D feature anchors survive canonicalization with near-zero projection error in tested fixtures.
- Duplicate faces, non-manifold edges, boundary edges, inconsistent winding, and degenerate triangles are diagnosed.
- Invalid/self-crossing outlines and negative half-depth inputs are rejected.

### Depth-field fitting

A synthetic noisy field test reduced RMS error from approximately 1.862 mm to 0.259 mm with the tested fit settings while preserving endpoint constraints and positive thickness.

This is a **synthetic fitting test**, not a claim about image-to-3D reconstruction accuracy.

### Review integrity

- changing a trace document after preview invalidates generation;
- changing the source image after preview invalidates generation;
- changing the reviewed canonical profile after preview invalidates generation;
- generation uses the exact reviewed profile rather than re-running a stochastic interpretation step.

### Production state

- accepted revisions are immutable and checksummed;
- a tampered revision is rejected;
- simulated interruption before active-manifest replacement leaves the previous manifest intact;
- failed candidate/guide/group construction is rolled back;
- unsupported unrecorded mesh edits are rejected as non-reconstructable;
- supported parameter/guide edits can be restored in a fresh Blender process.

### Overlap relations

Declared local front/back relations are checked through finite projected sampling. Tests include both passing and intentionally incorrect depth arrangements.

This is a diagnostic constraint, not a global collision proof.

## What these tests do not establish

They do not establish:

- automatic full-head design quality;
- correctness of monocular image depth;
- generalization across hairstyle categories;
- equivalence to a professional groom;
- global collision freedom;
- animation/rigging correctness.

## Public test conversion

The public release copies the reusable core but intentionally does not copy private reference images or character assets. The portable verification harness lives under `tests/`. Clean-machine validation for version 0.1.0 was completed on Blender 5.2.0 LTS; see `RELEASE_AUDIT.md` for the recorded release checks. Future release changes should rerun the public verification before publishing.
