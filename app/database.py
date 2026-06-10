from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, future=True, connect_args=connect_args)
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True))


def _add_column_if_missing(table_name, column_name, ddl_sqlite, ddl_postgres):
    inspector = inspect(engine)
    try:
        columns = {col["name"] for col in inspector.get_columns(table_name)}
    except Exception:
        return
    if column_name not in columns:
        with engine.begin() as conn:
            conn.execute(text(ddl_postgres if engine.dialect.name == "postgresql" else ddl_sqlite))


def _ensure_columns():
    _add_column_if_missing(
        "impregnations",
        "external_only",
        "ALTER TABLE impregnations ADD COLUMN external_only BOOLEAN DEFAULT 0",
        "ALTER TABLE impregnations ADD COLUMN external_only BOOLEAN DEFAULT FALSE",
    )
    _add_column_if_missing(
        "process_runs",
        "user_id",
        "ALTER TABLE process_runs ADD COLUMN user_id INTEGER",
        "ALTER TABLE process_runs ADD COLUMN user_id INTEGER",
    )


def init_db():
    from . import models

    Base.metadata.create_all(bind=engine)
    _ensure_columns()
