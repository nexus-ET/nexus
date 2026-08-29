"""Shared program-title → education major / sub-major matcher.

Used at scrape enrichment and at import into ``program_education_major_mappings``.
Loads the live ``education_majors`` / ``education_sub_majors`` catalog so new
rows participate without hardcoded ids.

High-confidence only: prefer sub-majors named in the award title.
Generic awards with a single obvious general sub-major get that default
(Bachelor of Business → Management; LLB → Law; Nursing; Education →
Teacher Education; Design → Design Studies; Engineering → General
Engineering). Leave empty for Science / Arts.
Listing/college stream dumps are ignored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable, Sequence

GENERIC_SUB_FOLDS = frozenset(
    {
        "law",
        "management",
        "medicine",
        "nursing",
        "education",
        "marketing",
        "finance",
        "accounting",
        "psychology",
        "architecture",
        "economics",
        "advertising",
        "mba",
        "music",
        "philosophy",
        "religion",
        "sociology",
        "languages",
        "literature",
        "history and archaeology",
        "health sciences",
        "allied health",
        "public health",
        "general design",
        "general engineering",
        "teacher education",
        "business administration",
        "information technology",
        "computer science",
        "software engineering",
        "liberal arts",
        "legal studies",
        "criminology",
        "social work",
        "event management",
        "design studies",
        "visual arts",
        "communication studies",
        "medical science",
        "marine science",
        "counselling and rehabilitation",
        "information and communications technology",
        "humanitarian and development",
        "policing practice and investigations",
        "advanced translation and professional interpreting",
        "urban design and regional planning",
        "real estate and property development",
        "international relations and asian studies",
    }
)

DEGREE_PREFIX = re.compile(
    r"^(?:"
    r"bachelor(?:\s+of)?|"
    r"master(?:\s+of)?|"
    r"associate(?:\s+degree)?(?:\s+(?:in|of))?|"
    r"juris\s+doctor|"
    r"doctor(?:\s+of)?|"
    r"diploma(?:\s+(?:in|of))?|"
    r"graduate\s+(?:certificate|diploma)(?:\s+in)?|"
    r"certificate(?:\s+(?:in|of))?"
    r")\s+",
    re.I,
)
HONOURS_NOISE = re.compile(
    r"\s*\(honours\)|\s+honours\b|"
    r"\s*[–—-]\s*(?:graduate\s+entry|entry\s+to\s+practice|qualifying|international)\b|"
    r"\s*[–—-]\s*choice\s+of\s+units\b",
    re.I,
)
SLASH_SPLIT = re.compile(r"\s*/\s*")
# Trailing institution course codes (e.g. VU ``NBSC``, ``HCOP``). Not MBA/LLM/TESOL.
_INSTITUTION_PROGRAM_CODE = re.compile(r"\s+[A-Z]{4,6}\d?\s*$")
_PROTECTED_TRAILING_FOLDS = frozenset(
    {
        "tesol",
        "mbbs",
        "ncea",
        "llb",
        "llm",
        "mba",
        "dba",
        "mres",
    }
)


def strip_program_code(name: str) -> str:
    raw = (name or "").strip()
    match = _INSTITUTION_PROGRAM_CODE.search(raw)
    if not match:
        return raw
    token = fold(match.group(0))
    if token in _PROTECTED_TRAILING_FOLDS:
        return raw
    return _INSTITUTION_PROGRAM_CODE.sub("", raw).strip()


DEGREE_TOKEN = re.compile(
    r"\b(?:bachelor|master|doctor|diploma|associate|certificate|"
    r"graduate\s+(?:certificate|diploma))\b",
    re.I,
)
# Split combined awards: "Bachelor of Arts / Bachelor of Laws",
# "Bachelor of Arts and Bachelor of Laws". Do not split "Business and Law"
# inside a single award or a faculty name.
NEXT_AWARD_SPLIT = re.compile(
    r"\s+(?:and|&)\s+(?=(?:bachelor|master|doctor|diploma|associate|"
    r"graduate\s+(?:certificate|diploma))\b)"
    r"|,\s*(?=(?:bachelor|master|doctor)\b)",
    re.I,
)

# Stripped award subject → catalog major. "Bachelor of Arts" is Arts & Design
# (product convention), not Humanities & Social Sciences / Liberal Arts.
AWARD_SUBJECT_MAJOR: dict[str, str] = {
    "arts": "Arts & Design",
    "creative arts": "Arts & Design",
    "fine arts": "Arts & Design",
    "visual arts": "Fine & Visual Arts",
    "fine and visual arts": "Fine & Visual Arts",
    "acting": "Arts & Design",
    "animation": "Film & Photography",
    "cinematic arts": "Film & Photography",
    "design": "Arts & Design",
    "industrial design": "Arts & Design",
    "communication": "Humanities",
    "aviation": "Aviation",
    "aviation management": "Aviation",
    "laws": "Law & Legal",
    "law": "Law & Legal",
    "legal studies": "Law & Legal",
    "business": "Business & Management",
    "commerce": "Business & Management",
    "business administration": "Business & Management",
    "business and mba": "Business & Management",
    "mba": "Business & Management",
    "property economics": "Business & Management",
    "property investment": "Business & Management",
    "property investment and development": "Business & Management",
    "financial planning": "Business & Management",
    "financial advice": "Business & Management",
    "applied financial advice": "Business & Management",
    "financial technology": "Business & Management",
    "fintech": "Business & Management",
    "information technology": "Information Technology",
    "information and communications technology": "Information Technology",
    "ict": "Information Technology",
    "computer science": "Computer Science",
    "data science": "Data Science",
    "applied data science": "Data Science",
    "data engineering": "Data Science",
    "cyber security": "Cybersecurity",
    "cybersecurity": "Cybersecurity",
    "science": "Life Sciences",
    "science advanced": "Life Sciences",
    "advanced science": "Life Sciences",
    "environmental science": "Life Sciences",
    "environment": "Life Sciences",
    "biomedical science": "Medical Sciences",
    "forensic science": "Physical Sciences",
    "engineering": "Engineering",
    "advanced engineering": "Engineering",
    "environmental engineering": "Engineering",
    "nursing": "Health Sciences",
    "public health": "Health Sciences",
    "public health informatics": "Health Sciences",
    "phi": "Health Sciences",
    "paramedic science": "Health Sciences",
    "exercise science": "Sport and Exercise Science",
    "clinical physiology": "Medical Sciences",
    "pharmacy": "Pharmacy and Pharmaceutical Sciences",
    "architecture": "Architecture & Planning",
    "architectural design": "Architecture & Planning",
    "built environment": "Architecture & Planning",
    "justice": "Public Policy & Social Work",
    "social work": "Public Policy & Social Work",
    "education": "Education & Training",
    "psychology": "Social Sciences",
    "behavioural science": "Social Sciences",
    "behavioral science": "Social Sciences",
    "international relations": "Social Sciences",
    "political science": "Social Sciences",
    "political science and international relations": "Social Sciences",
    "advanced political science and international relations": "Social Sciences",
    "languages": "Languages & Linguistics",
    "languages and linguistics": "Languages & Linguistics",
    "urban planning": "Architecture & Planning",
    "urban management and planning": "Architecture & Planning",
    "urban management": "Architecture & Planning",
    "planning": "Architecture & Planning",
    "marine science": "Life Sciences",
    "counselling": "Health Sciences",
    "counseling": "Health Sciences",
    "rehabilitation counselling": "Health Sciences",
    "stem foundations": "Life Sciences",
    "catchment hydrology": "Life Sciences",
    "disability studies": "Health Sciences",
    "financial crime investigation and compliance": "Business & Management",
    "financial crime": "Business & Management",
    "global development": "Business & Management",
    "safety leadership": "Education & Training",
    "strategic communication": "Humanities",
    "criminological research studies": "Law & Legal",
    "research studies in science": "Life Sciences",
    "research studies in business": "Business & Management",
    "research studies in engineering": "Engineering",
    "law research studies": "Law & Legal",
    "medical laboratory science": "Medical Sciences",
    "medical science": "Medical Sciences",
    "pharmacology and toxicology": "Pharmacy and Pharmaceutical Sciences",
    "professional engineering": "Engineering",
    "international law": "Law & Legal",
    "international law studies": "Law & Legal",
    "australian migration law and practice": "Law & Legal",
    "business analytics": "Business & Management",
    "creative and professional writing": "Humanities",
    "registered nurse prescribing": "Health Sciences",
    "education and professional studies research": "Education & Training",
    "humanitarian and development studies": "Public Policy & Social Work",
    "humanitarian and development": "Public Policy & Social Work",
    "policing": "Law & Legal",
    "applied policing": "Law & Legal",
    "interpreting and translation": "Languages & Linguistics",
    "translation and tesol": "Languages & Linguistics",
    "international studies": "Social Sciences",
    "art therapy": "Health Sciences",
    "juris doctor": "Law & Legal",
    "construction law": "Law & Legal",
    "agricultural science": "Agriculture & Food Sciences",
    "criminology": "Law & Legal",
    "crime prevention": "Law & Legal",
    "countering violent extremism": "Law & Legal",
    "legal services": "Law & Legal",
    "finance": "Business & Management",
    "applied music": "Arts & Design",
    "screen media": "Film & Photography",
    "digital content creation": "Film & Photography",
    "block teaching": "Education & Training",
    "education studies": "Education & Training",
    "digital learning and teaching": "Education & Training",
    "child and adolescent mental health": "Health Sciences",
    "mental health": "Health Sciences",
    "global health leadership": "Health Sciences",
    "health promotion": "Health Sciences",
    "health science": "Health Sciences",
    "chiropractic science": "Health Sciences",
    "dermal sciences": "Beauty and Wellness",
    "dermal science": "Beauty and Wellness",
    "human nutrition": "Health Sciences",
    "nutritional science": "Life Sciences",
    "dietetics": "Health Sciences",
    "diet and health": "Health Sciences",
    "osteopathy": "Health Sciences",
    "outdoor leadership": "Sport and Exercise Science",
    "outdoor education": "Health Sciences",
    "strength and conditioning": "Sport and Exercise Science",
    "laser safety": "Health Sciences",
    "community development": "Public Policy & Social Work",
    "international community development": "Public Policy & Social Work",
    "youth work": "Public Policy & Social Work",
    "applied research": "Life Sciences",
    "data analytics for sport performance": "Sport and Exercise Science",
    "transport systems": "Engineering",
    "engineering fundamentals": "Engineering",
    "web development and programming": "Computer Science",
    "web development": "Computer Science",
    "interpersonal and organisational skills": "Business & Management",
    "interpersonal and organizational skills": "Business & Management",
    "performance based building and fire codes": "Architecture & Planning",
    "science and the environment": "Life Sciences",
}

GENERIC_SUBJECTS = frozenset(
    {
        "science",
        "science advanced",
        "business",
        "arts",
        "education",
        "engineering",
        "philosophy",
        "laws",
        "law",
        "communication",
        "creative arts",
        "information technology",
        "computer science",
        "nursing",
        "business and mba",
        "business administration",
        "choice of units",
        "esports",
        "mba",
        "built environment",
        "advanced science",
        "advanced engineering",
        "environment",
        "aviation",
        "visual arts",
        "pharmacy",
    }
)

# Folded award subject (no named stream) → catalog sub-major. Only when
# that major still has no title-matched sub. Science/Engineering/Arts omit.
GENERIC_AWARD_DEFAULT_SUB: dict[str, str] = {
    "business": "Management",
    "business management": "Management",
    "commerce": "Management",
    "laws": "Law",
    "law": "Law",
    "llb": "Law",
    "nursing": "Nursing",
    "education": "Teacher Education",
    "information technology": "Information Technology",
    "computer science": "Computer Science",
    "mba": "MBA",
    "business and mba": "MBA",
    "business administration": "Business Administration",
    "public health": "Public Health",
    "architecture": "Architecture",
    "architectural design": "Architecture",
    "social work": "Social Work",
    "justice": "Criminology",
    "aviation": "Flight Operations & Pilot Training",
    "pharmacy": "Pharmaceutical Sciences",
    "cyber security": "Cybersecurity & Information Defense",
    "cybersecurity": "Cybersecurity & Information Defense",
    "information and communications technology": "Information and Communications Technology",
    "ict": "Information and Communications Technology",
    "humanitarian and development studies": "Humanitarian and Development",
    "humanitarian and development": "Humanitarian and Development",
    "policing": "Policing Practice & Investigations",
    "applied policing": "Policing Practice & Investigations",
    "interpreting and translation": "Advanced Translation & Professional Interpreting",
    "translation and tesol": "Advanced Translation & Professional Interpreting",
    "property investment": "Real Estate & Property Development",
    "property investment and development": "Real Estate & Property Development",
    "international studies": "International Relations and Asian Studies",
    "art therapy": "Psychotherapeutic Art Practice",
    "juris doctor": "Law",
    "planning": "Urban Design & Regional Planning",
    "urban management and planning": "Urban Design & Regional Planning",
    "urban management": "Urban Design & Regional Planning",
    "construction law": "Legal Studies",
    "environment": "Environmental & Earth Sciences",
    "environmental science": "Environmental & Earth Sciences",
    "finance": "Finance",
    "criminology": "Criminology",
    "legal services": "Legal Studies",
    "health science": "Health Sciences",
    "health sciences": "Health Sciences",
    "health": "Health Sciences",
    "health practice": "Health Sciences",
    "education studies": "Teacher Education",
    "block teaching": "Block Teaching",
    "exercise science": "Exercise & Sports Science",
    "design": "Design Studies",
    "visual arts": "Visual Arts",
    "engineering": "General Engineering",
    "advanced engineering": "General Engineering",
    "professional engineering": "Professional Engineering",
    "communication": "Communication Studies",
    "communications": "Communication Studies",
    "esports": "Esports Technology",
    "tesol": "Language Teaching & TESOL",
    "biomedical sciences": "Biomedical Science",
    "biomedical science": "Biomedical Science",
    "fire safety engineering": "Fire Safety & Building Compliance",
    "fire safety": "Fire Safety & Building Compliance",
    "educational studies": "Educational Research & Studies",
    "marine biology": "Marine Science",
    "medicine": "Medicine",
    "surgery": "Medicine",
}

# Extra folded aliases keyed by catalog sub-major fold (not ids).
CATALOG_SUB_ALIAS_EXTRAS: dict[str, tuple[str, ...]] = {
    "counselling and rehabilitation": (
        "counselling",
        "counseling",
        "rehabilitation counselling",
        "rehabilitation counseling",
    ),
    "financial crime and compliance": (
        "financial crime",
        "financial crime investigation and compliance",
        "financial crime investigation",
    ),
    "communication and professional writing": (
        "creative and professional writing",
        "professional writing",
        "creative writing",
    ),
    "criminological research studies": ("criminological research",),
    "legal research studies": (
        "law research studies",
        "legal research",
        "research studies in law",
    ),
    "science research": ("research studies in science",),
    "business research": ("research studies in business",),
    "engineering research": ("research studies in engineering",),
    "educational research and studies": (
        "education and professional studies research",
        "educational research",
        "educational studies",
        "education studies",
        "professional studies research",
    ),
    "catchment hydrology": ("catchment science",),
    "strategic communication": ("strategic communications",),
    "global development": ("international development",),
    "registered nurse prescribing": ("nurse prescribing",),
    "pharmacology and toxicology": ("pharmacology",),
    "medical laboratory science": ("medical laboratory",),
    "australian migration law and practice": ("migration law", "migration law and practice"),
    "information and communications technology": (
        "ict",
        "information and communications technology ict",
        "information communications technology",
    ),
    "humanitarian and development": (
        "humanitarian and development studies",
        "humanitarian studies",
        "humanitarian development",
        "international community development",
    ),
    "policing practice and investigations": (
        "policing",
        "applied policing",
        "policing practice",
        "policing investigations",
    ),
    "advanced translation and professional interpreting": (
        "interpreting and translation",
        "translation and interpreting",
        "interpreting",
        "translation",
        "professional interpreting",
        "translation and tesol",
    ),
    "real estate and property development": (
        "property investment",
        "property investment and development",
        "property development",
    ),
    "international relations and asian studies": (
        "international studies",
        "asian studies",
    ),
    "urban design and regional planning": (
        "urban and regional planning",
        "urban planning",
        "regional planning",
        "urban management and planning",
        "urban management",
        "planning",
    ),
    "psychotherapeutic art practice": ("art therapy", "arts therapy"),
    "child and adolescent mental health": ("child adolescent mental health",),
    "sports data analytics": (
        "data analytics for sport performance",
        "sport performance analytics",
        "sports analytics",
    ),
    "fire safety and building compliance": (
        "performance based building and fire codes",
        "building and fire codes",
        "fire codes",
        "fire safety engineering",
        "fire safety",
    ),
    "language teaching and tesol": ("tesol", "language teaching"),
    "esports technology": ("esports", "e sports"),
    "biomedical science": ("biomedical sciences",),
    "marine science": ("marine biology",),
    "communication studies": ("communications",),
    "medicine": ("surgery", "mbbs"),
    "theology": ("theological studies", "theological"),
    "christian studies": (
        "christian leadership",
        "christian",
    ),
    "health leadership and management": (
        "global health leadership",
        "health leadership",
    ),
    "dermal science": ("dermal sciences",),
    "health sciences": ("health science",),
    "digital learning": ("digital learning and teaching",),
    "educational technology": ("digital learning and teaching",),
    "web development": ("web development and programming",),
    "community services": (
        "community development",
        "youth work",
        "youth work and criminal justice",
    ),
    "interpersonal and organisational skills": (
        "interpersonal and organizational skills",
    ),
    "horticulture": (
        "horticultural",
        "horticultural science",
        "horticultural management",
        "horticultural business",
        "plant and horticultural",
        "plant systems",
    ),
    "gastronomy": ("culinary arts", "culinary", "food studies"),
    "patisserie": ("pastry", "patisserie and baking"),
    "certificate ii in cookery": (
        "cookery",
        "commercial cookery",
        "culinary arts",
        "culinary",
    ),
    "natural resources": (
        "natural resource",
        "natural resources management",
    ),
    "resource studies": ("resources studies",),
    "forestry": ("forest science", "forest management"),
    "bioethics and health": ("bioethics", "bioethics and health law"),
    "urban resilience and renewal": ("urban resilience",),
    "human interface technology": ("human interface", "hit lab"),
    "art curatorship": ("art curator", "curatorship", "curatorial"),
    "cognitive behaviour therapy": (
        "cognitive behavior therapy",
        "cognitive behavioural therapy",
        "cognitive behavioral therapy",
        "cbt",
    ),
    "primary health care": ("primary healthcare", "primary health"),
    "rural clinical practice": ("rural clinical",),
    "entrepreneurship and innovation": (
        "entrepreneurship",
        "entrepreneur",
        "innovation and entrepreneurship",
    ),
    "advancing university studies": ("advancing university", "diploma in advancing"),
    "foundation studies": ("foundation study", "certificate in foundation"),
    "university preparation": ("university prep", "certificate of university preparation"),
    "proficiency undergraduate": ("proficiency undergraduate",),
    "proficiency postgraduate": ("proficiency postgraduate",),
    "proficiency student exchange": ("proficiency student exchange",),
}

# (regex on full program title, preferred catalog sub-major labels in priority order)
TITLE_SUB_MAJOR_HINTS: list[tuple[str, tuple[str, ...]]] = [
    # NZ / newly added catalog subs — keep early so they beat generic Science/Arts matches
    (r"\bhorticultur", ("Horticulture",)),
    (r"\bgastronom", ("Gastronomy",)),
    (r"\bpatisserie\b", ("Patisserie",)),
    (
        r"\bcookery\b|\bculinary\s+arts\b|\bculinary\b",
        ("Certificate II in Cookery", "Gastronomy"),
    ),
    (r"\bforestry\b|\bforest\s+science\b", ("Forestry",)),
    (r"\bnatural\s+resources?\b", ("Natural Resources",)),
    (r"\bresource\s+studies\b", ("Resource Studies", "Natural Resources")),
    (r"\bentrepreneur", ("Entrepreneurship & Innovation",)),
    (r"\bbioethic", ("Bioethics and Health",)),
    (r"\baudiology\b", ("Audiology",)),
    (r"\bpalliative\b", ("Palliative Care",)),
    (r"\bradiation\s+therapy\b", ("Radiation Therapy",)),
    (r"\burban\s+resilience\b", ("Urban Resilience and Renewal",)),
    (r"\bhuman\s+interface\b", ("Human Interface Technology",)),
    (r"\bart\s+curator", ("Art Curatorship",)),
    (
        r"\bcognitive\s+behaviou?r(?:al)?\s+therap|\bcognitive\s+behaviou?r\b",
        ("Cognitive Behaviour Therapy",),
    ),
    (r"\bprimary\s+health\b", ("Primary Health Care",)),
    (r"\brural\s+clinical\b", ("Rural Clinical Practice",)),
    (r"\baeromedical\b", ("Paramedicine",)),
    (
        r"\bfood\s+technology\b|\bfood\s+safety\b|\bfood\s+science\b",
        ("Agriculture & Food Sciences",),
    ),
    (r"\bprecision\s+agriculture\b", ("Agriculture & Food Sciences",)),
    (r"\bproduct\s+design\b", ("Industrial Design", "General Design")),
    (
        r"\bmedical\s+engineering\b|\bmedical\s+technology\b",
        ("Biomedical Engineering", "Biomedical Science"),
    ),
    (
        r"\bfire\s+engineering\b",
        ("Fire Safety & Building Compliance", "Energy & Environmental Engineering"),
    ),
    (
        r"\bchild\s+and\s+adolescent\s+mental\s+health\b",
        ("Child and Adolescent Mental Health",),
    ),
    (r"\bmental\s+health\b", ("Mental Health",)),
    (r"\bhealth\s+promotion\b", ("Health Promotion",)),
    (
        r"\bglobal\s+health\s+leadership\b|\bhealth\s+leadership\b",
        ("Health Leadership & Management", "Global Health"),
    ),
    (r"\bstrength\s+and\s+conditioning\b", ("Strength & Conditioning",)),
    (r"\bosteopath", ("Osteopathy",)),
    (r"\bchiropractic\b", ("Chiropractic Science",)),
    (r"\bdermal\s+science", ("Dermal Science",)),
    (r"\bhuman\s+nutrition\b", ("Human Nutrition",)),
    (r"\bnutritional\s+science\b", ("Nutritional Science",)),
    (r"\bdietetics\b", ("Dietetics",)),
    (r"\bdiet\s+and\s+health\b", ("Diet and Health",)),
    (r"\boutdoor\s+leadership\b", ("Outdoor Leadership",)),
    (r"\boutdoor\s+education\b", ("Outdoor Education",)),
    (r"\blaser\s+safety\b", ("Laser Safety",)),
    (r"\bapplied\s+music\b", ("Applied Music",)),
    (r"\bscreen\s+media\b", ("Screen Media",)),
    (
        r"\bdigital\s+content\s+creation\b",
        ("Digital Storytelling", "Visual Media Content", "Screen Media"),
    ),
    (r"\bblock\s+teaching\b", ("Block Teaching",)),
    (
        r"\beducation\s*\(\s*primary",
        ("Primary Education",),
    ),
    (
        r"\bdigital\s+learning\b",
        ("Educational Technology", "Digital Learning"),
    ),
    (
        r"\bdata\s+analytics\s+for\s+sport|\bsport(?:s)?\s+data\s+analytics\b",
        ("Sports Data Analytics",),
    ),
    (r"\btransport\s+systems\b", ("Transport Systems",)),
    (
        r"\bfire\s+codes\b|\bbuilding\s+(?:and\s+)?fire\b|\bperformance[- ]based\s+building\b",
        ("Fire Safety & Building Compliance",),
    ),
    (
        r"\binternational\s+community\s+development\b",
        ("Humanitarian and Development",),
    ),
    (
        r"\bcommunity\s+development\b|\byouth\s+work\b",
        ("Community Services",),
    ),
    (r"\bcrime\s+prevention\b", ("Criminology",)),
    (r"\bengineering\s+\bfundamentals\b", ("Engineering Fundamentals",)),
    (r"\bweb\s+development\b", ("Web Development",)),
    (
        r"\binterpersonal\s+and\s+organis(?:ation|zation)al\s+skills\b",
        ("Interpersonal and Organisational Skills",),
    ),
    (
        r"\bscience\s+and\s+the\s+environment\b",
        ("Environmental & Earth Sciences",),
    ),
    (
        r"\binformation\s+and\s+communications\s+technology\b|\bict\b",
        ("Information and Communications Technology",),
    ),
    (
        r"\bhumanitarian\s+and\s+development\b",
        ("Humanitarian and Development",),
    ),
    (r"\bpolicing\b", ("Policing Practice & Investigations",)),
    (
        r"\binterpreting\b|\btranslation\b",
        ("Advanced Translation & Professional Interpreting",),
    ),
    (
        r"\bproperty\s+investment\b|\bproperty\s+development\b",
        ("Real Estate & Property Development",),
    ),
    (r"\binternational\s+studies\b", ("International Relations and Asian Studies",)),
    (r"\bart\s+therapy\b|\barts\s+therapy\b", ("Psychotherapeutic Art Practice",)),
    (
        r"\burban\s+management\b|\bmaster\s+of\s+planning\b",
        ("Urban Design & Regional Planning",),
    ),
    (r"\bjuris\s+doctor\b|\b\(jd\)\b", ("Law",)),
    (r"\bconstruction\s+law\b", ("Legal Studies",)),
    (r"\bagricultural\s+science\b", ("Agriculture & Food Sciences",)),
    (r"\bfood\s+science\b", ("Agriculture & Food Sciences",)),
    (r"\banimal\s+science\b|\bzoology\b", ("Biology & Life Sciences",)),
    (r"\bscience\s+\(\s*biology\s*\)|\(biology\)", ("Biology & Life Sciences",)),
    (r"\bphysical\s+education\b", ("Teacher Education",)),
    (r"\bpsychological\b", ("Psychology",)),
    (r"\brehabilitation\s+counsell", ("Counselling & Rehabilitation",)),
    (
        r"(?:bachelor|master|graduate\s+certificate|graduate\s+diploma|diploma)"
        r"\s+(?:of|in)\s+counsell",
        ("Counselling & Rehabilitation",),
    ),
    (r"\bmarine\s+science\b", ("Marine Science",)),
    (r"\bstem\s+foundations\b", ("STEM Foundations",)),
    (r"\bcatchment\s+hydrology\b|\bcatchment\s+science\b", ("Catchment Hydrology",)),
    (r"\bdisability\s+studies\b", ("Disability Studies",)),
    (r"\bfinancial\s+crime\b", ("Financial Crime & Compliance",)),
    (r"\bglobal\s+development\b", ("Global Development",)),
    (r"\bsafety\s+leadership\b", ("Safety Leadership",)),
    (r"\bstrategic\s+communication\b", ("Strategic Communication",)),
    (r"\bcriminological\s+research\b", ("Criminological Research Studies",)),
    (r"\bresearch\s+studies\s+in\s+science\b", ("Science Research",)),
    (r"\bresearch\s+studies\s+in\s+business\b", ("Business Research",)),
    (r"\bresearch\s+studies\s+in\s+engineering\b", ("Engineering Research",)),
    (
        r"\blaw\s+research\s+studies\b|\blegal\s+research\b",
        ("Legal Research Studies",),
    ),
    (
        r"\bcreative\s+and\s+professional\s+writing\b|\bprofessional\s+writing\b",
        ("Communication & Professional Writing",),
    ),
    (
        r"\bregistered\s+nurse\s+prescribing\b|\bnurse\s+prescribing\b",
        ("Registered Nurse Prescribing",),
    ),
    (r"\bmedical\s+laboratory\s+science\b", ("Medical Laboratory Science",)),
    (r"\bmedical\s+science\b", ("Medical Science",)),
    (r"\bpharmacology\b", ("Pharmacology & Toxicology",)),
    (r"\bprofessional\s+engineering\b", ("Professional Engineering",)),
    (r"\binternational\s+law\b", ("International Law",)),
    (r"\bmigration\s+law\b", ("Legal Studies",)),
    (r"\bbusiness\s+analytics\b", ("Business Analytics",)),
    (r"\bvisual\s+arts\b", ("Visual Arts",)),
    (
        r"\beducation\s+and\s+professional\s+studies\s+research\b|"
        r"\beducational\s+research\b",
        ("Educational Research & Studies",),
    ),
    (
        r"(?:bachelor|master|graduate\s+certificate|graduate\s+diploma|diploma|certificate)"
        r"\s+(?:of|in)\s+communication\b",
        ("Communication Studies",),
    ),
    (r"\bacting\b", ("Theatre & Dance",)),
    (r"\btheatre\b|\bdance\b", ("Theatre & Dance",)),
    (r"\banimation\b", ("Animation & Digital Media",)),
    (r"\bcinematic\b|\bfilm\b|\bphotography\b", ("Film, Photography & Media Production",)),
    (r"\baviation\s+management\b", ("Aviation Management",)),
    (r"\bairworthiness\b|\baviation\s+safety\b", ("Aviation Safety & Airworthiness",)),
    (
        r"\bpilot\b|\bflight\s+operations\b|\bbachelor\s+of\s+aviation\b",
        ("Flight Operations & Pilot Training",),
    ),
    (r"\bethical\s+hacking\b", ("Cybersecurity & Ethical Hacking",)),
    (
        r"\bcyber\s*security\b|\bcybersecurity\b",
        ("Cybersecurity & Information Defense", "Cybersecurity & Ethical Hacking"),
    ),
    (r"\bfinancial\s+technolog|\bfintech\b", ("Financial Technology (FinTech)",)),
    (
        r"\bfinancial\s+planning\b|\bfinancial\s+advice\b",
        ("Financial Planning & Advice",),
    ),
    (
        r"\benvironmental\s+science\b|"
        r"\bclimate\s+change\b|\bmaster\s+of\s+environment\b|"
        r"\bintegrated\s+water\b",
        ("Environmental & Earth Sciences",),
    ),
    (
        r"\benvironmental\s+engineering\b|\brenewable\s+energy\b",
        ("Energy & Environmental Engineering",),
    ),
    (r"\bclinical\s+exercise\b", ("Clinical Exercise Physiology",)),
    (
        r"\bexercise\s+science\b|\bsport(?:s)?\s+science\b|\bsport\s+development\b",
        ("Exercise & Sports Science",),
    ),
    (r"\bclinical\s+physiology\b", ("Clinical Physiology",)),
    (r"\bforensic\s+mental\s+health\b", ("Forensic Mental Health",)),
    (r"\bsuicidolog|\bsuicide\s+prevention\b", ("Mental Health & Suicide Prevention",)),
    (r"\bmental\s+health\s+practice\b", ("Mental Health Practice",)),
    (r"\bautism\b|\bneurodivers", ("Autism & Neurodiversity Studies",)),
    (
        r"\bbehaviou?r(?:al)?\s+analysis\b|\bapplied\s+behaviou?r",
        ("Behaviour Analysis",),
    ),
    (r"\binfection\s+(?:prevention|control)\b", ("Infection Control & Public Health",)),
    (
        r"\bhealth\s+(?:and\s+medical\s+)?research\b|\bhealth\s+research\b",
        ("Health Research Methods",),
    ),
    (r"\bprimary\s+maternity\b|\bmidwif", ("Midwifery & Maternity Care",)),
    (r"\bindustrial\s+design\b", ("Industrial Design",)),
    (r"\bhuman\s+services\b", ("Community Services",)),
    (r"\bpublic\s+policy\b|\bpolicy\s+analysis\b", ("Public Policy & Administration",)),
    (
        r"\binternational\s+relations\b|\bpolitical\s+science\b",
        ("Politics and International Relations",),
    ),
    (r"\bprimary\s+teaching\b", ("Primary Education",)),
    (r"\bsecondary\s+teaching\b", ("Teacher Education",)),
    (r"\bspecial\s+education\b", ("Teacher Education",)),
        (r"\burban\s+and\s+environmental\s+planning\b", ("Urban Design & Regional Planning",)),
    (
        r"\bcrime\s+scene\b|\bforensic\s+fingerprint\b|\bforensic\s+science\b",
        ("Forensic Science",),
    ),
    (r"\bpharmacy\b", ("Pharmaceutical Sciences", "Clinical Pharmacy")),
    (r"\btourism\b|\bhotel\s+management\b|\bhospitality\b", ("Hospitality Management",)),
    (r"\benvironmental\s+health\b", ("Environmental Health",)),
    (
        r"\boccupational\s+health(\s+and|\s+\&)?\s+safety\b",
        ("Occupational Health & Safety", "Occupational Health and Safety"),
    ),
    (r"\bpodiatr", ("Podiatry",)),
    (r"\bdiagnostic\s+genomic", ("Diagnostic Genomics",)),
    (r"\bdigital\s+communication\b", ("Media & Journalism", "Media")),
    (r"\bclinical\s+psychology\b", ("Psychology",)),
    (r"\bnurse\s+practitioner\b", ("Nursing",)),
    (r"\bnursing\b", ("Nursing",)),
    (r"\bparamedic", ("Paramedicine",)),
    (r"\bprofessional\s+accounting\b", ("Accounting",)),
    (r"\bproject\s+management\b", ("Project Management",)),
    (r"\binformation\s+technology\b", ("Information Technology",)),
    (r"\bcomputer\s+science\b", ("Computer Science",)),
    (r"\bdata\s+science\b", ("Data Science & Analytics", "Data Science")),
    (r"\bdata\s+engineering\b", ("Data Science & Analytics",)),
    (
        r"\bmachine\s+learning\b",
        ("Machine Learning & Deep Learning", "Artificial Intelligence"),
    ),
    (
        r"\bartificial\s+intelligence\b|\brobotics\b",
        ("Artificial Intelligence",),
    ),
    (
        r"\bbiomedical\s+(?:systems|engineering|technology)\b",
        ("Biomedical Engineering",),
    ),
    (r"\bbiomedical\s+sciences?\b", ("Biomedical Science", "Biotechnology")),
    (r"\bearly\s+childhood\b", ("Early Childhood Education",)),
    (r"\beducational\s+leadership\b", ("Educational Administration",)),
    (
        r"\btesol\b|teaching\s+english\s+to\s+speakers",
        ("Language Teaching & TESOL", "Teacher Education"),
    ),
    (
        r"\bmaster\s+of\s+teaching\b|\bteaching\s*\(\s+secondary\s*\)",
        ("Teacher Education",),
    ),
    (
        r"\binclusive\s+education\b|\bstem\s+in\s+education\b|"
        r"\btrauma[- ]aware\s+education\b|"
        r"\bschool\s+guidance\s+and\s+counselling\b|"
        r"\bindigenous\s+australian\s+education\b|"
        r"\baboriginal\s+and\s+torres\s+strait\b",
        ("Teacher Education",),
    ),
    (r"\bsocial\s+work\b", ("Social Work",)),
    (r"\bproperty\s+economics\b|\breal\s+estate\b", ("Real Estate Management",)),
    (r"\bstrategic\s+design\b", ("General Design",)),
    (r"\binterior\s+design\b", ("Interior Design",)),
    (r"\burban\s+(?:and\s+)?regional\s+planning\b", ("Urban Design & Regional Planning",)),
    (r"\barchitectural\s+design\b|\barchitecture\b", ("Architecture",)),
    (r"\bpsychological\s+science\b|\bpsychology\b", ("Psychology",)),
    (r"\burban\s+planning\b", ("Urban Design & Regional Planning",)),
    (r"\bdental\b|\bdentistry\b", ("Dental Science & Dentistry",)),
    (r"\bindigenous\s+(?:art|studio)\b", ("Indigenous Studio Art",)),
    (r"\blanguages?\b|\blinguistic", ("Languages",)),
    (r"\bclinical\s+leadership\b", ("Clinical Leadership & Management",)),
    (r"\bsecondary\s+education\b", ("Teacher Education",)),
    (r"\boccupational\s+therapy\b", ("Occupational Therapy",)),
    (
        r"\bbachelor\s+of\s+laws\b|\blaws?\s*\(\s*honours\s*\)|"
        r"\blaws?\b.*\bgraduate\s+entry\b|\bgraduate\s+entry\b.*\blaws?\b",
        ("Law",),
    ),
    (r"\bjustice\b", ("Criminology",)),
        (r"\bscreen\s+industr", ("Film, Photography & Media Production",)),
    (r"\bpromotional\s+communication\b", ("Advertising",)),
    (
        r"\bdigital\s+business\b",
        ("Entrepreneurship & Innovation",),
    ),
    (
        r"\bbusiness\s*[-–—]\s*international\b|\binternational\s+business\b",
        ("International Business",),
    ),
    (r"\bbusiness\s+management\b|\bmanagement\s+of\s+business\b", ("Management",)),
    (r"\bdigital\s+health\b", ("Management",)),
    (r"\bmba\b", ("MBA",)),
    (r"\bpublic\s+health\b", ("Public Health",)),
]

MAJOR_KEYWORD_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("aviation", "airworthiness", "pilot training"), "Aviation"),
    (
        ("animation", "cinematic", "photography", "film production"),
        "Film & Photography",
    ),
    (
        (
            "visual art",
            "sculpture",
            "painting",
            "ceramics",
            "printmaking",
            "studio art",
        ),
        "Fine & Visual Arts",
    ),
    (
        (
            "computer science",
            "information technology",
            "artificial intelligence",
            "machine learning",
            "robotics",
            "data science",
            "cybersecurity",
            "cyber security",
            "software engineering",
            "ict",
            "information and communications",
        ),
        "Computer Science",
    ),
    (
        (
            "financial planning",
            "financial advice",
            "fintech",
            "financial technology",
        ),
        "Business & Management",
    ),
    (("business", "commerce", "management", "marketing", "finance", "accounting", "mba"), "Business & Management"),
    (
        (
            "natural science",
            "physics",
            "chemistry",
            "biology",
            "mathematics",
            "biomedical science",
        ),
        "Life Sciences",
    ),
    (("engineer",), "Engineering"),
    (("humanities", "history", "philosophy", "liberal arts"), "Humanities"),
    (("social science", "sociology", "anthropology", "psychology"), "Social Sciences"),
    (("design", "creative", "fine art", "music", "film", "media"), "Arts & Design"),
    (("education", "teaching", "teacher"), "Education & Training"),
    (("law", "legal", "juris"), "Law & Legal"),
    (
        (
            "architect",
            "urban planning",
            "regional planning",
            "town planning",
            "built environment",
        ),
        "Architecture & Planning",
    ),
    (("public policy", "social work", "justice", "criminology", "humanitarian"), "Public Policy & Social Work"),
    (("agricultur", "veterinary", "vet "), "Agriculture & Food Sciences"),
    (
        (
            "health science",
            "nursing",
            "nurse",
            "midwif",
            "physiotherap",
            "medicine",
            "medical",
            "public health",
            "paramedic",
            "dentistry",
            "dental",
            "allied health",
            "occupational therap",
            "occupational health",
            "environmental health",
            "speech path",
            "podiatr",
            "genomic",
            "psycholog",
            "exercise science",
            "clinical physiology",
            "forensic mental",
            "autism",
            "suicidolog",
            "infection prevention",
            "midwif",
            "osteopath",
            "chiropractic",
            "nutrition",
            "dietetic",
            "dermal",
            "mental health",
            "outdoor leadership",
            "strength and conditioning",
        ),
        "Health Sciences",
    ),
    (("digital communication", "communication design"), "Arts & Design"),
    (("pharmacy", "pharma", "life science"), "Pharmacy and Pharmaceutical Sciences"),
]


@dataclass(frozen=True)
class MajorRef:
    id: int
    label: str
    fold: str


@dataclass(frozen=True)
class SubMajor:
    id: int
    name: str
    major_id: int
    major_label: str
    fold: str


@dataclass
class Action:
    kind: str  # UPDATE | INSERT
    program_id: int
    program_name: str
    map_id: int | None
    major_id: int
    major_label: str
    sub_id: int
    sub_name: str
    how: str


def fold(value: str | None) -> str:
    s = (value or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def sub_alias_folds(name: str, fold_s: str | None = None) -> list[str]:
    """Live-catalog match keys: label fold, paren-stripped, paren contents.

    New education_sub_majors rows participate by name without hardcoded ids.

    Do not emit a single-token paren-stripped head when the label has a
    specialty paren (``Health (Neonatal Care)`` must not alias as bare
    ``health``).
    """
    base = fold_s or fold(name)
    aliases: list[str] = []
    if base:
        aliases.append(base)
    paren_parts = re.findall(r"\(([^)]+)\)", name or "")
    stripped = fold(re.sub(r"\([^)]*\)", " ", name or ""))
    if stripped and stripped not in aliases:
        # Bare outer token after stripping a specialty paren is too broad.
        if not (paren_parts and len(stripped.split()) <= 1):
            aliases.append(stripped)
    for part in paren_parts:
        inner = fold(part)
        if inner and inner not in aliases:
            aliases.append(inner)
    extra: list[str] = []
    for item in aliases:
        swapped = item.replace("cybersecurity", "cyber security")
        if swapped != item:
            extra.append(swapped)
        swapped = item.replace("cyber security", "cybersecurity")
        if swapped != item:
            extra.append(swapped)
    for item in extra:
        if item not in aliases:
            aliases.append(item)
    for extra_alias in CATALOG_SUB_ALIAS_EXTRAS.get(base, ()):
        folded = fold(extra_alias)
        if folded and folded not in aliases:
            aliases.append(folded)
    return aliases


_PAREN_FIELD_RE = re.compile(r"\(([^)]+)\)")
_PAREN_NOISE_FOLDS = frozenset(
    {
        "honours",
        "honors",
        "deans scholar",
        "dean s scholar",
        "smah",
        "hhsc",
        "abab",
        "graduate entry",
        "international",
        "qualifying",
        "phd",
    }
)


def named_paren_fields(raw: str) -> list[str]:
    """Parenthetical streams that are not honours/code noise."""
    out: list[str] = []
    for chunk in _PAREN_FIELD_RE.findall(raw or ""):
        key = fold(chunk)
        if not key or key in _PAREN_NOISE_FOLDS:
            continue
        if "honour" in key or "honor" in key:
            continue
        if "dean" in key and "scholar" in key:
            continue
        if len(key) < 4:
            continue
        if key in {
            "science",
            "arts",
            "creative arts",
            "humanities",
            "liberal arts",
            "natural sciences",
            "natural science",
        }:
            continue
        out.append(chunk.strip())
    return out


def award_subject_key(name: str) -> str:
    """Folded subject after stripping degree prefix / honours noise."""
    cleaned = strip_program_code(name or "")
    cleaned = HONOURS_NOISE.sub(" ", cleaned)
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    cleaned = DEGREE_PREFIX.sub("", cleaned)
    key = fold(cleaned)
    if key.startswith("advanced "):
        key = key[len("advanced ") :]
    return key


def split_award_titles(name: str) -> list[str]:
    """Award components of a combined/double degree, else ``[name]``."""
    raw = strip_program_code(name or "")
    if not raw:
        return []
    parts: list[str] = []
    for slash_part in SLASH_SPLIT.split(raw):
        chunks = NEXT_AWARD_SPLIT.split(slash_part)
        parts.extend(c.strip(" -–—") for c in chunks if c.strip(" -–—"))
    seen: set[str] = set()
    uniq: list[str] = []
    for part in parts:
        key = fold(part)
        if not key or key in seen:
            continue
        seen.add(key)
        uniq.append(part)
    return uniq if uniq else [raw]


def looks_like_program_title(raw: str) -> bool:
    return bool(DEGREE_TOKEN.search(raw or ""))


def subject_phrases(name: str) -> list[str]:
    out: list[str] = []
    for part in SLASH_SPLIT.split(strip_program_code(name)):
        cleaned = HONOURS_NOISE.sub(" ", part)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—")
        parens = [
            p.strip()
            for p in re.findall(r"\(([^)]+)\)", cleaned)
            if fold(p) not in {"honours", "graduate entry"}
        ]
        core = re.sub(r"\([^)]*\)", " ", cleaned)
        core = DEGREE_PREFIX.sub("", core).strip()
        core = re.sub(r"\s+", " ", core).strip(" -–—")
        if core:
            out.append(core)
        out.extend(parens)
    seen: set[str] = set()
    uniq: list[str] = []
    for item in out:
        key = fold(item)
        if not key or key in seen:
            continue
        seen.add(key)
        uniq.append(item)
    return uniq


# Catalog labels that are a stem plus a field noun (Civil → Civil Engineering).
_FIELD_SUFFIXES = frozenset({"engineering", "science", "sciences", "technology", "studies"})
_MATCH_STOPWORDS = frozenset({"and", "of", "the", "in", "for", "to", "with"})
_TOKEN_STEM = {
    "sciences": "science",
    "communications": "communication",
}


def _stem_token(token: str) -> str:
    return _TOKEN_STEM.get(token, token)


def _stem_fold(value: str) -> str:
    return " ".join(_stem_token(t) for t in value.split())


def _whole_phrase_match(query: str, candidate: str) -> bool:
    """True when the catalog label is justified by the title subject.

    Match the catalog phrase *inside the title*, not the title inside a longer
    sibling label. ``business`` must not match ``international business``.
    """
    query = _stem_fold(query)
    candidate = _stem_fold(candidate)
    if query == candidate:
        return True
    q_toks = query.split()
    c_toks = candidate.split()
    if re.search(rf"(?:^| ){re.escape(candidate)}(?: |$)", query):
        if candidate in GENERIC_SUB_FOLDS and len(c_toks) < len(q_toks):
            return False
        return True
    # Allow Civil → Civil Engineering, but not Design → Design Technology when
    # the subject already has a configured generic default sub-major.
    if (
        query not in GENERIC_SUBJECTS
        and query not in GENERIC_AWARD_DEFAULT_SUB
        and len(c_toks) == len(q_toks) + 1
        and c_toks[: len(q_toks)] == q_toks
        and c_toks[-1] in _FIELD_SUFFIXES
    ):
        return True
    return False


def _phrase_in_haystack(needle: str, haystack: str) -> bool:
    """Whole-phrase containment (avoids ``certificate i`` ⊂ ``certificate in``)."""
    if not needle or not haystack:
        return False
    return bool(re.search(rf"(?:^| ){re.escape(needle)}(?: |$)", haystack))


def match_sub_from_live_catalog(raw: str, catalog: list[SubMajor]) -> SubMajor | None:
    """Longest distinctive catalog hit in the award title (no faculty dumps)."""
    hay = fold(strip_program_code(raw))
    subject = award_subject_key(raw)
    haystack = _stem_fold(f"{hay} {subject}".strip())
    ranked: list[tuple[int, int, int]] = []
    seen_sub: set[int] = set()
    for sub in catalog:
        best_for_sub: tuple[int, int] | None = None
        for alias in sub_alias_folds(sub.name, sub.fold):
            alias_n = _stem_fold(alias)
            if not alias_n or alias_n in GENERIC_SUBJECTS:
                continue
            atoks = [t for t in alias_n.split() if t not in _MATCH_STOPWORDS]
            score = 0
            if alias_n == subject or alias_n == hay:
                score = 500
            elif _whole_phrase_match(subject, alias_n) or _whole_phrase_match(hay, alias_n):
                score = 400
            elif _phrase_in_haystack(alias_n, haystack):
                score = 350
            elif len(atoks) >= 2:
                for n in range(len(atoks), 1, -1):
                    needle = " ".join(atoks[:n])
                    if _phrase_in_haystack(needle, haystack):
                        score = 200 + n * 15
                        break
            elif (
                len(atoks) == 1
                and len(atoks[0]) >= 6
                and atoks[0] not in GENERIC_SUBJECTS
                and _phrase_in_haystack(atoks[0], haystack)
            ):
                score = 110
            if score and (best_for_sub is None or score > best_for_sub[0]):
                best_for_sub = (score, len(alias_n))
        if best_for_sub is None:
            continue
        ranked.append((best_for_sub[0], best_for_sub[1], sub.id))
        seen_sub.add(sub.id)
    if not ranked:
        return None
    ranked.sort(reverse=True)
    top_score, top_len, top_id = ranked[0]
    for score, length, sid in ranked[1:]:
        if score == top_score and length == top_len and sid != top_id:
            return None
        break
    by_id = {s.id: s for s in catalog}
    return by_id.get(top_id)


def match_sub_by_label(
    label: str,
    catalog: list[SubMajor],
    *,
    prefer_major_ids: set[int] | None = None,
) -> SubMajor | None:
    key = fold(label)
    if not key:
        return None

    def score(sub: SubMajor) -> tuple[int, int]:
        aliases = sub_alias_folds(sub.name, sub.fold)
        if key in aliases or any(a == key for a in aliases):
            tier = 300
        elif any(_whole_phrase_match(key, alias) for alias in aliases):
            tier = 200
        else:
            return (-1, 0)
        prefer = 1 if prefer_major_ids and sub.major_id in prefer_major_ids else 0
        longest = max((len(a) for a in aliases), default=len(sub.fold))
        return (tier + prefer, longest)

    best: SubMajor | None = None
    best_score = (-1, 0)
    for sub in catalog:
        sc = score(sub)
        if sc > best_score:
            best_score = sc
            best = sub
    if best_score[0] < 0:
        return None
    return best


def fuzzy_under_major(phrase: str, subs: list[SubMajor]) -> tuple[SubMajor, str] | None:
    key = fold(phrase)
    if not key or key in GENERIC_SUBJECTS:
        return None

    exact = [s for s in subs if s.fold == key]
    if len(exact) == 1:
        return exact[0], "exact"
    safe = [s for s in subs if _whole_phrase_match(key, s.fold) and s.fold != key]
    if len(safe) == 1:
        return safe[0], "contains"
    if len(safe) > 1:
        safe.sort(key=lambda s: len(s.fold), reverse=True)
        if len(safe[0].fold) > len(safe[1].fold):
            return safe[0], "contains_longest"

    best: SubMajor | None = None
    best_score = 0.0
    for sub in subs:
        if sub.fold.startswith("general ") and sub.fold != key:
            continue
        ratio = SequenceMatcher(None, key, sub.fold).ratio()
        stoks = [t for t in sub.fold.split() if t not in {"and", "of", "the"}]
        if stoks and all(t in key for t in stoks) and len("".join(stoks)) >= 8:
            ratio = max(ratio, 0.93)
        if ratio > best_score:
            best_score = ratio
            best = sub
    if best and best_score >= 0.88:
        return best, f"fuzzy:{best_score:.2f}"
    return None


def hint_matches(name: str) -> list[tuple[str, ...]]:
    hits: list[tuple[str, ...]] = []
    for pattern, labels in TITLE_SUB_MAJOR_HINTS:
        if re.search(pattern, name, flags=re.IGNORECASE):
            hits.append(labels)
    return hits


def _majors_as_dicts(majors: Sequence[MajorRef | dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for major in majors:
        if isinstance(major, MajorRef):
            out.append({"id": major.id, "label": major.label, "fold": major.fold})
        else:
            out.append(
                {
                    "id": int(major["id"]),
                    "label": major.get("label") or major.get("name") or "",
                    "fold": major.get("fold") or fold(major.get("label") or major.get("name")),
                }
            )
    return out


def match_education_major(
    raw: str,
    majors: Sequence[MajorRef | dict[str, Any]],
) -> dict[str, Any]:
    catalog = _majors_as_dicts(majors)
    raw = strip_program_code(raw)
    key = fold(raw)
    entry: dict[str, Any] = {
        "name": (raw or "").strip(),
        "raw_name": (raw or "").strip(),
        "education_major_id": None,
        "match": None,
    }
    if not key:
        return entry

    for major in catalog:
        if key == major["fold"] or _major_fold_match(key, major["fold"]):
            entry["name"] = major["label"]
            entry["education_major_id"] = major["id"]
            entry["match"] = "exact"
            return entry

    subject = award_subject_key(raw)
    award_label = AWARD_SUBJECT_MAJOR.get(subject)
    if award_label:
        hit = _major_entry_for_label(
            catalog, award_label, raw=raw, match="award_subject"
        )
        if hit:
            return hit

    for major in catalog:
        if len(major["fold"]) >= 8 and (
            key in major["fold"] or major["fold"] in key
        ):
            entry["name"] = major["label"]
            entry["education_major_id"] = major["id"]
            entry["match"] = "contains"
            return entry

    for needles, label in MAJOR_KEYWORD_HINTS:
        if any(n in key for n in needles):
            hit = _major_entry_for_label(catalog, label, raw=raw, match="keyword")
            if hit:
                return hit
    return entry


_MAJOR_FOLD_ALIASES = {
    # CS five-way / legacy umbrella
    "computer science and it": "computer science",
    "computer science": "computer science and it",
    "computer science and information technology": "computer science",
    # Natural → Life / Physical split
    "natural sciences": "life sciences",
    "natural and physical sciences": "physical sciences",
    # Engineering rename
    "engineering and technology": "engineering",
    "engineering": "engineering and technology",
    # Humanities / Social split
    "humanities and social sciences": "humanities",
    "humanities": "humanities and social sciences",
    # Education rename
    "education": "education and training",
    "education and training": "education",
    # Law rename
    "law and legal studies": "law and legal",
    "law and legal": "law and legal studies",
    # Pharmacy rename
    "pharmacy and life sciences": "pharmacy and pharmaceutical sciences",
    "pharmacy and pharmaceutical sciences": "pharmacy and life sciences",
    # Health / Medical split
    "health sciences and medicine": "health sciences",
    "health sciences": "health sciences and medicine",
    "health and medical sciences": "medical sciences",
    # PHI merged into Health
    "public health informatics": "health sciences",
    "phi": "health sciences",
    # Agriculture / Vet split
    "agriculture and veterinary sciences": "agriculture and food sciences",
    "agriculture and food sciences": "agriculture and veterinary sciences",
    # Aviation rename
    "aviation studies": "aviation",
    "aviation": "aviation studies",
    # Hospitality rename
    "hospitality and tourism management": "hospitality and tourism",
    "hospitality and tourism": "hospitality and tourism management",
    # Theology rename
    "theology and religious studies": "theology and religious",
    "theology and religious": "theology and religious studies",
}


def _major_fold_match(want: str, got: str) -> bool:
    if want == got:
        return True
    return _MAJOR_FOLD_ALIASES.get(want) == got


def _major_entry_for_label(
    catalog: list[dict[str, Any]],
    label: str,
    *,
    raw: str,
    match: str,
) -> dict[str, Any] | None:
    want = fold(label)
    for major in catalog:
        if _major_fold_match(want, fold(major["label"])) or _major_fold_match(
            want, major["fold"]
        ):
            return {
                "name": major["label"],
                "raw_name": (raw or "").strip(),
                "education_major_id": major["id"],
                "match": match,
            }
    return None


def match_majors_from_program_title(
    raw: str,
    majors: Sequence[MajorRef | dict[str, Any]],
) -> list[dict[str, Any]]:
    """Majors from award names in the program title (combined degrees split).

    College/faculty names are not used here. ``Bachelor of Arts`` maps to
    Arts & Design; ``Bachelor of Business`` / ``Bachelor of Laws`` keep
    Business and Law. Arts-side duals stay major-only (no Fine Arts /
    General Design sub-major) unless a later title hint is specific.
    """
    catalog = _majors_as_dicts(majors)
    awards = split_award_titles(raw)
    combined = len(awards) > 1
    found: list[dict[str, Any]] = []
    seen: set[int] = set()

    sources = awards if combined else [raw]
    for piece in sources:
        hit = match_education_major(piece, catalog)
        mid = hit.get("education_major_id")
        if mid is None:
            continue
        mid = int(mid)
        if mid in seen:
            continue
        seen.add(mid)
        found.append(hit)
    return found


def match_education_majors_from_text(
    raw: str,
    majors: Sequence[MajorRef | dict[str, Any]],
) -> list[dict[str, Any]]:
    """Match majors from a program title or a college/faculty name.

    Degree titles (including combined awards) are classified from award
    names only. Faculty strings such as ``Business and Law`` still dump
    every keyword hit — callers must not apply that dump onto dual degrees
    whose titles already name specific fields.
    """
    if looks_like_program_title(raw):
        return match_majors_from_program_title(raw, majors)

    catalog = _majors_as_dicts(majors)
    key = fold(raw)
    if not key:
        return []
    found: list[dict[str, Any]] = []
    seen: set[int] = set()
    primary = match_education_major(raw, catalog)
    if primary.get("education_major_id"):
        found.append(primary)
        seen.add(int(primary["education_major_id"]))
    for needles, label in MAJOR_KEYWORD_HINTS:
        if not any(n in key for n in needles):
            continue
        extra = _major_entry_for_label(catalog, label, raw=raw, match="keyword")
        if extra is None:
            continue
        mid = int(extra["education_major_id"])
        if mid in seen:
            continue
        seen.add(mid)
        found.append(extra)
    return found


def match_education_sub_major(
    raw: str,
    sub_majors: Sequence[SubMajor | dict[str, Any]],
    *,
    prefer_major_id: int | None = None,
    major_labels: dict[int, str] | None = None,
) -> dict[str, Any]:
    catalog = catalog_from_mixed(sub_majors, major_labels=major_labels)
    prefer = {prefer_major_id} if prefer_major_id is not None else None
    hit = match_sub_by_label(raw, catalog, prefer_major_ids=prefer)
    if hit is None and prefer_major_id is not None:
        scoped = [s for s in catalog if s.major_id == prefer_major_id]
        fuzzy = fuzzy_under_major(raw, scoped)
        if fuzzy:
            hit = fuzzy[0]
    entry: dict[str, Any] = {
        "name": (raw or "").strip(),
        "raw_name": (raw or "").strip(),
        "education_sub_major_id": None,
        "education_major_id": None,
        "match": None,
    }
    if hit is None:
        return entry
    entry["name"] = hit.name
    entry["education_sub_major_id"] = hit.id
    entry["education_major_id"] = hit.major_id
    entry["match"] = "exact" if hit.fold == fold(raw) else "contains"
    return entry


def catalog_from_mixed(
    sub_majors: Sequence[SubMajor | dict[str, Any]],
    *,
    major_labels: dict[int, str] | None = None,
) -> list[SubMajor]:
    out: list[SubMajor] = []
    for item in sub_majors:
        if isinstance(item, SubMajor):
            out.append(item)
            continue
        mid = int(item["major_id"])
        name = str(item.get("name") or "")
        out.append(
            SubMajor(
                id=int(item["id"]),
                name=name,
                major_id=mid,
                major_label=(major_labels or {}).get(mid, str(item.get("major_label") or "")),
                fold=str(item.get("fold") or fold(name)),
            )
        )
    return out


def catalog_from_scrape_dicts(
    majors: Sequence[dict[str, Any]],
    sub_majors: Sequence[dict[str, Any]],
) -> tuple[list[MajorRef], list[SubMajor]]:
    major_refs = [
        MajorRef(
            id=int(m["id"]),
            label=str(m.get("label") or m.get("name") or ""),
            fold=str(m.get("fold") or fold(m.get("label") or m.get("name"))),
        )
        for m in majors
    ]
    labels = {m.id: m.label for m in major_refs}
    subs = catalog_from_mixed(sub_majors, major_labels=labels)
    return major_refs, subs


def load_taxonomy_from_cursor(cur: Any) -> tuple[list[MajorRef], list[SubMajor]]:
    """Load live catalog. ``cur`` is any DB-API cursor (psycopg)."""
    cur.execute(
        """
        SELECT id, label
        FROM education_majors
        WHERE COALESCE(is_active, true)
        ORDER BY id
        """
    )
    majors = [MajorRef(int(r[0]), r[1], fold(r[1])) for r in cur.fetchall()]
    cur.execute(
        """
        SELECT sm.id, sm.name, sm.major_id, m.label
        FROM education_sub_majors sm
        JOIN education_majors m ON m.id = sm.major_id
        ORDER BY sm.id
        """
    )
    catalog = [
        SubMajor(int(r[0]), r[1], int(r[2]), r[3], fold(r[1])) for r in cur.fetchall()
    ]
    return majors, catalog


def plan_actions(
    *,
    programs: list[tuple[int, str]],
    mappings: list[tuple[int, int, int, str, int | None, str | None]],
    catalog: list[SubMajor],
) -> list[Action]:
    by_major: dict[int, list[SubMajor]] = {}
    for sub in catalog:
        by_major.setdefault(sub.major_id, []).append(sub)

    maps_by_prog: dict[int, list[dict[str, Any]]] = {}
    for map_id, program_id, major_id, major_label, sub_id, sub_name in mappings:
        maps_by_prog.setdefault(program_id, []).append(
            {
                "map_id": map_id,
                "major_id": major_id,
                "major_label": major_label,
                "sub_id": sub_id,
                "sub_name": sub_name,
            }
        )

    actions: list[Action] = []
    for program_id, program_name in programs:
        rows = maps_by_prog.get(program_id) or []
        if not rows:
            continue
        major_ids = {r["major_id"] for r in rows}
        existing_sub_ids = {r["sub_id"] for r in rows if r["sub_id"] is not None}
        claimed_map_ids: set[int] = set()
        planned_sub_ids: set[int] = set(existing_sub_ids)
        planned_pairs: set[tuple[int, int]] = {
            (r["major_id"], r["sub_id"]) for r in rows if r["sub_id"] is not None
        }

        candidates: list[tuple[SubMajor, str]] = []

        for labels in hint_matches(program_name):
            for label in labels:
                hit = match_sub_by_label(label, catalog, prefer_major_ids=major_ids)
                if hit is None:
                    continue
                candidates.append((hit, f"hint:{label}"))
                break

        for phrase in subject_phrases(program_name):
            if fold(phrase) in GENERIC_SUBJECTS:
                continue
            for mid in sorted(major_ids):
                hit = fuzzy_under_major(phrase, by_major.get(mid, []))
                if hit:
                    candidates.append((hit[0], f"{hit[1]}:{phrase}"))

        seen_sub: set[int] = set()
        uniq: list[tuple[SubMajor, str]] = []
        for sub, how in candidates:
            if sub.id in seen_sub:
                continue
            seen_sub.add(sub.id)
            uniq.append((sub, how))

        covered_majors = {sub.major_id for sub, _how in uniq}
        for phrase in subject_phrases(program_name):
            default_label = GENERIC_AWARD_DEFAULT_SUB.get(fold(phrase))
            if not default_label:
                continue
            hit = match_sub_by_label(
                default_label, catalog, prefer_major_ids=major_ids
            )
            if hit is None or hit.major_id not in major_ids:
                continue
            if hit.major_id in covered_majors:
                continue
            if hit.id in seen_sub:
                continue
            uniq.append((hit, f"generic_default:{default_label}"))
            seen_sub.add(hit.id)
            covered_majors.add(hit.major_id)

        uniq.sort(key=lambda item: (-len(item[0].fold), item[0].id))

        for sub, how in uniq:
            if sub.id in planned_sub_ids:
                continue
            pair = (sub.major_id, sub.id)
            if pair in planned_pairs:
                continue

            null_rows = [
                r
                for r in rows
                if r["major_id"] == sub.major_id
                and r["sub_id"] is None
                and r["map_id"] not in claimed_map_ids
            ]
            if null_rows:
                target = null_rows[0]
                actions.append(
                    Action(
                        kind="UPDATE",
                        program_id=program_id,
                        program_name=program_name,
                        map_id=int(target["map_id"]),
                        major_id=sub.major_id,
                        major_label=sub.major_label,
                        sub_id=sub.id,
                        sub_name=sub.name,
                        how=how,
                    )
                )
                claimed_map_ids.add(int(target["map_id"]))
                planned_sub_ids.add(sub.id)
                planned_pairs.add(pair)
                continue

            major_present = sub.major_id in major_ids
            major_has_any_sub = any(
                r["sub_id"] is not None and r["major_id"] == sub.major_id for r in rows
            ) or any(
                a.major_id == sub.major_id and a.kind == "UPDATE"
                for a in actions
                if a.program_id == program_id
            )

            if not major_present or major_has_any_sub or not null_rows:
                other_null_same_major = [
                    r
                    for r in rows
                    if r["major_id"] == sub.major_id
                    and r["sub_id"] is None
                    and r["map_id"] not in claimed_map_ids
                ]
                if other_null_same_major:
                    continue
                if major_present and major_has_any_sub:
                    if not how.startswith("hint:"):
                        continue
                actions.append(
                    Action(
                        kind="INSERT",
                        program_id=program_id,
                        program_name=program_name,
                        map_id=None,
                        major_id=sub.major_id,
                        major_label=sub.major_label,
                        sub_id=sub.id,
                        sub_name=sub.name,
                        how=how,
                    )
                )
                major_ids.add(sub.major_id)
                planned_sub_ids.add(sub.id)
                planned_pairs.add(pair)

    actions = _prefer_early_childhood_over_admin(actions)
    actions = _dedupe_conflicting_updates(actions)
    return actions


def _prefer_early_childhood_over_admin(actions: list[Action]) -> list[Action]:
    by_prog: dict[int, list[Action]] = {}
    for a in actions:
        by_prog.setdefault(a.program_id, []).append(a)
    out: list[Action] = []
    for _pid, group in by_prog.items():
        names = {a.sub_name for a in group}
        if "Early Childhood Education" in names and "Educational Administration" in names:
            group = [a for a in group if a.sub_name != "Educational Administration"]
        out.extend(group)
    return out


def _dedupe_conflicting_updates(actions: list[Action]) -> list[Action]:
    updates: dict[int, Action] = {}
    inserts: list[Action] = []
    for a in actions:
        if a.kind != "UPDATE" or a.map_id is None:
            inserts.append(a)
            continue
        prev = updates.get(a.map_id)
        if prev is None:
            updates[a.map_id] = a
            continue
        prev_hint = prev.how.startswith("hint:")
        cur_hint = a.how.startswith("hint:")
        if cur_hint and not prev_hint:
            updates[a.map_id] = a
        elif cur_hint == prev_hint and len(fold(a.sub_name)) > len(fold(prev.sub_name)):
            updates[a.map_id] = a
    seen_ins: set[tuple[int, int, int]] = set()
    uniq_ins: list[Action] = []
    for a in inserts:
        key = (a.program_id, a.major_id, a.sub_id)
        if key in seen_ins:
            continue
        seen_ins.add(key)
        uniq_ins.append(a)
    return list(updates.values()) + uniq_ins


def insert_program_mapping_row(
    cur: Any,
    *,
    program_id: int,
    major_id: int,
    sub_id: int | None,
) -> bool:
    """Insert one PEM row; return True when a new row was created."""
    if sub_id is not None:
        cur.execute(
            """
            INSERT INTO program_education_major_mappings (
                program_id, education_major_id, education_sub_major_id
            )
            VALUES (%s, %s, %s)
            ON CONFLICT (program_id, education_major_id, education_sub_major_id)
            WHERE education_sub_major_id IS NOT NULL
            DO NOTHING
            """,
            (program_id, major_id, sub_id),
        )
    else:
        cur.execute(
            """
            INSERT INTO program_education_major_mappings (
                program_id, education_major_id, education_sub_major_id
            )
            VALUES (%s, %s, NULL)
            ON CONFLICT (program_id, education_major_id)
            WHERE education_sub_major_id IS NULL
            DO NOTHING
            """,
            (program_id, major_id),
        )
    return int(cur.rowcount or 0) == 1


def apply_actions(cur: Any, actions: list[Action]) -> tuple[int, int]:
    updated = inserted = 0
    for a in actions:
        if a.kind == "UPDATE":
            assert a.map_id is not None
            cur.execute(
                """
                UPDATE program_education_major_mappings
                SET education_sub_major_id = %s
                WHERE id = %s
                  AND education_sub_major_id IS NULL
                  AND education_major_id = %s
                """,
                (a.sub_id, a.map_id, a.major_id),
            )
            if cur.rowcount != 1:
                raise SystemExit(
                    f"ABORT: UPDATE map_id={a.map_id} matched {cur.rowcount} rows"
                )
            updated += 1
        else:
            if insert_program_mapping_row(
                cur,
                program_id=a.program_id,
                major_id=a.major_id,
                sub_id=a.sub_id,
            ):
                inserted += 1
    return updated, inserted


def dedupe_mapping_pairs(
    pairs: Iterable[tuple[int, int | None]],
) -> list[tuple[int, int | None]]:
    by_major: dict[int, list[int | None]] = {}
    for mid, sid in pairs:
        by_major.setdefault(int(mid), []).append(int(sid) if sid is not None else None)
    out: list[tuple[int, int | None]] = []
    seen: set[tuple[int, int | None]] = set()
    for mid, sids in by_major.items():
        filled = [s for s in sids if s is not None]
        chosen = filled if filled else [None]
        for sid in chosen:
            key = (mid, sid)
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
    return out


def classify_award_piece(
    raw: str,
    majors: Sequence[MajorRef | dict[str, Any]],
    catalog: list[SubMajor],
) -> tuple[int, int | None] | None:
    """One award title → at most one major and optional sub-major.

    Named streams and title hints win. Generic awards get a single catalog
    default sub when configured; Science / Arts stay major-only.
    """
    major_dicts = _majors_as_dicts(majors)
    raw = strip_program_code(raw)

    for labels in hint_matches(raw):
        for label in labels:
            hit = match_sub_by_label(label, catalog)
            if hit is not None:
                return hit.major_id, hit.id

    catalog_hit = match_sub_from_live_catalog(raw, catalog)
    if catalog_hit is not None:
        return catalog_hit.major_id, catalog_hit.id

    for field in named_paren_fields(raw):
        hit = match_sub_by_label(field, catalog)
        if hit is not None:
            return hit.major_id, hit.id
        nested = match_sub_from_live_catalog(field, catalog)
        if nested is not None:
            return nested.major_id, nested.id

    for phrase in subject_phrases(raw):
        if fold(phrase) in GENERIC_SUBJECTS:
            continue
        hit = match_sub_by_label(phrase, catalog)
        if hit is not None:
            return hit.major_id, hit.id

    major_hit = match_education_major(raw, major_dicts)
    mid = major_hit.get("education_major_id")
    if mid is None:
        default_label = GENERIC_AWARD_DEFAULT_SUB.get(award_subject_key(raw))
        if default_label:
            hit = match_sub_by_label(default_label, catalog)
            if hit is not None:
                return hit.major_id, hit.id
        return None
    mid = int(mid)
    scoped = [s for s in catalog if s.major_id == mid]
    for phrase in subject_phrases(raw):
        if fold(phrase) in GENERIC_SUBJECTS:
            continue
        fuzzy = fuzzy_under_major(phrase, scoped)
        if fuzzy:
            return fuzzy[0].major_id, fuzzy[0].id

    subject = award_subject_key(raw)
    default_label = GENERIC_AWARD_DEFAULT_SUB.get(subject)
    if default_label:
        hit = match_sub_by_label(
            default_label, catalog, prefer_major_ids={mid}
        )
        if hit is not None and hit.major_id == mid:
            return mid, hit.id
    return mid, None


def intended_mapping_pairs(
    program_name: str,
    majors: Sequence[MajorRef | dict[str, Any]],
    catalog: list[SubMajor],
) -> list[tuple[int, int | None]]:
    """Title-only pairs: one major (and sub if clear) per award name."""
    awards = split_award_titles(strip_program_code(program_name)) or [
        strip_program_code(program_name)
    ]
    rows: list[tuple[str, int, int | None]] = []
    for piece in awards:
        pair = classify_award_piece(piece, majors, catalog)
        if pair is None:
            continue
        rows.append((piece, pair[0], pair[1]))
    return _collapse_one_sub_per_major(rows, majors, catalog)


def _collapse_one_sub_per_major(
    rows: list[tuple[str, int, int | None]],
    majors: Sequence[MajorRef | dict[str, Any]],
    catalog: list[SubMajor],
) -> list[tuple[int, int | None]]:
    """Schema allows one sub per (program, major). Prefer named over generic."""
    sub_by_id = {s.id: s for s in catalog}
    default_folds = {fold(v) for v in GENERIC_AWARD_DEFAULT_SUB.values()}
    by_major: dict[int, list[tuple[str, int | None]]] = {}
    for piece, mid, sid in rows:
        by_major.setdefault(mid, []).append((piece, sid))

    out: list[tuple[int, int | None]] = []
    extra: list[tuple[int, int | None]] = []
    for mid, items in by_major.items():
        named_sids = [sid for _p, sid in items if sid is not None]
        unique_named = list(dict.fromkeys(named_sids))
        if len(unique_named) <= 1:
            chosen = unique_named[0] if unique_named else None
            out.append((mid, chosen))
            continue

        law_sid = next(
            (
                sid
                for sid in unique_named
                if fold(sub_by_id[sid].name) == "law"
            ),
            None,
        )
        if law_sid is not None:
            out.append((mid, law_sid))
            for piece, sid in items:
                if sid == law_sid or sid is None:
                    continue
                subject = award_subject_key(piece)
                label = AWARD_SUBJECT_MAJOR.get(subject)
                if not label:
                    continue
                hit = _major_entry_for_label(
                    _majors_as_dicts(majors),
                    label,
                    raw=piece,
                    match="conflict_rehome",
                )
                if hit and int(hit["education_major_id"]) != mid:
                    extra.append((int(hit["education_major_id"]), None))
            continue

        specific = [
            sid
            for sid in unique_named
            if fold(sub_by_id[sid].name) not in default_folds
        ]
        out.append((mid, (specific or unique_named)[0]))

    return dedupe_mapping_pairs(out + extra)


def finalize_mapping_pairs(
    program_name: str,
    seed_pairs: Sequence[tuple[int, int | None]],
    catalog: list[SubMajor],
    majors: Sequence[MajorRef | dict[str, Any]] | None = None,
) -> list[tuple[int, int | None]]:
    """Authoritative pairs for insert/update. Always run at import time."""
    if majors and looks_like_program_title(program_name):
        # Degree titles: ignore listing/college stream dumps entirely.
        return intended_mapping_pairs(program_name, majors, catalog)

    pairs = dedupe_mapping_pairs(seed_pairs)
    title_ids: list[int] = []
    if majors:
        for hit in match_majors_from_program_title(program_name, majors):
            mid = hit.get("education_major_id")
            if mid is not None:
                title_ids.append(int(mid))
        title_ids = list(dict.fromkeys(title_ids))
    if title_ids:
        title_set = set(title_ids)
        kept = [(mid, None) for mid, _sid in pairs if mid in title_set]
        have = {mid for mid, _sid in kept}
        for mid in title_ids:
            if mid not in have:
                kept.append((mid, None))
        pairs = dedupe_mapping_pairs(kept)
    elif not pairs and majors:
        for hit in match_education_majors_from_text(program_name, majors):
            mid = hit.get("education_major_id")
            if mid is not None:
                pairs.append((int(mid), None))
        pairs = dedupe_mapping_pairs(pairs)
    else:
        pairs = dedupe_mapping_pairs([(mid, None) for mid, _sid in pairs])
    if not pairs:
        return []

    labels = {s.major_id: s.major_label for s in catalog}
    mappings: list[tuple[int, int, int, str, int | None, str | None]] = []
    sub_name_by_id = {s.id: s.name for s in catalog}
    for i, (mid, sid) in enumerate(pairs, start=1):
        mappings.append(
            (
                i,
                0,
                mid,
                labels.get(mid, ""),
                sid,
                sub_name_by_id.get(sid) if sid is not None else None,
            )
        )
    actions = plan_actions(
        programs=[(0, program_name)],
        mappings=mappings,
        catalog=catalog,
    )
    result: dict[int, tuple[int, int | None]] = {
        i: pair for i, pair in enumerate(pairs, start=1)
    }
    extras: list[tuple[int, int | None]] = []
    for action in actions:
        if action.kind == "UPDATE" and action.map_id in result:
            result[action.map_id] = (action.major_id, action.sub_id)
        elif action.kind == "INSERT":
            extras.append((action.major_id, action.sub_id))
    return dedupe_mapping_pairs(list(result.values()) + extras)


def enrich_scraped_program(
    program_row: dict[str, Any],
    *,
    majors: Sequence[MajorRef | dict[str, Any]],
    catalog: list[SubMajor],
) -> None:
    """Fill JSON major/sub-major ids from the live catalog (high-confidence)."""
    name = str(program_row.get("name") or "")
    if not name:
        return
    majors_dicts = _majors_as_dicts(majors)
    major_list = list(program_row.get("majors") or [])
    title_guessed = match_majors_from_program_title(name, majors_dicts)
    if title_guessed:
        major_list = title_guessed
        program_row["majors"] = major_list
    elif not any(m.get("education_major_id") for m in major_list):
        guessed = match_education_majors_from_text(name, majors_dicts)
        if guessed:
            major_list = guessed
            program_row["majors"] = major_list

    seed: list[tuple[int, int | None]] = []
    for major in major_list:
        mid = major.get("education_major_id")
        if mid is None:
            continue
        mid = int(mid)
        seed.append((mid, None))

    pairs = finalize_mapping_pairs(name, seed, catalog, majors_dicts)
    major_by_id = {m["id"]: m for m in majors_dicts}
    sub_by_id = {s.id: s for s in catalog}

    existing_major_ids = {
        int(m["education_major_id"])
        for m in major_list
        if m.get("education_major_id") is not None
    }
    for mid, _sid in pairs:
        if mid in existing_major_ids:
            continue
        major = major_by_id.get(mid)
        if not major:
            continue
        major_list.append(
            {
                "name": major["label"],
                "raw_name": major["label"],
                "education_major_id": mid,
                "match": "via_title_matcher",
            }
        )
        existing_major_ids.add(mid)
    program_row["majors"] = major_list

    subs: list[dict[str, Any]] = []
    seen_sub_ids: set[int] = set()
    for _mid, sid in pairs:
        if sid is None or sid in seen_sub_ids:
            continue
        sub = sub_by_id.get(sid)
        if not sub:
            continue
        subs.append(
            {
                "name": sub.name,
                "raw_name": name,
                "education_sub_major_id": sub.id,
                "education_major_id": sub.major_id,
                "match": "title_matcher",
            }
        )
        seen_sub_ids.add(sid)
    program_row["sub_majors"] = subs
    program_row.pop("_sub_keys", None)
    program_row.pop("_major_keys", None)
