"""Thêm các trường cấu hình rerank còn thiếu vào app/core/config.py. An toàn chạy nhiều lần (idempotent)."""
import pathlib
p = pathlib.Path("app/core/config.py")
s = p.read_text()
fields = {
    "rerank_device": '    rerank_device: str = ""                   # "" = dùng EMBEDDING_DEVICE\n',
    "rerank_max_length": '    rerank_max_length: int = 512\n',
    "rerank_candidates": '    rerank_candidates: int = 0                # 0 = rerank toàn bộ top_k\n',
}
missing = [name for name in fields if f"{name}:" not in s]
if not missing:
    print("Đã có đủ các trường, không cần sửa.")
else:
    lines = s.splitlines(keepends=True)
    idx = next((i for i, l in enumerate(lines) if l.lstrip().startswith("rerank_model:")), None)
    if idx is None:
        raise SystemExit("KHÔNG tìm thấy dòng 'rerank_model:' trong config.py — dừng, không sửa gì. Hãy gửi nội dung file lên.")
    lines[idx + 1:idx + 1] = [fields[n] for n in missing]
    p.write_text("".join(lines))
    print("Đã thêm:", ", ".join(missing))