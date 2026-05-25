# Knowledge Base

Centralised, cloud-hosted knowledge base for Claude Code. Uses LightRAG (graph + vector hybrid retrieval) so Claude can answer relational questions like "what features are affected if I change the user model?" — not just semantic similarity.

## Architecture

```
Markdown docs (this repo)
  → GitHub Action on merge to main
  → scripts/ingest.py (frontmatter → graph triples → LightRAG /insert)
  → LightRAG on OCI VM (NetworkX graph + vector index)
  → MCP server on OCI VM (FastAPI wrapper, nginx reverse proxy)
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

### Prerequisites

- OCI VM (Ubuntu 22.04 recommended, at least 2 OCPU / 4 GB RAM)
- Docker + Docker Compose installed
- A domain or public IP for the VM
- OCI Security List / firewall rules: open ports 80 and 443 (or whichever port you expose)

### 1. Provision the OCI VM

```bash
# SSH into your VM
ssh ubuntu@<your-oci-public-ip>

# Install Docker
sudo apt update && sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
```

Open the required ports in OCI Console → Networking → Virtual Cloud Network → Security Lists:
- Ingress: TCP 80 and 443 from `0.0.0.0/0`
- (Optional) TCP 8080 / 8000 for direct access during testing

### 2. Deploy LightRAG

```bash
mkdir -p ~/kb && cd ~/kb
mkdir -p data/lightrag

# Create docker-compose.yml
cat > docker-compose.yml <<'EOF'
services:
  lightrag:
    image: ghcr.io/hkuds/lightrag:latest
    restart: unless-stopped
    ports:
      - "9621:9621"
    volumes:
      - ./data/lightrag:/data
    environment:
      LIGHTRAG_WORKING_DIR: /data
      LLM_BINDING: openai
      LLM_BINDING_API_KEY: ${OPENAI_API_KEY}
      LLM_MODEL: ${LLM_MODEL:-gpt-4.1-mini}
      EMBEDDING_BINDING: openai
      EMBEDDING_BINDING_API_KEY: ${OPENAI_API_KEY}
      EMBEDDING_MODEL: ${EMBEDDING_MODEL:-text-embedding-3-small}
      EMBEDDING_DIM: ${EMBEDDING_DIM:-1536}
      API_KEY: ${LIGHTRAG_API_KEY}

  mcp:
    build: ./mcp
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      LIGHTRAG_URL: http://lightrag:9621
      LIGHTRAG_API_KEY: ${LIGHTRAG_API_KEY}
      MCP_API_KEY: ${MCP_API_KEY}
    depends_on:
      - lightrag
EOF

# Create .env (never commit this)
cat > .env <<'EOF'
OPENAI_API_KEY=sk-...
LIGHTRAG_API_KEY=<random-secret>
MCP_API_KEY=<separate-random-secret>
LLM_BINDING=openai
LLM_MODEL=gpt-4.1-mini
EMBEDDING_BINDING=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
EOF
chmod 600 .env

# Copy the mcp/ directory to ~/kb/ before starting.
# If you have the repo cloned on the VM (e.g. /root/kb-code/cloud-knowledge):
#   cp -r /root/kb-code/cloud-knowledge/mcp ~/kb/mcp
# Or from your local machine:
#   scp -r ./mcp root@<your-oci-ip>:~/kb/

docker compose up -d
```

> The `mcp` service builds from `mcp/Dockerfile` in this repo. Copy the `mcp/` directory
> to `~/kb/mcp/` on the VM before running `docker compose up -d`, otherwise the build step
> will fail with "path not found".

### 3. Expose via HAProxy

Add a path-based route to your existing HAProxy config. Back up first:

```bash
cp /etc/haproxy/haproxy.cfg /etc/haproxy/haproxy.cfg.bak.$(date +%Y%m%d)
```

In `frontend https_front`, add the KB ACL **before** any catch-all path rule:

```haproxy
frontend https_front
    bind *:443 ssl crt /your/cert.pem

    acl host_main hdr(host) -i <your-domain>
    acl url_kb    path_beg /kb

    use_backend kb_mcp_backend if host_main url_kb
    # ... your existing use_backend rules below ...

backend kb_mcp_backend
    balance roundrobin
    option forwardfor
    http-request set-path "%[path,regsub(^/kb,)]"
    server mcp_1 127.0.0.1:8000 check
```

The `/kb` ACL must come before any catch-all path rule (`path_beg /`) or it will never match.

```bash
haproxy -c -f /etc/haproxy/haproxy.cfg   # validate
systemctl reload haproxy
```

Verify:
```bash
curl https://<your-domain>/kb/health
# {"status": "ok"}
```

### 4. Add GitHub Secrets

In this repo → Settings → Secrets and variables → Actions:

| Secret | Value |
|--------|-------|
| `LIGHTRAG_URL` | `https://<your-domain>/kb` (or `http://<public-ip>:9621` for direct access) |
| `LIGHTRAG_API_KEY` | Same as `LIGHTRAG_API_KEY` in `.env` |

### 5. Configure Claude Code

Add to `~/.claude/config.json`:

```json
{
  "mcpServers": {
    "knowledge-base": {
      "url": "https://<your-domain>",
      "type": "http",
      "headers": {
        "x-api-key": "<MCP_API_KEY>"
      }
    }
  }
}
```

### 6. Seed manually (first time)

```bash
pip install requests python-frontmatter

export LIGHTRAG_URL=https://<your-domain>/kb
export LIGHTRAG_API_KEY=<your-lightrag-api-key>

python scripts/seed.py
```

`seed.py` walks all `docs/**/*.md`, ingests each file, and reports a per-file success/failure summary. Run it any time you need to re-seed a fresh LightRAG instance.

### Systemd / persistence

Docker Compose with `restart: unless-stopped` will restart containers after a VM reboot automatically, as long as the Docker daemon is enabled:

```bash
sudo systemctl enable docker
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
