"""Pydantic schemas for Nexus Intel."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IntelGlossaryRead(BaseModel):
    id: UUID
    term_name: str
    slug: str
    category: str
    country_code: str
    lifecycle_stage: str
    short_definition: str
    full_explanation: str | None = None
    key_metrics: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    official_source_url: str | None = None
    is_student_facing: bool = False
    last_verified_at: datetime | None = None
    status: str = "ACTIVE"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class IntelInquiryTaxonomyNode(BaseModel):
    code: str
    name: str
    children: list["IntelInquiryTaxonomyNode"] = Field(default_factory=list)


class IntelInquiryFaqRead(BaseModel):
    id: UUID
    process_code: str
    process_name: str
    subprocess_code: str | None = None
    subprocess_name: str | None = None
    nested_process_code: str | None = None
    nested_process_name: str | None = None
    question: str
    answer: str
    sort_order: int = 0
    is_active: bool = True
    created_by: int | None = None
    updated_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class IntelInquiryFaqListResponse(BaseModel):
    items: list[IntelInquiryFaqRead]
    total: int


class IntelInquiryFaqCreate(BaseModel):
    path: str = Field(min_length=1, max_length=16)
    question: str = Field(min_length=5, max_length=5000)
    answer: str = Field(min_length=1, max_length=30000)
    sort_order: int = Field(default=0, ge=0, le=100000)

    @field_validator("path", "question", "answer")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value


class IntelInquiryFaqUpdate(BaseModel):
    path: str | None = Field(default=None, min_length=1, max_length=16)
    question: str | None = Field(default=None, min_length=5, max_length=5000)
    answer: str | None = Field(default=None, min_length=1, max_length=30000)
    sort_order: int | None = Field(default=None, ge=0, le=100000)

    @field_validator("path", "question", "answer")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value


IntelCategory = Literal["Admissions", "Visa", "Financial", "Work_Rights", "Legal"]
IntelLifecycleStage = Literal[
    "1_Discovery",
    "2_Prep",
    "3_Offer",
    "4_Finance",
    "5_Visa",
    "6_Onboarding",
]
IntelGlossaryStatus = Literal["ACTIVE", "ARCHIVED", "DRAFT"]


def _validate_optional_http_url(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Enter a valid URL starting with http:// or https://")
    return text


class IntelGlossaryCreate(BaseModel):
    term_name: str = Field(min_length=2, max_length=150)
    slug: str | None = Field(default=None, max_length=150)
    category: IntelCategory
    country_code: str = Field(min_length=2, max_length=10)
    lifecycle_stage: IntelLifecycleStage
    short_definition: str = Field(min_length=8, max_length=2000)
    full_explanation: str | None = Field(default=None, max_length=20000)
    key_metrics: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    official_source_url: str | None = Field(default=None, max_length=2000)
    is_student_facing: bool = False
    status: IntelGlossaryStatus = "ACTIVE"

    @field_validator("country_code")
    @classmethod
    def _upper_country(cls, value: str) -> str:
        return (value or "").strip().upper()

    @field_validator("slug")
    @classmethod
    def _normalize_slug(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        text = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")
        return text or None

    @field_validator("official_source_url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return _validate_optional_http_url(value)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value or []:
            tag = str(item).strip()
            if tag and tag not in cleaned:
                cleaned.append(tag)
        return cleaned[:20]


class IntelGlossaryUpdate(BaseModel):
    term_name: str | None = Field(default=None, min_length=2, max_length=150)
    slug: str | None = Field(default=None, max_length=150)
    category: IntelCategory | None = None
    country_code: str | None = Field(default=None, min_length=2, max_length=10)
    lifecycle_stage: IntelLifecycleStage | None = None
    short_definition: str | None = Field(default=None, min_length=8, max_length=2000)
    full_explanation: str | None = Field(default=None, max_length=20000)
    key_metrics: dict[str, Any] | None = None
    tags: list[str] | None = None
    official_source_url: str | None = Field(default=None, max_length=2000)
    is_student_facing: bool | None = None
    status: IntelGlossaryStatus | None = None

    @field_validator("country_code")
    @classmethod
    def _upper_country(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()

    @field_validator("slug")
    @classmethod
    def _normalize_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not str(value).strip():
            return None
        text = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")
        return text or None

    @field_validator("official_source_url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return _validate_optional_http_url(value)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned: list[str] = []
        for item in value:
            tag = str(item).strip()
            if tag and tag not in cleaned:
                cleaned.append(tag)
        return cleaned[:20]


class IntelGlossaryBulkDeleteRequest(BaseModel):
    term_ids: list[UUID] = Field(min_length=1)


class IntelGlossaryBulkDeleteResponse(BaseModel):
    deleted: int
    skipped: int
    ids: list[str] = Field(default_factory=list)


class IntelTooltipPayload(BaseModel):
    slug: str
    term_name: str
    short_definition: str
    last_verified_at: datetime | None = None
    official_source_url: str | None = None
    country_code: str
    category: str


class IntelGlossaryListResponse(BaseModel):
    items: list[IntelGlossaryRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class IntelTriviaRead(BaseModel):
    id: UUID
    question: str
    options: list[str]
    country_code: str | None = None
    active_date: date
    already_answered: bool = False
    selected_option_index: int | None = None
    is_correct: bool | None = None
    explanation: str | None = None
    streak: int = 0
    correct_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class IntelTriviaAnswerRequest(BaseModel):
    trivia_id: UUID
    selected_option_index: int = Field(ge=0, le=3)


class IntelTriviaAnswerResponse(BaseModel):
    is_correct: bool
    correct_option_index: int
    explanation: str
    streak: int
    correct_count: int


class IntelPreferencesRead(BaseModel):
    enable_daily_trivia: bool = True
    enable_contextual_tips: bool = True
    preferred_countries: list[str] = Field(default_factory=lambda: ["UK", "CA", "AU", "DE", "US"])
    trivia_streak: int = 0
    trivia_correct_count: int = 0


class IntelPreferencesUpdate(BaseModel):
    enable_daily_trivia: bool | None = None
    enable_contextual_tips: bool | None = None
    preferred_countries: list[str] | None = None


class IntelScraperConfigRead(BaseModel):
    id: UUID
    source_name: str
    target_url: str
    country_code: str
    scrape_interval_hours: int
    last_run_at: datetime | None = None
    status: str
    last_error: str | None = None
    last_content_hash: str | None = None
    last_fetched_at: datetime | None = None
    last_http_status: int | None = None
    linked_glossary_id: UUID | None = None
    linked_glossary_term: str | None = None

    model_config = ConfigDict(from_attributes=True)


class IntelScrapeRunResult(BaseModel):
    ran: int
    reviews_created: int
    unchanged: int = 0
    errors: int = 0
    skipped: str | int | None = None


class IntelScraperConfigUpdate(BaseModel):
    scrape_interval_hours: int = Field(ge=1, le=24 * 30)


class IntelScraperRunRequest(BaseModel):
    config_ids: list[UUID] | None = None


class IntelScrapeReviewRead(BaseModel):
    id: UUID
    scraper_config_id: UUID
    source_name: str | None = None
    glossary_id: UUID | None = None
    detected_at: datetime
    old_text: str | None = None
    new_text: str
    diff_summary: str | None = None
    status: str

    model_config = ConfigDict(from_attributes=True)


class IntelScrapeReviewBulkApproveRequest(BaseModel):
    review_ids: list[UUID] = Field(min_length=1)


class IntelScrapeReviewBulkApproveResponse(BaseModel):
    approved: int
    skipped: int
    items: list[IntelScrapeReviewRead]


class IntelAcademyModuleRead(BaseModel):
    id: UUID
    title: str
    slug: str
    summary: str
    country_code: str | None = None
    duration_minutes: int
    quiz: dict[str, Any]
    is_active: bool
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class ProofOfFundsRequest(BaseModel):
    country_code: Literal[
        "UK", "CA", "AU", "DE", "US", "JP", "FR", "AE", "NZ", "SG", "SE", "CH"
    ]
    tuition: float = Field(ge=0)
    living_costs: float = Field(ge=0)
    scholarships: float = Field(default=0, ge=0)


class ProofOfFundsResponse(BaseModel):
    country_code: str
    required_balance: float
    currency: str
    holding_days: int
    breakdown: dict[str, float]
    notes: list[str]


class RoiBenchmarkInputs(BaseModel):
    """Editable baseline inputs returned by the ROI benchmarks API (local currency)."""

    currency: str
    program_years: float = 2.0
    annual_tuition: float
    visa_fees: float = 0.0
    health_insurance_annual: float = 0.0
    books_supplies_annual: float = 800.0
    monthly_rent: float
    monthly_groceries: float
    monthly_transit: float
    monthly_other_living: float = 150.0
    scholarship_annual: float = 0.0
    part_time_earnings_annual: float = 0.0
    destination_starting_salary: float
    destination_salary_growth: float = 0.04
    destination_effective_tax_rate: float = 0.22
    home_counterfactual_salary: float
    home_salary_growth: float = 0.035
    home_effective_tax_rate: float = 0.15
    career_horizon_years: int = 10
    discount_rate: float = 0.05


class RoiBenchmarkResponse(BaseModel):
    country_code: str
    country_iso2: str
    metro_key: str | None = None
    location_label: str
    institution_id: int | None = None
    institution_name: str | None = None
    as_of: str
    disclaimer: str
    inputs: RoiBenchmarkInputs
    notes: list[str] = Field(default_factory=list)


class FxRateResponse(BaseModel):
    base: str
    quote: str
    rate: float
    as_of: str
    source: str = "frankfurter"
    notes: list[str] = Field(default_factory=list)


class CountryComparisonItem(BaseModel):
    country_code: str
    tuition_band: str
    psw_rights: str
    dependent_rules: str
    work_limits: str
    proof_of_funds_summary: str
    language_requirements: str = ""


class FutureInsightsEmployer(BaseModel):
    name: str
    website_url: str
    logo_url: str | None = None
    city_or_region: str | None = None
    sectors: list[str] = Field(default_factory=list)


class FutureInsightsJob(BaseModel):
    title: str
    employer_name: str
    location: str
    apply_url: str
    program_disciplines: list[str] = Field(default_factory=list)
    as_of: str


class FutureInsightsRoi(BaseModel):
    tuition_baseline: str
    health_fees_note: str
    median_starting_salary: str
    break_even_horizon: str
    ten_year_yield_note: str
    currency: str


class FutureInsightsImmigration(BaseModel):
    psw_rights: str
    work_limits: str
    dependent_rules: str
    pathway_notes: list[str] = Field(default_factory=list)
    language_requirements: str = ""
    proof_of_funds_summary: str = ""


class FutureInsightsCityLiving(BaseModel):
    shared_housing_monthly: str
    private_rent_monthly: str
    transit_index_note: str
    grocery_index_note: str
    climate_snapshot: str
    safety_snapshot: str


class FutureInsightsHabitatMetric(BaseModel):
    key: str
    label: str
    value: str
    score: float | None = None


class FutureInsightsHabitatCategory(BaseModel):
    key: str
    title: str
    summary: str
    metrics: list[FutureInsightsHabitatMetric] = Field(default_factory=list)


class FutureInsightsHabitat(BaseModel):
    """Grouped campus/city intelligence (livability, safety, jobs, amenities, etc.)."""

    location_label: str
    categories: list[FutureInsightsHabitatCategory] = Field(default_factory=list)


class FutureInsightsInstitutionContext(BaseModel):
    institution_id: int
    institution_name: str
    city_name: str | None = None
    state_name: str | None = None
    country_iso2: str | None = None
    metro_key: str | None = None
    location_label: str
    metro_matched: bool = False
    employers: list[FutureInsightsEmployer] = Field(default_factory=list)
    jobs: list[FutureInsightsJob] = Field(default_factory=list)
    city_living: FutureInsightsCityLiving | None = None
    habitat: FutureInsightsHabitat | None = None


class FutureInsightsDestinationPack(BaseModel):
    country_code: str
    country_iso2: str
    as_of: str
    disclaimer: str
    roi: FutureInsightsRoi
    employers: list[FutureInsightsEmployer] = Field(default_factory=list)
    jobs: list[FutureInsightsJob] = Field(default_factory=list)
    immigration: FutureInsightsImmigration
    city_living: FutureInsightsCityLiving
    habitat: FutureInsightsHabitat | None = None
    institutions: list[FutureInsightsInstitutionContext] = Field(default_factory=list)


class FutureInsightsResponse(BaseModel):
    destinations: list[FutureInsightsDestinationPack]
    unsupported_countries: list[str] = Field(default_factory=list)


SortField = Literal[
    "updated",
    "alpha",
    "term",
    "country",
    "category",
    "lifecycle",
    "definition",
    "source",
]
SortDir = Literal["asc", "desc"]


class IntelAiChatHistoryMessage(BaseModel):
    """Deprecated client-side history; prefer thread_id + server sliding window."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class IntelAiChatRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=4000)
    thread_id: str | None = Field(
        default=None,
        description="Optional conversation thread UUID. Created when omitted.",
    )
    # Kept for backward compatibility; server prefers DB history by thread_id.
    history: list[IntelAiChatHistoryMessage] = Field(default_factory=list, max_length=12)


class IntelAiSource(BaseModel):
    type: str
    title: str
    url: str | None = None
    id: str | None = None
    slug: str | None = None
    summary: str | None = None
    country_code: str | None = None
    category: str | None = None


class IntelAiChatResponse(BaseModel):
    id: str
    thread_id: str
    response_text: str
    sources: list[IntelAiSource] = Field(default_factory=list)
    retrieved_sources: list[IntelAiSource] = Field(default_factory=list)
    created_at: str | None = None


class IntelAiChatHistoryItem(BaseModel):
    id: str
    thread_id: str | None = None
    prompt: str
    response_text: str
    sources: list[IntelAiSource] = Field(default_factory=list)
    retrieved_sources: list[IntelAiSource] = Field(default_factory=list)
    created_at: str | None = None


class IntelAiChatHistoryResponse(BaseModel):
    thread_id: str | None = None
    items: list[IntelAiChatHistoryItem] = Field(default_factory=list)


class IntelAiThreadSummary(BaseModel):
    thread_id: str
    title: str
    started_at: str | None = None
    updated_at: str | None = None
    turn_count: int = 0


class IntelAiThreadGroup(BaseModel):
    key: Literal["today", "yesterday", "last_7_days", "older"]
    label: str
    threads: list[IntelAiThreadSummary] = Field(default_factory=list)


class IntelAiThreadsResponse(BaseModel):
    groups: list[IntelAiThreadGroup] = Field(default_factory=list)


class IntelAiThreadMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    sources: list[IntelAiSource] = Field(default_factory=list)
    retrieved_sources: list[IntelAiSource] = Field(default_factory=list)
    created_at: str | None = None


class IntelAiThreadDetailResponse(BaseModel):
    thread_id: str
    title: str | None = None
    messages: list[IntelAiThreadMessage] = Field(default_factory=list)
    updated_at: str | None = None
