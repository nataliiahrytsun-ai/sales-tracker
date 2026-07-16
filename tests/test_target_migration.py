"""Regression coverage for weekly target history migration."""

from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text

from app.config import DATABASE_URL_ENV_VAR


def test_existing_target_gets_canonical_week_and_new_unique_constraint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'target-migration.db').as_posix()}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "20260715_0006")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users "
                "(name, email, password_hash, active, must_change_password, "
                "auth_version, created_at) VALUES "
                "('Legacy User', 'legacy@example.com', 'hash', 1, 0, 1, "
                "'2026-07-16 09:00:00')",
            ),
        )
        connection.execute(
            text(
                "INSERT INTO targets "
                "(user_id, metric_name, target_value, effective_from, effective_until) "
                "VALUES (1, 'total_activities', 42, '2026-07-16', '2026-07-19')",
            ),
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT week_start, target_value, effective_from "
                    "FROM targets WHERE user_id = 1",
                ),
            ).mappings().one()
            indexes = inspect(connection).get_indexes("targets")
        assert row == {
            "week_start": "2026-07-13",
            "target_value": 42.0,
            "effective_from": "2026-07-16",
        }
        assert any(
            index["name"] == "uq_targets_user_week_metric"
            and index["unique"]
            and index["column_names"] == ["user_id", "week_start", "metric_name"]
            for index in indexes
        )
    finally:
        engine.dispose()
