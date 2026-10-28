"""Generate the JSON Schemas in data/schemas/ from the Pydantic contracts (D-008).

The schemas are build output: edit the models in src/claimsense/contracts/, then rerun this.

Usage:
    python scripts/generate_schemas.py          # write data/schemas/*.schema.json
    python scripts/generate_schemas.py --check  # fail if the files on disk are out of date
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from claimsense.contracts import SCHEMA_MODELS  # noqa: E402

OUT = ROOT / "data" / "schemas"


def schemas() -> dict[str, str]:
    """Return {file name: schema text} for every published contract."""
    return {f"{name}.schema.json": json.dumps(model.model_json_schema(), indent=2) + "\n"
            for name, model in SCHEMA_MODELS.items()}


def main(argv: list[str]) -> int:
    stale = []
    for name, text in schemas().items():
        path = OUT / name
        if "--check" in argv:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
    if stale:
        print(f"out of date, run scripts/generate_schemas.py: {', '.join(stale)}")
        return 1
    if "--check" not in argv:
        print(f"wrote {len(SCHEMA_MODELS)} schemas to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
