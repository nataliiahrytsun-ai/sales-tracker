"""Tests for safe SQLite backup verification and local restore."""

from collections.abc import Generator
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import re
import sqlite3

import pytest

from app import backup

ALEMBIC_REVISION = "20260721_0008"
FIXED_TIMESTAMP = datetime(2026, 7, 23, 14, 5, 6, 123456, tzinfo=UTC)
EXPECTED_BACKUP_NAME = (
    "sales_tracker_backup_20260723T140506123456Z.db"
)


def sqlite_url(path: Path) -> str:
    """Build a SQLAlchemy-style SQLite URL for a local test file."""
    return f"sqlite:///{path.as_posix()}"


def database_contents(path: Path) -> tuple[list[tuple[int, str]], str]:
    """Read known rows and the Alembic revision from a test database."""
    connection = sqlite3.connect(path)
    try:
        records = connection.execute(
            "SELECT id, value FROM sample_records ORDER BY id",
        ).fetchall()
        revision = connection.execute(
            "SELECT version_num FROM alembic_version",
        ).fetchone()
        assert revision is not None
        return records, revision[0]
    finally:
        connection.close()


def file_digest(path: Path) -> str:
    """Return a stable digest for immutability assertions."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def wal_database(
    tmp_path: Path,
) -> Generator[tuple[Path, sqlite3.Connection], None, None]:
    """Create committed test data that remains represented in an active WAL."""
    source = tmp_path / "source.db"
    connection = sqlite3.connect(source)
    assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
    connection.execute(
        "CREATE TABLE alembic_version "
        "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)",
    )
    connection.execute(
        "INSERT INTO alembic_version (version_num) VALUES (?)",
        (ALEMBIC_REVISION,),
    )
    connection.execute(
        "CREATE TABLE sample_records "
        "(id INTEGER PRIMARY KEY, value TEXT NOT NULL)",
    )
    connection.commit()
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    connection.execute(
        "INSERT INTO sample_records (value) VALUES (?)",
        ("committed in WAL",),
    )
    connection.commit()
    wal_path = Path(f"{source}-wal")
    assert wal_path.exists()
    assert wal_path.stat().st_size > 0
    try:
        yield source, connection
    finally:
        connection.close()


def test_backup_captures_wal_data_integrity_revision_and_timestamp(
    wal_database: tuple[Path, sqlite3.Connection],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SQLite backup API publishes a verified snapshot of committed WAL data."""
    source, _connection = wal_database
    destination = tmp_path / "backups"
    destination.mkdir()

    def unexpected_settings() -> None:
        raise AssertionError("Explicit test URL must not use the local database")

    monkeypatch.setattr(backup, "load_settings", unexpected_settings)
    result = backup.create_backup(
        destination,
        database_url=sqlite_url(source),
        timestamp=FIXED_TIMESTAMP,
    )

    assert result.path == destination / EXPECTED_BACKUP_NAME
    assert re.fullmatch(
        r"sales_tracker_backup_\d{8}T\d{12}Z\.db",
        result.path.name,
    )
    assert result.revisions == (ALEMBIC_REVISION,)
    assert database_contents(result.path) == (
        [(1, "committed in WAL")],
        ALEMBIC_REVISION,
    )
    with sqlite3.connect(result.path) as connection:
        assert connection.execute(
            "PRAGMA integrity_check",
        ).fetchone() == ("ok",)
    assert list(destination.glob("*.backup.tmp")) == []
    assert source.name == "source.db"
    assert result.path.resolve().is_relative_to(tmp_path.resolve())


def test_verify_backup_is_read_only_and_reports_revision(
    wal_database: tuple[Path, sqlite3.Connection],
    tmp_path: Path,
) -> None:
    """Verification checks integrity and Alembic without changing the backup."""
    source, _connection = wal_database
    destination = tmp_path / "backups"
    destination.mkdir()
    created = backup.create_backup(
        destination,
        database_url=sqlite_url(source),
        timestamp=FIXED_TIMESTAMP,
    )
    digest_before = file_digest(created.path)
    modified_before = created.path.stat().st_mtime_ns

    verified = backup.verify_backup(created.path)

    assert verified.revisions == (ALEMBIC_REVISION,)
    assert file_digest(created.path) == digest_before
    assert created.path.stat().st_mtime_ns == modified_before
    assert not Path(f"{created.path}-wal").exists()
    assert not Path(f"{created.path}-shm").exists()


def test_backup_never_overwrites_existing_timestamped_file(
    wal_database: tuple[Path, sqlite3.Connection],
    tmp_path: Path,
) -> None:
    """A timestamp collision fails without replacing the existing artifact."""
    source, _connection = wal_database
    destination = tmp_path / "backups"
    destination.mkdir()
    existing = destination / EXPECTED_BACKUP_NAME
    existing.write_bytes(b"existing-backup-sentinel")

    with pytest.raises(
        backup.BackupError,
        match="already exists",
    ):
        backup.create_backup(
            destination,
            database_url=sqlite_url(source),
            timestamp=FIXED_TIMESTAMP,
        )

    assert existing.read_bytes() == b"existing-backup-sentinel"
    assert list(destination.glob("*.backup.tmp")) == []


def test_backup_rejects_missing_source_without_creating_it(
    tmp_path: Path,
) -> None:
    """Opening a missing source never creates an empty SQLite file."""
    source = tmp_path / "missing-source.db"
    destination = tmp_path / "backups"
    destination.mkdir()

    with pytest.raises(
        backup.BackupError,
        match="Source database file does not exist",
    ):
        backup.create_backup(
            destination,
            database_url=sqlite_url(source),
        )

    assert not source.exists()
    assert list(destination.iterdir()) == []


def test_backup_rejects_non_sqlite_source_url(tmp_path: Path) -> None:
    """Operational backup remains SQLite-only."""
    destination = tmp_path / "backups"
    destination.mkdir()

    with pytest.raises(
        backup.BackupError,
        match="file-backed SQLite",
    ):
        backup.create_backup(
            destination,
            database_url="postgresql://database.example/sales",
        )


def test_backup_does_not_create_missing_destination_directory(
    wal_database: tuple[Path, sqlite3.Connection],
    tmp_path: Path,
) -> None:
    """Deployment mistakes are visible instead of creating surprise paths."""
    source, _connection = wal_database
    destination = tmp_path / "missing" / "backups"

    with pytest.raises(
        backup.BackupError,
        match="destination directory does not exist",
    ):
        backup.create_backup(
            destination,
            database_url=sqlite_url(source),
        )

    assert not destination.exists()


def test_failed_backup_removes_incomplete_temporary_file(
    wal_database: tuple[Path, sqlite3.Connection],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A verification failure leaves no temporary or final backup."""
    source, _connection = wal_database
    destination = tmp_path / "backups"
    destination.mkdir()

    def reject_verification(_path: Path) -> backup.VerificationResult:
        raise backup.BackupError("forced verification failure")

    monkeypatch.setattr(backup, "verify_backup", reject_verification)
    with pytest.raises(backup.BackupError, match="forced verification"):
        backup.create_backup(
            destination,
            database_url=sqlite_url(source),
            timestamp=FIXED_TIMESTAMP,
        )

    assert list(destination.iterdir()) == []


@pytest.mark.parametrize(
    ("contents", "expected_error"),
    [
        (b"not a sqlite database", "not a readable SQLite"),
        (b"", "does not contain the alembic_version"),
    ],
)
def test_verify_rejects_corrupt_or_unrelated_files(
    tmp_path: Path,
    contents: bytes,
    expected_error: str,
) -> None:
    """Corrupt and non-application files fail with actionable safe errors."""
    candidate = tmp_path / "invalid-backup.db"
    candidate.write_bytes(contents)

    with pytest.raises(backup.BackupError, match=expected_error):
        backup.verify_backup(candidate)


def test_verify_rejects_missing_file(tmp_path: Path) -> None:
    """Verification never creates a missing candidate."""
    missing = tmp_path / "missing-backup.db"

    with pytest.raises(backup.BackupError, match="does not exist"):
        backup.verify_backup(missing)

    assert not missing.exists()


def test_restore_creates_separate_verified_database_without_mutating_backup(
    wal_database: tuple[Path, sqlite3.Connection],
    tmp_path: Path,
) -> None:
    """Restore preserves records/revision and leaves its source byte-identical."""
    source, _connection = wal_database
    destination = tmp_path / "backups"
    restore_directory = tmp_path / "restores"
    destination.mkdir()
    restore_directory.mkdir()
    created = backup.create_backup(
        destination,
        database_url=sqlite_url(source),
        timestamp=FIXED_TIMESTAMP,
    )
    digest_before = file_digest(created.path)
    restored_path = restore_directory / "restored.db"

    restored = backup.restore_backup(created.path, restored_path)

    assert restored.path == restored_path
    assert restored.revisions == (ALEMBIC_REVISION,)
    assert database_contents(restored_path) == (
        [(1, "committed in WAL")],
        ALEMBIC_REVISION,
    )
    assert file_digest(created.path) == digest_before
    assert list(restore_directory.glob("*.restore.tmp")) == []
    assert not Path(f"{restored_path}-wal").exists()
    assert not Path(f"{restored_path}-shm").exists()


def test_restore_refuses_existing_target_without_explicit_replace(
    wal_database: tuple[Path, sqlite3.Connection],
    tmp_path: Path,
) -> None:
    """Default restore cannot overwrite an existing target."""
    source, _connection = wal_database
    backup_directory = tmp_path / "backups"
    restore_directory = tmp_path / "restores"
    backup_directory.mkdir()
    restore_directory.mkdir()
    created = backup.create_backup(
        backup_directory,
        database_url=sqlite_url(source),
        timestamp=FIXED_TIMESTAMP,
    )
    target = restore_directory / "existing.db"
    target.write_bytes(b"existing-target-sentinel")

    with pytest.raises(backup.BackupError, match="use --replace"):
        backup.restore_backup(created.path, target)

    assert target.read_bytes() == b"existing-target-sentinel"
    assert list(restore_directory.glob("*.restore.tmp")) == []


def test_restore_replaces_only_with_explicit_flag(
    wal_database: tuple[Path, sqlite3.Connection],
    tmp_path: Path,
) -> None:
    """The explicit replace flag atomically installs the verified restore."""
    source, _connection = wal_database
    backup_directory = tmp_path / "backups"
    restore_directory = tmp_path / "restores"
    backup_directory.mkdir()
    restore_directory.mkdir()
    created = backup.create_backup(
        backup_directory,
        database_url=sqlite_url(source),
        timestamp=FIXED_TIMESTAMP,
    )
    target = restore_directory / "existing.db"
    target.write_bytes(b"replace-me")

    result = backup.restore_backup(created.path, target, replace=True)

    assert result.path == target
    assert database_contents(target) == (
        [(1, "committed in WAL")],
        ALEMBIC_REVISION,
    )


def test_restore_requires_existing_target_parent(
    wal_database: tuple[Path, sqlite3.Connection],
    tmp_path: Path,
) -> None:
    """Restore does not create a missing target directory."""
    source, _connection = wal_database
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir()
    created = backup.create_backup(
        backup_directory,
        database_url=sqlite_url(source),
        timestamp=FIXED_TIMESTAMP,
    )
    target = tmp_path / "missing-parent" / "restored.db"

    with pytest.raises(
        backup.BackupError,
        match="target directory does not exist",
    ):
        backup.restore_backup(created.path, target)

    assert not target.parent.exists()


def test_restore_rejects_target_with_sqlite_sidecars(
    wal_database: tuple[Path, sqlite3.Connection],
    tmp_path: Path,
) -> None:
    """Stale/live target WAL state must be resolved before replacement."""
    source, _connection = wal_database
    backup_directory = tmp_path / "backups"
    restore_directory = tmp_path / "restores"
    backup_directory.mkdir()
    restore_directory.mkdir()
    created = backup.create_backup(
        backup_directory,
        database_url=sqlite_url(source),
        timestamp=FIXED_TIMESTAMP,
    )
    target = restore_directory / "existing.db"
    target.write_bytes(b"existing")
    wal_path = Path(f"{target}-wal")
    wal_path.write_bytes(b"active-or-stale-wal")

    with pytest.raises(backup.BackupError, match="sidecar files"):
        backup.restore_backup(created.path, target, replace=True)

    assert target.read_bytes() == b"existing"
    assert wal_path.read_bytes() == b"active-or-stale-wal"


def test_cli_verify_reports_safe_exit_codes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI failures use exit 1 and do not echo database contents."""
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"private corrupt contents")

    result = backup.main(["verify", str(corrupt)])

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert "Backup operation failed" in captured.err
    assert "private corrupt contents" not in captured.err
