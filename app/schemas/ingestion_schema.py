from datetime import datetime
from typing import Literal

from app.schemas.common_schema import CamelModel


class IngestionRunResponse(CamelModel):
    run_id: int
    mode: Literal["full", "incremental"]
    status: str                      # RUNNING | COMPLETED | FAILED
    started_at: datetime | None = None
    finished_at: datetime | None = None
    added: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    error: str | None = None
