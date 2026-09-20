"""Background reference preparation/preview for a source checkout."""
import argparse
import json
import sys
from pathlib import Path

import bpy

if not bpy.app.background:
    raise RuntimeError("Use the UI/Python API in an interactive Blender session, or run Blender with --background.")

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
sys.path.insert(0, str(SRC))

from tressir_tools import trace

parser = argparse.ArgumentParser()
parser.add_argument("action", choices=["prepare", "preview"])
parser.add_argument("--image")
parser.add_argument("--out")
parser.add_argument("--trace")
parser.add_argument("--part", default="PART01")
parser.add_argument("--height-mm", type=float, default=100)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])

if args.action == "prepare":
    if not args.image or not args.out:
        parser.error("prepare requires --image and --out")
    result = trace.prepare(args.image, args.out, args.part, args.height_mm)
else:
    if not args.trace:
        parser.error("preview requires --trace")
    result = trace.preview(args.trace, args.out)

print(json.dumps(result, ensure_ascii=False))
