"""Student-facing invoice email after Issue."""

from __future__ import annotations

import html
import logging
import re

from app.services.email_service import send_email

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def build_student_invoice_email(
    *,
    student_name: str,
    package_name: str,
    download_url: str,
    account_manager_name: str,
    company_name: str,
) -> tuple[str, str, str]:
    student = (student_name or "").strip() or "Student"
    package = (package_name or "").strip() or "your selected services"
    manager = (account_manager_name or "").strip() or "your account manager"
    company = (company_name or "").strip() or "NEXUS"
    link = (download_url or "").strip()

    subject = f"Invoice for {package} - {student}"
    body = (
        f"Dear {student},\n\n"
        f"Please find your invoice for the {package} here: {link}\n\n"
        "If your payment is still due, we kindly request that you complete it by the date "
        "indicated on the document. If you have already settled this balance, please "
        "disregard this notice. All approved payment methods are listed clearly at the "
        "bottom of the invoice for your convenience.\n\n"
        f"If you have any questions regarding this invoice, please feel free to reach out "
        f"to your account manager, {manager}.\n\n"
        "Best regards,\n\n"
        f"{company}"
    )

    safe_student = html.escape(student)
    safe_package = html.escape(package)
    safe_manager = html.escape(manager)
    safe_company = html.escape(company)
    safe_link = html.escape(link, quote=True)
    link_html = (
        f'<a href="{safe_link}" style="color:#0b57d0;text-decoration:underline;">'
        "Download invoice</a>"
        if link
        else "your invoice attachment"
    )
    html_body = (
        "<!DOCTYPE html><html><body "
        'style="font-family:Segoe UI,Arial,sans-serif;font-size:15px;color:#1a1a1a;'
        'background:#ffffff;padding:16px;line-height:1.5;">'
        f"<p style=\"margin:0 0 12px;\">Dear {safe_student},</p>"
        f"<p style=\"margin:0 0 12px;\">Please find your invoice for the {safe_package} "
        f"here: {link_html}.</p>"
        "<p style=\"margin:0 0 12px;\">If your payment is still due, we kindly request that "
        "you complete it by the date indicated on the document. If you have already settled "
        "this balance, please disregard this notice. All approved payment methods are listed "
        "clearly at the bottom of the invoice for your convenience.</p>"
        f"<p style=\"margin:0 0 12px;\">If you have any questions regarding this invoice, "
        f"please feel free to reach out to your account manager, {safe_manager}.</p>"
        f"<p style=\"margin:0 0 4px;\">Best regards,</p>"
        f"<p style=\"margin:0;\">{safe_company}</p>"
        "</body></html>"
    )
    return subject, body, html_body


def send_student_invoice_email(
    *,
    student_email: str,
    student_name: str,
    package_name: str,
    download_url: str,
    account_manager_name: str,
    company_name: str,
    pdf_bytes: bytes | None = None,
    pdf_filename: str | None = None,
) -> str:
    """
    Send the invoice notice email.

    Returns: "sent" | "skipped" | "failed"
    """
    email = (student_email or "").strip()
    if not email or not _EMAIL_RE.match(email):
        logger.warning("Invoice email skipped — missing/invalid student email %r", student_email)
        return "skipped"

    subject, body, html_body = build_student_invoice_email(
        student_name=student_name,
        package_name=package_name,
        download_url=download_url,
        account_manager_name=account_manager_name,
        company_name=company_name,
    )

    attachments = None
    if pdf_bytes and pdf_filename:
        attachments = [(pdf_filename, pdf_bytes, "application/pdf")]

    sent = send_email(
        [email],
        subject,
        body,
        html_body=html_body,
        attachments=attachments,
    )
    if sent:
        logger.info("Invoice email sent to %s subject=%r", email, subject)
        return "sent"

    # Some SMTP hosts reject large/mixed attachments — retry link-only.
    if attachments:
        logger.warning(
            "Invoice email with PDF attachment failed for %s; retrying without attachment",
            email,
        )
        sent = send_email(
            [email],
            subject,
            body,
            html_body=html_body,
            attachments=None,
        )
        if sent:
            logger.info("Invoice email sent to %s without attachment subject=%r", email, subject)
            return "sent"

    logger.error("Invoice email failed for %s subject=%r", email, subject)
    return "failed"
