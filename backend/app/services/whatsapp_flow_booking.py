from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.services.admissions_intake_flow import (
    _available_times_for_date,
    _finalize_consultation_booking,
    _format_slot_date,
    _format_slot_time,
    _load_context,
    _parse_time_selection,
    _save_context,
    ensure_consultation_slots,
)
from app.services.whatsapp_flow_config import parse_lead_id_from_flow_token

FLOW_JSON_PATH = (
    Path(__file__).resolve().parents[1] / "assets" / "whatsapp_flows" / "consultation_booking.json"
)


def get_flow_json_template() -> dict[str, Any]:
    return json.loads(FLOW_JSON_PATH.read_text(encoding="utf-8"))


def _booking_window() -> tuple[str, str]:
    today = date.today()
    max_day = today + timedelta(days=21)
    return today.isoformat(), max_day.isoformat()


def build_initial_flow_data(db: Session) -> dict[str, Any]:
    ensure_consultation_slots(db)
    min_date, max_date = _booking_window()
    return {
        "min_date": min_date,
        "max_date": max_date,
        "available_times": [],
        "selected_date_label": "Select a date to load available times.",
    }


def handle_flow_data_exchange(db: Session, decrypted: dict[str, Any]) -> dict[str, Any]:
    action = decrypted.get("action")
    data = decrypted.get("data") or {}
    screen = decrypted.get("screen") or "BOOKING"
    flow_token = decrypted.get("flow_token") or ""
    lead_id = parse_lead_id_from_flow_token(flow_token)

    if action == "ping":
        return {"data": {"status": "active"}}

    if action == "INIT":
        return {"screen": "BOOKING", "data": build_initial_flow_data(db)}

    selected_raw = data.get("selected_date") or (decrypted.get("payload") or {}).get("selected_date")
    if not selected_raw and action == "data_exchange":
        selected_raw = (decrypted.get("payload") or {}).get("selected_date")

    if action == "data_exchange" and selected_raw:
        try:
            selected_date = date.fromisoformat(str(selected_raw)[:10])
        except ValueError:
            return {
                "screen": "BOOKING",
                "data": {
                    **build_initial_flow_data(db),
                    "selected_date_label": "Could not read that date. Please pick again.",
                },
            }

        if lead_id:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if lead:
                context = _load_context(lead)
                context["selected_date"] = selected_date.isoformat()
                _save_context(db, lead, context)

        slots = _available_times_for_date(db, selected_date)
        available_times = [
            {"id": f"time:{slot.id}", "title": _format_slot_time(slot.slot_time)} for slot in slots[:10]
        ]
        min_date, max_date = _booking_window()
        return {
            "screen": "BOOKING",
            "data": {
                "min_date": min_date,
                "max_date": max_date,
                "available_times": available_times,
                "selected_date_label": f"Selected: {_format_slot_date(selected_date)}. Now choose a time.",
            },
        }

    return {"screen": screen, "data": build_initial_flow_data(db)}


def complete_booking_from_flow(
    db: Session,
    lead: Lead,
    selected_date_raw: str,
    selected_time_raw: str,
) -> str:
    selected_date = date.fromisoformat(str(selected_date_raw)[:10])
    slots = _available_times_for_date(db, selected_date)
    context = _load_context(lead)
    context["selected_date"] = selected_date.isoformat()
    context["time_slot_ids"] = [slot.id for slot in slots]
    _save_context(db, lead, context)

    choice = _parse_time_selection(str(selected_time_raw), slots, context)
    if choice is None:
        choice = _parse_time_selection(f"time:{selected_time_raw}", slots, context)
    if choice is None:
        raise ValueError("Could not match the selected time slot.")

    first = (lead.full_name or "there").split()[0]
    reply = _finalize_consultation_booking(db, lead, selected_date, slots[choice - 1].id, first)
    return reply.text


def parse_flow_completion_payload(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    return json.loads(raw)
