from app.schemas.academia_hub import CollegeCreate
from app.schemas.contact_entry import ContactEntry, normalize_email_contacts, normalize_phone_contacts


def test_normalize_email_contacts_preserves_contact_entry_instances():
    entries = [ContactEntry(type="General", value="admissions@jhu.edu")]
    normalized = normalize_email_contacts(entries)
    assert len(normalized) == 1
    assert normalized[0].type == "General"
    assert normalized[0].value == "admissions@jhu.edu"


def test_normalize_phone_contacts_preserves_contact_entry_instances():
    entries = [ContactEntry(type="Main", value="+1 410 555 0100")]
    normalized = normalize_phone_contacts(entries)
    assert len(normalized) == 1
    assert normalized[0].type == "Main"
    assert normalized[0].value == "+1 410 555 0100"


def test_college_create_accepts_contact_entry_instances_from_wizard_payload():
    college = CollegeCreate(
        institution_id=1,
        campus_id=None,
        name="School of Medicine",
        phone_numbers=[ContactEntry(type="Main", value="+1 410 555 0100")],
        email_addresses=[ContactEntry(type="General", value="admissions@jhu.edu")],
        sort_order=0,
    )
    assert college.email_addresses[0].value == "admissions@jhu.edu"
    assert college.phone_numbers[0].value == "+1 410 555 0100"
