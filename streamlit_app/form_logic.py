from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime
from typing import Any


def empty_form() -> dict:
    return {
        "project_name": "",
        "project_list_name": "",
        "client_name": "",
        "location_city_county": "",
        "location_state": "",
        "field_start_date": None,
        "project_manager_name": "",
        "field_supervisor_name": "",
        "od_intercept": None,
        "questionnaire_filename": "",
        "questionnaire_path": "",
        "sampling_plan_filename": "",
        "sampling_plan_path": "",
        "callback_languages": [],
        "od_translation_languages": [],
        "non_destination_place_type": None,
        "extra_trips_survey": None,
        "companion_survey": None,
        "tour_survey": None,
        "od_intercept_weekend": None,
        "questionnaire_weekend_filename": "",
        "questionnaire_weekend_path": "",
        "sampling_plan_weekend_filename": "",
        "sampling_plan_weekend_path": "",
        "callback_languages_weekend": [],
        "od_translation_languages_weekend": [],
        "non_destination_place_type_weekend": None,
        "extra_trips_survey_weekend": None,
        "companion_survey_weekend": None,
        "tour_survey_weekend": None,
        "sas_survey": None,
        "sas_translation_languages": [],
        "additional_notes": "",
    }


def _as_date_value(value: Any):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def snapshot_to_form(snapshot: dict | None) -> dict:
    if not snapshot:
        return empty_form()
    form = empty_form()
    for key in form:
        if key not in snapshot:
            continue
        value = snapshot.get(key)
        if key == "field_start_date":
            form[key] = _as_date_value(value)
        elif isinstance(form[key], list):
            form[key] = list(value or [])
        elif form[key] == "":
            form[key] = value or ""
        else:
            form[key] = value
    return form


def match_person_choice(name: str, users: list[dict]) -> dict:
    if not name:
        return {"choice": "", "other": ""}
    match = next((user for user in users if user.get("display_name") == name or user.get("name") == name), None)
    if match:
        return {"choice": match["id"], "other": ""}
    return {"choice": "other", "other": name}


def person_name(choice: str, other: str, users: list[dict]) -> str:
    if choice == "other":
        return (other or "").strip()
    match = next((user for user in users if user.get("id") == choice), None)
    if match:
        return match.get("display_name") or match.get("name") or ""
    return (choice or other or "").strip()


def form_fill_percent(*, actor_name: str, project_id: str, form: dict, manager_name: str, supervisor_name: str) -> int:
    checks = [
        bool(actor_name),
        bool(project_id),
        bool((form.get("project_name") or "").strip()),
        bool((form.get("client_name") or "").strip()),
        bool((form.get("location_city_county") or "").strip()),
        bool((form.get("location_state") or "").strip()),
        bool(form.get("field_start_date")),
        bool(manager_name),
        bool(supervisor_name),
        form.get("od_intercept") is not None,
        form.get("od_intercept_weekend") is not None,
        form.get("sas_survey") is not None,
        bool((form.get("additional_notes") or "").strip()),
    ]
    if form.get("od_intercept") is True:
        checks.extend(
            [
                bool(form.get("questionnaire_filename")),
                bool(form.get("sampling_plan_filename")),
                bool(form.get("callback_languages")),
                bool(form.get("od_translation_languages")),
                form.get("non_destination_place_type") is not None,
                form.get("extra_trips_survey") is not None,
                form.get("companion_survey") is not None,
                form.get("tour_survey") is not None,
            ]
        )
    if form.get("od_intercept_weekend") is True:
        checks.extend(
            [
                bool(form.get("questionnaire_weekend_filename")),
                bool(form.get("sampling_plan_weekend_filename")),
                bool(form.get("callback_languages_weekend")),
                bool(form.get("od_translation_languages_weekend")),
                form.get("non_destination_place_type_weekend") is not None,
                form.get("extra_trips_survey_weekend") is not None,
                form.get("companion_survey_weekend") is not None,
                form.get("tour_survey_weekend") is not None,
            ]
        )
    if form.get("sas_survey") is True:
        checks.append(bool(form.get("sas_translation_languages")))
    done = sum(1 for item in checks if item)
    return round((done / len(checks)) * 100)


def form_fingerprint(*, form: dict, actor_name: str, manager_name: str, supervisor_name: str) -> str:
    payload = deepcopy(form)
    start = payload.get("field_start_date")
    if isinstance(start, date):
        payload["field_start_date"] = start.isoformat()
    return json.dumps(
        {
            "form": payload,
            "actorName": actor_name,
            "managerName": manager_name,
            "supervisorName": supervisor_name,
        },
        sort_keys=True,
        default=str,
    )


def format_yes_no(value: Any) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Unset"


def format_when(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%b %d, %Y, %I:%M %p").replace(" 0", " ")
    if isinstance(value, date):
        return value.strftime("%b %d, %Y")
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%b %d, %Y, %I:%M %p").replace(" 0", " ")
    except ValueError:
        return text


def _same_value(left, right) -> bool:
    if isinstance(left, list) or isinstance(right, list):
        return json.dumps(sorted(map(str, left or []))) == json.dumps(sorted(map(str, right or [])))
    return str(left or "") == str(right or "")


def _display_value(value) -> str:
    if isinstance(value, list):
        return ", ".join(value) if value else "none"
    if value is True or value is False:
        return format_yes_no(value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value) if value else "—"


DIFF_FIELDS = [
    ("project_list_name", "Project list"),
    ("project_name", "Project name"),
    ("client_name", "Client"),
    ("location_city_county", "City / county"),
    ("location_state", "State"),
    ("field_start_date", "Field start date"),
    ("project_manager_name", "Project manager"),
    ("field_supervisor_name", "Field supervisor"),
    ("od_intercept", "Weekday O-D"),
    ("questionnaire_filename", "Weekday questionnaire"),
    ("sampling_plan_filename", "Weekday sampling plan"),
    ("callback_languages", "Weekday call-back languages"),
    ("od_translation_languages", "Weekday full-translation languages"),
    ("non_destination_place_type", "Weekday non-destination"),
    ("extra_trips_survey", "Weekday extra-trips"),
    ("companion_survey", "Weekday companion"),
    ("tour_survey", "Weekday 24-hour TOUR"),
    ("od_intercept_weekend", "Weekend O-D"),
    ("questionnaire_weekend_filename", "Weekend questionnaire"),
    ("sampling_plan_weekend_filename", "Weekend sampling plan"),
    ("callback_languages_weekend", "Weekend call-back languages"),
    ("od_translation_languages_weekend", "Weekend full-translation languages"),
    ("non_destination_place_type_weekend", "Weekend non-destination"),
    ("extra_trips_survey_weekend", "Weekend extra-trips"),
    ("companion_survey_weekend", "Weekend companion"),
    ("tour_survey_weekend", "Weekend 24-hour TOUR"),
    ("sas_survey", "SAS survey"),
    ("sas_translation_languages", "SAS languages"),
    ("additional_notes", "Notes"),
]


def snapshot_diff(current, previous) -> list[str]:
    if not previous:
        return ["First save for this project"]
    changes = []
    for key, label in DIFF_FIELDS:
        if not _same_value(current.get(key) if current else None, previous.get(key) if previous else None):
            changes.append(f"{label}: {_display_value(previous.get(key) if previous else None)} → {_display_value(current.get(key) if current else None)}")
    if not changes:
        return ["Saved again with no field changes"]
    return changes[:5]


def format_project_brief(*, project_title, actor_name, manager_name, supervisor_name, form, last_saved_label) -> str:
    def line(label, value):
        return f"{label}: {_display_value(value)}"

    parts = [
        "Transit survey project brief",
        project_title or "Untitled project",
        last_saved_label or "Not saved yet",
        "",
        line("Filled out by", actor_name),
        line("Project list", form.get("project_list_name") or project_title),
        line("Project name", form.get("project_name") or project_title),
        line("Client", form.get("client_name")),
        line(
            "Location",
            ", ".join(item for item in [form.get("location_city_county"), form.get("location_state")] if item),
        ),
        line("Field start", form.get("field_start_date")),
        line("Project manager", manager_name),
        line("Field supervisor", supervisor_name),
        "",
        line("Weekday O-D", form.get("od_intercept")),
    ]
    if form.get("od_intercept") is True:
        parts.extend(
            [
                line("Weekday questionnaire", form.get("questionnaire_filename")),
                line("Weekday sampling plan", form.get("sampling_plan_filename")),
                line("Weekday call-back", form.get("callback_languages")),
                line("Weekday full translation", form.get("od_translation_languages")),
                line("Weekday 24-hour TOUR", form.get("tour_survey")),
            ]
        )
    parts.extend(["", line("Weekend O-D", form.get("od_intercept_weekend"))])
    if form.get("od_intercept_weekend") is True:
        parts.extend(
            [
                line("Weekend questionnaire", form.get("questionnaire_weekend_filename")),
                line("Weekend sampling plan", form.get("sampling_plan_weekend_filename")),
                line("Weekend call-back", form.get("callback_languages_weekend")),
                line("Weekend full translation", form.get("od_translation_languages_weekend")),
                line("Weekend 24-hour TOUR", form.get("tour_survey_weekend")),
            ]
        )
    parts.extend(
        [
            "",
            line("SAS survey", form.get("sas_survey")),
            line("SAS languages", form.get("sas_translation_languages")) if form.get("sas_survey") is True else None,
            "",
            "Notes:",
            (form.get("additional_notes") or "").strip() or "—",
        ]
    )
    return "\n".join(item for item in parts if item is not None)
