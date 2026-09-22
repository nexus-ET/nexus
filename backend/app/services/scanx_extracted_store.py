"""Persist ScanX extraction rows into ``documents`` / ``extracted_document_data``.

Uses a short-lived session so failures never roll back the OCR job session.
Tables may be unmigrated — errors are logged and ignored.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def _ensure_document_type(db: Any, code: str) -> uuid.UUID | None:
    from app.models.document_extraction import DocumentType

    code_u = (code or "").strip().upper()
    if not code_u:
        return None
    row = db.query(DocumentType).filter(DocumentType.code == code_u).first()
    if row:
        return row.id
    row = DocumentType(code=code_u, name=code_u.replace("_", " ").title())
    db.add(row)
    db.flush()
    return row.id


def persist_extracted_from_scanx(
    *,
    scanx_doc: Any,
    field_group: str,
    structured_data: dict[str, Any],
    bounding_box: Any = None,
    confidence_score: float | None = None,
    is_low_confidence: bool = False,
    reading_order_index: int = 0,
) -> uuid.UUID | None:
    """Create/update UUID ``documents`` + ``extracted_document_data`` for a ScanX doc."""
    from app.db.database import SessionLocal, safe_close_session

    db = SessionLocal()
    try:
        from app.models.document_extraction import Document, ExtractedDocumentData

        type_code = str(getattr(scanx_doc, "document_type_id", "") or "").strip().upper()
        type_id = _ensure_document_type(db, type_code or "OTHER")
        if type_id is None:
            return None

        lead_id = int(getattr(scanx_doc, "lead_id"))
        storage_path = (
            str(getattr(scanx_doc, "r2_key", None) or "").strip()
            or f"scanx/{lead_id}/{getattr(scanx_doc, 'doc_uuid', scanx_doc.id)}"
        )
        upload_source = str(getattr(scanx_doc, "source", None) or "NEXUS_CRM").upper()
        if upload_source in {"CRM"}:
            upload_source = "NEXUS_CRM"
        if upload_source in {"MOBILE"}:
            upload_source = "MOBILE_APP"

        status = str(getattr(scanx_doc, "status", "") or "").strip().lower()
        status = {
            "uploading": "UPLOADING",
            "parsing": "PARSING",
            "action_required": "ACTION_REQUIRED",
            "verified": "VERIFIED",
            "red_flag": "RED_FLAG",
        }.get(status, (status or "PARSING").upper().replace(" ", "_")[:32])

        doc_row = (
            db.query(Document)
            .filter(
                Document.candidate_id == lead_id,
                Document.storage_path == storage_path,
            )
            .first()
        )
        if doc_row is None:
            doc_row = Document(
                candidate_id=lead_id,
                document_type_id=type_id,
                upload_source=upload_source[:32],
                uploader_user_id=getattr(scanx_doc, "uploader_user_id", None),
                storage_path=storage_path[:1024],
                file_size_bytes=getattr(scanx_doc, "byte_size", None),
                page_count=getattr(scanx_doc, "page_count", None),
                status=status[:32],
            )
            db.add(doc_row)
            db.flush()
        else:
            doc_row.document_type_id = type_id
            doc_row.status = status[:32]
            doc_row.file_size_bytes = getattr(scanx_doc, "byte_size", None)
            doc_row.page_count = getattr(scanx_doc, "page_count", None)
            doc_row.upload_source = upload_source[:32]

        db.query(ExtractedDocumentData).filter(
            ExtractedDocumentData.document_id == doc_row.id,
            ExtractedDocumentData.field_group == field_group,
        ).delete(synchronize_session=False)

        conf = confidence_score
        if conf is None:
            scores = structured_data.get("confidence_scores")
            if isinstance(scores, dict) and scores:
                vals = [float(v) for v in scores.values() if isinstance(v, (int, float))]
                conf = min(vals) if vals else None

        low_flag = bool(
            is_low_confidence or structured_data.get("is_low_confidence") is True
        )
        box = bounding_box
        if box is None:
            boxes = structured_data.get("bounding_boxes")
            if isinstance(boxes, dict) and boxes:
                first = next(iter(boxes.values()), None)
                if isinstance(first, list):
                    box = first

        row = ExtractedDocumentData(
            document_id=doc_row.id,
            field_group=field_group[:64],
            structured_data=dict(structured_data),
            bounding_box=box,
            confidence_score=conf,
            is_low_confidence=low_flag,
            reading_order_index=int(reading_order_index or 0),
        )
        db.add(row)
        db.commit()

        if field_group == "passport" and isinstance(structured_data, dict):
            _sync_passport_spouse_to_students_master(
                db,
                lead_id=lead_id,
                spouse_name=structured_data.get("spouse_name"),
            )

        return row.id
    except Exception:
        logger.warning(
            "ScanX extracted_document_data persist skipped doc_id=%s",
            getattr(scanx_doc, "id", None),
            exc_info=True,
        )
        try:
            db.rollback()
        except Exception:
            pass
        return None
    finally:
        safe_close_session(db)


def _sync_passport_spouse_to_students_master(
    db: Any,
    *,
    lead_id: int,
    spouse_name: Any,
) -> None:
    """Best-effort: copy passport spouse_name onto students_master when present."""
    name = str(spouse_name or "").strip()
    if not name or len(name) > 255:
        return
    try:
        from app.models.students_master import StudentsMaster

        row = (
            db.query(StudentsMaster)
            .filter(StudentsMaster.lead_id == int(lead_id))
            .first()
        )
        if row is None:
            return
        if (row.spouse_name or "").strip() == name:
            return
        row.spouse_name = name
        db.commit()
    except Exception:
        logger.debug(
            "students_master spouse_name sync skipped lead_id=%s",
            lead_id,
            exc_info=True,
        )
        try:
            db.rollback()
        except Exception:
            pass
