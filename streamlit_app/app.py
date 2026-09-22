from __future__ import annotations

import html
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from data import (
    admin_records,
    bootstrap,
    create_project,
    file_download_url,
    find_or_create_language,
    find_or_create_project,
    find_or_create_user,
    project_list_name,
    get_snapshot,
    latest_snapshot,
    list_snapshots,
    refresh_lists,
    save_snapshot,
    update_named,
    upload_file,
    verify_admin_password,
)
from form_logic import (
    empty_form,
    form_fill_percent,
    form_fingerprint,
    format_project_brief,
    format_when,
    format_yes_no,
    match_person_choice,
    person_name,
    snapshot_diff,
    snapshot_to_form,
)

st.set_page_config(page_title="Transit Survey Desk", layout="wide", initial_sidebar_state="collapsed")

BRAND_MARK = """<div class="mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="5.2" y="4.2" width="13.6" height="16.4" rx="2.3" stroke="currentColor" stroke-width="1.7"/>
  <rect x="8.3" y="2.7" width="7.4" height="2.8" rx="1.1" fill="currentColor"/>
  <path d="M8.4 10.2h5.4M8.4 13h4.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
  <circle cx="9.1" cy="16.8" r="1.15" fill="currentColor"/>
  <circle cx="16.2" cy="16.8" r="1.15" fill="currentColor"/>
  <path d="M9.1 16.8c2.2 0 3.6-2.6 7.1-2.6" stroke="currentColor" stroke-width="1.55" stroke-linecap="round"/>
</svg></div>"""

STYLE_PATH = Path(__file__).resolve().parent / "styles.css"
YN_LABELS = {True: "Yes", False: "No", None: "Unset"}
YN_VALUES = {"Yes": True, "No": False, "Unset": None}
UPLOAD_FIELDS = {
    "questionnaire": ("questionnaire_filename", "questionnaire_path"),
    "sampling": ("sampling_plan_filename", "sampling_plan_path"),
    "questionnaire_weekend": ("questionnaire_weekend_filename", "questionnaire_weekend_path"),
    "sampling_weekend": ("sampling_plan_weekend_filename", "sampling_plan_weekend_path"),
}
SNAPSHOT_FILES = (
    ("Questionnaire", "questionnaire_filename", "questionnaire_path"),
    ("Sampling plan", "sampling_plan_filename", "sampling_plan_path"),
    ("Weekend questionnaire", "questionnaire_weekend_filename", "questionnaire_weekend_path"),
    ("Weekend sampling plan", "sampling_plan_weekend_filename", "sampling_plan_weekend_path"),
)
FILE_FIELD_KEYS = [key for pair in UPLOAD_FIELDS.values() for key in pair]


def inject_css() -> None:
    css = STYLE_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def init_state() -> None:
    defaults = {
        "page": "form",
        "connected": None,
        "error": "",
        "notice": "",
        "users": [],
        "projects": [],
        "languages": [],
        "form": empty_form(),
        "history": [],
        "viewing_snapshot": None,
        "last_saved": None,
        "baseline": "",
        "pending_baseline": True,
        "admin_ok": False,
        "admin_password": "",
        "admin_snapshot": None,
        "admin_versions": [],
        "admin_records": [],
        "show_history": False,
        "show_brief": False,
        "show_admin_login": False,
        "show_new_project": False,
        "show_save_success": False,
        "save_success_message": "",
        "bootstrapped": False,
        "lang_nonce": 0,
        "file_nonce": 0,
        "stored_files": {},
        "saving": False,
        "pending_save": False,
        "pending_form_reset": False,
        "blank_entry": False,
        "pending_project_select": "",
        "pending_person_select": {},
        "actor_choice": "",
        "actor_other": "",
        "pm_choice": "",
        "pm_other": "",
        "fs_choice": "",
        "fs_other": "",
        "project_id": "",
        "od_kit_choice": "Weekday",
        "toast": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def set_lists(payload: dict) -> None:
    st.session_state.users = payload.get("users") or []
    st.session_state.projects = payload.get("projects") or []
    st.session_state.languages = payload.get("languages") or []


def active_items(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row.get("is_active", True)]


def lang_name(row: dict) -> str:
    return row.get("display_name") or row.get("name") or ""


def hydrate_yes_no(key: str, value) -> None:
    if value is True:
        st.session_state[f"yn_{key}"] = "Yes"
    elif value is False:
        st.session_state[f"yn_{key}"] = "No"
    else:
        st.session_state[f"yn_{key}"] = None


def apply_pending_person_select() -> None:
    pending = st.session_state.pop("pending_person_select", None) or {}
    for prefix, user_id in pending.items():
        if not user_id:
            continue
        st.session_state[f"sel_{prefix}"] = user_id
        st.session_state[f"{prefix}_choice"] = user_id
        st.session_state[f"other_{prefix}"] = ""
        st.session_state[f"{prefix}_other"] = ""


def hydrate_person(prefix: str, name: str) -> None:
    matched = match_person_choice(name or "", st.session_state.users)
    if matched["choice"] == "other" and matched["other"]:
        created = find_or_create_user(matched["other"])
        remember_user(created)
        if created.get("id"):
            matched = {"choice": created["id"], "other": ""}
    st.session_state[f"sel_{prefix}"] = matched["choice"]
    st.session_state[f"other_{prefix}"] = matched["other"]
    st.session_state[f"{prefix}_choice"] = matched["choice"]
    st.session_state[f"{prefix}_other"] = matched["other"]


def hydrate_form_widgets(form: dict) -> None:
    st.session_state.w_project_name = form.get("project_name") or ""
    st.session_state.w_client_name = form.get("client_name") or ""
    st.session_state.w_city = form.get("location_city_county") or ""
    st.session_state.w_state = form.get("location_state") or ""
    st.session_state.w_field_start = form.get("field_start_date")
    st.session_state.w_notes = form.get("additional_notes") or ""
    hydrate_person("pm", form.get("project_manager_name") or "")
    hydrate_person("fs", form.get("field_supervisor_name") or "")
    for key in [
        "od_intercept",
        "od_intercept_weekend",
        "sas_survey",
        "non_destination_place_type",
        "extra_trips_survey",
        "companion_survey",
        "tour_survey",
        "non_destination_place_type_weekend",
        "extra_trips_survey_weekend",
        "companion_survey_weekend",
        "tour_survey_weekend",
    ]:
        hydrate_yes_no(key, form.get(key))
    st.session_state.sas_langs = list(form.get("sas_translation_languages") or [])
    st.session_state.lang_nonce += 1
    st.session_state.file_nonce += 1


def stored_files_from(source: dict | None) -> dict:
    source = source or {}
    return {key: source.get(key) or "" for key in FILE_FIELD_KEYS}


def clear_form_file_fields(form: dict) -> None:
    for key in FILE_FIELD_KEYS:
        form[key] = ""


def reset_upload_widgets() -> None:
    st.session_state.file_nonce += 1
    for kind in UPLOAD_FIELDS:
        st.session_state.pop(f"processed_{kind}", None)


def has_attached_file(name_key: str) -> bool:
    form = st.session_state.form
    stored = st.session_state.get("stored_files") or {}
    return bool(form.get(name_key) or stored.get(name_key))


def file_pair_for_save(name_key: str, path_key: str, enabled: bool) -> tuple[str | None, str | None]:
    if not enabled:
        return None, None
    form = st.session_state.form
    stored = st.session_state.get("stored_files") or {}
    name = form.get(name_key) or stored.get(name_key) or None
    path = form.get(path_key) or stored.get(path_key) or None
    return name, path


def form_for_status() -> dict:
    form = dict(st.session_state.form)
    stored = st.session_state.get("stored_files") or {}
    for key in FILE_FIELD_KEYS:
        form[key] = form.get(key) or stored.get(key) or ""
    return form


def reset_form_for_new_entry() -> None:
    actor_sel = st.session_state.get("sel_actor") or st.session_state.get("actor_choice") or ""
    actor_other = st.session_state.get("other_actor") or st.session_state.get("actor_other") or ""
    project_id = st.session_state.get("project_id") or ""
    w_project = st.session_state.get("w_project") or project_id
    history = list(st.session_state.get("history") or [])
    last_saved = st.session_state.get("last_saved")
    st.session_state.viewing_snapshot = None
    st.session_state.od_kit_choice = "Weekday"
    apply_snapshot(None)
    st.session_state.project_id = project_id
    st.session_state.w_project = w_project
    st.session_state.history = history
    st.session_state.last_saved = last_saved
    st.session_state.blank_entry = True
    st.session_state.sel_actor = actor_sel
    st.session_state.other_actor = actor_other
    st.session_state.actor_choice = actor_sel
    st.session_state.actor_other = actor_other
    for prefix in ("pm", "fs"):
        st.session_state[f"sel_{prefix}"] = ""
        st.session_state[f"other_{prefix}"] = ""
        st.session_state[f"{prefix}_choice"] = ""
        st.session_state[f"{prefix}_other"] = ""
    reset_upload_widgets()


def apply_pending_form_reset() -> None:
    if not st.session_state.pop("pending_form_reset", False):
        return
    reset_form_for_new_entry()


def apply_snapshot(snapshot: dict | None, show_files: bool = False) -> None:
    form = snapshot_to_form(snapshot)
    st.session_state.stored_files = stored_files_from(snapshot)
    if not show_files:
        clear_form_file_fields(form)
    st.session_state.form = form
    hydrate_form_widgets(form)
    st.session_state.pending_baseline = True


def remember_save(snapshot: dict | None) -> None:
    if not snapshot:
        st.session_state.last_saved = None
        return
    st.session_state.last_saved = {
        "saved_at": snapshot.get("saved_at"),
        "saved_by_name": snapshot.get("saved_by_name"),
    }


def remember_project(project: dict) -> None:
    if not project.get("id"):
        return
    projects = list(st.session_state.projects or [])
    if any(str(item.get("id")) == str(project["id"]) for item in projects):
        return
    projects.append(
        {
            "id": project["id"],
            "name": project.get("name") or project.get("display_name") or "",
            "display_name": project.get("display_name") or project.get("name") or "",
            "is_active": True,
        }
    )
    projects.sort(key=lambda item: (item.get("name") or item.get("display_name") or "").lower())
    st.session_state.projects = projects


def apply_pending_project_select() -> None:
    pending = st.session_state.pop("pending_project_select", None)
    if pending is None or pending == "":
        return
    st.session_state.w_project = pending


def load_project(project_id: str, apply_latest: bool = True) -> None:
    st.session_state.project_id = project_id or ""
    st.session_state.viewing_snapshot = None
    st.session_state.notice = ""
    st.session_state.error = ""
    if not project_id:
        apply_snapshot(None)
        st.session_state.history = []
        remember_save(None)
        return
    try:
        latest = latest_snapshot(project_id)
        versions = list_snapshots(project_id)
        st.session_state.history = versions
        remember_save(latest)
        if apply_latest and latest:
            apply_snapshot(latest)
            st.session_state.blank_entry = False
        else:
            apply_snapshot(None)
    except Exception as exc:
        st.session_state.error = str(exc)


def on_project_change() -> None:
    choice = (st.session_state.get("w_project") or "").strip()
    projects = active_items(st.session_state.projects)
    known_ids = {str(item["id"]) for item in projects}
    if not choice:
        st.session_state.blank_entry = True
        load_project("", apply_latest=False)
        return
    if choice in known_ids:
        st.session_state.blank_entry = True
        load_project(choice, apply_latest=False)
        return
    try:
        project, existed = find_or_create_project(choice)
        remember_project(project)
        reload_lists()
        st.session_state.pending_project_select = project["id"]
        st.session_state.blank_entry = not existed
        load_project(project["id"], apply_latest=existed)
    except Exception as exc:
        st.session_state.error = str(exc)


def ensure_bootstrap() -> None:
    if st.session_state.bootstrapped:
        return
    try:
        payload = bootstrap()
        set_lists(payload)
        st.session_state.connected = True
        st.session_state.error = ""
    except Exception as exc:
        st.session_state.connected = False
        st.session_state.error = str(exc) or "Could not reach Snowflake."
    st.session_state.bootstrapped = True


def reload_lists() -> None:
    set_lists(refresh_lists())


def remember_user(user: dict) -> None:
    if not user.get("id"):
        return
    users = list(st.session_state.users or [])
    if any(str(item.get("id")) == str(user["id"]) for item in users):
        return
    users.append(
        {
            "id": user["id"],
            "name": user.get("name") or "",
            "display_name": user.get("name") or "",
            "is_active": True,
            "is_admin": False,
        }
    )
    users.sort(key=lambda item: (item.get("display_name") or item.get("name") or "").lower())
    st.session_state.users = users


def resolve_user(name: str) -> tuple[dict, bool]:
    trimmed = (name or "").strip()
    if not trimmed:
        return {"id": None, "name": ""}, False
    for item in st.session_state.get("users") or []:
        label = (item.get("display_name") or item.get("name") or "").strip()
        if label.lower() == trimmed.lower():
            return {"id": item.get("id"), "name": label}, False
    return find_or_create_user(trimmed), True


def run_save() -> None:
    st.session_state.saving = True
    st.session_state.error = ""
    st.rerun()


def complete_save() -> None:
    try:
        with st.spinner("Saving…"):
            save_form()
    finally:
        st.session_state.saving = False
    if not st.session_state.error:
        form = st.session_state.form
        message = st.session_state.get("save_success_message") or (
            f"{(form.get('project_name') or form.get('project_list_name') or 'Project').strip()} saved successfully."
        )
        close_dialogs()
        st.session_state.show_save_success = True
        st.session_state.save_success_message = message
    st.rerun()


def current_person(prefix: str) -> tuple[str, str]:
    choice = st.session_state.get(f"sel_{prefix}", st.session_state.get(f"{prefix}_choice", ""))
    other = st.session_state.get(f"other_{prefix}", st.session_state.get(f"{prefix}_other", ""))
    return choice or "", other or ""


def actor_manager_supervisor() -> tuple[str, str, str]:
    users = st.session_state.users
    actor_choice, actor_other = current_person("actor")
    pm_choice, pm_other = current_person("pm")
    fs_choice, fs_other = current_person("fs")
    return (
        person_name(actor_choice, actor_other, users),
        person_name(pm_choice, pm_other, users),
        person_name(fs_choice, fs_other, users),
    )


def sync_text_fields(form: dict) -> None:
    form["project_list_name"] = project_list_name(st.session_state.get("project_id") or "")
    form["project_name"] = st.session_state.get("w_project_name", form.get("project_name") or "")
    form["client_name"] = st.session_state.get("w_client_name", form.get("client_name") or "")
    form["location_city_county"] = st.session_state.get("w_city", form.get("location_city_county") or "")
    form["location_state"] = st.session_state.get("w_state", form.get("location_state") or "")
    form["field_start_date"] = st.session_state.get("w_field_start", form.get("field_start_date"))
    form["additional_notes"] = st.session_state.get("w_notes", form.get("additional_notes") or "")
    _pm, manager, supervisor = actor_manager_supervisor()
    form["project_manager_name"] = manager
    form["field_supervisor_name"] = supervisor
    for key in [
        "od_intercept",
        "od_intercept_weekend",
        "sas_survey",
        "non_destination_place_type",
        "extra_trips_survey",
        "companion_survey",
        "tour_survey",
        "non_destination_place_type_weekend",
        "extra_trips_survey_weekend",
        "companion_survey_weekend",
        "tour_survey_weekend",
    ]:
        label = st.session_state.get(f"yn_{key}")
        if label in YN_VALUES:
            form[key] = YN_VALUES[label]
        elif label in (None, "Unset", ""):
            form[key] = None
    form["sas_translation_languages"] = list(st.session_state.get("sas_langs") or form.get("sas_translation_languages") or [])


def next_action(*, actor_name: str, project_id: str, form: dict, dirty: bool, read_only: bool, last_saved: dict | None) -> str:
    if read_only:
        return "You are viewing an older save. Return to the latest version to keep editing."
    if not actor_name:
        return "First: choose who is filling this out."
    if not project_id:
        return "Next: choose a project. The latest save loads automatically."
    if form.get("od_intercept") is None:
        return "Next: set weekday O-D to Yes or No."
    if form.get("od_intercept") is True and not has_attached_file("questionnaire_filename"):
        return "Weekday O-D is on — upload the questionnaire."
    if form.get("od_intercept_weekend") is None:
        return "Next: set weekend O-D to Yes or No."
    if form.get("sas_survey") is None:
        return "Next: set SAS to Yes or No."
    if dirty:
        return "You have unsaved changes. Save to keep a new Snowflake version."
    if last_saved:
        return "All caught up. Edit anything and Save to add another version."
    return "Ready to save the first version of this project."


def save_block_reason(*, actor_name: str, project_id: str, read_only: bool) -> str | None:
    if read_only:
        return "Return to the latest save to edit"
    if not actor_name:
        return "Select who is filling this out"
    if not project_id:
        return "Select or create a project"
    return None


def yes_no(label: str, key: str, disabled: bool = False):
    widget_key = f"yn_{key}"
    if st.session_state.get(widget_key) == "Unset":
        st.session_state[widget_key] = None
    if widget_key not in st.session_state:
        hydrate_yes_no(key, st.session_state.form.get(key))
    choice = st.segmented_control(label, ["Yes", "No"], key=widget_key, disabled=disabled, required=False)
    st.session_state.form[key] = True if choice == "Yes" else False if choice == "No" else None
    return st.session_state.form[key]


def adopt_typed_person(prefix: str, users: list[dict]) -> None:
    choice = (st.session_state.get(f"sel_{prefix}") or "").strip()
    if not choice or choice == "other":
        return
    known_ids = {str(row.get("id")) for row in users}
    if choice in known_ids:
        return
    try:
        created = find_or_create_user(choice)
        if not created.get("id"):
            return
        remember_user(created)
        pending = dict(st.session_state.get("pending_person_select") or {})
        pending[prefix] = created["id"]
        st.session_state.pending_person_select = pending
        st.session_state.error = ""
    except Exception as exc:
        st.session_state.error = str(exc)
    st.rerun()


def person_field(label: str, prefix: str, users: list[dict], *, required: bool = False, disabled: bool = False) -> None:
    if st.session_state.get(f"sel_{prefix}") == "other":
        typed = (
            st.session_state.get(f"other_{prefix}")
            or st.session_state.get(f"{prefix}_other")
            or ""
        ).strip()
        if typed:
            created = find_or_create_user(typed)
            remember_user(created)
            if created.get("id"):
                st.session_state[f"sel_{prefix}"] = created["id"]
                st.session_state[f"{prefix}_choice"] = created["id"]
        else:
            st.session_state[f"sel_{prefix}"] = ""
    users = active_items(st.session_state.users)
    options = [("", "Select…")] + [(row["id"], row.get("display_name") or row.get("name")) for row in users]
    labels = {item[0]: item[1] for item in options}
    ids = [item[0] for item in options]
    heading = f"{label} *" if required else label
    if f"sel_{prefix}" not in st.session_state:
        st.session_state[f"sel_{prefix}"] = st.session_state.get(f"{prefix}_choice", "")
    current = st.session_state.get(f"sel_{prefix}")
    if current and current not in ids:
        ids = ids + [current]
        labels[current] = current
    st.selectbox(
        heading,
        ids,
        format_func=lambda item: labels.get(item, item or "Select…"),
        key=f"sel_{prefix}",
        disabled=disabled,
        accept_new_options=True,
        placeholder="Choose or type a name",
    )
    if not disabled:
        adopt_typed_person(prefix, users)


def file_href(path: str, filename: str) -> str:
    if not path or not filename:
        return ""
    try:
        return file_download_url(path, filename) or ""
    except Exception:
        return ""


def render_file_download(label: str, filename: str, path: str, key: str) -> None:
    name = (filename or "").strip()
    info, action = st.columns([3.2, 1], gap="small", vertical_alignment="center", wrap=False)
    with info:
        if name:
            st.markdown(f"<div class='file-chip'><span>{html.escape(label)}</span><span>{html.escape(name)}</span></div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='file-chip wait'><span>{html.escape(label)}</span><span>No file on this save</span></div>", unsafe_allow_html=True)
    with action:
        href = file_href(path, name)
        if href:
            st.link_button("Download", href, width="stretch", key=key)
        else:
            st.button("Download", disabled=True, width="stretch", key=key, help="Upload succeeded only if S3 is available. This save has no downloadable file.")


def render_snapshot_files(snapshot: dict, key_prefix: str) -> None:
    st.markdown("### Files")
    st.caption("Files live in the S3 folder for this project. Download opens a time-limited link.")
    for label, name_key, path_key in SNAPSHOT_FILES:
        render_file_download(label, snapshot.get(name_key) or "", snapshot.get(path_key) or "", f"{key_prefix}_{name_key}")


def render_version_picker(versions: list[dict], current_id: str, key: str) -> None:
    if not versions:
        st.caption("No versions saved yet.")
        return
    labels: list[str] = []
    by_label: dict[str, str] = {}
    current_label = ""
    for index, item in enumerate(versions):
        stamp = format_when(item.get("saved_at")) or f"Version {index + 1}"
        who = item.get("saved_by_name") or "—"
        label = f"{'Latest · ' if index == 0 else ''}{stamp} · {who}"
        if label in by_label:
            label = f"{label} ({index + 1})"
        labels.append(label)
        by_label[label] = str(item["id"])
        if str(item["id"]) == str(current_id):
            current_label = label
    if not current_label:
        current_label = labels[0]
    picked = st.radio(
        "All versions",
        labels,
        index=labels.index(current_label),
        key=key,
    )
    picked_id = by_label[picked]
    if picked_id != str(current_id):
        try:
            st.session_state.admin_snapshot = get_snapshot(picked_id)
            st.session_state.error = ""
            st.session_state.notice = f"Showing save from {picked}."
        except Exception as exc:
            st.session_state.error = str(exc)
        st.rerun()


def file_row(label: str, kind: str, filename: str, path: str, disabled: bool) -> None:
    with st.container():
        st.markdown('<div class="file-card-mark"></div>', unsafe_allow_html=True)
        st.markdown(f"<p class='file-label'>{html.escape(label)}</p>", unsafe_allow_html=True)
        if filename:
            href = file_href(path, filename)
            name = html.escape(filename)
            chip, dl = st.columns([3.2, 1], gap="small", vertical_alignment="center", wrap=False)
            with chip:
                st.markdown(
                    f"<div class='file-chip'><span>{name}</span><span>{'On S3 · replace below' if href else 'Saved on form · S3 download unavailable'}</span></div>",
                    unsafe_allow_html=True,
                )
            with dl:
                if href:
                    st.link_button("Download", href, width="stretch", key=f"dl_{kind}_{st.session_state.file_nonce}")
                else:
                    st.button("Download", disabled=True, width="stretch", key=f"dl_{kind}_{st.session_state.file_nonce}", help="The S3 bucket is missing or this file has no stored path.")
        else:
            st.markdown("<div class='file-chip wait'><span>No file yet</span><span>PDF, Word, or spreadsheet</span></div>", unsafe_allow_html=True)
        uploaded = st.file_uploader(
            f"Upload {label.lower()}",
            key=f"up_{kind}_{st.session_state.file_nonce}",
            disabled=disabled,
            label_visibility="collapsed",
        )
    if uploaded is not None and not disabled:
        token = f"{uploaded.name}:{uploaded.size}"
        processed_key = f"processed_{kind}"
        if st.session_state.get(processed_key) != token:
            try:
                result = upload_file(uploaded.name, uploaded.getvalue(), uploaded.type)
                name_key, path_key = UPLOAD_FIELDS[kind]
                st.session_state.form[name_key] = result["original_filename"]
                st.session_state.form[path_key] = result["path"]
                st.session_state[processed_key] = token
                st.session_state.file_nonce += 1
                st.session_state.toast = f"Uploaded {result['original_filename']} to S3."
                st.session_state.notice = st.session_state.toast
                st.session_state.error = ""
            except Exception as exc:
                st.session_state.error = str(exc)
            st.rerun()


def language_pills(label: str, key: str, options: list[str], selected: list[str], disabled: bool) -> list[str]:
    if key not in st.session_state:
        st.session_state[key] = [name for name in selected if name in options]
    picked = st.pills(
        label,
        options,
        selection_mode="multi",
        key=key,
        disabled=disabled or not options,
        width="content",
        wrap=True,
    )
    return [name for name in (picked or []) if name in options]


def add_language_controls(
    input_key: str,
    button_key: str,
    disabled: bool,
    *,
    placeholder: str = "Missing language name",
    on_click=None,
    args: tuple = (),
) -> None:
    with st.container():
        st.markdown('<div class="add-lang-row save-color-btn"></div>', unsafe_allow_html=True)
        field, action = st.columns([4.5, 1.2], gap="small", vertical_alignment="center", wrap=False)
        with field:
            st.text_input(
                "Add a language",
                key=input_key,
                disabled=disabled,
                placeholder=placeholder,
                label_visibility="collapsed",
            )
        with action:
            st.button(
                "Add",
                type="primary",
                key=button_key,
                disabled=disabled,
                width="stretch",
                on_click=on_click,
                args=args,
            )


def language_matrix(kit: str, callback_key: str, translation_key: str, languages: list[dict], disabled: bool) -> None:
    form = st.session_state.form
    st.caption("Tap a language for call-back, full translation, or both.")
    names = [lang_name(row) for row in languages]
    for extra in list(form.get(callback_key) or []) + list(form.get(translation_key) or []):
        if extra and extra not in names:
            names.append(extra)
    current_cb = list(form.get(callback_key) or [])
    current_tr = list(form.get(translation_key) or [])
    nonce = st.session_state.lang_nonce
    form[callback_key] = language_pills("Call-back", f"pills_cb_{kit}_{nonce}", names, current_cb, disabled)
    form[translation_key] = language_pills("Full translation", f"pills_tr_{kit}_{nonce}", names, current_tr, disabled)
    add_language_controls(
        f"new_lang_{kit}",
        f"btn_lang_{kit}",
        disabled,
        on_click=add_od_language,
        args=(kit, callback_key),
    )


def od_kit(prefix: str, enabled_key: str, languages: list[dict], disabled: bool) -> None:
    form = st.session_state.form
    weekend = prefix == "weekend"
    q_kind = "questionnaire_weekend" if weekend else "questionnaire"
    s_kind = "sampling_weekend" if weekend else "sampling"
    q_name = "questionnaire_weekend_filename" if weekend else "questionnaire_filename"
    q_path = "questionnaire_weekend_path" if weekend else "questionnaire_path"
    s_name = "sampling_plan_weekend_filename" if weekend else "sampling_plan_filename"
    s_path = "sampling_plan_weekend_path" if weekend else "sampling_plan_path"
    cb_key = "callback_languages_weekend" if weekend else "callback_languages"
    tr_key = "od_translation_languages_weekend" if weekend else "od_translation_languages"
    nd_key = "non_destination_place_type_weekend" if weekend else "non_destination_place_type"
    et_key = "extra_trips_survey_weekend" if weekend else "extra_trips_survey"
    co_key = "companion_survey_weekend" if weekend else "companion_survey"
    tour_key = "tour_survey_weekend" if weekend else "tour_survey"

    yes_no("O-D intercept survey?", enabled_key, disabled=disabled)
    if form.get(enabled_key) is not True:
        return

    st.markdown("<p class='file-label'>Files</p>", unsafe_allow_html=True)
    files_l, files_r = st.columns(2)
    with files_l:
        file_row("Questionnaire", q_kind, form.get(q_name) or "", form.get(q_path) or "", disabled)
    with files_r:
        file_row("Sampling plan / route list", s_kind, form.get(s_name) or "", form.get(s_path) or "", disabled)

    st.markdown("<p class='file-label'>Survey options</p>", unsafe_allow_html=True)
    opt_l, opt_r = st.columns(2)
    with opt_l:
        yes_no("Non-destination place type?", nd_key, disabled=disabled)
        yes_no("Companion survey?", co_key, disabled=disabled)
    with opt_r:
        yes_no("Extra-trips survey?", et_key, disabled=disabled)
        yes_no("24-hour TOUR survey?", tour_key, disabled=disabled)

    st.markdown("<p class='file-label'>Languages</p>", unsafe_allow_html=True)
    language_matrix(prefix, cb_key, tr_key, languages, disabled)


def close_dialogs() -> None:
    st.session_state.show_admin_login = False
    st.session_state.show_new_project = False
    st.session_state.show_history = False
    st.session_state.show_brief = False
    st.session_state.show_save_success = False


def dismiss_save_success() -> None:
    st.session_state.show_save_success = False


def dismiss_admin_login() -> None:
    st.session_state.show_admin_login = False


def dismiss_new_project() -> None:
    st.session_state.show_new_project = False


def dismiss_history() -> None:
    st.session_state.show_history = False


def dismiss_brief() -> None:
    st.session_state.show_brief = False


def open_admin() -> None:
    close_dialogs()
    if st.session_state.admin_ok:
        st.session_state.page = "admin"
        return
    st.session_state.show_admin_login = True


def dialog_form_actions(cancel_key: str, confirm_label: str, confirm_key: str) -> tuple[bool, bool]:
    with st.container():
        st.markdown('<div class="dialog-actions"></div>', unsafe_allow_html=True)
        left, right = st.columns(2, gap="small", vertical_alignment="center", wrap=False)
        with left:
            cancelled = st.form_submit_button("Cancel", key=cancel_key, width="stretch")
        with right:
            confirmed = st.form_submit_button(confirm_label, type="primary", key=confirm_key, width="stretch")
        return cancelled, confirmed


@st.dialog("Admin sign in", on_dismiss=dismiss_admin_login)
def admin_login_dialog() -> None:
    st.caption("The form stays available without signing in.")
    with st.form("admin_login_form", border=False):
        password = st.text_input("Password", type="password", key="admin_password_input", placeholder="Admin password")
        cancelled, signed_in = dialog_form_actions("admin_cancel", "Sign in", "admin_signin")
    if cancelled:
        st.session_state.show_admin_login = False
        st.rerun()
    if signed_in:
        try:
            verify_admin_password(password)
            st.session_state.admin_ok = True
            st.session_state.admin_password = password
            st.session_state.show_admin_login = False
            st.session_state.page = "admin"
            st.session_state.error = ""
        except Exception as exc:
            st.session_state.error = str(exc)
        st.rerun()


@st.dialog("New project", on_dismiss=dismiss_new_project)
def new_project_dialog() -> None:
    with st.form("new_project_form", border=False):
        name = st.text_input("Project name", key="new_project_name", placeholder="Project name")
        cancelled, created_click = dialog_form_actions("cancel_project", "Create", "create_project_btn")
    if cancelled:
        st.session_state.show_new_project = False
        st.rerun()
    if created_click:
        try:
            project, existed = find_or_create_project(name or "")
            reload_lists()
            st.session_state.pending_project_select = project["id"]
            st.session_state.show_new_project = False
            st.session_state.blank_entry = not existed
            load_project(project["id"], apply_latest=existed)
            label = project.get("name") or project.get("display_name")
            st.session_state.notice = f"{'Opened' if existed else 'Created'} {label}."
        except Exception as exc:
            st.session_state.error = str(exc)
        st.rerun()


@st.dialog("Save history", width="large", on_dismiss=dismiss_history)
def history_dialog() -> None:
    items = st.session_state.history or []
    if not items:
        st.write("No saves yet for this project.")
        return
    st.caption("Older saves are read-only. Open one to inspect it, then return to the latest version to keep editing.")
    for index, item in enumerate(items):
        previous = items[index + 1] if index + 1 < len(items) else None
        diffs = snapshot_diff(item, previous)
        label = "Latest — " if index == 0 else ""
        st.markdown(
            f"<div class='history-item'><strong>{html.escape(label + format_when(item.get('saved_at')))}</strong>"
            f"<span>Saved by {html.escape(item.get('saved_by_name') or '—')}</span></div>",
            unsafe_allow_html=True,
        )
        for change in diffs:
            st.markdown(f"- {change}")
        if st.button("Open this version", key=f"open_hist_{item['id']}"):
            try:
                snapshot = get_snapshot(item["id"])
                apply_snapshot(snapshot, show_files=True)
                st.session_state.viewing_snapshot = snapshot
                st.session_state.show_history = False
                st.session_state.notice = ""
            except Exception as exc:
                st.session_state.error = str(exc)
            st.rerun()


@st.dialog("Saved", on_dismiss=dismiss_save_success)
def save_success_dialog() -> None:
    message = st.session_state.get("save_success_message") or "Project saved successfully."
    st.markdown(f"<p class='save-success-copy'>{html.escape(message)}</p>", unsafe_allow_html=True)
    with st.container():
        st.markdown('<div class="dialog-actions"></div>', unsafe_allow_html=True)
        if st.button("OK", type="primary", width="stretch", key="save_success_ok"):
            dismiss_save_success()
            st.rerun()


@st.dialog("Project brief", width="large", on_dismiss=dismiss_brief)
def brief_dialog(text: str) -> None:
    st.code(text)
    st.download_button("Download brief", text, file_name="project-brief.txt", mime="text/plain")
    components.html(
        f"""
        <button style="font:700 14px 'Source Sans 3',sans-serif;padding:10px 16px;border:0;border-radius:12px;background:#2b6cb0;color:#fff;cursor:pointer"
          onclick='navigator.clipboard.writeText({json.dumps(text)}); this.textContent="Copied";'>
          Copy to clipboard
        </button>
        """,
        height=52,
    )
    if st.button("Close brief"):
        st.session_state.show_brief = False
        st.rerun()


def save_form() -> None:
    form = st.session_state.form
    actor_name, manager_name, supervisor_name = actor_manager_supervisor()
    project_id = st.session_state.project_id
    st.session_state.error = ""
    st.session_state.notice = ""
    if not actor_name:
        st.session_state.error = "Select who is filling out the form (or choose Other and type a name)."
        return
    if not project_id:
        st.session_state.error = "Select a project or create a new one."
        return
    try:
        actor, actor_new = resolve_user(actor_name)
        manager, manager_new = resolve_user(manager_name)
        supervisor, supervisor_new = resolve_user(supervisor_name)
        payload = {
            **form,
            "project_list_name": project_list_name(project_id),
            "saved_by_user_id": actor["id"],
            "saved_by_name": actor["name"],
            "project_manager_name": manager["name"] or None,
            "field_supervisor_name": supervisor["name"] or None,
            "field_start_date": form.get("field_start_date") or None,
            "callback_languages": form.get("callback_languages") or [] if form.get("od_intercept") else [],
            "od_translation_languages": form.get("od_translation_languages") or [] if form.get("od_intercept") else [],
            "non_destination_place_type": form.get("non_destination_place_type") if form.get("od_intercept") else None,
            "extra_trips_survey": form.get("extra_trips_survey") if form.get("od_intercept") else None,
            "companion_survey": form.get("companion_survey") if form.get("od_intercept") else None,
            "tour_survey": form.get("tour_survey") if form.get("od_intercept") else None,
            "questionnaire_weekend_filename": file_pair_for_save("questionnaire_weekend_filename", "questionnaire_weekend_path", bool(form.get("od_intercept_weekend")))[0],
            "questionnaire_weekend_path": file_pair_for_save("questionnaire_weekend_filename", "questionnaire_weekend_path", bool(form.get("od_intercept_weekend")))[1],
            "sampling_plan_weekend_filename": file_pair_for_save("sampling_plan_weekend_filename", "sampling_plan_weekend_path", bool(form.get("od_intercept_weekend")))[0],
            "sampling_plan_weekend_path": file_pair_for_save("sampling_plan_weekend_filename", "sampling_plan_weekend_path", bool(form.get("od_intercept_weekend")))[1],
            "callback_languages_weekend": form.get("callback_languages_weekend") or [] if form.get("od_intercept_weekend") else [],
            "od_translation_languages_weekend": form.get("od_translation_languages_weekend") or [] if form.get("od_intercept_weekend") else [],
            "non_destination_place_type_weekend": form.get("non_destination_place_type_weekend") if form.get("od_intercept_weekend") else None,
            "extra_trips_survey_weekend": form.get("extra_trips_survey_weekend") if form.get("od_intercept_weekend") else None,
            "companion_survey_weekend": form.get("companion_survey_weekend") if form.get("od_intercept_weekend") else None,
            "tour_survey_weekend": form.get("tour_survey_weekend") if form.get("od_intercept_weekend") else None,
            "sas_translation_languages": form.get("sas_translation_languages") or [] if form.get("sas_survey") else [],
        }
        saved = save_snapshot(project_id, payload)
        if actor_new:
            remember_user(actor)
        if manager_new:
            remember_user(manager)
        if supervisor_new:
            remember_user(supervisor)
        name = (saved.get("project_name") or saved.get("project_list_name") or form.get("project_name") or "Project").strip()
        st.session_state.save_success_message = f"{name} saved successfully."
        st.session_state.notice = ""
        st.session_state.toast = ""
        st.session_state.history = [saved] + [
            item for item in (st.session_state.history or []) if str(item.get("id")) != str(saved.get("id"))
        ]
        remember_save(saved)
        st.session_state.viewing_snapshot = None
        st.session_state.pending_form_reset = True
    except Exception as exc:
        st.session_state.error = str(exc)
    finally:
        st.session_state.pending_save = False


def return_to_latest() -> None:
    project_id = st.session_state.project_id
    if not project_id:
        return
    latest = latest_snapshot(project_id)
    apply_snapshot(latest)
    remember_save(latest)
    st.session_state.viewing_snapshot = None


def render_banners() -> None:
    if st.session_state.error:
        st.markdown(f"<div class='banner error'>{html.escape(st.session_state.error)}</div>", unsafe_allow_html=True)
    if st.session_state.notice and not st.session_state.get("show_save_success"):
        st.markdown(f"<div class='banner ok'>{html.escape(st.session_state.notice)}</div>", unsafe_allow_html=True)
    viewing = st.session_state.viewing_snapshot
    if viewing:
        st.markdown(
            f"<div class='banner info'>Viewing save from {html.escape(format_when(viewing.get('saved_at')))} "
            f"by {html.escape(viewing.get('saved_by_name') or '—')}. This version is read-only.</div>",
            unsafe_allow_html=True,
        )
        if st.button("Return to latest", type="primary"):
            try:
                return_to_latest()
            except Exception as exc:
                st.session_state.error = str(exc)
            st.rerun()


def add_named_from_admin(kind: str, title: str) -> None:
    name = (st.session_state.get(f"admin_new_{kind}") or "").strip()
    st.session_state.error = ""
    try:
        if kind == "users":
            find_or_create_user(name)
        elif kind == "projects":
            create_project(name)
        else:
            find_or_create_language(name)
        reload_lists()
        st.session_state[f"admin_new_{kind}"] = ""
        st.session_state.notice = f"Added to {title.lower()}."
    except Exception as exc:
        st.session_state.error = str(exc)


def add_od_language(kit: str, callback_key: str) -> None:
    form = st.session_state.form
    st.session_state.error = ""
    try:
        created = find_or_create_language(st.session_state.get(f"new_lang_{kit}") or "")
        label = lang_name(created)
        reload_lists()
        if label:
            form[callback_key] = list(dict.fromkeys(list(form.get(callback_key) or []) + [label]))
        st.session_state.lang_nonce += 1
        st.session_state.toast = f"Added {label}."
        st.session_state[f"new_lang_{kit}"] = ""
    except Exception as exc:
        st.session_state.error = str(exc)


def add_sas_language() -> None:
    st.session_state.error = ""
    try:
        created = find_or_create_language(st.session_state.get("new_lang_sas") or "")
        reload_lists()
        label = lang_name(created)
        if label:
            current = list(st.session_state.form.get("sas_translation_languages") or [])
            st.session_state.form["sas_translation_languages"] = list(dict.fromkeys(current + [label]))
        st.session_state.lang_nonce += 1
        st.session_state.new_lang_sas = ""
        st.session_state.toast = f"Added {label}."
    except Exception as exc:
        st.session_state.error = str(exc)


def named_admin(title: str, kind: str, items: list[dict], name_key: str) -> None:
    st.markdown(f"### {title}")
    st.caption("Add names used in the form dropdowns. Deactivate to hide them without changing old saves.")
    add_col, btn_col = st.columns([3, 1])
    with add_col:
        st.text_input(f"New {title[:-1].lower()} name", key=f"admin_new_{kind}")
    with btn_col:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        st.button("Add", key=f"admin_add_{kind}", on_click=add_named_from_admin, args=(kind, title))
    for item in items:
        label = item.get(name_key) or item.get("name") or item.get("display_name")
        status = "Active" if item.get("is_active") else "Inactive"
        left, mid, right = st.columns([3, 1, 1.4])
        with left:
            style = "text-decoration:line-through;color:#5b6773" if not item.get("is_active") else ""
            st.markdown(f"<div style='{style}'>{html.escape(label or '')}</div>", unsafe_allow_html=True)
        with mid:
            st.caption(status)
        with right:
            action = "Deactivate" if item.get("is_active") else "Reactivate"
            if st.button(action, key=f"toggle_{kind}_{item['id']}"):
                try:
                    update_named(
                        kind,
                        item["id"],
                        st.session_state.admin_password,
                        is_active=not item.get("is_active"),
                    )
                    reload_lists()
                except Exception as exc:
                    st.session_state.error = str(exc)
                st.rerun()


def snapshot_detail_html(snapshot: dict) -> str:
    def cell(label, value):
        return f"<div><dt>{html.escape(label)}</dt><dd>{html.escape(value or '—')}</dd></div>"

    blocks = [
        cell("Project list", snapshot.get("project_list_name") or project_list_name(str(snapshot.get("project_id") or "")) or ""),
        cell("Project name", snapshot.get("project_name") or ""),
        cell("Client", snapshot.get("client_name") or ""),
        cell("City or county", snapshot.get("location_city_county") or ""),
        cell("State", snapshot.get("location_state") or ""),
        cell("Field start", str(snapshot.get("field_start_date") or "—")),
        cell("Project manager", snapshot.get("project_manager_name") or ""),
        cell("Field supervisor", snapshot.get("field_supervisor_name") or ""),
        cell("O-D intercept (weekday)", format_yes_no(snapshot.get("od_intercept"))),
    ]
    if snapshot.get("od_intercept") is True:
        blocks.extend(
            [
                cell("Call-back languages", ", ".join(snapshot.get("callback_languages") or [])),
                cell("Full-translation languages", ", ".join(snapshot.get("od_translation_languages") or [])),
                cell("Non-destination", format_yes_no(snapshot.get("non_destination_place_type"))),
                cell("Extra-trips", format_yes_no(snapshot.get("extra_trips_survey"))),
                cell("Companion", format_yes_no(snapshot.get("companion_survey"))),
                cell("24-hour TOUR", format_yes_no(snapshot.get("tour_survey"))),
            ]
        )
    blocks.append(cell("O-D intercept (weekend)", format_yes_no(snapshot.get("od_intercept_weekend"))))
    if snapshot.get("od_intercept_weekend") is True:
        blocks.extend(
            [
                cell("Weekend call-back", ", ".join(snapshot.get("callback_languages_weekend") or [])),
                cell("Weekend full translation", ", ".join(snapshot.get("od_translation_languages_weekend") or [])),
                cell("Weekend 24-hour TOUR", format_yes_no(snapshot.get("tour_survey_weekend"))),
            ]
        )
    blocks.append(cell("SAS survey", format_yes_no(snapshot.get("sas_survey"))))
    if snapshot.get("sas_survey") is True:
        blocks.append(cell("SAS languages", ", ".join(snapshot.get("sas_translation_languages") or [])))
    notes = html.escape((snapshot.get("additional_notes") or "").strip() or "—")
    return f"<dl class='record-grid'>{''.join(blocks)}</dl><div class='file-chip'><span>Notes</span><span>{notes}</span></div>"


def render_admin() -> None:
    st.markdown(
        f"""
        <div class="brand-bar">
          <div class="brand-mark">{BRAND_MARK}<div><strong>Admin console</strong><span>Saved records and lists</span></div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.container():
        st.markdown('<div class="nav-actions"></div>', unsafe_allow_html=True)
        back_col, out_col = st.columns(2, gap="small", vertical_alignment="center", wrap=False)
        with back_col:
            if st.button("Back to form", key="admin_back", width="stretch"):
                st.session_state.page = "form"
                st.session_state.admin_snapshot = None
                st.rerun()
        with out_col:
            if st.button("Sign out", key="admin_signout", width="stretch"):
                st.session_state.admin_ok = False
                st.session_state.admin_password = ""
                st.session_state.page = "form"
                st.session_state.admin_snapshot = None
                st.rerun()
    render_banners()
    records_tab, lists_tab = st.tabs(["Saved records", "Lists"])
    with records_tab:
        if st.session_state.admin_snapshot:
            snapshot = st.session_state.admin_snapshot
            if st.button("Back to all records"):
                st.session_state.admin_snapshot = None
                st.session_state.admin_versions = []
                st.rerun()
            list_title = snapshot.get("project_list_name") or project_list_name(str(snapshot.get("project_id") or "")) or "Untitled project"
            setup_title = snapshot.get("project_name") or "—"
            st.markdown(f"## {html.escape(list_title)}")
            st.caption(f"Project name: {setup_title}")
            st.caption(f"Showing save from {format_when(snapshot.get('saved_at'))} by {snapshot.get('saved_by_name') or '—'}. Pick another version below to switch.")
            render_version_picker(
                st.session_state.admin_versions or [],
                str(snapshot.get("id") or ""),
                f"admin_version_radio_{snapshot.get('project_id')}",
            )
            st.markdown(snapshot_detail_html(snapshot), unsafe_allow_html=True)
            render_snapshot_files(snapshot, f"admin_file_{snapshot.get('id')}")
        else:
            st.markdown("## Saved records")
            st.caption("Every project save appears here, separate from the form. Open a row to read the latest answers and older versions.")
            try:
                records = admin_records(st.session_state.admin_password)
            except Exception as exc:
                st.session_state.error = str(exc)
                records = []
            if not records:
                st.write("No projects yet.")
            for record in records:
                list_title = record.get("project_list_name") or "Untitled list"
                setup_title = record.get("project_name") or "No project name yet"
                place = ", ".join(item for item in [record.get("location_city_county"), record.get("location_state")] if item)
                meta = f"{record.get('client_name') or 'No client yet'}" + (f" · {place}" if place else "")
                versions = int(record.get("version_count") or 0)
                st.markdown(
                    f"<div class='record-card'><p class='eyebrow'>Project list</p>"
                    f"<h3 class='serif'>{html.escape(list_title)}</h3>"
                    f"<p class='record-setup-name'>Project name: {html.escape(setup_title)}</p>"
                    f"<p>{html.escape(meta)}</p>"
                    f"<p>{html.escape(format_when(record.get('saved_at')) or 'No saves yet')} · "
                    f"{html.escape(record.get('saved_by_name') or '—')} · {versions} version{'s' if versions != 1 else ''}</p></div>",
                    unsafe_allow_html=True,
                )
                if st.button("View", key=f"view_rec_{record['project_id']}", disabled=not record.get("snapshot_id")):
                    try:
                        snapshot = get_snapshot(record["snapshot_id"])
                        if not snapshot.get("project_list_name"):
                            snapshot["project_list_name"] = record.get("project_list_name") or project_list_name(record["project_id"])
                        st.session_state.admin_snapshot = snapshot
                        st.session_state.admin_versions = list_snapshots(record["project_id"])
                        radio_key = f"admin_version_radio_{record['project_id']}"
                        if radio_key in st.session_state:
                            del st.session_state[radio_key]
                    except Exception as exc:
                        st.session_state.error = str(exc)
                    st.rerun()
    with lists_tab:
        named_admin("Users", "users", st.session_state.users, "display_name")
        named_admin("Projects", "projects", st.session_state.projects, "name")
        named_admin("Languages", "languages", st.session_state.languages, "name")


def render_form() -> None:
    apply_pending_person_select()
    form = st.session_state.form
    users = active_items(st.session_state.users)
    projects = active_items(st.session_state.projects)
    languages = active_items(st.session_state.languages)
    read_only = bool(st.session_state.viewing_snapshot)
    actor_name, manager_name, supervisor_name = actor_manager_supervisor()
    sync_text_fields(form)
    actor_name, manager_name, supervisor_name = actor_manager_supervisor()
    project_id = st.session_state.project_id
    fill = form_fill_percent(
        actor_name=actor_name,
        project_id=project_id,
        form=form_for_status(),
        manager_name=manager_name,
        supervisor_name=supervisor_name,
    )
    fingerprint = form_fingerprint(form=form, actor_name=actor_name, manager_name=manager_name, supervisor_name=supervisor_name)
    if st.session_state.pending_baseline:
        st.session_state.baseline = fingerprint
    dirty = bool(st.session_state.baseline) and fingerprint != st.session_state.baseline and not read_only
    selected = next((item for item in projects if item["id"] == project_id), None)
    project_title = form.get("project_name") or (selected.get("name") if selected else "No project selected")
    project_detail = " · ".join(
        item for item in [form.get("client_name"), ", ".join(part for part in [form.get("location_city_county"), form.get("location_state")] if part)] if item
    )
    last_saved = st.session_state.last_saved
    last_saved_label = (
        f"Saved {format_when(last_saved['saved_at'])}" + (f" by {last_saved['saved_by_name']}" if last_saved.get("saved_by_name") else "")
        if last_saved
        else ""
    )
    hint = next_action(
        actor_name=actor_name,
        project_id=project_id,
        form=form,
        dirty=dirty,
        read_only=read_only,
        last_saved=last_saved,
    )
    block = save_block_reason(actor_name=actor_name, project_id=project_id, read_only=read_only)
    if read_only:
        status, tone = "Viewing an older save", "info"
    elif dirty:
        status, tone = "Unsaved changes", "wait"
    elif last_saved_label:
        status, tone = "Saved", "live"
    else:
        status, tone = "Not started", "wait"

    st.markdown(
        f"""
        <div class="brand-bar">
          <div class="brand-mark">{BRAND_MARK}
          <div><strong>Transit Survey Desk</strong><span>Project startup form</span></div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.container():
        st.markdown('<div class="nav-actions"></div>', unsafe_allow_html=True)
        admin_col, brief_col, hist_col = st.columns(3, gap="small", vertical_alignment="center", wrap=False)
        with admin_col:
            if st.button("Admin", key="nav_admin", width="stretch"):
                open_admin()
                st.rerun()
        with brief_col:
            if st.button("Copy brief", key="nav_brief", width="stretch"):
                close_dialogs()
                st.session_state.show_brief = True
        with hist_col:
            history_count = len(st.session_state.history) if project_id else 0
            history_label = f"History ({history_count})" if history_count else "History"
            if st.button(history_label, disabled=not project_id, key="nav_history", width="stretch", help="Select a project first" if not project_id else "Open earlier saves"):
                try:
                    st.session_state.history = list_snapshots(project_id) if project_id else []
                    close_dialogs()
                    st.session_state.show_history = True
                except Exception as exc:
                    st.session_state.error = str(exc)
                    st.rerun()

    st.markdown(
        f"""
        <div class="workspace-strip">
          <div>
            <p class="eyebrow">Active project</p>
            <strong class="workspace-title">{html.escape(project_title)}</strong>
            <p class="workspace-detail">{html.escape(project_detail or "Add client and location in setup")}</p>
          </div>
          <div class="workspace-meta">
            <span class="pill {tone}">{html.escape(status)}</span>
            <span class="workspace-save">{html.escape(last_saved_label or "Not saved yet")}</span>
            <span class="workspace-fill">{fill}% complete</span>
          </div>
        </div>
        <div class="next-hint">{html.escape(hint)}</div>
        """,
        unsafe_allow_html=True,
    )

    od_state = "On" if form.get("od_intercept") is True or form.get("od_intercept_weekend") is True else "Off" if form.get("od_intercept") is False and form.get("od_intercept_weekend") is False else "—"
    sas_state = "Yes" if form.get("sas_survey") is True else "No" if form.get("sas_survey") is False else "—"
    steps = [
        ("Author", actor_name or "Needed", bool(actor_name)),
        ("Project", (selected or {}).get("name") or "Needed", bool(project_id)),
        ("Setup", form.get("client_name") or form.get("project_name") or "—", bool(form.get("project_name") and form.get("client_name"))),
        ("O-D", od_state, form.get("od_intercept") is not None and form.get("od_intercept_weekend") is not None),
        ("SAS", sas_state, form.get("sas_survey") is not None),
        ("Notes", "Added" if form.get("additional_notes") else "Optional", True),
    ]
    st.markdown(
        "<div class='step-line'>"
        + "".join(
            f"<span class='step-dot {'done' if done else ''}'><b>{html.escape(title)}</b> {html.escape(detail)}</span>"
            for title, detail, done in steps
        )
        + "</div>",
        unsafe_allow_html=True,
    )
    render_banners()

    with st.container():
        st.markdown("<div class='card-start'></div>", unsafe_allow_html=True)
        st.markdown("<div class='section-kicker'><span class='section-num'>1</span><p class='eyebrow'>Start here</p></div>", unsafe_allow_html=True)
        st.markdown("## Who")
        st.caption("Choose who is filling this out. Required to save.")
        person_field("User", "actor", users, required=True)

    with st.container():
        st.markdown("<div class='card-start'></div>", unsafe_allow_html=True)
        st.markdown("<p class='eyebrow'>Start here</p>", unsafe_allow_html=True)
        st.markdown("## Which project")
        st.caption("Select a list name to start a blank save. Type an existing name to open its last version.")
        ids = [""] + [item["id"] for item in projects]
        labels = {"": "Select a project…"}
        labels.update({item["id"]: item.get("name") or item.get("display_name") for item in projects})
        if "w_project" not in st.session_state:
            st.session_state.w_project = project_id
        st.selectbox(
            "Project *",
            ids,
            format_func=lambda item: labels.get(item, item or "Select a project…"),
            key="w_project",
            on_change=on_project_change,
            accept_new_options=True,
            placeholder="Choose or type a project name",
        )
        st.markdown('<div class="save-color-btn"></div>', unsafe_allow_html=True)
        if st.button("New project", type="primary", key="open_new_project"):
            close_dialogs()
            st.session_state.show_new_project = True

    with st.container():
        st.markdown("<div class='card-start'></div>", unsafe_allow_html=True)
        st.markdown("<div class='section-kicker'><span class='section-num'>2</span><p class='eyebrow'>Brief</p></div>", unsafe_allow_html=True)
        st.markdown("## Project set up info")
        st.caption("Core identity and field staffing for this survey.")
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("Project name", key="w_project_name", disabled=read_only)
            st.text_input("City or county", key="w_city", disabled=read_only)
            if "w_field_start" not in st.session_state:
                st.session_state.w_field_start = form.get("field_start_date")
            st.date_input("Field collection start date", key="w_field_start", disabled=read_only, format="YYYY-MM-DD")
        with c2:
            st.text_input("Client name", key="w_client_name", disabled=read_only)
            st.text_input("State", key="w_state", disabled=read_only)
        m1, m2 = st.columns(2)
        with m1:
            person_field("Project manager", "pm", users, disabled=read_only)
        with m2:
            person_field("Field supervisor", "fs", users, disabled=read_only)

    with st.container():
        st.markdown("<div class='card-start'></div>", unsafe_allow_html=True)
        st.markdown("<div class='section-kicker'><span class='section-num'>3</span><p class='eyebrow'>Instruments</p></div>", unsafe_allow_html=True)
        st.markdown("## O-D intercept survey")
        st.caption("Weekday and weekend kits are saved separately. Switch to edit each one.")
        weekday_status = "On" if form.get("od_intercept") is True else "Off" if form.get("od_intercept") is False else "Unset"
        weekend_status = "On" if form.get("od_intercept_weekend") is True else "Off" if form.get("od_intercept_weekend") is False else "Unset"
        kit = st.segmented_control(
            "O-D kit",
            ["Weekday", "Weekend"],
            key="od_kit_choice",
            label_visibility="collapsed",
        )
        st.caption(f"Weekday · {weekday_status}   ·   Weekend · {weekend_status}")
        if (kit or "Weekday") == "Weekend":
            od_kit("weekend", "od_intercept_weekend", languages, read_only)
        else:
            od_kit("weekday", "od_intercept", languages, read_only)

    with st.container():
        st.markdown("<div class='card-start'></div>", unsafe_allow_html=True)
        st.markdown("<div class='section-kicker'><span class='section-num'>4</span><p class='eyebrow'>Follow-up</p></div>", unsafe_allow_html=True)
        st.markdown("## SAS survey")
        yes_no("SAS survey?", "sas_survey", disabled=read_only)
        if form.get("sas_survey") is True:
            names = [lang_name(row) for row in languages]
            for extra in form.get("sas_translation_languages") or []:
                if extra not in names:
                    names.append(extra)
            picked = language_pills(
                "Full-translation languages",
                f"pills_sas_{st.session_state.lang_nonce}",
                names,
                list(form.get("sas_translation_languages") or []),
                read_only,
            )
            st.session_state.sas_langs = picked
            st.session_state.form["sas_translation_languages"] = picked
            add_language_controls("new_lang_sas", "btn_lang_sas", read_only, on_click=add_sas_language)

    with st.container():
        st.markdown("<div class='card-start'></div>", unsafe_allow_html=True)
        st.markdown("<div class='section-kicker'><span class='section-num'>5</span><p class='eyebrow'>Context</p></div>", unsafe_allow_html=True)
        st.markdown("## Additional notes")
        st.text_area("Notes", key="w_notes", disabled=read_only, placeholder="Anything else the team should know…", label_visibility="collapsed", height=120)

    actor_name, manager_name, supervisor_name = actor_manager_supervisor()
    fill = form_fill_percent(
        actor_name=actor_name,
        project_id=st.session_state.project_id,
        form=form_for_status(),
        manager_name=manager_name,
        supervisor_name=supervisor_name,
    )
    fingerprint = form_fingerprint(form=form, actor_name=actor_name, manager_name=manager_name, supervisor_name=supervisor_name)
    if st.session_state.pending_baseline:
        st.session_state.baseline = fingerprint
        st.session_state.pending_baseline = False
    dirty = bool(st.session_state.baseline) and fingerprint != st.session_state.baseline and not read_only
    last_saved = st.session_state.last_saved
    last_saved_label = (
        f"Saved {format_when(last_saved['saved_at'])}" + (f" by {last_saved['saved_by_name']}" if last_saved.get("saved_by_name") else "")
        if last_saved
        else ""
    )
    block = save_block_reason(actor_name=actor_name, project_id=st.session_state.project_id, read_only=read_only)
    save_caption = block or ("Read-only history view" if read_only else "Unsaved changes" if dirty else "All changes saved" if last_saved else "Nothing saved yet")
    with st.container():
        st.markdown("<div class='save-dock-marker'></div>", unsafe_allow_html=True)
        dock_l, dock_r = st.columns([4, 1.1])
        with dock_l:
            st.markdown(
                f"<div class='save-caption'><strong>{html.escape(save_caption)}</strong>"
                f"<div class='progress-track'><div class='progress-fill' style='width:{fill}%'></div></div>"
                f"<span>{fill}% complete{' · ' + html.escape(last_saved_label) if last_saved_label else ''}</span></div>",
                unsafe_allow_html=True,
            )
        with dock_r:
            saving = bool(st.session_state.saving)
            if st.button(
                "Saving…" if saving else "Save",
                type="primary",
                disabled=bool(block) or saving,
                width="stretch",
                key="save_bottom",
                help="Saving…" if saving else (block or "Writes a new Snowflake snapshot"),
            ):
                run_save()
        if st.session_state.saving:
            complete_save()

    if st.session_state.show_save_success:
        save_success_dialog()
    elif st.session_state.show_admin_login:
        admin_login_dialog()
    elif st.session_state.show_new_project:
        new_project_dialog()
    elif st.session_state.show_history:
        history_dialog()
    elif st.session_state.show_brief:
        brief_dialog(
            format_project_brief(
                project_title=project_title,
                actor_name=actor_name,
                manager_name=manager_name,
                supervisor_name=supervisor_name,
                form=form_for_status(),
                last_saved_label=last_saved_label,
            )
        )


def main() -> None:
    inject_css()
    init_state()
    ensure_bootstrap()
    apply_pending_form_reset()
    apply_pending_project_select()
    st.session_state.pending_save = False
    toast = st.session_state.get("toast") or ""
    if toast and not st.session_state.get("show_save_success"):
        st.toast(toast)
        st.session_state.toast = ""
    if st.session_state.page == "admin" and st.session_state.admin_ok:
        render_admin()
    else:
        render_form()


if __name__ == "__main__":
    main()
else:
    main()
