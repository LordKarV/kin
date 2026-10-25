"""Save the seeded demo database, and put it back between judges.

Every card shown and every bridge told changes what KIN thinks each person knows, so the table demo only works the
first time. `save` right after seeding; `restore` after each judge's call has hung up. Uses SQLite's online backup,
so the backend can keep running and the phones keep their sign-in tokens (they live in the same database). Do not
restore while a call or a ring is in progress.

    cd backend && .venv/bin/python ../scripts/demo_snapshot.py save
    cd backend && .venv/bin/python ../scripts/demo_snapshot.py restore
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def copy(src: Path, dst: Path) -> None:
    """Page-by-page copy that waits out the server's locks; dst ends up identical to src."""
    a, b = sqlite3.connect(src), sqlite3.connect(dst)
    try:
        a.backup(b)
    finally:
        a.close()
        b.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["save", "restore"])
    ap.add_argument("--db", type=Path, default=BACKEND / "kin.db", help="the database the backend uses")
    ap.add_argument("--snapshot", type=Path, default=BACKEND / "kin.demo-snapshot.db")
    args = ap.parse_args()
    src, dst = (args.db, args.snapshot) if args.action == "save" else (args.snapshot, args.db)
    if not src.exists():
        sys.exit(f"{src} does not exist" + (" (run save after seeding first)" if args.action == "restore" else ""))
    copy(src, dst)
    print(f"{args.action}d: {src} -> {dst}")


if __name__ == "__main__":
    main()
