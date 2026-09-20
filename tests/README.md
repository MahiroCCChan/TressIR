# Public Blender verification

The core verification script must run in a separate background Blender process. It uses synthetic/profile fixtures only and must not be run against an active user scene.

From the repository root:

```bash
blender --background --factory-startup --python-exit-code 1 --python tests/run_blender_checks.py
```

Then verify reconstruction in a fresh Blender process:

```bash
blender --background --factory-startup --python-exit-code 1 --python tests/run_blender_checks.py -- --restore-only
```

Artifacts are written under `tests/_artifacts/` and are ignored by Git.

Clean-machine verification for version 0.1.0 was completed on Blender 5.2.0 LTS. See `RELEASE_AUDIT.md` for the recorded release checks. Future release changes should rerun both verification commands above before publishing.
