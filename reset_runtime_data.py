#!/usr/bin/env python3
"""
Delete operational data while preserving stable reference tables.

Default preserved tables:
- health_facilities
- resources
- dietary_recommendation
- wards
- sub_counties
- medical_record_type
"""

from __future__ import annotations

import argparse

from sqlalchemy import MetaData, inspect, text

from app import create_app, db


DEFAULT_PRESERVED_TABLES = {
    "health_facilities",
    "resources",
    "dietary_recommendation",
    "wards",
    "sub_counties",
    "medical_record_type",
}


def _parse_args():
    parser = argparse.ArgumentParser(description="Reset runtime data while preserving reference tables.")
    parser.add_argument(
        "--preserve",
        help="Comma-separated table names to preserve. Defaults to the built-in reference table list.",
    )
    return parser.parse_args()


def _reset_sequences(connection, table_names: list[str]):
    inspector = inspect(connection)
    for table_name in table_names:
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "id" not in columns:
            continue
        connection.execute(
            text(
                """
                SELECT setval(pg_get_serial_sequence(:table_name, 'id'), 1, false)
                WHERE pg_get_serial_sequence(:table_name, 'id') IS NOT NULL
                """
            ),
            {"table_name": table_name},
        )


def reset_runtime_data(preserved_tables: set[str] | None = None):
    preserved_tables = preserved_tables or set(DEFAULT_PRESERVED_TABLES)
    app = create_app()

    with app.app_context():
        connection = db.session.connection()

        if "health_facilities" in preserved_tables:
            connection.execute(text("UPDATE health_facilities SET facility_admin_id = NULL"))
        if "dietary_recommendation" in preserved_tables:
            connection.execute(text("UPDATE dietary_recommendation SET created_by = NULL"))

        metadata = MetaData()
        metadata.reflect(bind=connection)

        deletable_tables = [
            table
            for table in reversed(metadata.sorted_tables)
            if table.name not in preserved_tables
        ]

        deleted_table_names: list[str] = []
        for table in deletable_tables:
            connection.execute(table.delete())
            deleted_table_names.append(table.name)

        _reset_sequences(connection, deleted_table_names)
        db.session.commit()

        print("Runtime data reset complete.")
        print(f"Preserved tables: {', '.join(sorted(preserved_tables))}")
        print(f"Cleared tables: {', '.join(deleted_table_names)}")


if __name__ == "__main__":
    args = _parse_args()
    preserve = (
        {item.strip() for item in args.preserve.split(",") if item.strip()}
        if args.preserve
        else None
    )
    reset_runtime_data(preserve)
