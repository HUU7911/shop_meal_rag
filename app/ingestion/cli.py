"""Điểm vào ingestion:
    python -m app.ingestion.cli full         # build collection mới + đổi alias
    python -m app.ingestion.cli incremental  # chỉ phần thay đổi
    python -m app.ingestion.cli verify       # kiểm tra số lượng/metadata collection
"""
import asyncio
import sys

from app.ingestion import pipeline


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "incremental"
    if mode not in {"full", "incremental", "verify"}:
        print(__doc__)
        return 2
    print(asyncio.run(pipeline.run(mode)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
