"""Tests for unified Meta Lead Ads ingestion (Facebook + Instagram)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

from app.services.facebook_leads import (
    MetaLeadsBackfillResult,
    _iter_graph_paginated,
    _lead_summary_to_event,
    _parse_created_time,
    backfill_historical_leads,
    extract_leadgen_events,
    map_platform_to_source,
    map_platform_to_channel,
    meta_created_time_to_utc_naive,
    resolve_backfill_credentials,
)
from app.models.lead import LeadChannel, LeadSource


class _FakeSaveResult:
    def __init__(self, *, created: bool):
        self.created = created
        self.lead = MagicMock(id=42)


def test_resolve_backfill_credentials_uses_env(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.facebook_leads.settings.META_PAGE_ID",
        "PAGE_ENV",
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.facebook_leads.settings.META_GRAPH_ACCESS_TOKEN",
        "TOKEN_ENV",
        raising=False,
    )
    page_id, token = resolve_backfill_credentials()
    assert page_id == "PAGE_ENV"
    assert token == "TOKEN_ENV"


def test_iter_graph_paginated_follows_next_links(monkeypatch) -> None:
    pages = [
        {
            "data": [{"id": "FORM_1"}],
            "paging": {"next": "https://graph.facebook.com/v20.0/next-page"},
        },
        {"data": [{"id": "FORM_2"}], "paging": {}},
    ]

    def fake_graph_get(url: str, *, params=None):
        assert pages, "unexpected extra Graph API call"
        payload = pages.pop(0)
        if params is not None:
            assert params["access_token"] == "TOKEN"
        else:
            assert url == "https://graph.facebook.com/v20.0/next-page"
        return payload

    monkeypatch.setattr("app.services.facebook_leads._graph_get_json", fake_graph_get)

    rows = list(
        _iter_graph_paginated(
            "PAGE/leadgen_forms",
            access_token="TOKEN",
            params={"fields": "id"},
            request_delay_seconds=0,
        )
    )
    assert [row["id"] for row in rows] == ["FORM_1", "FORM_2"]


def test_lead_summary_to_event_maps_ids() -> None:
    event = _lead_summary_to_event(
        {"id": "LEAD_99", "ad_id": "AD_1", "created_time": 1710000000},
        page_id="PAGE_1",
        form_id="FORM_1",
    )
    assert event is not None
    assert event.leadgen_id == "LEAD_99"
    assert event.page_id == "PAGE_1"
    assert event.form_id == "FORM_1"
    assert event.ad_id == "AD_1"
    assert event.created_time == 1710000000


def test_parse_created_time_accepts_iso_strings() -> None:
    iso_value = "2018-09-26T20:02:12+0000"
    parsed = _parse_created_time(iso_value)
    assert parsed is not None
    assert parsed == int(
        datetime.fromisoformat("2018-09-26T20:02:12+00:00")
        .astimezone(timezone.utc)
        .timestamp()
    )
    assert _parse_created_time("2018-09-26T20:02:12Z") == parsed


def test_meta_created_time_to_utc_naive() -> None:
    parsed = meta_created_time_to_utc_naive(1710000000)
    assert parsed == datetime.fromtimestamp(1710000000, tz=timezone.utc).replace(tzinfo=None)


def test_build_meta_lead_time_filter() -> None:
    from app.services.facebook_leads import build_meta_lead_time_filter

    assert build_meta_lead_time_filter(None) is None
    assert build_meta_lead_time_filter("1710000000") == [
        {"field": "time_created", "operator": "GREATER_THAN", "value": 1710000000}
    ]
    assert build_meta_lead_time_filter("1710000000", "1710003600") == [
        {"field": "time_created", "operator": "GREATER_THAN", "value": 1710000000},
        {"field": "time_created", "operator": "LESS_THAN", "value": 1710003600},
    ]


def test_iter_form_leads_uses_time_created_filtering(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []

    def fake_iter_graph_paginated(path, *, access_token, params=None, request_delay_seconds=0.0):
        captured.append({"path": path, "params": dict(params or {})})
        return iter([])

    monkeypatch.setattr("app.services.facebook_leads._iter_graph_paginated", fake_iter_graph_paginated)

    from app.services.facebook_leads import iter_form_leads

    list(iter_form_leads("FORM_1", "TOKEN", since="1710000000", request_delay_seconds=0))

    assert captured[0]["path"] == "FORM_1/leads"
    assert "since" not in captured[0]["params"]
    assert captured[0]["params"]["filtering"] == (
        '[{"field": "time_created", "operator": "GREATER_THAN", "value": 1710000000}]'
    )


def test_backfill_historical_leads_passes_since_filter(monkeypatch) -> None:
    db = MagicMock()
    seen_since: list[str | None] = []

    monkeypatch.setattr(
        "app.services.facebook_leads.fetch_leadgen_form_ids",
        lambda page_id, token, request_delay_seconds=1.0: ["FORM_1"],
    )

    def fake_iter_form_leads(form_id, token, since=None, until=None, request_delay_seconds=1.0):
        seen_since.append(since)
        return iter([])

    monkeypatch.setattr("app.services.facebook_leads.iter_form_leads", fake_iter_form_leads)
    monkeypatch.setattr(
        "app.services.facebook_leads.diagnose_meta_leads_access",
        lambda page_id, access_token: [],
    )
    monkeypatch.setattr(
        "app.services.facebook_leads.resolve_page_access_token",
        lambda page_id, access_token: "PAGE_TOKEN",
    )

    result = backfill_historical_leads(
        db,
        "PAGE_1",
        "TOKEN",
        since="1710000000",
        request_delay_seconds=0,
        delta_since_label="2024-03-09 13:20:00 UTC",
    )
    assert seen_since == ["1710000000"]
    assert result.leads_seen == 0
    assert result.delta_since_unix == "1710000000"
    assert result.delta_since_label == "2024-03-09 13:20:00 UTC"


def test_backfill_historical_leads_uses_sync_and_skips_existing(monkeypatch) -> None:
    db = MagicMock()

    monkeypatch.setattr(
        "app.services.facebook_leads.fetch_leadgen_form_ids",
        lambda page_id, token, request_delay_seconds=1.0: ["FORM_1"],
    )
    monkeypatch.setattr(
        "app.services.facebook_leads.iter_form_leads",
        lambda form_id, token, since=None, until=None, request_delay_seconds=1.0: [
            {"id": "LEAD_EXISTING", "created_time": 1},
            {"id": "LEAD_NEW", "created_time": 2},
        ],
    )

    monkeypatch.setattr(
        "app.services.leads.ingest_meta_leadgen_event_sync",
        lambda event, access_token=None: _FakeSaveResult(
            created=event.leadgen_id == "LEAD_NEW"
        ),
    )
    monkeypatch.setattr(
        "app.services.leads.meta_leadgen_id_exists",
        lambda leadgen_id: leadgen_id == "LEAD_EXISTING",
    )
    monkeypatch.setattr(
        "app.services.facebook_leads.diagnose_meta_leads_access",
        lambda page_id, access_token: [],
    )
    monkeypatch.setattr(
        "app.services.facebook_leads.resolve_page_access_token",
        lambda page_id, access_token: "PAGE_TOKEN",
    )

    def query_side_effect(model):
        return MagicMock()

    db.query.side_effect = query_side_effect

    result = backfill_historical_leads(
        db,
        "PAGE_1",
        "TOKEN",
        request_delay_seconds=0,
    )
    assert isinstance(result, MetaLeadsBackfillResult)
    assert result.forms_processed == 1
    assert result.leads_seen == 2
    assert result.leads_created == 1
    assert result.leads_skipped == 1


def test_extract_leadgen_events_parses_facebook_and_instagram_payloads() -> None:
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "PAGE_123",
                "changes": [
                    {
                        "field": "leadgen",
                        "value": {
                            "ad_id": "AD_1",
                            "form_id": "FORM_1",
                            "leadgen_id": "LEAD_1",
                            "created_time": 1710000000,
                            "page_id": "PAGE_123",
                        },
                    },
                    {
                        "field": "messages",
                        "value": {"messages": []},
                    },
                ],
            }
        ],
    }

    events = extract_leadgen_events(payload)
    assert len(events) == 1
    assert events[0].leadgen_id == "LEAD_1"
    assert events[0].page_id == "PAGE_123"
    assert events[0].form_id == "FORM_1"


def test_map_platform_to_source_and_channel() -> None:
    assert map_platform_to_source("instagram") == LeadSource.INSTAGRAM_LEAD
    assert map_platform_to_source("facebook") == LeadSource.FACEBOOK_LEAD
    assert map_platform_to_source(None) == LeadSource.FACEBOOK_LEAD

    assert map_platform_to_channel("instagram") == LeadChannel.INSTAGRAM
    assert map_platform_to_channel("facebook") == LeadChannel.FACEBOOK
