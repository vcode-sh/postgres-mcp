# ruff: noqa: B008
import logging
from typing import Optional

from mcp.types import CallToolResult
from pydantic import Field

from postgres_mcp.sql import SafeSqlDriver
from postgres_mcp.sql import has_view_column

from ._response import format_error_response
from ._response import format_text_response
from ._state import get_sql_driver

logger = logging.getLogger(__name__)


async def postgres_list_schemas() -> CallToolResult:
    """List all schemas in the database."""
    try:
        sql_driver = await get_sql_driver()
        rows = await sql_driver.execute_query(
            """
            SELECT
                schema_name,
                schema_owner,
                CASE
                    WHEN schema_name LIKE 'pg_%' THEN 'System Schema'
                    WHEN schema_name = 'information_schema' THEN 'System Information Schema'
                    ELSE 'User Schema'
                END as schema_type
            FROM information_schema.schemata
            ORDER BY schema_type, schema_name
            """
        )
        schemas = [row.cells for row in rows] if rows else []
        return format_text_response(schemas)
    except Exception as e:
        logger.error(f"Error listing schemas: {e}")
        return format_error_response(str(e))


async def postgres_list_objects(
    schema_name: str = Field(description="Schema name"),
    object_type: str = Field(description="Object type: 'table', 'view', 'sequence', or 'extension'", default="table"),
    offset: Optional[int] = Field(description="Number of objects to skip (for pagination)", default=None),
    limit: Optional[int] = Field(description="Maximum number of objects to return (for pagination)", default=None),
) -> CallToolResult:
    """List objects of a given type in a schema."""
    try:
        sql_driver = await get_sql_driver()

        param_pagination = ""
        param_pagination_args: list[object] = []
        raw_pagination = ""
        if limit is not None:
            param_pagination += " LIMIT {}"
            param_pagination_args.append(limit)
            raw_pagination += f" LIMIT {int(limit)}"
        if offset is not None:
            param_pagination += " OFFSET {}"
            param_pagination_args.append(offset)
            raw_pagination += f" OFFSET {int(offset)}"

        if object_type in ("table", "view"):
            table_type = "BASE TABLE" if object_type == "table" else "VIEW"
            rows = await SafeSqlDriver.execute_param_query(
                sql_driver,
                f"""
                SELECT table_schema, table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = {{}} AND table_type = {{}}
                ORDER BY table_name{param_pagination}
                """,
                [schema_name, table_type, *param_pagination_args],
            )
            objects = (
                [{"schema": row.cells["table_schema"], "name": row.cells["table_name"], "type": row.cells["table_type"]} for row in rows]
                if rows
                else []
            )

        elif object_type == "sequence":
            rows = await SafeSqlDriver.execute_param_query(
                sql_driver,
                f"""
                SELECT sequence_schema, sequence_name, data_type
                FROM information_schema.sequences
                WHERE sequence_schema = {{}}
                ORDER BY sequence_name{param_pagination}
                """,
                [schema_name, *param_pagination_args],
            )
            objects = (
                [{"schema": row.cells["sequence_schema"], "name": row.cells["sequence_name"], "data_type": row.cells["data_type"]} for row in rows]
                if rows
                else []
            )

        elif object_type == "extension":
            query = f"""
                SELECT extname, extversion, extrelocatable
                FROM pg_extension
                ORDER BY extname{raw_pagination}
                """
            rows = await sql_driver.execute_query(query)  # type: ignore[arg-type]
            objects = (
                [{"name": row.cells["extname"], "version": row.cells["extversion"], "relocatable": row.cells["extrelocatable"]} for row in rows]
                if rows
                else []
            )

        else:
            return format_error_response(f"Unsupported object type: {object_type}")

        return format_text_response(objects)
    except Exception as e:
        logger.error(f"Error listing objects: {e}")
        return format_error_response(str(e))


async def postgres_get_object_details(
    schema_name: str = Field(description="Schema name"),
    object_name: str = Field(description="Object name"),
    object_type: str = Field(description="Object type: 'table', 'view', 'sequence', or 'extension'", default="table"),
) -> CallToolResult:
    """Get detailed information about a database object."""
    try:
        sql_driver = await get_sql_driver()

        if object_type in ("table", "view"):
            col_rows = await SafeSqlDriver.execute_param_query(
                sql_driver,
                """
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    column_default,
                    is_generated,
                    generation_expression
                FROM information_schema.columns
                WHERE table_schema = {} AND table_name = {}
                ORDER BY ordinal_position
                """,
                [schema_name, object_name],
            )
            columns = (
                [
                    {
                        "column": r.cells["column_name"],
                        "data_type": r.cells["data_type"],
                        "is_nullable": r.cells["is_nullable"],
                        "default": r.cells["column_default"],
                        "is_generated": r.cells["is_generated"],
                        "generation_expression": r.cells["generation_expression"],
                    }
                    for r in col_rows
                ]
                if col_rows
                else []
            )

            con_rows = await SafeSqlDriver.execute_param_query(
                sql_driver,
                """
                SELECT tc.constraint_name, tc.constraint_type, kcu.column_name
                FROM information_schema.table_constraints AS tc
                LEFT JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.table_schema = {} AND tc.table_name = {}
                """,
                [schema_name, object_name],
            )

            has_conenforced = await has_view_column(sql_driver, "pg_catalog", "pg_constraint", "conenforced")
            con_meta_rows = await SafeSqlDriver.execute_param_query(
                sql_driver,
                f"""
                SELECT
                    con.conname AS constraint_name,
                    con.convalidated AS is_validated,
                    {"con.conenforced AS is_enforced" if has_conenforced else "TRUE AS is_enforced"}
                FROM pg_catalog.pg_constraint con
                INNER JOIN pg_catalog.pg_class rel ON rel.oid = con.conrelid
                INNER JOIN pg_catalog.pg_namespace nsp ON nsp.oid = rel.relnamespace
                WHERE nsp.nspname = {{}} AND rel.relname = {{}}
                """,
                [schema_name, object_name],
            )
            con_meta_by_name = {r.cells["constraint_name"]: r.cells for r in con_meta_rows} if con_meta_rows else {}

            constraints: dict[str, dict[str, object]] = {}
            if con_rows:
                for row in con_rows:
                    cname = row.cells["constraint_name"]
                    ctype = row.cells["constraint_type"]
                    col = row.cells["column_name"]

                    if cname not in constraints:
                        constraints[cname] = {"type": ctype, "columns": []}
                    if col:
                        cols_list: list[object] = constraints[cname]["columns"]  # type: ignore[assignment]
                        cols_list.append(col)

                    meta = con_meta_by_name.get(cname)
                    if meta is not None:
                        constraints[cname]["is_validated"] = meta["is_validated"]
                        if has_conenforced:
                            constraints[cname]["is_enforced"] = meta["is_enforced"]

            constraints_list = [{"name": name, **data} for name, data in constraints.items()]

            idx_rows = await SafeSqlDriver.execute_param_query(
                sql_driver,
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = {} AND tablename = {}
                """,
                [schema_name, object_name],
            )

            indexes = [{"name": r.cells["indexname"], "definition": r.cells["indexdef"]} for r in idx_rows] if idx_rows else []

            result = {
                "basic": {"schema": schema_name, "name": object_name, "type": object_type},
                "columns": columns,
                "constraints": constraints_list,
                "indexes": indexes,
            }

        elif object_type == "sequence":
            rows = await SafeSqlDriver.execute_param_query(
                sql_driver,
                """
                SELECT sequence_schema, sequence_name, data_type, start_value, increment
                FROM information_schema.sequences
                WHERE sequence_schema = {} AND sequence_name = {}
                """,
                [schema_name, object_name],
            )

            if rows and rows[0]:
                row = rows[0]
                result = {
                    "schema": row.cells["sequence_schema"],
                    "name": row.cells["sequence_name"],
                    "data_type": row.cells["data_type"],
                    "start_value": row.cells["start_value"],
                    "increment": row.cells["increment"],
                }
            else:
                result = {}

        elif object_type == "extension":
            rows = await SafeSqlDriver.execute_param_query(
                sql_driver,
                """
                SELECT extname, extversion, extrelocatable
                FROM pg_extension
                WHERE extname = {}
                """,
                [object_name],
            )

            if rows and rows[0]:
                row = rows[0]
                result = {"name": row.cells["extname"], "version": row.cells["extversion"], "relocatable": row.cells["extrelocatable"]}
            else:
                result = {}

        else:
            return format_error_response(f"Unsupported object type: {object_type}")

        return format_text_response(result)
    except Exception as e:
        logger.error(f"Error getting object details: {e}")
        return format_error_response(str(e))
