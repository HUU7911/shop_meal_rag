"""Điều phối một lượt chat. Đây là service DUY NHẤT mà router chat gọi.

Trình tự:
 1. ConversationService: lấy/tạo conversation (kiểm tra chủ sở hữu)
 2. HistoryService: lấy lịch sử gần nhất theo HISTORY_MAX_TURNS / HISTORY_MAX_TOKENS
 3. RAGEngine.invoke(RAGRequest)  -> RAGResult
 4. HistoryService: lưu message user + assistant (kèm sources, trace)
 5. Trả ChatResponse (có message_id)

Quy tắc: ChatService không chứa logic embedding/chunking/truy vấn Qdrant.
"""
from app.core.security import CurrentUser
from app.schemas.chat_schema import ChatRequest, ChatResponse


class ChatService:
    async def handle(self, user: CurrentUser, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError  # TODO(Member 01)
