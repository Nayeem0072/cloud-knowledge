# Knowledge Base

Centralised, cloud-hosted knowledge base for Claude Code. Uses LightRAG (graph + vector hybrid retrieval) so Claude can answer relational questions like "what features are affected if I change the user model?" — not just semantic similarity.

## Architecture

```
Markdown docs (this repo)
  → GitHub Action on merge to main
  → scripts/ingest.py (frontmatter → graph triples → LightRAG /insert)
  → LightRAG on Railway (NetworkX graph + vector index)
  → MCP server on Railway (FastAPI wrapper)
  → Claude Code via ~/.claude/config.json
```

## Repository structure

```
knowledge-base/
├── docs/
│   ├── features/   ← One .md per product feature
│   └── services/   ← One .md per backend service
├── scripts/
│   ├── ingest.py           ← Called by GitHub Action to upsert/delete docs
│   └── staleness_check.py  ← Weekly cron: flags missing docs & stale reviews
├── mcp/
│   ├── server.py           ← FastAPI MCP server
│   └── requirements.txt
├── .github/
│   ├── workflows/
│   │   ├── ingest.yml      ← Fires on merge to main for docs/**/*.md
│   │   └── staleness.yml   ← Weekly Monday 09:00 UTC cron
│   └── CODEOWNERS
└── CLAUDE.md               ← Claude Code hook instructions
```

## Deployment

### 1. Deploy LightRAG on Railway

1. Go to [railway.app](https://railway.app) → New project → Deploy from Docker image
2. Image: `ghcr.io/hkuedl/lightrag:latest`
3. Set environment variables:

| Variable | Value |
|----------|-------|
| `LIGHTRAG_WORKING_DIR` | `/data` |
| `OPENAI_API_KEY` | `sk-...` |
| `LIGHTRAG_LLM_MODEL` | `gpt-4o-mini` |
| `LIGHTRAG_EMBEDDING_MODEL` | `text-embedding-3-small` |
| `API_KEY` | a random secret (used to auth ingest + MCP calls) |

4. Copy the Railway public URL (e.g. `https://kb-production.up.railway.app`)

### 2. Deploy MCP server on Railway

1. Add a second service in the same Railway project
2. Deploy `mcp/server.py` — start command: `uvicorn mcp.server:app --host 0.0.0.0 --port $PORT`
3. Set environment variables:

| Variable | Value |
|----------|-------|
| `LIGHTRAG_URL` | Your LightRAG Railway URL |
| `LIGHTRAG_API_KEY` | Same as `API_KEY` above |
| `MCP_API_KEY` | A separate random secret for MCP auth |

### 3. Add GitHub Secrets

In this repo → Settings → Secrets and variables → Actions:

| Secret | Value |
|--------|-------|
| `LIGHTRAG_URL` | Your LightRAG Railway URL |
| `LIGHTRAG_API_KEY` | Same as `API_KEY` above |

### 4. Configure Claude Code

Add to `~/.claude/config.json`:

```json
{
  "mcpServers": {
    "knowledge-base": {
      "url": "https://your-mcp-server.up.railway.app",
      "type": "http",
      "headers": {
        "x-api-key": "your-mcp-key"
      }
    }
  }
}
```

### 5. Seed manually (first time)

```bash
pip install requests python-frontmatter
export LIGHTRAG_URL=https://kb-production.up.railway.app
export LIGHTRAG_API_KEY=your-secret-key

for f in docs/features/*.md docs/services/*.md; do
  python scripts/ingest.py upsert "$f"
done
```

## Document schema

Every document must have this frontmatter:

```yaml
---
id: feature-billing          # kebab-case, globally unique
type: feature                # feature | service | concept | adr
service: payments-service    # which service owns this
depends_on:
  - feature-user-accounts
related_to:
  - feature-promo-codes
owned_by: payments-team
status: stable               # stable | beta | deprecated
last_reviewed: 2026-05-21
---
```

And these H2 sections in order:

- `## What it does`
- `## Business rules`
- `## Connections`
- `## Data model`
- `## Events emitted`
- `## Known limitations`

## MCP tools available to Claude Code

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `query_knowledge_base` | `query: string, mode?: string` | Hybrid graph+vector search |
| `get_feature` | `feature_id: string` | Fetch a specific feature doc by id |
| `list_features` | `service?: string` | Discover all features, optionally by service |
