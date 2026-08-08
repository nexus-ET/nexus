"""FX helpers for ROI calculator INR equivalents."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import httpx
from fastapi import HTTPException

from app.schemas.nexus_intel import FxRateResponse

# Last-resort mid-market approximations if the live feed is unreachable.
_FALLBACK_TO_INR: dict[str, float] = {
    "INR": 1.0,
    "USD": 83.5,
    "CAD": 61.0,
    "GBP": 106.0,
    "EUR": 90.0,
    "AUD": 55.0,
    "NZD": 50.0,
    "SGD": 62.0,
    "JPY": 0.56,
    "CHF": 95.0,
    "HKD": 10.7,
    "MYR": 18.5,
    "AED": 22.7,
    "QAR": 22.9,
    "SEK": 7.8,
    "NOK": 7.6,
    "PLN": 21.0,
    "RUB": 0.95,
}


def _parse_as_of(raw: str | None) -> date:
    if not raw:
        return date.today()
    try:
        return datetime.strptime(raw.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def _frankfurter_url(base: str, quote: str, as_of: date) -> str:
    # Public Frankfurter v1 API (ECB-derived). Query uses base/symbols.
    if as_of >= date.today():
        return f"https://api.frankfurter.dev/v1/latest?base={base}&symbols={quote}"
    return f"https://api.frankfurter.dev/v1/{as_of.isoformat()}?base={base}&symbols={quote}"


def fetch_fx_rate(*, base: str, quote: str = "INR", as_of: str | None = None) -> FxRateResponse:
    base_c = (base or "").strip().upper()
    quote_c = (quote or "INR").strip().upper()
    if not base_c or not quote_c:
        raise HTTPException(status_code=400, detail="base and quote currencies are required")
    if base_c == quote_c:
        return FxRateResponse(
            base=base_c,
            quote=quote_c,
            rate=1.0,
            as_of=_parse_as_of(as_of).isoformat(),
            source="identity",
            notes=["Same currency — rate is 1."],
        )

    day = _parse_as_of(as_of)
    notes: list[str] = []
    # Frankfurter has no weekend quotes — walk back a few days.
    last_error: str | None = None
    for offset in range(0, 6):
        try_day = day - timedelta(days=offset)
        url = _frankfurter_url(base_c, quote_c, try_day)
        try:
            with httpx.Client(
                timeout=8.0,
                headers={"User-Agent": "NexusROI/1.0"},
                follow_redirects=True,
            ) as client:
                resp = client.get(url)
            if resp.status_code >= 400:
                last_error = f"HTTP {resp.status_code}"
                continue
            payload = resp.json()
            rates = payload.get("rates") or {}
            rate = rates.get(quote_c)
            if rate is None:
                last_error = f"No {quote_c} rate in response"
                continue
            as_of_out = str(payload.get("date") or try_day.isoformat())
            if offset:
                notes.append(f"Rolled back to {as_of_out} (market closed on requested date).")
            return FxRateResponse(
                base=base_c,
                quote=quote_c,
                rate=float(rate),
                as_of=as_of_out,
                source="frankfurter",
                notes=notes,
            )
        except Exception as exc:  # noqa: BLE001 — fall through to fallback
            last_error = str(exc)
            continue

    # Cross via USD if direct pair missing (e.g. some exotic bases).
    if base_c != "USD" and quote_c == "INR":
        try:
            usd_inr = fetch_fx_rate(base="USD", quote="INR", as_of=as_of)
            base_usd = fetch_fx_rate(base=base_c, quote="USD", as_of=as_of)
            return FxRateResponse(
                base=base_c,
                quote="INR",
                rate=float(base_usd.rate) * float(usd_inr.rate),
                as_of=usd_inr.as_of,
                source="frankfurter-cross",
                notes=["Cross rate via USD."] + usd_inr.notes + base_usd.notes,
            )
        except Exception:  # noqa: BLE001
            pass

    fallback = _FALLBACK_TO_INR.get(base_c)
    if quote_c == "INR" and fallback is not None:
        return FxRateResponse(
            base=base_c,
            quote=quote_c,
            rate=fallback,
            as_of=day.isoformat(),
            source="fallback",
            notes=[
                f"Live FX unavailable ({last_error or 'unknown'}); using indicative fallback mid-rate.",
            ],
        )

    raise HTTPException(
        status_code=502,
        detail=f"Unable to fetch FX rate {base_c}/{quote_c}: {last_error or 'unknown error'}",
    )
