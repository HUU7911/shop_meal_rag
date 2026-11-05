"""Ghép chunk + kết quả tool thành context trong giới hạn token; khử trùng lặp; tạo SourceItem.

Quy tắc:
  * Kết quả tool (live) đứng TRƯỚC chunk: là nguồn sự thật cho giá/trạng thái/đơn hàng.
  * Chunk trùng (cùng document + cùng nội dung) chỉ giữ 1.
  * Hết ngân sách token thì dừng; nếu chưa có gì thì cắt bớt phần tử đầu tiên cho vừa.
  * SourceItem: 1 nguồn / tài liệu (lấy điểm cao nhất); tool không tìm thấy / lỗi thì không tạo source.
"""
from dataclasses import dataclass, field

from app.rag.types import Hit, ToolResult
from app.rag.utils import estimate_tokens, snippet, truncate_to_tokens
from app.schemas.chat_schema import SourceItem, SourceType

_CONTENT_TYPE_TO_SOURCE = {"FAQ": SourceType.FAQ, "POLICY": SourceType.POLICY,
                           "PRODUCT": SourceType.PRODUCT, "DOCUMENT": SourceType.DOCUMENT}


def _merge(a: SourceItem, b: SourceItem) -> SourceItem:
    """Gộp 2 nguồn cùng tài liệu. `a` đến trước (tool live luôn đứng trước chunk).
    Hai chunk có điểm: giữ bản điểm cao. Tool + chunk: giữ thông tin của tool (url, tiêu đề), lấy điểm của chunk."""
    if a.score is not None and b.score is not None:
        base, other = (a, b) if a.score >= b.score else (b, a)
        score = base.score
    else:
        base, other = a, b
        score = a.score if a.score is not None else b.score
    return SourceItem(type=base.type, id=base.id, title=base.title or other.title,
                      snippet=base.snippet or other.snippet, url=base.url or other.url, score=score)


@dataclass
class BuiltContext:
    text: str = ""
    sources: list[SourceItem] = field(default_factory=list)
    has_context: bool = False       # có ít nhất 1 chunk hoặc 1 tool result THÀNH CÔNG (có dữ liệu)


class ContextBuilder:
    def build(self, hits: list[Hit], tool_results: list[ToolResult], max_tokens: int) -> BuiltContext:
        blocks: list[tuple[str, SourceItem | None]] = []
        for tr in tool_results:
            label = "Dữ liệu trực tiếp" if tr.ok else "Lưu ý hệ thống"
            source = (SourceItem(type=tr.kind, id=tr.ref_id, title=tr.title, snippet=snippet(tr.text), url=tr.url)
                      if tr.ok and tr.found else None)
            blocks.append((f"({label}) {tr.text}", source))
        seen: set[tuple[str, str]] = set()
        for h in hits:
            key = (h.document_id, " ".join(h.text.split()))
            if key in seen:
                continue
            seen.add(key)
            source = SourceItem(type=_CONTENT_TYPE_TO_SOURCE.get(h.content_type, SourceType.DOCUMENT),
                                id=h.document_id, title=h.title, snippet=snippet(h.text),
                                url=h.payload.get("source_url"),
                                score=round(h.rerank_score if h.rerank_score is not None else h.score, 4))
            blocks.append((f"({h.content_type}) {h.title}\n{h.text}", source))

        parts, sources, used = [], {}, 0
        for body, source in blocks:
            number = len(parts) + 1
            piece = f"[{number}] {body}"
            cost = estimate_tokens(piece)
            if used + cost > max_tokens:
                if parts:
                    break
                piece, cost = truncate_to_tokens(piece, max_tokens), max_tokens
            parts.append(piece)
            used += cost
            if source is not None:
                key = (source.type, source.id)
                sources[key] = _merge(sources[key], source) if key in sources else source
        has_context = any(tr.ok and tr.found for tr in tool_results) or bool(hits)
        return BuiltContext(text="\n\n".join(parts), sources=list(sources.values()), has_context=has_context)
