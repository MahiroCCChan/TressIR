"""Install the built TressIR ZIP into a fresh Blender user profile and smoke-test it."""
from pathlib import Path
import json
import sys
import bpy

REPO = Path(__file__).resolve().parents[1]
DIST = REPO / "dist"
zips = sorted(DIST.glob("TressIR-Hair-Tools-*.zip"))
if not zips:
    raise RuntimeError("No built TressIR add-on ZIP found in dist/.")
ZIP = zips[-1]

print("INSTALL_ZIP", ZIP)

# Legacy add-on install path used by Blender's Add-ons preferences.
result_install = bpy.ops.preferences.addon_install(filepath=str(ZIP), overwrite=True)
print("ADDON_INSTALL", result_install)

result_enable = bpy.ops.preferences.addon_enable(module="tressir_tools")
print("ADDON_ENABLE", result_enable)

addon_entry = bpy.context.preferences.addons.get("tressir_tools")
if addon_entry is None:
    raise RuntimeError("TressIR was not present in enabled add-ons after installation.")

import tressir_tools
from tressir_tools import production, quality

if not hasattr(bpy.types, "S06C_PT_tools"):
    raise RuntimeError("TressIR panel class was not registered.")

profile_path = REPO / "examples" / "profiles" / "sheet_3_tips.json"
profile = json.loads(profile_path.read_text(encoding="utf-8"))
before = set(bpy.data.objects.keys())
obj = production.build_candidate(bpy.context, profile, "INSTALL_SMOKE")
report = quality.analyze(
    [v.co[:] for v in obj.data.vertices],
    [p.vertices[:] for p in obj.data.polygons],
)

summary = {
    "zip": str(ZIP),
    "module": tressir_tools.__name__,
    "version": list(tressir_tools.bl_info.get("version", ())),
    "panel_registered": hasattr(bpy.types, "S06C_PT_tools"),
    "candidate": obj.name,
    "vertices": len(obj.data.vertices),
    "faces": len(obj.data.polygons),
    "blocking": report["blocking"],
    "unrelated_scene_objects_preserved": before.issubset(set(bpy.data.objects.keys())),
}
print("TRESSIR_INSTALL_SMOKE", json.dumps(summary, sort_keys=True))

if summary["blocking"] or not summary["unrelated_scene_objects_preserved"]:
    raise RuntimeError("Installed TressIR package failed geometry smoke test.")
