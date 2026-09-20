"""Repository preflight checks for a public TressIR release.

Run with a normal Python interpreter from anywhere:
    python scripts/preflight.py
"""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]

required = [
    "README.md",
    "README.zh-CN.md",
    "QUICKSTART.md",
    "LICENSE",
    "VERSION",
    "src/tressir_tools/__init__.py",
    "examples/minimal_build.py",
    "tests/run_blender_checks.py",
    "scripts/build_addon_zip.py",
    "scripts/install_zip_smoke_test.py",
]

forbidden_text = [
    "C:\\Users\\",
    "F:\\McpDesk",
    "apiToken",
    "GirlsFrontline",
    "Suomi reference",
]

forbidden_suffixes = {
    ".blend",
    ".blend1",
    ".blend2",
}

errors = []

for rel in required:
    if not (REPO / rel).is_file():
        errors.append(f"missing required file: {rel}")

for path in REPO.rglob("*"):
    if not path.is_file():
        continue
    rel = path.relative_to(REPO)

    if rel.as_posix() == "scripts/preflight.py":
        continue
    if any(part in {".git", "dist", "_artifacts", "__pycache__"} for part in rel.parts):
        continue

    if path.suffix.lower() in forbidden_suffixes:
        errors.append(f"unexpected Blender scene file: {rel}")

    if path.suffix.lower() == ".zip":
        errors.append(f"unexpected committed ZIP/archive: {rel}")

    if path.stat().st_size > 5_000_000:
        errors.append(f"unexpected large file (>5 MB): {rel}")

    if path.suffix.lower() in {".py", ".md", ".txt", ".json", ".toml", ".yml", ".yaml"} or path.name in {
        ".gitignore",
        "LICENSE",
        "VERSION",
    }:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"text-like file is not UTF-8: {rel}")
            continue
        for needle in forbidden_text:
            if needle.lower() in text.lower():
                errors.append(f"forbidden public-release text {needle!r} in {rel}")

if errors:
    print("TressIR public preflight: FAIL")
    for item in errors:
        print(" -", item)
    raise SystemExit(1)

print("TressIR public preflight: PASS")
print("Repository:", REPO)
print("Version:", (REPO / "VERSION").read_text(encoding="utf-8").strip())
