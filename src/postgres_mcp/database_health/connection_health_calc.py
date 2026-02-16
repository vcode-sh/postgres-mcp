from dataclasses import dataclass

from ..sql import SqlDriver
from ..sql import has_view_column


@dataclass
class ConnectionHealthMetrics:
    total_connections: int
    idle_connections: int
    max_total_connections: int
    max_idle_connections: int
    is_total_connections_healthy: bool
    is_idle_connections_healthy: bool

    @property
    def is_healthy(self) -> bool:
        return self.is_total_connections_healthy and self.is_idle_connections_healthy


class ConnectionHealthCalc:
    def __init__(
        self,
        sql_driver: SqlDriver,
        max_total_connections: int = 500,
        max_idle_connections: int = 100,
    ):
        self.sql_driver = sql_driver
        self.max_total_connections = max_total_connections
        self.max_idle_connections = max_idle_connections

    async def total_connections_check(self) -> str:
        """Check if total number of connections is within healthy limits."""
        total = await self._get_total_connections()

        if total <= self.max_total_connections:
            return f"Total connections healthy: {total}"
        return f"High number of connections: {total} (max: {self.max_total_connections})"

    async def idle_connections_check(self) -> str:
        """Check if number of idle connections is within healthy limits."""
        idle = await self._get_idle_connections()

        if idle <= self.max_idle_connections:
            return f"Idle connections healthy: {idle}"
        return f"High number of idle connections: {idle} (max: {self.max_idle_connections})"

    async def connection_health_check(self) -> str:
        """Run all connection health checks and return combined results."""
        total = await self._get_total_connections()
        idle = await self._get_idle_connections()

        if total > self.max_total_connections:
            return f"High number of connections: {total}"
        elif idle > self.max_idle_connections:
            wait_events = await self._get_idle_in_transaction_wait_events()
            message = f"High number of connections idle in transaction: {idle}"
            if wait_events:
                details = "\n".join(
                    [
                        "Idle in transaction wait events:",
                        *(
                            f"- {event['wait_event_type']}:{event['wait_event']} "
                            f"(count={event['count']})" + (f" - {event['wait_event_description']}" if event["wait_event_description"] else "")
                            for event in wait_events
                        ),
                    ]
                )
                message = f"{message}\n{details}"
            return message
        else:
            return f"Connections healthy: {total} total, {idle} idle"

    async def _get_total_connections(self) -> int:
        """Get the total number of database connections."""
        result = await self.sql_driver.execute_query("""
            SELECT COUNT(*) as count
            FROM pg_stat_activity
        """)
        result_list = [dict(x.cells) for x in result] if result else []
        return result_list[0]["count"] if result_list else 0

    async def _get_idle_connections(self) -> int:
        """Get the number of connections that are idle in transaction."""
        result = await self.sql_driver.execute_query("""
            SELECT COUNT(*) as count
            FROM pg_stat_activity
            WHERE state = 'idle in transaction'
        """)
        result_list = [dict(x.cells) for x in result] if result else []
        return result_list[0]["count"] if result_list else 0

    async def _get_idle_in_transaction_wait_events(self) -> list[dict[str, str | int]]:
        """Return grouped wait-event context for idle-in-transaction sessions."""
        if not await has_view_column(self.sql_driver, "pg_catalog", "pg_wait_events", "name"):
            return []

        try:
            result = await self.sql_driver.execute_query("""
                SELECT
                    COALESCE(a.wait_event_type, 'Unknown') AS wait_event_type,
                    COALESCE(a.wait_event, 'Unknown') AS wait_event,
                    COALESCE(w.description, '') AS wait_event_description,
                    COUNT(*)::int AS count
                FROM pg_stat_activity a
                LEFT JOIN pg_catalog.pg_wait_events w
                    ON w.type = a.wait_event_type
                    AND w.name = a.wait_event
                WHERE a.state = 'idle in transaction'
                GROUP BY 1, 2, 3
                ORDER BY 4 DESC, 1, 2
            """)
            if not result:
                return []
            return [dict(x.cells) for x in result]
        except Exception:
            return []
