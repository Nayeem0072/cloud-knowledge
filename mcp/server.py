"""
MCP server — thin FastAPI wrapper around LightRAG.

Exposes three tools that Claude Code calls via the MCP protocol:
    POST /mcp/query_knowledge_base  — hybrid graph+vector search
    GET  /mcp/get_feature/{id}      — local graph query by feature id
    GET  /mcp/list_features         — global graph query, optional ?service= filter

Authentication: every request must include the header `x-api-key: <MCP_API_KEY>`.

Required environment variables:
    LIGHTRAG_URL      — e.g. https://kb-production.up.railway.app
    LIGHTRAG_API_KEY  — Bearer token for LightRAG API
    MCP_API_KEY       — Secret shared with Claude Code clients
"""

import os

import requests
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


app = FastAPI(title="Knowledge Base MCP Server")

LIGHTRAG_URL = os.environ["LIGHTRAG_URL"].rstrip("/")
LIGHTRAG_KEY = os.environ["LIGHTRAG_API_KEY"]
MCP_KEY = os.environ["MCP_API_KEY"]


def _lg_headers() -> dict:
    return {"Authorization": f"Bearer {LIGHTRAG_KEY}"}


def _require_auth(x_api_key: str) -> None:
    if x_api_key != MCP_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _lightrag_query(query: str, mode: str) -> dict:
    resp = requests.post(
        f"{LIGHTRAG_URL}/query",
        headers=_lg_headers(),
        json={"query": query, "mode": mode},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str
    mode: str = "hybrid"


@app.post("/mcp/query_knowledge_base")
def query_knowledge_base(
    req: QueryRequest,
    x_api_key: str = Header(...),
) -> dict:
    """
    Hybrid graph+vector search — use for all open-ended questions.

    modes: naive | local | global | hybrid (default)
    """
    _require_auth(x_api_key)
    return _lightrag_query(req.query, req.mode)


@app.get("/mcp/get_feature/{feature_id}")
def get_feature(
    feature_id: str,
    x_api_key: str = Header(...),
) -> dict:
    """
    Fetch a specific feature doc by its frontmatter id (e.g. 'feature-billing').
    Uses local graph mode to return the node and its immediate edges.
    """
    _require_auth(x_api_key)
    return _lightrag_query(feature_id, "local")


@app.get("/mcp/list_features")
def list_features(
    service: str | None = None,
    x_api_key: str = Header(...),
) -> dict:
    """
    Discover all features, optionally filtered by service name.
    Uses global graph mode to traverse community clusters.
    """
    _require_auth(x_api_key)
    query = f"list all features in {service}" if service else "list all features"
    return _lightrag_query(query, "global")
