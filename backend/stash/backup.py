"""Consistent database backup; never copies a live SQLite file directly."""
import argparse
from pathlib import Path
import sqlite3
from .db import data_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--database", type=Path, default=data_dir() / "stash.db")
    args = parser.parse_args()
    if args.destination.exists():
        parser.error("Destination already exists")
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{args.database.resolve()}?mode=ro", uri=True) as source, sqlite3.connect(args.destination) as target:
        source.backup(target)
    print(args.destination)
    print("Shelf registry/settings backed up. Back up project folders including .stash separately.")


if __name__ == "__main__":
    main()
