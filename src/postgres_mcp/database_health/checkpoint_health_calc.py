from dataclasses import dataclass

from ..sql import SqlDriver
from ..sql import has_view_column


@dataclass
class CheckpointerMetrics:
    num_timed: int
    num_requested: int
    restartpoints_timed: int
    restartpoints_req: int
    restartpoints_done: int
    write_time: float
    sync_time: float
    buffers_written: int
    num_done: int | None = None
    slru_written: int | None = None
    stats_reset: str | None = None


class CheckpointHealthCalc:
    def __init__(self, sql_driver: SqlDriver):
        self.sql_driver = sql_driver

    async def checkpoint_health_check(self) -> str:
        """Check checkpoint and restartpoint health statistics."""
        metrics = await self._get_checkpointer_metrics()
        if metrics is None:
            return "Checkpoint statistics unavailable (requires PostgreSQL 17 or later)."

        checkpoint_line = f"Checkpoints: timed={metrics.num_timed}, requested={metrics.num_requested}"
        if metrics.num_done is not None:
            checkpoint_line += f", done={metrics.num_done}"

        restartpoint_line = (
            "Restartpoints: "
            f"timed={metrics.restartpoints_timed}, "
            f"requested={metrics.restartpoints_req}, "
            f"done={metrics.restartpoints_done}"
        )
        io_line = f"Checkpoint I/O time: write={metrics.write_time:.1f} ms, sync={metrics.sync_time:.1f} ms"
        buffers_line = f"Buffers written: shared={metrics.buffers_written}"
        if metrics.slru_written is not None:
            buffers_line += f", slru={metrics.slru_written}"

        lines = [checkpoint_line, restartpoint_line, io_line, buffers_line]
        if metrics.stats_reset:
            lines.append(f"Stats reset at: {metrics.stats_reset}")
        return "\n".join(lines)

    async def _get_checkpointer_metrics(self) -> CheckpointerMetrics | None:
        """Read checkpointer metrics if pg_stat_checkpointer is available."""
        if not await has_view_column(self.sql_driver, "pg_catalog", "pg_stat_checkpointer", "num_timed"):
            return None

        has_num_done = await has_view_column(self.sql_driver, "pg_catalog", "pg_stat_checkpointer", "num_done")
        has_slru_written = await has_view_column(self.sql_driver, "pg_catalog", "pg_stat_checkpointer", "slru_written")

        result = await self.sql_driver.execute_query(f"""
            SELECT
                COALESCE(num_timed, 0)::bigint AS num_timed,
                COALESCE(num_requested, 0)::bigint AS num_requested,
                COALESCE(restartpoints_timed, 0)::bigint AS restartpoints_timed,
                COALESCE(restartpoints_req, 0)::bigint AS restartpoints_req,
                COALESCE(restartpoints_done, 0)::bigint AS restartpoints_done,
                COALESCE(write_time, 0)::double precision AS write_time,
                COALESCE(sync_time, 0)::double precision AS sync_time,
                COALESCE(buffers_written, 0)::bigint AS buffers_written,
                {"COALESCE(num_done, 0)::bigint AS num_done" if has_num_done else "NULL::bigint AS num_done"},
                {"COALESCE(slru_written, 0)::bigint AS slru_written" if has_slru_written else "NULL::bigint AS slru_written"},
                stats_reset::text AS stats_reset
            FROM pg_catalog.pg_stat_checkpointer
        """)

        if not result:
            return None

        row = dict(result[0].cells)
        return CheckpointerMetrics(
            num_timed=int(row["num_timed"]),
            num_requested=int(row["num_requested"]),
            restartpoints_timed=int(row["restartpoints_timed"]),
            restartpoints_req=int(row["restartpoints_req"]),
            restartpoints_done=int(row["restartpoints_done"]),
            write_time=float(row["write_time"]),
            sync_time=float(row["sync_time"]),
            buffers_written=int(row["buffers_written"]),
            num_done=int(row["num_done"]) if row["num_done"] is not None else None,
            slru_written=int(row["slru_written"]) if row["slru_written"] is not None else None,
            stats_reset=row["stats_reset"],
        )
