from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.country import Country

DEFAULT_COUNTRIES: list[dict[str, str | int]] = [
    {"iso2": "IN", "name": "India", "dial_code": "91", "sort_order": 1},
    {"iso2": "US", "name": "United States", "dial_code": "1", "sort_order": 2},
    {"iso2": "GB", "name": "United Kingdom", "dial_code": "44", "sort_order": 3},
    {"iso2": "AE", "name": "United Arab Emirates", "dial_code": "971", "sort_order": 4},
    {"iso2": "SA", "name": "Saudi Arabia", "dial_code": "966", "sort_order": 5},
    {"iso2": "AU", "name": "Australia", "dial_code": "61", "sort_order": 6},
    {"iso2": "SG", "name": "Singapore", "dial_code": "65", "sort_order": 7},
    {"iso2": "PK", "name": "Pakistan", "dial_code": "92", "sort_order": 8},
    {"iso2": "BD", "name": "Bangladesh", "dial_code": "880", "sort_order": 9},
    {"iso2": "LK", "name": "Sri Lanka", "dial_code": "94", "sort_order": 10},
    {"iso2": "CA", "name": "Canada", "dial_code": "1", "sort_order": 11},
    {"iso2": "DE", "name": "Germany", "dial_code": "49", "sort_order": 12},
    {"iso2": "FR", "name": "France", "dial_code": "33", "sort_order": 13},
    {"iso2": "JP", "name": "Japan", "dial_code": "81", "sort_order": 14},
]


def seed_countries(db: Session) -> None:
    for item in DEFAULT_COUNTRIES:
        existing = db.query(Country).filter(Country.iso2 == item["iso2"]).first()
        if existing:
            existing.name = str(item["name"])
            existing.dial_code = str(item["dial_code"])
            existing.sort_order = int(item["sort_order"])
            existing.is_active = True
            continue
        db.add(
            Country(
                iso2=str(item["iso2"]),
                name=str(item["name"]),
                dial_code=str(item["dial_code"]),
                sort_order=int(item["sort_order"]),
                is_active=True,
            )
        )
    db.commit()


def list_active_countries(db: Session) -> list[Country]:
    return (
        db.query(Country)
        .filter(Country.is_active.is_(True))
        .order_by(Country.sort_order.asc(), Country.name.asc())
        .all()
    )


def get_country_by_iso2(db: Session, iso2: str) -> Country | None:
    normalized = (iso2 or "").strip().upper()
    if len(normalized) != 2:
        return None
    return (
        db.query(Country)
        .filter(Country.iso2 == normalized, Country.is_active.is_(True))
        .first()
    )
