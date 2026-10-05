import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def data_dir():
    return Path(os.environ.get("STASH_DATA_DIR", str(Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "stash"))).expanduser()


def open_database(path=None):
    target = Path(path or data_dir() / "stash.db")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Preserve the old shelf while taking a consistent SQLite backup on first stash launch.
    if path is None and not target.exists() and not os.environ.get("STASH_DATA_DIR"):
        legacy = target.parent.parent / "trackle" / "trackle.db"
        if legacy.is_file():
            import sqlite3
            with sqlite3.connect(f"file:{legacy}?mode=ro", uri=True) as source, sqlite3.connect(target) as destination:
                source.backup(destination)
    engine = create_engine(f"sqlite:///{target}", connect_args={"check_same_thread": False, "timeout": 10})

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")

    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    return engine, sessionmaker(engine, expire_on_commit=False)
