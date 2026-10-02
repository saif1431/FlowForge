"""Export the API contract without starting services or loading credentials."""

import json
from pathlib import Path

from app.main import app

if __name__ == "__main__":
    target = Path(__file__).resolve().parents[2] / "frontend/openapi.json"
    target.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    print("Exported frontend/openapi.json")
