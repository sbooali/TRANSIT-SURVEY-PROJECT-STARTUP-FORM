import json
from datetime import date, datetime
from typing import Any


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            return [text]
    return [str(value)]


def json_array(values: list[str] | None) -> str:
    return json.dumps(values or [])


def row_to_named(row: dict, name_key: str = "display_name") -> dict:
    return {
        "id": row["id"],
        "name": row.get("name") or row.get("display_name"),
        "display_name": row.get("display_name") or row.get("name"),
        "is_active": bool(row.get("is_active", True)),
        "is_admin": bool(row.get("is_admin", False)),
        "created_at": row.get("created_at"),
    }


def row_to_snapshot(row: dict) -> dict:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "saved_at": row.get("saved_at"),
        "saved_by_user_id": row.get("saved_by_user_id"),
        "saved_by_name": row.get("saved_by_name"),
        "project_name": row.get("project_name"),
        "project_list_name": row.get("project_list_name"),
        "client_name": row.get("client_name"),
        "location_city_county": row.get("location_city_county"),
        "location_state": row.get("location_state"),
        "field_start_date": _as_date(row.get("field_start_date")),
        "project_manager_name": row.get("project_manager_name"),
        "field_supervisor_name": row.get("field_supervisor_name"),
        "od_intercept": _as_bool(row.get("od_intercept")),
        "questionnaire_filename": row.get("questionnaire_filename"),
        "questionnaire_path": row.get("questionnaire_path"),
        "sampling_plan_filename": row.get("sampling_plan_filename"),
        "sampling_plan_path": row.get("sampling_plan_path"),
        "callback_languages": as_list(row.get("callback_languages")),
        "od_translation_languages": as_list(row.get("od_translation_languages")),
        "non_destination_place_type": _as_bool(row.get("non_destination_place_type")),
        "extra_trips_survey": _as_bool(row.get("extra_trips_survey")),
        "companion_survey": _as_bool(row.get("companion_survey")),
        "tour_survey": _as_bool(row.get("tour_survey")),
        "od_intercept_weekend": _as_bool(row.get("od_intercept_weekend")),
        "questionnaire_weekend_filename": row.get("questionnaire_weekend_filename"),
        "questionnaire_weekend_path": row.get("questionnaire_weekend_path"),
        "sampling_plan_weekend_filename": row.get("sampling_plan_weekend_filename"),
        "sampling_plan_weekend_path": row.get("sampling_plan_weekend_path"),
        "callback_languages_weekend": as_list(row.get("callback_languages_weekend")),
        "od_translation_languages_weekend": as_list(row.get("od_translation_languages_weekend")),
        "non_destination_place_type_weekend": _as_bool(row.get("non_destination_place_type_weekend")),
        "extra_trips_survey_weekend": _as_bool(row.get("extra_trips_survey_weekend")),
        "companion_survey_weekend": _as_bool(row.get("companion_survey_weekend")),
        "tour_survey_weekend": _as_bool(row.get("tour_survey_weekend")),
        "sas_survey": _as_bool(row.get("sas_survey")),
        "sas_translation_languages": as_list(row.get("sas_translation_languages")),
        "additional_notes": row.get("additional_notes"),
    }


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return bool(value)


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return value
