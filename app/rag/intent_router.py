"""Phân loại ý định bằng LUẬT trên văn bản đã bỏ dấu (khách hay gõ không dấu).

Thứ tự ưu tiên (dừng ở luật đầu tiên khớp):
 1. Có mã đơn                                            -> ORDER_STATUS
 2. Hỏi trạng thái đơn CỦA MÌNH (đơn + của tôi + đang ở đâu...) -> ORDER_STATUS
 3. Từ khóa chính sách/thanh toán/giao hàng/hủy đổi/đặt hàng -> FAQ_POLICY
 3b. Chủ đề không liên quan (thời tiết, bitcoin...) mà không nhắc món -> OUT_OF_SCOPE
 4. Nhắc món/giá/còn hàng hoặc có bộ lọc giá/danh mục      -> PRODUCT_DETAIL | PRODUCT_SEARCH
 5. Chào hỏi/cảm ơn ngắn                                  -> SMALLTALK
 6. Còn lại                                               -> FAQ_POLICY (retrieval + ngưỡng điểm quyết định có trả lời không)

Chỉ nghĩ tới classifier/LLM khi `make eval` (intent accuracy) cho thấy luật không đủ.
"""
from app.rag.utils import extract_order_id, has_phrase, strip_accents
from app.schemas.chat_schema import Intent

ORDER_WORDS = ["don", "don hang", "ma don"]
PERSONAL = ["cua toi", "cua minh", "toi da dat", "toi vua dat", "minh da dat", "minh vua dat", "don toi"]
ORDER_STATUS_MARKERS = ["o dau", "dang o", "trang thai", "tinh trang", "da giao", "bao gio", "chua thay",
                        "tra cuu", "kiem tra don", "theo doi", "giao toi dau", "toi dau roi", "giao chua",
                        "bao lau nua", "den dau roi"]

POLICY = ["dat mon", "dat hang", "mua hang", "bao hanh", "giam gia", "khuyen mai", "ma giam", "voucher",
          "uu dai", "coupon", "huy", "hoan tien", "doi tra", "chinh sach", "quy dinh", "dieu khoan", "bao mat",
          "phi ship", "phi giao", "phi van chuyen", "thoi gian giao", "giao hang bao lau",
          "thanh toan", "phuong thuc", "xuat hoa don", "ho tro", "lien he"]

PRODUCT_WORDS = ["mon", "mon an", "do an", "com", "bun", "pho", "thuc don", "menu", "do uong", "nuoc",
                 "combo"]
# "sản phẩm" quá chung ("quy trình bảo hành sản phẩm"): chỉ tính khi đi kèm từ hỏi giá/còn hàng/liệt kê.
WEAK_PRODUCT_WORDS = ["san pham"]
PRICE_WORDS = ["gia", "bao nhieu tien", "re", "re nhat", "re hon"]
STOCK_WORDS = ["con hang", "het hang", "con ban", "co ban khong"]
DETAIL_MARKERS = ["gia bao nhieu", "bao nhieu tien", "con hang", "het hang", "co chua", "khong chua",
                  "thanh phan", "di ung", "dinh duong", "calo", "kcal", "con ban"]
LISTING_MARKERS = ["san pham nao", "nhung mon nao", "co mon nao", "mon nao", "danh sach", "liet ke", "goi y", "nen an gi",
                   "an gi", "menu", "thuc don", "re nhat", "duoi", "tren", "toi da", "toi thieu",
                   "tu .{1,12} den"]

GREETING = ["xin chao", "chao", "hello", "hi", "hey", "alo", "cam on", "thanks", "thank you",
            "tam biet", "bye", "hen gap lai"]
OFF_TOPIC = ["thoi tiet", "bong da", "ty so", "chung khoan", "bitcoin", "lap trinh", "viet code", "python",
             "dich sang", "giai toan", "phuong trinh", "chinh tri", "bau cu", "xo so", "tu vi", "cuoc song"]


class IntentRouter:
    def route(self, question: str, filters: dict | None = None) -> Intent:
        filters = filters or {}
        q = strip_accents(question)

        if filters.get("order_id") or extract_order_id(question):
            return Intent.ORDER_STATUS
        if has_phrase(q, ORDER_WORDS) and has_phrase(q, PERSONAL) and has_phrase(q, ORDER_STATUS_MARKERS):
            return Intent.ORDER_STATUS
        if has_phrase(q, POLICY):
            return Intent.FAQ_POLICY

        # Chủ đề không liên quan đứng TRƯỚC nhánh sản phẩm: "giá bitcoin" chứa "giá" nhưng không phải hỏi giá món.
        if has_phrase(q, OFF_TOPIC) and not has_phrase(q, PRODUCT_WORDS):
            return Intent.OUT_OF_SCOPE

        has_filters = any(k in filters for k in ("max_price", "min_price", "category"))
        weak_product = has_phrase(q, WEAK_PRODUCT_WORDS) and (has_phrase(q, DETAIL_MARKERS) or has_phrase(q, LISTING_MARKERS))
        if (has_filters or weak_product or has_phrase(q, PRODUCT_WORDS) or has_phrase(q, PRICE_WORDS)
                or has_phrase(q, STOCK_WORDS)):
            if has_phrase(q, DETAIL_MARKERS) and not has_phrase(q, LISTING_MARKERS) and not has_filters:
                return Intent.PRODUCT_DETAIL
            return Intent.PRODUCT_SEARCH

        if has_phrase(q, GREETING) and len(q.split()) <= 6:
            return Intent.SMALLTALK
        return Intent.FAQ_POLICY