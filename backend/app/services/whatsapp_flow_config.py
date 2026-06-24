from __future__ import annotations

import os
from datetime import datetime


def is_whatsapp_flow_enabled() -> bool:
    return bool(os.getenv("WHATSAPP_FLOW_ID", "").strip())


def get_whatsapp_flow_id() -> str:
    return os.getenv("WHATSAPP_FLOW_ID", "").strip()


def build_flow_token(lead_id: int) -> str:
    return f"nexus-lead-{lead_id}-{int(datetime.utcnow().timestamp())}"


def parse_lead_id_from_flow_token(flow_token: str) -> int | None:
    if not flow_token:
        return None
    parts = flow_token.split("-")
    if len(parts) >= 3 and parts[0] == "nexus" and parts[1] == "lead":
        try:
            return int(parts[2])
        except ValueError:
            return None
    return None
