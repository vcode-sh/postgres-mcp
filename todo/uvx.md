# uvx-first Adoption Plan for postgres-mcp

## Goal
- Make `uvx` (or `uv tool install postgres-mcp` + direct binary) the **default recommended launch path** for end users in docs and examples.
- Keep Docker and other transport options available as explicit alternatives.
- Reduce onboarding friction compared with current container-first experience.
- Keep production/security behavior unchanged unless explicitly documented.

**Owner:** TBD
**Target date (target):** TBD
**Status:** Planned

## Current baseline (as of repository state)
- Package already exposes console entrypoint `postgres-mcp` in `pyproject.toml`.
- README already includes `uvx` usage, but Docker is currently the recommended path in many examples.
- Current client config in repo (`.mcp.json`) uses Docker example for postgres server.
- Docker entrypoint includes localhost remapping (`host.docker.internal` / `172.17.0.1`) for container use.

## Why `uvx`
1. Matches current MCP ecosystem pattern (comparable to `bunx`/`npx` one-command runtime).
2. Avoids Docker image pull + container runtime requirements for most users.
3. Keeps Python server implementation and all existing tool surface unchanged.
4. Works on Linux/macOS/Windows where `uv` is already available.

---

## Planned end state
- `README.md`: first-class “Recommended install/run” section shows `uvx` + MCP config snippets.
- `.mcp.json` example includes at least one `uvx`-based profile and Docker marked as optional.
- New docs include clear transport guidance (`stdio` default), env var behavior (`DATABASE_URI`), and troubleshooting.
- CI/lifecycle validates `uvx` startup command syntax in docs/tests where feasible.

---

## High-level architecture decisions
- No runtime rewrite in Rust/TypeScript is needed for this initiative.
- Keep Python server code as-is for now.
- Do not remove Docker support; keep as fallback for containerized / locked-down environments.
- Favor additive changes to docs + examples + packaging metadata.
- Avoid hard dependency on `bun` for core package distribution.

---

## Workstreams

### A) Documentation and UX (priority: P0)
#### A1. README restructuring
- [ ] Move `uvx` block to top of Quick Start, before Docker.
- [ ] Add explicit “Recommended path (uvx)” section with:
  - command to run once with environment variable
  - command for restricted mode
  - command for streamable-http transport
- [ ] Keep Docker section after UV-based path (clearly marked as alternative).
- [ ] Update all local config examples to use `command: "postgres-mcp"` where applicable.
- [ ] Add “localhost and host mapping” note to Docker section only.
- [ ] Add security note:
  - restricted mode for production
  - read-only db user optional best practice
- [ ] Ensure example snippets are valid JSON for common clients.

#### A2. Client config snippets
- [ ] Create/refresh a dedicated MCP section with examples for:
  - Claude Desktop
  - Cursor
  - Windsurf
  - Generic MCP clients
- [ ] For each, include both:
  - `uvx` version (recommended)
  - `uv tool install` version (alternative lower overhead)
- [ ] Add a dedicated “no Docker no Docker Desktop” section.

#### A3. Troubleshooting section
- [ ] Add common `uvx` troubleshooting bullets:
  - `uv` not installed
  - `uvx` command not on PATH
  - env var `DATABASE_URI` not propagated by editor/client
  - transport mismatch with MCP client type
- [ ] Add verification command:
  - `uvx postgres-mcp --help`
  - `DATABASE_URI=... uvx postgres-mcp --access-mode=restricted --transport=stdio`

---

### B) Default config and examples (priority: P0)
#### B1. Replace docker-first sample config
- [ ] Update `.mcp.json` (repo example) to include `postgres-vcodesh` with `uvx`.
- [ ] Add optional second block `postgres-vcodesh-docker` for Docker users.
- [ ] Keep env var-based DB URL usage (not hardcoded credentials).

#### B2. Add “paste-ready” snippets
- [ ] Add a short file under `examples/` (or update existing) with copy-paste configs for uvx.
- [ ] Add one JSON block per client style.

#### B3. Add quick onboarding checklist
- [ ] Include ordered checklist:
  - install uv
  - run uvx help
  - set DATABASE_URI
  - add to MCP config
  - verify tool list available

---

### C) Distribution hygiene (priority: P1)
#### C1. Confirm package metadata supports direct execution
- [ ] Verify `project.scripts` already includes `postgres-mcp` in `pyproject.toml` and remains stable.
- [ ] Validate command name and entrypoint docs are consistent in all docs.
- [ ] Ensure no `mcp.json` examples pass command as `postgres-mcp` without requiring path wrappers.

#### C2. Publish and versioning policy
- [ ] Define minimum version bump strategy for docs-only changes (usually patch/minor according to your release policy).
- [ ] Add release note entry describing `uvx` as recommended path.
- [ ] Update badge/short description where installation method is listed.

#### C3. Optional: uvx wrapper convenience package
- [ ] Evaluate if a tiny npm/bun wrapper is still needed for parity with pure Bun CLI flow.
- [ ] If yes, create separate plan; otherwise explicitly document `uvx`/`uv tool install` as default.

---

### D) Quality and validation (priority: P1)
#### D1. Config/lint checks
- [ ] Add docs consistency checks if available in repo pipeline (e.g. markdown lint or examples check).
- [ ] Manual review checklist for each documented command:
  - command names
  - argument names
  - env var names
  - transport flags

#### D2. Compatibility validation
- [ ] Quick matrix for docs test:
  - Linux/macOS/Windows command forms
  - Claude/Cursor/Windsurf style JSON shape differences
  - `stdio` and streamable HTTP examples

#### D3. No functional regression
- [ ] Confirm no behavioral change in server code path (except docs/examples/config ergonomics).
- [ ] Keep existing transport and Docker behavior fully functional.

---

## Risks and mitigations
- **Risk:** Some clients do not resolve `uvx` in non-interactive runtime.
  - **Mitigation:** include `uv tool install` alternative with explicit `PATH` note.
- **Risk:** Windows shell/PATH behavior for `uvx` differs by client.
  - **Mitigation:** include explicit `postgres-mcp` and `uv tool install postgres-mcp` fallback.
- **Risk:** Organizations disallow pip/uv network access.
  - **Mitigation:** keep Docker section with enterprise-friendly notes and registry pinning.
- **Risk:** Confusion around transport defaults (`stdio` vs SSE/HTTP).
  - **Mitigation:** clearly mark default transport and provide examples with `--transport` explicitly.

---

## Implementation checklist (by sequence)
1. Update `.mcp.json` example to uvx-first.
2. Rework README Quick Start and add dedicated recommended-path sections.
3. Add dedicated client snippets in `examples/`.
4. Add troubleshooting + onboarding checklist section.
5. Add release note and version guidance.
6. Optional follow-up: wrapper package decision.

---

## Deliverables
- `todo/uvx.md` (this plan)
- Updated `README.md` with uvx-first onboarding
- Updated `.mcp.json` example
- Optional: `examples/*` with uvx configs
- Optional: release note + changelog note

## Exit criteria
- New users can run successfully with 2–3 steps using `uvx` in first run.
- Docker remains functional and documented as fallback.
- No server code changes needed for core plan implementation.
- Documentation and examples reflect a single clear recommended path.
