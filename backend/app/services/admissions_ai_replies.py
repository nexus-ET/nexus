from __future__ import annotations

import re


def generate_contextual_admissions_reply(
    user_message: str,
    *,
    student_name: str = "there",
    has_prior_ai_turns: bool = False,
) -> str:
    text = (user_message or "").strip()
    first = (student_name or "there").split()[0]
    lower = text.lower()

    if not text:
        if has_prior_ai_turns:
            return (
                f"Hi {first}, just checking in from Edutrust Admissions. "
                "Have you had a chance to think about which program or intake you'd like to apply for?"
            )
        return (
            f"Hi {first}! I'm here to help with programs, entry requirements, fees, and application steps. "
            "What would you like to explore first?"
        )

    if any(word in lower for word in ("human", "advisor", "agent", "person", "talk to someone")):
        return (
            f"Of course, {first}. I'll connect you with a human admissions advisor on this chat shortly."
        )

    if re.search(r"\b(hi|hello|hey|good morning|good evening|good afternoon)\b", lower):
        return (
            f"Hi {first}! Lovely to hear from you. "
            "Which course or country are you interested in, and when would you like to start studying?"
        )

    if any(word in lower for word in ("course", "program", "programme", "degree", "study", "major")):
        return (
            f"Great question, {first}. Edutrust offers pathways in business, IT, health sciences, and more. "
            "Which field interests you most, and are you looking at undergraduate or postgraduate study?"
        )

    if any(word in lower for word in ("fee", "fees", "cost", "price", "tuition", "afford", "scholarship")):
        return (
            f"Fees depend on the program and intake, {first}. "
            "Tell me which course you're considering and I can outline the typical range and scholarship options."
        )

    if any(word in lower for word in ("requirement", "document", "documents", "transcript", "ielts", "toefl", "visa")):
        return (
            f"Usually we look for academic transcripts, ID/passport, English test results (if applicable), "
            f"and a personal statement, {first}. Which level are you applying for — foundation, bachelor, or master?"
        )

    if any(word in lower for word in ("when", "deadline", "intake", "start date", "semester", "apply")):
        return (
            f"We run multiple intakes through the year, {first}. "
            "Are you aiming to start in the next few months, or later in the year?"
        )

    if any(word in lower for word in ("yes", "yeah", "yep", "sure", "ok", "okay", "confirm")):
        return (
            f"Perfect, {first}! To move things forward, could you share your highest qualification so far "
            "(e.g. high school, diploma, or bachelor's)?"
        )

    if any(word in lower for word in ("no", "not yet", "later", "maybe")):
        return (
            f"No problem at all, {first}. "
            "Would you like a quick overview of our most popular programs while you decide?"
        )

    if any(word in lower for word in ("thank", "thanks", "appreciate")):
        return (
            f"You're very welcome, {first}! "
            "Is there anything else about admissions, documents, or timelines I can help with?"
        )

    snippet = text[:120].strip()
    return (
        f"Thanks for sharing that, {first}. Regarding \"{snippet}\" — "
        "could you tell me a bit more about your study goal so I can give you a precise answer?"
    )
