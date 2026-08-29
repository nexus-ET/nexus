from __future__ import annotations

from datetime import date, datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROFILE_NAME_MAX_LENGTH = 50
PROFILE_EMAIL_MAX_LENGTH = 50
PROFILE_ADDRESS_MAX_LENGTH = 50
PROFILE_CITY_STATE_MAX_LENGTH = 50
PROFILE_ZIPCODE_MAX_LENGTH = 7

GenderOption = Literal["MALE", "FEMALE"]
MaritalStatusOption = Literal["SINGLE", "MARRIED"]
StudentMasterSaveScope = Literal["profile", "academia", "full"]


class CandidateProfileLocationIn(BaseModel):
    address1: str | None = Field(default=None, max_length=PROFILE_ADDRESS_MAX_LENGTH)
    address2: str | None = Field(default=None, max_length=PROFILE_ADDRESS_MAX_LENGTH)
    address3: str | None = Field(default=None, max_length=PROFILE_ADDRESS_MAX_LENGTH)
    city: str | None = Field(default=None, max_length=PROFILE_CITY_STATE_MAX_LENGTH)
    state: str | None = Field(default=None, max_length=PROFILE_CITY_STATE_MAX_LENGTH)
    country_iso2: str | None = None
    zipcode: str | None = Field(default=None, max_length=PROFILE_ZIPCODE_MAX_LENGTH)


class CandidateProfileEducationIn(BaseModel):
    degree_code: str | None = None
    degree_other: str | None = None
    major: str | None = None
    university: str | None = None
    graduation_year: int | None = Field(default=None, ge=1950, le=2100)
    gpa_cgpa_code: str | None = None
    gpa_cgpa_other: str | None = None


class CandidateProfileStudyInterestIn(BaseModel):
    target_destination_iso2: str | None = None
    target_program_code: str | None = None
    target_course_code: str | None = None


class CandidateProfileAptitudeIn(BaseModel):
    english_test_scores: str | None = None
    gre_score: str | None = None
    gmat_score: str | None = None


class StudentMasterSaveRequest(BaseModel):
    save_scope: StudentMasterSaveScope = "profile"
    first_name: str | None = Field(default=None, max_length=PROFILE_NAME_MAX_LENGTH)
    middle_name: str | None = Field(default=None, max_length=PROFILE_NAME_MAX_LENGTH)
    last_name: str | None = Field(default=None, max_length=PROFILE_NAME_MAX_LENGTH)
    date_of_birth: date | None = None
    gender: GenderOption | None = None
    marital_status: MaritalStatusOption | None = None
    email: str | None = Field(default=None, max_length=PROFILE_EMAIL_MAX_LENGTH)
    phone_country_iso2: str | None = None
    phone_local: str | None = None
    phone_country_iso2_secondary: str | None = None
    phone_local_secondary: str | None = None
    location: CandidateProfileLocationIn = Field(default_factory=CandidateProfileLocationIn)
    education: CandidateProfileEducationIn = Field(default_factory=CandidateProfileEducationIn)
    study_interest: CandidateProfileStudyInterestIn = Field(default_factory=CandidateProfileStudyInterestIn)
    aptitude_scores: CandidateProfileAptitudeIn = Field(default_factory=CandidateProfileAptitudeIn)


class StudentMasterSaveResponse(BaseModel):
    booking_id: int
    lead_id: int | None = None
    students_master_id: int
    saved_at: datetime
    profile: dict

    model_config = ConfigDict(from_attributes=True)


class StudentMasterInvoiceHit(BaseModel):
    id: int
    lead_id: int | None = None
    full_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone_country_iso2: str | None = None
    phone_local: str | None = None
    phone_number: str | None = None
    address_street: str | None = None
    address1: str | None = None
    address2: str | None = None
    address3: str | None = None
    city: str | None = None
    state: str | None = None
    country_iso2: str | None = None
    zipcode: str | None = None
    target_destination_iso2: str | None = None
    assigned_advisor_id: int | None = None
    assigned_advisor_name: str | None = None
    updated_at: str | None = None


class StudentMasterInvoiceSearchResponse(BaseModel):
    items: list[StudentMasterInvoiceHit]
    total: int
