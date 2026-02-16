<div align="center">

<img src="assets/postgres-mcp-pro.png" alt="Postgres MCP Pro Logo" width="600"/>

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![PyPI - Version](https://img.shields.io/pypi/v/postgres-mcp)](https://pypi.org/project/postgres-mcp/)
[![Discord](https://img.shields.io/discord/1336769798603931789?label=Discord)](https://discord.gg/4BEHC7ZM)

<h3>Give your AI assistant superpowers for PostgreSQL.</h3>
<p>Index tuning, explain plans, health checks, and safe SQL execution — all through MCP.</p>

<div class="toc">
  <a href="#what-is-this">What is this?</a> •
  <a href="#what-can-it-do">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#usage-examples">Examples</a> •
  <a href="#available-tools">Tools</a> •
  <a href="#faq">FAQ</a> •
  <a href="#credits">Credits</a>
</div>

</div>

---

## What is this?

**Postgres MCP Pro** connects your AI assistant (Claude, Cursor, Windsurf, etc.) directly to your PostgreSQL database — but it does much more than just run queries.

It gives your AI the ability to:
- Check if your database is healthy
- Find and fix slow queries
- Recommend the right indexes for your workload
- Explore your schema and understand your data model
- Execute SQL safely, even on production databases

Think of it as a **database expert that your AI assistant can call on whenever it needs help with Postgres**.

### How it works

Your AI assistant communicates with Postgres MCP Pro using the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) — an open standard that lets AI tools interact with external services. You install the server once, point it at your database, and your AI assistant automatically gains access to all the database tools.

## What can it do?

| Feature | What it means for you |
|---------|----------------------|
| **Database Health Checks** | Spot problems before they become outages — index bloat, connection limits, vacuum issues, replication lag, and more. |
| **Index Tuning** | Automatically analyzes your queries and recommends the best indexes. Uses real optimization algorithms, not guesswork. |
| **Query Plans** | See exactly how Postgres will run a query. Test "what if I added this index?" without actually creating it. |
| **Schema Intelligence** | Your AI understands your tables, columns, constraints, and relationships — so it writes correct SQL from the start. |
| **Safe SQL Execution** | Two modes: **unrestricted** for development (full access), **restricted** for production (read-only with guardrails). |

## Quick Start

You need two things:
1. **Your database connection URL** (the `postgresql://...` string)
2. **Docker** or **Python 3.12+**

### Step 1: Install

**With Docker** (recommended — no dependency issues):

```bash
docker pull crystaldba/postgres-mcp
```

**With Python** (via pipx or uv):

```bash
pipx install postgres-mcp
# or
uv pip install postgres-mcp
```

### Step 2: Connect to your AI assistant

Add this to your AI assistant's MCP configuration file. Replace the database URL with your own.

<details>
<summary><b>Claude Desktop</b></summary>

Config file location:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%/Claude/claude_desktop_config.json`

**Docker:**
```json
{
  "mcpServers": {
    "postgres": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "DATABASE_URI",
        "crystaldba/postgres-mcp",
        "--access-mode=unrestricted"
      ],
      "env": {
        "DATABASE_URI": "postgresql://username:password@localhost:5432/dbname"
      }
    }
  }
}
```

**uvx:**
```json
{
  "mcpServers": {
    "postgres": {
      "command": "uvx",
      "args": ["postgres-mcp", "--access-mode=unrestricted"],
      "env": {
        "DATABASE_URI": "postgresql://username:password@localhost:5432/dbname"
      }
    }
  }
}
```

**pipx:**
```json
{
  "mcpServers": {
    "postgres": {
      "command": "postgres-mcp",
      "args": ["--access-mode=unrestricted"],
      "env": {
        "DATABASE_URI": "postgresql://username:password@localhost:5432/dbname"
      }
    }
  }
}
```

> Docker automatically remaps `localhost` to work from inside the container (uses `host.docker.internal` on macOS/Windows).

</details>

<details>
<summary><b>Cursor</b></summary>

Open the Command Palette, go to **Cursor Settings**, then the **MCP** tab. Add the same configuration as above.

</details>

<details>
<summary><b>Windsurf</b></summary>

Open the Command Palette, go to **Open Windsurf Settings Page**. Add the same configuration as above.

</details>

<details>
<summary><b>Other clients (Goose, Qodo Gen, etc.)</b></summary>

Most MCP clients use a similar JSON config. Adapt the examples above for your client:
- **Goose**: Run `goose configure`, then select `Add Extension`.
- **Qodo Gen**: Open Chat panel > `Connect more tools` > `+ Add new MCP`.

</details>

### Step 3: Choose your access mode

| Mode | Use when | What it does |
|------|----------|-------------|
| `--access-mode=unrestricted` | Development | Full read/write access. Your AI can modify data and schema. |
| `--access-mode=restricted` | Production | Read-only. SQL is parsed and validated before execution. Query time limits enforced. |

### That's it!

Start a conversation with your AI assistant and ask it about your database. It will automatically use the Postgres tools when needed.

## Demo

*From Unusable to Lightning Fast*

We generated a movie app using an AI assistant, but the SQLAlchemy ORM code ran painfully slow. Using Postgres MCP Pro with Cursor, we fixed the performance issues in minutes:

- Fixed slow ORM queries, indexing, and caching
- Fixed a broken page by exploring the data and fixing queries
- Improved top movies by fixing the ORM query to surface better results

See the video below or read the [play-by-play](examples/movie-app.md).

https://github.com/user-attachments/assets/24e05745-65e9-4998-b877-a368f1eadc13

## Usage Examples

Just talk to your AI assistant naturally. Here are some things you can ask:

> Check the health of my database and identify any issues.

> What are the slowest queries in my database? How can I speed them up?

> My app is slow. How can I make it faster?

> Analyze my database workload and suggest indexes to improve performance.

> Help me optimize this query: SELECT * FROM orders JOIN customers ON orders.customer_id = customers.id WHERE orders.created_at > '2023-01-01';

## Available Tools

All tools are exposed via the [MCP tools protocol](https://modelcontextprotocol.io/docs/concepts/tools), which has the widest client support.

| Tool | What it does |
|------|-------------|
| `postgres_list_schemas` | List all schemas in the database. |
| `postgres_list_objects` | List tables, views, sequences, or extensions in a schema. Supports pagination. |
| `postgres_get_object_details` | Show columns, constraints, and indexes for a specific table or object. |
| `postgres_execute_sql` | Run SQL queries. Read-only in restricted mode. Supports pagination. |
| `postgres_explain_query` | Show the execution plan for a query. Can simulate hypothetical indexes. |
| `postgres_get_top_queries` | Find the slowest or most resource-heavy queries (via `pg_stat_statements`). |
| `postgres_analyze_workload_indexes` | Analyze your workload and recommend optimal indexes. |
| `postgres_analyze_query_indexes` | Analyze specific queries (up to 10) and recommend indexes. |
| `postgres_analyze_db_health` | Run health checks: index health, connections, vacuum, replication, cache, constraints, sequences. |

## Advanced Setup

### Remote server (SSE / Streamable HTTP)

By default, the server runs locally over stdio. For remote or shared setups, you can use SSE or streamable HTTP transport:

```bash
# SSE transport
docker run -p 8000:8000 \
  -e DATABASE_URI=postgresql://username:password@localhost:5432/dbname \
  crystaldba/postgres-mcp --access-mode=unrestricted --transport=sse

# Streamable HTTP transport
docker run -p 8000:8000 \
  -e DATABASE_URI=postgresql://username:password@localhost:5432/dbname \
  crystaldba/postgres-mcp --access-mode=unrestricted --transport=streamable-http
```

Then configure your MCP client to connect:

```json
{
  "mcpServers": {
    "postgres": {
      "type": "sse",
      "url": "http://localhost:8000/sse"
    }
  }
}
```

> For Windsurf, use `"serverUrl"` instead of `"url"`.

### Optional Postgres extensions

For index tuning and performance analysis, install these extensions on your database:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;  -- query performance stats
CREATE EXTENSION IF NOT EXISTS hypopg;               -- hypothetical index simulation
```

**Cloud databases** (AWS RDS, Azure, Google Cloud SQL): These extensions are usually available — just run the `CREATE EXTENSION` commands above.

**Self-managed Postgres**: You may need to add `pg_stat_statements` to `shared_preload_libraries` in your Postgres config, and install the `hypopg` package separately via your OS package manager.

### Experimental: LLM-powered index tuning

In addition to the algorithmic index tuner, there's an experimental mode that uses an LLM to propose index configurations iteratively. Set the `OPENAI_API_KEY` environment variable to enable it, then use `method="llm"` when calling the index analysis tools.

## FAQ

**What makes this different from other Postgres MCP servers?**

Most Postgres MCP servers let your AI run queries — that's it. Postgres MCP Pro adds real database expertise: algorithmic index tuning (based on [Microsoft's Database Tuning Advisor](https://www.microsoft.com/en-us/research/wp-content/uploads/2020/06/Anytime-Algorithm-of-Database-Tuning-Advisor-for-Microsoft-SQL-Server.pdf)), deterministic health checks, workload analysis, and hypothetical index simulation. These are proven techniques, not LLM guesses.

**Why not just let the AI write its own health-check queries?**

LLMs are great at reasoning and language, but they can be slow, expensive, and inconsistent for tasks where well-tested algorithms already exist. Postgres MCP Pro pairs the flexibility of AI with the reliability of classical database optimization.

**What Postgres versions are supported?**

Tested with Postgres 12, 15, 16, and 17. Targeting support for versions 13 through 17.

**Is it safe to use on production?**

In **restricted mode**, yes. All SQL is parsed and validated before execution, only read-only operations are allowed, and query execution time is limited. For extra safety, you can also use a read-only database user.

## Credits

This project was originally created by [Crystal DBA](https://www.crystaldba.ai) ([crystaldba/postgres-mcp](https://github.com/crystaldba/postgres-mcp)). Database health checks are adapted from [PgHero](https://github.com/ankane/pghero).

This fork is maintained by [vcode](https://x.com/vcode_sh) ([vcode-sh/postgres-mcp](https://github.com/vcode-sh/postgres-mcp)) with improvements to code architecture, MCP protocol compliance, and developer experience.

## Related Projects

**Postgres MCP Servers**
- [PG-MCP](https://github.com/stuzero/pg-mcp-server) — Flexible connection options, explain plans, extension context.
- [Query MCP](https://github.com/alexander-zuev/supabase-mcp-server) — Supabase Postgres with three-tier safety architecture.
- [Supabase MCP](https://github.com/supabase-community/supabase-mcp) — Supabase management features.
- [Neon MCP](https://github.com/neondatabase-labs/mcp-server-neon) — Neon serverless Postgres management.
- [Nile MCP](https://github.com/niledatabase/nile-mcp-server) — Nile multi-tenant Postgres management.

**DBA & Performance Tools**
- [Dexter](https://github.com/DexterDB/dexter) — Automatic indexing for PostgreSQL.
- [PgHero](https://github.com/ankane/pghero) — Performance dashboard with recommendations.
- [pgAnalyze](https://pganalyze.com/) — Monitoring and analytics platform.
- [Xata Agent](https://github.com/xataio/agent) — AI-powered database health monitoring.

## Development

For contributors and developers who want to work on the project.

### Setup

```bash
git clone https://github.com/vcode-sh/postgres-mcp.git
cd postgres-mcp
uv sync
```

### Run

```bash
uv run postgres-mcp "postgresql://user:password@localhost:5432/dbname"
```

### Test

```bash
# Unit tests only
uv run pytest tests/unit/ -v

# All tests (requires Docker for integration tests with PG 12, 15, 16)
uv run pytest -v --log-cli-level=INFO
```

### Lint & Type Check

```bash
uv run ruff format --check .
uv run ruff check .
uv run pyright
```
