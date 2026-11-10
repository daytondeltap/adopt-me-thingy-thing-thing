import pytest

from adoptme.parsing import normalize_variant_input, norm_name, parse_number, split_variant


@pytest.mark.parametrize(
    "text,expected",
    [("1,234.5", 1234.5), ("12k", 12000.0), ("1.5M", 1_500_000.0), ("  42 ", 42.0), ("N/A", None), (None, None), ("", None)],
)
def test_parse_number(text, expected):
    assert parse_number(text) == expected


def test_norm_name():
    assert norm_name("Shadow-Dragon!") == "shadow dragon"
    assert norm_name("  Bat  Dragon ") == "bat dragon"


@pytest.mark.parametrize(
    "raw,clean,variant",
    [
        ("Shadow Dragon", "Shadow Dragon", "normal"),
        ("Neon Shadow Dragon", "Shadow Dragon", "neon"),
        ("Mega Neon Shadow Dragon FR", "Shadow Dragon", "mega_fr"),
        ("Frost Dragon Fly", "Frost Dragon", "normal_f"),
        ("Flyer", "Flyer", "normal"),  # whole-word only
        ("Neon Owl Ride", "Owl", "neon_r"),
    ],
)
def test_split_variant(raw, clean, variant):
    assert split_variant(raw) == (clean, variant)


def test_normalize_variant_input():
    assert normalize_variant_input("any") == "any"
    assert normalize_variant_input("") == "any"
    assert normalize_variant_input("Mega FR") == "mega_fr"
    assert normalize_variant_input("neon") == "neon"
