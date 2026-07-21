from __future__ import annotations

from types import SimpleNamespace

from app.services.candidate_profile_service import build_candidate_profile


class FakeCountry:
    def __init__(self, iso2: str, name: str, dial_code: str) -> None:
        self.iso2 = iso2
        self.name = name
        self.dial_code = dial_code


def test_build_candidate_profile_from_offline_additional_data(monkeypatch) -> None:
    from app.services import candidate_profile_service as service

    lead = SimpleNamespace(
        id=42,
        full_name="Jane Q Public",
        email="jane@example.com",
        phone_number="+919876543210",
        preferred_country="Australia",
        current_location="Mumbai, Maharashtra, India",
        additional_data={
            "first_name": "Jane",
            "middle_name": "Q",
            "last_name": "Public",
            "date_of_birth": "2001-05-12",
            "phone_country_iso2": "IN",
            "education": {
                "degree_code": "BACHELORS",
                "degree": "Bachelor's",
                "major": "Computer Science",
                "university": "Example University",
                "graduation_year": 2024,
                "gpa_cgpa_code": "GPA_3_5",
                "gpa_cgpa": "3.5 / 4.0",
            },
            "location": {
                "address1": "12 Main Street",
                "city": "Mumbai",
                "state": "Maharashtra",
                "country_iso2": "IN",
                "country": "India",
                "zipcode": "400001",
            },
            "target_destination_iso2": "AU",
            "target_destination": "Australia",
            "target_program_code": "COMPUTER_SCIENCE_IT",
            "target_program": "Computer Science & IT",
            "target_course_code": "BSC_COMPUTER_SCIENCE",
            "target_course": "BSc Computer Science",
        },
        intake_context=None,
    )

    countries = [
        FakeCountry("IN", "India", "91"),
        FakeCountry("AU", "Australia", "61"),
    ]

    monkeypatch.setattr(service, "list_active_countries", lambda db: countries)
    monkeypatch.setattr(
        service,
        "get_country_by_iso2",
        lambda db, iso2: next((country for country in countries if country.iso2 == iso2), None),
    )

    profile = build_candidate_profile(db=None, lead=lead, booking=None)  # type: ignore[arg-type]

    assert profile["first_name"] == "Jane"
    assert profile["education"]["major"] == "Computer Science"
    assert profile["location"]["address1"] == "12 Main Street"
    assert profile["study_interest"]["target_destination_iso2"] == "AU"
    assert profile["phone_local"] == "9876543210"
