import os
import threading
from contextlib import contextmanager
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR
load_dotenv(ROOT_DIR / ".env")

_lock = threading.Lock()
_conn = None
_private_key_der = None


def _private_key_bytes():
    global _private_key_der
    if _private_key_der is not None:
        return _private_key_der

    key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    if not key_path:
        return None

    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

    passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    with open(key_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=passphrase.encode() if passphrase else None,
            backend=default_backend(),
        )
    _private_key_der = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return _private_key_der


def _connect_kwargs() -> dict:
    account = os.getenv("SNOWFLAKE_ACCOUNT")
    user = os.getenv("SNOWFLAKE_USER")
    if not account or not user:
        raise RuntimeError(
            "Missing SNOWFLAKE_ACCOUNT or SNOWFLAKE_USER. Copy .env.example to .env."
        )

    kwargs = {
        "account": account,
        "user": user,
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
        "database": os.getenv("SNOWFLAKE_DATABASE", "TRANSIT_SURVEY"),
        "schema": os.getenv("SNOWFLAKE_SCHEMA", "STARTUP_FORM"),
        "role": os.getenv("SNOWFLAKE_ROLE") or None,
        "client_session_keep_alive": True,
    }

    key_bytes = _private_key_bytes()
    if key_bytes:
        kwargs["private_key"] = key_bytes
    else:
        password = os.getenv("SNOWFLAKE_PASSWORD")
        if not password:
            raise RuntimeError(
                "Set SNOWFLAKE_PASSWORD or SNOWFLAKE_PRIVATE_KEY_PATH in .env."
            )
        kwargs["password"] = password

    return {k: v for k, v in kwargs.items() if v is not None}


def _is_open(conn) -> bool:
    try:
        return conn is not None and not conn.is_closed()
    except Exception:
        return False


def _open_connection():
    return snowflake.connector.connect(**_connect_kwargs())


def _reset_connection():
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
    _conn = None


def _ensure_connection():
    global _conn
    if not _is_open(_conn):
        _conn = _open_connection()
    return _conn


@contextmanager
def get_connection():
    with _lock:
        yield _ensure_connection()


def _run(sql: str, params: tuple | list | None, fetch: bool):
    last_error = None
    for attempt in range(2):
        try:
            conn = _ensure_connection()
            cur = conn.cursor()
            try:
                cur.execute(sql, params)
                if not fetch:
                    conn.commit()
                    return None
                if not cur.description:
                    return []
                columns = [col[0].lower() for col in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
            finally:
                cur.close()
        except Exception as exc:
            last_error = exc
            _reset_connection()
            if attempt == 1:
                raise
    raise last_error


def fetch_all(sql: str, params: tuple | list | None = None) -> list[dict]:
    with _lock:
        return _run(sql, params, fetch=True)


def fetch_one(sql: str, params: tuple | list | None = None) -> dict | None:
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple | list | None = None) -> None:
    with _lock:
        _run(sql, params, fetch=False)
