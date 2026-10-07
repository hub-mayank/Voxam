"""Write db/schema.sql (PostgreSQL DDL) from the SQLAlchemy models. A test fails if the committed file differs.
Usage: python scripts/export_schema.py"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))

from app.db.ddl import postgres_ddl  # noqa: E402

out = root / "db" / "schema.sql"
out.write_text(postgres_ddl())
print(f"wrote {out}")
