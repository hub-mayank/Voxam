"""Write the API contract to docs/openapi.json. A test fails if the committed file differs from this output.
Usage: python scripts/export_openapi.py   (use --check to only compare)"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))

from app.api.main import create_app, openapi_json  # noqa: E402
from app.api.settings import Settings  # noqa: E402

out = root / "docs" / "openapi.json"
text = openapi_json(create_app(Settings({}, contract_stub=True)))
if "--check" in sys.argv:
    sys.exit(0 if out.exists() and out.read_text() == text else "docs/openapi.json is out of date: run scripts/export_openapi.py")
out.write_text(text)
print(f"wrote {out} ({len(text)} bytes)")
