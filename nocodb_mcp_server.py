#!/usr/bin/env python3
"""
NocoDB MCP Server (fixed)
- Keeps original structure but fixes param resolution, base_id handling, and list_tables return type.
- Removes accidental Context injection into get_nocodb_client.
- Ensures all tools resolve (nocodb_url, api_token, base_id) consistently.
"""

import os
import json
import httpx
import logging
from typing import Dict, List, Optional, Any
from mcp.server.fastmcp import FastMCP, Context
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route, Mount
import uvicorn
import sys
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# --- Authorization: Bearer <MCP_AUTH_TOKEN> ---
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Разрешим health без токена, всё остальное — только с токеном
        if request.url.path == "/" and request.method in ("GET", "HEAD"):
            return await call_next(request)

        secret = os.environ.get("MCP_AUTH_TOKEN")
        if not secret:
            return JSONResponse({"error": "Server misconfigured: MCP_AUTH_TOKEN not set"}, 500)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth.split(" ", 1)[1].strip() != secret:
            return JSONResponse({"error": "Unauthorized"}, 401)

        return await call_next(request)

# --- Logging ---
logger = logging.getLogger("nocodb-mcp")
logger.setLevel(logging.INFO)

# --- MCP server ---
mcp = FastMCP("NocoDB MCP Server", log_level="INFO")

# ---------- Helpers ----------

def _resolve_base_id(base_id: Optional[str]) -> str:
    base = base_id or os.environ.get("NOCODB_BASE_ID")
    if not base:
        raise ValueError("NocoDB Base ID is not provided (param base_id or ENV NOCODB_BASE_ID).")
    return base

async def get_nocodb_client(
    nocodb_url: Optional[str] = None,
    api_token: Optional[str] = None,
) -> httpx.AsyncClient:
    """
    Create an authenticated httpx AsyncClient for NocoDB.
    Accepts params or falls back to env vars NOCODB_URL/NOCODB_API_TOKEN.
    """
    url = (nocodb_url or os.environ.get("NOCODB_URL") or "").rstrip("/")
    token = api_token or os.environ.get("NOCODB_API_TOKEN")
    if not url:
        raise ValueError("NocoDB URL is not provided (param nocodb_url or ENV NOCODB_URL).")
    if not token:
        raise ValueError("NocoDB API token is not provided (param api_token or ENV NOCODB_API_TOKEN).")
    headers = {"xc-token": token, "Content-Type": "application/json"}
    return httpx.AsyncClient(base_url=url, headers=headers, timeout=30.0)

async def get_table_id(
    client: httpx.AsyncClient,
    base_id: Optional[str],
    table_name: str,
) -> str:
    """
    Resolve a table name or id to the table id, within a base.
    Tries exact id match, then title/table_name/name (case/underscore-insensitive).
    """
    base = _resolve_base_id(base_id)
    resp = await client.get(f"/api/v2/meta/bases/{base}/tables")
    resp.raise_for_status()
    tables = resp.json().get("list", [])

    # exact id match
    for t in tables:
        if t.get("id") == table_name:
            return t["id"]

    needle_raw = table_name.strip()
    needle_norm = needle_raw.lower().replace("_", "").replace(" ", "")
    for t in tables:
        candidates = [
            t.get("title") or "",
            t.get("table_name") or t.get("name") or "",
        ]
        for cand in candidates:
            cand_raw = (cand or "").strip()
            if cand_raw == needle_raw:
                return t["id"]
            cand_norm = cand_raw.lower().replace("_", "").replace(" ", "")
            if cand_norm == needle_norm:
                return t["id"]

    raise ValueError(
        f"Table '{table_name}' not found in base '{base}'. "
        f"Available: {[{'id': t.get('id'), 'title': t.get('title'), 'name': t.get('table_name') or t.get('name')} for t in tables]}"
    )

# ---------- Tools ----------

@mcp.tool()
async def list_tables(
    nocodb_url: Optional[str] = None,
    api_token: Optional[str] = None,
    base_id: Optional[str] = None,
) -> dict:
    """
    List tables for the given base. Always returns a DICT to satisfy validators.
    Return shape: {"tables": [...], "pageInfo": {...}}
    """
    client = await get_nocodb_client(nocodb_url, api_token)
    base = _resolve_base_id(base_id)
    try:
        resp = await client.get(f"/api/v2/meta/bases/{base}/tables")
        resp.raise_for_status()
        data = resp.json()  # {"list":[...], "pageInfo":{...}} in NocoDB v2
        return {"tables": data.get("list", data), "pageInfo": data.get("pageInfo")}
    finally:
        await client.aclose()

@mcp.tool()
async def retrieve_records(
    table_name: str,
    row_id: Optional[str] = None,
    filters: Optional[str] = None,
    limit: Optional[int] = 10,
    offset: Optional[int] = 0,
    sort: Optional[str] = None,
    fields: Optional[str] = None,

    nocodb_url: Optional[str] = None,
    api_token: Optional[str] = None,
    base_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    Retrieve one or multiple records from a NocoDB table.
    """
    if not table_name:
        return {"error": True, "message": "Table name is required"}

    client = await get_nocodb_client(nocodb_url, api_token)
    try:
        table_id = await get_table_id(client, base_id, table_name)

        if row_id:
            url = f"/api/v2/tables/{table_id}/records/{row_id}"
            response = await client.get(url)
        else:
            url = f"/api/v2/tables/{table_id}/records"
            params = {}
            if limit is not None: params["limit"] = limit
            if offset is not None: params["offset"] = offset
            if sort: params["sort"] = sort
            if fields: params["fields"] = fields
            if filters: params["where"] = filters
            response = await client.get(url, params=params)

        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        return {"error": True, "status_code": e.response.status_code, "message": e.response.text}
    except Exception as e:
        return {"error": True, "message": str(e)}
    finally:
        await client.aclose()

@mcp.tool()
async def create_records(
    table_name: str,
    data: Any,
    bulk: bool = False,

    nocodb_url: Optional[str] = None,
    api_token: Optional[str] = None,
    base_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    Create one or multiple records.
    """
    if not table_name:
        return {"error": True, "message": "Table name is required"}
    if data is None:
        return {"error": True, "message": "Data is required"}

    # Normalize bulk data
    if bulk and not isinstance(data, list):
        data = [data]
    if not bulk and isinstance(data, list):
        data = data[0] if data else {}

    client = await get_nocodb_client(nocodb_url, api_token)
    try:
        table_id = await get_table_id(client, base_id, table_name)
        if bulk:
            url = f"/api/v2/tables/{table_id}/records/bulk"
        else:
            url = f"/api/v2/tables/{table_id}/records"
        resp = await client.post(url, json=data)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": True, "status_code": e.response.status_code, "message": e.response.text}
    except Exception as e:
        return {"error": True, "message": str(e)}
    finally:
        await client.aclose()

@mcp.tool()
async def update_records(
    table_name: str,
    row_id: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    bulk: bool = False,
    bulk_ids: Optional[List[str]] = None,

    nocodb_url: Optional[str] = None,
    api_token: Optional[str] = None,
    base_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    Update one or multiple records.
    """
    if not table_name:
        return {"error": True, "message": "Table name is required"}
    if not data:
        return {"error": True, "message": "Data parameter is required for updates"}
    if bulk and not bulk_ids:
        return {"error": True, "message": "Bulk IDs are required for bulk updates"}
    if (not bulk) and not row_id:
        return {"error": True, "message": "Row ID is required for single record update"}

    client = await get_nocodb_client(nocodb_url, api_token)
    try:
        table_id = await get_table_id(client, base_id, table_name)
        if bulk and bulk_ids:
            url = f"/api/v2/tables/{table_id}/records/bulk"
            payload = {"ids": bulk_ids, "data": data}
            resp = await client.patch(url, json=payload)
        else:
            url = f"/api/v2/tables/{table_id}/records/{row_id}"
            resp = await client.patch(url, json=data)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": True, "status_code": e.response.status_code, "message": e.response.text}
    except Exception as e:
        return {"error": True, "message": str(e)}
    finally:
        await client.aclose()

@mcp.tool()
async def delete_records(
    table_name: str,
    row_id: Optional[str] = None,
    bulk: bool = False,
    bulk_ids: Optional[List[str]] = None,

    nocodb_url: Optional[str] = None,
    api_token: Optional[str] = None,
    base_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    Delete one or multiple records.
    """
    if not table_name:
        return {"error": True, "message": "Table name is required"}
    if bulk and not bulk_ids:
        return {"error": True, "message": "Bulk IDs are required for bulk deletion"}
    if (not bulk) and not row_id:
        return {"error": True, "message": "Row ID is required for single record deletion"}

    client = await get_nocodb_client(nocodb_url, api_token)
    try:
        table_id = await get_table_id(client, base_id, table_name)
        if bulk and bulk_ids:
            url = f"/api/v2/tables/{table_id}/records/bulk"
            resp = await client.request("DELETE", url, json={"ids": bulk_ids})
        else:
            url = f"/api/v2/tables/{table_id}/records/{row_id}"
            resp = await client.delete(url)
        resp.raise_for_status()
        # 204 no content -> fabricate success json
        if resp.status_code == 204:
            return {"success": True, "message": "Record(s) deleted successfully"}
        try:
            data = resp.json()
            if isinstance(data, (int, float)):
                return {"success": True, "message": f"{int(data)} record(s) deleted successfully"}
            if not isinstance(data, dict):
                return {"success": True, "message": "Record(s) deleted successfully", "response_data": data}
            return data
        except json.JSONDecodeError:
            return {"success": True, "message": "Record(s) deleted successfully (non-JSON response)"}
    except httpx.HTTPStatusError as e:
        return {"error": True, "status_code": e.response.status_code, "message": e.response.text}
    except Exception as e:
        return {"error": True, "message": str(e)}
    finally:
        await client.aclose()

@mcp.tool()
async def get_schema(
    table_name: str,
    nocodb_url: Optional[str] = None,
    api_token: Optional[str] = None,
    base_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    Retrieve table schema (columns) for a table.
    """
    if not table_name:
        return {"error": True, "message": "Table name is required"}

    client = await get_nocodb_client(nocodb_url, api_token)
    try:
        table_id = await get_table_id(client, base_id, table_name)
        url = f"/api/v2/meta/tables/{table_id}"
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": True, "status_code": e.response.status_code, "message": e.response.text}
    except Exception as e:
        return {"error": True, "message": str(e)}
    finally:
        await client.aclose()

# ---------- New Tools ----------



# ---------- Starlette app (health + SSE) ----------

def create_app():
    mcp_sse = mcp.sse_app()  # exposes /sse
    async def health(_req):
        return PlainTextResponse("ok")
    app = Starlette(routes=[
        Route("/", health, methods=["GET", "HEAD"]),
        Mount("/", app=mcp_sse),
    ])
    if hasattr(app.router, "redirect_slashes"):
        app.router.redirect_slashes = False
    return app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Python version: {sys.version}")
    print("Starting NocoDB MCP server (fixed)")
    print(f"Env NOCODB_URL set: {'NOCODB_URL' in os.environ}")
    uvicorn.run(create_app(), host="0.0.0.0", port=port)





