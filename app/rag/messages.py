"""Thông điệp chuẩn khi không gọi LLM (fallback/canned). Giọng: lịch sự, ngắn gọn, tiếng Việt."""
from app.rag.utils import strip_accents


def no_info(contact: str) -> str:
    return (f"Xin lỗi, hiện mình chưa có thông tin về nội dung này. "
            f"Bạn vui lòng liên hệ {contact} để được hỗ trợ nhé.")


def upstream_down(contact: str) -> str:
    return (f"Hiện mình chưa kiểm tra được thông tin này (hệ thống đang bận). "
            f"Bạn thử lại sau ít phút hoặc liên hệ {contact} nhé.")


def llm_unavailable(contact: str) -> str:
    return (f"Hệ thống trả lời đang tạm thời không khả dụng. "
            f"Bạn vui lòng thử lại sau hoặc liên hệ {contact} nhé.")


def unsafe_output(contact: str) -> str:
    return ("Mình chưa có thông tin chắc chắn về nội dung này nên không muốn trả lời sai. "
            f"Để an toàn, bạn vui lòng hỏi trực tiếp {contact} nhé.")


LOGIN_REQUIRED = "Để xem thông tin đơn hàng, bạn vui lòng đăng nhập tài khoản Shop Meal rồi hỏi lại giúp mình nhé."
OUT_OF_SCOPE = ("Mình là trợ lý của Shop Meal nên chỉ hỗ trợ về món ăn, đặt hàng, thanh toán, "
                "giao hàng và chính sách của cửa hàng. Bạn cần mình giúp gì trong các việc này không?")
BLOCKED = "Mình không thể thực hiện yêu cầu này. Bạn cần hỗ trợ gì về món ăn hay đơn hàng của Shop Meal không?"
ALLERGY_NOTE = ("Lưu ý: thông tin về thành phần/dị ứng/dinh dưỡng chỉ mang tính tham khảo, "
                "bạn vui lòng kiểm tra lại với cửa hàng trước khi đặt.")


def smalltalk(question: str) -> str:
    q = strip_accents(question)
    if any(w in q for w in ("cam on", "thanks", "thank")):
        return "Rất vui được giúp bạn! Cần hỗ trợ thêm gì cứ hỏi mình nhé."
    if any(w in q for w in ("tam biet", "bye", "hen gap lai")):
        return "Cảm ơn bạn đã ghé Shop Meal, hẹn gặp lại bạn!"
    return "Xin chào! Mình là trợ lý của Shop Meal. Bạn muốn hỏi về món ăn, đơn hàng hay chính sách của cửa hàng?"
