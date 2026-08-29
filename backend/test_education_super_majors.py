"""Light tests for education super-majors service helpers."""

from app.services.education_super_majors import _slugify_code


def test_slugify_super_major_code():
    assert (
        _slugify_code("Computer Science & Information Technology")
        == "COMPUTER_SCIENCE_INFORMATION_TECHNOLOGY"
    )
    assert _slugify_code("Mathematics") == "MATHEMATICS"
    assert _slugify_code("  Arts, Humanities & Social Sciences ") == (
        "ARTS_HUMANITIES_SOCIAL_SCIENCES"
    )
