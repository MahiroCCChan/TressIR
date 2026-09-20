"""Build an installable Blender add-on ZIP from the public source tree."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "tressir_tools"
DIST = REPO / "dist"
VERSION = (REPO / "VERSION").read_text(encoding="utf-8").strip()

if not SRC.is_dir():
    raise SystemExit(f"Missing package directory: {SRC}")

DIST.mkdir(parents=True, exist_ok=True)
out = DIST / f"TressIR-Hair-Tools-{VERSION}.zip"

with ZipFile(out, "w", compression=ZIP_DEFLATED) as zf:
    for path in sorted(SRC.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        arcname = Path("tressir_tools") / path.relative_to(SRC)
        zf.write(path, arcname.as_posix())

print(out)
