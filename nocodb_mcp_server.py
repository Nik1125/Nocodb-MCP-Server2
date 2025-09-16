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

@mcp.tool()
async def find_contact_by_name(
    table_name: str,
    name: str,
    limit: int = 5,
    nocodb_url: Optional[str] = None,
    api_token: Optional[str] = None,
    base_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    Упрощённый поиск контакта по полю Contact_Name.
    Пример: find_contact_by_name("Contacts", "Nikita Aleksyeyenko", 1)

    Возвращает ровно то, что возвращает /tables/{id}/records.
    """
    if not table_name:
        return {"error": True, "message": "Table name is required"}
    if not name:
        return {"error": True, "message": "Name is required"}

    client = await get_nocodb_client(nocodb_url, api_token)
    try:
        table_id = await get_table_id(client, base_id, table_name)

        # Собираем корректный where (с кавычками для строки)
        where = f"(Contact_Name,eq,'{name}')"

        params = {"limit": limit, "where": where}
        url = f"/api/v2/tables/{table_id}/records"
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": True, "status_code": e.response.status_code, "message": e.response.text}
    except Exception as e:
        return {"error": True, "message": str(e)}
    finally:
        await client.aclose()

@mcp.tool()
async def find_by_field(
    table_name: str,
    field: str,
    value: Any,
    op: str = "eq",          # eq, neq, gt, gte, lt, lte, like, in, nin ...
    limit: int = 25,
    nocodb_url: Optional[str] = None,
    api_token: Optional[str] = None,
    base_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    Универсальный поиск по одному полю.
    Примеры:
      find_by_field("Contacts", "Contact_Name", "Nikita", op="eq", limit=1)
      find_by_field("Leads", "Score", 80, op="gt")
      find_by_field("Contacts", "Email", "%@gmail.com", op="like")
    """
    if not table_name:
        return {"error": True, "message": "Table name is required"}
    if not field:
        return {"error": True, "message": "Field is required"}

    # Валидируем оператор
    allowed_ops = {"eq","neq","gt","gte","lt","lte","like","in","nin"}
    if op not in allowed_ops:
        return {"error": True, "message": f"Unsupported op '{op}'. Allowed: {sorted(allowed_ops)}"}

    # Подготовим значение: строки в кавычки, числа — как есть, списки для IN/NIN
    def _fmt(v: Any) -> str:
        if v is None:
            return "null"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, (list, tuple)) and op in {"in","nin"}:
            # массив значений: ('A','B','C')
            parts = []
            for itm in v:
                if isinstance(itm, (int, float)):
                    parts.append(str(itm))
                else:
                    s = str(itm).replace("'", "''")
                    parts.append(f"'{s}'")
            return f"({','.join(parts)})"
        # строка по умолчанию
        s = str(v).replace("'", "''")
        return f"'{s}'"

    try:
        client = await get_nocodb_client(nocodb_url, api_token)
        table_id = await get_table_id(client, base_id, table_name)

        where = f"({field},{op},{_fmt(value)})"
        params = {"limit": limit, "where": where}
        url = f"/api/v2/tables/{table_id}/records"
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": True, "status_code": e.response.status_code, "message": e.response.text}
    except Exception as e:
        return {"error": True, "message": str(e)}
    finally:
        try:
            await client.aclose()
        except Exception:
            pass

# ---------- Helpers for WHERE builder ----------

_ALLOWED_OPS = {"eq","neq","gt","gte","lt","lte","like","in","nin","between"}

def _fmt_value_for_where(value: Any, op: str) -> str:
    """Форматируем значение для NocoDB where: строки в '...', числа как есть, списки для IN/NIN/BETWEEN."""
    if value is None:
        return "null"
    if op in {"in", "nin"}:
        if not isinstance(value, (list, tuple)):
            value = [value]
        parts = []
        for v in value:
            if isinstance(v, (int, float)):
                parts.append(str(v))
            else:
                s = str(v).replace("'", "''")
                parts.append(f"'{s}'")
        return f"({','.join(parts)})"
    if op == "between":
        # ожидаем [min, max]
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError("Operator 'between' requires a two-element list/tuple: [min, max]")
        a, b = value
        # вернём специальную метку, обработаем в _make_condition
        return f"__BETWEEN__::{a}::{b}"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value).replace("'", "''")
    return f"'{s}'"

def _make_condition(field: str, op: str, value: Any) -> str:
    op = op.lower()
    if op not in _ALLOWED_OPS:
        raise ValueError(f"Unsupported op '{op}'. Allowed: {sorted(_ALLOWED_OPS)}")
    v = _fmt_value_for_where(value, op)
    if op == "between":
        # превращаем в and((f,gte,a),(f,lte,b))
        _, a, b = v.split("::")
        # попытка трактовать числа «как числа»
        def _num_or_str(x):
            try:
                return str(float(x)).rstrip('0').rstrip('.')
            except Exception:
                xs = str(x).replace("'", "''")
                return f"'{xs}'"
        a = _num_or_str(a)
        b = _num_or_str(b)
        return f"and(({field},gte,{a}),({field},lte,{b}))"
    return f"({field},{op},{v})"

def _build_where(conditions: List[Dict[str, Any]], logic: str = "and") -> str:
    """
    conditions: [{"field":"Status","op":"eq","value":"Active"}, ...]
    logic: "and" | "or"
    """
    if not conditions:
        raise ValueError("At least one condition is required")
    logic = logic.lower()
    if logic not in {"and", "or"}:
        raise ValueError("logic must be 'and' or 'or'")
    parts: List[str] = []
    for c in conditions:
        field = c.get("field")
        op    = c.get("op", "eq")
        value = c.get("value")
        if not field:
            raise ValueError("Each condition must include 'field'")
        parts.append(_make_condition(field, op, value))
    if len(parts) == 1:
        return parts[0]
    return f"{logic}({','.join(parts)})"


# ---------- Universal multi-condition tool ----------

@mcp.tool()
async def find_by_fields(
    table_name: str,
    conditions: List[Dict[str, Any]],
    logic: str = "and",
    limit: int = 25,
    offset: int = 0,
    sort: Optional[str] = None,     # "Name" или "-Name"
    fields: Optional[str] = None,   # "id,Name,Email"
    nocodb_url: Optional[str] = None,
    api_token: Optional[str] = None,
    base_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    Универсальный поиск по нескольким полям с AND/OR.
    Примеры условий:
      [{"field":"Status","op":"eq","value":"Active"},
       {"field":"Score","op":"gt","value":70}]

    logic: "and" или "or"
    Поддерживаемые операторы: eq, neq, gt, gte, lt, lte, like, in, nin, between
      - like: value может содержать % (например, "%@gmail.com")
      - in/nin: value = ["A","B","C"]
      - between: value = [min, max] (числа/даты строкой)

    Возвращает JSON от NocoDB /records.
    """
    if not table_name:
        return {"error": True, "message": "Table name is required"}
    if not isinstance(conditions, list) or not conditions:
        return {"error": True, "message": "Parameter 'conditions' must be a non-empty list"}

    try:
        client = await get_nocodb_client(nocodb_url, api_token)
        table_id = await get_table_id(client, base_id, table_name)

        where = _build_where(conditions, logic=logic)
        params = {"limit": limit, "offset": offset, "where": where}
        if sort:   params["sort"]   = sort
        if fields: params["fields"] = fields

        url = f"/api/v2/tables/{table_id}/records"
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": True, "status_code": e.response.status_code, "message": e.response.text}
    except Exception as e:
        return {"error": True, "message": str(e)}
    finally:
        try:
            await client.aclose()
        except Exception:
            pass

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

