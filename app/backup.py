"""Safe SQLite backup verification and local restore operations."""

import argparse
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

from app.config import load_settings, sqlite_database_path

BACKUP_FILENAME_PREFIX = "sales_tracker_backup_"
BACKUP_FILENAME_SUFFIX = ".db"
BACKUP_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S%fZ"


class BackupError(RuntimeError):
    """A safe, user-facing operational failure."""


@dataclass(frozen=True)
class VerificationResult:
    """Verified SQLite backup metadata."""

    path: Path
    revisions: tuple[str, ...]


def _existing_writable_directory(path: Path, *, label: str) -> Path:
    """Require an existing writable directory without creating it."""
    directory = path.expanduser().absolute()
    if not directory.exists():
        raise BackupError(f"{label} directory does not exist")
    if not directory.is_dir():
        raise BackupError(f"{label} path is not a directory")
    if not os.access(directory, os.W_OK):
        raise BackupError(f"{label} directory is not writable")
    return directory


def _existing_database_file(path: Path, *, label: str) -> Path:
    """Require an existing regular database file."""
    database_file = path.expanduser().absolute()
    if not database_file.exists():
        raise BackupError(f"{label} database file does not exist")
    if not database_file.is_file():
        raise BackupError(f"{label} database path is not a file")
    return database_file


def _read_only_sqlite_uri(
    path: Path,
    *,
    immutable: bool = False,
) -> str:
    """Build an encoded SQLite URI that cannot create or modify the file."""
    immutable_option = "&immutable=1" if immutable else ""
    return (
        f"{path.resolve(strict=True).as_uri()}?mode=ro{immutable_option}"
    )


def _integrity_check(connection: sqlite3.Connection) -> None:
    """Require SQLite's full integrity check to report only ok."""
    rows = connection.execute("PRAGMA integrity_check").fetchall()
    if rows != [("ok",)]:
        raise BackupError("SQLite integrity_check did not return ok")


def verify_backup(path: Path | str) -> VerificationResult:
    """Verify integrity and readable Alembic revision without modifying a file."""
    backup_path = _existing_database_file(Path(path), label="Backup")
    try:
        with closing(
            sqlite3.connect(
                _read_only_sqlite_uri(backup_path, immutable=True),
                uri=True,
            ),
        ) as connection:
            connection.execute("PRAGMA query_only=ON")
            _integrity_check(connection)
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'alembic_version'",
            ).fetchone()
            if table_exists is None:
                raise BackupError(
                    "Backup does not contain the alembic_version table",
                )
            revisions = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT version_num FROM alembic_version ORDER BY version_num",
                ).fetchall()
                if isinstance(row[0], str) and row[0]
            )
            if not revisions:
                raise BackupError(
                    "Backup does not contain a readable Alembic revision",
                )
    except BackupError:
        raise
    except sqlite3.Error as error:
        raise BackupError("Backup is not a readable SQLite database") from error
    return VerificationResult(path=backup_path, revisions=revisions)


def _temporary_path(
    directory: Path,
    *,
    prefix: str,
    suffix: str,
) -> Path:
    """Create an exclusive temporary file in the final destination directory."""
    descriptor, raw_path = tempfile.mkstemp(
        dir=directory,
        prefix=prefix,
        suffix=suffix,
    )
    os.close(descriptor)
    return Path(raw_path)


def _sqlite_backup(source: Path, destination: Path) -> None:
    """Copy a live SQLite snapshot, including committed WAL transactions."""
    try:
        with (
            closing(
                sqlite3.connect(
                    _read_only_sqlite_uri(source),
                    uri=True,
                ),
            ) as source_connection,
            closing(sqlite3.connect(destination)) as destination_connection,
        ):
            source_connection.backup(destination_connection)
            journal_mode = destination_connection.execute(
                "PRAGMA journal_mode=DELETE",
            ).fetchone()
            if journal_mode is None or journal_mode[0].lower() != "delete":
                raise BackupError(
                    "Could not finalize a standalone SQLite backup file",
                )
    except sqlite3.Error as error:
        raise BackupError("SQLite backup operation failed") from error


def _sync_file(path: Path) -> None:
    """Flush a completed SQLite file before publishing it."""
    with path.open("r+b") as file_handle:
        os.fsync(file_handle.fileno())


def _publish_without_overwrite(temporary: Path, final: Path) -> None:
    """Atomically publish a same-filesystem file only when final is absent."""
    try:
        os.link(temporary, final)
    except FileExistsError as error:
        raise BackupError("Destination file already exists") from error
    except OSError as error:
        raise BackupError(
            "Could not atomically publish the destination file",
        ) from error
    temporary.unlink()


def backup_filename(timestamp: datetime) -> str:
    """Return a UTC timestamped backup filename."""
    if timestamp.tzinfo is None:
        raise ValueError("Backup timestamp must include timezone information")
    utc_timestamp = timestamp.astimezone(UTC)
    return (
        f"{BACKUP_FILENAME_PREFIX}"
        f"{utc_timestamp.strftime(BACKUP_TIMESTAMP_FORMAT)}"
        f"{BACKUP_FILENAME_SUFFIX}"
    )


def create_backup(
    destination_directory: Path | str,
    *,
    database_url: str | None = None,
    timestamp: datetime | None = None,
) -> VerificationResult:
    """Create, verify, and atomically publish a live SQLite backup."""
    configured_url = database_url or load_settings().database_url
    try:
        source_path = Path(sqlite_database_path(configured_url))
    except RuntimeError as error:
        raise BackupError(
            "Source must be a file-backed SQLite database URL",
        ) from error
    source = _existing_database_file(source_path, label="Source")
    destination = _existing_writable_directory(
        Path(destination_directory),
        label="Backup destination",
    )
    final_path = destination / backup_filename(timestamp or datetime.now(UTC))
    if final_path.exists():
        raise BackupError("Destination backup file already exists")

    temporary = _temporary_path(
        destination,
        prefix=f".{final_path.name}.",
        suffix=".backup.tmp",
    )
    try:
        _sqlite_backup(source, temporary)
        verification = verify_backup(temporary)
        _sync_file(temporary)
        _publish_without_overwrite(temporary, final_path)
        return VerificationResult(
            path=final_path,
            revisions=verification.revisions,
        )
    finally:
        if temporary.exists():
            temporary.unlink()


def restore_backup(
    backup_path: Path | str,
    target_path: Path | str,
    *,
    replace: bool = False,
) -> VerificationResult:
    """Restore a verified backup to an explicit, independently verified file."""
    source_verification = verify_backup(backup_path)
    target = Path(target_path).expanduser().absolute()
    target_parent = _existing_writable_directory(
        target.parent,
        label="Restore target",
    )
    if target.exists():
        if not target.is_file():
            raise BackupError("Restore target path is not a file")
        if not replace:
            raise BackupError(
                "Restore target already exists; use --replace explicitly",
            )
    for suffix in ("-wal", "-shm"):
        if Path(f"{target}{suffix}").exists():
            raise BackupError(
                "Restore target has SQLite sidecar files; stop the "
                "application and resolve them before restore",
            )
    if source_verification.path == target:
        raise BackupError("Backup and restore target must be different files")

    temporary = _temporary_path(
        target_parent,
        prefix=f".{target.name}.",
        suffix=".restore.tmp",
    )
    try:
        _sqlite_backup(source_verification.path, temporary)
        restored_verification = verify_backup(temporary)
        if restored_verification.revisions != source_verification.revisions:
            raise BackupError("Restored Alembic revision does not match backup")
        _sync_file(temporary)
        if replace:
            os.replace(temporary, target)
        else:
            _publish_without_overwrite(temporary, target)
        return VerificationResult(
            path=target,
            revisions=restored_verification.revisions,
        )
    finally:
        if temporary.exists():
            temporary.unlink()


def build_parser() -> argparse.ArgumentParser:
    """Build the operational backup/verify/restore command parser."""
    parser = argparse.ArgumentParser(prog="python -m app.backup")
    subcommands = parser.add_subparsers(dest="command", required=True)

    backup_parser = subcommands.add_parser(
        "backup",
        help="Create and verify a timestamped SQLite backup.",
    )
    backup_parser.add_argument(
        "--destination-dir",
        required=True,
        type=Path,
        help="Existing directory where the backup will be published.",
    )
    backup_parser.add_argument(
        "--database-url",
        help=(
            "Optional SQLite URL; defaults to SALES_TRACKER_DATABASE_URL "
            "through application settings."
        ),
    )

    verify_parser = subcommands.add_parser(
        "verify",
        help="Verify a backup without modifying it.",
    )
    verify_parser.add_argument("backup_path", type=Path)

    restore_parser = subcommands.add_parser(
        "restore",
        help="Restore a verified backup to an explicit local file.",
    )
    restore_parser.add_argument("backup_path", type=Path)
    restore_parser.add_argument("target_path", type=Path)
    restore_parser.add_argument(
        "--replace",
        action="store_true",
        help="Explicitly replace an existing target file.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run a backup operation with safe messages and exit codes."""
    parsed = build_parser().parse_args(arguments)
    try:
        if parsed.command == "backup":
            result = create_backup(
                parsed.destination_dir,
                database_url=parsed.database_url,
            )
            print(
                f"Backup created and verified: {result.path} "
                f"(Alembic: {', '.join(result.revisions)})",
            )
            return 0
        if parsed.command == "verify":
            result = verify_backup(parsed.backup_path)
            print(
                f"Backup verified: {result.path} "
                f"(Alembic: {', '.join(result.revisions)})",
            )
            return 0
        if parsed.command == "restore":
            result = restore_backup(
                parsed.backup_path,
                parsed.target_path,
                replace=parsed.replace,
            )
            print(
                f"Backup restored and verified: {result.path} "
                f"(Alembic: {', '.join(result.revisions)})",
            )
            return 0
    except (BackupError, RuntimeError) as error:
        print(f"Backup operation failed: {error}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
