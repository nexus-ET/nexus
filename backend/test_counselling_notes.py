from app.services.counselling_note_service import (
    _decode_universities,
    _encode_universities,
    _normalize_summarize_response,
    _parse_follow_up,
    _parse_summarize_payload,
    _summarize_has_structured_content,
)


def test_decode_universities_from_json():
    assert _decode_universities('["MIT", "Stanford"]') == ["MIT", "Stanford"]


def test_encode_universities():
    assert _encode_universities(["MIT", "Stanford"]) == '["MIT", "Stanford"]'


def test_parse_follow_up_iso_date():
    assert _parse_follow_up("2026-07-15") is not None
    assert str(_parse_follow_up("2026-07-15")) == "2026-07-15"


def test_parse_summarize_payload():
    payload = _parse_summarize_payload(
        '{"preferred_universities":["UK"],"scholarship_interests":"Merit aid",'
        '"career_goals":"Data scientist","recommendations":"Apply early",'
        '"next_follow_up":"2026-08-01"}'
    )
    assert payload.preferred_universities == ["UK"]
    assert payload.scholarship_interests == "Merit aid"
    assert payload.recommendations == "Apply early"
    assert str(payload.next_follow_up) == "2026-08-01"


def test_normalize_summarize_response_moves_transcript_dump_to_recommendations():
    raw = "Voice input and AI extraction for our session notes about Canada and MBA goals."
    parsed = _normalize_summarize_response(
        _parse_summarize_payload(
            '{"scholarship_interests": "Voice input and AI extraction for our session notes about Canada and MBA goals."}'
        ),
        raw,
    )
    assert parsed.scholarship_interests == ""
    assert "Voice input" in (parsed.recommendations or "")


def test_summarize_has_structured_content():
    assert _summarize_has_structured_content(
        _parse_summarize_payload('{"career_goals":"MBA in Canada"}')
    ) is True
    assert _summarize_has_structured_content(_parse_summarize_payload("{}")) is False
