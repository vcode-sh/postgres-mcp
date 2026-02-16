# Releasing

## How Docker images are published

Docker images are built and pushed **automatically** by GitHub Actions to two registries:

| Registry | Image | URL |
|----------|-------|-----|
| DockerHub | `vcodesh/postgres-mcp` | https://hub.docker.com/r/vcodesh/postgres-mcp |
| GHCR | `ghcr.io/vcode-sh/postgres-mcp` | https://github.com/orgs/vcode-sh/packages |

Each image is built for **two architectures**: `linux/amd64` and `linux/arm64`.

## Publishing a new version

### Option A: Git tag (recommended)

Create and push a version tag. The workflow triggers automatically.

```bash
git tag v0.2.0
git push origin v0.2.0
```

This publishes:
- `vcodesh/postgres-mcp:0.2.0`
- `vcodesh/postgres-mcp:latest`
- Same tags on `ghcr.io/vcode-sh/postgres-mcp`

### Option B: Manual trigger

Go to [Actions > Build and Push Docker Image](https://github.com/vcode-sh/postgres-mcp/actions/workflows/docker-build-dockerhub.yml), click **"Run workflow"**, and enter the version number (without `v` prefix).

### Option C: CLI

```bash
gh workflow run "Build and Push Docker Image" --field version=0.2.0 --repo vcode-sh/postgres-mcp
```

## Monitoring a build

```bash
# Watch latest run
gh run list --workflow="Build and Push Docker Image" --repo vcode-sh/postgres-mcp --limit=1

# View details of a specific run
gh run view <run-id> --repo vcode-sh/postgres-mcp

# Check for warnings
gh run view --job=<job-id> --repo vcode-sh/postgres-mcp | grep -i warning
```

Typical build time: **~2 minutes** (with cache), **~4-5 minutes** (first build or cache miss).

## Required secrets

These must be configured in [GitHub repo settings > Secrets](https://github.com/vcode-sh/postgres-mcp/settings/secrets/actions):

| Secret | Value |
|--------|-------|
| `DOCKERHUB_USERNAME` | `vcodesh` |
| `DOCKERHUB_TOKEN` | DockerHub access token (create at https://hub.docker.com/settings/security) |

`GITHUB_TOKEN` is provided automatically by GitHub Actions — no setup needed for GHCR.

## Version numbering

Use [semantic versioning](https://semver.org/): `vMAJOR.MINOR.PATCH`

- **Patch** (`v0.1.1`): Bug fixes, minor improvements
- **Minor** (`v0.2.0`): New features, non-breaking changes
- **Major** (`v1.0.0`): Breaking changes (tool renames, removed features)
