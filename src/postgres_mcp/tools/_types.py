from typing import List
from typing import Union

import mcp.types as types

ResponseType = List[Union[types.TextContent, types.ImageContent, types.EmbeddedResource]]

PG_STAT_STATEMENTS = "pg_stat_statements"
