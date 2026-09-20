"""Small public-release smoke test. Run only in a separate background Blender."""
from pathlib import Path
import json
import sys

import bpy

if not bpy.app.background:
    raise RuntimeError("Run this test with Blender --background --factory-startup.")

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
PROFILE = REPO / "examples" / "profiles" / "sheet_3_tips.json"
sys.path.insert(0, str(SRC))

import tressir_tools as addon
from tressir_tools import production, quality

addon.register()
before = set(bpy.data.objects.keys())
profile = json.loads(PROFILE.read_text(encoding="utf-8"))
obj = production.build_candidate(bpy.context, profile, "SMOKE")
report = quality.analyze(
    [v.co[:] for v in obj.data.vertices],
    [p.vertices[:] for p in obj.data.polygons],
)

result = {
    "addon_registered": True,
    "object_created": obj.name,
    "vertices": len(obj.data.vertices),
    "faces": len(obj.data.polygons),
    "blocking": report["blocking"],
    "unrelated_scene_objects_preserved": before.issubset(set(bpy.data.objects.keys())),
}
print("TRESSIR_SMOKE", json.dumps(result, sort_keys=True))

if result["blocking"] or not result["unrelated_scene_objects_preserved"]:
    raise RuntimeError("Public smoke test failed.")
