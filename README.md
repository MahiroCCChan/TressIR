# TressIR

TressIR is an experimental intermediate representation and lightweight browser editor for structured stylized-hair clump geometry.

The current prototype records **2D geometric evidence per hair clump** rather than automatically guessing a final 3D shape. Each clump can store:

- FRONT left boundary
- FRONT right boundary
- SIDE centerline / bend guide
- Part ID and display color

The accompanying JSON format uses the schema identifier `tressir.multiclump.trace.v1`.

## Repository layout

- `editor/TressIR_multiclump_trace_editor.html` — self-contained browser editor
- `examples/multiclump_trace_v1.json` — example multi-clump trace data

## Quick start

Open `editor/TressIR_multiclump_trace_editor.html` in a modern desktop browser.

In the editor:

1. Add or select a hair clump.
2. Choose FRONT left boundary, FRONT right boundary, or SIDE centerline.
3. Double-click to add points.
4. Drag points to edit them.
5. Export or import JSON as needed.

The current editor is intentionally evidence-oriented: it captures trace information and does not automatically reconstruct full 3D hair geometry.

## Status

Early prototype / work in progress. File organization, schemas, naming, and reconstruction logic may change.

## License

A license has not been selected yet. Add a `LICENSE` file before treating the project as reusable open-source software.
