"""Load/reload TressIR from this source checkout without changing the current scene."""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"

previous = sys.modules.get("tressir_tools")
if previous and hasattr(previous, "unregister"):
    previous.unregister()

for name in list(sys.modules):
    if name == "tressir_tools" or name.startswith("tressir_tools."):
        del sys.modules[name]

if str(SRC) in sys.path:
    sys.path.remove(str(SRC))
sys.path.insert(0, str(SRC))

import tressir_tools

tressir_tools.register()
print(f"TressIR loaded from {SRC}. Current scene preserved.")
