"""Nexus Intel AI Assistant — hybrid retrieval + grounded LLM synthesis."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from typing import Any

import httpx
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models.academia_institution import Institution
from app.models.country import Country
from app.models.level import Level
from app.models.nexus_intel import IntelAiChatLog, IntelGlossary
from app.models.program import Program
from app.services.ai_providers import parse_model_ref
from app.services.lead_study_interest import resolve_lead_study_interest

logger = logging.getLogger(__name__)

COUNTRY_ALIASES: dict[str, str] = {
    "canada": "CA",
    "canadian": "CA",
    "ca": "CA",
    "uk": "UK",
    "united kingdom": "UK",
    "britain": "UK",
    "british": "UK",
    "england": "UK",
    "australia": "AU",
    "australian": "AU",
    "au": "AU",
    "germany": "DE",
    "german": "DE",
    "de": "DE",
    "usa": "US",
    "united states": "US",
    "america": "US",
    "american": "US",
    "us": "US",
    "japan": "JP",
    "japanese": "JP",
    "jp": "JP",
    "france": "FR",
    "french": "FR",
    "fr": "FR",
    "uae": "AE",
    "dubai": "AE",
    "emirates": "AE",
    "ae": "AE",
    "new zealand": "NZ",
    "nz": "NZ",
    "singapore": "SG",
    "sg": "SG",
    "sweden": "SE",
    "swedish": "SE",
    "se": "SE",
    "switzerland": "CH",
    "swiss": "CH",
    "ch": "CH",
    "russia": "RU",
    "russian": "RU",
    "india": "IN",
    "indian": "IN",
    "china": "CN",
    "chinese": "CN",
    "ireland": "IE",
    "irish": "IE",
    "italy": "IT",
    "italian": "IT",
    "spain": "ES",
    "spanish": "ES",
    "netherlands": "NL",
    "dutch": "NL",
    "holland": "NL",
    "malaysia": "MY",
    "philippines": "PH",
    "poland": "PL",
    "polish": "PL",
    "hungary": "HU",
    "georgia": "GE",
    "kazakhstan": "KZ",
    "uzbekistan": "UZ",
    "bangladesh": "BD",
    "nepal": "NP",
    "sri lanka": "LK",
}

STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "for",
    "of",
    "to",
    "in",
    "on",
    "at",
    "is",
    "are",
    "was",
    "were",
    "be",
    "what",
    "which",
    "who",
    "how",
    "when",
    "where",
    "why",
    "does",
    "do",
    "did",
    "can",
    "could",
    "should",
    "would",
    "with",
    "from",
    "this",
    "that",
    "these",
    "those",
    "any",
    "all",
    "student",
    "students",
    "please",
    "tell",
    "me",
    "about",
    "need",
    "needs",
    "current",
    "latest",
    "you",
    "your",
    "yours",
    "our",
    "ours",
    "have",
    "has",
    "had",
    "available",
    "offer",
    "offers",
    "offering",
    "offerings",
    "show",
    "list",
    "give",
    "get",
    "find",
    "there",
    "here",
}

# Expand subject tokens so "Medicine" also matches MBBS / MD / clinical rows.
SUBJECT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "medicine": ("medicine", "medic", "medical", "mbbs", "md", "mds", "clinical", "physician", "surgery"),
    "medical": ("medicine", "medic", "medical", "mbbs", "md", "clinical", "surgery"),
    "mbbs": ("mbbs", "medicine", "medical", "surgery"),
    "md": ("md", "medicine", "medical", "doctor"),
    "dental": ("dental", "dentistry", "bds", "mds", "surgery"),
    "dentistry": ("dental", "dentistry", "bds", "mds"),
    "engineering": ("engineering", "engineer", "beng", "meng"),
    "law": ("law", "llb", "llm", "jd", "legal"),
    "business": ("business", "mba", "bba", "commerce", "management", "finance", "marketing"),
    "computer": ("computer", "computing", "cs", "software", "programming"),
    "data": ("data", "analytics", "science", "ml", "ai"),
}

CATALOG_INTENT = re.compile(
    r"\b(courses?|programs?|majors?|degrees?|universit(?:y|ies)|colleges?|"
    r"offer(?:s|ings?)?|catalog|qualification|curriculum|subjects?)\b",
    re.I,
)

PEOPLE_INTENT = re.compile(
    r"\b(students?|leads?|prospects?|aspiring|candidates?|applicants?|"
    r"enquir(?:y|ies)|pipeline)\b",
    re.I,
)

COUNT_INTENT = re.compile(
    r"\b(how many|count|number of|total(?:\s+number)?|how much)\b",
    re.I,
)

PLACE_INTENT = re.compile(
    r"\b(states?|cities?|city|province|region|regions?|geography|towns?)\b",
    re.I,
)

SCHEDULE_INTENT = re.compile(
    r"\b(appointments?|bookings?|booked|schedule[ds]?|consultation|slots?|"
    r"calendar|meeting|counselling|counseling|sessions?|"
    r"wrap[- ]?up|completed|completion|outcome)\b",
    re.I,
)

ACTION_INTENT = re.compile(
    r"\b("
    r"reschedul(?:e|ed|ing)|cancel(?:led|ing)|"
    r"send(?:\s+\w+){0,3}\s+(?:a\s+)?(?:whats?app|email|sms|message|confirmation)|"
    r"(?:whats?app|email)\s+(?:confirmation|message)|"
    r"message\s+(?:the\s+)?(?:student|lead|candidate|prospect)|"
    r"(?:please\s+|can\s+you\s+|could\s+you\s+)?"
    r"(?:schedule|book|confirm|update|change|move)\b"
    r".{0,80}\b(?:for|to|at|tomorrow|today|\d{1,2}\s*(?:am|pm)|appointment|session|booking)\b"
    r")",
    re.I,
)

# Imperative / side-effect requests must never be answered as if the action happened.
MUTATING_ACTION_INTENT = re.compile(
    r"\b("
    r"reschedul(?:e|ed|ing)|cancel(?:led|ing)|"
    r"send(?:\s+\w+){0,4}\s+(?:a\s+)?(?:whats?app|email|sms|message|confirmation)|"
    r"(?:whats?app|email)\s+(?:confirmation|message)|"
    r"(?:book|schedule|confirm)\s+(?:the\s+|an?\s+)?(?:appointment|booking|session|slot)|"
    r"(?:please\s+|can\s+you\s+|could\s+you\s+|go\s+ahead\s+and\s+)"
    r"(?:schedule|book|reschedule|cancel|send|update|change|move)\b"
    r")",
    re.I,
)

# Pronoun / deictic follow-ups that refer to an earlier lead/booking in the thread.
REFERENTIAL_FOLLOWUP = re.compile(
    r"\b("
    r"this|that|the|said|same|above|previous|earlier"
    r")\s+(student|lead|booking|appointment|session|candidate|prospect)\b|"
    r"\b(their|his|her)\s+(status|session|booking|appointment)\b|"
    r"\bcurrent status of (this|that|the)\s+lead\b",
    re.I,
)

LEAD_ID_RE = re.compile(r"\blead\s*#?\s*(\d+)\b", re.I)
BOOKING_ID_RE = re.compile(r"\bbooking\s*(?:id)?\s*[#:]?\s*(\d+)\b", re.I)

LIVE_HINTS = re.compile(
    r"\b(current|latest|today|now|verify|live|updated|202[4-9]|real[- ]?time)\b",
    re.I,
)

HTML_TAG_RE = re.compile(r"<[^>]+>", re.I)
HTML_ENTITY_RE = re.compile(
    r"&nbsp;|&amp;|&lt;|&gt;|&quot;|&#39;|&apos;|&#(\d+);|&#x([0-9a-fA-F]+);",
    re.I,
)


def _decode_html_entities(text: str) -> str:
    def _repl(match: re.Match[str]) -> str:
        token = match.group(0).lower()
        if token == "&nbsp;":
            return " "
        if token == "&amp;":
            return "&"
        if token == "&lt;":
            return "<"
        if token == "&gt;":
            return ">"
        if token in {"&quot;",}:
            return '"'
        if token in {"&#39;", "&apos;"}:
            return "'"
        if match.group(1):
            try:
                return chr(int(match.group(1)))
            except ValueError:
                return ""
        if match.group(2):
            try:
                return chr(int(match.group(2), 16))
            except ValueError:
                return ""
        return ""

    return HTML_ENTITY_RE.sub(_repl, text)


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    cleaned = HTML_TAG_RE.sub(" ", str(text))
    cleaned = _decode_html_entities(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _sanitize_assistant_text(text: str | None) -> str:
    """Remove HTML from model output while preserving Markdown line breaks."""
    if not text:
        return ""
    cleaned = HTML_TAG_RE.sub("", str(text))
    cleaned = _decode_html_entities(cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


SYSTEM_PROMPT = """You are Nexus Intel AI, an expert compliance and institutional knowledge assistant. You must answer questions *only* using the provided context chunks from the Nexus database, glossary, and verified records.

Answer using ONLY the provided Nexus context JSON buckets and the verified sources list (leads, courses, programs, majors, levels, institutions, countries, states, cities, bookings, appointments, glossary, web).

Rules:
1. Factual constraint: every claim must be supported by the provided context. Prefer quoting or paraphrasing retrieved fields (definitions, counts, names, codes, dates) over free-form prose.
2. Anti-hallucination fallback: if the answer cannot be determined explicitly from the provided context, you must state exactly: "I could not find verified information regarding this in the Nexus Intel database." Do not extrapolate, assume, or make up policies, dates, fees, visa rules, or requirements.
3. Match the question intent. For "how many / count" questions about students/leads, lead with the exact count from context, then a short bullet list of names + target country/program. Do not invent extra leads.
4. When a destination country is specified, only use leads whose target country matches that destination (ignore unrelated countries).
5. For follow-ups about "this/that student/lead/session/booking", use the lead + booking + appointment rows in context. Report booking status (e.g. SCHEDULED, COMPLETED), scheduled time, and lead stage exactly as stored. SCHEDULED means the session is not completed yet unless status/outcome says otherwise.
6. You are read-only. Never claim you scheduled, rescheduled, cancelled, confirmed, updated, or sent any message/email/WhatsApp unless the context explicitly contains a stored record proving that action already happened. If asked to perform an action, say you cannot perform actions from this chat and report only the current stored status.
7. Ignore unrelated buckets (e.g. levels/glossary/visa terms) unless the user asked about them.
8. Prefer precise bullets. Never invent fees, policies, institutions, or leads. Never output HTML.
9. Do not expose full phone numbers or emails.
10. Only cite sources that appear in the provided verified sources / context.

Respond with a single JSON object only:
{
  "response_text": "<markdown answer>",
  "sources": [
    {"type": "glossary|country|state|city|level|program|major|course|university|lead|booking|appointment|web", "title": "<short title>", "url": "<optional url or null>", "id": "<optional id or null>"}
  ]
}
Only include sources you actually used (max 12).
"""


def _extract_country_codes(prompt: str) -> list[str]:
    lower = prompt.lower()
    found: list[str] = []
    for alias, code in sorted(COUNTRY_ALIASES.items(), key=lambda x: -len(x[0])):
        if re.search(rf"\b{re.escape(alias)}\b", lower) and code not in found:
            found.append(code)
    return found


def _keywords(prompt: str, *, limit: int = 8) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-']{2,}", prompt.lower())
    out: list[str] = []
    for token in tokens:
        if token in STOPWORDS or token in COUNTRY_ALIASES:
            continue
        if token not in out:
            out.append(token)
        if len(out) >= limit:
            break
    return out


def _subject_terms(prompt: str) -> list[str]:
    """Keywords plus synonym expansions for subject matching."""
    base = _keywords(prompt)
    # Generic catalog words are weak alone — keep them but expand subjects.
    weak = {"courses", "course", "programs", "program", "majors", "major", "degrees", "degree"}
    terms: list[str] = []
    for token in base:
        if token in weak:
            continue
        for syn in SUBJECT_SYNONYMS.get(token, (token,)):
            if syn not in terms:
                terms.append(syn)
    if not terms:
        # Fall back to non-weak keywords if user only said "courses"
        terms = [t for t in base if t not in weak] or base
    return terms


def _is_catalog_intent(prompt: str) -> bool:
    return bool(CATALOG_INTENT.search(prompt or ""))


def _is_people_intent(prompt: str) -> bool:
    return bool(PEOPLE_INTENT.search(prompt or ""))


def _is_count_intent(prompt: str) -> bool:
    return bool(COUNT_INTENT.search(prompt or ""))


def _is_place_intent(prompt: str) -> bool:
    return bool(PLACE_INTENT.search(prompt or ""))


def _is_schedule_intent(prompt: str) -> bool:
    return bool(SCHEDULE_INTENT.search(prompt or ""))


def _is_action_request(prompt: str) -> bool:
    text = prompt or ""
    return bool(MUTATING_ACTION_INTENT.search(text) or ACTION_INTENT.search(text))


def _is_mutating_action_request(prompt: str) -> bool:
    return bool(MUTATING_ACTION_INTENT.search(prompt or ""))


def _is_referential_followup(prompt: str) -> bool:
    return bool(REFERENTIAL_FOLLOWUP.search(prompt or ""))


def _extract_ids_from_text(text: str) -> tuple[list[int], list[int]]:
    lead_ids: list[int] = []
    booking_ids: list[int] = []
    for match in LEAD_ID_RE.finditer(text or ""):
        try:
            lead_ids.append(int(match.group(1)))
        except (TypeError, ValueError):
            continue
    for match in BOOKING_ID_RE.finditer(text or ""):
        try:
            booking_ids.append(int(match.group(1)))
        except (TypeError, ValueError):
            continue
    return lead_ids, booking_ids


def _extract_entity_ids_from_history(
    prior_turns: list[IntelAiChatLog],
) -> tuple[list[int], list[int]]:
    """Pull lead/booking IDs mentioned in earlier turns of this thread."""
    lead_ids: list[int] = []
    booking_ids: list[int] = []

    def _push(dst: list[int], value: Any) -> None:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return
        if n > 0 and n not in dst:
            dst.append(n)

    for turn in prior_turns:
        blob = f"{turn.prompt or ''}\n{turn.response_text or ''}"
        leads, bookings = _extract_ids_from_text(blob)
        for lid in leads:
            _push(lead_ids, lid)
        for bid in bookings:
            _push(booking_ids, bid)

        payload = turn.retrieved_sources if isinstance(turn.retrieved_sources, dict) else {}
        for key in ("sources", "retrieved"):
            for item in payload.get(key) or []:
                if not isinstance(item, dict):
                    continue
                kind = str(item.get("type") or "").lower()
                if kind == "lead":
                    _push(lead_ids, item.get("id") or item.get("lead_id"))
                elif kind in {"booking", "appointment"}:
                    _push(booking_ids, item.get("id"))
                    _push(lead_ids, item.get("lead_id"))
                if item.get("lead_id") is not None:
                    _push(lead_ids, item.get("lead_id"))

    return lead_ids, booking_ids


def _lead_matches_destination(
    *,
    country_text: str,
    destination_iso2: str | None,
    country_names: list[str],
    country_codes: list[str],
) -> bool:
    """True when lead target country matches prompt destination filters."""
    if not country_names and not country_codes:
        return True
    blob = f"{country_text or ''} {destination_iso2 or ''}".lower()
    if any(name.lower() in blob for name in country_names):
        return True
    if destination_iso2:
        dest = destination_iso2.upper()
        iso_set = {c.upper() for c in country_codes}
        if dest in iso_set:
            return True
        if dest == "GB" and "UK" in iso_set:
            return True
    # Alias fragments (e.g. russian → russia)
    for alias, code in COUNTRY_ALIASES.items():
        if code in country_codes and len(alias) >= 4 and alias in blob:
            return True
    return False


def _country_ids_for_prompt(db: Session, prompt: str) -> list[int]:
    codes = _extract_country_codes(prompt)
    if not codes:
        return []
    iso_filter = list(codes)
    if "UK" in codes:
        iso_filter.append("GB")
    return [c.id for c in db.query(Country.id).filter(Country.iso2.in_(iso_filter)).all()]


def _country_name_patterns(prompt: str) -> list[str]:
    """Human country names mentioned in the prompt (for Lead.preferred_country)."""
    lower = prompt.lower()
    names: list[str] = []
    for alias, code in sorted(COUNTRY_ALIASES.items(), key=lambda x: -len(x[0])):
        if len(alias) < 3 and alias not in {"uk", "uae", "usa"}:
            continue
        if re.search(rf"\b{re.escape(alias)}\b", lower):
            # Prefer canonical display from alias map reverse
            display = alias.title() if alias not in {"uk", "uae", "usa"} else alias.upper()
            canon = {
                "CA": "Canada",
                "UK": "United Kingdom",
                "AU": "Australia",
                "DE": "Germany",
                "US": "United States",
                "JP": "Japan",
                "FR": "France",
                "AE": "United Arab Emirates",
                "NZ": "New Zealand",
                "SG": "Singapore",
                "SE": "Sweden",
                "CH": "Switzerland",
                "RU": "Russia",
                "IN": "India",
                "CN": "China",
                "IE": "Ireland",
                "IT": "Italy",
                "ES": "Spain",
                "NL": "Netherlands",
                "MY": "Malaysia",
                "PH": "Philippines",
                "PL": "Poland",
                "HU": "Hungary",
                "GE": "Georgia",
                "KZ": "Kazakhstan",
                "UZ": "Uzbekistan",
                "BD": "Bangladesh",
                "NP": "Nepal",
                "LK": "Sri Lanka",
            }.get(code, display)
            if canon not in names:
                names.append(canon)
            if alias.title() not in names and len(alias) > 2:
                names.append(alias.title())
    return names


def _truncate(text: str | None, limit: int) -> str:
    value = _strip_html(text)
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _score_text(haystack: str, terms: list[str]) -> int:
    text = (haystack or "").lower()
    if not text or not terms:
        return 0
    score = 0
    for term in terms:
        if term in text:
            score += 3 if re.search(rf"\b{re.escape(term)}\b", text) else 1
            if text.startswith(term) or f" {term}" in f" {text}":
                score += 1
    return score


def retrieve_glossary(db: Session, prompt: str, *, limit: int = 8) -> list[dict[str, Any]]:
    countries = _extract_country_codes(prompt)
    keywords = _keywords(prompt)
    subject = _subject_terms(prompt)
    search_words = subject or keywords
    # Always search glossary; keep a smaller slice for pure catalog prompts.
    max_rows = min(3, limit) if _is_catalog_intent(prompt) and not LIVE_HINTS.search(prompt) else limit

    clauses = []
    for word in search_words[:8]:
        pattern = f"%{word}%"
        clauses.append(
            or_(
                IntelGlossary.term_name.ilike(pattern),
                IntelGlossary.short_definition.ilike(pattern),
                IntelGlossary.full_explanation.ilike(pattern),
                IntelGlossary.category.ilike(pattern),
                IntelGlossary.slug.ilike(pattern),
            )
        )
    if not clauses and prompt.strip():
        needle = f"%{prompt.strip()[:120]}%"
        clauses.append(
            or_(
                IntelGlossary.term_name.ilike(needle),
                IntelGlossary.short_definition.ilike(needle),
                IntelGlossary.full_explanation.ilike(needle),
            )
        )

    query = db.query(IntelGlossary).filter(IntelGlossary.status == "ACTIVE")
    if clauses:
        query = query.filter(or_(*clauses))
    if countries:
        # Prefer matching country rows, but do not hard-fail if empty.
        country_rows = (
            query.filter(IntelGlossary.country_code.in_([*countries, "GLOBAL"]))
            .order_by(IntelGlossary.updated_at.desc())
            .limit(max_rows)
            .all()
        )
        rows = country_rows or query.order_by(IntelGlossary.updated_at.desc()).limit(max_rows).all()
    else:
        rows = query.order_by(IntelGlossary.updated_at.desc()).limit(max_rows).all()

    sources: list[dict[str, Any]] = []
    for row in rows:
        sources.append(
            {
                "type": "glossary",
                "id": str(row.id),
                "title": row.term_name,
                "slug": row.slug,
                "country_code": row.country_code,
                "category": row.category,
                "lifecycle_stage": row.lifecycle_stage,
                "short_definition": _strip_html(row.short_definition),
                "full_explanation": _truncate(row.full_explanation, 1200),
                "key_metrics": row.key_metrics,
                "url": row.official_source_url,
            }
        )
    return sources


def retrieve_countries(db: Session, prompt: str, *, limit: int = 6) -> list[dict[str, Any]]:
    codes = _extract_country_codes(prompt)
    names = _country_name_patterns(prompt)
    terms = _subject_terms(prompt) + _keywords(prompt)
    clauses = []
    for code in codes:
        clauses.append(Country.iso2 == code)
        # Intel uses UK; ISO may be GB
        if code == "UK":
            clauses.append(Country.iso2 == "GB")
    for name in names:
        clauses.append(Country.name.ilike(f"%{name}%"))
    for term in terms[:6]:
        if term in COUNTRY_ALIASES or len(term) < 3:
            continue
        clauses.append(Country.name.ilike(f"%{term}%"))
        clauses.append(Country.iso2.ilike(f"%{term}%"))

    if not clauses:
        return []

    rows = (
        db.query(Country)
        .filter(Country.is_active.is_(True), or_(*clauses))
        .order_by(Country.name.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "type": "country",
            "id": str(row.id),
            "title": row.name,
            "code": row.iso2,
            "country_code": row.iso2,
            "summary": f"Country record ({row.iso2})",
            "url": None,
        }
        for row in rows
    ]


def retrieve_states(db: Session, prompt: str, *, limit: int = 8) -> list[dict[str, Any]]:
    from app.models.academia_geography import GeographyState

    country_ids = _country_ids_for_prompt(db, prompt)
    keywords = _keywords(prompt)
    subject = _subject_terms(prompt)
    weak = {
        "states",
        "state",
        "cities",
        "city",
        "province",
        "region",
        "regions",
        "geography",
        "towns",
        "town",
    }
    terms = [t for t in [*subject, *keywords] if t not in weak]
    clauses = []
    for term in terms[:8]:
        pattern = f"%{term}%"
        clauses.append(GeographyState.name.ilike(pattern))
        clauses.append(GeographyState.region_code.ilike(pattern))
    if country_ids:
        clauses.append(GeographyState.country_id.in_(country_ids))

    if not clauses:
        if not _is_place_intent(prompt):
            return []
        rows = (
            db.query(GeographyState)
            .options(joinedload(GeographyState.country))
            .filter(GeographyState.is_active.is_(True))
            .order_by(GeographyState.name.asc())
            .limit(limit)
            .all()
        )
    else:
        rows = (
            db.query(GeographyState)
            .options(joinedload(GeographyState.country))
            .filter(GeographyState.is_active.is_(True), or_(*clauses))
            .order_by(GeographyState.name.asc())
            .limit(max(limit * 2, 12))
            .all()
        )
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        country_name = row.country.name if row.country else None
        country_iso = row.country.iso2 if row.country else None
        blob = f"{row.name} {row.region_code or ''} {country_name or ''} {country_iso or ''}"
        score = _score_text(blob, terms) if terms else 0
        if country_ids and row.country_id in country_ids:
            score += 4
        if score <= 0:
            if country_ids and row.country_id in country_ids:
                score = 2
            elif _is_place_intent(prompt) and not terms:
                score = 1
            else:
                continue
        scored.append(
            (
                score,
                {
                    "type": "state",
                    "id": str(row.id),
                    "title": row.name,
                    "code": row.region_code,
                    "country": country_name,
                    "country_code": country_iso,
                    "summary": f"State/province in {country_name or '—'}"
                    + (f" ({row.region_code})" if row.region_code else ""),
                    "url": None,
                },
            )
        )
    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:limit]]


def retrieve_cities(db: Session, prompt: str, *, limit: int = 8) -> list[dict[str, Any]]:
    from app.models.academia_geography import GeographyCity

    country_ids = _country_ids_for_prompt(db, prompt)
    keywords = _keywords(prompt)
    subject = _subject_terms(prompt)
    weak = {
        "states",
        "state",
        "cities",
        "city",
        "province",
        "region",
        "regions",
        "geography",
        "towns",
        "town",
    }
    terms = [t for t in [*subject, *keywords] if t not in weak]
    clauses = []
    for term in terms[:8]:
        pattern = f"%{term}%"
        clauses.append(GeographyCity.name.ilike(pattern))
        clauses.append(GeographyCity.postal_code_prefix.ilike(pattern))
        clauses.append(GeographyCity.time_zone.ilike(pattern))
    if country_ids:
        clauses.append(GeographyCity.country_id.in_(country_ids))

    if not clauses:
        if not _is_place_intent(prompt):
            return []
        rows = (
            db.query(GeographyCity)
            .options(joinedload(GeographyCity.country), joinedload(GeographyCity.state))
            .filter(GeographyCity.is_active.is_(True))
            .order_by(GeographyCity.name.asc())
            .limit(limit)
            .all()
        )
    else:
        rows = (
            db.query(GeographyCity)
            .options(joinedload(GeographyCity.country), joinedload(GeographyCity.state))
            .filter(GeographyCity.is_active.is_(True), or_(*clauses))
            .order_by(GeographyCity.name.asc())
            .limit(max(limit * 2, 12))
            .all()
        )
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        country_name = row.country.name if row.country else None
        country_iso = row.country.iso2 if row.country else None
        state_name = row.state.name if row.state else None
        blob = f"{row.name} {state_name or ''} {country_name or ''} {country_iso or ''}"
        score = _score_text(blob, terms) if terms else 0
        if country_ids and row.country_id in country_ids:
            score += 4
        if score <= 0:
            if country_ids and row.country_id in country_ids:
                score = 2
            elif _is_place_intent(prompt) and not terms:
                score = 1
            else:
                continue
        scored.append(
            (
                score,
                {
                    "type": "city",
                    "id": str(row.id),
                    "title": row.name,
                    "state": state_name,
                    "country": country_name,
                    "country_code": country_iso,
                    "summary": " · ".join(x for x in [state_name, country_name, row.time_zone] if x),
                    "url": None,
                },
            )
        )
    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:limit]]


def retrieve_schedule(
    db: Session,
    prompt: str,
    *,
    lead_ids: list[int] | None = None,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (bookings, appointments/slots) relevant to the prompt."""
    from datetime import datetime, timedelta

    from app.models.consultation_slot import ConsultationSlot
    from app.models.counselling_booking import CounsellingBooking
    from app.models.lead import Lead

    keywords = _keywords(prompt)
    subject = _subject_terms(prompt)
    weak = {
        "appointments",
        "appointment",
        "bookings",
        "booking",
        "booked",
        "schedule",
        "scheduled",
        "consultation",
        "slots",
        "slot",
        "calendar",
        "meeting",
        "counselling",
        "counseling",
        "session",
        "sessions",
        "completed",
        "completion",
        "status",
        "current",
        "outcome",
        "student",
        "students",
        "lead",
        "leads",
    }
    terms = [t for t in [*subject, *keywords] if t not in weak]
    lead_ids = list(dict.fromkeys(int(x) for x in (lead_ids or []) if x is not None))

    booking_clauses = []
    for term in terms[:8]:
        pattern = f"%{term}%"
        booking_clauses.append(CounsellingBooking.candidate_name.ilike(pattern))
        booking_clauses.append(CounsellingBooking.notes.ilike(pattern))
        booking_clauses.append(CounsellingBooking.wrap_up_notes.ilike(pattern))
        booking_clauses.append(CounsellingBooking.status.ilike(pattern))
        booking_clauses.append(CounsellingBooking.outcome_key.ilike(pattern))

    bookings: list[dict[str, Any]] = []
    want_schedule = bool(
        booking_clauses
        or lead_ids
        or _is_schedule_intent(prompt)
        or _is_people_intent(prompt)
        or _is_referential_followup(prompt)
    )
    if want_schedule:
        query = db.query(CounsellingBooking)
        filters = []
        if booking_clauses:
            filters.append(or_(*booking_clauses))
        if lead_ids:
            filters.append(CounsellingBooking.lead_id.in_(lead_ids))
        # Prefer pinned lead bookings; otherwise open a recent/upcoming window.
        if lead_ids:
            pass
        elif _is_schedule_intent(prompt) or not filters:
            cutoff = datetime.utcnow() - timedelta(days=60)
            horizon = datetime.utcnow() + timedelta(days=120)
            filters.append(
                CounsellingBooking.scheduled_time.between(cutoff, horizon)
            )
        if filters:
            query = query.filter(or_(*filters))
        rows = query.order_by(CounsellingBooking.scheduled_time.desc()).limit(limit).all()
        for row in rows:
            when = row.scheduled_time.isoformat(sep=" ", timespec="minutes") if row.scheduled_time else "—"
            summary = (
                f"Status: {row.status or '—'} · When: {when}"
                + (f" · Lead #{row.lead_id}" if row.lead_id else "")
                + (f" · {_truncate(row.notes, 120)}" if row.notes else "")
            )
            bookings.append(
                {
                    "type": "booking",
                    "id": str(row.id),
                    "title": row.candidate_name,
                    "summary": summary,
                    "status": row.status,
                    "scheduled_time": when,
                    "lead_id": row.lead_id,
                    "url": None,
                }
            )

    appointments: list[dict[str, Any]] = []
    slot_query = (
        db.query(ConsultationSlot, Lead)
        .outerjoin(Lead, Lead.id == ConsultationSlot.lead_id)
        .filter(ConsultationSlot.lead_id.isnot(None))
    )
    slot_filters = []
    if lead_ids:
        slot_filters.append(ConsultationSlot.lead_id.in_(lead_ids))
    if terms:
        slot_filters.append(or_(*[Lead.full_name.ilike(f"%{t}%") for t in terms[:6]]))
    if not lead_ids and (_is_schedule_intent(prompt) or not slot_filters):
        today = datetime.utcnow().date() - timedelta(days=14)
        slot_filters.append(ConsultationSlot.slot_date >= today)
    if slot_filters and (
        lead_ids
        or terms
        or _is_schedule_intent(prompt)
        or _is_people_intent(prompt)
        or _is_referential_followup(prompt)
    ):
        slot_rows = (
            slot_query.filter(or_(*slot_filters))
            .order_by(ConsultationSlot.slot_date.desc(), ConsultationSlot.slot_time.desc())
            .limit(limit)
            .all()
        )
        for slot, lead in slot_rows:
            title = (lead.full_name if lead else None) or f"Lead #{slot.lead_id}"
            when = f"{slot.slot_date.isoformat()} {slot.slot_time}"
            appointments.append(
                {
                    "type": "appointment",
                    "id": str(slot.id),
                    "title": title,
                    "summary": f"Consultation slot · {when}"
                    + (f" · Lead #{slot.lead_id}" if slot.lead_id else ""),
                    "scheduled_time": when,
                    "lead_id": slot.lead_id,
                    "url": None,
                }
            )

    return bookings[:limit], appointments[:limit]


def retrieve_levels(db: Session, prompt: str, *, limit: int = 6) -> list[dict[str, Any]]:
    terms = _subject_terms(prompt) or _keywords(prompt)
    year_hints = re.findall(
        r"\b(1[0-6][\s\-]?year|masters?|bachelors?|phd|diploma|foundation|undergraduate|postgraduate)\b",
        prompt,
        re.I,
    )
    search = list(dict.fromkeys([*terms, *[h.replace("-", " ").strip().lower() for h in year_hints]]))
    if not search:
        return []
    clauses = []
    for term in search:
        pattern = f"%{term}%"
        clauses.append(
            or_(Level.name.ilike(pattern), Level.code.ilike(pattern), Level.description.ilike(pattern))
        )
    rows = (
        db.query(Level)
        .filter(or_(*clauses))
        .order_by(Level.name.asc())
        .limit(limit)
        .all()
    )
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        blob = f"{row.name} {row.code or ''} {row.description or ''}"
        scored.append(
            (
                _score_text(blob, search),
                {
                    "type": "level",
                    "id": str(row.id),
                    "title": row.name,
                    "code": row.code,
                    "summary": _truncate(row.description, 400),
                    "url": None,
                },
            )
        )
    scored.sort(key=lambda x: -x[0])
    return [item for score, item in scored if score > 0][:limit] or [item for _, item in scored[:limit]]


def retrieve_leads(
    db: Session,
    prompt: str,
    *,
    lead_ids: list[int] | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    from app.models.lead import Lead
    from app.models.students_master import StudentsMaster
    from app.services.lead_study_interest import study_interest_profile_fields

    pinned_ids = [int(x) for x in (lead_ids or []) if x is not None]
    # Deduplicate while preserving order.
    pinned_ids = list(dict.fromkeys(pinned_ids))

    subject = _subject_terms(prompt)
    keywords = _keywords(prompt)
    country_names = _country_name_patterns(prompt)
    country_codes = _extract_country_codes(prompt)
    search_terms = list(dict.fromkeys([*subject, *keywords, *[n.lower() for n in country_names]]))
    weak = {
        "students",
        "student",
        "leads",
        "lead",
        "aspiring",
        "candidates",
        "candidate",
        "study",
        "names",
        "name",
        "target",
        "targets",
        "information",
        "info",
        "other",
        "details",
        "session",
        "sessions",
        "completed",
        "completion",
        "status",
        "current",
        "outcome",
        "booking",
        "bookings",
        "appointment",
        "appointments",
        "scheduled",
        "schedule",
    }
    # Drop noise terms entirely — do not fall back to weak-only search.
    search_terms = [t for t in search_terms if t not in weak]
    if (
        not search_terms
        and not country_names
        and not country_codes
        and not pinned_ids
        and not (_is_people_intent(prompt) or _is_count_intent(prompt))
    ):
        return []

    clauses = []
    for term in search_terms[:10]:
        pattern = f"%{term}%"
        clauses.append(Lead.preferred_country.ilike(pattern))
        clauses.append(Lead.academic_summary.ilike(pattern))
        clauses.append(Lead.intake_context.ilike(pattern))
        clauses.append(Lead.full_name.ilike(pattern))
        clauses.append(Lead.current_location.ilike(pattern))
        clauses.append(Lead.budget_tier.ilike(pattern))
        clauses.append(Lead.admission_stage.ilike(pattern))
        clauses.append(cast(Lead.additional_data, String).ilike(pattern))
        clauses.append(Lead.source.ilike(pattern))
    for name in country_names:
        clauses.append(Lead.preferred_country.ilike(f"%{name}%"))
        clauses.append(Lead.intake_context.ilike(f"%{name}%"))
        clauses.append(cast(Lead.additional_data, String).ilike(f"%{name}%"))

    sm_clauses = []
    for code in country_codes:
        sm_clauses.append(StudentsMaster.target_destination_iso2 == code)
        if code == "UK":
            sm_clauses.append(StudentsMaster.target_destination_iso2 == "GB")
    for name in country_names:
        # Catch free-text destination in aspirations JSON
        sm_clauses.append(cast(StudentsMaster.aspirations_data, String).ilike(f"%{name}%"))
    for term in search_terms[:8]:
        pattern = f"%{term}%"
        sm_clauses.extend(
            [
                StudentsMaster.target_course_code.ilike(pattern),
                StudentsMaster.target_program_code.ilike(pattern),
                StudentsMaster.first_name.ilike(pattern),
                StudentsMaster.last_name.ilike(pattern),
                StudentsMaster.middle_name.ilike(pattern),
                StudentsMaster.city.ilike(pattern),
                StudentsMaster.state.ilike(pattern),
                StudentsMaster.major.ilike(pattern),
                StudentsMaster.university.ilike(pattern),
                StudentsMaster.degree_code.ilike(pattern),
                cast(StudentsMaster.aspirations_data, String).ilike(pattern),
            ]
        )

    query = (
        db.query(Lead, StudentsMaster)
        .outerjoin(StudentsMaster, StudentsMaster.lead_id == Lead.id)
        .filter(Lead.archived_at.is_(None))
    )

    # Destination-first filter when the prompt names a country (avoids "many"/"aspiring" noise).
    if country_names or country_codes:
        dest_clauses: list[Any] = []
        for name in country_names:
            dest_clauses.append(Lead.preferred_country.ilike(f"%{name}%"))
            dest_clauses.append(Lead.intake_context.ilike(f"%{name}%"))
            dest_clauses.append(cast(Lead.additional_data, String).ilike(f"%{name}%"))
            # Alias fragments (Russian, etc.)
            for alias, code in COUNTRY_ALIASES.items():
                if code in country_codes and len(alias) >= 4:
                    dest_clauses.append(Lead.preferred_country.ilike(f"%{alias}%"))
                    dest_clauses.append(cast(Lead.additional_data, String).ilike(f"%{alias}%"))
        for code in country_codes:
            dest_clauses.append(StudentsMaster.target_destination_iso2 == code)
            if code == "UK":
                dest_clauses.append(StudentsMaster.target_destination_iso2 == "GB")
        # Keep pinned thread leads even if destination filter would drop them.
        if pinned_ids:
            query = query.filter(or_(or_(*dest_clauses), Lead.id.in_(pinned_ids)))
        else:
            query = query.filter(or_(*dest_clauses))
    else:
        filters = []
        if clauses:
            filters.append(or_(*clauses))
        if sm_clauses:
            filters.append(or_(*sm_clauses))
        if pinned_ids:
            filters.append(Lead.id.in_(pinned_ids))
        if filters:
            query = query.filter(or_(*filters))
        elif not (_is_people_intent(prompt) or _is_count_intent(prompt)):
            return []

    pool_limit = max(80, limit * 6) if (country_names or country_codes) else max(50, limit * 5)
    if pinned_ids:
        pool_limit = max(pool_limit, len(pinned_ids) + limit)
    pool = query.order_by(Lead.updated_at.desc()).limit(pool_limit).all()

    # Guarantee pinned IDs are in the pool even if keyword/destination filters missed them.
    if pinned_ids:
        have = {lead.id for lead, _ in pool}
        missing = [i for i in pinned_ids if i not in have]
        if missing:
            extra = (
                db.query(Lead, StudentsMaster)
                .outerjoin(StudentsMaster, StudentsMaster.lead_id == Lead.id)
                .filter(Lead.archived_at.is_(None), Lead.id.in_(missing))
                .all()
            )
            pool = list(extra) + list(pool)

    scored: list[tuple[int, dict[str, Any]]] = []

    for lead, student in pool:
        interest = resolve_lead_study_interest(lead)
        profile = study_interest_profile_fields(lead)

        sm_destination = (student.target_destination_iso2 if student else None) or interest.get(
            "destination_iso2"
        )
        sm_program_code = (student.target_program_code if student else None) or interest.get(
            "program_code"
        )
        sm_course_code = (student.target_course_code if student else None) or interest.get(
            "course_code"
        )

        country = (
            profile.get("preferred_country")
            or interest.get("country")
            or lead.preferred_country
            or ""
        ) or ""
        course = (profile.get("preferred_course") or interest.get("course") or "") or ""
        program = (profile.get("target_program") or interest.get("program") or "") or ""
        target_degree = interest.get("target_degree") or ""
        target_major = interest.get("target_major") or ""

        student_name = None
        if student:
            parts = [student.first_name, student.middle_name, student.last_name]
            student_name = " ".join(p for p in parts if p).strip() or None
        display_name = student_name or lead.full_name or f"Lead #{lead.id}"

        location_bits = []
        if student and student.city:
            location_bits.append(student.city)
        if student and student.state:
            location_bits.append(student.state)
        if student and student.country_iso2:
            location_bits.append(student.country_iso2)
        if lead.current_location:
            location_bits.append(lead.current_location)
        location = " · ".join(dict.fromkeys(location_bits)) if location_bits else None

        stage = lead.admission_stage or (
            lead.stage.value if hasattr(lead.stage, "value") else str(lead.stage or "")
        )
        channel = lead.channel.value if hasattr(lead.channel, "value") else str(lead.channel or "")
        source = lead.source or None

        blob = " ".join(
            [
                display_name,
                country,
                course,
                program,
                target_degree or "",
                target_major or "",
                sm_destination or "",
                sm_program_code or "",
                sm_course_code or "",
                lead.academic_summary or "",
                location or "",
                stage or "",
                channel or "",
                source or "",
                lead.budget_tier or "",
                str(getattr(lead, "test_scores", "") or ""),
            ]
        ).lower()

        score = _score_text(blob, search_terms)
        if lead.id in pinned_ids:
            score += 20
        for name in country_names:
            if name.lower() in country.lower() or name.lower() in blob:
                score += 5
        for code in country_codes:
            code_l = code.lower()
            if code_l in blob or (sm_destination or "").lower() == code_l:
                score += 4
            if code == "UK" and (sm_destination or "").upper() == "GB":
                score += 4

        country_matched = _lead_matches_destination(
            country_text=country,
            destination_iso2=sm_destination,
            country_names=country_names,
            country_codes=country_codes,
        )
        # When the prompt names a destination, only keep matching leads
        # (pinned thread leads are always kept).
        if (country_names or country_codes) and not country_matched and lead.id not in pinned_ids:
            continue
        if score <= 0:
            if lead.id in pinned_ids:
                score = 10
            elif country_matched:
                score = 3
            elif _is_people_intent(prompt) and not (country_names or country_codes):
                score = 1
            else:
                continue

        summary_parts = [
            f"Name: {display_name}",
            f"Target country: {country or sm_destination or '—'}",
            f"Target program: {program or sm_program_code or '—'}",
            f"Target course: {course or sm_course_code or '—'}",
        ]
        if target_degree:
            summary_parts.append(f"Degree: {target_degree}")
        if target_major:
            summary_parts.append(f"Major: {target_major}")
        if location:
            summary_parts.append(f"Location: {location}")
        if lead.budget_tier:
            summary_parts.append(f"Budget: {lead.budget_tier}")
        summary_parts.append(f"Stage: {stage or '—'}")
        if channel:
            summary_parts.append(f"Channel: {channel}")
        if source:
            summary_parts.append(f"Source: {source}")
        if lead.academic_summary:
            summary_parts.append(f"Academics: {_truncate(lead.academic_summary, 160)}")

        scored.append(
            (
                score,
                {
                    "type": "lead",
                    "id": str(lead.id),
                    "title": display_name,
                    "summary": " · ".join(summary_parts),
                    "name": display_name,
                    "full_name": lead.full_name,
                    "target_country": country or None,
                    "target_destination_iso2": sm_destination or None,
                    "target_program": program or None,
                    "target_program_code": sm_program_code or None,
                    "target_course": course or None,
                    "target_course_code": sm_course_code or None,
                    "target_degree": target_degree or None,
                    "target_major": target_major or None,
                    "location": location,
                    "budget_tier": lead.budget_tier or None,
                    "academic_summary": _truncate(lead.academic_summary, 400) or None,
                    "stage": stage or None,
                    "channel": channel or None,
                    "source": source,
                    "country": country or None,
                    "country_code": sm_destination or None,
                    "course": course or None,
                    "program": program or None,
                    "url": None,
                },
            )
        )

    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:limit]]


def retrieve_academia(db: Session, prompt: str, *, limit: int = 16) -> list[dict[str, Any]]:
    from app.models.education_course import EducationCourse
    from app.models.education_major import EducationMajor
    from app.models.target_course import TargetCourse

    terms = _subject_terms(prompt)
    keywords = _keywords(prompt)
    if not terms and not keywords and not prompt.strip():
        return []

    search_terms = terms or keywords
    patterns = [f"%{t}%" for t in search_terms]
    country_codes = _extract_country_codes(prompt)
    scored: list[tuple[int, dict[str, Any]]] = []

    def add(score: int, item: dict[str, Any]) -> None:
        if score <= 0:
            return
        scored.append((score, item))

    # --- Majors ---
    major_clauses = [
        or_(EducationMajor.label.ilike(p), EducationMajor.code.ilike(p), EducationMajor.description.ilike(p))
        for p in patterns
    ]
    if major_clauses:
        majors = (
            db.query(EducationMajor)
            .filter(EducationMajor.is_active.is_(True), or_(*major_clauses))
            .order_by(EducationMajor.label.asc())
            .limit(10)
            .all()
        )
        for row in majors:
            blob = f"{row.label} {row.code or ''} {row.description or ''}"
            add(
                _score_text(blob, search_terms) + 4,
                {
                    "type": "major",
                    "id": str(row.id),
                    "title": row.label,
                    "code": row.code,
                    "summary": _truncate(row.description, 400) or f"Education major ({row.code})",
                    "url": None,
                },
            )

    major_ids = [int(s[1]["id"]) for s in scored if s[1].get("type") == "major"]

    # --- Education courses ---
    course_clauses = [
        or_(
            EducationCourse.label.ilike(p),
            EducationCourse.code.ilike(p),
            EducationCourse.description.ilike(p),
        )
        for p in patterns
    ]
    course_query = db.query(EducationCourse).options(
        joinedload(EducationCourse.education_major),
        joinedload(EducationCourse.program),
        joinedload(EducationCourse.level),
    ).filter(EducationCourse.is_active.is_(True))
    if course_clauses and major_ids:
        course_query = course_query.filter(
            or_(or_(*course_clauses), EducationCourse.education_major_id.in_(major_ids))
        )
    elif course_clauses:
        course_query = course_query.filter(or_(*course_clauses))
    elif major_ids:
        course_query = course_query.filter(EducationCourse.education_major_id.in_(major_ids))
    else:
        course_query = None

    if course_query is not None:
        courses = course_query.order_by(EducationCourse.label.asc()).limit(14).all()
        for row in courses:
            major_label = row.education_major.label if row.education_major else None
            blob = f"{row.label} {row.code or ''} {row.description or ''} {major_label or ''}"
            bonus = 5 if major_ids and row.education_major_id in major_ids else 0
            add(
                _score_text(blob, search_terms) + bonus + 3,
                {
                    "type": "course",
                    "id": str(row.id),
                    "title": row.label,
                    "code": row.code,
                    "major": major_label,
                    "program": row.program.name if row.program else None,
                    "level": row.level.name if row.level else row.course_level,
                    "summary": _truncate(
                        row.description or (f"Course under {major_label}" if major_label else None),
                        400,
                    ),
                    "url": None,
                },
            )

    # --- Target courses ---
    tc_clauses = [
        or_(TargetCourse.label.ilike(p), TargetCourse.code.ilike(p), TargetCourse.level.ilike(p))
        for p in patterns
    ]
    if tc_clauses:
        target_courses = (
            db.query(TargetCourse)
            .options(joinedload(TargetCourse.qualification_program), joinedload(TargetCourse.education_major))
            .filter(TargetCourse.is_active.is_(True), or_(*tc_clauses))
            .order_by(TargetCourse.label.asc())
            .limit(14)
            .all()
        )
        for row in target_courses:
            major_label = row.education_major.label if row.education_major else None
            prog_name = row.qualification_program.name if row.qualification_program else None
            blob = f"{row.label} {row.code or ''} {row.level or ''} {major_label or ''} {prog_name or ''}"
            add(
                _score_text(blob, search_terms) + 4,
                {
                    "type": "course",
                    "id": f"target-{row.id}",
                    "title": row.label,
                    "code": row.code,
                    "major": major_label,
                    "program": prog_name,
                    "level": row.level,
                    "summary": _truncate(
                        " · ".join(x for x in [row.level, major_label, prog_name] if x),
                        400,
                    ),
                    "url": None,
                },
            )

    # --- Programs ---
    prog_clauses = [
        or_(Program.name.ilike(p), Program.code.ilike(p), Program.description.ilike(p)) for p in patterns
    ]
    if prog_clauses:
        programs = (
            db.query(Program)
            .options(joinedload(Program.level))
            .filter(Program.is_active.is_(True), or_(*prog_clauses))
            .order_by(Program.name.asc())
            .limit(14)
            .all()
        )
        for row in programs:
            blob = f"{row.name} {row.code or ''} {row.description or ''}"
            add(
                _score_text(blob, search_terms) + 3,
                {
                    "type": "program",
                    "id": str(row.id),
                    "title": row.name,
                    "code": row.code,
                    "level": row.level.name if row.level else None,
                    "summary": _truncate(row.description, 400),
                    "url": None,
                },
            )

    # --- Institutions (subject and/or destination country) ---
    inst_query = db.query(Institution).options(joinedload(Institution.country)).filter(
        Institution.is_active.is_(True)
    )
    inst_clauses = []
    if patterns:
        for p in patterns:
            inst_clauses.append(
                or_(
                    Institution.name.ilike(p),
                    Institution.code.ilike(p),
                    Institution.short_description.ilike(p),
                    Institution.long_description.ilike(p),
                )
            )
    country_ids: list[int] = []
    if country_codes:
        iso_filter = list(country_codes)
        if "UK" in country_codes:
            iso_filter.append("GB")
        country_ids = [
            c.id
            for c in db.query(Country.id).filter(Country.iso2.in_(iso_filter)).all()
        ]
        if country_ids:
            inst_clauses.append(Institution.country_id.in_(country_ids))

    if inst_clauses:
        institutions = (
            inst_query.filter(or_(*inst_clauses))
            .order_by(Institution.name.asc())
            .limit(12)
            .all()
        )
        for row in institutions:
            country_name = row.country.name if row.country else None
            country_iso = row.country.iso2 if row.country else None
            blob = (
                f"{row.name} {row.code or ''} {_strip_html(row.short_description)} "
                f"{_strip_html(row.long_description)} {country_name or ''} {country_iso or ''}"
            )
            score = _score_text(blob, search_terms)
            if country_ids and row.country_id in country_ids:
                score += 6
            # Keep country-matched institutions even without subject terms.
            if score <= 0 and country_ids and row.country_id in country_ids:
                score = 4
            # When a destination country is specified, don't pad with unrelated unis.
            if country_ids and row.country_id not in country_ids:
                continue
            if score < 3 and not (country_ids and row.country_id in country_ids):
                continue
            add(
                score,
                {
                    "type": "university",
                    "id": str(row.id),
                    "title": row.name,
                    "code": row.code,
                    "institution_type": row.institution_type,
                    "country": country_name,
                    "country_code": country_iso,
                    "summary": _truncate(row.short_description or row.long_description, 500),
                    "url": row.institution_web_url,
                },
            )

    best: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    for score, item in scored:
        key = (str(item.get("type")), str(item.get("title")).lower())
        prev = best.get(key)
        if not prev or score > prev[0]:
            best[key] = (score, item)

    ranked = sorted(best.values(), key=lambda x: -x[0])
    return [item for _, item in ranked[:limit]]


def _needs_web_fallback(
    prompt: str,
    *,
    glossary_hits: int,
    academia_hits: int,
    lead_hits: int,
    country_hits: int,
    place_hits: int = 0,
    schedule_hits: int = 0,
) -> bool:
    if not settings.INTEL_AI_WEB_SEARCH_ENABLED:
        return False
    internal = (
        glossary_hits
        + academia_hits
        + lead_hits
        + country_hits
        + place_hits
        + schedule_hits
    )
    if internal > 0 and (
        _is_catalog_intent(prompt)
        or _is_people_intent(prompt)
        or _is_place_intent(prompt)
        or _is_schedule_intent(prompt)
    ):
        return False
    if LIVE_HINTS.search(prompt):
        return True
    return internal < 2


async def retrieve_web(prompt: str, *, limit: int = 3) -> list[dict[str, Any]]:
    """Lightweight DuckDuckGo Instant Answer lookup (no API key)."""
    query = prompt.strip()[:200]
    if not query:
        return []

    def _fetch() -> dict[str, Any]:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            response = client.get(url, params=params, headers={"User-Agent": "NexusIntelAI/1.0"})
            response.raise_for_status()
            return response.json()

    try:
        data = await asyncio.to_thread(_fetch)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Intel AI web search failed: %s", exc)
        return []

    sources: list[dict[str, Any]] = []
    abstract = (data.get("AbstractText") or "").strip()
    abstract_url = (data.get("AbstractURL") or "").strip() or None
    heading = (data.get("Heading") or "").strip() or "Web result"
    if abstract:
        sources.append(
            {
                "type": "web",
                "id": None,
                "title": heading,
                "summary": _truncate(abstract, 800),
                "url": abstract_url,
            }
        )

    for topic in (data.get("RelatedTopics") or [])[: limit * 2]:
        if len(sources) >= limit:
            break
        if not isinstance(topic, dict):
            continue
        text = (topic.get("Text") or "").strip()
        first_url = (topic.get("FirstURL") or "").strip() or None
        if not text:
            continue
        sources.append(
            {
                "type": "web",
                "id": None,
                "title": _truncate(text.split(" - ")[0], 120),
                "summary": _truncate(text, 500),
                "url": first_url,
            }
        )
    return sources


def _compact_item(item: dict[str, Any], *, kind: str) -> dict[str, Any]:
    """Keep only high-signal fields to shrink prompt evaluation cost."""
    if kind == "glossary":
        metrics = item.get("key_metrics")
        return {
            "type": "glossary",
            "id": item.get("id"),
            "title": item.get("title") or item.get("term_name"),
            "country_code": item.get("country_code"),
            "short_definition": _truncate(item.get("short_definition"), 220),
            "key_metrics": metrics if isinstance(metrics, dict) else None,
            "url": item.get("url"),
        }
    if kind == "lead":
        return {
            "type": "lead",
            "id": item.get("id"),
            "name": item.get("name") or item.get("title"),
            "target_country": item.get("target_country") or item.get("country"),
            "target_program": item.get("target_program") or item.get("program"),
            "target_course": item.get("target_course") or item.get("course"),
            "stage": item.get("stage"),
            "channel": item.get("channel"),
        }
    if kind in {"course", "program", "major", "level", "university", "country", "state", "city"}:
        return {
            "type": item.get("type") or kind,
            "id": item.get("id"),
            "title": item.get("title"),
            "code": item.get("code") or item.get("country_code"),
            "summary": _truncate(item.get("summary") or item.get("short_definition"), 180),
            "country_code": item.get("country_code"),
            "url": item.get("url"),
        }
    if kind in {"booking", "appointment"}:
        return {
            "type": item.get("type") or kind,
            "id": item.get("id"),
            "title": item.get("title"),
            "summary": _truncate(item.get("summary"), 160),
            "scheduled_time": item.get("scheduled_time"),
            "status": item.get("status"),
        }
    if kind == "web":
        return {
            "type": "web",
            "title": item.get("title"),
            "summary": _truncate(item.get("summary"), 160),
            "url": item.get("url"),
        }
    return {
        "type": item.get("type") or kind,
        "id": item.get("id"),
        "title": item.get("title"),
        "summary": _truncate(item.get("summary"), 160),
    }


def _compact_context_for_llm(
    context: dict[str, Any],
    *,
    max_chars: int,
    prefer_schedule: bool = False,
) -> dict[str, Any]:
    """Build a compact JSON context under max_chars for faster Ollama prompt eval."""
    lead_cap = 6 if prefer_schedule else 24
    limits = {
        "bookings": 8 if prefer_schedule else 6,
        "appointments": 8 if prefer_schedule else 6,
        "leads": lead_cap,
        "courses": 10,
        "programs": 10,
        "majors": 8,
        "levels": 6,
        "institutions": 8,
        "countries": 6,
        "states": 6,
        "cities": 6,
        "glossary": 10,
        "web": 3,
    }
    compact: dict[str, Any] = {}
    for key, limit in limits.items():
        rows = context.get(key) or []
        if not rows:
            continue
        kind = "lead" if key == "leads" else "university" if key == "institutions" else key.rstrip("s")
        if key == "countries":
            kind = "country"
        if key == "cities":
            kind = "city"
        if key == "states":
            kind = "state"
        if key == "bookings":
            kind = "booking"
        if key == "appointments":
            kind = "appointment"
        if key == "glossary":
            kind = "glossary"
        if key == "web":
            kind = "web"
        if key == "majors":
            kind = "major"
        if key == "levels":
            kind = "level"
        if key == "programs":
            kind = "program"
        if key == "courses":
            kind = "course"
        compact[key] = [_compact_item(row, kind=kind) for row in rows[:limit]]

    # Prefer schedule evidence when the question is about sessions/bookings/status.
    if prefer_schedule:
        priority = (
            "bookings",
            "appointments",
            "leads",
            "countries",
            "courses",
            "programs",
            "majors",
            "institutions",
            "states",
            "cities",
            "levels",
            "glossary",
            "web",
        )
        essential_keys = ("bookings", "appointments", "leads", "countries")
    else:
        priority = (
            "leads",
            "countries",
            "bookings",
            "appointments",
            "courses",
            "programs",
            "majors",
            "institutions",
            "states",
            "cities",
            "levels",
            "glossary",
            "web",
        )
        essential_keys = ("leads", "bookings", "appointments", "countries", "courses", "programs")

    encoded = json.dumps(compact, ensure_ascii=False, default=str)
    if len(encoded) <= max_chars:
        return compact

    trimmed = dict(compact)
    for key in reversed(priority):
        if len(json.dumps(trimmed, ensure_ascii=False, default=str)) <= max_chars:
            break
        protected = {"bookings", "appointments"} if prefer_schedule else {"leads", "bookings", "appointments"}
        if key in trimmed and len(trimmed[key]) > 1:
            trimmed[key] = trimmed[key][: max(1, len(trimmed[key]) // 2)]
        elif key in trimmed and key not in protected:
            trimmed.pop(key, None)
    # Final hard slice — never drop bookings/appointments when present.
    encoded = json.dumps(trimmed, ensure_ascii=False, default=str)
    if len(encoded) > max_chars:
        essential = {k: trimmed[k] for k in essential_keys if k in trimmed}
        return essential or trimmed
    return trimmed


def _build_context_payload(
    *,
    glossary: list[dict[str, Any]],
    countries: list[dict[str, Any]],
    states: list[dict[str, Any]],
    cities: list[dict[str, Any]],
    levels: list[dict[str, Any]],
    academia: list[dict[str, Any]],
    leads: list[dict[str, Any]],
    bookings: list[dict[str, Any]],
    appointments: list[dict[str, Any]],
    web: list[dict[str, Any]],
) -> dict[str, Any]:
    programs = [x for x in academia if x.get("type") == "program"]
    majors = [x for x in academia if x.get("type") == "major"]
    courses = [x for x in academia if x.get("type") == "course"]
    institutions = [x for x in academia if x.get("type") == "university"]
    return {
        "glossary": glossary,
        "countries": countries,
        "states": states,
        "cities": cities,
        "levels": levels,
        "programs": programs,
        "majors": majors,
        "courses": courses,
        "institutions": institutions,
        "leads": leads,
        "bookings": bookings,
        "appointments": appointments,
        "web": web,
    }


def _flatten_context(context: dict[str, Any]) -> list[dict[str, Any]]:
    order = (
        "leads",
        "bookings",
        "appointments",
        "courses",
        "programs",
        "majors",
        "levels",
        "institutions",
        "cities",
        "states",
        "countries",
        "glossary",
        "web",
    )
    out: list[dict[str, Any]] = []
    for key in order:
        out.extend(context.get(key) or [])
    return out


def _citation_view(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in sources:
        out.append(
            {
                "type": item.get("type"),
                "title": _strip_html(item.get("title")),
                "url": item.get("url"),
                "id": item.get("id"),
                "slug": item.get("slug"),
                "summary": _strip_html(item.get("short_definition") or item.get("summary")),
                "country_code": item.get("country_code") or item.get("country"),
                "category": item.get("category"),
            }
        )
    return out


async def _call_intel_llm(messages: list[dict[str, str]]) -> str:
    """Dedicated LLM call with longer timeout / token budget for RAG answers."""
    model = settings.INTEL_AI_MODEL or os.getenv("INTEL_AI_MODEL") or "openai:gpt-4o-mini"
    provider, model_id = parse_model_ref(model)
    timeout_seconds = float(
        max(
            int(settings.INTEL_AI_TIMEOUT_SECONDS or 300),
            int(settings.OLLAMA_TIMEOUT_SECONDS or 120),
            180,
        )
    )

    def _openai() -> str:
        api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
        if not api_key:
            return ""
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=timeout_seconds)
        response = client.chat.completions.create(
            model=model_id or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=messages,
            max_tokens=1600,
            temperature=0.1,
            top_p=0.9,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""

    def _groq() -> str:
        api_key = settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY")
        if not api_key:
            return ""
        from groq import Groq

        client = Groq(api_key=api_key, timeout=timeout_seconds)
        response = client.chat.completions.create(
            model=model_id,
            messages=messages,
            max_tokens=1600,
            temperature=0.1,
            top_p=0.9,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""

    def _ollama() -> str:
        configured_base = settings.OLLAMA_BASE_URL or os.getenv(
            "OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"
        )
        native_base = configured_base.rstrip("/").removesuffix("/v1")
        chat_url = f"{native_base}/api/chat"
        keep_alive_raw = settings.INTEL_AI_OLLAMA_KEEP_ALIVE or os.getenv(
            "INTEL_AI_OLLAMA_KEEP_ALIVE", "-1"
        )
        # Ollama accepts int -1 for forever, but string "-1" 400s ("missing unit").
        keep_alive: str | int
        if str(keep_alive_raw).strip() in {"-1", "forever", "infinite"}:
            keep_alive = -1
        else:
            try:
                keep_alive = int(str(keep_alive_raw).strip())
            except ValueError:
                keep_alive = str(keep_alive_raw).strip() or "24h"
        num_predict = int(settings.INTEL_AI_OLLAMA_NUM_PREDICT or 1024)
        num_ctx = int(settings.INTEL_AI_OLLAMA_NUM_CTX or 8192)
        temperature = float(settings.INTEL_AI_OLLAMA_TEMPERATURE or 0.1)
        top_p = float(settings.INTEL_AI_OLLAMA_TOP_P or 0.9)
        payload = {
            "model": model_id,
            # Native role messages enable KV cache reuse of the static system prompt.
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "format": "json",
            "stream": False,
            "keep_alive": keep_alive,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": num_predict,
                "num_ctx": num_ctx,
            },
        }
        http_timeout = httpx.Timeout(
            connect=15.0,
            read=timeout_seconds,
            write=60.0,
            pool=15.0,
        )
        with httpx.Client(timeout=http_timeout) as client:
            response = client.post(chat_url, json=payload)
            if response.is_error:
                # Surface Ollama's body (e.g. invalid keep_alive) in server logs.
                logger.warning(
                    "Intel AI Ollama HTTP %s: %s",
                    response.status_code,
                    (response.text or "")[:500],
                )
            response.raise_for_status()
            data = response.json()
        content = (data.get("message") or {}).get("content") or ""

        # Telemetry: Ollama returns nanosecond durations on /api/chat.
        try:
            total_ns = float(data.get("total_duration") or 0)
            load_ns = float(data.get("load_duration") or 0)
            prompt_ns = float(data.get("prompt_eval_duration") or 0)
            eval_ns = float(data.get("eval_duration") or 0)
            prompt_count = int(data.get("prompt_eval_count") or 0)
            eval_count = int(data.get("eval_count") or 0)
            eval_rate = (eval_count / (eval_ns / 1e9)) if eval_ns > 0 else 0.0
            prompt_rate = (prompt_count / (prompt_ns / 1e9)) if prompt_ns > 0 else 0.0
            logger.info(
                "Intel AI Ollama metrics model=%s keep_alive=%r num_ctx=%s num_predict=%s "
                "total=%.2fs load=%.2fs prompt_eval=%.2fs (%.1f tok/s, %d toks) "
                "gen_eval=%.2fs (%.1f tok/s, %d toks)",
                model_id,
                keep_alive,
                num_ctx,
                num_predict,
                total_ns / 1e9,
                load_ns / 1e9,
                prompt_ns / 1e9,
                prompt_rate,
                prompt_count,
                eval_ns / 1e9,
                eval_rate,
                eval_count,
            )
        except Exception:  # noqa: BLE001
            logger.debug("Intel AI Ollama metrics unavailable", exc_info=True)
        return content

    try:
        if provider == "groq":
            return await asyncio.to_thread(_groq)
        if provider == "ollama":
            return await asyncio.to_thread(_ollama)
        return await asyncio.to_thread(_openai)
    except httpx.TimeoutException as exc:
        logger.warning("Intel AI LLM timed out after %ss: %s", timeout_seconds, exc)
        return ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("Intel AI LLM call failed: %s", exc)
        return ""


def _parse_llm_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def _schedule_status_fallback(
    context: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """Deterministic answer for session/booking/lead status from retrieved rows."""
    leads = context.get("leads") or []
    bookings = context.get("bookings") or []
    appointments = context.get("appointments") or []
    lines: list[str] = [
        "Here is the current status from Nexus counselling records:",
        "",
    ]
    if leads:
        lines.append("### Lead")
        for item in leads[:4]:
            name = item.get("name") or item.get("title") or f"Lead #{item.get('id')}"
            stage = item.get("stage") or "—"
            country = item.get("target_country") or item.get("country") or "—"
            lines.append(
                f"- **{name}** (Lead #{item.get('id')}) — stage: **{stage}**; "
                f"target country: {country}"
            )
        lines.append("")
    if bookings:
        lines.append("### Booking / session")
        for item in bookings[:6]:
            status = (item.get("status") or "—").upper()
            when = item.get("scheduled_time") or "—"
            completed = status in {"COMPLETED", "DONE", "FINISHED", "WRAPPED_UP"}
            lines.append(
                f"- **Booking #{item.get('id')}** — **{item.get('title') or '—'}**"
            )
            lines.append(
                f"  - Status: **{status}**"
                + (" (session completed)" if completed else " (session not completed)")
            )
            lines.append(f"  - Scheduled: {when}")
            if item.get("lead_id"):
                lines.append(f"  - Lead #{item.get('lead_id')}")
            if item.get("summary"):
                lines.append(f"  - {_strip_html(item.get('summary'))}")
        lines.append("")
    if appointments:
        lines.append("### Consultation slot")
        for item in appointments[:4]:
            lines.append(
                f"- **{item.get('title') or 'Slot'}** — {item.get('scheduled_time') or item.get('summary') or '—'}"
                + (f" · Lead #{item.get('lead_id')}" if item.get("lead_id") else "")
            )
        lines.append("")
    lines.append("_Human verification is recommended before advising a student._")
    cited = _citation_view([*leads[:4], *bookings[:6], *appointments[:4]])
    return "\n".join(lines), cited


def _action_request_fallback(
    context: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """Deterministic response for action requests; this chat cannot mutate records."""
    leads = context.get("leads") or []
    bookings = context.get("bookings") or []
    appointments = context.get("appointments") or []
    lines: list[str] = [
        "I cannot schedule, reschedule, cancel, or send WhatsApp/email messages from this chat.",
        "Here is the current stored status in Nexus:",
        "",
    ]
    if bookings:
        lines.append("### Current booking")
        for item in bookings[:4]:
            status = (item.get("status") or "—").upper()
            when = item.get("scheduled_time") or "—"
            lines.append(
                f"- **Booking #{item.get('id')}** — status: **{status}**; scheduled: {when}"
                + (f"; lead #{item.get('lead_id')}" if item.get("lead_id") else "")
            )
        lines.append("")
    if appointments:
        lines.append("### Current consultation slot")
        for item in appointments[:4]:
            lines.append(
                f"- **{item.get('title') or 'Slot'}** — {item.get('scheduled_time') or item.get('summary') or '—'}"
            )
        lines.append("")
    if leads:
        lines.append("### Current lead")
        for item in leads[:3]:
            name = item.get("name") or item.get("title") or f"Lead #{item.get('id')}"
            stage = item.get("stage") or "—"
            lines.append(f"- **{name}** (Lead #{item.get('id')}) — stage: **{stage}**")
        lines.append("")
    lines.append("No new action was executed by this AI chat.")
    cited = _citation_view([*bookings[:4], *appointments[:4], *leads[:3]])
    return "\n".join(lines), cited


def _fallback_response(
    context: dict[str, Any], *, prompt: str = ""
) -> tuple[str, list[dict[str, Any]]]:
    flat = _flatten_context(context)
    leads = context.get("leads") or []
    bookings = context.get("bookings") or []
    appointments = context.get("appointments") or []
    lines: list[str] = []

    if _is_action_request(prompt):
        return _action_request_fallback(context)

    if (_is_schedule_intent(prompt) or _is_referential_followup(prompt)) and (
        bookings or appointments or leads
    ):
        return _schedule_status_fallback(context)

    # Count / people questions: answer directly from leads; skip unrelated buckets.
    if (_is_count_intent(prompt) or _is_people_intent(prompt)) and (
        _extract_country_codes(prompt) or _country_name_patterns(prompt) or leads
    ):
        dest = ", ".join(
            _country_name_patterns(prompt)
            or _extract_country_codes(prompt)
            or ["the requested destination"]
        )
        lines.append(
            f"**{len(leads)}** student lead(s) are aspiring to study in **{dest}**."
        )
        lines.append("")
        if leads:
            lines.append("### Matching leads")
            for item in leads[:20]:
                name = item.get("name") or item.get("title") or "—"
                country = item.get("target_country") or item.get("country") or "—"
                program = item.get("target_program") or item.get("program") or "—"
                course = item.get("target_course") or item.get("course") or "—"
                stage = item.get("stage") or "—"
                lines.append(
                    f"- **{name}** — country: {country}; program: {program}; "
                    f"course: {course}; stage: {stage}"
                )
            lines.append("")
        else:
            lines.append("No matching leads were found for that destination in Nexus.")
            lines.append("")
        lines.append("_Human verification is recommended before advising a student._")
        return "\n".join(lines), _citation_view(leads[:12])

    lines = [
        "I could not reach the language model, so here is a grounded summary from retrieved Nexus records.",
        "",
    ]
    section_labels = [
        ("leads", "Matching leads / students"),
        ("bookings", "Counselling bookings"),
        ("appointments", "Appointments / consultation slots"),
        ("courses", "Courses"),
        ("programs", "Programs"),
        ("majors", "Majors"),
        ("levels", "Levels"),
        ("institutions", "Institutions"),
        ("cities", "Cities"),
        ("states", "States / provinces"),
        ("countries", "Countries"),
        ("glossary", "Glossary"),
        ("web", "External notes (verify manually)"),
    ]
    any_hits = False
    for key, label in section_labels:
        items = context.get(key) or []
        if not items:
            continue
        any_hits = True
        lines.append(f"### {label}")
        for item in items[:6]:
            if key == "glossary":
                lines.append(
                    f"- **{item['title']}** ({item.get('country_code') or '—'}): "
                    f"{_strip_html(item.get('short_definition'))}"
                )
            elif key == "leads":
                name = item.get("name") or item.get("title") or "—"
                lines.append(
                    f"- **{name}** — country: {item.get('target_country') or item.get('country') or '—'}; "
                    f"program: {item.get('target_program') or item.get('program') or '—'}; "
                    f"course: {item.get('target_course') or item.get('course') or '—'}"
                )
            else:
                summary = _strip_html(item.get("summary")) or "—"
                lines.append(f"- **{item['title']}** ({item.get('type') or key}): {summary}")
            if item.get("url"):
                lines.append(f"  - Official: {item['url']}")
        lines.append("")
    if not any_hits:
        lines.append(
            "No matching records were found across leads, catalog, countries, or glossary. "
            "A counselor should verify this topic against official sources."
        )
    else:
        lines.append("_Human verification is recommended before advising a student._")
    sources = _citation_view(flat[:10])
    return "\n".join(lines), sources


def _parse_thread_id(raw: str | None) -> uuid.UUID | None:
    if not raw or not str(raw).strip():
        return None
    try:
        return uuid.UUID(str(raw).strip())
    except (ValueError, TypeError, AttributeError):
        raise ValueError("thread_id must be a valid UUID") from None


def _load_thread_turns(
    db: Session,
    *,
    user_id: int,
    thread_id: uuid.UUID,
    max_turns: int,
) -> list[IntelAiChatLog]:
    """Return the oldest→newest sliding window of prior turns for this user thread."""
    if max_turns <= 0:
        return []
    rows = (
        db.query(IntelAiChatLog)
        .filter(
            IntelAiChatLog.user_id == user_id,
            IntelAiChatLog.thread_id == thread_id,
        )
        .order_by(IntelAiChatLog.created_at.desc())
        .limit(max_turns)
        .all()
    )
    rows.reverse()
    return rows


_REFUSAL_RE = re.compile(
    r"could not find (verified )?information|could not find any information",
    re.I,
)


def _is_refusal_response(text: str | None) -> bool:
    return bool(_REFUSAL_RE.search(text or ""))


_ACTION_CLAIM_RE = re.compile(
    r"\b(i can|i will|scheduled|rescheduled|cancelled|confirmed|sent|message sent|"
    r"whatsapp confirmation message sent|updated to)\b",
    re.I,
)


def _claims_action_taken(text: str | None) -> bool:
    return bool(_ACTION_CLAIM_RE.search(text or ""))


def _prior_turns_for_llm(
    turns: list[IntelAiChatLog],
    *,
    max_turns: int,
    has_fresh_evidence: bool,
) -> list[IntelAiChatLog]:
    """
    Keep a short dialogue window for Ollama, but drop recent identical refusal
    turns when this request already retrieved fresh lead/booking evidence.
    Those refusals otherwise prime the model to refuse again.
    """
    if not turns:
        return []
    filtered = turns
    if has_fresh_evidence:
        filtered = [t for t in turns if not _is_refusal_response(t.response_text)]
        if not filtered:
            filtered = turns
    return filtered[-max_turns:]


def _assert_thread_access(db: Session, *, user_id: int, thread_id: uuid.UUID) -> None:
    """Reject thread_ids that belong to another user (or are unknown spoof attempts)."""
    owner = (
        db.query(IntelAiChatLog.user_id)
        .filter(IntelAiChatLog.thread_id == thread_id)
        .order_by(IntelAiChatLog.created_at.asc())
        .first()
    )
    if owner is not None and int(owner[0]) != int(user_id):
        raise ValueError("thread_id is not accessible")


def _truncate_history_text(text: str, *, limit: int) -> str:
    cleaned = _strip_html(text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)].rstrip() + "…"


def _verified_sources_manifest(compact_context: dict[str, Any], *, max_items: int = 40) -> str:
    """Human-readable source list injected above the user question for grounding."""
    lines: list[str] = []
    for bucket, rows in compact_context.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = (
                row.get("title")
                or row.get("name")
                or row.get("term_name")
                or row.get("code")
                or "—"
            )
            sid = row.get("id")
            kind = row.get("type") or bucket.rstrip("s")
            suffix = f", id={sid}" if sid not in (None, "") else ""
            lines.append(f"- [{kind}] {title}{suffix}")
            if len(lines) >= max_items:
                return "\n".join(lines)
    return "\n".join(lines) if lines else "- (no verified Nexus records retrieved)"


def _build_ollama_messages(
    *,
    prior_turns: list[IntelAiChatLog],
    current_prompt: str,
    compact_context: dict[str, Any],
) -> list[dict[str, str]]:
    """
    Native role messages for KV cache:
      system (stable) → prior user/assistant pairs → current user (+ RAG)
    Sources metadata is injected immediately above the user question.
    """
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in prior_turns:
        user_text = _truncate_history_text(turn.prompt, limit=600)
        assistant_text = _truncate_history_text(turn.response_text, limit=900)
        if user_text:
            messages.append({"role": "user", "content": user_text})
        if assistant_text:
            messages.append({"role": "assistant", "content": assistant_text})

    sources_block = _verified_sources_manifest(compact_context)
    messages.append(
        {
            "role": "user",
            "content": (
                "Verified sources available for this answer (use only these origins):\n"
                f"{sources_block}\n\n"
                f"Question: {current_prompt}\n\n"
                "Context JSON (evidence — answer only from this):\n"
                f"{json.dumps(compact_context, ensure_ascii=False, default=str)}"
            ),
        }
    )
    return messages


async def run_intel_ai_chat(
    db: Session,
    *,
    user_id: int,
    prompt: str,
    thread_id: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    cleaned = (prompt or "").strip()
    if not cleaned:
        raise ValueError("Prompt is required")

    parsed_thread = _parse_thread_id(thread_id)
    if parsed_thread is not None:
        _assert_thread_access(db, user_id=user_id, thread_id=parsed_thread)
        active_thread = parsed_thread
    else:
        active_thread = uuid.uuid4()

    max_turns = max(1, min(int(settings.INTEL_AI_HISTORY_TURNS or 3), 6))
    # Deep lookback for lead/booking IDs (separate from the short Ollama dialogue window).
    entity_lookback = max(max_turns, 40)
    entity_turns = _load_thread_turns(
        db, user_id=user_id, thread_id=active_thread, max_turns=entity_lookback
    )

    # Fallback for clients that still send inline history (no DB thread yet).
    if not entity_turns and history:
        synthetic: list[IntelAiChatLog] = []
        clipped = history[-(entity_lookback * 2) :]
        pending_user: str | None = None
        for turn in clipped:
            role = (turn.get("role") or "").strip().lower()
            content = (turn.get("content") or "").strip()
            if not content:
                continue
            if role == "user":
                pending_user = content
            elif role == "assistant" and pending_user:
                synthetic.append(
                    IntelAiChatLog(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        thread_id=active_thread,
                        prompt=pending_user,
                        response_text=content,
                    )
                )
                pending_user = None
        entity_turns = synthetic[-entity_lookback:]

    history_lead_ids, history_booking_ids = _extract_entity_ids_from_history(entity_turns)
    prompt_lead_ids, prompt_booking_ids = _extract_ids_from_text(cleaned)
    pinned_lead_ids = list(dict.fromkeys([*prompt_lead_ids, *history_lead_ids]))
    # Booking IDs from history help resolve lead_id when text only said "Booking ID 93".
    if history_booking_ids or prompt_booking_ids:
        from app.models.counselling_booking import CounsellingBooking

        booking_lookup_ids = list(dict.fromkeys([*prompt_booking_ids, *history_booking_ids]))
        linked = (
            db.query(CounsellingBooking.lead_id)
            .filter(
                CounsellingBooking.id.in_(booking_lookup_ids),
                CounsellingBooking.lead_id.isnot(None),
            )
            .all()
        )
        for (lid,) in linked:
            if lid and int(lid) not in pinned_lead_ids:
                pinned_lead_ids.append(int(lid))

    referential = _is_referential_followup(cleaned)
    people_focus = (
        _is_people_intent(cleaned)
        or _is_count_intent(cleaned)
        or (referential and bool(pinned_lead_ids))
        or bool(pinned_lead_ids and _is_schedule_intent(cleaned))
    )
    country_focus = bool(_extract_country_codes(cleaned) or _country_name_patterns(cleaned))
    catalog_focus = _is_catalog_intent(cleaned)
    place_focus = _is_place_intent(cleaned)
    schedule_focus = _is_schedule_intent(cleaned) or (
        referential and bool(pinned_lead_ids)
    )
    focused_followup = bool(
        pinned_lead_ids and (schedule_focus or referential or _is_people_intent(cleaned))
    )

    glossary_k = int(settings.INTEL_AI_GLOSSARY_TOP_K or 12)
    academia_k = int(settings.INTEL_AI_ACADEMIA_TOP_K or 18)
    country_k = int(settings.INTEL_AI_COUNTRY_TOP_K or 6)
    place_k = int(settings.INTEL_AI_PLACE_TOP_K or 8)
    level_k = int(settings.INTEL_AI_LEVEL_TOP_K or 6)

    # Intent-scoped retrieval keeps Ollama prompt evaluation small and answers specific.
    if people_focus and country_focus and not catalog_focus and not focused_followup:
        glossary: list[dict[str, Any]] = []
        levels: list[dict[str, Any]] = []
        academia: list[dict[str, Any]] = []
        states: list[dict[str, Any]] = []
        cities: list[dict[str, Any]] = []
        countries = retrieve_countries(db, cleaned, limit=max(3, country_k // 2))
        dest_codes = set(_extract_country_codes(cleaned))
        if dest_codes:
            countries = [
                c
                for c in countries
                if (c.get("code") or c.get("country_code") or "").upper() in dest_codes
                or ((c.get("code") or "").upper() == "GB" and "UK" in dest_codes)
            ] or countries[:1]
        lead_limit = 40 if _is_count_intent(cleaned) else 24
        leads = retrieve_leads(db, cleaned, limit=lead_limit)
        bookings: list[dict[str, Any]] = []
        appointments: list[dict[str, Any]] = []
        web: list[dict[str, Any]] = []
    else:
        glossary = (
            []
            if (people_focus and not catalog_focus)
            else retrieve_glossary(db, cleaned, limit=glossary_k)
        )
        countries = retrieve_countries(db, cleaned, limit=country_k)
        states = (
            retrieve_states(db, cleaned, limit=place_k) if place_focus or country_focus else []
        )
        cities = (
            retrieve_cities(db, cleaned, limit=place_k) if place_focus or country_focus else []
        )
        levels = retrieve_levels(db, cleaned, limit=level_k) if catalog_focus else []
        academia = (
            retrieve_academia(db, cleaned, limit=academia_k)
            if (catalog_focus or not people_focus)
            else []
        )

        # Schedule first when asking about session/booking status so we can pin lead IDs.
        schedule_seed_ids = list(pinned_lead_ids)
        schedule_limit = 10 if schedule_focus or focused_followup else 5
        bookings, appointments = (
            retrieve_schedule(
                db, cleaned, lead_ids=schedule_seed_ids or None, limit=schedule_limit
            )
            if schedule_focus or people_focus or focused_followup
            else ([], [])
        )
        for row in [*bookings, *appointments]:
            lid = row.get("lead_id")
            try:
                n = int(lid) if lid is not None else 0
            except (TypeError, ValueError):
                n = 0
            if n > 0 and n not in pinned_lead_ids:
                pinned_lead_ids.append(n)

        if focused_followup or (schedule_focus and pinned_lead_ids):
            lead_limit = max(4, len(pinned_lead_ids) + 1)
            leads = retrieve_leads(
                db,
                cleaned,
                lead_ids=pinned_lead_ids,
                limit=lead_limit,
            )
            # Re-fetch schedule scoped to the resolved lead set (drops unrelated noise).
            bookings, appointments = retrieve_schedule(
                db, cleaned, lead_ids=pinned_lead_ids, limit=schedule_limit
            )
        else:
            lead_limit = 24 if people_focus else 10
            leads = (
                retrieve_leads(
                    db,
                    cleaned,
                    lead_ids=pinned_lead_ids or None,
                    limit=lead_limit,
                )
                if (people_focus or country_focus or pinned_lead_ids)
                else []
            )
            if schedule_focus or people_focus:
                lead_ids = [int(x["id"]) for x in leads if str(x.get("id") or "").isdigit()]
                for lid in pinned_lead_ids:
                    if lid not in lead_ids:
                        lead_ids.append(lid)
                if lead_ids and not bookings:
                    bookings, appointments = retrieve_schedule(
                        db, cleaned, lead_ids=lead_ids, limit=schedule_limit
                    )
        web = []
        if _needs_web_fallback(
            cleaned,
            glossary_hits=len(glossary),
            academia_hits=len(academia) + len(levels),
            lead_hits=len(leads),
            country_hits=len(countries),
            place_hits=len(states) + len(cities),
            schedule_hits=len(bookings) + len(appointments),
        ):
            web = await retrieve_web(cleaned)

    context = _build_context_payload(
        glossary=glossary,
        countries=countries,
        states=states,
        cities=cities,
        levels=levels,
        academia=academia,
        leads=leads,
        bookings=bookings,
        appointments=appointments,
        web=web,
    )
    retrieved_all = _flatten_context(context)
    max_chars = int(settings.INTEL_AI_CONTEXT_CHARS or 6000)
    prefer_schedule = bool(schedule_focus or focused_followup or bookings or appointments)
    compact_context = _compact_context_for_llm(
        context, max_chars=max_chars, prefer_schedule=prefer_schedule
    )

    has_fresh_evidence = bool(leads or bookings or appointments)
    prior_turns = _prior_turns_for_llm(
        entity_turns,
        max_turns=max_turns,
        has_fresh_evidence=has_fresh_evidence and prefer_schedule,
    )

    # Never ask the LLM to "perform" bookings/WhatsApp — it will invent success.
    if _is_mutating_action_request(cleaned):
        response_text, sources = _action_request_fallback(context)
        log = IntelAiChatLog(
            id=uuid.uuid4(),
            user_id=user_id,
            thread_id=active_thread,
            prompt=cleaned,
            response_text=response_text,
            retrieved_sources={
                "sources": sources,
                "retrieved": _citation_view(retrieved_all),
                "context_counts": {
                    "glossary": len(glossary),
                    "countries": len(countries),
                    "states": len(states),
                    "cities": len(cities),
                    "levels": len(levels),
                    "programs": len(context.get("programs") or []),
                    "majors": len(context.get("majors") or []),
                    "courses": len(context.get("courses") or []),
                    "institutions": len(context.get("institutions") or []),
                    "leads": len(leads),
                    "bookings": len(bookings),
                    "appointments": len(appointments),
                    "web": len(web),
                    "compact_chars": len(
                        json.dumps(compact_context, ensure_ascii=False, default=str)
                    ),
                    "history_turns": len(prior_turns),
                    "pinned_leads": pinned_lead_ids[:12],
                    "entity_lookback_turns": len(entity_turns),
                    "action_blocked": True,
                },
            },
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return {
            "id": str(log.id),
            "thread_id": str(active_thread),
            "response_text": response_text,
            "sources": sources,
            "retrieved_sources": _citation_view(retrieved_all),
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }

    messages = _build_ollama_messages(
        prior_turns=prior_turns,
        current_prompt=cleaned,
        compact_context=compact_context,
    )

    raw = await _call_intel_llm(messages)
    parsed = _parse_llm_json(raw)
    response_text = _sanitize_assistant_text(parsed.get("response_text") or "")
    llm_sources = parsed.get("sources") if isinstance(parsed.get("sources"), list) else []
    action_request = _is_action_request(cleaned)

    if not response_text:
        response_text, sources = _fallback_response(context, prompt=cleaned)
    else:
        sources = []
        for item in llm_sources[:12]:
            if not isinstance(item, dict):
                continue
            sources.append(
                {
                    "type": item.get("type") or "glossary",
                    "title": _strip_html(item.get("title") or item.get("name") or "Source"),
                    "url": item.get("url"),
                    "id": item.get("id"),
                    "slug": item.get("slug"),
                    "summary": _strip_html(item.get("summary")),
                }
            )
        if not sources:
            sources = _citation_view((leads or retrieved_all)[:12])

        # If the model refused despite schedule/lead evidence, answer from records.
        if _is_refusal_response(response_text) and (
            bookings or appointments or (prefer_schedule and leads)
        ):
            response_text, sources = _schedule_status_fallback(context)
        elif action_request and _claims_action_taken(response_text):
            response_text, sources = _action_request_fallback(context)

    log = IntelAiChatLog(
        id=uuid.uuid4(),
        user_id=user_id,
        thread_id=active_thread,
        prompt=cleaned,
        response_text=response_text,
        retrieved_sources={
            "sources": sources,
            "retrieved": _citation_view(retrieved_all),
            "context_counts": {
                "glossary": len(glossary),
                "countries": len(countries),
                "states": len(states),
                "cities": len(cities),
                "levels": len(levels),
                "programs": len(context.get("programs") or []),
                "majors": len(context.get("majors") or []),
                "courses": len(context.get("courses") or []),
                "institutions": len(context.get("institutions") or []),
                "leads": len(leads),
                "bookings": len(bookings),
                "appointments": len(appointments),
                "web": len(web),
                "compact_chars": len(
                    json.dumps(compact_context, ensure_ascii=False, default=str)
                ),
                "history_turns": len(prior_turns),
                "pinned_leads": pinned_lead_ids[:12],
                "entity_lookback_turns": len(entity_turns),
            },
        },
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return {
        "id": str(log.id),
        "thread_id": str(active_thread),
        "response_text": response_text,
        "sources": sources,
        "retrieved_sources": _citation_view(retrieved_all),
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def list_chat_history(
    db: Session,
    *,
    user_id: int,
    limit: int = 30,
    thread_id: str | None = None,
) -> list[dict[str, Any]]:
    query = db.query(IntelAiChatLog).filter(IntelAiChatLog.user_id == user_id)
    parsed_thread = _parse_thread_id(thread_id) if thread_id else None
    if parsed_thread is not None:
        _assert_thread_access(db, user_id=user_id, thread_id=parsed_thread)
        query = query.filter(IntelAiChatLog.thread_id == parsed_thread)
    rows = query.order_by(IntelAiChatLog.created_at.desc()).limit(limit).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        payload = row.retrieved_sources if isinstance(row.retrieved_sources, dict) else {}
        items.append(
            {
                "id": str(row.id),
                "thread_id": str(row.thread_id) if row.thread_id else None,
                "prompt": row.prompt,
                "response_text": row.response_text,
                "sources": payload.get("sources") or [],
                "retrieved_sources": payload.get("retrieved") or [],
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return items


def _thread_title_from_prompt(prompt: str | None) -> str:
    text = _strip_html(prompt or "").strip().replace("\n", " ")
    if not text:
        return "Untitled chat"
    if len(text) <= 72:
        return text
    return text[:71].rstrip() + "…"


def _bucket_for_date(when, *, today) -> tuple[str, str]:
    """Return (key, label) for sidebar date grouping."""
    from datetime import timedelta

    if when is None:
        return "older", "Older"
    day = when.date() if hasattr(when, "date") else when
    if day == today:
        return "today", "Today"
    if day == today - timedelta(days=1):
        return "yesterday", "Yesterday"
    if day >= today - timedelta(days=7):
        return "last_7_days", "Last 7 Days"
    return "older", "Older"


def list_chat_threads(
    db: Session,
    *,
    user_id: int,
    limit: int = 60,
) -> list[dict[str, Any]]:
    """
    Return date-bucketed thread summaries for the sidebar.
    Uses an aggregate query (no N+1) plus one DISTINCT ON for first prompts.
    """
    from datetime import datetime, timezone

    from sqlalchemy import func

    limit = max(1, min(int(limit or 60), 120))
    aggregates = (
        db.query(
            IntelAiChatLog.thread_id.label("thread_id"),
            func.min(IntelAiChatLog.created_at).label("started_at"),
            func.max(IntelAiChatLog.created_at).label("updated_at"),
            func.count(IntelAiChatLog.id).label("turn_count"),
        )
        .filter(
            IntelAiChatLog.user_id == user_id,
            IntelAiChatLog.thread_id.isnot(None),
        )
        .group_by(IntelAiChatLog.thread_id)
        .order_by(func.max(IntelAiChatLog.created_at).desc())
        .limit(limit)
        .all()
    )
    if not aggregates:
        return []

    thread_ids = [row.thread_id for row in aggregates if row.thread_id]
    # First prompt per thread (PostgreSQL DISTINCT ON).
    first_rows = (
        db.query(IntelAiChatLog)
        .filter(
            IntelAiChatLog.user_id == user_id,
            IntelAiChatLog.thread_id.in_(thread_ids),
        )
        .order_by(IntelAiChatLog.thread_id.asc(), IntelAiChatLog.created_at.asc())
        .distinct(IntelAiChatLog.thread_id)
        .all()
    )
    titles = {row.thread_id: _thread_title_from_prompt(row.prompt) for row in first_rows}

    today = datetime.now(timezone.utc).date()
    buckets: dict[str, dict[str, Any]] = {
        "today": {"key": "today", "label": "Today", "threads": []},
        "yesterday": {"key": "yesterday", "label": "Yesterday", "threads": []},
        "last_7_days": {"key": "last_7_days", "label": "Last 7 Days", "threads": []},
        "older": {"key": "older", "label": "Older", "threads": []},
    }

    for row in aggregates:
        tid = row.thread_id
        if tid is None:
            continue
        updated = row.updated_at
        key, _label = _bucket_for_date(updated, today=today)
        buckets[key]["threads"].append(
            {
                "thread_id": str(tid),
                "title": titles.get(tid) or "Untitled chat",
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "updated_at": updated.isoformat() if updated else None,
                "turn_count": int(row.turn_count or 0),
            }
        )

    return [bucket for bucket in buckets.values() if bucket["threads"]]


def get_chat_thread(
    db: Session,
    *,
    user_id: int,
    thread_id: str,
    limit: int = 100,
) -> dict[str, Any]:
    """Return chronological user/assistant messages for one owned thread."""
    parsed = _parse_thread_id(thread_id)
    if parsed is None:
        raise ValueError("thread_id is required")
    _assert_thread_access(db, user_id=user_id, thread_id=parsed)

    rows = (
        db.query(IntelAiChatLog)
        .filter(
            IntelAiChatLog.user_id == user_id,
            IntelAiChatLog.thread_id == parsed,
        )
        .order_by(IntelAiChatLog.created_at.asc())
        .limit(max(1, min(int(limit or 100), 200)))
        .all()
    )
    if not rows:
        raise ValueError("thread not found")

    messages: list[dict[str, Any]] = []
    for row in rows:
        payload = row.retrieved_sources if isinstance(row.retrieved_sources, dict) else {}
        created = row.created_at.isoformat() if row.created_at else None
        messages.append(
            {
                "id": f"{row.id}-u",
                "role": "user",
                "content": row.prompt,
                "sources": [],
                "retrieved_sources": [],
                "created_at": created,
            }
        )
        messages.append(
            {
                "id": str(row.id),
                "role": "assistant",
                "content": row.response_text,
                "sources": payload.get("sources") or [],
                "retrieved_sources": payload.get("retrieved") or [],
                "created_at": created,
            }
        )

    return {
        "thread_id": str(parsed),
        "title": _thread_title_from_prompt(rows[0].prompt),
        "messages": messages,
        "updated_at": rows[-1].created_at.isoformat() if rows[-1].created_at else None,
    }
