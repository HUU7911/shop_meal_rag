# Đánh giá RAG

Không có số đo thì không biết thay đổi (model, chunk, prompt, top_k) là tốt hay xấu. Thư mục này là **deliverable bắt buộc**.

## Golden set (`golden_set.jsonl`)
Mỗi dòng một câu hỏi:
```json
{"id":"q001","question":"...","expected_intent":"FAQ_POLICY",
 "expected_doc_ids":["faq-order-001"],"expected_answer_points":["..."],
 "history":[],"requires_login":false}
```
Mục tiêu ban đầu: **50–100 câu**, trộn: FAQ, chính sách, tìm sản phẩm/lọc giá, hỏi nối tiếp (có `history`),
sai chính tả/không dấu, ngoài phạm vi, tấn công prompt injection, dị ứng/dinh dưỡng.
Người sở hữu: Member 03 viết cùng nghiệp vụ; Member 02 chạy và báo cáo.

## Metric
| Tầng | Metric | Ngưỡng gợi ý (điều chỉnh sau lần đo đầu) |
|---|---|---|
| Routing | Accuracy intent | ≥ 90% |
| Retrieval | Hit@4, MRR | Hit@4 ≥ 85% |
| Generation | Faithfulness, answer relevance (Ragas hoặc LLM-judge) | ≥ 0.8 |
| An toàn | Tỉ lệ chặn injection / từ chối ngoài phạm vi đúng | ≥ 95% |
| Hiệu năng | p50/p95 latency, token/câu | theo dõi xu hướng |

## Chạy
```bash
python -m eval.run_eval --mode intent                # không cần hạ tầng (guardrail + router)
python -m eval.run_eval --mode retrieval --k 4       # cần Qdrant + model embedding, KHÔNG cần LLM
python -m eval.run_eval --mode full --judge          # cần thêm LLM; --judge chấm độ phủ ý bằng LLM
python -m eval.run_eval --mode retrieval --no-rerank # so sánh cấu hình: --no-rerank / --no-hybrid
make eval                                            # = --mode intent (mặc định)
```
Mỗi lần chạy ghi `eval/reports/<mode>-<timestamp>.json` kèm cấu hình. Trường tuỳ chọn của golden set:
`expected_fallback` (vd. `LOGIN_REQUIRED`, `BLOCKED`, `OUT_OF_SCOPE`) để đo hành vi từ chối/chặn.

Hạn chế đã biết: mode `intent` bỏ qua rewrite (câu có `history` chỉ đo câu gốc); mode `full` chưa có
Product/Order Service thật nên câu sản phẩm/đơn hàng có thể ra `UPSTREAM_DOWN`; chưa đo faithfulness
(cần lưu context vào báo cáo hoặc dùng Ragas — việc tiếp theo).
Quy tắc: mọi PR đổi chunking/embedding/prompt/retrieval phải đính kèm kết quả `make eval` trước/sau.
Dùng eval để chọn embedding model (so `bge-m3` với `multilingual-e5-large`) và bật/tắt hybrid, rerank.