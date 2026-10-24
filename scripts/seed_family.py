"""Populate the DB with the demo family. Run from repo root: python scripts/seed_family.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.session import init_db, session_scope  # noqa: E402
from app.db.seed import seed_demo_family  # noqa: E402

if __name__ == "__main__":
    init_db()
    with session_scope() as s:
        fam = seed_demo_family(s)
        print(f"seeded family #{fam.id} '{fam.name}' ({fam.heritage_lang}) with {len(fam.people)} people")
