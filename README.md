# TressIR

**TressIR is a structured intermediate representation and deterministic geometry toolchain for LLM-assisted stylized hair authoring in Blender.**

Instead of asking a general-purpose model to directly manipulate low-level mesh geometry, TressIR exposes a smaller hair-specific representation: contours, depth fields, thickness, local ridges, part identity, and explicit overlap relations. Reviewed parameters are then compiled deterministically into editable Blender geometry.

> Public release: **0.1.0**. The geometry backend is usable. Robust single-image 2D → high-quality 3D structure recovery is still an open problem.

## Quick start

Requirements:

- Blender **5.2**
- Blender's bundled Python and NumPy
- no external Python packages for the core runtime

For the shortest first run, follow **[QUICKSTART.md](QUICKSTART.md)**.

Load TressIR from a source checkout in Blender's Python Console:

```python
import runpy
runpy.run_path(r"/absolute/path/to/TressIR/scripts/register_local.py")
```

The panel appears at:

```text
3D View → N sidebar → Hair Tools
```

Then run the included synthetic example:

```text
examples/minimal_build.py
```

It creates one TressIR candidate and does not require a private character asset.

To build an installable add-on ZIP:

```bash
python scripts/build_addon_zip.py
```

The archive is written to `dist/`. In Blender 5.2, use **Preferences → Add-ons → Install from Disk**, select the ZIP, then enable **TressIR Hair Tools** after installation.

Compatibility note: the public Python package is `tressir_tools`. Historical data schemas such as `sword06c.sheet.v4` and existing `s06c_*` Blender serialization fields are intentionally retained so pre-release assets remain readable; they are not the public project name.

## What TressIR does

A typical workflow is:

```text
reference / visual interpretation
        ↓
structured hair description
(contour, depth, thickness, ridges, overlap)
        ↓
review + fingerprinted parameters
        ↓
deterministic geometry generation
        ↓
editable Blender candidate
        ↓
validation / optional production acceptance
```

The same geometry backend can also fit a compact depth field from an existing 3D reference mesh. Measured 3D geometry and image-estimated depth are kept distinct in provenance.

The LLM/VLM used to interpret an image is external to TressIR. The core geometry backend does not require a remote inference API.

## What TressIR does not claim

TressIR is not currently:

- a general single-image 3D reconstruction model;
- a replacement for dedicated 3D-native generators;
- an automatic full-head hairstyle solver;
- a proof of global collision freedom;
- a finished grooming, rigging, or game-optimization pipeline.

Image-authored depth is treated as an estimate, not as a measurement.

## Core design

### Hair-specific representation

The connected-sheet representation keeps a 2D boundary while adding a compact 3D field for center position, half-depth, and section rotation. Named tips/notches remain explicit anchors. Shallow surface structure can be represented by ridge guides; separate overlapping clumps remain separate parts.

### Review before generation

The trace/structure workflows generate review artifacts from the same canonical parameters that later create the mesh. Source, input, and reviewed profile fingerprints are checked again at generation time, so a stale preview cannot be reused after edits.

### Recoverable production assets

Accepted parts are saved as immutable parameter revisions. TressIR checks that serialized parameters and supported guides can reconstruct the evaluated geometry before committing an asset. Unsupported direct mesh edits, unsupported modifiers, and tampered revisions are rejected rather than silently recorded as reconstructable.

## Included examples

Portable JSON examples live in `examples/profiles/`:

- `sheet_2_tips.json`
- `sheet_3_tips.json`
- `sheet_5_tips.json`
- `measured_field_sheet.json` — synthetic depth-field fixture
- `legacy_clump.json` — synthetic compatibility fixture

These examples do not require a third-party character model.

## Main modules

| Module | Responsibility |
| --- | --- |
| `sheet_v4.py` | connected-sheet representation and mesh generation |
| `fields.py` | compact B-spline depth-field fitting and evaluation |
| `trace.py` | reviewed image-contour → canonical profile workflow |
| `structure.py` | multi-part structure, estimated depth, ridges, overlap declarations |
| `production.py` | candidate/active/archive lifecycle, immutable revisions, restore |
| `quality.py` | topology and region-aware mesh diagnostics |
| `blender_ops.py` | Blender object creation, rebuild, guides, reference fitting |

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the full flow.

## Validation

The development test suite covers geometry generation, compact depth fitting, stale-review invalidation, topology diagnostics, reconstructability checks, immutable revision checksums, rollback, fresh-process restore, and finite sampled overlap relations.

The public repository contains:

- `scripts/smoke_test.py` — small background-Blender smoke test;
- `tests/run_blender_checks.py` — broader reusable-tool verification;
- `scripts/preflight.py` — repository release hygiene checks.

See **[docs/VALIDATION.md](docs/VALIDATION.md)** for what these tests do and do not establish.

## Known limits

The current sheet model is strongest for stylized bangs, side locks, and moderately curved connected sheets. Hooks, near-horizontal roots, severe twists, and geometry that is not locally representable as the current graph-like sheet may require splitting, local reorientation, or a different primitive.

Finite overlap sampling is a diagnostic, not a proof of global collision freedom. Technical mesh validity is not the same as artistic approval.

See **[docs/LIMITATIONS.md](docs/LIMITATIONS.md)**.

## Open problem: 2D → structure

The main research frontier is reliable recovery of structured 3D hair descriptions from incomplete 2D evidence.

Questions include:

- when should one visible region become one sheet versus multiple overlapping sheets?
- how should hidden boundaries and depth uncertainty remain explicit?
- when should the current sheet primitive be replaced by a sweep/strand/other primitive?
- can multiple views be reconciled into one structure without access to the original mesh?

See **[docs/RESEARCH_QUESTIONS.md](docs/RESEARCH_QUESTIONS.md)** and **[benchmarks/README.md](benchmarks/README.md)**.

## Repository policy

This public repository intentionally excludes private research history and third-party character assets. See **[THIRD_PARTY.md](THIRD_PARTY.md)**.

## License

TressIR is released under the **MIT License**. See **[LICENSE](LICENSE)**.
