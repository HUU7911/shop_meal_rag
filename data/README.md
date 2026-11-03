# data/

| Thư mục | Nội dung | Định dạng |
|---|---|---|
| `faq/` | FAQ theo nhóm (`faq_order.json`, `faq_payment.json`, ...) | JSON: `id, category, question, keywords[], answer, enabled` |
| `policies/` | Chính sách (`*_policy.md`) | Markdown + front-matter: `policy_id, title, version, effective_date, enabled` |
| `products/` | Cache/snapshot sản phẩm (nguồn thật là Product Service) | JSON, không commit |
| `documents/` | Tài liệu bổ sung (hướng dẫn, giới thiệu) | Markdown |
| `processed/` | Dữ liệu trung gian sau làm sạch/chunk | Không commit |

> Nội dung trong `faq/` và `policies/` hiện là **MẪU MINH HỌA** – cần thay bằng nội dung nghiệp vụ thật
> (và dùng làm nguồn cho `eval/golden_set.jsonl`). Không đưa PII hay dữ liệu bí mật vào đây.
