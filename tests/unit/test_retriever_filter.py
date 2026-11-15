"""Cần qdrant-client (có trong requirements.txt); bỏ qua nếu chưa cài."""
from datetime import datetime, timezone


def test_filter_always_has_enabled_and_effective_date():
    import pytest
    pytest.importorskip("qdrant_client")
    from app.rag.retriever import build_filter

    flt = build_filter(["FAQ", "POLICY"], category="ORDER", now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    keys = [getattr(c, "key", None) for c in flt.must]
    assert "enabled" in keys and "content_type" in keys and "category" in keys
    assert any(getattr(c, "should", None) for c in flt.must)           # nhánh effective_date
    bare = build_filter(None)
    assert [getattr(c, "key", None) for c in bare.must].count("content_type") == 0
