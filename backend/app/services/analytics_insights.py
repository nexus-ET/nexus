from __future__ import annotations

import json
import os
from typing import Any, Literal

ChartType = Literal["funnel", "channel", "ai_efficacy", "velocity"]


def _heuristic_explain(chart_type: ChartType, data: dict[str, Any]) -> str:
    if chart_type == "funnel":
        weeks = data.get("weeks") or []
        if len(weeks) < 2:
            return "Not enough weekly funnel history yet to identify a trend. Add more lead activity to unlock week-over-week insights."
        latest = weeks[-1]
        previous = weeks[-2]
        inquiry_delta = latest.get("inquiry", 0) - previous.get("inquiry", 0)
        enrolled_delta = latest.get("enrolled", 0) - previous.get("enrolled", 0)
        if inquiry_delta > 0 and enrolled_delta <= 0:
            return (
                f"Inquiries rose by {inquiry_delta} week-over-week while enrollments stayed flat, "
                "which suggests more top-of-funnel volume without downstream conversion improvements."
            )
        if latest.get("conversion_rate", 0) < previous.get("conversion_rate", 0):
            return (
                f"Conversion dipped from {previous.get('conversion_rate', 0)}% to {latest.get('conversion_rate', 0)}%, "
                "often a sign that newer inquiries need stronger qualification or advisor follow-up."
            )
        return (
            f"Enrollment conversion improved to {latest.get('conversion_rate', 0)}% this week with {latest.get('enrolled', 0)} closes, "
            "indicating healthier movement from inquiry to enrolled."
        )

    if chart_type == "channel":
        channels = data.get("channels") or []
        if not channels:
            return "No channel activity was found for this period. Expand the date range or verify lead source tagging."
        best = max(channels, key=lambda row: row.get("conversion_rate", 0))
        worst = min(channels, key=lambda row: row.get("conversion_rate", 0))
        return (
            f"{best.get('channel')} is outperforming at {best.get('conversion_rate', 0)}% conversion, "
            f"while {worst.get('channel')} trails at {worst.get('conversion_rate', 0)}% and may need source-specific nurturing."
        )

    if chart_type == "ai_efficacy":
        weeks = data.get("weeks") or []
        if len(weeks) < 2:
            return "AI resolution history is still thin. More closed leads are needed before efficacy trends become meaningful."
        latest = weeks[-1]
        previous = weeks[-2]
        delta = round(latest.get("resolution_rate", 0) - previous.get("resolution_rate", 0), 1)
        if delta >= 0:
            return (
                f"AI resolution rate increased by {delta} points to {latest.get('resolution_rate', 0)}%, "
                "suggesting recent prompt or routing changes are reducing human escalations."
            )
        return (
            f"AI resolution rate fell by {abs(delta)} points to {latest.get('resolution_rate', 0)}%, "
            "which may reflect tougher lead intent or more complex cases entering the pipeline."
        )

    velocity = data
    delta = velocity.get("delta_days", 0)
    change = velocity.get("change_percent", 0)
    if delta <= 0:
        return (
            f"Lead velocity improved by {abs(delta)} days versus last month ({change}% faster), "
            "meaning prospects are reaching enrolled status more quickly."
        )
    return (
        f"Lead velocity slowed by {delta} days compared with last month ({change}% increase), "
        "which can indicate longer advisor cycles or heavier handoff volume."
    )


async def explain_chart_trend(chart_type: ChartType, data: dict[str, Any]) -> dict[str, str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "summary": _heuristic_explain(chart_type, data),
            "source": "heuristic",
        }

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        prompt = (
            "You are a Nexus admissions analytics assistant. "
            "Analyze the JSON chart data and respond with exactly two concise sentences explaining "
            "why the trend may be happening. Avoid bullet points.\n\n"
            f"Chart type: {chart_type}\n"
            f"Data: {json.dumps(data)}"
        )
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "Provide concise analytics insight in two sentences."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=180,
            temperature=0.4,
        )
        summary = response.choices[0].message.content.strip()
        return {"summary": summary, "source": "llm"}
    except Exception:
        return {
            "summary": _heuristic_explain(chart_type, data),
            "source": "heuristic",
        }
