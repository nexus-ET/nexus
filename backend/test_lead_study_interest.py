from types import SimpleNamespace

from app.services.lead_study_interest import (
    build_target_intake_task,
    enrich_lead_payload_from_meta_fields,
    hydrate_lead_study_interest,
    lead_has_complete_study_interest,
    resolve_lead_study_interest,
)
from app.services.intake_templates import render_deterministic_intake_text, render_outreach_intake_followup


def test_resolve_lead_study_interest_from_meta_additional_data():
    lead = SimpleNamespace(
        preferred_country=None,
        additional_data={
            "preferred_country": "UK",
            "preferred_course_university": "Fashion Design",
        },
        intake_context=None,
    )
    study = resolve_lead_study_interest(lead)  # type: ignore[arg-type]
    assert study["country"] == "UK"
    assert study["course"] == "Fashion Design"
    assert lead_has_complete_study_interest(lead) is True  # type: ignore[arg-type]


def test_enrich_lead_payload_from_meta_fields():
    payload = enrich_lead_payload_from_meta_fields(
        {
            "additional_data": {
                "preferred_country": "Canada",
                "preferred_course_university": "MBA",
            }
        }
    )
    assert payload["preferred_country"] == "Canada"
    assert "preferred_course" in payload["intake_context"]


def test_hydrate_lead_study_interest_promotes_meta_fields():
    lead = SimpleNamespace(
        preferred_country=None,
        additional_data={"preferred_country": "Germany", "target_program": "MSc CS"},
        intake_context=None,
    )

    class FakeSession:
        def commit(self):
            pass

        def refresh(self, obj):
            pass

    changed = hydrate_lead_study_interest(FakeSession(), lead, commit=True)  # type: ignore[arg-type]
    assert changed is True
    assert lead.preferred_country == "Germany"
    assert lead.intake_context is not None


def test_build_target_intake_task_skips_when_country_prefilled():
    lead = SimpleNamespace(
        preferred_country="UK",
        additional_data={},
        intake_context=None,
    )
    task = build_target_intake_task(lead)  # type: ignore[arg-type]
    assert "course/program missing" in task
    assert "UK" in task
    assert "Ask only for course/program" in task


def test_build_target_intake_task_asks_both_when_blank():
    lead = SimpleNamespace(
        preferred_country=None,
        additional_data={},
        intake_context=None,
    )
    task = build_target_intake_task(lead)  # type: ignore[arg-type]
    assert "destination country and course/program" in task


def test_target_template_asks_only_course_when_country_prefilled():
    lead = SimpleNamespace(
        full_name="Priya Sharma",
        preferred_country="UK",
        intake_context='{"pending_country": "UK"}',
    )
    text = render_deterministic_intake_text(
        lead,  # type: ignore[arg-type]
        task=build_target_intake_task(lead),  # type: ignore[arg-type]
    )
    assert "UK" in text
    assert "course or program" in text.lower()
    assert "which country would you like to study in" not in text.lower()


def test_outreach_intake_followup_uses_consultation_prompt_only() -> None:
    text = render_outreach_intake_followup()
    assert text == "To book your free study abroad consultation, simply reply with your full name."
    assert "Admissions assistant" not in text
    assert "Hi " not in text
