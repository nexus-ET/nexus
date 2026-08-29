"""Invoice PDF upload, signed download, and student email API."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.core.rate_limit import STRICT_RATE_LIMIT, limiter
from app.db.database import get_db
from app.models.user import User
from app.services.audit_service import log_action
from app.services.business_profile_service import (
    DEFAULT_BUSINESS_ID,
    get_business_profile,
    resolve_business_id_for_user,
)
from app.services.invoice_email_service import send_student_invoice_email
from app.services.invoice_storage import (
    build_invoice_download_url,
    fetch_invoice_pdf,
    upload_issued_invoice_pdf,
    verify_invoice_download_token,
)

router = APIRouter(prefix="/invoices", tags=["Invoices"])


class InvoicePdfUploadResponse(BaseModel):
    storage_key: str
    financial_year: str
    filename: str
    folder_created: bool = False
    bytes: int = Field(ge=0)
    download_url: str = ""
    email_status: str = "skipped"  # sent | skipped | failed


class InvoiceDownloadLinkRequest(BaseModel):
    storage_key: str = Field(..., min_length=8, max_length=500)


class InvoiceDownloadLinkResponse(BaseModel):
    storage_key: str
    filename: str
    download_url: str


@router.post("/upload-pdf", response_model=InvoicePdfUploadResponse)
@router.post("/upload-pdf/", response_model=InvoicePdfUploadResponse)
@limiter.limit(STRICT_RATE_LIMIT)
@log_action("upload_invoice_pdf", "invoice")
async def upload_invoice_pdf(
    request: Request,
    file: UploadFile = File(...),
    invoice_date: str | None = Form(default=None),
    student_email: str | None = Form(default=None),
    student_name: str | None = Form(default=None),
    package_name: str | None = Form(default=None),
    account_manager_name: str | None = Form(default=None),
    company_name: str | None = Form(default=None),
    send_email: str = Form(default="true"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_page_access("/invoices")),
):
    content = await file.read()
    result = upload_issued_invoice_pdf(
        filename=file.filename or "invoice.pdf",
        content=content,
        invoice_date=invoice_date,
    )
    storage_key = str(result["storage_key"])
    filename = str(result["filename"])
    download_url = build_invoice_download_url(
        storage_key,
        request_base_url=str(request.base_url).rstrip("/"),
        filename=filename,
    )

    email_status = "skipped"
    should_email = str(send_email or "true").strip().lower() in {"1", "true", "yes", "on"}
    if should_email:
        resolved_company = (company_name or "").strip()
        if not resolved_company:
            try:
                business_id = resolve_business_id_for_user(current_user)
            except Exception:
                business_id = DEFAULT_BUSINESS_ID
            profile = get_business_profile(db, business_id)
            resolved_company = (profile.get("business_name") or "").strip() or "NEXUS"

        email_status = await asyncio.to_thread(
            send_student_invoice_email,
            student_email=student_email or "",
            student_name=student_name or "",
            package_name=package_name or "",
            download_url=download_url,
            account_manager_name=account_manager_name or "",
            company_name=resolved_company,
            pdf_bytes=content,
            pdf_filename=filename,
        )

    return InvoicePdfUploadResponse(
        storage_key=storage_key,
        financial_year=str(result["financial_year"]),
        filename=filename,
        folder_created=bool(result.get("folder_created")),
        bytes=int(result.get("bytes") or 0),
        download_url=download_url,
        email_status=email_status,
    )


@router.post("/download-link", response_model=InvoiceDownloadLinkResponse)
@router.post("/download-link/", response_model=InvoiceDownloadLinkResponse)
@limiter.limit(STRICT_RATE_LIMIT)
@log_action("invoice_download_link", "invoice")
async def create_invoice_download_link(
    request: Request,
    payload: InvoiceDownloadLinkRequest,
    current_user: User = Depends(deps.require_page_access("/invoices")),
):
    """Return a fresh Cloudflare (or signed) URL for an uploaded invoice PDF."""
    _ = current_user
    storage_key = payload.storage_key.strip()
    filename = storage_key.rsplit("/", 1)[-1] or "invoice.pdf"
    download_url = build_invoice_download_url(
        storage_key,
        request_base_url=str(request.base_url).rstrip("/"),
        filename=filename,
    )
    return InvoiceDownloadLinkResponse(
        storage_key=storage_key,
        filename=filename,
        download_url=download_url,
    )


@router.get("/download")
@router.get("/download/")
def download_invoice_pdf_query(token: str = Query(..., min_length=16)):
    """Unauthenticated student download via ``?token=`` (preferred for email links)."""
    return _invoice_pdf_response(token)


@router.get("/download/{token:path}")
def download_invoice_pdf_path(token: str):
    """Legacy path-token download (older emails)."""
    return _invoice_pdf_response(token)


def _invoice_pdf_response(token: str) -> Response:
    storage_key = verify_invoice_download_token(token)
    body, content_type = fetch_invoice_pdf(storage_key)
    filename = storage_key.rsplit("/", 1)[-1] or "invoice.pdf"
    return Response(
        content=body,
        media_type=content_type or "application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=0, no-cache",
        },
    )
