from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

try:
    import psycopg
except ImportError:  # pragma: no cover - optional dependency at runtime
    psycopg = None

DB_NAME = "skill_lab.db"


def _db_path() -> Path:
    return Path(__file__).resolve().parent / DB_NAME


def _database_url() -> str:
    configured = (
        os.environ.get("SKILL_LAB_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()
    if configured:
        return configured
    return f"sqlite:///{_db_path()}"


def _is_postgres_url(url: str) -> bool:
    lowered = url.lower()
    return lowered.startswith("postgresql://") or lowered.startswith("postgres://")


def _is_sqlite_url(url: str) -> bool:
    return url.lower().startswith("sqlite:///")


def _sqlite_path_from_url(url: str) -> str:
    if not _is_sqlite_url(url):
        return str(_db_path())
    raw_path = url[len("sqlite:///") :]
    if raw_path == ":memory:":
        return raw_path
    return str(Path(raw_path).expanduser())


def _is_postgres_conn(conn: Any) -> bool:
    return not isinstance(conn, sqlite3.Connection)


def _connect() -> Any:
    url = _database_url()

    if _is_postgres_url(url):
        if psycopg is None:
            raise RuntimeError(
                "PostgreSQL URL is configured but psycopg is not installed. "
                "Install it with: pip install psycopg[binary]"
            )
        normalized = "postgresql://" + url.split("://", 1)[1]
        timeout_raw = os.environ.get("SKILL_LAB_DB_CONNECT_TIMEOUT", "5").strip()
        try:
            connect_timeout = max(int(timeout_raw), 1)
        except ValueError:
            connect_timeout = 5
        return psycopg.connect(normalized, connect_timeout=connect_timeout)

    sqlite_path = _sqlite_path_from_url(url)
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def _connect_ctx() -> Iterable[Any]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _placeholder(conn: Any) -> str:
    return "%s" if _is_postgres_conn(conn) else "?"


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return dict(row)
    if isinstance(row, dict):
        return row
    columns = [str(desc[0]) for desc in cursor.description or []]
    return {columns[idx]: row[idx] for idx in range(len(columns))}


def _execute(conn: Any, query: str, params: tuple[Any, ...] = ()) -> Any:
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        return cursor
    except Exception:
        cursor.close()
        raise


def _fetchone(conn: Any, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        row = cursor.fetchone()
        if row is None:
            return None
        return _row_to_dict(cursor, row)
    finally:
        cursor.close()


def _fetchall(conn: Any, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [_row_to_dict(cursor, row) for row in rows]
    finally:
        cursor.close()


def _existing_columns(conn: Any, table: str) -> set[str]:
    if _is_postgres_conn(conn):
        token = _placeholder(conn)
        rows = _fetchall(
            conn,
            (
                "SELECT column_name "
                "FROM information_schema.columns "
                f"WHERE table_schema = 'public' AND table_name = {token}"
            ),
            (table,),
        )
        return {str(row["column_name"]) for row in rows}

    rows = _fetchall(conn, f"PRAGMA table_info({table})")
    return {str(row["name"]) for row in rows}


def _ensure_columns(conn: Any, table: str, required_columns: dict[str, str]) -> None:
    existing = _existing_columns(conn, table)
    for name, definition in required_columns.items():
        if name not in existing:
            _execute(conn, f"ALTER TABLE {table} ADD COLUMN {name} {definition}").close()


def init_db() -> None:
    with _connect_ctx() as conn:
        if _is_postgres_conn(conn):
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS problems (
                    id BIGINT PRIMARY KEY,
                    title TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    expected_time DOUBLE PRECISION NOT NULL,
                    concept_tags TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT ''
                )
                """,
            ).close()
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS attempts (
                    id BIGSERIAL PRIMARY KEY,
                    problem_id BIGINT NOT NULL REFERENCES problems(id),
                    topic TEXT NOT NULL DEFAULT '',
                    difficulty TEXT NOT NULL DEFAULT '',
                    time_taken DOUBLE PRECISION NOT NULL,
                    predicted_time DOUBLE PRECISION NOT NULL,
                    confidence INTEGER NOT NULL CHECK(confidence >= 0 AND confidence <= 100),
                    correct BOOLEAN NOT NULL,
                    error_tag TEXT,
                    structural_features TEXT,
                    source_platform TEXT,
                    external_submission_id TEXT,
                    timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
                """,
            ).close()
            problems_columns = {
                "concept_tags": "TEXT NOT NULL DEFAULT ''",
                "description": "TEXT NOT NULL DEFAULT ''",
            }
            attempts_columns = {
                "topic": "TEXT NOT NULL DEFAULT ''",
                "difficulty": "TEXT NOT NULL DEFAULT ''",
                "predicted_time": "DOUBLE PRECISION NOT NULL DEFAULT 0",
                "confidence": "INTEGER NOT NULL DEFAULT 0",
                "error_tag": "TEXT",
                "structural_features": "TEXT",
                "source_platform": "TEXT",
                "external_submission_id": "TEXT",
                "timestamp": "TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP",
            }
        else:
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS problems (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    expected_time REAL NOT NULL,
                    concept_tags TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT ''
                )
                """,
            ).close()
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    problem_id INTEGER NOT NULL,
                    topic TEXT NOT NULL DEFAULT '',
                    difficulty TEXT NOT NULL DEFAULT '',
                    time_taken REAL NOT NULL,
                    predicted_time REAL NOT NULL,
                    confidence INTEGER NOT NULL CHECK(confidence >= 0 AND confidence <= 100),
                    correct INTEGER NOT NULL CHECK(correct IN (0, 1)),
                    error_tag TEXT,
                    structural_features TEXT,
                    source_platform TEXT,
                    external_submission_id TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(problem_id) REFERENCES problems(id)
                )
                """,
            ).close()
            problems_columns = {
                "concept_tags": "TEXT NOT NULL DEFAULT ''",
                "description": "TEXT NOT NULL DEFAULT ''",
            }
            attempts_columns = {
                "topic": "TEXT NOT NULL DEFAULT ''",
                "difficulty": "TEXT NOT NULL DEFAULT ''",
                "predicted_time": "REAL NOT NULL DEFAULT 0",
                "confidence": "INTEGER NOT NULL DEFAULT 0",
                "error_tag": "TEXT",
                "structural_features": "TEXT",
                "source_platform": "TEXT",
                "external_submission_id": "TEXT",
                "timestamp": "DATETIME DEFAULT CURRENT_TIMESTAMP",
            }

        _ensure_columns(conn, "problems", problems_columns)
        _ensure_columns(conn, "attempts", attempts_columns)

        # Remove duplicate platform-imported attempts to safely enforce uniqueness.
        _execute(
            conn,
            """
            DELETE FROM attempts
            WHERE source_platform IS NOT NULL
              AND external_submission_id IS NOT NULL
              AND id NOT IN (
                  SELECT MIN(id)
                  FROM attempts
                  WHERE source_platform IS NOT NULL
                    AND external_submission_id IS NOT NULL
                  GROUP BY source_platform, external_submission_id
              )
            """,
        ).close()

        _execute(
            conn,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_attempts_source_external
            ON attempts (source_platform, external_submission_id)
            WHERE source_platform IS NOT NULL AND external_submission_id IS NOT NULL
            """,
        ).close()
        _execute(
            conn,
            "CREATE INDEX IF NOT EXISTS ix_attempts_timestamp ON attempts (timestamp)",
        ).close()
        _execute(
            conn,
            "CREATE INDEX IF NOT EXISTS ix_attempts_topic ON attempts (topic)",
        ).close()
        _execute(
            conn,
            "CREATE INDEX IF NOT EXISTS ix_attempts_problem_id ON attempts (problem_id)",
        ).close()


def upsert_problems(problems: list[dict[str, Any]]) -> None:
    with _connect_ctx() as conn:
        token = _placeholder(conn)
        values = ", ".join([token] * 7)
        query = f"""
            INSERT INTO problems (id, title, topic, difficulty, expected_time, concept_tags, description)
            VALUES ({values})
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                topic=excluded.topic,
                difficulty=excluded.difficulty,
                expected_time=excluded.expected_time,
                concept_tags=excluded.concept_tags,
                description=excluded.description
        """
        for problem in problems:
            _execute(
                conn,
                query,
                (
                    problem["id"],
                    problem["title"],
                    problem["topic"],
                    problem["difficulty"],
                    float(problem["expected_time"]),
                    ",".join(problem["concept_tags"]),
                    problem["description"],
                ),
            ).close()


def log_attempt(attempt: dict[str, Any]) -> bool:
    with _connect_ctx() as conn:
        token = _placeholder(conn)
        source_platform = attempt.get("source_platform")
        external_submission_id = attempt.get("external_submission_id")
        timestamp = attempt.get("timestamp")

        columns = [
            "problem_id",
            "topic",
            "difficulty",
            "time_taken",
            "predicted_time",
            "confidence",
            "correct",
            "error_tag",
            "structural_features",
            "source_platform",
            "external_submission_id",
        ]
        params: list[Any] = [
            attempt["problem_id"],
            attempt["topic"],
            attempt["difficulty"],
            float(attempt["time_taken"]),
            float(attempt["predicted_time"]),
            int(attempt["confidence"]),
            bool(attempt["correct"]) if _is_postgres_conn(conn) else int(bool(attempt["correct"])),
            attempt.get("error_tag"),
            attempt.get("structural_features"),
            source_platform,
            external_submission_id,
        ]

        if timestamp:
            columns.append("timestamp")
            params.append(timestamp)

        placeholders = ", ".join([token] * len(columns))
        query = (
            f"INSERT INTO attempts ({', '.join(columns)}) "
            f"VALUES ({placeholders}) "
            "ON CONFLICT DO NOTHING"
        )
        cursor = _execute(conn, query, tuple(params))
        inserted = cursor.rowcount != 0
        cursor.close()
        return inserted


def fetch_attempts_with_problem_meta() -> list[dict[str, Any]]:
    query = """
    SELECT
        a.id,
        a.problem_id,
        a.topic,
        a.difficulty,
        a.time_taken,
        a.predicted_time,
        a.confidence,
        a.correct,
        a.error_tag,
        a.structural_features,
        a.source_platform,
        a.external_submission_id,
        a.timestamp,
        p.expected_time
    FROM attempts a
    JOIN problems p ON p.id = a.problem_id
    ORDER BY a.timestamp ASC, a.id ASC
    """

    with _connect_ctx() as conn:
        rows = _fetchall(conn, query)

    return [dict(row) for row in rows]
