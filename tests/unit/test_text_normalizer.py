from app.embedding.text_normalizer import normalize_text


def test_nfc_and_whitespace():
    decomposed = "Co\u031b\u0300m   ga\u0300"   # ký tự tổ hợp
    out = normalize_text(decomposed)
    assert "  " not in out and out == out.strip()
