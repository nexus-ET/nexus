from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_academia_admin
from app.db.database import get_db
from app.models.user import User
from app.schemas.document_requirement import (
    DocumentChecklistCreate,
    DocumentChecklistLevelsResponse,
    DocumentChecklistScopeResponse,
    DocumentRequirementCreate,
    DocumentRequirementListResponse,
    DocumentRequirementRead,
    DocumentRequirementUpdate,
    DocumentTemplateDownloadResponse,
    normalize_program_level_value,
)
from app.services import document_requirement_service as service
from app.services.business_profile_service import (
    get_business_pdf_branding,
    get_business_profile,
    resolve_business_id_for_user,
)
from app.services.document_checklist_pdf import build_document_checklist_pdf
from app.services.document_checklist_storage import upload_document_checklist
from app.services.document_template_storage import (
    ensure_template_media_key,
    fetch_template_bytes,
    normalize_template_key,
    resolve_download_url,
    upload_document_template,
)

router = APIRouter(prefix="/document-requirements", tags=["Document Requirements"])


@router.get("", response_model=DocumentRequirementListResponse)
@router.get("/", response_model=DocumentRequirementListResponse)
def list_requirements(
    program_level: str | None = Query(None),
    country_id: list[int] | None = Query(None),
    is_global: bool | None = Query(None),
    q: str | None = Query(None, max_length=150),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    level = None
    if program_level:
        try:
            level = normalize_program_level_value(program_level)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    rows, total = service.list_document_requirements(
        db,
        program_level=level,
        country_ids=country_id or None,
        is_global=is_global,
        q=q,
        page=page,
        page_size=page_size,
    )
    return DocumentRequirementListResponse(
        items=[
            DocumentRequirementRead.model_validate(service.serialize_requirement(r))
            for r in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=service.total_pages(total, page_size),
    )


@router.post("", response_model=DocumentRequirementRead, status_code=201)
@router.post("/", response_model=DocumentRequirementRead, status_code=201)
def create_requirement(
    payload: DocumentRequirementCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    row = service.create_document_requirement(db, payload)
    return DocumentRequirementRead.model_validate(service.serialize_requirement(row))


@router.get("/checklist-scope", response_model=DocumentChecklistScopeResponse)
def get_checklist_scope(
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    """Whether Country-Specific is selectable and which countries have mappings."""
    payload = service.checklist_scope_options(db)
    return DocumentChecklistScopeResponse.model_validate(payload)


@router.get("/checklist-levels", response_model=DocumentChecklistLevelsResponse)
def list_checklist_levels(
    scope: str = Query("global"),
    country_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    """Levels with documents for the checklist scope (for radio grey-out).

    Query params scope/country_id do not affect Add/Edit level pickers.
    """
    try:
        normalized_scope = DocumentChecklistCreate.normalize_checklist_scope(scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if normalized_scope == "global" and country_id is not None:
        raise HTTPException(
            status_code=400,
            detail="country_id must not be provided when scope is global",
        )
    if normalized_scope == "country_specific" and country_id is None:
        return DocumentChecklistLevelsResponse(program_levels=[])

    return DocumentChecklistLevelsResponse(
        program_levels=service.list_catalog_levels_with_requirements(
            db,
            scope=normalized_scope,
            country_id=country_id,
        )
    )


@router.post("/checklists")
def create_document_checklist(
    payload: DocumentChecklistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_academia_admin),
):
    """Generate a Document Checklist PDF, store it (R2 or local), and return the bytes."""
    if payload.scope == "global" and payload.country_id is not None:
        raise HTTPException(
            status_code=400,
            detail="country_id must not be provided when scope is global",
        )
    if payload.scope == "country_specific" and payload.country_id is None:
        raise HTTPException(
            status_code=400,
            detail="country_id is required when scope is country_specific",
        )

    business_id = resolve_business_id_for_user(current_user)
    profile = get_business_profile(db, business_id)
    short_name = (profile.get("business_short_name") or "").strip()
    if not short_name:
        raise HTTPException(
            status_code=400,
            detail=(
                "Business short name is required to create a document checklist. "
                "Set Business short name in Settings before creating a checklist."
            ),
        )

    catalog_level = service.resolve_catalog_level(db, payload.program_level)
    level_name = catalog_level.name
    country_name: str | None = None
    country_id = payload.country_id
    if payload.scope == "country_specific":
        countries = service.resolve_countries(db, [int(country_id)])
        country_name = countries[0].name
        if not service.has_country_mapped_requirement_for_level(
            db,
            program_level=level_name,
            country_id=int(country_id),
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No country-mapped document requirements for level '{level_name}' "
                    f"and country '{country_name}'. "
                    "A country checklist requires at least one requirement linked to that country."
                ),
            )

    rows = service.list_requirements_for_checklist(
        db,
        program_level=level_name,
        scope=payload.scope,
        country_id=country_id,
    )
    if not rows:
        if payload.scope == "global":
            detail = (
                f"No global document requirements are assigned to level '{level_name}'. "
                "Choose a level that has at least one global document."
            )
        else:
            detail = (
                f"No document requirements apply to level '{level_name}' "
                f"for country '{country_name}'. "
                "Choose a level that has documents for this country."
            )
        raise HTTPException(status_code=400, detail=detail)

    branding = get_business_pdf_branding(db, business_id)
    generated_at = datetime.now()
    pdf_bytes = build_document_checklist_pdf(
        level_name=level_name,
        rows=[
            {
                "document_name": row.document_name,
                "description": row.description,
                "accepted_format": row.accepted_format,
            }
            for row in rows
        ],
        generated_at=generated_at,
        business_name=branding.get("business_name"),
        logo_path=branding.get("logo_path"),
        country_name=country_name,
    )
    uploaded = upload_document_checklist(
        level_name=level_name,
        business_short_name=short_name,
        content=pdf_bytes,
        country_name=country_name,
    )
    filename = str(uploaded["filename"])

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, max-age=0, no-cache",
            "X-Checklist-Storage-Key": str(uploaded["storage_key"]),
            "X-Checklist-Filename": filename,
        },
    )


@router.get("/media/{object_key:path}")
def stream_template_media(
    object_key: str,
    _: User = Depends(get_current_active_user),
):
    """Authenticated media for templates and checklist PDFs (CDN/presign fallback).

    Any signed-in user may open links recorded on counselor notes; mutating
    admin routes remain academia-admin only.
    """
    from app.services.document_checklist_storage import (
        checklist_key_prefix,
        fetch_checklist_bytes,
        normalize_checklist_key,
    )

    raw = (object_key or "").strip().lstrip("/")
    checklist_prefix = f"{checklist_key_prefix()}/"
    if raw.startswith(checklist_prefix):
        key = normalize_checklist_key(raw)
        body, content_type = fetch_checklist_bytes(key)
    else:
        key = normalize_template_key(ensure_template_media_key(raw))
        body, content_type = fetch_template_bytes(key)
    filename = key.rsplit("/", 1)[-1]
    return Response(
        content=body,
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=0, no-cache",
        },
    )


@router.get("/{requirement_id}", response_model=DocumentRequirementRead)
def get_requirement(
    requirement_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    row = service.get_document_requirement(db, requirement_id)
    return DocumentRequirementRead.model_validate(service.serialize_requirement(row))


@router.put("/{requirement_id}", response_model=DocumentRequirementRead)
def update_requirement(
    requirement_id: int,
    payload: DocumentRequirementUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    row = service.update_document_requirement(db, requirement_id, payload)
    return DocumentRequirementRead.model_validate(service.serialize_requirement(row))


@router.delete("/{requirement_id}", status_code=204)
def delete_requirement(
    requirement_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    service.delete_document_requirement(db, requirement_id)
    return Response(status_code=204)


@router.post("/{requirement_id}/template", response_model=DocumentRequirementRead)
async def upload_template(
    requirement_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_academia_admin),
):
    content = await file.read()
    uploaded = upload_document_template(
        filename=file.filename or "template",
        content=content,
        content_type=file.content_type,
    )
    row = service.attach_template(
        db,
        requirement_id=requirement_id,
        template_name=str(uploaded["template_name"]),
        file_url=str(uploaded["file_url"]),
        file_size=int(uploaded["file_size"]),
        uploaded_by=current_user.id,
    )
    return DocumentRequirementRead.model_validate(service.serialize_requirement(row))


@router.get(
    "/{requirement_id}/template",
    response_model=DocumentTemplateDownloadResponse,
)
def download_template(
    requirement_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    row = service.get_document_requirement(db, requirement_id)
    if not row.template:
        raise HTTPException(status_code=404, detail="No template uploaded for this requirement.")
    template = row.template
    return DocumentTemplateDownloadResponse(
        template_id=template.id,
        template_name=template.template_name,
        file_url=template.file_url,
        download_url=resolve_download_url(
            template.file_url,
            filename=template.template_name,
        ),
        file_size=template.file_size,
    )
