# Public release audit — 0.1.0

## Extracted into this repository

- reusable TressIR geometry/tooling core;
- portable synthetic/profile fixtures;
- a minimal first-run example;
- portable loading, packaging, smoke-test, install-test, and release-preflight scripts;
- public documentation focused on installation, architecture, limits, and validation.

## Intentionally excluded

- third-party character assets and textures;
- private references;
- private `runs/` and exploratory scripts;
- `history/`, old handoff bundles, and archived ZIPs;
- v3 example .blend files;
- private Sword06 visual-relay configuration/integration;
- generated .blend checkpoints;
- internal result JSON containing absolute machine paths.

## Release checks

- [x] MIT source-code license added.
- [x] Public core extracted into a separate repository.
- [x] Local machine paths, Windows username, private relay token fields, and known third-party character names removed from public source/docs/examples.
- [x] Public fixtures selected or rewritten to avoid private character/reference provenance.
- [x] No .blend, cached Python bytecode, or prebuilt archive is intended to be committed.
- [x] User-facing `QUICKSTART.md` and `examples/minimal_build.py` added.
- [x] Repository preflight passed on Blender 5.2.0 LTS.
- [x] Background smoke test passed: add-on registered; synthetic candidate generated with 2100 vertices / 4196 faces; no blocking mesh issues.
- [x] Full reusable-tool verification passed.
- [x] Fresh-process restore passed for both tested accepted-part kinds; second restore added zero objects.
- [x] Final add-on ZIP built from `scripts/build_addon_zip.py`.
- [x] ZIP installed into an isolated fresh Blender user profile.
- [x] Installed add-on enabled successfully; panel class registered; synthetic candidate generated with no blocking mesh issues.
- [x] Unrelated factory-scene objects were preserved in smoke/install checks.

## Final release artifact

`dist/TressIR-Hair-Tools-0.1.0.zip`

- size: 58,434 bytes
- SHA-256: `1730971dc643f58b451dd4301667efd7083b3112ef0427decd22265f2060aee9`
- tested with Blender 5.2.0 LTS (build hash `fbe6228777e7`)

The `dist/` directory is ignored by Git; publish the ZIP separately as a GitHub Release asset if desired.

## Media

The first release does not require screenshots or third-party reference artwork. Media can be added later when redistribution rights are clear.

## Claim policy

Safe current description:

> TressIR is a structured intermediate representation and deterministic geometry toolchain for LLM-assisted stylized hair authoring in Blender.

Do not claim that TressIR provides robust general single-image high-quality 3D hair reconstruction. The 2D-to-structure frontend remains an open problem.
