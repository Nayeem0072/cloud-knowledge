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
    image: ghcr.io/hkuedl/lightrag:latest
    restart: unless-stopped
    ports:
      - "9621:9621"
    volumes:
      - ./data/lightrag:/data
    environment:
      LIGHTRAG_WORKING_DIR: /data
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      LIGHTRAG_LLM_MODEL: ${LIGHTRAG_LLM_MODEL:-gpt-4o-mini}
      LIGHTRAG_EMBEDDING_MODEL: ${LIGHTRAG_EMBEDDING_MODEL:-text-embedding-3-small}
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
EOF
chmod 600 .env

docker compose up -d
```

> The `mcp` service expects a `Dockerfile` in the `mcp/` directory. Add one that runs:
> `CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]`

### 3. Expose via nginx (HTTPS)

Install nginx and certbot, then create `/etc/nginx/sites-available/kb`:

```nginx
server {
    listen 80;
    server_name <your-domain-or-ip>;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name <your-domain-or-ip>;

    ssl_certificate     /etc/letsencrypt/live/<your-domain>/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/<your-domain>/privkey.pem;

    # MCP server
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # LightRAG API (optional — restrict if not needed publicly)
    location /lightrag/ {
        proxy_pass http://127.0.0.1:9621/;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/kb /etc/nginx/sites-enabled/
sudo certbot --nginx -d <your-domain>
sudo nginx -s reload
```

### 4. Add GitHub Secrets

In this repo → Settings → Secrets and variables → Actions:

| Secret | Value |
|--------|-------|
| `LIGHTRAG_URL` | `https://<your-domain>/lightrag` (or `http://<public-ip>:9621` if not behind nginx) |
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
export LIGHTRAG_URL=https://<your-domain>/lightrag
export LIGHTRAG_API_KEY=<your-lightrag-api-key>

for f in docs/features/*.md docs/services/*.md; do
  python scripts/ingest.py upsert "$f"
done
```

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
