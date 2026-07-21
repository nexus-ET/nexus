"""Configurable contact type labels for campus/college phone, fax, and email fields."""

PHONE_CONTACT_TYPES: tuple[str, ...] = (
    "Main",
    "Admissions",
    "Inquiries",
    "Registrar",
    "Campus",
    "Other",
)

# Fax uses the same type vocabulary as phone numbers.
FAX_CONTACT_TYPES: tuple[str, ...] = PHONE_CONTACT_TYPES

EMAIL_CONTACT_TYPES: tuple[str, ...] = (
    "General",
    "Admissions",
    "Support",
    "Registrar",
    "Inquiries",
    "Applications help",
    "Financial aid",
    "Other",
)

WEB_LINK_TYPES: tuple[str, ...] = (
    "Website",
    "Admissions",
    "Enquiries",
    "Contact Page",
    "Campus",
    "College",
)

PHONE_TYPE_MAIN = "Main"
FAX_TYPE_MAIN = PHONE_TYPE_MAIN
EMAIL_TYPE_GENERAL = "General"
WEB_LINK_TYPE_WEBSITE = "Website"
