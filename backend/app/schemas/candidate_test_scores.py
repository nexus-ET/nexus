from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TestName(str, Enum):
    IELTS = "IELTS"
    TOEFL = "TOEFL"
    SAT = "SAT"
    GRE = "GRE"
    GMAT = "GMAT"
    ACT = "ACT"
    LSAT_MCAT = "LSAT_MCAT"
    PTE = "PTE"
    DUOLINGO = "DUOLINGO"


class TestSectionConfig(BaseModel):
    section_name: str
    data_type: Literal["float", "integer"]
    max_length: int
    min_score: float
    max_score: float


class OverallScoreConfig(BaseModel):
    data_type: Literal["float", "integer"]
    max_length: int
    min_score: float
    max_score: float
    auto_method: Literal["sum", "average", "none"] = "none"


OVERALL_SCORE_CONFIG: dict[TestName, OverallScoreConfig] = {
    TestName.IELTS: OverallScoreConfig(
        data_type="float",
        max_length=3,
        min_score=0.0,
        max_score=9.0,
        auto_method="average",
    ),
    TestName.TOEFL: OverallScoreConfig(
        data_type="float",
        max_length=6,
        min_score=0.0,
        max_score=120.0,
        auto_method="sum",
    ),
    TestName.SAT: OverallScoreConfig(
        data_type="integer",
        max_length=4,
        min_score=400,
        max_score=1600,
        auto_method="sum",
    ),
    TestName.GRE: OverallScoreConfig(
        data_type="integer",
        max_length=3,
        min_score=260,
        max_score=340,
        auto_method="sum",
    ),
    TestName.GMAT: OverallScoreConfig(
        data_type="integer",
        max_length=3,
        min_score=205,
        max_score=805,
        auto_method="none",
    ),
    TestName.ACT: OverallScoreConfig(
        data_type="integer",
        max_length=2,
        min_score=1,
        max_score=36,
        auto_method="average",
    ),
    TestName.LSAT_MCAT: OverallScoreConfig(
        data_type="integer",
        max_length=3,
        min_score=120,
        max_score=528,
        auto_method="none",
    ),
    TestName.PTE: OverallScoreConfig(
        data_type="integer",
        max_length=2,
        min_score=10,
        max_score=90,
        auto_method="average",
    ),
    TestName.DUOLINGO: OverallScoreConfig(
        data_type="integer",
        max_length=3,
        min_score=10,
        max_score=160,
        auto_method="none",
    ),
}


TEST_SECTION_CONFIG: dict[TestName, list[TestSectionConfig]] = {
    TestName.IELTS: [
        TestSectionConfig(
            section_name="Reading",
            data_type="float",
            max_length=3,
            min_score=0.0,
            max_score=9.0,
        ),
        TestSectionConfig(
            section_name="Writing",
            data_type="float",
            max_length=3,
            min_score=0.0,
            max_score=9.0,
        ),
        TestSectionConfig(
            section_name="Listening",
            data_type="float",
            max_length=3,
            min_score=0.0,
            max_score=9.0,
        ),
        TestSectionConfig(
            section_name="Speaking",
            data_type="float",
            max_length=3,
            min_score=0.0,
            max_score=9.0,
        ),
    ],
    TestName.TOEFL: [
        TestSectionConfig(
            section_name="Reading",
            data_type="float",
            max_length=4,
            min_score=0.0,
            max_score=30.0,
        ),
        TestSectionConfig(
            section_name="Listening",
            data_type="float",
            max_length=4,
            min_score=0.0,
            max_score=30.0,
        ),
        TestSectionConfig(
            section_name="Speaking",
            data_type="float",
            max_length=4,
            min_score=0.0,
            max_score=30.0,
        ),
        TestSectionConfig(
            section_name="Writing",
            data_type="float",
            max_length=4,
            min_score=0.0,
            max_score=30.0,
        ),
    ],
    TestName.SAT: [
        TestSectionConfig(
            section_name="Math",
            data_type="integer",
            max_length=3,
            min_score=200,
            max_score=800,
        ),
        TestSectionConfig(
            section_name="Reading",
            data_type="integer",
            max_length=3,
            min_score=200,
            max_score=800,
        ),
    ],
    TestName.GRE: [
        TestSectionConfig(
            section_name="Quantitative",
            data_type="integer",
            max_length=3,
            min_score=130,
            max_score=170,
        ),
        TestSectionConfig(
            section_name="Verbal",
            data_type="integer",
            max_length=3,
            min_score=130,
            max_score=170,
        ),
    ],
    TestName.GMAT: [
        TestSectionConfig(
            section_name="Quantitative",
            data_type="integer",
            max_length=2,
            min_score=60,
            max_score=90,
        ),
        TestSectionConfig(
            section_name="Verbal",
            data_type="integer",
            max_length=2,
            min_score=60,
            max_score=90,
        ),
    ],
    TestName.ACT: [
        TestSectionConfig(
            section_name="English",
            data_type="integer",
            max_length=2,
            min_score=1,
            max_score=36,
        ),
        TestSectionConfig(
            section_name="Math",
            data_type="integer",
            max_length=2,
            min_score=1,
            max_score=36,
        ),
        TestSectionConfig(
            section_name="Reading",
            data_type="integer",
            max_length=2,
            min_score=1,
            max_score=36,
        ),
        TestSectionConfig(
            section_name="Science",
            data_type="integer",
            max_length=2,
            min_score=1,
            max_score=36,
        ),
    ],
    TestName.LSAT_MCAT: [
        TestSectionConfig(
            section_name="Overall",
            data_type="integer",
            max_length=3,
            min_score=120,
            max_score=528,
        ),
    ],
    TestName.PTE: [
        TestSectionConfig(
            section_name="Speaking",
            data_type="integer",
            max_length=2,
            min_score=10,
            max_score=90,
        ),
        TestSectionConfig(
            section_name="Writing",
            data_type="integer",
            max_length=2,
            min_score=10,
            max_score=90,
        ),
        TestSectionConfig(
            section_name="Reading",
            data_type="integer",
            max_length=2,
            min_score=10,
            max_score=90,
        ),
        TestSectionConfig(
            section_name="Listening",
            data_type="integer",
            max_length=2,
            min_score=10,
            max_score=90,
        ),
    ],
    TestName.DUOLINGO: [
        TestSectionConfig(
            section_name="Overall",
            data_type="integer",
            max_length=3,
            min_score=10,
            max_score=160,
        ),
    ],
}


class CandidateTestScoreSectionInput(BaseModel):
    section_name: str = Field(..., min_length=1, max_length=50)
    score: Decimal


class CandidateTestScoreSaveRequest(BaseModel):
    test_name: TestName
    test_date: date | None = None
    score_report_url: str | None = Field(default=None, max_length=500)
    overall_score: Decimal | None = None
    sections: list[CandidateTestScoreSectionInput] = Field(..., min_length=1)

    @field_validator("score_report_url")
    @classmethod
    def normalize_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class CandidateTestScoreOut(BaseModel):
    id: int
    lead_id: int | None
    booking_id: int | None
    test_name: TestName
    test_date: date | None
    overall_score: Decimal | None
    section_name: str
    score: Decimal
    score_report_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CandidateTestScoresResponse(BaseModel):
    booking_id: int
    lead_id: int | None
    scores: list[CandidateTestScoreOut]


class CandidateTestScoreAttemptDeleteRequest(BaseModel):
    score_ids: list[int] = Field(..., min_length=1)


class CandidateTestScoreAttemptReplaceRequest(CandidateTestScoreSaveRequest):
    score_ids: list[int] = Field(..., min_length=1)
