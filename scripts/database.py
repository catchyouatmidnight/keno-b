"""Consistent SQLite backups and explicit offline restore. Use only your own backups."""
import argparse
import os
import sqlite3
import tempfile
from pathlib import Path

DB = Path(os.environ.get("KENO_DB", "/data/keno.db"))
TABLES = {"settings", "conversations", "memories", "turns"}


def snapshot(source, destination):
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst)
            dst.execute("PRAGMA journal_mode=DELETE")
    os.chmod(destination, 0o600)


def validate(path):
    if not path.is_file() or path.stat().st_size > 250_000_000:
        raise ValueError("Backup missing or larger than 250 MB")
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as c:
        if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Backup failed integrity check")
        if c.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ValueError("Unsupported backup schema version")
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables != TABLES or c.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view')").fetchone():
            raise ValueError("Unexpected database structure")
        if c.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Backup has broken references")
        if c.execute("SELECT count(*) FROM settings WHERE key IN ('profile','identity')").fetchone()[0] != 2:
            raise ValueError("Backup is missing profile or identity")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("file", type=Path)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if args.action == "backup":
        if not DB.exists():
            raise SystemExit("Database not initialized; start backend first")
        if args.file.exists():
            raise SystemExit("Destination exists; choose a new backup filename")
        snapshot(DB, args.file)
    else:
        if not args.replace:
            raise SystemExit("Restore requires explicit --replace and a stopped backend")
        validate(args.file)
        DB.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(dir=DB.parent, suffix=".restore")
        os.close(descriptor)
        temporary = Path(name)
        try:
            snapshot(args.file, temporary)
            # The backend must be stopped so there are no writers or stale WAL readers.
            for suffix in ("-wal", "-shm"):
                Path(str(DB) + suffix).unlink(missing_ok=True)
            os.replace(temporary, DB)
        finally:
            temporary.unlink(missing_ok=True)
    print(f"{args.action} complete")


if __name__ == "__main__":
    main()
