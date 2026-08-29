"""Shared helpers for building program major/sub-major suggestion JSON files."""
from __future__ import annotations

import re
from typing import Any

from app.services.program_taxonomy_matcher import intended_mapping_pairs

PLACEHOLDER_MAJORS = {"", "—", "-", "–"}


def fold(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def heuristic_override(title: str) -> tuple[str, str, str] | None:
    """High-confidence title overrides returning (major, sub, category)."""
    t = fold(title)

    if re.match(r"^doctor of philosophy", t) or t in {
        "doctor of philosophy phd",
        "master of philosophy",
    }:
        return ("—", "major-only ambiguous", "research_generic")

    if "group exercise" in t:
        return ("Sport and Exercise Science", "Exercise & Sports Science", "sport")
    if "pacific nutrition" in t or ("nutrition" in t and "proficiency" in t):
        return ("Health Sciences", "Diet and Health", "health_nutrition")
    if "foundation studies" in t:
        return ("Education & Training", "Foundation Studies", "pathway")
    if "university preparation" in t:
        return ("Education & Training", "University Preparation", "pathway")
    if "proficiency student exchange" in t:
        return ("Education & Training", "Proficiency Student Exchange", "pathway")
    if "proficiency postgraduate" in t:
        return ("Education & Training", "Proficiency Postgraduate", "pathway")
    if "proficiency undergraduate" in t:
        return ("Education & Training", "Proficiency Undergraduate", "pathway")
    if "certificate of proficiency" in t or re.search(r"\bproficiency\b", t):
        return ("Education & Training", "Proficiency", "pathway")
    if "advancing university" in t:
        return ("Education & Training", "Advancing University Studies", "pathway")
    if "diploma for graduates" in t:
        return ("Education & Training", "Graduates", "pathway")
    if re.search(r"\bdiploma in university studies\b", t):
        return ("Education & Training", "University Studies", "pathway")

    if "gastronomy" in t:
        return ("Hospitality & Tourism", "Gastronomy", "culinary")
    if "patisserie" in t:
        return ("Agriculture & Food Sciences", "Patisserie", "culinary")
    if re.search(r"\bcookery\b|\bculinary\b", t):
        return ("Hospitality & Tourism", "Certificate II in Cookery", "culinary")

    if "entrepreneur" in t:
        return ("Business & Management", "Entrepreneurship & Innovation", "business")

    if "viticulture" in t or re.search(r"\bwine\b", t):
        return ("Agriculture & Food Sciences", "Viticulture and Oenology", "agriculture")
    if "horticultur" in t or "plant systems" in t:
        return ("Agriculture & Food Sciences", "Horticulture", "agriculture")
    if "forestry" in t or "forest science" in t:
        return ("Agriculture & Food Sciences", "Forestry", "agriculture")
    if "natural resource" in t:
        return ("Agriculture & Food Sciences", "Natural Resources", "agriculture")
    if "resource studies" in t:
        return ("Physical Sciences", "Resource Studies", "environment")
    if "food technology" in t or "food safety" in t:
        return ("Agriculture & Food Sciences", "Agriculture & Food Sciences", "agriculture")
    if "precision agriculture" in t or re.search(r"\bagriculture\b", t):
        if "precision" in t:
            return ("Agriculture & Food Sciences", "Agriculture & Food Sciences", "agriculture")

    if "bioethic" in t:
        return ("Health Sciences", "Bioethics and Health", "health")
    if "audiology" in t:
        return ("Health Sciences", "Audiology", "health")
    if "palliative" in t:
        return ("Health Sciences", "Palliative Care", "health")
    if "radiation therapy" in t:
        return ("Medical Sciences", "Radiation Therapy", "health")
    if "aeromedical" in t:
        return ("Health Sciences", "Paramedicine", "health")
    if "cognitive behaviou" in t or "cognitive behavior" in t:
        return ("Health Sciences", "Cognitive Behaviour Therapy", "health")
    if "primary health" in t:
        return ("Health Sciences", "Primary Health Care", "health")
    if "rural clinical" in t:
        return ("Health Sciences", "Rural Clinical Practice", "health")
    if re.search(r"\brehabilitation\b", t) and "counsell" not in t:
        return ("Health Sciences", "Rehabilitation", "health")
    if "medical technology" in t:
        return ("Medical Sciences", "Biomedical Science", "health")
    if "obstetrics" in t or "gynaecology" in t or "gynecology" in t:
        return ("Health Sciences", "Maternal, Child and Family Health", "health_clinical")

    if "urban resilience" in t:
        return ("Architecture & Planning", "Urban Resilience and Renewal", "planning")
    if "human interface" in t:
        return ("Computer Science", "Human Interface Technology", "computing")
    if "art curator" in t:
        return ("Fine & Visual Arts", "Art Curatorship", "arts")
    if "illustration" in t:
        return ("Social Sciences", "Illustration", "arts")
    if "border and biosecurity" in t or ("biosecurity" in t and "border" in t):
        return ("Social Sciences", "Border and Biosecurity", "security")
    if "land and society" in t or "environment and society" in t:
        return ("Social Sciences", "Land and Society", "environment_society")

    if "fire engineering" in t:
        return ("Architecture & Planning", "Fire Safety & Building Compliance", "engineering")
    if "product design" in t:
        return ("Arts & Design", "Industrial Design", "design")
    if "medical engineering" in t:
        return ("Engineering", "Biomedical Engineering", "engineering")
    if "peace and conflict" in t:
        return ("Social Sciences", "Politics and International Relations", "social")
    if "te reo" in t:
        return ("Languages & Linguistics", "Indigenous Linguistics", "language")
    if "maori studies" in t or "māori studies" in t:
        return ("Languages & Linguistics", "Māori Studies", "indigenous")

    if "teaching primary" in t or re.search(r"\bprimary\b.*\bteach", t):
        return ("Education & Training", "Primary Education", "education")
    if "teaching secondary" in t or re.search(r"\bsecondary\b.*\bteach", t):
        return ("Education & Training", "Secondary Education", "education")
    if "early childhood" in t:
        return ("Education & Training", "Early Childhood Education", "education")
    if "specialist teaching" in t:
        return ("Education & Training", "Professional Teaching & Training Practice", "education")
    if "tertiary teaching" in t or "clinical teaching" in t:
        return ("Education & Training", "Tertiary Education Practice", "education")
    if re.search(r"\bteaching\b|\bteacher\b", t) and "learning" in t:
        return ("Education & Training", "Teacher Education", "education")

    return None


def resolve_from_ids(
    *,
    major_id: int | None,
    sub_id: int | None,
    major_by_id: dict[int, str],
    sub_by_id: dict[int, tuple[int, str]],
) -> tuple[str, str, int | None, int | None, bool, str | None, str]:
    if major_id is None:
        return ("—", "needs manual review", None, None, False, "No major matched.", "unknown")
    major_label = major_by_id.get(major_id, "—")
    if sub_id is None:
        return (
            major_label,
            "major-only",
            major_id,
            None,
            True,
            None,
            "matcher_major_only",
        )
    parent, sub_label = sub_by_id[sub_id]
    if parent != major_id:
        major_label = major_by_id.get(parent, major_label)
        major_id = parent
    return (
        major_label,
        sub_label,
        major_id,
        sub_id,
        True,
        None,
        "matcher",
    )


def resolve_labels(
    *,
    suggested_major: str,
    suggested_sub_major: str,
    major_by_label: dict[str, int],
    sub_by_parent_name: dict[tuple[int, str], int],
    category: str,
) -> tuple[str, str, int | None, int | None, bool, str | None, str]:
    major_label = suggested_major.strip()
    if major_label in PLACEHOLDER_MAJORS:
        return (
            "—",
            suggested_sub_major,
            None,
            None,
            False,
            "No catalog major suggested.",
            category,
        )
    major_id = major_by_label.get(major_label)
    if major_id is None:
        return (
            major_label,
            suggested_sub_major,
            None,
            None,
            False,
            f"Major not found in catalog: {suggested_major}",
            category,
        )
    sub_norm = suggested_sub_major.strip().lower()
    if "ambiguous" in sub_norm or "needs manual review" in sub_norm:
        return (
            major_label,
            suggested_sub_major,
            major_id,
            None,
            False,
            "Sub-major suggestion is ambiguous.",
            category,
        )
    if sub_norm in {"major-only", "major only", "", "—", "-", "–"}:
        return (major_label, "major-only", major_id, None, True, None, category)
    sub_id = sub_by_parent_name.get((major_id, suggested_sub_major.strip()))
    if sub_id is None:
        for (mid, sname), sid in sub_by_parent_name.items():
            if sname == suggested_sub_major.strip():
                return (
                    next(
                        (lab for lab, i in major_by_label.items() if i == mid),
                        major_label,
                    ),
                    sname,
                    mid,
                    sid,
                    True,
                    None,
                    category,
                )
        return (
            major_label,
            suggested_sub_major,
            major_id,
            None,
            False,
            f"Sub-major not found under {suggested_major}: {suggested_sub_major}",
            category,
        )
    return (
        major_label,
        suggested_sub_major.strip(),
        major_id,
        sub_id,
        True,
        None,
        category,
    )


def pick_suggestion(
    title: str,
    *,
    majors,
    catalog,
    major_by_id: dict[int, str],
    sub_by_id: dict[int, tuple[int, str]],
    major_by_label: dict[str, int],
    sub_by_parent_name: dict[tuple[int, str], int],
) -> dict[str, Any]:
    override = heuristic_override(title)
    if override is not None:
        major, sub, category = override
        (
            major_label,
            sub_label,
            major_id,
            sub_id,
            applicable,
            apply_note,
            category,
        ) = resolve_labels(
            suggested_major=major,
            suggested_sub_major=sub,
            major_by_label=major_by_label,
            sub_by_parent_name=sub_by_parent_name,
            category=category,
        )
        return {
            "suggested_major": major_label,
            "suggested_sub_major": sub_label,
            "education_major_id": major_id,
            "education_sub_major_id": sub_id,
            "applicable": applicable,
            "apply_note": apply_note,
            "category": category,
            "source": "heuristic",
        }

    pairs = intended_mapping_pairs(title, majors, catalog)
    if pairs:
        mid, sid = pairs[0]
        (
            major_label,
            sub_label,
            major_id,
            sub_id,
            applicable,
            apply_note,
            category,
        ) = resolve_from_ids(
            major_id=mid,
            sub_id=sid,
            major_by_id=major_by_id,
            sub_by_id=sub_by_id,
        )
        if sid is None:
            return {
                "suggested_major": major_label,
                "suggested_sub_major": "major-only ambiguous",
                "education_major_id": major_id,
                "education_sub_major_id": None,
                "applicable": False,
                "apply_note": "Matcher returned major-only; no confident sub-major.",
                "category": "matcher_major_only",
                "source": "matcher",
            }
        return {
            "suggested_major": major_label,
            "suggested_sub_major": sub_label,
            "education_major_id": major_id,
            "education_sub_major_id": sub_id,
            "applicable": applicable,
            "apply_note": apply_note,
            "category": category,
            "source": "matcher",
        }

    return {
        "suggested_major": "—",
        "suggested_sub_major": "needs manual review",
        "education_major_id": None,
        "education_sub_major_id": None,
        "applicable": False,
        "apply_note": "No suggestion from heuristic or matcher.",
        "category": "unknown",
        "source": "none",
    }


def fetch_institution_programs(cur, institutions: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for uni in institutions:
        iid = int(uni["id"])
        tag = rf"institution_id={iid}([^0-9]|$)"
        cur.execute(
            """
            SELECT
              p.id,
              p.name,
              pem.education_major_id,
              pem.education_sub_major_id
            FROM programs p
            LEFT JOIN program_education_major_mappings pem ON pem.program_id = p.id
            WHERE p.description ~ %s AND COALESCE(p.is_active, true)
            ORDER BY p.name, pem.id
            """,
            (tag,),
        )
        by_program: dict[int, dict] = {}
        for pid, name, mid, sid in cur.fetchall():
            pid = int(pid)
            bucket = by_program.get(pid)
            if bucket is None:
                bucket = {
                    "institution_id": iid,
                    "institution_name": uni["name"],
                    "program_id": pid,
                    "program_title": name,
                    "mappings": [],
                }
                by_program[pid] = bucket
            if mid is not None:
                bucket["mappings"].append(
                    (
                        int(mid),
                        int(sid) if sid is not None else None,
                    )
                )
        for bucket in by_program.values():
            mappings: list[tuple[int, int | None]] = bucket["mappings"]
            current = None
            with_sub = [m for m in mappings if m[1] is not None]
            if with_sub:
                current = with_sub[0]
            elif mappings:
                current = mappings[0]
            rows.append(
                {
                    "institution_id": bucket["institution_id"],
                    "institution_name": bucket["institution_name"],
                    "program_id": bucket["program_id"],
                    "program_title": bucket["program_title"],
                    "current_major_id": current[0] if current else None,
                    "current_sub_major_id": current[1] if current else None,
                    "mapping_keys": set(mappings),
                }
            )
    return rows


def build_suggestion_rows(
    programs: list[dict],
    *,
    majors,
    catalog,
    major_by_id: dict[int, str],
    sub_by_id: dict[int, tuple[int, str]],
    major_by_label: dict[str, int],
    sub_by_parent_name: dict[tuple[int, str], int],
    new_sub_folds: frozenset[str],
    include_upgrades: bool = True,
) -> tuple[list[dict], list[dict]]:
    suggestions: list[dict] = []
    new_sub_examples: list[dict] = []
    catalog_new_ids = {s.id for s in catalog if fold(s.name) in new_sub_folds}

    for prog in programs:
        cur_mid = prog["current_major_id"]
        cur_sid = prog["current_sub_major_id"]
        title = prog["program_title"]

        suggestion = pick_suggestion(
            title,
            majors=majors,
            catalog=catalog,
            major_by_id=major_by_id,
            sub_by_id=sub_by_id,
            major_by_label=major_by_label,
            sub_by_parent_name=sub_by_parent_name,
        )

        sug_mid = suggestion["education_major_id"]
        sug_sid = suggestion["education_sub_major_id"]
        applicable = bool(suggestion["applicable"]) and sug_sid is not None

        if cur_mid is None:
            status = "unmapped"
            include = True
        elif cur_sid is None:
            status = "major_only"
            include = applicable and sug_sid is not None
        else:
            is_upgrade = (
                include_upgrades
                and applicable
                and sug_sid is not None
                and sug_sid != cur_sid
                and (
                    sug_sid in catalog_new_ids
                    or fold(suggestion["suggested_sub_major"]) in new_sub_folds
                )
            )
            if not is_upgrade:
                continue
            status = "upgrade"
            include = True

        if not include:
            continue

        mapping_keys = prog.get("mapping_keys") or set()
        if sug_mid is not None and (sug_mid, sug_sid) in mapping_keys:
            continue
        if sug_sid is not None and any(sid == sug_sid for _mid, sid in mapping_keys):
            continue

        row = {
            "institution_id": prog["institution_id"],
            "institution_name": prog["institution_name"],
            "program_id": prog["program_id"],
            "program_title": title,
            "suggested_major": suggestion["suggested_major"],
            "suggested_sub_major": suggestion["suggested_sub_major"],
            "category": suggestion["category"],
            "status": status,
            "education_major_id": sug_mid,
            "education_sub_major_id": sug_sid,
            "applicable": applicable,
            "apply_note": suggestion["apply_note"],
            "source": suggestion["source"],
            "current_education_major_id": cur_mid,
            "current_education_sub_major_id": cur_sid,
        }
        suggestions.append(row)

        if sug_sid in catalog_new_ids or (
            suggestion["suggested_sub_major"]
            and fold(suggestion["suggested_sub_major"]) in new_sub_folds
        ):
            new_sub_examples.append(
                {
                    "program_title": title,
                    "institution_name": prog["institution_name"],
                    "suggested_major": suggestion["suggested_major"],
                    "suggested_sub_major": suggestion["suggested_sub_major"],
                    "status": status,
                }
            )

    return suggestions, new_sub_examples
