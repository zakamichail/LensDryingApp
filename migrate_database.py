import argparse
import os
from pathlib import Path

from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.orm import sessionmaker

from app.config import DATA_DIR
from app.models import AuditLog, Impregnation, Material, ProcessRun, User


SQLITE_URL = f"sqlite:///{DATA_DIR / 'lens_drying.sqlite3'}"
POSTGRES_URL = os.getenv(
    "POSTGRES_DATABASE_URL",
    "postgresql+psycopg://lens_user:lens_password@localhost:5432/lens_drying",
)

TABLES = [User, Material, Impregnation, ProcessRun, AuditLog]


def _engine(url):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, future=True, connect_args=connect_args)


def _count(session, model):
    return session.scalar(select(func.count()).select_from(model)) or 0


def _row_payload(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _reset_postgres_sequences(session, tables):
    if session.bind.dialect.name != "postgresql":
        return
    for model in tables:
        table = model.__tablename__
        pk = next(iter(model.__table__.primary_key.columns)).name
        session.execute(
            text(
                "SELECT setval("
                "pg_get_serial_sequence(:table_name, :pk_name), "
                f"COALESCE((SELECT MAX({pk}) FROM {table}), 1), "
                f"(SELECT COUNT(*) > 0 FROM {table})"
                ")"
            ),
            {"table_name": table, "pk_name": pk},
        )


def migrate(source_url, target_url, replace=False, dry_run=False):
    source_engine = _engine(source_url)
    target_engine = _engine(target_url)
    SourceSession = sessionmaker(bind=source_engine, future=True)
    TargetSession = sessionmaker(bind=target_engine, future=True)

    with SourceSession() as source, TargetSession() as target:
        source_counts = {model.__tablename__: _count(source, model) for model in TABLES}
        target_counts = {model.__tablename__: _count(target, model) for model in TABLES}
        print("Источник:", source_url)
        print("Приемник:", target_url)
        print("Строки источника:", source_counts)
        print("Строки приемника до миграции:", target_counts)

        if dry_run:
            print("Пробный запуск: данные не изменялись.")
            return

        non_empty = {name: count for name, count in target_counts.items() if count}
        if non_empty and not replace:
            raise SystemExit(
                "Приемник не пустой. Добавьте --replace, если нужно заменить его содержимое: "
                + str(non_empty)
            )

        for model in reversed(TABLES):
            target.execute(delete(model))
        target.flush()

        for model in TABLES:
            rows = source.scalars(select(model).order_by(model.id)).all()
            target.add_all(model(**_row_payload(row)) for row in rows)
            target.flush()

        _reset_postgres_sequences(target, TABLES)
        target.commit()

        final_counts = {model.__tablename__: _count(target, model) for model in TABLES}
        print("Строки приемника после миграции:", final_counts)


def main():
    parser = argparse.ArgumentParser(description="Миграция данных между SQLite и PostgreSQL.")
    parser.add_argument(
        "direction",
        choices=["sqlite-to-postgres", "postgres-to-sqlite"],
        help="Направление миграции.",
    )
    parser.add_argument("--replace", action="store_true", help="Очистить приемник перед переносом.")
    parser.add_argument("--dry-run", action="store_true", help="Показать счетчики без изменения данных.")
    args = parser.parse_args()

    if args.direction == "sqlite-to-postgres":
        migrate(SQLITE_URL, POSTGRES_URL, replace=args.replace, dry_run=args.dry_run)
    else:
        migrate(POSTGRES_URL, SQLITE_URL, replace=args.replace, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
