"""Export the API's OpenAPI document (the frontend's typed API contract).

Usage (from backend/): .venv/bin/python ../scripts/export_openapi.py ../docs/openapi.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.main import app  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
out.write_text(json.dumps(app.openapi(), indent=2) + "\n")
print(f"wrote {out} ({len(app.openapi()['paths'])} paths)")
