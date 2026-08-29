"""Nexus Intel API routes."""

from __future__ import annotations

import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.db.database import get_db
from app.models.user import User
from app.schemas.nexus_intel import (
    CountryComparisonItem,
    FutureInsightsResponse,
    FxRateResponse,
    IntelAcademyModuleRead,
    IntelAiChatHistoryResponse,
    IntelAiChatRequest,
    IntelAiChatResponse,
    IntelAiSource,
    IntelAiThreadDetailResponse,
    IntelAiThreadsResponse,
    IntelGlossaryBulkDeleteRequest,
    IntelGlossaryBulkDeleteResponse,
    IntelGlossaryCreate,
    IntelGlossaryListResponse,
    IntelGlossaryRead,
    IntelGlossaryUpdate,
    IntelInquiryFaqCreate,
    IntelInquiryFaqListResponse,
    IntelInquiryFaqRead,
    IntelInquiryFaqUpdate,
    IntelInquiryTaxonomyNode,
    IntelPreferencesRead,
    IntelPreferencesUpdate,
    IntelScrapeReviewBulkApproveRequest,
    IntelScrapeReviewBulkApproveResponse,
    IntelScrapeReviewRead,
    IntelScrapeRunResult,
    IntelScraperConfigRead,
    IntelScraperConfigUpdate,
    IntelScraperRunRequest,
    IntelTooltipPayload,
    IntelTriviaAnswerRequest,
    IntelTriviaAnswerResponse,
    IntelTriviaRead,
    ProofOfFundsRequest,
    ProofOfFundsResponse,
    RoiBenchmarkResponse,
    SortDir,
    SortField,
)
from app.services import intel_ai_assistant as intel_ai
from app.services import nexus_intel as service

router = APIRouter(prefix="/intel", tags=["Nexus Intel"])


def _glossary_read(row) -> IntelGlossaryRead:
    data = service.glossary_to_dict(row)
    return IntelGlossaryRead(**data)


@router.get("/inquiry-hub/taxonomy", response_model=list[IntelInquiryTaxonomyNode])
def get_inquiry_taxonomy(
    _user: User = Depends(deps.get_current_active_user),
):
    return service.inquiry_taxonomy()


@router.get("/inquiry-hub/faqs", response_model=IntelInquiryFaqListResponse)
def list_inquiry_faqs(
    path: list[str] | None = Query(None),
    q: str | None = Query(None, max_length=200),
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_active_user),
):
    try:
        rows, total = service.list_inquiry_faqs(db, paths=path, q=q)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return IntelInquiryFaqListResponse(items=rows, total=total)


@router.post("/inquiry-hub/faqs", response_model=IntelInquiryFaqRead, status_code=201)
def create_inquiry_faq(
    body: IntelInquiryFaqCreate,
    db: Session = Depends(get_db),
    user: User = Depends(deps.get_current_active_user),
):
    try:
        return service.create_inquiry_faq(db, body.model_dump(), user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/inquiry-hub/faqs/{faq_id}", response_model=IntelInquiryFaqRead)
def update_inquiry_faq(
    faq_id: UUID,
    body: IntelInquiryFaqUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(deps.get_current_active_user),
):
    try:
        return service.update_inquiry_faq(
            db, faq_id, body.model_dump(exclude_unset=True), user.id
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/inquiry-hub/faqs/{faq_id}", status_code=204)
def delete_inquiry_faq(
    faq_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(deps.get_current_active_user),
):
    service.delete_inquiry_faq(db, faq_id, user.id)


@router.get("/terms", response_model=IntelGlossaryListResponse)
def list_terms(
    db: Session = Depends(get_db),
    q: str | None = Query(None),
    country_code: str | None = Query(None),
    lifecycle_stage: str | None = Query(None),
    category: str | None = Query(None),
    sort_by: SortField = Query("updated"),
    sort_dir: SortDir = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    _user: User = Depends(deps.get_current_user),
):
    rows, total = service.list_glossary_terms(
        db,
        q=q,
        country_code=country_code,
        lifecycle_stage=lifecycle_stage,
        category=category,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    total_pages = max(1, math.ceil(total / page_size)) if total else 1
    return IntelGlossaryListResponse(
        items=[_glossary_read(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.get("/terms/{slug}", response_model=IntelGlossaryRead)
def get_term(
    slug: str,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    row = service.get_glossary_by_slug(db, slug)
    if not row:
        raise HTTPException(status_code=404, detail="Term not found.")
    return _glossary_read(row)


@router.get("/terms/{slug}/tooltip", response_model=IntelTooltipPayload)
def get_term_tooltip(
    slug: str,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    row = service.get_glossary_by_slug(db, slug)
    if not row:
        raise HTTPException(status_code=404, detail="Term not found.")
    return IntelTooltipPayload(
        slug=row.slug,
        term_name=row.term_name,
        short_definition=row.short_definition,
        last_verified_at=row.last_verified_at,
        official_source_url=row.official_source_url,
        country_code=row.country_code,
        category=row.category,
    )


@router.get("/admin/terms", response_model=IntelGlossaryListResponse)
def admin_list_terms(
    db: Session = Depends(get_db),
    q: str | None = Query(None),
    country_code: str | None = Query(None),
    lifecycle_stage: str | None = Query(None),
    category: str | None = Query(None),
    status: str | None = Query("ALL"),
    sort_by: SortField = Query("updated"),
    sort_dir: SortDir = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    _user: User = Depends(deps.require_academia_admin),
):
    rows, total = service.list_glossary_terms(
        db,
        q=q,
        country_code=country_code,
        lifecycle_stage=lifecycle_stage,
        category=category,
        status=status,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    total_pages = max(1, math.ceil(total / page_size)) if total else 1
    return IntelGlossaryListResponse(
        items=[_glossary_read(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post("/admin/terms", response_model=IntelGlossaryRead, status_code=201)
def admin_create_term(
    body: IntelGlossaryCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_academia_admin),
):
    row = service.create_glossary_term(db, body.model_dump())
    return _glossary_read(row)


@router.post(
    "/admin/terms/bulk-delete",
    response_model=IntelGlossaryBulkDeleteResponse,
)
def admin_bulk_delete_terms(
    body: IntelGlossaryBulkDeleteRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_academia_admin),
):
    return service.delete_glossary_terms_bulk(db, body.term_ids)


@router.patch("/admin/terms/{term_id}", response_model=IntelGlossaryRead)
def admin_update_term(
    term_id: UUID,
    body: IntelGlossaryUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_academia_admin),
):
    row = service.update_glossary_term(
        db, term_id, body.model_dump(exclude_unset=True)
    )
    return _glossary_read(row)


@router.delete("/admin/terms/{term_id}")
def admin_delete_term(
    term_id: UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_academia_admin),
):
    return service.delete_glossary_term(db, term_id)


@router.get("/trivia/daily", response_model=IntelTriviaRead | None)
def get_daily_trivia(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    payload = service.get_daily_trivia(db, current_user.id)
    if not payload:
        return None
    return IntelTriviaRead(**payload)


@router.post("/trivia/answer", response_model=IntelTriviaAnswerResponse)
def submit_trivia_answer(
    body: IntelTriviaAnswerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    result = service.answer_trivia(
        db, current_user.id, body.trivia_id, body.selected_option_index
    )
    return IntelTriviaAnswerResponse(**result)


@router.get("/preferences", response_model=IntelPreferencesRead)
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    prefs = service.get_or_create_preferences(db, current_user.id)
    return service.preferences_to_read(prefs)


@router.patch("/preferences", response_model=IntelPreferencesRead)
def patch_preferences(
    body: IntelPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    return service.update_preferences(db, current_user.id, body)


@router.get("/academy", response_model=list[IntelAcademyModuleRead])
def list_academy(
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    return service.list_academy_modules(db)


@router.post("/workflows/proof-of-funds", response_model=ProofOfFundsResponse)
def proof_of_funds(
    body: ProofOfFundsRequest,
    _user: User = Depends(deps.get_current_user),
):
    return service.calculate_proof_of_funds(body)


@router.get("/workflows/compare", response_model=list[CountryComparisonItem])
def compare_countries(
    countries: str = Query(..., description="Comma-separated country codes, max 3"),
    _user: User = Depends(deps.get_current_user),
):
    codes = [part.strip() for part in countries.split(",") if part.strip()]
    return service.compare_countries(codes)


@router.get("/future-insights", response_model=FutureInsightsResponse)
def future_insights(
    countries: str = Query(
        ...,
        description="Comma-separated destination country codes (ISO2 or Intel codes, e.g. CA,GB,UK)",
    ),
    programs: str | None = Query(
        None,
        description="Optional comma-separated program/discipline codes to soft-filter job listings",
    ),
    institution_ids: str | None = Query(
        None,
        description="Optional comma-separated shortlisted institution IDs for metro-local employers/jobs",
    ),
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    from app.services import future_insights as future_insights_service

    codes = [part.strip() for part in countries.split(",") if part.strip()]
    program_codes = (
        [part.strip() for part in programs.split(",") if part.strip()] if programs else []
    )
    inst_ids: list[int] = []
    if institution_ids:
        for part in institution_ids.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                inst_ids.append(int(part))
            except ValueError:
                continue
    return future_insights_service.get_future_insights(
        codes,
        program_codes,
        institution_ids=inst_ids or None,
        db=db,
    )


@router.get("/roi-benchmarks", response_model=RoiBenchmarkResponse)
def roi_benchmarks(
    country: str = Query(..., description="Destination country ISO2 or Intel code (e.g. US, GB, UK)"),
    institution_id: int | None = Query(None, description="Optional shortlisted institution id"),
    metro_key: str | None = Query(None, description="Optional metro key override (e.g. los-angeles)"),
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    from app.services import roi_benchmarks as roi_benchmarks_service

    return roi_benchmarks_service.get_roi_benchmarks(
        country_code=country,
        metro_key=metro_key,
        institution_id=institution_id,
        db=db,
    )


@router.get("/fx-rate", response_model=FxRateResponse)
def fx_rate(
    base: str = Query(..., description="Source currency code, e.g. USD"),
    quote: str = Query("INR", description="Target currency code (default INR)"),
    as_of: str | None = Query(None, description="ISO date YYYY-MM-DD (defaults to today)"),
    _user: User = Depends(deps.get_current_user),
):
    from app.services import fx_rates as fx_rates_service

    return fx_rates_service.fetch_fx_rate(base=base, quote=quote, as_of=as_of)


@router.get("/admin/scraper/config", response_model=list[IntelScraperConfigRead])
def list_scraper_config(
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_academia_admin),
):
    return service.list_scraper_configs(db)


@router.patch("/admin/scraper/config/{config_id}", response_model=IntelScraperConfigRead)
def patch_scraper_config(
    config_id: UUID,
    body: IntelScraperConfigUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_academia_admin),
):
    return service.update_scraper_interval(db, config_id, body.scrape_interval_hours)


@router.post("/admin/scraper/run", response_model=IntelScrapeRunResult)
def trigger_scraper(
    db: Session = Depends(get_db),
    config_id: UUID | None = Query(None),
    body: IntelScraperRunRequest = IntelScraperRunRequest(),
    _user: User = Depends(deps.require_academia_admin),
):
    return service.run_scraper(db, config_id=config_id, config_ids=body.config_ids)


@router.get("/admin/scraper/reviews", response_model=list[IntelScrapeReviewRead])
def list_reviews(
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_academia_admin),
):
    rows = service.list_scrape_reviews(db)
    return [IntelScrapeReviewRead(**service.scrape_review_to_read(row)) for row in rows]


@router.post(
    "/admin/scraper/reviews/bulk-approve",
    response_model=IntelScrapeReviewBulkApproveResponse,
)
@router.post(
    "/admin/scraper/reviews/approve-bulk",
    response_model=IntelScrapeReviewBulkApproveResponse,
    include_in_schema=False,
)
def approve_reviews_bulk(
    body: IntelScrapeReviewBulkApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_academia_admin),
):
    result = service.approve_scrape_reviews_bulk(db, body.review_ids, current_user.id)
    return IntelScrapeReviewBulkApproveResponse(
        approved=result["approved"],
        skipped=result["skipped"],
        items=[IntelScrapeReviewRead(**item) for item in result["items"]],
    )


@router.post("/admin/scraper/reviews/{review_id}/approve", response_model=IntelScrapeReviewRead)
def approve_review(
    review_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_academia_admin),
):
    row = service.approve_scrape_review(db, review_id, current_user.id)
    return IntelScrapeReviewRead(**service.scrape_review_to_read(row))


def _ai_sources(items: list[dict]) -> list[IntelAiSource]:
    return [IntelAiSource(**{k: v for k, v in item.items() if k in IntelAiSource.model_fields}) for item in items]


@router.post("/ai/chat", response_model=IntelAiChatResponse)
async def intel_ai_chat(
    body: IntelAiChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    try:
        result = await intel_ai.run_intel_ai_chat(
            db,
            user_id=current_user.id,
            prompt=body.prompt,
            thread_id=body.thread_id,
            history=[m.model_dump() for m in body.history],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return IntelAiChatResponse(
        id=result["id"],
        thread_id=result["thread_id"],
        response_text=result["response_text"],
        sources=_ai_sources(result.get("sources") or []),
        retrieved_sources=_ai_sources(result.get("retrieved_sources") or []),
        created_at=result.get("created_at"),
    )


@router.get("/ai/history", response_model=IntelAiChatHistoryResponse)
def intel_ai_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
    limit: int = Query(30, ge=1, le=100),
    thread_id: str | None = Query(None, description="Optional thread UUID filter"),
):
    try:
        items = intel_ai.list_chat_history(
            db, user_id=current_user.id, limit=limit, thread_id=thread_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return IntelAiChatHistoryResponse(
        thread_id=thread_id,
        items=[
            {
                "id": item["id"],
                "thread_id": item.get("thread_id"),
                "prompt": item["prompt"],
                "response_text": item["response_text"],
                "sources": _ai_sources(item.get("sources") or []),
                "retrieved_sources": _ai_sources(item.get("retrieved_sources") or []),
                "created_at": item.get("created_at"),
            }
            for item in items
        ]
    )


@router.get("/ai/threads", response_model=IntelAiThreadsResponse)
def intel_ai_threads(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
    limit: int = Query(60, ge=1, le=120),
):
    groups = intel_ai.list_chat_threads(db, user_id=current_user.id, limit=limit)
    return IntelAiThreadsResponse(groups=groups)


@router.get("/ai/threads/{thread_id}", response_model=IntelAiThreadDetailResponse)
def intel_ai_thread_detail(
    thread_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
    limit: int = Query(100, ge=1, le=200),
):
    try:
        detail = intel_ai.get_chat_thread(
            db, user_id=current_user.id, thread_id=str(thread_id), limit=limit
        )
    except ValueError as exc:
        detail_msg = str(exc)
        status = 404 if "not found" in detail_msg.lower() else 400
        raise HTTPException(status_code=status, detail=detail_msg) from exc
    return IntelAiThreadDetailResponse(
        thread_id=detail["thread_id"],
        title=detail.get("title"),
        updated_at=detail.get("updated_at"),
        messages=[
            {
                "id": msg["id"],
                "role": msg["role"],
                "content": msg["content"],
                "sources": _ai_sources(msg.get("sources") or []),
                "retrieved_sources": _ai_sources(msg.get("retrieved_sources") or []),
                "created_at": msg.get("created_at"),
            }
            for msg in detail.get("messages") or []
        ],
    )
