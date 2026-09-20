# Public API status

The TressIR repository version begins at 0.1.0. Existing `sword06c.*` schema identifiers retain the historical namespace of the private pre-release project and remain unchanged for data compatibility.

## Intended public contracts

These formats are candidates for compatibility-conscious evolution:

- `sword06c.trace.v1`
- `sword06c.structure.v1`
- `sword06c.sheet.v4`
- `sword06c.depth-field.v1`
- production revision/active manifests written by `production.py`

Breaking schema changes should use a new schema identifier or provide an explicit migration path.

## Internal details

The following should not be treated as stable APIs yet:

- Blender custom-property names;
- review HTML layout;
- temporary directory names;
- private helper functions prefixed with `_`;
- exact UI labels and panel layout;
- test artifact paths.

The first public release is intentionally conservative: preserving existing data formats is more important than renaming internal v3/v4 identifiers to match the repository's 0.x release number. The public Python package is `tressir_tools`; historical `sword06c.*` schemas and current `s06c_*` Blender serialization identifiers are retained for compatibility and are not the public brand name.
