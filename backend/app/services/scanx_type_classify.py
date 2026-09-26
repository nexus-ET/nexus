"""Post-OCR document-type classification via RegEx / heuristics.

Assigns ScanX ``document_type_id`` codes (PASSPORT, TR_TRANSCRIPT, LOR, SOP,
EMPLOYMENT_LETTER, …) or ``UNKNOWN`` when confidence is below threshold.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Minimum winning score (0–1) before we accept a type; else UNKNOWN.
_CONFIDENCE_THRESHOLD = 0.42


@dataclass
class TypeClassification:
    document_type_id: str
    confidence: float
    reason: str
    scores: dict[str, float] = field(default_factory=dict)

    def to_metrics(self) -> dict[str, Any]:
        return {
            "auto_document_type_id": self.document_type_id,
            "auto_document_type_confidence": round(float(self.confidence), 3),
            "auto_document_type_reason": self.reason,
            "auto_document_type_scores": {
                k: round(float(v), 3) for k, v in self.scores.items()
            },
            "auto_document_type_threshold": _CONFIDENCE_THRESHOLD,
        }


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").upper()).strip()


def _score_passport_signals(text: str, raw: str) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    if re.search(r"\bP<[A-Z]{3}[A-Z0-9<]{20,}", raw.replace(" ", ""), re.I):
        score += 0.55
        reasons.append("mrz_p_line")
    if re.search(r"\bPASSPORT\b", text):
        score += 0.2
        reasons.append("passport_keyword")
    if re.search(r"\bSURNAME\b", text) and re.search(r"\bGIVEN\s+NAMES?\b", text):
        score += 0.2
        reasons.append("surname_given")
    if re.search(r"\bREPUBLIC\s+OF\s+INDIA\b", text):
        score += 0.22
        reasons.append("republic_of_india")
    if re.search(r"\b[A-Z]\d{7}\b", text):
        score += 0.2
        reasons.append("passport_number")
    if re.search(r"\b(MRZ|MACHINE[- ]READABLE)\b", text):
        score += 0.1
        reasons.append("mrz_label")
    if re.search(r"\b(DATE\s+OF\s+EXPIRY|DATE\s+OF\s+ISSUE)\b", text):
        score += 0.08
        reasons.append("issue_expiry")
    if re.search(r"\bDATE\s+OF\s+BIRTH\b", text):
        score += 0.08
        reasons.append("date_of_birth")
    return min(1.0, score), "+".join(reasons) or "none"


def _score_passport(text: str, raw: str, *, original: str | None = None) -> tuple[float, str]:
    """Score passport cues on the full OCR and again with comment lines removed.

    Notary / attestation stamps must not hide a page that still reads as a passport.
    """
    best_s, best_r = _score_passport_signals(text, raw)
    source = original if original is not None else text
    try:
        from app.services.scanx_passport import strip_non_passport_comments

        stripped = strip_non_passport_comments(source)
    except Exception:
        return best_s, best_r
    if not stripped.strip() or stripped == source:
        return best_s, best_r
    s2, r2 = _score_passport_signals(
        _norm(stripped),
        stripped.upper().replace(" ", ""),
    )
    if s2 > best_s:
        return s2, r2
    return best_s, best_r


def _score_academic_transcript(text: str) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    if re.search(
        r"HIGHER\s+SECONDARY\s+COURSE\s+CERTIFICATE|STATE\s+BOARD|BOARD\s+OF\s+SECONDARY",
        text,
    ):
        score += 0.35
        reasons.append("board_certificate")
    if re.search(r"\bMARKS?\s+OBTAINED\b|\bOBTAINED\s+THE\s+FOLLOWING\s+MARKS\b", text):
        score += 0.25
        reasons.append("marks_obtained")
    if re.search(r"\bTHEORY\b", text) and re.search(r"\bPRACTICAL\b", text):
        score += 0.2
        reasons.append("theory_practical")
    if re.search(r"\b(SUBJECTS?|GRADE\s*SHEET|MARK\s*SHEET|TRANSCRIPT)\b", text):
        score += 0.15
        reasons.append("subject_grid")
    if re.search(r"\b(REGISTER\s*NO|ROLL\s*NO|EXAMINATION)\b", text):
        score += 0.08
        reasons.append("exam_ids")
    # Dense digit rows suggest mark grids.
    digit_lines = sum(
        1
        for ln in text.splitlines()
        if re.search(r"\d{2,3}", ln) and re.search(r"[A-Z]{3,}", ln)
    )
    if digit_lines >= 4:
        score += 0.12
        reasons.append("numeric_grid")
    return min(1.0, score), "+".join(reasons) or "none"


def _score_lor(text: str) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    if re.search(r"TO\s+WHOM\s+IT\s+MAY\s+CONCERN", text):
        score += 0.35
        reasons.append("to_whom")
    if re.search(
        r"I\s+AM\s+WRITING\s+TO\s+RECOMMEND|WRITING\s+THIS\s+LETTER\s+OF\s+RECOMMENDATION|"
        r"PLEASED\s+TO\s+RECOMMEND|STRONGLY\s+RECOMMEND",
        text,
    ):
        score += 0.4
        reasons.append("recommend_phrase")
    if re.search(r"\b(LETTER\s+OF\s+RECOMMENDATION|RECOMMENDATION\s+LETTER|LOR)\b", text):
        score += 0.25
        reasons.append("lor_header")
    if re.search(
        r"\b(PROFESSOR|DR\.|ASSOCIATE\s+PROFESSOR|HEAD\s+OF\s+DEPARTMENT|REFEREE)\b",
        text,
    ):
        score += 0.1
        reasons.append("academic_title")
    if re.search(r"\b(SINCERELY|YOURS\s+FAITHFULLY|BEST\s+REGARDS)\b", text):
        score += 0.08
        reasons.append("signoff")
    return min(1.0, score), "+".join(reasons) or "none"


def _score_sop(text: str) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    if re.search(
        r"\b(STATEMENT\s+OF\s+PURPOSE|PERSONAL\s+STATEMENT|SOP)\b",
        text,
    ):
        score += 0.4
        reasons.append("sop_header")
    if re.search(
        r"\b(MY\s+ACADEMIC\s+(BACKGROUND|GOALS)|CAREER\s+OBJECTIVE|I\s+ASPIRE|"
        r"PURSUING\s+(A|AN|MY)\s+(MASTER|BACHELOR|PH\.?D))\b",
        text,
    ):
        score += 0.25
        reasons.append("career_academic")
    # Long narrative without mark grids.
    words = len(text.split())
    if words >= 250 and not re.search(r"\bTHEORY\b.*\bPRACTICAL\b", text):
        score += 0.15
        reasons.append("long_narrative")
    if re.search(r"\b(IN\s+CONCLUSION|THROUGHOUT\s+MY\s+(LIFE|CAREER|STUDIES))\b", text):
        score += 0.1
        reasons.append("essay_close")
    return min(1.0, score), "+".join(reasons) or "none"


def _score_work_experience(text: str) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    if re.search(
        r"\b(EMPLOYMENT|EMPLOYER|EMPLOYEE|WORK\s+EXPERIENCE|EXPERIENCE\s+CERTIFICATE)\b",
        text,
    ):
        score += 0.3
        reasons.append("employment")
    if re.search(r"\b(DESIGNATION|JOB\s+TITLE|POSITION\s+HELD)\b", text):
        score += 0.2
        reasons.append("designation")
    if re.search(r"\b(TENURE|FROM\s+.+\s+TO\s+|PERIOD\s+OF\s+(EMPLOYMENT|SERVICE))\b", text):
        score += 0.2
        reasons.append("tenure")
    if re.search(
        r"\b(THIS\s+IS\s+TO\s+CERTIFY|HAS\s+BEEN\s+EMPLOYED|WAS\s+EMPLOYED\s+WITH)\b",
        text,
    ):
        score += 0.25
        reasons.append("certify_employed")
    if re.search(r"\b(HR\s+MANAGER|HUMAN\s+RESOURCES|COMPANY\s+LETTERHEAD)\b", text):
        score += 0.1
        reasons.append("hr_letterhead")
    return min(1.0, score), "+".join(reasons) or "none"


def classify_document_type(
    text: str | None,
    *,
    filename: str | None = None,
    prior_type_id: str | None = None,
) -> TypeClassification:
    """Return best-matching document_type_id from OCR/native text."""
    raw = text or ""
    blob = _norm(raw)
    name = _norm(filename or "")

    scores: dict[str, float] = {}
    reasons: dict[str, str] = {}

    s, r = _score_passport(blob, raw.upper().replace(" ", ""), original=raw)
    # Filename hints.
    if re.search(r"PASSPORT", name):
        s = min(1.0, s + 0.25)
        r = (r + "+filename") if r != "none" else "filename"
    scores["PASSPORT"] = s
    reasons["PASSPORT"] = r

    s, r = _score_academic_transcript(blob)
    if re.search(r"TRANSCRIPT|MARK\s*SHEET|GRADE\s*SHEET|HSC|SSLC", name):
        s = min(1.0, s + 0.2)
        r = (r + "+filename") if r != "none" else "filename"
    scores["TR_TRANSCRIPT"] = s
    reasons["TR_TRANSCRIPT"] = r

    s, r = _score_lor(blob)
    if re.search(r"\bLOR\b|RECOMMENDATION", name):
        s = min(1.0, s + 0.25)
        r = (r + "+filename") if r != "none" else "filename"
    scores["LOR"] = s
    reasons["LOR"] = r

    s, r = _score_sop(blob)
    if re.search(r"\bSOP\b|STATEMENT|PERSONAL\s*STATEMENT", name):
        s = min(1.0, s + 0.25)
        r = (r + "+filename") if r != "none" else "filename"
    scores["SOP"] = s
    reasons["SOP"] = r

    s, r = _score_work_experience(blob)
    if re.search(r"EMPLOY|EXPERIENCE|TENURE|OFFER", name):
        s = min(1.0, s + 0.15)
        r = (r + "+filename") if r != "none" else "filename"
    scores["EMPLOYMENT_LETTER"] = s
    reasons["EMPLOYMENT_LETTER"] = r

    best_type = max(scores, key=lambda k: scores[k])
    best_score = float(scores[best_type])

    # Prefer prior type only if auto is weak and prior was explicitly set (not UNKNOWN/AUTO).
    prior = (prior_type_id or "").strip().upper()
    if (
        prior
        and prior not in {"UNKNOWN", "AUTO", ""}
        and best_score < _CONFIDENCE_THRESHOLD
    ):
        return TypeClassification(
            document_type_id=prior,
            confidence=best_score,
            reason=f"retain_prior_low_auto({reasons.get(best_type, '')})",
            scores=scores,
        )

    if best_score < _CONFIDENCE_THRESHOLD:
        return TypeClassification(
            document_type_id="UNKNOWN",
            confidence=best_score,
            reason=f"below_threshold:{best_type}:{reasons.get(best_type, '')}",
            scores=scores,
        )

    # Normalize aliases to canonical ScanX codes.
    canonical = {
        "ACADEMIC_TRANSCRIPT": "TR_TRANSCRIPT",
        "WORK_EXPERIENCE": "EMPLOYMENT_LETTER",
    }.get(best_type, best_type)

    return TypeClassification(
        document_type_id=canonical,
        confidence=best_score,
        reason=reasons.get(best_type, "matched"),
        scores=scores,
    )
