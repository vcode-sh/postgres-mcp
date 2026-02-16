from dataclasses import dataclass

from ..sql import SqlDriver
from ..sql import has_view_column


@dataclass
class ConstraintMetrics:
    schema: str
    table: str
    name: str
    referenced_schema: str | None
    referenced_table: str | None
    validated: bool
    enforced: bool


class ConstraintHealthCalc:
    def __init__(self, sql_driver: SqlDriver):
        self.sql_driver = sql_driver

    async def invalid_constraints_check(self) -> str:
        """Check for invalid and, when available, not-enforced constraints.

        Returns:
            String describing any invalid constraints found
        """
        metrics = await self._get_invalid_constraints()

        if not metrics:
            return "No invalid or not-enforced constraints found."

        result = ["Constraint issues found:"]
        for metric in metrics:
            if not metric.validated and not metric.enforced:
                issue = "is invalid and not enforced"
            elif not metric.validated:
                issue = "is invalid"
            else:
                issue = "is not enforced"

            if metric.referenced_table:
                result.append(
                    f"Constraint '{metric.name}' on table '{metric.schema}.{metric.table}' "
                    f"referencing '{metric.referenced_schema}.{metric.referenced_table}' {issue}"
                )
            else:
                result.append(f"Constraint '{metric.name}' on table '{metric.schema}.{metric.table}' {issue}")
        return "\n".join(result)

    async def _get_invalid_constraints(self) -> list[ConstraintMetrics]:
        """Get all invalid (and optionally not-enforced) constraints in the database."""
        has_conenforced = await has_view_column(self.sql_driver, "pg_catalog", "pg_constraint", "conenforced")
        where_clause = "con.convalidated = false"
        if has_conenforced:
            where_clause = f"({where_clause} OR con.conenforced = false)"

        results = await self.sql_driver.execute_query(f"""
            SELECT
                nsp.nspname AS schema,
                rel.relname AS table,
                con.conname AS name,
                fnsp.nspname AS referenced_schema,
                frel.relname AS referenced_table,
                con.convalidated AS validated,
                {"con.conenforced AS enforced" if has_conenforced else "TRUE AS enforced"}
            FROM
                pg_catalog.pg_constraint con
            INNER JOIN
                pg_catalog.pg_class rel ON rel.oid = con.conrelid
            LEFT JOIN
                pg_catalog.pg_class frel ON frel.oid = con.confrelid
            LEFT JOIN
                pg_catalog.pg_namespace nsp ON nsp.oid = con.connamespace
            LEFT JOIN
                pg_catalog.pg_namespace fnsp ON fnsp.oid = frel.relnamespace
            WHERE
                {where_clause}
        """)

        if not results:
            return []

        result_list = [dict(x.cells) for x in results]

        return [
            ConstraintMetrics(
                schema=row["schema"],
                table=row["table"],
                name=row["name"],
                referenced_schema=row["referenced_schema"],
                referenced_table=row["referenced_table"],
                validated=row["validated"],
                enforced=row["enforced"],
            )
            for row in result_list
        ]

    async def _get_total_constraints(self) -> int:
        """Get the total number of constraints."""
        result = await self.sql_driver.execute_query("""
            SELECT COUNT(*) as count
            FROM information_schema.table_constraints
        """)
        if not result:
            return 0
        result_list = [dict(x.cells) for x in result]
        return result_list[0]["count"] if result_list else 0

    async def _get_active_constraints(self) -> int:
        """Get the number of active constraints."""
        result = await self.sql_driver.execute_query("""
            SELECT COUNT(*) as count
            FROM information_schema.table_constraints
            WHERE is_deferrable = 'NO'
        """)
        if not result:
            return 0
        result_list = [dict(x.cells) for x in result]
        return result_list[0]["count"] if result_list else 0
