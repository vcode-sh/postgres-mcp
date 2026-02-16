from dataclasses import dataclass
from typing import Optional

from ..sql import SqlDriver
from ..sql import get_server_info
from ..sql import has_view_column


@dataclass
class ReplicationSlot:
    slot_name: str
    database: str
    active: bool
    invalidation_reason: str | None = None
    inactive_since: str | None = None
    failover: bool | None = None
    synced: bool | None = None


@dataclass
class ReplicationMetrics:
    is_replica: bool
    replication_lag_seconds: Optional[float]
    is_replicating: bool
    replication_slots: list[ReplicationSlot]


class ReplicationCalc:
    def __init__(self, sql_driver: SqlDriver):
        self.sql_driver = sql_driver
        self._server_version: Optional[int] = None
        self._feature_support: dict[str, bool] = {}

    async def replication_health_check(self) -> str:
        """Check replication health including lag and slots."""
        metrics = await self._get_replication_metrics()
        result = []

        if metrics.is_replica:
            result.append("This is a replica database.")
            # Check replication status
            if not metrics.is_replicating:
                result.append("WARNING: Replica is not actively replicating from primary!")
            else:
                result.append("Replica is actively replicating from primary.")

            # Check replication lag
            if metrics.replication_lag_seconds is not None:
                if metrics.replication_lag_seconds == 0:
                    result.append("No replication lag detected.")
                else:
                    result.append(f"Replication lag: {metrics.replication_lag_seconds:.1f} seconds")
        else:
            result.append("This is a primary database.")
            if metrics.is_replicating:
                result.append("Has active replicas connected.")
            else:
                result.append("No active replicas connected.")

        # Check replication slots for both primary and replica
        if metrics.replication_slots:
            active_slots = [s for s in metrics.replication_slots if s.active]
            inactive_slots = [s for s in metrics.replication_slots if not s.active]

            if active_slots:
                result.append("\nActive replication slots:")
                for slot in active_slots:
                    result.append(self._format_slot(slot))

            if inactive_slots:
                result.append("\nInactive replication slots:")
                for slot in inactive_slots:
                    result.append(self._format_slot(slot))
        else:
            result.append("\nNo replication slots found.")

        return "\n".join(result)

    async def _get_replication_metrics(self) -> ReplicationMetrics:
        """Get comprehensive replication metrics."""
        return ReplicationMetrics(
            is_replica=await self._is_replica(),
            replication_lag_seconds=await self._get_replication_lag(),
            is_replicating=await self._is_replicating(),
            replication_slots=await self._get_replication_slots(),
        )

    async def _is_replica(self) -> bool:
        """Check if this database is a replica."""
        result = await self.sql_driver.execute_query("SELECT pg_is_in_recovery()")
        result_list = [dict(x.cells) for x in result] if result is not None else []
        return bool(result_list[0]["pg_is_in_recovery"]) if result_list else False

    async def _get_replication_lag(self) -> Optional[float]:
        """Get replication lag in seconds."""
        if not self._feature_supported("replication_lag"):
            return None

        # Use appropriate functions based on PostgreSQL version
        if await self._get_server_version() >= 100000:
            lag_condition = "pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn()"
        else:
            lag_condition = "pg_last_xlog_receive_location() = pg_last_xlog_replay_location()"

        try:
            result = await self.sql_driver.execute_query(f"""
                SELECT
                    CASE
                        WHEN NOT pg_is_in_recovery() OR {lag_condition} THEN 0
                        ELSE EXTRACT (EPOCH FROM NOW() - pg_last_xact_replay_timestamp())
                    END
                AS replication_lag
            """)
            result_list = [dict(x.cells) for x in result] if result is not None else []
            return float(result_list[0]["replication_lag"]) if result_list else None
        except Exception:
            self._feature_support["replication_lag"] = False
            return None

    async def _get_replication_slots(self) -> list[ReplicationSlot]:
        """Get information about replication slots."""
        if await self._get_server_version() < 90400 or not self._feature_supported("replication_slots"):
            return []

        try:
            supports_invalidation_reason = await has_view_column(
                self.sql_driver,
                "pg_catalog",
                "pg_replication_slots",
                "invalidation_reason",
            )
            supports_inactive_since = await has_view_column(
                self.sql_driver,
                "pg_catalog",
                "pg_replication_slots",
                "inactive_since",
            )
            supports_failover = await has_view_column(
                self.sql_driver,
                "pg_catalog",
                "pg_replication_slots",
                "failover",
            )
            supports_synced = await has_view_column(
                self.sql_driver,
                "pg_catalog",
                "pg_replication_slots",
                "synced",
            )

            result = await self.sql_driver.execute_query(f"""
                SELECT
                    slot_name,
                    database,
                    active,
                    {"invalidation_reason AS invalidation_reason" if supports_invalidation_reason else "NULL::text AS invalidation_reason"},
                    {"inactive_since::text AS inactive_since" if supports_inactive_since else "NULL::text AS inactive_since"},
                    {"failover AS failover" if supports_failover else "NULL::boolean AS failover"},
                    {"synced AS synced" if supports_synced else "NULL::boolean AS synced"}
                FROM pg_replication_slots
            """)
            if result is None:
                return []
            result_list = [dict(x.cells) for x in result]
            return [
                ReplicationSlot(
                    slot_name=row["slot_name"],
                    database=row["database"],
                    active=row["active"],
                    invalidation_reason=row["invalidation_reason"],
                    inactive_since=row["inactive_since"],
                    failover=row["failover"],
                    synced=row["synced"],
                )
                for row in result_list
            ]
        except Exception:
            self._feature_support["replication_slots"] = False
            return []

    def _format_slot(self, slot: ReplicationSlot) -> str:
        details: list[str] = []
        if slot.failover is not None:
            details.append(f"failover={slot.failover}")
        if slot.synced is not None:
            details.append(f"synced={slot.synced}")
        if slot.inactive_since:
            details.append(f"inactive_since={slot.inactive_since}")
        if slot.invalidation_reason:
            details.append(f"invalidation_reason={slot.invalidation_reason}")
        detail_text = f" [{', '.join(details)}]" if details else ""
        return f"- {slot.slot_name} (database: {slot.database}){detail_text}"

    async def _is_replicating(self) -> bool:
        """Check if replication is active."""
        if not self._feature_supported("replicating"):
            return False

        try:
            result = await self.sql_driver.execute_query("SELECT state FROM pg_stat_replication")
            result_list = [dict(x.cells) for x in result] if result is not None else []
            return bool(result_list and len(result_list) > 0)
        except Exception:
            self._feature_support["replicating"] = False
            return False

    async def _get_server_version(self) -> int:
        """Get PostgreSQL server version as a number (e.g. 100000 for version 10.0)."""
        if self._server_version is None:
            self._server_version = (await get_server_info(self.sql_driver)).server_version_num
        return self._server_version

    def _feature_supported(self, feature: str) -> bool:
        """Check if a feature is supported and cache the result."""
        return self._feature_support.get(feature, True)
