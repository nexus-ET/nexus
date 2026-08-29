"""Unit tests for invoice R2 path helpers (no live Cloudflare calls)."""

from datetime import date

import pytest
from fastapi import HTTPException

from app.services.invoice_email_service import build_student_invoice_email
from app.services.invoice_storage import (
    INVOICE_ROOT_PREFIX,
    fy_prefix,
    indian_financial_year_folder,
    make_invoice_download_token,
    parse_invoice_calendar_date,
    sanitize_invoice_pdf_filename,
    verify_invoice_download_token,
)


def test_invoice_root_prefix_is_accounts_invoices():
    assert INVOICE_ROOT_PREFIX == "ADMIN/ACCOUNTS/INVOICES"
    fy = indian_financial_year_folder(date(2026, 8, 11))
    assert fy_prefix(fy) == "ADMIN/ACCOUNTS/INVOICES/FY_2026_2027/"
    assert (
        f"{fy_prefix(fy)}INV-1_Issued.pdf"
        == "ADMIN/ACCOUNTS/INVOICES/FY_2026_2027/INV-1_Issued.pdf"
    )


def test_indian_financial_year_folder_april_boundary():
    assert indian_financial_year_folder(date(2026, 8, 11)) == "FY_2026_2027"
    assert indian_financial_year_folder(date(2027, 3, 31)) == "FY_2026_2027"
    assert indian_financial_year_folder(date(2027, 4, 1)) == "FY_2027_2028"
    assert indian_financial_year_folder(date(2028, 3, 31)) == "FY_2027_2028"


def test_sanitize_invoice_pdf_filename():
    assert (
        sanitize_invoice_pdf_filename(
            "INV-2026-0042_1042_Priya Sharma_11-Aug-2026_Issued.pdf"
        )
        == "INV-2026-0042_1042_Priya_Sharma_11-Aug-2026_Issued.pdf"
    )
    with pytest.raises(HTTPException):
        sanitize_invoice_pdf_filename("notes.txt")


def test_parse_invoice_calendar_date():
    assert parse_invoice_calendar_date("2026-08-11") == date(2026, 8, 11)
    with pytest.raises(HTTPException):
        parse_invoice_calendar_date("11-08-2026")


def test_invoice_download_token_roundtrip():
    key = (
        "ADMIN/ACCOUNTS/INVOICES/FY_2026_2027/"
        "INV-2026-0042_1042_Priya_Sharma_11-Aug-2026_Issued.pdf"
    )
    token = make_invoice_download_token(key)
    assert "__" in token
    assert verify_invoice_download_token(token) == key


def test_legacy_invoice_download_token_still_accepted():
    key = "ADMIN/INVOICES/FY_2026_2027/INV-2026-0042_1042_Priya_Sharma_11-Aug-2026_Issued.pdf"
    token = make_invoice_download_token(key)
    assert verify_invoice_download_token(token) == key


def test_student_invoice_email_template():
    subject, body, html_body = build_student_invoice_email(
        student_name="Priya Sharma",
        package_name="Premium Visa Package",
        download_url="https://example.com/api/v1/invoices/download?token=abc",
        account_manager_name="Ishq Ahmed",
        company_name="EduTrust",
    )
    assert subject == "Invoice for Premium Visa Package - Priya Sharma"
    assert "Dear Priya Sharma," in body
    assert "https://example.com/api/v1/invoices/download?token=abc" in body
    assert "Ishq Ahmed" in body
    assert "EduTrust" in body
    assert "Download invoice" in html_body


def test_sanitize_replaces_spaces():
    assert (
        sanitize_invoice_pdf_filename("EDT-26-27-0005_1_Ishan S Ahmed_11-Aug-2026_Issued.pdf")
        == "EDT-26-27-0005_1_Ishan_S_Ahmed_11-Aug-2026_Issued.pdf"
    )
