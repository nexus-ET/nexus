"""Unit tests for ScanX front/back upload grouping (no DB)."""

from __future__ import annotations

from app.services.scanx_upload_group import (
    group_upload_file_indices,
    pairing_stem,
    passport_side_from_filename,
)


def test_chaitanya_front_back_pdfs_group_together():
    names = [
        "Chaitanya Passport front.pdf",
        "Chaitanya Passport_back.pdf",
    ]
    assert passport_side_from_filename(names[0]) == "front"
    assert passport_side_from_filename(names[1]) == "back"
    assert pairing_stem(names[0]) == pairing_stem(names[1])
    groups = group_upload_file_indices(names)
    assert groups == [[0, 1]]


def test_unrelated_pdfs_without_side_cues_stay_separate():
    names = ["Alice Passport.pdf", "Bob Passport.pdf"]
    groups = group_upload_file_indices(names)
    assert groups == [[0], [1]]


def test_jpeg_batch_still_groups_all_images():
    names = ["page1.jpg", "page2.jpg", "page3.png"]
    groups = group_upload_file_indices(names)
    assert groups == [[0, 1, 2]]


def test_mixed_batch_images_group_pdf_pair_and_singleton():
    names = [
        "a.jpg",
        "b.jpg",
        "Chaitanya Passport front.pdf",
        "other.pdf",
        "Chaitanya Passport_back.pdf",
    ]
    groups = group_upload_file_indices(names)
    assert [0, 1] in groups
    assert [2, 4] in groups
    assert [3] in groups
