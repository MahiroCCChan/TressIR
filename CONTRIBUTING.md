# Contributing

TressIR is currently an early research-engineering project. Contributions that improve reproducibility, representation design, validation, or 2D-to-structure recovery are welcome.

## Good contribution areas

- reproducible Blender bugs and fixes;
- new legal-to-redistribute synthetic/reference fixtures;
- stronger geometry validation;
- alternative hair primitives or representation experiments;
- better 2D/multi-view structure recovery frontends;
- benchmark harnesses and controlled direct-Blender baselines;
- documentation and portability improvements.

## Before opening a pull request

1. Do not include proprietary character models, game assets, textures, or reference art without redistribution rights.
2. Keep measured 3D evidence separate from image-inferred estimates.
3. Do not report finite sampled overlap checks as global collision proofs.
4. Add or update a reproducible test when changing geometry or production-state behavior.
5. Keep private paths, credentials, API tokens, and local relay configuration out of commits.

## Design principle

Prefer explicit, inspectable parameters and deterministic geometry over hidden defaults. When the system does not know something, represent uncertainty or require an explicit estimate instead of silently inventing a measurement.
