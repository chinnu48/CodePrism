from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

try:
    import psycopg
except ImportError:  # pragma: no cover - optional dependency at runtime
    psycopg = None

SQLITE_DB_NAME = "skill_lab.db"
DEFAULT_POSTGRES_DB_NAME = "skill_lab"
ENV_FILE_NAME = ".env"
PASSWORD_HASH_ITERATIONS = 120_000
DEFAULT_ADMIN_USERNAME = "addme"
DEFAULT_ADMIN_PASSWORD = "admin@4848"
ROLE_ADMIN = "admin"
ROLE_USER = "user"


def _db_path() -> Path:
    return Path(__file__).resolve().parent / SQLITE_DB_NAME


def _env_path() -> Path:
    return Path(__file__).resolve().parent / ENV_FILE_NAME


def _load_local_env() -> None:
    path = _env_path()
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


def _default_postgres_url() -> str:
    scheme = (os.environ.get("SKILL_LAB_DB_SCHEME") or "postgresql").strip() or "postgresql"
    host = (os.environ.get("SKILL_LAB_DB_HOST") or os.environ.get("PGHOST") or "localhost").strip() or "localhost"
    port = (os.environ.get("SKILL_LAB_DB_PORT") or os.environ.get("PGPORT") or "5432").strip() or "5432"
    name = (
        os.environ.get("SKILL_LAB_DB_NAME")
        or os.environ.get("PGDATABASE")
        or DEFAULT_POSTGRES_DB_NAME
    ).strip() or DEFAULT_POSTGRES_DB_NAME
    user = (os.environ.get("SKILL_LAB_DB_USER") or os.environ.get("PGUSER") or "postgres").strip()
    password = (os.environ.get("SKILL_LAB_DB_PASSWORD") or os.environ.get("PGPASSWORD") or "").strip()

    auth = ""
    if user:
        auth = quote(user, safe="")
        if password:
            auth = f"{auth}:{quote(password, safe='')}"
        auth = f"{auth}@"

    return f"{scheme}://{auth}{host}:{port}/{name}"


def _database_url() -> str:
    _load_local_env()

    configured = (
        os.environ.get("SKILL_LAB_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()
    if configured:
        return configured
    return _default_postgres_url()


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
                "PostgreSQL is the default database but psycopg is not installed. "
                "Install it with: pip install psycopg[binary], or set "
                "SKILL_LAB_DATABASE_URL=sqlite:///C:/path/to/skill_lab.db to use SQLite explicitly."
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


def _normalize_username(username: str) -> str:
    return username.strip().lower()


def _hash_password(password: str, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        actual_salt,
        PASSWORD_HASH_ITERATIONS,
    )
    salt_b64 = base64.b64encode(actual_salt).decode("ascii")
    hash_b64 = base64.b64encode(derived).decode("ascii")
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt_b64}${hash_b64}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_b64, hash_b64 = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(hash_b64.encode("ascii"))
    except (TypeError, ValueError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _ensure_columns(conn: Any, table: str, required_columns: dict[str, str]) -> None:
    existing = _existing_columns(conn, table)
    for name, definition in required_columns.items():
        if name not in existing:
            _execute(conn, f"ALTER TABLE {table} ADD COLUMN {name} {definition}").close()


def _seed_default_admin(conn: Any) -> None:
    token = _placeholder(conn)
    admin_hash = _hash_password(DEFAULT_ADMIN_PASSWORD)
    existing = _fetchone(
        conn,
        f"SELECT id FROM users WHERE username = {token}",
        (DEFAULT_ADMIN_USERNAME,),
    )
    if existing is None:
        _execute(
            conn,
            f"INSERT INTO users (username, password_hash, role) VALUES ({token}, {token}, {token})",
            (DEFAULT_ADMIN_USERNAME, admin_hash, ROLE_ADMIN),
        ).close()
        return

    _execute(
        conn,
        f"UPDATE users SET password_hash = {token}, role = {token} WHERE username = {token}",
        (admin_hash, ROLE_ADMIN, DEFAULT_ADMIN_USERNAME),
    ).close()


def _problem_params(problem: dict[str, Any]) -> tuple[Any, ...]:
    return (
        problem["id"],
        problem["title"],
        problem["topic"],
        problem["difficulty"],
        float(problem["expected_time"]),
        ",".join(str(tag).strip() for tag in problem["concept_tags"] if str(tag).strip()),
        problem["description"],
        json.dumps(problem["test_cases"]),
        str(problem.get("problem_source") or "local"),
    )


def init_db() -> None:
    with _connect_ctx() as conn:
        if _is_postgres_conn(conn):
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
                """,
            ).close()
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
                    description TEXT NOT NULL DEFAULT '',
                    test_cases TEXT NOT NULL DEFAULT '[]',
                    problem_source TEXT NOT NULL DEFAULT 'local'
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
                    user_id BIGINT,
                    timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
                """,
            ).close()
            users_columns = {
                "role": "TEXT NOT NULL DEFAULT 'user'",
                "created_at": "TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP",
            }
            problems_columns = {
                "concept_tags": "TEXT NOT NULL DEFAULT ''",
                "description": "TEXT NOT NULL DEFAULT ''",
                "test_cases": "TEXT NOT NULL DEFAULT '[]'",
                "problem_source": "TEXT NOT NULL DEFAULT 'local'",
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
                "user_id": "BIGINT",
                "timestamp": "TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP",
            }
        else:
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """,
            ).close()
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
                    description TEXT NOT NULL DEFAULT '',
                    test_cases TEXT NOT NULL DEFAULT '[]',
                    problem_source TEXT NOT NULL DEFAULT 'local'
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
                    user_id INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(problem_id) REFERENCES problems(id)
                )
                """,
            ).close()
            users_columns = {
                "role": "TEXT NOT NULL DEFAULT 'user'",
                "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
            }
            problems_columns = {
                "concept_tags": "TEXT NOT NULL DEFAULT ''",
                "description": "TEXT NOT NULL DEFAULT ''",
                "test_cases": "TEXT NOT NULL DEFAULT '[]'",
                "problem_source": "TEXT NOT NULL DEFAULT 'local'",
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
                "user_id": "INTEGER",
                "timestamp": "DATETIME DEFAULT CURRENT_TIMESTAMP",
            }

        _ensure_columns(conn, "users", users_columns)
        _ensure_columns(conn, "problems", problems_columns)
        _ensure_columns(conn, "attempts", attempts_columns)
        _seed_default_admin(conn)

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
        _execute(
            conn,
            "CREATE INDEX IF NOT EXISTS ix_attempts_user_id ON attempts (user_id)",
        ).close()


def seed_problems(problems: list[dict[str, Any]]) -> None:
    with _connect_ctx() as conn:
        token = _placeholder(conn)
        values = ", ".join([token] * 9)
        query = f"""
            INSERT INTO problems (id, title, topic, difficulty, expected_time, concept_tags, description, test_cases, problem_source)
            VALUES ({values})
            ON CONFLICT(id) DO NOTHING
        """
        for problem in problems:
            _execute(conn, query, _problem_params(problem)).close()


def upsert_problems(problems: list[dict[str, Any]]) -> None:
    with _connect_ctx() as conn:
        token = _placeholder(conn)
        values = ", ".join([token] * 9)
        query = f"""
            INSERT INTO problems (id, title, topic, difficulty, expected_time, concept_tags, description, test_cases, problem_source)
            VALUES ({values})
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                topic=excluded.topic,
                difficulty=excluded.difficulty,
                expected_time=excluded.expected_time,
                concept_tags=excluded.concept_tags,
                description=excluded.description,
                test_cases=excluded.test_cases,
                problem_source=excluded.problem_source
        """
        for problem in problems:
            _execute(conn, query, _problem_params(problem)).close()


def fetch_problems(include_external: bool = False) -> list[dict[str, Any]]:
    with _connect_ctx() as conn:
        params: tuple[Any, ...] = ()
        query = """
            SELECT id, title, topic, difficulty, expected_time, concept_tags, description, test_cases, problem_source
            FROM problems
        """
        if not include_external:
            token = _placeholder(conn)
            query += f" WHERE problem_source = {token}"
            params = ("local",)
        query += " ORDER BY id ASC"
        rows = _fetchall(conn, query, params)

    problems: list[dict[str, Any]] = []
    for row in rows:
        raw_test_cases = str(row.get("test_cases") or "[]")
        try:
            test_cases = json.loads(raw_test_cases)
        except json.JSONDecodeError:
            test_cases = [{"input": None, "output": None}]
        if not isinstance(test_cases, list) or not test_cases:
            test_cases = [{"input": None, "output": None}]

        problems.append(
            {
                "id": int(row["id"]),
                "title": str(row["title"]),
                "topic": str(row["topic"]),
                "difficulty": str(row["difficulty"]),
                "expected_time": float(row["expected_time"]),
                "concept_tags": [
                    tag.strip()
                    for tag in str(row.get("concept_tags") or "").split(",")
                    if tag.strip()
                ],
                "description": str(row.get("description") or ""),
                "test_cases": test_cases,
                "problem_source": str(row.get("problem_source") or "local"),
            }
        )

    return problems


def create_user(username: str, password: str) -> dict[str, Any]:
    normalized = _normalize_username(username)
    if len(normalized) < 3:
        raise ValueError("Username must be at least 3 characters.")
    if not all(ch.isalnum() or ch in {"_", "-", "."} for ch in normalized):
        raise ValueError("Username may only contain letters, numbers, dots, dashes, and underscores.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    with _connect_ctx() as conn:
        token = _placeholder(conn)
        existing = _fetchone(
            conn,
            f"SELECT id, username FROM users WHERE username = {token}",
            (normalized,),
        )
        if existing is not None:
            raise ValueError("That username is already registered.")

        _execute(
            conn,
            f"INSERT INTO users (username, password_hash, role) VALUES ({token}, {token}, {token})",
            (normalized, _hash_password(password), ROLE_USER),
        ).close()
        user = _fetchone(
            conn,
            f"SELECT id, username, role, created_at FROM users WHERE username = {token}",
            (normalized,),
        )

    if user is None:
        raise RuntimeError("User registration completed but could not be loaded.")
    return user


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    normalized = _normalize_username(username)
    if not normalized or not password:
        return None

    with _connect_ctx() as conn:
        token = _placeholder(conn)
        row = _fetchone(
            conn,
            f"SELECT id, username, password_hash, role, created_at FROM users WHERE username = {token}",
            (normalized,),
        )

    if row is None or not _verify_password(password, str(row["password_hash"])):
        return None

    return {
        "id": row["id"],
        "username": row["username"],
        "role": row.get("role") or ROLE_USER,
        "created_at": row["created_at"],
    }


def log_attempt(attempt: dict[str, Any]) -> bool:
    with _connect_ctx() as conn:
        token = _placeholder(conn)
        source_platform = attempt.get("source_platform")
        external_submission_id = attempt.get("external_submission_id")
        timestamp = attempt.get("timestamp")
        user_id = attempt.get("user_id")

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

        if user_id is not None:
            columns.append("user_id")
            params.append(int(user_id))

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


def fetch_attempts_with_problem_meta(user_id: int | None = None) -> list[dict[str, Any]]:
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
        a.user_id,
        a.timestamp,
        p.expected_time
    FROM attempts a
    JOIN problems p ON p.id = a.problem_id
    """

    with _connect_ctx() as conn:
        params: tuple[Any, ...] = ()
        if user_id is not None:
            token = _placeholder(conn)
            query += f" WHERE a.user_id = {token}"
            params = (int(user_id),)
        query += " ORDER BY a.timestamp ASC, a.id ASC"
        rows = _fetchall(conn, query, params)

    return [dict(row) for row in rows]
