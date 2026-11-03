"""Làm sạch dữ liệu: bỏ HTML, chuẩn hóa Unicode NFC/khoảng trắng (dùng embedding.text_normalizer),
loại bản ghi rỗng/trùng, kiểm tra trường bắt buộc. Bản ghi lỗi -> ghi log + bỏ qua, không dừng cả job."""


def clean_record(record: dict) -> dict | None:
    raise NotImplementedError  # TODO(Member 03)
