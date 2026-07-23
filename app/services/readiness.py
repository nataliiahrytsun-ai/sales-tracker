"""Read-only SQLite and Alembic readiness checks."""

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import sqlite3

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.config import sqlite_database_path

READINESS_SQLITE_TIMEOUT_SECONDS = 1.0
DATABASE_UNAVAILABLE = "database unavailable"
SCHEMA_REVISION_UNAVAILABLE = "schema revision unavailable"
SCHEMA_REVISION_MISMATCH = "schema revision mismatch"


class ReadinessError(RuntimeError):
    """A categorized readiness failure safe for application logs."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


@dataclass(frozen=True)
class ReadinessResult:
    """Internal readiness metadata that is never exposed publicly."""

    revision: str


def project_alembic_head() -> str:
    """Read the single current Alembic head from the project migrations."""
    project_root = Path(__file__).resolve().parents[2]
    configuration = Config(str(project_root / "alembic.ini"))
    scripts = ScriptDirectory.from_config(configuration)
    head = scripts.get_current_head()
    if not head:
        raise ReadinessError(SCHEMA_REVISION_UNAVAILABLE)
    return head


def _read_only_sqlite_uri(path: Path) -> str:
    """Build a URI that requires an existing SQLite file."""
    return f"{path.resolve(strict=True).as_uri()}?mode=ro"


class ReadinessChecker:
    """Check database availability and migration state without writes."""

    def __init__(
        self,
        database_url: str,
        *,
        expected_revision: str | None = None,
        timeout_seconds: float = READINESS_SQLITE_TIMEOUT_SECONDS,
    ) -> None:
        self.database_url = database_url
        self.expected_revision = expected_revision
        self.timeout_seconds = timeout_seconds

    def check(self) -> ReadinessResult:
        """Return readiness metadata or raise a safe categorized failure."""
        try:
            database_path = Path(
                sqlite_database_path(self.database_url),
            ).expanduser().absolute()
            if not database_path.is_file():
                raise ReadinessError(DATABASE_UNAVAILABLE)
            database_uri = _read_only_sqlite_uri(database_path)
            connection = sqlite3.connect(
                database_uri,
                uri=True,
                timeout=self.timeout_seconds,
            )
        except ReadinessError:
            raise
        except (OSError, RuntimeError, sqlite3.Error) as error:
            raise ReadinessError(DATABASE_UNAVAILABLE) from error

        try:
            with closing(connection):
                connection.execute("PRAGMA query_only=ON")
                connection.execute("SELECT 1").fetchone()
                revision = self._read_revision(connection)
        except ReadinessError:
            raise
        except sqlite3.Error as error:
            raise ReadinessError(DATABASE_UNAVAILABLE) from error

        try:
            expected_revision = (
                self.expected_revision or project_alembic_head()
            )
        except ReadinessError:
            raise
        except Exception as error:
            raise ReadinessError(SCHEMA_REVISION_UNAVAILABLE) from error
        if revision != expected_revision:
            raise ReadinessError(SCHEMA_REVISION_MISMATCH)
        return ReadinessResult(revision=revision)

    @staticmethod
    def _read_revision(connection: sqlite3.Connection) -> str:
        """Require one non-empty revision from alembic_version."""
        try:
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'alembic_version'",
            ).fetchone()
            if table_exists is None:
                raise ReadinessError(SCHEMA_REVISION_UNAVAILABLE)
            rows = connection.execute(
                "SELECT version_num FROM alembic_version",
            ).fetchall()
        except ReadinessError:
            raise
        except sqlite3.Error as error:
            raise ReadinessError(SCHEMA_REVISION_UNAVAILABLE) from error

        if (
            len(rows) != 1
            or not isinstance(rows[0][0], str)
            or not rows[0][0].strip()
        ):
            raise ReadinessError(SCHEMA_REVISION_UNAVAILABLE)
        return rows[0][0]
