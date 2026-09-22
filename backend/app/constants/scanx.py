"""ScanX CRM v1 constants — document types, R2 subfolders, D11 message catalog."""

from __future__ import annotations

from typing import Final

# Eight allowed STUDENTS subfolders (D9).
SCANX_SUBFOLDERS: Final[tuple[str, ...]] = (
    "ACADEMICS",
    "APPLICATIONS",
    "DIGITAL-PRESENCE",
    "NON-ACADEMICS",
    "PROFESSIONAL-EXPERIENCE",
    "PROFILE",
    "PROJECTS-AND-RESEARCH",
    "TEST-SCORES",
)

# document_type_id → SUBFOLDER (1:1). Reject unmapped types.
DOCUMENT_TYPE_TO_SUBFOLDER: Final[dict[str, str]] = {
    "TR_TRANSCRIPT": "ACADEMICS",
    "DIPLOMA": "ACADEMICS",
    "GRADE_SHEET": "ACADEMICS",
    "ACADEMIC_CERTIFICATE": "ACADEMICS",
    "ACADEMIC_TRANSCRIPT": "ACADEMICS",  # alias → treated as TR_TRANSCRIPT in classifier
    "APPLICATION_FORM": "APPLICATIONS",
    "OFFER_LETTER": "APPLICATIONS",
    "SOP": "APPLICATIONS",
    "LOR": "APPLICATIONS",
    "PORTFOLIO": "DIGITAL-PRESENCE",
    "SOCIAL_PROFILE": "DIGITAL-PRESENCE",
    "EXTRACURRICULAR": "NON-ACADEMICS",
    "VOLUNTEERING": "NON-ACADEMICS",
    "AWARD": "NON-ACADEMICS",
    "CV_RESUME": "PROFESSIONAL-EXPERIENCE",
    "EMPLOYMENT_LETTER": "PROFESSIONAL-EXPERIENCE",
    "WORK_EXPERIENCE": "PROFESSIONAL-EXPERIENCE",  # alias → EMPLOYMENT_LETTER
    "INTERNSHIP": "PROFESSIONAL-EXPERIENCE",
    "PASSPORT": "PROFILE",
    "PHOTO": "PROFILE",
    "PERSONAL_PARTICULARS": "PROFILE",
    "PROJECT_REPORT": "PROJECTS-AND-RESEARCH",
    "RESEARCH_PAPER": "PROJECTS-AND-RESEARCH",
    "PUBLICATION": "PROJECTS-AND-RESEARCH",
    "IELTS": "TEST-SCORES",
    "TOEFL": "TEST-SCORES",
    "GRE": "TEST-SCORES",
    "GMAT": "TEST-SCORES",
    "OTHER_TEST_SCORE": "TEST-SCORES",
    # Auto-classify pending / low-confidence fallback (manual review queue).
    "UNKNOWN": "PROFILE",
    "AUTO": "PROFILE",
}

DOCUMENT_TYPE_LABELS: Final[dict[str, str]] = {
    "TR_TRANSCRIPT": "Academic transcript",
    "DIPLOMA": "Diploma / degree certificate",
    "GRADE_SHEET": "Grade sheet",
    "ACADEMIC_CERTIFICATE": "Academic certificate",
    "ACADEMIC_TRANSCRIPT": "Academic transcript",
    "APPLICATION_FORM": "Application form",
    "OFFER_LETTER": "Offer letter",
    "SOP": "Statement of purpose",
    "LOR": "Letter of recommendation",
    "PORTFOLIO": "Portfolio",
    "SOCIAL_PROFILE": "Social / digital profile",
    "EXTRACURRICULAR": "Extracurricular",
    "VOLUNTEERING": "Volunteering",
    "AWARD": "Award / recognition",
    "CV_RESUME": "CV / resume",
    "EMPLOYMENT_LETTER": "Employment letter",
    "WORK_EXPERIENCE": "Work experience",
    "INTERNSHIP": "Internship letter",
    "PASSPORT": "Passport",
    "PHOTO": "Photo",
    "PERSONAL_PARTICULARS": "Personal particulars",
    "PROJECT_REPORT": "Project report",
    "RESEARCH_PAPER": "Research paper",
    "PUBLICATION": "Publication",
    "IELTS": "IELTS score",
    "TOEFL": "TOEFL score",
    "GRE": "GRE score",
    "GMAT": "GMAT score",
    "OTHER_TEST_SCORE": "Other test score",
    "UNKNOWN": "Unknown (needs review)",
    "AUTO": "Auto-detect",
}

DOCX_MIME_TYPE: Final[str] = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

ALLOWED_MIME_TYPES: Final[frozenset[str]] = frozenset(
    {
        "application/pdf",
        DOCX_MIME_TYPE,
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/tiff",
        "image/tif",
    }
)

ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
)

STATUS_UPLOADING = "uploading"
STATUS_PARSING = "parsing"
STATUS_ACTION_REQUIRED = "action_required"
STATUS_VERIFIED = "verified"
STATUS_RED_FLAG = "red_flag"

STATUS_LABELS: Final[dict[str, str]] = {
    STATUS_UPLOADING: "Uploading",
    STATUS_PARSING: "Parsing",
    STATUS_ACTION_REQUIRED: "Review Scan",
    STATUS_VERIFIED: "Verified",
    STATUS_RED_FLAG: "Red Flags",
}

SOURCE_CRM = "crm"
# Reserved for Phase 2 — do not accept via CRM API in v1.
SOURCE_MOBILE = "mobile"

CONCURRENT_UPLOAD_CAP = 10

# D11 counsellor message catalog (M1–M15). Placeholders {X}/{N} filled at runtime.
MESSAGE_CATALOG: Final[dict[str, dict[str, str]]] = {
    "M1": {
        "severity": "blocking",
        "message": "Select a student before uploading a document.",
    },
    "M2": {
        "severity": "blocking",
        "message": "Document type could not be determined. Re-process after OCR, or contact support if this persists.",
    },
    "M3": {
        "severity": "blocking",
        "message": "This file type isn’t supported. Please upload a PDF, DOCX, PNG, JPEG, or TIFF.",
    },
    "M4": {
        "severity": "blocking",
        "message": "This file is too large. Maximum size is {X}.",
    },
    "M5": {
        "severity": "blocking",
        "message": "This document has too many pages. Maximum is {N} pages for PDF.",
    },
    "M6": {
        "severity": "blocking",
        "message": "This PDF is password-protected. Remove the password and upload again.",
    },
    "M7": {
        "severity": "blocking",
        "message": "We couldn’t read this file. It may be damaged — try re-exporting or a different copy.",
    },
    "M8": {
        "severity": "warning",
        "message": "Image quality looks low (under 150 DPI). OCR may be less accurate — consider a clearer scan.",
    },
    "M9": {
        "severity": "blocking",
        "message": "You already have the maximum number of uploads in progress. Wait for one to finish.",
    },
    "M10": {
        "severity": "blocking",
        "message": "Upload didn’t complete. Check your connection and try again.",
    },
    "M11": {
        "severity": "blocking",
        "message": "This file couldn’t be accepted for security reasons. Contact your admin if you believe this is a mistake.",
    },
    "M12": {
        "severity": "info",
        "message": "Review needed — open the document to check extracted details and confirm.",
    },
    "M13": {
        "severity": "info",
        "message": "Using default upload limits. Server settings were unavailable — you can still upload.",
    },
    "M14": {
        "severity": "warning",
        "message": "No extractable text was found (scanned or empty PDF/DOCX). Open the file and review manually.",
    },
    "M15": {
        "severity": "warning",
        "message": "OCR found no readable text (or OCR timed out/failed). Use Re-process, or open the file and review manually.",
    },
    "M16": {
        "severity": "warning",
        "message": "Processing failed after the file was accepted. Use Re-process — the file itself does not look damaged.",
    },
    "M17": {
        "severity": "blocking",
        "message": (
            "A ScanX job for “{NAME}” is already in progress for this student. "
            "Wait until it finishes, fails, or is cancelled before uploading that filename again."
        ),
    },
}


def subfolder_for_document_type(document_type_id: str) -> str | None:
    return DOCUMENT_TYPE_TO_SUBFOLDER.get((document_type_id or "").strip().upper())


def format_message(
    code: str,
    *,
    max_size_label: str | None = None,
    max_pages: int | None = None,
    name: str | None = None,
) -> str:
    entry = MESSAGE_CATALOG.get(code)
    if not entry:
        return "Something went wrong. Please try again."
    text = entry["message"]
    if max_size_label is not None:
        text = text.replace("{X}", max_size_label)
    if max_pages is not None:
        text = text.replace("{N}", str(max_pages))
    if name is not None:
        text = text.replace("{NAME}", name)
    return text
