# integrations/

Nơi **duy nhất** gọi Product Service và Order Service. Dùng chung bởi `rag/tools` và `ingestion`.
Yêu cầu: `httpx.AsyncClient` dùng lại; timeout `SERVICE_HTTP_TIMEOUT_SECONDS`; retry giới hạn cho GET;
lỗi quy về `UpstreamUnavailableError`; `OrderClient` luôn chuyển JWT của chính user.
