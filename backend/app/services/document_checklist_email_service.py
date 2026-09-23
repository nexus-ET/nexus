"""Send Document Checklist email from counselor follow-up notes."""

from __future__ import annotations

import logging
import mimetypes
import re
from datetime import datetime
from html import escape
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.document_requirement import DocumentRequirement
from app.models.lead import Lead
from app.models.user import User
from app.services import document_requirement_service as req_service
from app.services.business_profile_service import (
    DEFAULT_BUSINESS_ID,
    get_business_pdf_branding,
    get_business_profile,
    resolve_business_id_for_user,
)
from app.services.document_checklist_pdf import build_document_checklist_pdf
from app.services.document_checklist_storage import (
    public_url_for_checklist_key,
    upload_document_checklist,
)
from app.services.document_template_storage import (
    fetch_template_bytes,
    public_url_for_template_key,
    storage_key_from_file_url,
)
from app.services.email_service import is_smtp_configured, send_email
from app.utils.timezone import utc_now

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _business_id_for_optional_user(user: User | None) -> int:
    if user is None:
        return DEFAULT_BUSINESS_ID
    return resolve_business_id_for_user(user)


def _student_greeting_name(lead: Lead) -> str | None:
    name = (getattr(lead, "full_name", None) or "").strip()
    return name or None


def _durable_template_url(file_url: str | None, storage_key: str | None) -> str | None:
    if storage_key:
        try:
            return public_url_for_template_key(storage_key)
        except HTTPException:
            pass
    cleaned = (file_url or "").strip()
    return cleaned or None


def _sent_document_entry(*, label: str, url: str | None) -> dict[str, Any]:
    name = (label or "").strip() or "Document"
    cleaned_url = (url or "").strip() or None
    return {
        "label": name,
        "url": cleaned_url,
        "link_unavailable": cleaned_url is None,
    }


def _attachment_kind(document_name: str) -> str:
    """Classify an attached requirement file as lor, sop, or other."""
    lowered = (document_name or "").strip().lower()
    if not lowered:
        return "other"
    if "letter of recommendation" in lowered or "letters of recommendation" in lowered:
        return "lor"
    if re.search(r"\blors?\b", lowered):
        return "lor"
    if "statement of purpose" in lowered:
        return "sop"
    if re.search(r"\bsop\b", lowered):
        return "sop"
    return "other"


def _questionnaire_paragraph(attached_names: list[str]) -> str | None:
    """Intake-questionnaire paragraph when LOR and/or SOP files are attached."""
    has_lor = False
    has_sop = False
    for name in attached_names:
        kind = _attachment_kind(name)
        if kind == "lor":
            has_lor = True
        elif kind == "sop":
            has_sop = True
    if has_lor and has_sop:
        return (
            "Additionally, please find attached the intake questionnaires for "
            "your Statement of Purpose (SOP) and Letters of Recommendation "
            "(LORs). Kindly fill these out so our team can begin drafting "
            "your documents."
        )
    if has_sop:
        return (
            "Additionally, please find attached the intake questionnaire for "
            "your Statement of Purpose (SOP). Kindly fill this out so our "
            "team can begin drafting your document."
        )
    if has_lor:
        return (
            "Additionally, please find attached the intake questionnaire for "
            "your Letters of Recommendation (LORs). Kindly fill this out so "
            "our team can begin drafting your document."
        )
    return None


_HTML_P = 'margin:0 0 12px;line-height:1.5;'
_REPLY_ALL_SENTENCE = (
    'For all future correspondence, please reply by clicking "Reply All" '
    "to keep your counselor in the loop."
)


def _html_p(inner: str, *, bold: bool = False) -> str:
    content = f"<strong>{inner}</strong>" if bold else inner
    return f'<p style="{_HTML_P}">{content}</p>'


def _build_email_bodies(
    *,
    business_name: str,
    student_name: str | None,
    level_name: str,
    country_name: str | None,
    checklist_rows: list[dict[str, Any]],
    attached_template_names: list[str],
) -> tuple[str, str]:
    company = (business_name or "").strip() or "NEXUS"
    greeting = f"Dear {student_name}," if student_name else "Dear Student,"
    team_line = f"{company} Team"

    if country_name:
        studies_clause = f"your {level_name} studies in {country_name}"
    else:
        studies_clause = f"your {level_name} studies"

    doc_paras: list[str] = []
    for index, row in enumerate(checklist_rows, start=1):
        title = (row.get("document_name") or "").strip() or "Document"
        fmt = (row.get("accepted_format") or "").strip()
        if fmt:
            doc_paras.append(f"{index}. {title} — Accepted format: {fmt}")
        else:
            doc_paras.append(f"{index}. {title}")

    docs_block = "\n\n".join(doc_paras) if doc_paras else "(No documents listed)"

    questionnaire = _questionnaire_paragraph(attached_template_names)
    questionnaire_block = f"\n\n{questionnaire}" if questionnaire else ""

    intro = (
        "I hope your counseling session was helpful. The next step in your "
        "journey is preparing your university application. To get started "
        f"with {studies_clause}, please gather and prepare the following "
        "documents:"
    )
    guideline_size = (
        "Ensure all documents adhere to the specified formats above, with a "
        "total file size under 5MB."
    )
    guideline_attach = (
        "Please send your documents directly as email attachments "
        "(do not share via Google Drive links)."
    )
    thank_you = (
        "Thank you, and I look forward to receiving your documents soon."
    )

    plain = (
        f"{greeting}\n\n"
        f"Greetings from {company}!\n\n"
        f"{intro}\n\n"
        f"{docs_block}\n\n"
        "Important Submission Guidelines:\n\n"
        f"{guideline_size}\n\n"
        f"{guideline_attach}"
        f"{questionnaire_block}\n\n"
        f"{_REPLY_ALL_SENTENCE}\n\n"
        f"{thank_you}\n\n"
        "Best regards,\n\n"
        f"{team_line}"
    )

    html_parts = [
        _html_p(escape(greeting), bold=True),
        _html_p(f"Greetings from {escape(company)}!", bold=True),
        _html_p(escape(intro)),
    ]
    if doc_paras:
        for line in doc_paras:
            html_parts.append(_html_p(escape(line)))
    else:
        html_parts.append(_html_p(escape("(No documents listed)")))
    html_parts.extend(
        [
            _html_p(escape("Important Submission Guidelines:"), bold=True),
            _html_p(escape(guideline_size)),
            _html_p(escape(guideline_attach)),
        ]
    )
    if questionnaire:
        html_parts.append(_html_p(escape(questionnaire)))
    html_parts.extend(
        [
            _html_p(escape(_REPLY_ALL_SENTENCE), bold=True),
            _html_p(escape(thank_you)),
            (
                f'<p style="{_HTML_P}"><strong>{escape("Best regards,")}</strong>'
                f"<br><strong>{escape(team_line)}</strong></p>"
            ),
        ]
    )
    html = (
        "<!DOCTYPE html><html><body style=\"font-family:Segoe UI,Arial,sans-serif;"
        "font-size:15px;color:#1a1a1a;background:#ffffff;padding:16px;\">"
        f"{''.join(html_parts)}</body></html>"
    )
    return plain, html


def _load_checklist_requirements(
    db: Session,
    *,
    program_level: str,
    scope: str,
    country_id: int | None,
) -> list[DocumentRequirement]:
    rows = req_service.list_requirements_for_checklist(
        db,
        program_level=program_level,
        scope=scope,
        country_id=country_id,
    )
    if not rows:
        return []
    ids = [row.id for row in rows]
    loaded = (
        db.query(DocumentRequirement)
        .options(joinedload(DocumentRequirement.template))
        .filter(DocumentRequirement.id.in_(ids))
        .all()
    )
    by_id = {row.id: row for row in loaded}
    return [by_id[rid] for rid in ids if rid in by_id]


def _collect_template_attachments(
    rows: list[DocumentRequirement],
) -> tuple[list[tuple[str, bytes, str]], list[dict[str, Any]]]:
    """Return (email attachments, sent-document entries for templates actually attached)."""
    attachments: list[tuple[str, bytes, str]] = []
    sent_docs: list[dict[str, Any]] = []
    for row in rows:
        template = row.template
        if template is None or not (template.file_url or "").strip():
            continue
        key = storage_key_from_file_url(template.file_url)
        if not key:
            logger.warning(
                "Skipping template for requirement %s — could not resolve storage key",
                row.id,
            )
            continue
        try:
            content, content_type = fetch_template_bytes(key)
        except HTTPException as exc:
            logger.warning(
                "Skipping template for requirement %s: %s",
                row.id,
                getattr(exc, "detail", exc),
            )
            continue
        except Exception:
            logger.exception(
                "Skipping template for requirement %s — fetch failed",
                row.id,
            )
            continue
        if not content:
            continue
        filename = (template.template_name or "").strip() or f"template_{row.id}"
        mime = (content_type or "").split(";")[0].strip().lower()
        if not mime or mime == "application/octet-stream":
            guessed, _ = mimetypes.guess_type(filename)
            mime = (guessed or "application/octet-stream").split(";")[0].strip()
        attachments.append((filename, content, mime))
        label = (row.document_name or "").strip() or filename
        sent_docs.append(
            _sent_document_entry(
                label=label,
                url=_durable_template_url(template.file_url, key),
            )
        )
    return attachments, sent_docs


def prepare_checklist_email_assets(
    db: Session,
    *,
    program_level: str,
    scope: str,
    country_id: int | None,
    current_user: User | None,
) -> dict[str, Any]:
    """Build PDF + template attachments for the selected checklist.

    Raises HTTPException for validation / generation failures (caller may map to
    email_error after note save, or raise before save for bad selection).
    """
    if scope == "global" and country_id is not None:
        raise HTTPException(
            status_code=400,
            detail="country_id must not be provided when scope is global",
        )
    if scope == "country_specific" and country_id is None:
        raise HTTPException(
            status_code=400,
            detail="country_id is required when scope is country_specific",
        )

    business_id = _business_id_for_optional_user(current_user)
    profile = get_business_profile(db, business_id)
    short_name = (profile.get("business_short_name") or "").strip()
    if not short_name:
        raise HTTPException(
            status_code=400,
            detail=(
                "Business short name is required to create a document checklist. "
                "Set Business short name in Settings before sending a checklist."
            ),
        )

    catalog_level = req_service.resolve_catalog_level(db, program_level)
    level_name = catalog_level.name
    country_name: str | None = None

    if scope == "country_specific":
        countries = req_service.resolve_countries(db, [int(country_id)])
        country_name = countries[0].name
        if not req_service.has_country_mapped_requirement_for_level(
            db,
            program_level=level_name,
            country_id=int(country_id),
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No country-mapped document requirements for level '{level_name}' "
                    f"and country '{country_name}'."
                ),
            )

    rows = _load_checklist_requirements(
        db,
        program_level=level_name,
        scope=scope,
        country_id=country_id,
    )
    if not rows:
        if scope == "global":
            detail = (
                f"No global document requirements are assigned to level '{level_name}'."
            )
        else:
            detail = (
                f"No document requirements apply to level '{level_name}' "
                f"for country '{country_name}'."
            )
        raise HTTPException(status_code=400, detail=detail)

    branding = get_business_pdf_branding(db, business_id)
    business_name = branding.get("business_name") or profile.get("business_name") or "NEXUS"
    generated_at = datetime.now()
    checklist_row_dicts = [
        {
            "document_name": row.document_name,
            "description": row.description,
            "accepted_format": row.accepted_format,
        }
        for row in rows
    ]
    pdf_bytes = build_document_checklist_pdf(
        level_name=level_name,
        rows=checklist_row_dicts,
        generated_at=generated_at,
        business_name=business_name,
        logo_path=branding.get("logo_path"),
        country_name=country_name,
    )
    uploaded = upload_document_checklist(
        level_name=level_name,
        business_short_name=short_name,
        content=pdf_bytes,
        country_name=country_name,
    )
    pdf_filename = str(uploaded["filename"])
    storage_key = str(uploaded["storage_key"])
    try:
        checklist_url = public_url_for_checklist_key(storage_key)
    except HTTPException:
        checklist_url = None

    template_attachments, template_sent_docs = _collect_template_attachments(rows)
    attachments: list[tuple[str, bytes, str]] = [
        (pdf_filename, pdf_bytes, "application/pdf"),
        *template_attachments,
    ]
    sent_documents = [
        _sent_document_entry(label=pdf_filename, url=checklist_url),
        *template_sent_docs,
    ]
    attached_template_names = [doc["label"] for doc in template_sent_docs]

    return {
        "level_name": level_name,
        "country_name": country_name,
        "business_name": business_name,
        "business_short_name": short_name,
        "checklist_rows": checklist_row_dicts,
        "attachments": attachments,
        "attached_template_names": attached_template_names,
        "pdf_filename": pdf_filename,
        "sent_documents": sent_documents,
    }


def send_document_checklist_to_lead(
    db: Session,
    *,
    lead: Lead,
    program_level: str,
    scope: str,
    country_id: int | None,
    current_user: User | None,
) -> dict[str, Any]:
    """Generate checklist PDF, attach templates, and email the lead.

    Returns:
      {
        "sent": bool,
        "error": str | None,
        "email_to": str | None,
        "sent_at": datetime | None,
        "sent_documents": list[dict] | None,
      }
    """
    empty_fail = {
        "sent": False,
        "error": None,
        "email_to": None,
        "sent_at": None,
        "sent_documents": None,
    }

    email = (getattr(lead, "email", None) or "").strip()
    if not email or not _EMAIL_RE.match(email):
        return {
            **empty_fail,
            "error": (
                "This lead has no valid email address. "
                "The note was saved, but the document checklist email was not sent."
            ),
        }

    if not is_smtp_configured():
        return {
            **empty_fail,
            "error": (
                "Email (SMTP) is not configured on the server. "
                "The note was saved, but the document checklist email was not sent."
            ),
        }

    try:
        assets = prepare_checklist_email_assets(
            db,
            program_level=program_level,
            scope=scope,
            country_id=country_id,
            current_user=current_user,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return {
            **empty_fail,
            "error": (
                f"The note was saved, but the document checklist email was not sent: "
                f"{detail}"
            ),
        }
    except Exception as exc:
        logger.exception("Failed to prepare document checklist email assets")
        return {
            **empty_fail,
            "error": (
                "The note was saved, but the document checklist email could not be "
                f"prepared: {exc}"
            ),
        }

    student_name = _student_greeting_name(lead)
    body, html_body = _build_email_bodies(
        business_name=str(assets["business_name"]),
        student_name=student_name,
        level_name=str(assets["level_name"]),
        country_name=assets.get("country_name"),
        checklist_rows=list(assets["checklist_rows"]),
        attached_template_names=list(assets["attached_template_names"]),
    )
    subject = (
        f"Document checklist for your {assets['level_name']} studies"
        if not assets.get("country_name")
        else (
            f"Document checklist for your {assets['level_name']} studies "
            f"({assets['country_name']})"
        )
    )
    short_name = (assets.get("business_short_name") or "").strip()
    if short_name:
        subject = f"{short_name} - {subject}"

    sent = send_email(
        [email],
        subject,
        body,
        html_body=html_body,
        attachments=list(assets["attachments"]),
    )
    if not sent:
        return {
            **empty_fail,
            "error": (
                "The note was saved, but the document checklist email could not be "
                "delivered. Please verify SMTP settings and try again."
            ),
        }

    return {
        "sent": True,
        "error": None,
        "email_to": email,
        "sent_at": utc_now(),
        "sent_documents": list(assets.get("sent_documents") or []),
    }


def validate_checklist_email_selection(
    db: Session,
    *,
    program_level: str | None,
    scope: str | None,
    country_id: int | None,
) -> tuple[str, str, int | None]:
    """Validate UI selection before saving when Send email is Yes."""
    level = (program_level or "").strip()
    if not level:
        raise HTTPException(
            status_code=400,
            detail="Select a program level before sending the document checklist email.",
        )
    raw_scope = (scope or "global").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "global": "global",
        "country_specific": "country_specific",
        "countryspecific": "country_specific",
        "country": "country_specific",
    }
    normalized_scope = aliases.get(raw_scope)
    if normalized_scope is None:
        raise HTTPException(
            status_code=400,
            detail="Checklist scope must be Global or Country-Specific.",
        )
    if normalized_scope == "country_specific" and country_id is None:
        raise HTTPException(
            status_code=400,
            detail="Select a country before sending a country-specific document checklist.",
        )
    if normalized_scope == "global":
        country_id = None

    enabled = req_service.list_catalog_levels_with_requirements(
        db,
        scope=normalized_scope,
        country_id=country_id,
    )
    catalog = req_service.resolve_catalog_level(db, level)
    if catalog.name not in enabled:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No document checklist can be built for level '{catalog.name}' "
                "with the selected scope."
            ),
        )
    return catalog.name, normalized_scope, country_id
