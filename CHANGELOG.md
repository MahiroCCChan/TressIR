# Changelog

## 0.1.0

First public release candidate.

- Extracted the reusable geometry/tooling core from the private Sword06C research workspace and published it as TressIR.
- Renamed the public add-on/package surface to `TressIR` / `tressir_tools` while retaining historical `sword06c.*` data schemas for compatibility.
- Added portable loading and add-on packaging scripts.
- Added public documentation for architecture, validation scope, limitations, and open research questions.
- Added synthetic/profile examples that do not depend on private character assets.
- Excluded private relay integration, historical runs, proprietary character assets, old handoff bundles, and local machine paths from the public core.

Internal schema names such as `sword06c.sheet.v4` are preserved for compatibility; the public repository version starts at 0.1.0.
