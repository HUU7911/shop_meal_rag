import pytest

from app.embedding.text_normalizer import normalize_text

def test_nfc_and_whitespace():
    decomposed = "Co\u031b\u0300m   ga\u0300"
    out = normalize_text(decomposed)

    assert "  " not in out
    assert out == out.strip()


def test_preserve_vietnamese_accents():
    assert normalize_text("Cơm gà") == "Cơm gà"


def test_remove_space_before_punctuation():
    assert normalize_text("Xin chào   !") == "Xin chào!"


def test_collapse_whitespace():
    assert normalize_text("Cơm   gà\nxối\tmỡ") == "Cơm gà xối mỡ"


def test_empty_string():
    assert normalize_text("") == ""


def test_reject_non_string():
    with pytest.raises(TypeError):
        normalize_text(None)
