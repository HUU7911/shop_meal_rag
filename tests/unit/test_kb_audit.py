from eval.kb_audit import audit_payloads, build_golden_rows


def chunk(doc, title="Câu hỏi?", text="Nội dung trả lời đủ dài để không bị coi là quá ngắn.", ctype="FAQ", idx=0, **kw):
    p = {"chunk_id": f"{doc}-{idx}", "document_id": doc, "content_type": ctype, "title": title, "text": text,
         "chunk_index": idx, "content_hash": "h", "updated_at": "2026-01-01T00:00:00Z", "enabled": True}
    p.update(kw)
    return (f"id-{doc}-{idx}", p)


META = ("meta", {"content_type": "META", "enabled": False, "embedding_model": "BAAI/bge-m3"})


def test_audit_clean_kb_has_no_issues():
    r = audit_payloads([chunk("a"), chunk("b", title="Khác?"), META], expected_model="BAAI/bge-m3")
    assert r["issues"] == [] and r["warnings"] == [] and r["content_chunks"] == 2 and r["meta_point"]
    assert r["by_content_type"] == {"FAQ": 2}


def test_audit_detects_blocking_problems():
    broken = ("x", {"content_type": "FAQ", "text": "ngắn"})                      # thiếu document_id, title...
    r = audit_payloads([broken, chunk("a"), chunk("a"), META], expected_model="other-model")
    text = " ".join(r["issues"])
    assert "thiếu trường bắt buộc" in text and "trùng" in text and "other-model" in text


def test_audit_warns_about_placeholders_short_text_and_missing_meta():
    r = audit_payloads([chunk("a", text="[MẪU] Thay bằng nội dung thật từ nghiệp vụ."), chunk("b", text="Ngắn")])
    joined = " ".join(r["warnings"])
    assert "giữ chỗ" in joined and "quá ngắn" in joined and "META" in joined


def test_golden_rows_have_title_and_unaccented_variant_and_skip_duplicates():
    items = [chunk("a", title="Hủy đơn thế nào?"), chunk("b", title="Phí giao hàng"), chunk("c", title="Phí giao hàng"),
             chunk("d", title="Thanh toan", ctype="FAQ"), chunk("p", ctype="POLICY", title="Chính sách"),
             chunk("z", title="Đã tắt", enabled=False)]
    rows = build_golden_rows(items)
    by_doc = {}
    for r in rows:
        by_doc.setdefault(r["expected_doc_ids"][0], []).append(r["question"])
    assert by_doc["a"] == ["Hủy đơn thế nào?", "huy don the nao?"]       # gốc + không dấu
    assert by_doc["d"] == ["Thanh toan"]                                   # đã không dấu: không thêm bản trùng
    assert "b" not in by_doc and "c" not in by_doc                          # hai FAQ trùng câu hỏi: bỏ vì nhãn mơ hồ
    assert "p" not in by_doc and "z" not in by_doc                          # chỉ FAQ đang bật
    assert all(r["expected_intent"] == "FAQ_POLICY" and r["source"].startswith("auto") for r in rows)
    assert [r["id"] for r in rows] == ["kb001", "kb002", "kb003"]