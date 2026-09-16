import os
import re
import secrets
import sys
import uuid
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from lib.db import BACKEND_DIR, execute, fetch_all, fetch_one
from lib.models import CreateNamedItem, SnapshotCreate, UpdateNamedItem
from lib.serializers import json_array, row_to_named, row_to_snapshot
from lib.storage import presigned_url, upload_bytes

app = FastAPI(title="Transit Survey Project Startup Form")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _admin_password() -> str:
    return (os.getenv("ADMIN_PASSWORD") or "").strip()


def _assert_admin_password(password: str | None):
    expected = _admin_password()
    if not expected:
        raise HTTPException(status_code=503, detail="Set ADMIN_PASSWORD in .env and restart the API.")
    given = (password or "").strip()
    if not given or not secrets.compare_digest(given, expected):
        raise HTTPException(status_code=403, detail="Admin password is incorrect.")
    return True


def require_admin(x_admin_password: str | None = Header(default=None, alias="X-Admin-Password")):
    return _assert_admin_password(x_admin_password)


USER_COLUMNS = "ID, DISPLAY_NAME, IS_ACTIVE, IS_ADMIN, CREATED_AT"


@app.get("/api/health")
def health():
    try:
        row = fetch_one("SELECT CURRENT_VERSION() AS VERSION")
        return {"ok": True, "snowflake": True, "version": row["version"] if row else None}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/bootstrap")
def bootstrap():
    try:
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
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/users")
def list_users(active_only: bool = False):
    sql = f"SELECT {USER_COLUMNS} FROM USERS"
    if active_only:
        sql += " WHERE IS_ACTIVE = TRUE"
    sql += " ORDER BY DISPLAY_NAME"
    return [row_to_named(row) for row in fetch_all(sql)]


@app.post("/api/admin/login")
def admin_login(body: dict):
    _assert_admin_password((body or {}).get("password"))
    return {"ok": True}


@app.post("/api/users")
def create_user(body: CreateNamedItem):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    existing = fetch_one(
        f"SELECT {USER_COLUMNS} FROM USERS WHERE LOWER(DISPLAY_NAME) = LOWER(%s)",
        (name,),
    )
    if existing:
        if not existing.get("is_active"):
            execute("UPDATE USERS SET IS_ACTIVE = TRUE WHERE ID = %s", (existing["id"],))
            existing = fetch_one(f"SELECT {USER_COLUMNS} FROM USERS WHERE ID = %s", (existing["id"],))
        return row_to_named(existing)
    item_id = str(uuid.uuid4())
    execute(
        "INSERT INTO USERS (ID, DISPLAY_NAME, IS_ACTIVE, IS_ADMIN) VALUES (%s, %s, TRUE, FALSE)",
        (item_id, name),
    )
    row = fetch_one(f"SELECT {USER_COLUMNS} FROM USERS WHERE ID = %s", (item_id,))
    return row_to_named(row)


@app.patch("/api/users/{user_id}")
def update_user(
    user_id: str,
    body: UpdateNamedItem,
    _admin=Depends(require_admin),
):
    existing = fetch_one("SELECT ID FROM USERS WHERE ID = %s", (user_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    if body.name is not None:
        execute("UPDATE USERS SET DISPLAY_NAME = %s WHERE ID = %s", (body.name.strip(), user_id))
    if body.is_active is not None:
        execute("UPDATE USERS SET IS_ACTIVE = %s WHERE ID = %s", (body.is_active, user_id))
    if body.is_admin is not None:
        execute("UPDATE USERS SET IS_ADMIN = %s WHERE ID = %s", (body.is_admin, user_id))
    row = fetch_one(f"SELECT {USER_COLUMNS} FROM USERS WHERE ID = %s", (user_id,))
    return row_to_named(row)


@app.get("/api/projects")
def list_projects(active_only: bool = False):
    sql = "SELECT ID, NAME, IS_ACTIVE, CREATED_AT FROM PROJECTS"
    if active_only:
        sql += " WHERE IS_ACTIVE = TRUE"
    sql += " ORDER BY NAME"
    return [row_to_named(row, "name") for row in fetch_all(sql)]


@app.post("/api/projects")
def create_project(body: CreateNamedItem):
    item_id = str(uuid.uuid4())
    execute(
        "INSERT INTO PROJECTS (ID, NAME, IS_ACTIVE) VALUES (%s, %s, TRUE)",
        (item_id, body.name.strip()),
    )
    row = fetch_one("SELECT ID, NAME, IS_ACTIVE, CREATED_AT FROM PROJECTS WHERE ID = %s", (item_id,))
    return row_to_named(row, "name")


@app.patch("/api/projects/{project_id}")
def update_project(project_id: str, body: UpdateNamedItem, _admin=Depends(require_admin)):
    existing = fetch_one("SELECT ID FROM PROJECTS WHERE ID = %s", (project_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    if body.name is not None:
        execute("UPDATE PROJECTS SET NAME = %s WHERE ID = %s", (body.name.strip(), project_id))
    if body.is_active is not None:
        execute("UPDATE PROJECTS SET IS_ACTIVE = %s WHERE ID = %s", (body.is_active, project_id))
    row = fetch_one("SELECT ID, NAME, IS_ACTIVE, CREATED_AT FROM PROJECTS WHERE ID = %s", (project_id,))
    return row_to_named(row, "name")


@app.get("/api/languages")
def list_languages(active_only: bool = False):
    sql = "SELECT ID, NAME, IS_ACTIVE, CREATED_AT FROM LANGUAGES"
    if active_only:
        sql += " WHERE IS_ACTIVE = TRUE"
    sql += " ORDER BY NAME"
    return [row_to_named(row, "name") for row in fetch_all(sql)]


@app.post("/api/languages")
def create_language(body: CreateNamedItem):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    existing = fetch_one(
        "SELECT ID, NAME, IS_ACTIVE, CREATED_AT FROM LANGUAGES WHERE LOWER(NAME) = LOWER(%s)",
        (name,),
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
    execute(
        "INSERT INTO LANGUAGES (ID, NAME, IS_ACTIVE) VALUES (%s, %s, TRUE)",
        (item_id, name),
    )
    row = fetch_one("SELECT ID, NAME, IS_ACTIVE, CREATED_AT FROM LANGUAGES WHERE ID = %s", (item_id,))
    return row_to_named(row, "name")


@app.patch("/api/languages/{language_id}")
def update_language(language_id: str, body: UpdateNamedItem, _admin=Depends(require_admin)):
    existing = fetch_one("SELECT ID FROM LANGUAGES WHERE ID = %s", (language_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Language not found")
    if body.name is not None:
        execute("UPDATE LANGUAGES SET NAME = %s WHERE ID = %s", (body.name.strip(), language_id))
    if body.is_active is not None:
        execute("UPDATE LANGUAGES SET IS_ACTIVE = %s WHERE ID = %s", (body.is_active, language_id))
    row = fetch_one("SELECT ID, NAME, IS_ACTIVE, CREATED_AT FROM LANGUAGES WHERE ID = %s", (language_id,))
    return row_to_named(row, "name")


@app.get("/api/admin/records")
def admin_records(_admin=Depends(require_admin)):
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


@app.get("/api/projects/{project_id}/snapshots")
def list_snapshots(project_id: str):
    if not fetch_one("SELECT ID FROM PROJECTS WHERE ID = %s", (project_id,)):
        raise HTTPException(status_code=404, detail="Project not found")
    rows = fetch_all(
        """
        SELECT * FROM PROJECT_SNAPSHOTS
        WHERE PROJECT_ID = %s
        ORDER BY SAVED_AT DESC
        """,
        (project_id,),
    )
    return [row_to_snapshot(row) for row in rows]


@app.get("/api/projects/{project_id}/snapshots/latest")
def latest_snapshot(project_id: str):
    if not fetch_one("SELECT ID FROM PROJECTS WHERE ID = %s", (project_id,)):
        raise HTTPException(status_code=404, detail="Project not found")
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


@app.get("/api/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: str):
    row = fetch_one("SELECT * FROM PROJECT_SNAPSHOTS WHERE ID = %s", (snapshot_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return row_to_snapshot(row)


@app.post("/api/projects/{project_id}/snapshots")
def create_snapshot(project_id: str, body: SnapshotCreate):
    if not fetch_one("SELECT ID FROM PROJECTS WHERE ID = %s", (project_id,)):
        raise HTTPException(status_code=404, detail="Project not found")
    if not body.saved_by_name.strip():
        raise HTTPException(status_code=400, detail="saved_by_name is required")

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
            body.saved_by_user_id,
            body.saved_by_name.strip(),
            body.project_name,
            body.client_name,
            body.location_city_county,
            body.location_state,
            body.field_start_date,
            body.project_manager_name,
            body.field_supervisor_name,
            body.od_intercept,
            body.questionnaire_filename,
            body.questionnaire_path,
            body.sampling_plan_filename,
            body.sampling_plan_path,
            json_array(body.callback_languages),
            json_array(body.od_translation_languages),
            body.non_destination_place_type,
            body.extra_trips_survey,
            body.companion_survey,
            body.tour_survey,
            body.od_intercept_weekend,
            body.questionnaire_weekend_filename,
            body.questionnaire_weekend_path,
            body.sampling_plan_weekend_filename,
            body.sampling_plan_weekend_path,
            json_array(body.callback_languages_weekend),
            json_array(body.od_translation_languages_weekend),
            body.non_destination_place_type_weekend,
            body.extra_trips_survey_weekend,
            body.companion_survey_weekend,
            body.tour_survey_weekend,
            body.sas_survey,
            json_array(body.sas_translation_languages),
            body.additional_notes,
        ),
    )
    row = fetch_one("SELECT * FROM PROJECT_SNAPSHOTS WHERE ID = %s", (snapshot_id,))
    return row_to_snapshot(row)


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return cleaned or "upload"


@app.post("/api/uploads")
async def upload_file(file: UploadFile = File(...)):
    original = file.filename or "upload"
    stored = f"{uuid.uuid4().hex}_{_safe_filename(original)}"
    content = await file.read()
    stored_info = upload_bytes(stored, content, file.content_type)
    return {
        "original_filename": original,
        "stored_filename": stored,
        "key": stored_info["key"],
        "path": stored_info["path"],
        "url": stored_info["url"],
    }


@app.get("/api/files/{stored_filename}")
def download_file(stored_filename: str):
    if "/" in stored_filename or "\\" in stored_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    download_name = stored_filename.split("_", 1)[-1]
    return RedirectResponse(presigned_url(stored_filename, download_name), status_code=302)


frontend_dist = BACKEND_DIR.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    print("Starting API at http://127.0.0.1:8000")
    print("Open the form at http://localhost:5173 (run npm run dev in frontend)")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
