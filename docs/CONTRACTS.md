# Hợp đồng giữa các module

> **Chốt ngày đầu tiên.** Mọi thay đổi ở đây cần thông báo cả 3 thành viên và cập nhật tài liệu này.
> Phần code tương ứng nằm sẵn trong `app/schemas/`, `app/rag/types.py`, `app/ingestion/payload.py`.

## 1. REST API (Member 01 ⇄ Frontend)

Prefix: `/api/v1/chatbot`

| Method | Path | Mô tả |
|---|---|---|
| POST | `/chat` | Gửi câu hỏi, nhận câu trả lời đầy đủ |
| POST | `/chat/stream` | Như trên nhưng SSE (`token`, `sources`, `done`, `error`) |
| POST | `/conversations` | Tạo conversation mới |
| GET | `/conversations` | Danh sách conversation của user (phân trang) |
| GET | `/history/{conversation_id}` | Tin nhắn trong conversation (phân trang) |
| DELETE | `/history/{conversation_id}` | Xóa (soft delete) |
| POST | `/feedback` | Đánh giá một câu trả lời |
| GET | `/health` · `/health/ready` | Liveness / Readiness (Qdrant, Redis, MySQL, LLM) |
| POST | `/admin/ingestion/run` | Kích hoạt ingestion (cần `X-Internal-Key` hoặc role ADMIN) |

### ChatRequest
```json
{ "conversationId": null, "message": "Món cơm nào dưới 50k?" }
```
`conversationId` = `null` ở lượt đầu → server tạo và trả về. `message` tối đa `MESSAGE_MAX_LENGTH` ký tự.

### ChatResponse
```json
{
  "conversationId": "c_01HXYZ",
  "messageId": "m_01HXYZ",
  "answer": "Hiện có 3 món cơm dưới 50.000đ: ...",
  "intent": "PRODUCT_SEARCH",
  "sources": [
    { "type": "PRODUCT", "id": "product-001", "title": "Cơm gà xối mỡ",
      "snippet": "Cơm gà xối mỡ giòn...", "url": "/products/product-001", "score": 0.82 }
  ],
  "metadata": { "model": "…", "promptVersion": "v1", "retrievalCount": 4, "fallback": null }
}
```
> `messageId` bắt buộc để Feedback tham chiếu được.

### FeedbackRequest
```json
{ "conversationId": "c_01HXYZ", "messageId": "m_01HXYZ",
  "rating": "NEGATIVE", "reason": "INACCURATE", "comment": "Giá không đúng" }
```
`rating`: `POSITIVE | NEGATIVE`. `reason` (khi NEGATIVE): `INACCURATE | IRRELEVANT | NOT_FOUND | OTHER`.

### Lỗi chuẩn
```json
{ "error": { "code": "RETRIEVAL_ERROR", "message": "…", "requestId": "…" } }
```

## 2. RAG Engine (Member 02 ⇄ Member 01)

```python
class RAGEngine:
    async def invoke(self, request: RAGRequest) -> RAGResult: ...
    async def stream(self, request: RAGRequest) -> AsyncIterator[RAGEvent]: ...
```

- `RAGRequest`: `question`, `history[]` (role/content, đã cắt theo token budget), `user` (id, roles, is_guest),
  `request_id`.
- `RAGResult`: `answer`, `intent`, `sources[]`, `trace` (chunk_id + score, model, prompt_version, token usage,
  latency từng bước), `fallback_reason` (nullable).
- RAG **không** đọc/ghi MySQL; ChatService chịu trách nhiệm lưu.
- Intent: `FAQ_POLICY | PRODUCT_SEARCH | PRODUCT_DETAIL | ORDER_STATUS | SMALLTALK | OUT_OF_SCOPE`.
- Chi tiết kiểu dữ liệu: `app/rag/types.py`.

## 3. Qdrant Knowledge Base (Member 02 ⇄ Member 03)

- **Collection thật:** `shop_meal_knowledge_v{N}`; **alias:** `shop_meal_knowledge` (`QDRANT_COLLECTION`).
  Đổi embedding model = tạo collection `v{N+1}` → index lại → đổi alias (không downtime).
- **Vectors (named):** `dense` (kích thước = `EMBEDDING_DIM`, cosine) và `sparse` (BM25/SPLADE-style) cho hybrid.
- **ID điểm:** `uuid5(NAMESPACE, f"{content_type}:{source_id}:{chunk_index}")` – ổn định, upsert idempotent.
- **Metadata của collection:** `embedding_model`, `embedding_dim`, `kb_version`, `built_at`.

### Payload (mọi chunk)

| Field | Kiểu | Ghi chú |
|---|---|---|
| `chunk_id` | str | = point id |
| `document_id` | str | FAQ id / tên file policy / product_id |
| `content_type` | `FAQ` \| `POLICY` \| `PRODUCT` \| `DOCUMENT` | **có payload index** |
| `title` | str | Hiển thị ở sources |
| `text` | str | Nội dung chunk |
| `category` | str? | ORDER, PAYMENT, … / RICE, … **(index)** |
| `enabled` | bool | **(index)** retriever luôn lọc `true` |
| `version` | str? | Policy |
| `effective_date` | datetime? | Policy; retriever lọc `<= now` **(index)** |
| `chunk_index` | int | |
| `content_hash` | str | sha256 của text đã chuẩn hóa → incremental |
| `updated_at` | datetime | |
| `source_url` | str? | Deep link tới trang sản phẩm/FAQ |

Riêng `PRODUCT`: `product_id` **(index)**, `product_type`, `status_snapshot`, `price_snapshot`.
Hai trường `*_snapshot` **chỉ để lọc thô**; giá/trạng thái trả cho người dùng **phải lấy live**.
Giá và trạng thái **không** được đưa vào `text` được embed.

## 4. Embedding (dùng chung)

```python
class EmbeddingService:
    def embed_query(self, text: str) -> DenseVec  # + sparse
    def embed_documents(self, texts: list[str]) -> list[...]
    model_name: str; dim: int
```
Retriever kiểm tra `embedding_model`/`dim` trong metadata collection khi khởi động; lệch → báo lỗi rõ ràng.

## 5. Product / Order Service (integrations)

`app/integrations/product_client.py` và `order_client.py` là nguồn duy nhất gọi service ngoài.
Timeout `SERVICE_HTTP_TIMEOUT_SECONDS`, retry có giới hạn, lỗi quy về `UpstreamUnavailableError`.
Order client luôn chuyển JWT của chính user; **không** dùng service account để tra đơn của người khác.

## 6. Bảng MySQL (Member 01)

`conversations`, `chat_messages`, `feedback`, `ingestion_documents`, `ingestion_runs`
– chi tiết ở `app/db/models/` và `app/db/README.md`.
