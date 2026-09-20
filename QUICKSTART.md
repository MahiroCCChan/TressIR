# TressIR quick start

This is the shortest path from a source checkout to a generated TressIR hair-sheet candidate.

## 1. Requirements

- Blender 5.2
- No external Python packages

## 2. Load the add-on from the checkout

Open Blender → **Scripting** → Python Console and run:

```python
import runpy
runpy.run_path(r"/absolute/path/to/TressIR/scripts/register_local.py")
```

You should see the panel at:

```text
3D View → N sidebar → Hair Tools
```

Loading the add-on does not open, reset, or overwrite the current scene.

## 3. Generate the included example

The safest first test is the synthetic profile example.

In Blender's Scripting workspace, open:

```text
examples/minimal_build.py
```

and press **Run Script**.

It creates one object named like:

```text
TRESSIR_CANDIDATE_PUBLIC_EXAMPLE
```

The script does not delete unrelated scene objects.

## 4. Import a profile through the UI

In **Hair Tools**:

1. set a Part ID;
2. click **Import JSON as candidate**;
3. choose one of the files in `examples/profiles/`;
4. inspect/edit the candidate;
5. use **Check mesh quality** before accepting production assets.

## 5. Use your own image

TressIR does not automatically solve single-image 3D reconstruction. The image workflow is:

```text
image
→ explicit trace / structure JSON
→ review overlay
→ generate the reviewed parameters
→ adjust depth / guides in Blender
```

The relevant modules and prompts are:

- `trace.py` + `LLM_TRACE_PROMPT.txt`
- `structure.py` + `LLM_STRUCTURE_PROMPT.txt`

The LLM/VLM that fills those files is external to TressIR.

## 6. Build an installable ZIP

From the repository root with a normal Python interpreter:

```bash
python scripts/build_addon_zip.py
```

The resulting ZIP appears in `dist/`. In Blender 5.2, open **Preferences → Add-ons → Install from Disk**, select the ZIP, then enable **TressIR Hair Tools**. Installing a legacy add-on does not automatically enable it.

## Something broke?

Open an issue with:

- Blender version;
- TressIR commit/version;
- the smallest JSON input that reproduces the problem;
- traceback/error text.

Do not upload proprietary character models just to report a bug.
