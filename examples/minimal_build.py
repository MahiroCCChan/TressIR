"""Create one synthetic TressIR candidate without touching unrelated scene objects.

Run from Blender:
    blender --background --factory-startup --python examples/minimal_build.py

Or open this file in Blender's Text Editor and press Run Script.
"""
from pathlib import Path
import json
import sys
import bpy

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
PROFILE = REPO / "examples" / "profiles" / "sheet_3_tips.json"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tressir_tools import production, quality

# The geometry API does not require UI class registration. This keeps the
# example safe whether or not the add-on is already enabled.
profile = json.loads(PROFILE.read_text(encoding="utf-8"))
before = set(bpy.data.objects.keys())
obj = production.build_candidate(bpy.context, profile, "PUBLIC_EXAMPLE")
report = quality.analyze(
    [v.co[:] for v in obj.data.vertices],
    [p.vertices[:] for p in obj.data.polygons],
)

# Leave the new candidate selected for interactive users.
for item in bpy.context.selected_objects:
    item.select_set(False)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj

unrelated_preserved = before.issubset(set(bpy.data.objects.keys()))
print(
    json.dumps(
        {
            "object": obj.name,
            "vertices": len(obj.data.vertices),
            "faces": len(obj.data.polygons),
            "blocking": report["blocking"],
            "unrelated_scene_objects_preserved": unrelated_preserved,
        },
        indent=2,
    )
)

if report["blocking"] or not unrelated_preserved:
    raise RuntimeError("TressIR minimal example failed validation.")
