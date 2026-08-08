"""Grouped campus/city habitat categories for Future Insights."""

from __future__ import annotations

from app.schemas.nexus_intel import (
    FutureInsightsCityLiving,
    FutureInsightsHabitat,
    FutureInsightsHabitatCategory,
    FutureInsightsHabitatMetric,
)

# Canonical grouping shown in the UI (order matters).
HABITAT_CATEGORY_DEFS: list[tuple[str, str]] = [
    ("city_campus_snapshot", "City & Campus Snapshot"),
    ("livability_scores", "Livability Scores & Pulse"),
    ("housing_neighborhood", "Housing & Neighborhood"),
    ("transit_mobility", "Transit & Mobility"),
    ("safety_health", "Safety & Health"),
    ("lifestyle_amenities", "Lifestyle & Amenities"),
    ("income_careers", "Income & Careers"),
    ("digital_academic", "Digital & Academic"),
    ("ecosystem_culture", "Ecosystem & Culture"),
    ("funding_support", "Subsidies & Grants"),
]


def _m(key: str, label: str, value: str, score: float | None = None) -> FutureInsightsHabitatMetric:
    return FutureInsightsHabitatMetric(key=key, label=label, value=value, score=score)


def _cat(
    key: str, title: str, summary: str, metrics: list[FutureInsightsHabitatMetric]
) -> FutureInsightsHabitatCategory:
    return FutureInsightsHabitatCategory(key=key, title=title, summary=summary, metrics=metrics)


def _default_pack(
    *,
    location_label: str,
    city: FutureInsightsCityLiving | None,
    country_code: str | None,
) -> FutureInsightsHabitat:
    living = city
    code = (country_code or "").upper()
    if code == "GB":
        code = "UK"

    housing_shared = living.shared_housing_monthly if living else "Confirm local student housing boards"
    housing_private = living.private_rent_monthly if living else "Confirm city rent indices near campus"
    transit = living.transit_index_note if living else "Map campus ↔ housing commute before commit"
    grocery = living.grocery_index_note if living else "Budget with local CPI / student market data"
    safety = living.safety_snapshot if living else "Use campus security + city crime dashboards"
    climate = living.climate_snapshot if living else "Review seasonal climate for the specific city"

    return FutureInsightsHabitat(
        location_label=location_label,
        categories=[
            _cat(
                "city_campus_snapshot",
                "City & Campus Snapshot",
                "Orientation layer for landing, neighbourhood choice, and campus–city fit.",
                [
                    _m("city_overview", "City Overview", f"{location_label} — student hub with mixed residential and employment corridors."),
                    _m("campus_proximity", "Campus Proximity", "Most daily needs typically within 15–40 minutes by local transit or bike from main campus."),
                    _m(
                        "campus_city_compass",
                        "360° Campus & City Compass",
                        "Balance academics, housing, transit, part-time work, and social life within one metro catchment.",
                        72,
                    ),
                    _m("neighborhood_level", "Neighborhood Level", "Prioritise verified student neighbourhoods within a short commute of campus facilities."),
                ],
            ),
            _cat(
                "livability_scores",
                "Livability Scores & Pulse",
                "Composite counsellor scores (indicative 0–100) for session talk-tracks — not official rankings.",
                [
                    _m("livability_index", "Livability Index", "Solid student livability with cost and housing as the main pressure points.", 74),
                    _m("student_livability_score", "Student Livability Score", "Academic + lifestyle balance is workable with disciplined budgeting.", 76),
                    _m("student_survival_index", "Student Survival Index", "Survivable on a mid-range budget if shared housing + cooking at home.", 71),
                    _m("life_landing_score", "Life & Landing Score", "Landing is smooth when housing is locked before arrival.", 73),
                    _m("eduhabitat_index", "EduHabitat Index", "Strong study ecosystem when campus services + libraries are used actively.", 78),
                    _m("campus_pulse", "Campus / Student Pulse", "Active student societies; peak stress around exams and visa milestones.", 75),
                ],
            ),
            _cat(
                "housing_neighborhood",
                "Housing & Neighborhood",
                "Where students live, and what monthly living cash-flow looks like.",
                [
                    _m("housing", "Housing", f"Shared: {housing_shared}. Private: {housing_private}."),
                    _m("neighborhood_detail", "Neighborhood Level", "Choose areas with evening lighting, grocery access, and peer density."),
                    _m("grocery_living", "Daily Grocery & Living Expenses", grocery),
                ],
            ),
            _cat(
                "transit_mobility",
                "Transit & Mobility",
                "How students move between campus, housing, work, and amenities.",
                [
                    _m("transit_mobility", "Transit & Mobility", transit),
                    _m("climate_mobility", "Season / Climate note", climate),
                ],
            ),
            _cat(
                "safety_health",
                "Safety & Health",
                "Personal safety, air quality, insurance, and medical access.",
                [
                    _m("safety_health", "Safety & Health", safety),
                    _m("safety_crime", "Safety & Crime", "Campus cores are typically safer than late-night entertainment districts — use official crime maps."),
                    _m("air_quality", "Air Quality Index", "Usually acceptable for study cities; monitor seasonal smoke/pollution alerts."),
                    _m("health_insurance", "Health Insurance", "Mandatory or strongly expected student/private cover — confirm before visa/enrolment."),
                    _m("hospital_access", "Hospital & Health Access", "University clinics + nearby hospitals within typical metro ambulance response zones."),
                    _m("medical_infrastructure", "Medical Infrastructure", "Adequate for routine care; specialist wait times vary by public vs private systems."),
                ],
            ),
            _cat(
                "lifestyle_amenities",
                "Lifestyle & Amenities",
                "Day-to-day student life outside the classroom.",
                [
                    _m("lifestyle", "Lifestyle & Amenities", "Cafés, parks, gyms, and cultural venues are reachable from most student neighbourhoods."),
                    _m("shopping", "Shopping", "Campus stores + nearby malls/markets cover weekly needs."),
                    _m("dining", "Dining", "Mix of campus canteens, affordable casual dining, and weekend treat spots."),
                    _m("fitness", "Fitness", "University gyms + municipal/private fitness options near housing clusters."),
                ],
            ),
            _cat(
                "income_careers",
                "Income & Careers",
                "Work while studying and early-career pathways around the campus metro.",
                [
                    _m("income_careers", "Income & Careers", "Part-time campus/metro roles common; full-time graduate hiring concentrated in the metro job market."),
                    _m("jobs_full_time", "Jobs — Full-time", "Graduate full-time roles cluster with major employers in this metro — see Local Job Market cards."),
                    _m("jobs_part_time", "Jobs — Part-time", "Retail, hospitality, tutoring, and on-campus roles are the usual student mix (visa hour caps apply)."),
                ],
            ),
            _cat(
                "digital_academic",
                "Digital & Academic",
                "Connectivity, libraries, labs, and academic support density.",
                [
                    _m("digital_academic", "Digital & Academic", "Expect reliable campus Wi‑Fi, library digital stacks, and common LMS tooling."),
                    _m("study_spaces", "Study infrastructure", "Libraries, labs, and 24/7 study zones vary by faculty — tour during admit season."),
                ],
            ),
            _cat(
                "ecosystem_culture",
                "Ecosystem & Culture",
                "Social fabric, diversity, and weekend culture around campus.",
                [
                    _m("ecosystem_culture", "Ecosystem & Culture", "International student communities are active; local culture shapes weekend life."),
                    _m("community", "Student community", "Societies, faith groups, and co-national networks help landing in the first 90 days."),
                ],
            ),
            _cat(
                "funding_support",
                "Subsidies & Grants",
                "Money levers beyond family funding — scholarships, fee waivers, and local supports.",
                [
                    _m(
                        "subsidies_grants",
                        "Subsidies & Grants",
                        "Check institution scholarships, government fee waivers, and destination-specific student discounts (transit/health).",
                    ),
                    _m("work_study", "Work-study / on-campus aid", "On-campus jobs and departmental assistantships can offset living costs where visa rules allow."),
                ],
            ),
        ],
    )


# Metro-specific overrides (replace whole categories by key).
_METRO_HABITAT: dict[str, dict[str, FutureInsightsHabitatCategory]] = {
    "los-angeles": {
        "city_campus_snapshot": _cat(
            "city_campus_snapshot",
            "City & Campus Snapshot",
            "UCLA / USC / Caltech catchment — Westside & LA Basin student living.",
            [
                _m("city_overview", "City Overview", "Los Angeles is a polycentric mega-city: entertainment, aerospace, biotech, and trade hubs surround campus corridors (Westwood, Downtown, Pasadena)."),
                _m("campus_proximity", "Campus Proximity", "UCLA Westwood: groceries/gyms walkable; many internships 25–60 min via Metro/Big Blue Bus/carpool."),
                _m("campus_city_compass", "360° Campus & City Compass", "Strong academic brand + entertainment economy; housing cost and car dependence are the main trade-offs.", 79),
                _m("neighborhood_level", "Neighborhood Level", "Westwood, Sawtelle, Palms, Culver City, Koreatown — trade rent vs commute."),
            ],
        ),
        "livability_scores": _cat(
            "livability_scores",
            "Livability Scores & Pulse",
            "Indicative counsellor scores for LA campus living (0–100).",
            [
                _m("livability_index", "Livability Index", "High amenity / weather upside; housing affordability drags the score.", 71),
                _m("student_livability_score", "Student Livability Score", "Excellent campus life if shared housing is secured early.", 74),
                _m("student_survival_index", "Student Survival Index", "Tight on budget-friendly bands without roommates + meal prep.", 66),
                _m("life_landing_score", "Life & Landing Score", "Landing is smoother with temporary housing for week 1–2.", 70),
                _m("eduhabitat_index", "EduHabitat Index", "World-class libraries/labs and research density around UCLA/Caltech/USC.", 88),
                _m("campus_pulse", "Campus / Student Pulse", "Very active Greek life, clubs, and internship recruiting seasons.", 84),
            ],
        ),
        "housing_neighborhood": _cat(
            "housing_neighborhood",
            "Housing & Neighborhood",
            "LA rents are the #1 counsellor talking point.",
            [
                _m("housing", "Housing", "Shared near Westwood often USD $1,000–$1,600; private 1BR USD $2,200–$3,500+."),
                _m("neighborhood_detail", "Neighborhood Level", "Westwood premium; Palms/Culver better value; avoid unverified Craigslist-only deals."),
                _m("grocery_living", "Daily Grocery & Living Expenses", "Plan ~USD $350–$550/mo groceries + USD $80–$150 utilities/share; Trader Joe’s / ethnic markets help."),
            ],
        ),
        "transit_mobility": _cat(
            "transit_mobility",
            "Transit & Mobility",
            "Improving rail, still car-influenced.",
            [
                _m("transit_mobility", "Transit & Mobility", "Metro + Big Blue Bus / BruinBus; many students still use cars or rideshare for internships."),
                _m("climate_mobility", "Season / Climate note", "Mild winters, dry summers; wildfire smoke days can disrupt outdoor plans."),
            ],
        ),
        "safety_health": _cat(
            "safety_health",
            "Safety & Health",
            "Campus security is strong; neighbourhood selection matters.",
            [
                _m("safety_health", "Safety & Health", "UCLA/USC campus security + night shuttles; off-campus awareness required."),
                _m("safety_crime", "Safety & Crime", "Property crime risk higher near busy corridors — use campus apps and well-lit routes."),
                _m("air_quality", "Air Quality Index", "Often Good–Moderate; watch wildfire season AQI alerts."),
                _m("health_insurance", "Health Insurance", "University health insurance usually mandatory for internationals (USHIP-style)."),
                _m("hospital_access", "Hospital & Health Access", "Ronald Reagan UCLA Medical Center and nearby clinics for students."),
                _m("medical_infrastructure", "Medical Infrastructure", "Excellent specialty care; cost is high without insurance."),
            ],
        ),
        "lifestyle_amenities": _cat(
            "lifestyle_amenities",
            "Lifestyle & Amenities",
            "Entertainment capital energy with beach + campus culture.",
            [
                _m("lifestyle", "Lifestyle & Amenities", "Beaches, hiking, museums, and film culture within a 30–60 min radius."),
                _m("shopping", "Shopping", "Westwood Village, Santa Monica Place, The Grove — plus Asian markets in Sawtelle/Koreatown."),
                _m("dining", "Dining", "Campus dining + global cuisine; budget eats common in Sawtelle / K-Town."),
                _m("fitness", "Fitness", "Wooden Center / campus gyms + abundant private studios."),
            ],
        ),
        "income_careers": _cat(
            "income_careers",
            "Income & Careers",
            "Entertainment, aerospace, biotech, and tech satellite offices.",
            [
                _m("income_careers", "Income & Careers", "Strong internship density in media, aerospace (SpaceX/Hawthorne), biotech (Amgen), and consulting."),
                _m("jobs_full_time", "Jobs — Full-time", "New-grad pipelines at Netflix, Disney, SpaceX, Amgen, Deloitte LA, Google Playa Vista."),
                _m("jobs_part_time", "Jobs — Part-time", "Campus jobs, tutoring, F&B in Westwood/Santa Monica; respect F-1 hour rules."),
            ],
        ),
        "digital_academic": _cat(
            "digital_academic",
            "Digital & Academic",
            "Top-tier research and digital infrastructure.",
            [
                _m("digital_academic", "Digital & Academic", "High-speed campus network, extensive digital libraries, and research computing access."),
                _m("study_spaces", "Study infrastructure", "Powell / YRL and 24-hour campus study options during peak terms."),
            ],
        ),
        "ecosystem_culture": _cat(
            "ecosystem_culture",
            "Ecosystem & Culture",
            "Highly international and industry-connected.",
            [
                _m("ecosystem_culture", "Ecosystem & Culture", "Large international cohort; entertainment networking culture is unique to LA."),
                _m("community", "Student community", "Active cultural clubs and industry student orgs (film, consulting, engineering)."),
            ],
        ),
        "funding_support": _cat(
            "funding_support",
            "Subsidies & Grants",
            "Institutional aid + limited state supports for internationals.",
            [
                _m("subsidies_grants", "Subsidies & Grants", "UCLA/USC merit & departmental awards; internationals rarely get federal need-based aid — verify early."),
                _m("work_study", "Work-study / on-campus aid", "On-campus employment and GSR/TA roles (graduate) are the practical offsets."),
            ],
        ),
    },
}


_COUNTRY_HABITAT_NOTES: dict[str, dict[str, str]] = {
    "US": {
        "funding": "Institution scholarships dominate for internationals; federal aid is usually unavailable.",
        "part_time": "On-campus work primary on F-1; CPT/OPT for authorized off-campus.",
        "insurance": "University health plans are typically mandatory.",
    },
    "CA": {
        "funding": "Entrance scholarships + provincial supports vary; SDS/GIC planning still critical.",
        "part_time": "On/off-campus work per IRCC student rules.",
        "insurance": "UHIP / provincial plans depending on province.",
    },
    "UK": {
        "funding": "University scholarships + occasional Chevening/external awards.",
        "part_time": "Typically up to 20 hrs/week in term on Student visa.",
        "insurance": "IHS covers NHS access for most Student visa holders.",
    },
    "AU": {
        "funding": "Australia Awards / university scholarships; OSHC is mandatory.",
        "part_time": "Student visa work-hour caps apply (confirm current Home Affairs rules).",
        "insurance": "OSHC required for Student visa.",
    },
    "DE": {
        "funding": "DAAD / Deutschlandstipendium / low public tuition is the main lever.",
        "part_time": "120 full / 240 half days typical student work framework.",
        "insurance": "Statutory/private health insurance mandatory.",
    },
    "PL": {
        "funding": "University fee waivers and NAWA-related opportunities — check annually.",
        "part_time": "Students often work without a separate permit (confirm current law).",
        "insurance": "Health insurance required for visa/residence.",
    },
}


def build_habitat(
    *,
    location_label: str,
    country_code: str | None = None,
    metro_key: str | None = None,
    city_living: FutureInsightsCityLiving | None = None,
) -> FutureInsightsHabitat:
    base = _default_pack(location_label=location_label, city=city_living, country_code=country_code)
    categories = {c.key: c for c in base.categories}

    code = (country_code or "").upper()
    if code == "GB":
        code = "UK"
    notes = _COUNTRY_HABITAT_NOTES.get(code or "", {})
    if notes:
        if "funding_support" in categories and notes.get("funding"):
            cats = list(categories["funding_support"].metrics)
            cats[0] = _m("subsidies_grants", "Subsidies & Grants", notes["funding"])
            categories["funding_support"] = categories["funding_support"].model_copy(update={"metrics": cats})
        if "income_careers" in categories and notes.get("part_time"):
            cats = list(categories["income_careers"].metrics)
            cats[2] = _m("jobs_part_time", "Jobs — Part-time", notes["part_time"])
            categories["income_careers"] = categories["income_careers"].model_copy(update={"metrics": cats})
        if "safety_health" in categories and notes.get("insurance"):
            cats = list(categories["safety_health"].metrics)
            for idx, metric in enumerate(cats):
                if metric.key == "health_insurance":
                    cats[idx] = _m("health_insurance", "Health Insurance", notes["insurance"])
            categories["safety_health"] = categories["safety_health"].model_copy(update={"metrics": cats})

    if metro_key and metro_key in _METRO_HABITAT:
        categories.update(_METRO_HABITAT[metro_key])

    ordered = [
        categories[key]
        for key, _title in HABITAT_CATEGORY_DEFS
        if key in categories
    ]
    return FutureInsightsHabitat(location_label=location_label, categories=ordered)
