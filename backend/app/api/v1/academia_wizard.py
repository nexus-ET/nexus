from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import require_academia_admin
from app.db.database import get_db
from app.models.academia_institution import Institution
from app.models.user import User
from app.schemas.academia_wizard import (
    AcademiaAuditLogRead,
    InstitutionPictureRead,
    WizardDraftCreate,
    WizardDraftRead,
    WizardDraftUpdate,
    WizardStepSaveRequest,
)
from app.services import academia_audit_service as audit_service
from app.services import institution_wizard_service as wizard_service
from app.services.institution_asset_storage import (
    MAX_ASSET_BYTES,
    delete_institution_asset,
    fetch_r2_object,
    list_institution_assets,
    upload_institution_asset,
)

router = APIRouter()


@router.get("/academia/media/{object_key:path}")
def get_academia_media(object_key: str):
    """Public-read proxy for institution assets stored in R2 or local uploads."""
    body, content_type = fetch_r2_object(object_key)
    return Response(
        content=body,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": "inline",
        },
    )


@router.get("/academia/institutions/{institution_id}/pictures/assets")
def list_institution_picture_assets(
    institution_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    institution = db.query(Institution).filter(Institution.id == institution_id).first()
    if not institution:
        raise HTTPException(status_code=404, detail="Institution not found.")
    return list_institution_assets(institution)


@router.post("/academia/institutions/{institution_id}/pictures/upload")
async def upload_institution_pictures(
    institution_id: int,
    picture_type: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    institution = db.query(Institution).filter(Institution.id == institution_id).first()
    if not institution:
        raise HTTPException(status_code=404, detail="Institution not found.")
    if not files or len(files) > 20:
        raise HTTPException(status_code=400, detail="Select between 1 and 20 images.")

    uploaded: list[dict[str, object]] = []
    for upload in files:
        original_name = Path(upload.filename or "").name
        if not original_name:
            raise HTTPException(status_code=400, detail="Each file must have a filename.")
        content_type = (upload.content_type or "").lower()
        content = await upload.read(MAX_ASSET_BYTES + 1)
        uploaded.append(
            upload_institution_asset(
                institution=institution,
                asset_type=picture_type,
                filename=original_name,
                content=content,
                content_type=content_type,
            )
        )

    return uploaded


@router.delete("/academia/institutions/{institution_id}/pictures")
def delete_institution_picture_asset(
    institution_id: int,
    storage_key: str | None = None,
    url: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    """Delete one gallery/logo/banner object from Cloudflare R2 (or local uploads)."""
    institution = db.query(Institution).filter(Institution.id == institution_id).first()
    if not institution:
        raise HTTPException(status_code=404, detail="Institution not found.")
    if not storage_key and not url:
        raise HTTPException(
            status_code=400,
            detail="Provide a storage_key or url query parameter to delete an image.",
        )
    result = delete_institution_asset(
        institution=institution,
        object_key=storage_key,
        url=url,
    )
    wizard_service.remove_institution_picture_references(
        db,
        institution_id,
        {str(result["storage_key"])},
    )
    return result


@router.post("/academia/institutions/{institution_id}/pictures/delete")
def delete_institution_picture_asset_post(
    institution_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    """JSON body variant for gallery deletes (more reliable through some proxies)."""
    institution = db.query(Institution).filter(Institution.id == institution_id).first()
    if not institution:
        raise HTTPException(status_code=404, detail="Institution not found.")
    storage_key = payload.get("storage_key") if isinstance(payload, dict) else None
    url = payload.get("url") if isinstance(payload, dict) else None
    if not storage_key and not url:
        raise HTTPException(status_code=400, detail="Provide storage_key or url.")
    result = delete_institution_asset(
        institution=institution,
        object_key=str(storage_key) if storage_key else None,
        url=str(url) if url else None,
    )
    wizard_service.remove_institution_picture_references(
        db,
        institution_id,
        {str(result["storage_key"])},
    )
    return result


@router.post("/academia/institutions/{institution_id}/pictures/delete-bulk")
def delete_institution_picture_assets_bulk(
    institution_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    """Delete multiple gallery objects and remove their persisted references."""
    institution = db.query(Institution).filter(Institution.id == institution_id).first()
    if not institution:
        raise HTTPException(status_code=404, detail="Institution not found.")
    urls = payload.get("urls") if isinstance(payload, dict) else None
    if not isinstance(urls, list) or not urls:
        raise HTTPException(status_code=400, detail="Provide a non-empty urls list.")
    if len(urls) > 100:
        raise HTTPException(status_code=400, detail="Delete no more than 100 images at once.")

    deleted_keys: set[str] = set()
    for value in urls:
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(status_code=400, detail="Every image URL must be a string.")
        result = delete_institution_asset(institution=institution, url=value)
        deleted_keys.add(str(result["storage_key"]))

    wizard_service.remove_institution_picture_references(
        db,
        institution_id,
        deleted_keys,
    )
    return {"ok": True, "deleted": len(deleted_keys)}


def _draft_read(draft) -> WizardDraftRead:
    return WizardDraftRead.model_validate(wizard_service._draft_to_read(draft))


@router.get("/academia/wizard/drafts", response_model=list[WizardDraftRead])
def list_wizard_drafts(
    db: Session = Depends(get_db),
    user: User = Depends(require_academia_admin),
):
    return [_draft_read(row) for row in wizard_service.list_drafts_admin(db, user_id=user.id)]


@router.post("/academia/wizard/drafts", response_model=WizardDraftRead)
def create_wizard_draft(
    payload: WizardDraftCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_academia_admin),
):
    draft = wizard_service.create_draft_admin(
        db,
        user_id=user.id,
        title=payload.title or "Untitled Institution",
    )
    return _draft_read(draft)


@router.post(
    "/academia/wizard/drafts/from-institution/{institution_id}",
    response_model=WizardDraftRead,
)
def create_wizard_draft_from_institution(
    institution_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_academia_admin),
):
    draft = wizard_service.create_draft_from_institution_admin(
        db,
        institution_id,
        user_id=user.id,
    )
    return _draft_read(draft)


@router.get("/academia/wizard/drafts/{draft_id}", response_model=WizardDraftRead)
def get_wizard_draft(
    draft_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_academia_admin),
):
    return _draft_read(wizard_service.get_draft_admin(db, draft_id, user_id=user.id))


@router.put("/academia/wizard/drafts/{draft_id}", response_model=WizardDraftRead)
def update_wizard_draft(
    draft_id: int,
    payload: WizardDraftUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_academia_admin),
):
    data = payload.model_dump(exclude_unset=True)
    payload_data = data.pop("payload", None)
    if payload_data is not None:
        data["payload"] = payload_data.model_dump() if hasattr(payload_data, "model_dump") else payload_data
    draft = wizard_service.update_draft_admin(db, draft_id, user_id=user.id, **data)
    return _draft_read(draft)


@router.post("/academia/wizard/drafts/{draft_id}/steps", response_model=WizardDraftRead)
def save_wizard_step(
    draft_id: int,
    payload: WizardStepSaveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_academia_admin),
):
    draft = wizard_service.save_wizard_step(db, draft_id, user_id=user.id, request=payload)
    return _draft_read(draft)


@router.post("/academia/wizard/drafts/{draft_id}/publish", response_model=WizardDraftRead)
def publish_wizard_draft(
    draft_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_academia_admin),
):
    draft = wizard_service.publish_draft_admin(db, draft_id, user_id=user.id)
    return _draft_read(draft)


@router.delete("/academia/wizard/drafts/{draft_id}")
def delete_wizard_draft(
    draft_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_academia_admin),
):
    wizard_service.delete_draft_admin(db, draft_id, user_id=user.id)
    return {"ok": True}


@router.get("/academia/institutions/{institution_id}/history", response_model=list[AcademiaAuditLogRead])
def list_institution_history(
    institution_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    rows = audit_service.list_academia_audit(
        db,
        entity_type="institution",
        entity_id=institution_id,
    )
    return [AcademiaAuditLogRead.model_validate(row) for row in rows]


@router.get("/academia/institutions/{institution_id}/pictures", response_model=list[InstitutionPictureRead])
def list_institution_pictures(
    institution_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return [
        InstitutionPictureRead.model_validate(row)
        for row in wizard_service.list_institution_pictures(db, institution_id)
    ]
