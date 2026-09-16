import os
import re
import secrets
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.db import execute, fetch_all, fetch_one
from lib.serializers import json_array, row_to_named, row_to_snapshot
from lib.storage import presigned_url, stored_name_from_path, upload_bytes

USER_COLUMNS = "ID, DISPLAY_NAME, IS_ACTIVE, IS_ADMIN, CREATED_AT"


class ServiceError(RuntimeError):
    pass


def _unwrap(exc: Exception) -> ServiceError:
    if isinstance(exc, ServiceError):
        return exc
    detail = getattr(exc, "detail", None)
    return ServiceError(str(detail if detail not in (None, "") else exc))


def health() -> dict:
    row = fetch_one("SELECT CURRENT_VERSION() AS VERSION")
    return {"ok": True, "snowflake": True, "version": row["version"] if row else None}


def bootstrap() -> dict:
    return {
        "ok": True,
        "users": [row_to_named(row) for row in fetch_all(f"SELECT {USER_COLUMNS} FROM USERS ORDER BY DISPLAY_NAME")],
        "projects": [
            row_to_named(row, "name")
            for row in fetch_all("SELECT ID, NAME, IS_ACTIVE, CREATED_AT FROM PROJECTS ORDER BY NAME")
        ],
        "languages": [
            row_to_named(row, "name")
            for row in fetch_all("SELECT ID, NAME, IS_ACTIVE, CREATED_AT FROM LANGUAGES ORDER BY NAME")
        ],
    }


def list_users() -> list[dict]:
    return [
        row_to_named(row)
        for row in fetch_all(f"SELECT {USER_COLUMNS} FROM USERS ORDER BY DISPLAY_NAME")
    ]


def list_projects() -> list[dict]:
    return [
        row_to_named(row, "name")
        for row in fetch_all("SELECT ID, NAME, IS_ACTIVE, CREATED_AT FROM PROJECTS ORDER BY NAME")
    ]


def list_languages() -> list[dict]:
    return [
        row_to_named(row, "name")
        for row in fetch_all("SELECT ID, NAME, IS_ACTIVE, CREATED_AT FROM LANGUAGES ORDER BY NAME")
    ]


def refresh_lists() -> dict:
    return {
        "users": list_users(),
        "projects": list_projects(),
        "languages": list_languages(),
    }


def find_or_create_user(name: str) -> dict:
    trimmed = (name or "").strip()
    if not trimmed:
        return {"id": None, "name": ""}
    existing = fetch_one(
        f"SELECT {USER_COLUMNS} FROM USERS WHERE LOWER(DISPLAY_NAME) = LOWER(%s)",
        (trimmed,),
    )
    if existing:
        if not existing.get("is_active"):
            execute("UPDATE USERS SET IS_ACTIVE = TRUE WHERE ID = %s", (existing["id"],))
            existing = fetch_one(f"SELECT {USER_COLUMNS} FROM USERS WHERE ID = %s", (existing["id"],))
        row = row_to_named(existing)
        return {"id": row["id"], "name": row["display_name"] or row["name"]}
    item_id = str(uuid.uuid4())
    execute(
        "INSERT INTO USERS (ID, DISPLAY_NAME, IS_ACTIVE, IS_ADMIN) VALUES (%s, %s, TRUE, FALSE)",
        (item_id, trimmed),
    )
    return {"id": item_id, "name": trimmed}


def create_project(name: str) -> dict:
    trimmed = (name or "").strip()
    if not trimmed:
        raise ServiceError("Project name is required.")
    item_id = str(uuid.uuid4())
    execute("INSERT INTO PROJECTS (ID, NAME, IS_ACTIVE) VALUES (%s, %s, TRUE)", (item_id, trimmed))
    row = fetch_one("SELECT ID, NAME, IS_ACTIVE, CREATED_AT FROM PROJECTS WHERE ID = %s", (item_id,))
    return row_to_named(row, "name")


def find_or_create_language(name: str) -> dict:
    trimmed = (name or "").strip()
    if not trimmed:
        raise ServiceError("Language name is required.")
    existing = fetch_one(
        "SELECT ID, NAME, IS_ACTIVE, CREATED_AT FROM LANGUAGES WHERE LOWER(NAME) = LOWER(%s)",
        (trimmed,),
    )
    if existing:
        if not existing.get("is_active"):
            execute("UPDATE LANGUAGES SET IS_ACTIVE = TRUE WHERE ID = %s", (existing["id"],))
            existing = fetch_one(
                "SELECT ID, NAME, IS_ACTIVE, CREATED_AT FROM LANGUAGES WHERE ID = %s",
                (existing["id"],),
            )
        return row_to_named(existing, "name")
    item_id = str(uuid.uuid4())
    execute("INSERT INTO LANGUAGES (ID, NAME, IS_ACTIVE) VALUES (%s, %s, TRUE)", (item_id, trimmed))
    row = fetch_one("SELECT ID, NAME, IS_ACTIVE, CREATED_AT FROM LANGUAGES WHERE ID = %s", (item_id,))
    return row_to_named(row, "name")


def admin_password_configured() -> bool:
    return bool((os.getenv("ADMIN_PASSWORD") or "").strip())


def verify_admin_password(password: str | None) -> bool:
    expected = (os.getenv("ADMIN_PASSWORD") or "").strip()
    if not expected:
        raise ServiceError("Set ADMIN_PASSWORD in .env.")
    given = (password or "").strip()
    if not given or not secrets.compare_digest(given, expected):
        raise ServiceError("Admin password is incorrect.")
    return True


def _require_admin(password: str | None) -> None:
    verify_admin_password(password)


def update_named(kind: str, item_id: str, password: str | None, *, name: str | None = None, is_active: bool | None = None) -> dict:
    _require_admin(password)
    tables = {
        "users": ("USERS", "DISPLAY_NAME", USER_COLUMNS, None),
        "projects": ("PROJECTS", "NAME", "ID, NAME, IS_ACTIVE, CREATED_AT", "name"),
        "languages": ("LANGUAGES", "NAME", "ID, NAME, IS_ACTIVE, CREATED_AT", "name"),
    }
    if kind not in tables:
        raise ServiceError("Unknown list.")
    table, name_col, columns, name_key = tables[kind]
    existing = fetch_one(f"SELECT ID FROM {table} WHERE ID = %s", (item_id,))
    if not existing:
        raise ServiceError("Item not found.")
    if name is not None:
        execute(f"UPDATE {table} SET {name_col} = %s WHERE ID = %s", (name.strip(), item_id))
    if is_active is not None:
        execute(f"UPDATE {table} SET IS_ACTIVE = %s WHERE ID = %s", (is_active, item_id))
    row = fetch_one(f"SELECT {columns} FROM {table} WHERE ID = %s", (item_id,))
    return row_to_named(row, name_key or "display_name")


def admin_records(password: str | None) -> list[dict]:
    _require_admin(password)
    rows = fetch_all(
        """
        SELECT
            p.ID AS PROJECT_ID,
            p.NAME AS PROJECT_LIST_NAME,
            p.IS_ACTIVE AS PROJECT_IS_ACTIVE,
            s.ID AS SNAPSHOT_ID,
            s.SAVED_AT,
            s.SAVED_BY_NAME,
            s.PROJECT_NAME,
            s.CLIENT_NAME,
            s.LOCATION_CITY_COUNTY,
            s.LOCATION_STATE,
            (
                SELECT COUNT(*)
                FROM PROJECT_SNAPSHOTS x
                WHERE x.PROJECT_ID = p.ID
            ) AS VERSION_COUNT
        FROM PROJECTS p
        LEFT JOIN PROJECT_SNAPSHOTS s
            ON s.PROJECT_ID = p.ID
            AND s.SAVED_AT = (
                SELECT MAX(SAVED_AT)
                FROM PROJECT_SNAPSHOTS x
                WHERE x.PROJECT_ID = p.ID
            )
        ORDER BY s.SAVED_AT DESC NULLS LAST, p.NAME
        """
    )
    return [
        {
            "project_id": row["project_id"],
            "project_list_name": row.get("project_list_name"),
            "project_is_active": bool(row.get("project_is_active", True)),
            "snapshot_id": row.get("snapshot_id"),
            "saved_at": row.get("saved_at"),
            "saved_by_name": row.get("saved_by_name"),
            "project_name": row.get("project_name"),
            "client_name": row.get("client_name"),
            "location_city_county": row.get("location_city_county"),
            "location_state": row.get("location_state"),
            "version_count": int(row.get("version_count") or 0),
        }
        for row in rows
    ]


def list_snapshots(project_id: str) -> list[dict]:
    if not fetch_one("SELECT ID FROM PROJECTS WHERE ID = %s", (project_id,)):
        raise ServiceError("Project not found.")
    rows = fetch_all(
        """
        SELECT * FROM PROJECT_SNAPSHOTS
        WHERE PROJECT_ID = %s
        ORDER BY SAVED_AT DESC
        """,
        (project_id,),
    )
    return [row_to_snapshot(row) for row in rows]


def latest_snapshot(project_id: str) -> dict | None:
    if not fetch_one("SELECT ID FROM PROJECTS WHERE ID = %s", (project_id,)):
        raise ServiceError("Project not found.")
    row = fetch_one(
        """
        SELECT * FROM PROJECT_SNAPSHOTS
        WHERE PROJECT_ID = %s
        ORDER BY SAVED_AT DESC
        LIMIT 1
        """,
        (project_id,),
    )
    if not row:
        return None
    return row_to_snapshot(row)


def get_snapshot(snapshot_id: str) -> dict:
    row = fetch_one("SELECT * FROM PROJECT_SNAPSHOTS WHERE ID = %s", (snapshot_id,))
    if not row:
        raise ServiceError("Snapshot not found.")
    return row_to_snapshot(row)


def save_snapshot(project_id: str, body: dict) -> dict:
    saved_by_name = (body.get("saved_by_name") or "").strip()
    if not saved_by_name:
        raise ServiceError("saved_by_name is required")

    snapshot_id = str(uuid.uuid4())
    execute(
        """
        INSERT INTO PROJECT_SNAPSHOTS (
            ID, PROJECT_ID, SAVED_BY_USER_ID, SAVED_BY_NAME,
            PROJECT_NAME, CLIENT_NAME, LOCATION_CITY_COUNTY, LOCATION_STATE,
            FIELD_START_DATE, PROJECT_MANAGER_NAME, FIELD_SUPERVISOR_NAME,
            OD_INTERCEPT, QUESTIONNAIRE_FILENAME, QUESTIONNAIRE_PATH,
            SAMPLING_PLAN_FILENAME, SAMPLING_PLAN_PATH,
            CALLBACK_LANGUAGES, OD_TRANSLATION_LANGUAGES,
            NON_DESTINATION_PLACE_TYPE, EXTRA_TRIPS_SURVEY, COMPANION_SURVEY, TOUR_SURVEY,
            OD_INTERCEPT_WEEKEND, QUESTIONNAIRE_WEEKEND_FILENAME, QUESTIONNAIRE_WEEKEND_PATH,
            SAMPLING_PLAN_WEEKEND_FILENAME, SAMPLING_PLAN_WEEKEND_PATH,
            CALLBACK_LANGUAGES_WEEKEND, OD_TRANSLATION_LANGUAGES_WEEKEND,
            NON_DESTINATION_PLACE_TYPE_WEEKEND, EXTRA_TRIPS_SURVEY_WEEKEND, COMPANION_SURVEY_WEEKEND, TOUR_SURVEY_WEEKEND,
            SAS_SURVEY, SAS_TRANSLATION_LANGUAGES, ADDITIONAL_NOTES
        )
        SELECT
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            PARSE_JSON(%s), PARSE_JSON(%s),
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            PARSE_JSON(%s), PARSE_JSON(%s),
            %s, %s, %s, %s,
            %s, PARSE_JSON(%s), %s
        """,
        (
            snapshot_id,
            project_id,
            body.get("saved_by_user_id"),
            saved_by_name,
            body.get("project_name"),
            body.get("client_name"),
            body.get("location_city_county"),
            body.get("location_state"),
            body.get("field_start_date"),
            body.get("project_manager_name"),
            body.get("field_supervisor_name"),
            body.get("od_intercept"),
            body.get("questionnaire_filename"),
            body.get("questionnaire_path"),
            body.get("sampling_plan_filename"),
            body.get("sampling_plan_path"),
            json_array(body.get("callback_languages") or []),
            json_array(body.get("od_translation_languages") or []),
            body.get("non_destination_place_type"),
            body.get("extra_trips_survey"),
            body.get("companion_survey"),
            body.get("tour_survey"),
            body.get("od_intercept_weekend"),
            body.get("questionnaire_weekend_filename"),
            body.get("questionnaire_weekend_path"),
            body.get("sampling_plan_weekend_filename"),
            body.get("sampling_plan_weekend_path"),
            json_array(body.get("callback_languages_weekend") or []),
            json_array(body.get("od_translation_languages_weekend") or []),
            body.get("non_destination_place_type_weekend"),
            body.get("extra_trips_survey_weekend"),
            body.get("companion_survey_weekend"),
            body.get("tour_survey_weekend"),
            body.get("sas_survey"),
            json_array(body.get("sas_translation_languages") or []),
            body.get("additional_notes"),
        ),
    )
    return row_to_snapshot(
        {
            **body,
            "id": snapshot_id,
            "project_id": project_id,
            "saved_at": datetime.now(timezone.utc),
            "saved_by_name": saved_by_name,
        }
    )


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return cleaned or "upload"


def upload_file(original_name: str, content: bytes, content_type: str | None = None) -> dict:
    original = original_name or "upload"
    stored = f"{uuid.uuid4().hex}_{_safe_filename(original)}"
    try:
        stored_info = upload_bytes(stored, content, content_type)
    except Exception as exc:
        raise _unwrap(exc) from exc
    return {
        "original_filename": original,
        "stored_filename": stored,
        "key": stored_info["key"],
        "path": stored_info["path"],
        "url": stored_info["url"],
    }


def file_download_url(path: str, download_name: str | None = None) -> str:
    if not path:
        return ""
    stored = stored_name_from_path(path)
    if not stored or "/" in stored or "\\" in stored:
        return ""
    name = download_name or stored.split("_", 1)[-1]
    try:
        return presigned_url(stored, name)
    except Exception as exc:
        raise _unwrap(exc) from exc
