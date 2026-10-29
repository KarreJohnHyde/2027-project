"""Idempotent, versioned schema migrations.

`Base.metadata.create_all` creates missing tables but never alters existing
ones, so a database created by an earlier release would silently lack new
columns. Each migration here adds nullable columns in place and is recorded
in `schema_migrations`; evidence already stored is never rewritten.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

MIGRATIONS: tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...] = (
    (
        "2026_10_24_001_statement_context",
        tuple(
            ("clinical_report_statements", column, ddl)
            for column, ddl in (
                ("entity_text", "VARCHAR(128)"),
                ("entity_start", "INTEGER"),
                ("entity_end", "INTEGER"),
                ("category", "VARCHAR(32)"),
                ("certainty", "VARCHAR(32)"),
                ("experiencer", "VARCHAR(16)"),
                ("comparison", "VARCHAR(32)"),
                ("section", "VARCHAR(48)"),
                ("anatomical_site", "VARCHAR(128)"),
                ("laterality", "VARCHAR(8)"),
                ("anatomy_system", "VARCHAR(32)"),
                ("atlas_structure_id", "VARCHAR(160)"),
                ("cues", "JSON"),
                ("extractor_version", "VARCHAR(32)"),
            )
        ),
    ),
    (
        "2026_10_24_002_measurement_context",
        tuple(
            ("medical_measurements", column, ddl)
            for column, ddl in (
                ("canonical_code", "VARCHAR(32)"),
                ("code_system", "VARCHAR(64)"),
                ("code_mapping_status", "VARCHAR(64)"),
                ("reference_low", "FLOAT"),
                ("reference_high", "FLOAT"),
                ("reference_text", "VARCHAR(64)"),
                ("reference_source", "VARCHAR(32)"),
                ("documented_flag", "VARCHAR(16)"),
                ("conversion_status", "VARCHAR(48)"),
                ("documented_date", "VARCHAR(10)"),
                ("anatomy_system", "VARCHAR(32)"),
                ("association", "VARCHAR(48)"),
                ("source_page", "INTEGER"),
            )
        ),
    ),
    (
        "2026_10_25_003_measurement_ocr_coordinates",
        tuple(
            ("medical_measurements", column, ddl)
            for column, ddl in (
                ("source_bbox", "JSON"),
                ("source_bbox_coordinate_space", "VARCHAR(64)"),
                ("source_image_width", "INTEGER"),
                ("source_image_height", "INTEGER"),
            )
        ),
    ),
    (
        "2026_10_25_004_measurement_semantics",
        tuple(
            ("medical_measurements", column, ddl)
            for column, ddl in (
                ("result_operator", "VARCHAR(2)"),
                ("specimen", "VARCHAR(64)"),
                ("laboratory_method", "VARCHAR(128)"),
                ("laboratory_name", "VARCHAR(128)"),
                ("reference_low_inclusive", "BOOLEAN"),
                ("reference_high_inclusive", "BOOLEAN"),
                ("extractor_version", "VARCHAR(32)"),
            )
        ),
    ),
    (
        "2026_10_25_005_human_review_corrections",
        (
            ("human_reviews", "correction_payload", "JSON"),
        ),
    ),
    (
        "2026_10_26_001_measurement_reference_strata",
        tuple(
            ("medical_measurements", column, ddl)
            for column, ddl in (
                ("reference_options", "JSON"),
                ("reference_selection", "VARCHAR(48)"),
                ("documented_category", "VARCHAR(64)"),
            )
        ),
    ),
    (
        "2026_10_27_002_uploaded_file_versions",
        tuple(
            ("uploaded_files", column, ddl)
            for column, ddl in (
                ("version_number", "INTEGER NOT NULL DEFAULT 1"),
                ("supersedes_file_id", "INTEGER"),
                ("superseded_by_file_id", "INTEGER"),
                ("withdrawn_at", "DATETIME"),
                ("withdrawn_by_id", "INTEGER"),
                ("withdrawal_reason", "VARCHAR(256)"),
            )
        ),
    ),
    (
        "2026_10_27_001_user_verification_status",
        (
            (
                "users",
                "verification_status",
                "VARCHAR(16) NOT NULL DEFAULT 'UNVERIFIED'",
            ),
        ),
    ),
    (
        "2026_10_29_001_demographic_source_provenance",
        (
            ("reviewed_demographics", "source_reference_id", "INTEGER"),
            ("reviewed_demographics", "source_kind", "VARCHAR(32)"),
        ),
    ),
    ("2026_10_29_002_shared_user_emails", ()),
)


def run_migrations(engine: Engine) -> list[str]:
    """Apply pending migrations and return the versions applied in this call."""
    applied_now: list[str] = []
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(64) PRIMARY KEY, applied_at VARCHAR(40) NOT NULL)"
        ))
        done = {row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))}
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        # SQLAlchemy persists Enum member names in PostgreSQL. Existing
        # installations therefore need the new non-privileged role added to
        # the database enum before a public self-registration can be stored.
        # New databases already receive this value from Base.metadata.
        if engine.dialect.name == "postgresql" and "users" in tables:
            connection.execute(text("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'PUBLIC'"))
        if engine.dialect.name == "postgresql" and "uploaded_files" in tables:
            connection.execute(text("ALTER TYPE modalitytype ADD VALUE IF NOT EXISTS 'SIGNAL'"))
        for version, columns in MIGRATIONS:
            if version in done:
                continue
            for table, column, ddl in columns:
                if table not in tables:
                    continue
                existing = {item["name"] for item in inspector.get_columns(table)}
                if column not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            if (
                version == "2026_10_29_002_shared_user_emails"
                and "users" in tables
                and "email" in {item["name"] for item in inspector.get_columns("users")}
            ):
                # Older schemas created email as a unique index (index=True,
                # unique=True). Preserve every user while replacing that
                # constraint with the ordinary lookup index declared by User.
                email_constraints = [
                    constraint for constraint in inspector.get_unique_constraints("users")
                    if constraint.get("column_names") == ["email"]
                ]
                constraint_names = {constraint.get("name") for constraint in email_constraints}
                for constraint in email_constraints:
                    if engine.dialect.name == "sqlite":
                        raise RuntimeError(
                            "Cannot safely remove a table-level unique email constraint from SQLite users."
                        )
                    name = engine.dialect.identifier_preparer.quote(constraint["name"])
                    connection.execute(text(f"ALTER TABLE users DROP CONSTRAINT {name}"))
                for index in inspector.get_indexes("users"):
                    if (
                        index.get("column_names") == ["email"]
                        and index.get("unique")
                        and not index.get("duplicates_constraint")
                        and index["name"] not in constraint_names
                    ):
                        name = engine.dialect.identifier_preparer.quote(index["name"])
                        connection.execute(text(f"DROP INDEX {name}"))
                inspector = inspect(connection)
                email_indexes = {
                    index["name"] for index in inspector.get_indexes("users")
                    if index.get("column_names") == ["email"]
                }
                if "ix_users_email" not in email_indexes:
                    index_name = engine.dialect.identifier_preparer.quote("ix_users_email")
                    connection.execute(text(f"CREATE INDEX {index_name} ON users (email)"))
            if version == "2026_10_29_001_demographic_source_provenance" and "reviewed_demographics" in tables:
                # Preserve known source links. A legacy NULL FK could mean either
                # an attestation or a deleted source, so do not guess its origin.
                connection.execute(text(
                    "UPDATE reviewed_demographics SET source_reference_id = source_file_id, source_kind = 'FILE' "
                    "WHERE source_file_id IS NOT NULL AND source_kind IS NULL"
                ))
            connection.execute(
                text("INSERT INTO schema_migrations (version, applied_at) VALUES (:version, :applied_at)"),
                {"version": version, "applied_at": datetime.now(timezone.utc).isoformat()},
            )
            applied_now.append(version)
            inspector = inspect(connection)
    if applied_now:
        logger.info("Applied schema migrations: %s", ", ".join(applied_now))
    return applied_now


def migration_status(engine: Engine) -> dict:
    with engine.connect() as connection:
        try:
            done = {row[0]: row[1] for row in connection.execute(text("SELECT version, applied_at FROM schema_migrations"))}
        except Exception:
            done = {}
    return {
        "expected": [version for version, _ in MIGRATIONS],
        "applied": done,
        "pending": [version for version, _ in MIGRATIONS if version not in done],
    }
