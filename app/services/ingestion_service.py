"""Kích hoạt ingestion từ API admin (POST /admin/ingestion/run).

Chạy bằng TIẾN TRÌNH CON (`python -m app.ingestion.cli <mode>`) thay vì gọi pipeline trong tiến trình API:
embedding là CPU-bound, chạy cùng event loop sẽ làm đứng toàn bộ API chat. Đổi lại tốn thêm RAM khi
tiến trình con nạp model embedding. Chỉ cho phép MỘT lượt chạy tại một thời điểm (409 nếu đang chạy).
"""
import ast
import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable

from app.core.errors import ConflictError, NotFoundError
from app.db.unit_of_work import UnitOfWorkFactory
from app.schemas.ingestion_schema import IngestionRunResponse

log = logging.getLogger("app.services.ingestion")

Runner = Callable[[str], Awaitable[dict]]
RUN_TIMEOUT_SECONDS = 3600
STAT_KEYS = ("added", "updated", "deleted", "skipped")


async def subprocess_runner(mode: str) -> dict:
    """Chạy CLI ingestion, trả dict kết quả (dòng cuối stdout) hoặc {} nếu không đọc được."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "app.ingestion.cli", mode,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=RUN_TIMEOUT_SECONDS)
    except asyncio.CancelledError:
        proc.kill()
        raise
    except TimeoutError:
        proc.kill()
        raise RuntimeError(f"Ingestion quá {RUN_TIMEOUT_SECONDS}s, đã dừng tiến trình.") from None
    lines = out.decode("utf-8", errors="replace").strip().splitlines()
    if proc.returncode != 0:
        tail = " | ".join(lines[-3:])
        raise RuntimeError(f"CLI ingestion thoát mã {proc.returncode}: {tail}"[:900])
    try:
        parsed = ast.literal_eval(lines[-1]) if lines else {}
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, SyntaxError):
        return {}


class IngestionService:
    def __init__(self, uow_factory: UnitOfWorkFactory, runner: Runner = subprocess_runner):
        self._uow = uow_factory
        self._runner = runner
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    async def recover(self) -> int:
        """Gọi khi khởi động: lượt còn RUNNING là của tiến trình trước đã chết -> đánh dấu FAILED."""
        async with self._uow() as uow:
            return await uow.ingestion.fail_stale_runs("Tiến trình API khởi động lại khi đang chạy.")

    async def start(self, mode: str) -> IngestionRunResponse:
        if self._lock.locked():
            raise ConflictError("Ingestion đang chạy, vui lòng đợi lượt hiện tại kết thúc.")
        await self._lock.acquire()
        try:
            async with self._uow() as uow:
                run = await uow.ingestion.create_run(mode)
            response = IngestionRunResponse(
                run_id=run.id, mode=mode, status="RUNNING", started_at=run.started_at
            )
        except BaseException:
            self._lock.release()
            raise
        self._task = asyncio.create_task(self._execute(run.id, mode), name=f"ingestion-{run.id}")
        return response

    async def _execute(self, run_id: int, mode: str) -> None:
        status, stats, error = "COMPLETED", {}, None
        try:
            result = await self._runner(mode)
            stats = {k: int(result[k]) for k in STAT_KEYS if isinstance(result.get(k), int)}
            log.info("Ingestion run %s xong: %s", run_id, result)
        except asyncio.CancelledError:
            status, error = "FAILED", "Bị hủy do API tắt."
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("Ingestion run %s lỗi", run_id)
            status, error = "FAILED", f"{type(exc).__name__}: {exc}"[:1000]
        finally:
            try:
                async with self._uow() as uow:
                    await uow.ingestion.finish_run(run_id, status=status, stats=stats, error=error)
            except Exception:  # noqa: BLE001
                log.exception("Không ghi được kết quả ingestion run %s", run_id)
            finally:
                self._lock.release()

    async def get_run(self, run_id: int) -> IngestionRunResponse:
        async with self._uow() as uow:
            run = await uow.ingestion.get_run(run_id)
            if run is None:
                raise NotFoundError("Không tìm thấy lượt ingestion.")
            return IngestionRunResponse(
                run_id=run.id, mode=run.mode, status=run.status, started_at=run.started_at,
                finished_at=run.finished_at, added=run.added or 0, updated=run.updated or 0,
                deleted=run.deleted or 0, skipped=run.skipped or 0, error=run.error,
            )

    async def aclose(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
