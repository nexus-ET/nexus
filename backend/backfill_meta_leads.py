#!/usr/bin/env python
"""One-time historical sync of Meta Lead Ads into Nexus."""

from __future__ import annotations

import argparse
import sys

from app.db.database import SessionLocal
from app.db.register_models import register_all_models
from app.services.facebook_leads import (
    backfill_historical_leads,
    diagnose_meta_leads_access,
    resolve_backfill_credentials,
)
from app.services.leads import resolve_delta_sync_cursor


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill historical Meta Lead Ads for a Facebook Page into Nexus.",
    )
    parser.add_argument(
        "--page-id",
        help="Facebook Page ID (defaults to META_PAGE_ID in .env).",
    )
    parser.add_argument(
        "--access-token",
        help="Page Access Token with leads_retrieval (defaults to META_GRAPH_ACCESS_TOKEN).",
    )
    parser.add_argument(
        "--since",
        help="Optional start filter for leads (YYYY-MM-DD or Unix timestamp).",
    )
    parser.add_argument(
        "--until",
        help="Optional end filter for leads (YYYY-MM-DD or Unix timestamp).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds to pause between Graph API calls (default: 1.0).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate token + page access only; do not import leads.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        page_id, access_token = resolve_backfill_credentials(
            page_id=args.page_id,
            access_token=args.access_token,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.check:
        findings = diagnose_meta_leads_access(page_id, access_token)
        if findings:
            print("Meta Lead Ads access check failed:")
            for item in findings:
                print(f"  - {item}")
            return 1
        print("Meta Lead Ads access check passed.")
        print(f"  Page ID: {page_id}")
        return 0

    register_all_models()
    db = SessionLocal()
    try:
        since = args.since
        delta_label = None
        delta_initial = False
        if since is None:
            cursor = resolve_delta_sync_cursor(db)
            since = cursor.since_unix
            delta_label = cursor.since_label
            delta_initial = cursor.is_initial_backfill
            print(
                f"Delta sync since {delta_label} "
                f"({'initial 30-day window' if delta_initial else 'latest stored lead'})"
            )
        result = backfill_historical_leads(
            db,
            page_id,
            access_token,
            since=since,
            until=args.until,
            request_delay_seconds=max(0.0, args.delay),
            delta_since_label=delta_label,
            delta_is_initial_backfill=delta_initial,
        )
    finally:
        db.close()

    print("Meta Lead Ads historical backfill complete")
    print(f"  Page ID:         {page_id}")
    print(f"  Forms processed: {result.forms_processed}")
    print(f"  Leads seen:      {result.leads_seen}")
    print(f"  Leads created:   {result.leads_created}")
    print(f"  Leads skipped:   {result.leads_skipped}")
    if result.errors:
        print(f"  Errors ({len(result.errors)}):")
        for error in result.errors:
            print(f"    - {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
