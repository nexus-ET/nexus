from __future__ import annotations

from pydantic import BaseModel, Field


class MetaLeadsBackfillRequest(BaseModel):
    page_id: str | None = Field(
        default=None,
        description="Facebook Page ID. Defaults to META_PAGE_ID from environment.",
    )
    access_token: str | None = Field(
        default=None,
        description="Page Access Token with leads_retrieval. Defaults to META_GRAPH_ACCESS_TOKEN.",
    )
    since: str | None = Field(
        default=None,
        description="Optional start date filter (YYYY-MM-DD or Unix timestamp) for lead retrieval.",
    )
    until: str | None = Field(
        default=None,
        description="Optional end date filter (YYYY-MM-DD or Unix timestamp) for lead retrieval.",
    )
    request_delay_seconds: float = Field(
        default=1.0,
        ge=0.0,
        le=60.0,
        description="Pause between Graph API calls to reduce rate-limit risk.",
    )


class MetaLeadsBackfillResponse(BaseModel):
    forms_processed: int
    leads_seen: int
    leads_created: int
    leads_skipped: int
    errors: list[str]
