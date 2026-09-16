from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class NamedItem(BaseModel):
    id: str
    display_name: Optional[str] = None
    name: Optional[str] = None
    is_active: bool = True
    is_admin: bool = False
    created_at: Optional[datetime] = None


class CreateNamedItem(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    is_admin: bool = False


class UpdateNamedItem(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=500)
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


class SnapshotCreate(BaseModel):
    saved_by_user_id: Optional[str] = None
    saved_by_name: str = Field(min_length=1, max_length=255)
    project_name: Optional[str] = None
    client_name: Optional[str] = None
    location_city_county: Optional[str] = None
    location_state: Optional[str] = None
    field_start_date: Optional[date] = None
    project_manager_name: Optional[str] = None
    field_supervisor_name: Optional[str] = None
    od_intercept: Optional[bool] = None
    questionnaire_filename: Optional[str] = None
    questionnaire_path: Optional[str] = None
    sampling_plan_filename: Optional[str] = None
    sampling_plan_path: Optional[str] = None
    callback_languages: list[str] = Field(default_factory=list)
    od_translation_languages: list[str] = Field(default_factory=list)
    non_destination_place_type: Optional[bool] = None
    extra_trips_survey: Optional[bool] = None
    companion_survey: Optional[bool] = None
    tour_survey: Optional[bool] = None
    od_intercept_weekend: Optional[bool] = None
    questionnaire_weekend_filename: Optional[str] = None
    questionnaire_weekend_path: Optional[str] = None
    sampling_plan_weekend_filename: Optional[str] = None
    sampling_plan_weekend_path: Optional[str] = None
    callback_languages_weekend: list[str] = Field(default_factory=list)
    od_translation_languages_weekend: list[str] = Field(default_factory=list)
    non_destination_place_type_weekend: Optional[bool] = None
    extra_trips_survey_weekend: Optional[bool] = None
    companion_survey_weekend: Optional[bool] = None
    tour_survey_weekend: Optional[bool] = None
    sas_survey: Optional[bool] = None
    sas_translation_languages: list[str] = Field(default_factory=list)
    additional_notes: Optional[str] = None


class SnapshotOut(SnapshotCreate):
    id: str
    project_id: str
    saved_at: Optional[datetime] = None


class SnapshotSummary(BaseModel):
    id: str
    project_id: str
    saved_at: Optional[datetime] = None
    saved_by_name: str
    project_name: Optional[str] = None
