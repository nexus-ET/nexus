"""Checklist email body lists serial and title only."""

from app.services.document_checklist_email_service import _build_email_bodies


def test_checklist_email_body_is_serial_then_title_only():
    plain, html = _build_email_bodies(
        business_name="EduTrust",
        student_name="Ishan",
        level_name="Undergraduate",
        country_name="Canada",
        checklist_rows=[
            {"document_name": "Passport", "accepted_format": "PDF Only"},
            {
                "document_name": "Academic transcripts",
                "accepted_format": "PDF, JPEG, or PNG",
            },
            {"document_name": "  English test score  ", "accepted_format": ""},
        ],
        attached_template_names=[],
    )

    assert "1. Passport" in plain
    assert "2. Academic transcripts" in plain
    assert "3. English test score" in plain
    assert "1. Passport" in html
    assert "2. Academic transcripts" in html
    assert "3. English test score" in html

    for body in (plain, html):
        assert "Accepted format" not in body
        assert "PDF Only" not in body
        assert "PDF, JPEG, or PNG" not in body
        assert "specified formats" not in body

    assert "Dear Ishan," in plain
    assert "Ensure the total file size of all documents is under 5MB." in plain
    assert "Best regards," in plain
    assert "Edutrust Global Admissions" in plain
    assert "Edutrust Global Admissions" in html
    assert "EduTrust Team" not in plain
    assert "Edutrust Overseas Education Team" not in plain
