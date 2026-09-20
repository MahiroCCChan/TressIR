# Known limitations

These limits are part of the current model, not merely missing UI polish.

## Geometry representation

The connected sheet is a constrained local surface family. It works best for stylized bangs, side locks, and moderately curved clumps.

Weak cases include:

- hooks and strong return curls;
- near-horizontal roots;
- sections near the representation's vertical singularity;
- geometry that requires multiple depth values for the same local graph coordinate;
- highly intertwined strand bundles;
- topology that should naturally be represented as a sweep/strand rather than a sheet.

The preferred response is to split, reorient, or use another primitive rather than forcing every shape into one sheet.

## Multi-part continuity

Parts can have explicit front/back relations, but current overlap constraints do not solve root continuity or shared scalp-flow constraints. Natural junctions between several clumps remain an open modeling problem.

## Collision checking

Overlap checks use finite projected sampling. Passing them means the declared sampled relation passed at the stated resolution. It does not prove global absence of intersections.

## Image interpretation

The software can enforce that an image-authored depth field is explicitly marked as estimated, but it cannot guarantee that the interpretation is visually or physically correct.

A wrong segmentation, hidden-boundary guess, or part decomposition can therefore produce a technically valid but semantically wrong mesh.

## Artistic quality

Closed/manifold geometry is not equivalent to a good hairstyle. Final silhouette, root design, flow, spacing, animation, material response, and game-ready optimization still require artistic/production evaluation.

## Production scope

The current parameter assets do not attempt to serialize a full character rig, material/texture package, grooming simulation, or final engine asset.
