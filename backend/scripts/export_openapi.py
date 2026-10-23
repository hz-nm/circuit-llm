"""Write the API's OpenAPI schema to ``frontend/openapi.json`` (used to generate TS types)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from circuits_llm.api import create_app
from circuits_llm.settings import Settings

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Settings(data_dir=Path(tmp)))
        schema = app.openapi()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
