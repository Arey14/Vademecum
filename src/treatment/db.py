"""Conexión e inicialización de la base de tratamiento (data/treatment.db)."""
from pathlib import Path

from sqlalchemy import Engine, event
from sqlmodel import SQLModel, create_engine

from src.config import TREATMENT_DB_PATH
from src.treatment import models  # noqa: F401  (registra las tablas en el metadata)


def get_engine(path: str | Path | None = None) -> Engine:
    db_path = Path(path) if path else TREATMENT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):  # SQLite no aplica las FK por defecto
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def init_db(engine: Engine | None = None) -> Engine:
    engine = engine or get_engine()
    SQLModel.metadata.create_all(engine)
    return engine


if __name__ == "__main__":
    e = init_db()
    print(f"Base de tratamiento lista en {e.url}")
