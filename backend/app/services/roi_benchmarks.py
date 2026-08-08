"""Numeric ROI calculator benchmarks (server-seeded; not hardcoded in React)."""

from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.schemas.nexus_intel import RoiBenchmarkInputs, RoiBenchmarkResponse
from app.services.future_insights_metros import match_metro_key, metro_location_label

_AS_OF = date.today().isoformat()
_DISCLAIMER = (
    "Counsellor modelling aid only — not financial, tax, or immigration advice. "
    "Benchmarks are indicative midpoints; always verify with offers and official sources."
)

_ISO2_TO_INTEL = {"GB": "UK"}
_INTEL_TO_ISO2 = {"UK": "GB"}


def _normalize(code: str) -> str:
    upper = (code or "").strip().upper()
    return _ISO2_TO_INTEL.get(upper, upper)


def _iso2(intel: str) -> str:
    return _INTEL_TO_ISO2.get(intel, intel)


def _inputs(**kwargs) -> RoiBenchmarkInputs:
    return RoiBenchmarkInputs(**kwargs)


# Country-level midpoint benchmarks in local currency.
_COUNTRY: dict[str, RoiBenchmarkInputs] = {
    "US": _inputs(
        currency="USD",
        program_years=2,
        annual_tuition=35000,
        visa_fees=500,
        health_insurance_annual=2500,
        books_supplies_annual=1200,
        monthly_rent=1600,
        monthly_groceries=400,
        monthly_transit=120,
        monthly_other_living=200,
        destination_starting_salary=65000,
        destination_salary_growth=0.045,
        destination_effective_tax_rate=0.24,
        home_counterfactual_salary=18000,
        home_salary_growth=0.04,
        home_effective_tax_rate=0.15,
        part_time_earnings_annual=6000,
    ),
    "CA": _inputs(
        currency="CAD",
        program_years=2,
        annual_tuition=28000,
        visa_fees=250,
        health_insurance_annual=900,
        books_supplies_annual=1000,
        monthly_rent=1400,
        monthly_groceries=350,
        monthly_transit=120,
        monthly_other_living=180,
        destination_starting_salary=55000,
        destination_salary_growth=0.04,
        destination_effective_tax_rate=0.26,
        home_counterfactual_salary=18000,
        part_time_earnings_annual=8000,
    ),
    "UK": _inputs(
        currency="GBP",
        program_years=1,
        annual_tuition=22000,
        visa_fees=490,
        health_insurance_annual=776,  # IHS-style annualised placeholder
        books_supplies_annual=800,
        monthly_rent=1100,
        monthly_groceries=280,
        monthly_transit=150,
        monthly_other_living=160,
        destination_starting_salary=32000,
        destination_salary_growth=0.035,
        destination_effective_tax_rate=0.25,
        home_counterfactual_salary=15000,
        part_time_earnings_annual=5000,
    ),
    "AU": _inputs(
        currency="AUD",
        program_years=2,
        annual_tuition=32000,
        visa_fees=700,
        health_insurance_annual=700,
        books_supplies_annual=900,
        monthly_rent=1500,
        monthly_groceries=380,
        monthly_transit=140,
        monthly_other_living=180,
        destination_starting_salary=65000,
        destination_salary_growth=0.04,
        destination_effective_tax_rate=0.27,
        home_counterfactual_salary=18000,
        part_time_earnings_annual=9000,
    ),
    "DE": _inputs(
        currency="EUR",
        program_years=2,
        annual_tuition=1500,
        visa_fees=100,
        health_insurance_annual=1440,
        books_supplies_annual=600,
        monthly_rent=700,
        monthly_groceries=250,
        monthly_transit=60,
        monthly_other_living=120,
        destination_starting_salary=48000,
        destination_salary_growth=0.035,
        destination_effective_tax_rate=0.30,
        home_counterfactual_salary=15000,
        part_time_earnings_annual=5000,
    ),
    "FR": _inputs(
        currency="EUR",
        program_years=2,
        annual_tuition=4000,
        visa_fees=100,
        health_insurance_annual=300,
        books_supplies_annual=600,
        monthly_rent=850,
        monthly_groceries=280,
        monthly_transit=75,
        monthly_other_living=140,
        destination_starting_salary=38000,
        destination_salary_growth=0.03,
        destination_effective_tax_rate=0.28,
        home_counterfactual_salary=15000,
        part_time_earnings_annual=4000,
    ),
    "IE": _inputs(
        currency="EUR",
        program_years=1,
        annual_tuition=16000,
        visa_fees=300,
        health_insurance_annual=600,
        books_supplies_annual=700,
        monthly_rent=1200,
        monthly_groceries=300,
        monthly_transit=120,
        monthly_other_living=150,
        destination_starting_salary=38000,
        destination_salary_growth=0.04,
        destination_effective_tax_rate=0.28,
        home_counterfactual_salary=15000,
        part_time_earnings_annual=5000,
    ),
    "NL": _inputs(
        currency="EUR",
        program_years=2,
        annual_tuition=14000,
        visa_fees=210,
        health_insurance_annual=1500,
        books_supplies_annual=700,
        monthly_rent=900,
        monthly_groceries=280,
        monthly_transit=90,
        monthly_other_living=140,
        destination_starting_salary=42000,
        destination_salary_growth=0.035,
        destination_effective_tax_rate=0.32,
        home_counterfactual_salary=15000,
        part_time_earnings_annual=4500,
    ),
    "NO": _inputs(
        currency="NOK",
        program_years=2,
        annual_tuition=0,
        visa_fees=6000,
        health_insurance_annual=0,
        books_supplies_annual=8000,
        monthly_rent=9000,
        monthly_groceries=4500,
        monthly_transit=800,
        monthly_other_living=1500,
        destination_starting_salary=520000,
        destination_salary_growth=0.03,
        destination_effective_tax_rate=0.30,
        home_counterfactual_salary=300000,
        part_time_earnings_annual=40000,
    ),
    "SE": _inputs(
        currency="SEK",
        program_years=2,
        annual_tuition=140000,
        visa_fees=1500,
        health_insurance_annual=0,
        books_supplies_annual=6000,
        monthly_rent=7000,
        monthly_groceries=3500,
        monthly_transit=900,
        monthly_other_living=1200,
        destination_starting_salary=370000,
        destination_salary_growth=0.03,
        destination_effective_tax_rate=0.30,
        home_counterfactual_salary=250000,
        part_time_earnings_annual=35000,
    ),
    "CH": _inputs(
        currency="CHF",
        program_years=2,
        annual_tuition=1500,
        visa_fees=200,
        health_insurance_annual=3600,
        books_supplies_annual=800,
        monthly_rent=1400,
        monthly_groceries=450,
        monthly_transit=90,
        monthly_other_living=200,
        destination_starting_salary=80000,
        destination_salary_growth=0.03,
        destination_effective_tax_rate=0.22,
        home_counterfactual_salary=20000,
        part_time_earnings_annual=6000,
    ),
    "JP": _inputs(
        currency="JPY",
        program_years=2,
        annual_tuition=900000,
        visa_fees=10000,
        health_insurance_annual=40000,
        books_supplies_annual=50000,
        monthly_rent=70000,
        monthly_groceries=35000,
        monthly_transit=10000,
        monthly_other_living=15000,
        destination_starting_salary=4200000,
        destination_salary_growth=0.025,
        destination_effective_tax_rate=0.18,
        home_counterfactual_salary=1500000,
        part_time_earnings_annual=600000,
    ),
    "NZ": _inputs(
        currency="NZD",
        program_years=2,
        annual_tuition=30000,
        visa_fees=400,
        health_insurance_annual=700,
        books_supplies_annual=900,
        monthly_rent=1300,
        monthly_groceries=350,
        monthly_transit=120,
        monthly_other_living=160,
        destination_starting_salary=58000,
        destination_salary_growth=0.035,
        destination_effective_tax_rate=0.24,
        home_counterfactual_salary=18000,
        part_time_earnings_annual=8000,
    ),
    "SG": _inputs(
        currency="SGD",
        program_years=2,
        annual_tuition=35000,
        visa_fees=100,
        health_insurance_annual=600,
        books_supplies_annual=800,
        monthly_rent=1400,
        monthly_groceries=400,
        monthly_transit=120,
        monthly_other_living=200,
        destination_starting_salary=48000,
        destination_salary_growth=0.04,
        destination_effective_tax_rate=0.10,
        home_counterfactual_salary=18000,
        part_time_earnings_annual=3000,
    ),
    "AE": _inputs(
        currency="AED",
        program_years=2,
        annual_tuition=70000,
        visa_fees=2000,
        health_insurance_annual=4000,
        books_supplies_annual=2000,
        monthly_rent=4500,
        monthly_groceries=1200,
        monthly_transit=400,
        monthly_other_living=600,
        destination_starting_salary=120000,
        destination_salary_growth=0.04,
        destination_effective_tax_rate=0.0,
        home_counterfactual_salary=60000,
        part_time_earnings_annual=0,
    ),
    "HK": _inputs(
        currency="HKD",
        program_years=1,
        annual_tuition=180000,
        visa_fees=600,
        health_insurance_annual=4000,
        books_supplies_annual=5000,
        monthly_rent=12000,
        monthly_groceries=3500,
        monthly_transit=600,
        monthly_other_living=1500,
        destination_starting_salary=280000,
        destination_salary_growth=0.04,
        destination_effective_tax_rate=0.12,
        home_counterfactual_salary=120000,
        part_time_earnings_annual=20000,
    ),
    "MY": _inputs(
        currency="MYR",
        program_years=2,
        annual_tuition=35000,
        visa_fees=500,
        health_insurance_annual=1200,
        books_supplies_annual=1500,
        monthly_rent=1200,
        monthly_groceries=600,
        monthly_transit=150,
        monthly_other_living=250,
        destination_starting_salary=48000,
        destination_salary_growth=0.04,
        destination_effective_tax_rate=0.12,
        home_counterfactual_salary=24000,
        part_time_earnings_annual=6000,
    ),
    "PL": _inputs(
        currency="PLN",
        program_years=2,
        annual_tuition=16000,
        visa_fees=400,
        health_insurance_annual=1200,
        books_supplies_annual=1500,
        monthly_rent=2200,
        monthly_groceries=900,
        monthly_transit=150,
        monthly_other_living=300,
        destination_starting_salary=78000,
        destination_salary_growth=0.04,
        destination_effective_tax_rate=0.20,
        home_counterfactual_salary=36000,
        part_time_earnings_annual=12000,
    ),
    "QA": _inputs(
        currency="QAR",
        program_years=2,
        annual_tuition=80000,
        visa_fees=1000,
        health_insurance_annual=3000,
        books_supplies_annual=2000,
        monthly_rent=4000,
        monthly_groceries=1200,
        monthly_transit=300,
        monthly_other_living=500,
        destination_starting_salary=140000,
        destination_salary_growth=0.035,
        destination_effective_tax_rate=0.0,
        home_counterfactual_salary=50000,
        part_time_earnings_annual=0,
    ),
    "IN": _inputs(
        currency="INR",
        program_years=2,
        annual_tuition=250000,
        visa_fees=0,
        health_insurance_annual=15000,
        books_supplies_annual=20000,
        monthly_rent=15000,
        monthly_groceries=6000,
        monthly_transit=2000,
        monthly_other_living=3000,
        destination_starting_salary=600000,
        destination_salary_growth=0.06,
        destination_effective_tax_rate=0.15,
        home_counterfactual_salary=360000,
        part_time_earnings_annual=0,
    ),
    "RU": _inputs(
        currency="RUB",
        program_years=2,
        annual_tuition=350000,
        visa_fees=10000,
        health_insurance_annual=20000,
        books_supplies_annual=25000,
        monthly_rent=35000,
        monthly_groceries=15000,
        monthly_transit=2500,
        monthly_other_living=8000,
        destination_starting_salary=900000,
        destination_salary_growth=0.04,
        destination_effective_tax_rate=0.13,
        home_counterfactual_salary=480000,
        part_time_earnings_annual=120000,
    ),
}

# Metro overrides (partial field updates).
_METRO_OVERRIDES: dict[str, dict] = {
    "los-angeles": {
        "monthly_rent": 2200,
        "monthly_groceries": 450,
        "monthly_transit": 100,
        "destination_starting_salary": 72000,
        "health_insurance_annual": 2800,
        "annual_tuition": 38000,
    },
    "san-francisco-bay": {
        "monthly_rent": 2800,
        "monthly_groceries": 500,
        "destination_starting_salary": 95000,
        "annual_tuition": 42000,
    },
    "new-york": {
        "monthly_rent": 2600,
        "monthly_groceries": 480,
        "monthly_transit": 132,
        "destination_starting_salary": 80000,
    },
    "boston": {
        "monthly_rent": 2200,
        "destination_starting_salary": 75000,
    },
    "seattle": {
        "monthly_rent": 2000,
        "destination_starting_salary": 85000,
    },
    "toronto": {
        "monthly_rent": 1800,
        "destination_starting_salary": 60000,
    },
    "vancouver": {
        "monthly_rent": 1900,
        "destination_starting_salary": 58000,
    },
    "london": {
        "monthly_rent": 1400,
        "destination_starting_salary": 36000,
        "health_insurance_annual": 776,
    },
    "sydney": {
        "monthly_rent": 1800,
        "destination_starting_salary": 70000,
    },
    "melbourne": {
        "monthly_rent": 1600,
        "destination_starting_salary": 65000,
    },
    "berlin": {
        "monthly_rent": 750,
        "destination_starting_salary": 48000,
    },
    "tokyo": {
        "monthly_rent": 90000,
        "destination_starting_salary": 4500000,
    },
    "paris": {
        "monthly_rent": 1000,
        "destination_starting_salary": 40000,
    },
    "dublin": {
        "monthly_rent": 1500,
        "destination_starting_salary": 42000,
    },
    "amsterdam": {
        "monthly_rent": 1200,
        "destination_starting_salary": 45000,
    },
    "warsaw": {
        "monthly_rent": 2800,
        "destination_starting_salary": 90000,
    },
    "singapore-city": {
        "monthly_rent": 1600,
        "destination_starting_salary": 52000,
    },
    "dubai": {
        "monthly_rent": 5000,
        "destination_starting_salary": 140000,
    },
    "hong-kong-island": {
        "monthly_rent": 16000,
        "destination_starting_salary": 300000,
    },
}


def _apply_override(base: RoiBenchmarkInputs, override: dict) -> RoiBenchmarkInputs:
    data = base.model_dump()
    data.update(override)
    return RoiBenchmarkInputs(**data)


def get_roi_benchmarks(
    *,
    country_code: str,
    metro_key: str | None = None,
    institution_id: int | None = None,
    db: Session | None = None,
) -> RoiBenchmarkResponse:
    intel = _normalize(country_code)
    if intel not in _COUNTRY:
        raise HTTPException(status_code=400, detail=f"Unsupported country for ROI benchmarks: {country_code}")

    institution_name: str | None = None
    city_name: str | None = None
    state_name: str | None = None
    resolved_metro = metro_key

    if institution_id and db is not None:
        from app.models.academia_geography import GeographyCity, GeographyState
        from app.models.academia_institution import Institution
        from app.models.country import Country

        row = db.query(Institution).filter(Institution.id == institution_id).first()
        if row:
            institution_name = row.name
            city = (
                db.query(GeographyCity).filter(GeographyCity.id == row.city_id).first()
                if row.city_id
                else None
            )
            state = (
                db.query(GeographyState).filter(GeographyState.id == row.state_id).first()
                if row.state_id
                else None
            )
            city_name = city.name if city else None
            state_name = state.name if state else None
            if row.country_id:
                country = db.query(Country).filter(Country.id == row.country_id).first()
                if country and country.iso2:
                    intel = _normalize(country.iso2)
            if not resolved_metro:
                resolved_metro = match_metro_key(
                    country_code=intel,
                    institution_name=row.name,
                    city_name=city_name,
                    state_name=state_name,
                )

    if intel not in _COUNTRY:
        raise HTTPException(status_code=400, detail=f"Unsupported country for ROI benchmarks: {intel}")

    base = _COUNTRY[intel]
    if resolved_metro and resolved_metro in _METRO_OVERRIDES:
        inputs = _apply_override(base, _METRO_OVERRIDES[resolved_metro])
    else:
        inputs = base.model_copy()

    fallback = ", ".join(p for p in [city_name, state_name, _iso2(intel)] if p) or _iso2(intel)
    location_label = metro_location_label(resolved_metro, fallback)
    if institution_name:
        location_label = f"{institution_name} · {location_label}"

    notes = [
        f"Benchmarks in {inputs.currency} for {_iso2(intel)}"
        + (f" / {resolved_metro}" if resolved_metro else "")
        + ".",
        "Home counterfactual salary defaults to a typical origin-market graduate band — edit for the student.",
        "Effective tax rates are simplified averages for modelling, not filing advice.",
    ]

    return RoiBenchmarkResponse(
        country_code=intel,
        country_iso2=_iso2(intel),
        metro_key=resolved_metro,
        location_label=location_label,
        institution_id=institution_id,
        institution_name=institution_name,
        as_of=_AS_OF,
        disclaimer=_DISCLAIMER,
        inputs=inputs,
        notes=notes,
    )
