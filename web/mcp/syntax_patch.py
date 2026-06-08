"""Idempotent patch mcp.py для Cursor (ТЗ §10.5, MCP-Docker-сборка-и-фиксы §2.2)."""

from __future__ import annotations

from pathlib import Path

PATCH_MARKER = "# 1c-cursor: Cursor MCP compatibility"

PATCH_BLOCK = f'''
        {PATCH_MARKER}
        elif method == "resources/list":
            return JSONResponse(content={{
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {{"resources": []}},
            }})

        elif method == "resources/templates/list":
            return JSONResponse(content={{
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {{"resourceTemplates": []}},
            }})

        elif method == "ping":
            return JSONResponse(content={{
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {{}},
            }})

        elif method in ("notifications/initialized", "notifications/cancelled"):
            return JSONResponse(content={{"status": "ok"}})
'''


def mcp_routes_path(repo_dir: Path) -> Path:
    return repo_dir / "src" / "api" / "routes" / "mcp.py"


def is_patched(mcp_py: Path) -> bool:
    if not mcp_py.is_file():
        return False
    text = mcp_py.read_text(encoding="utf-8")
    return PATCH_MARKER in text or 'elif method == "ping":' in text


def apply_mcp_patch(repo_dir: Path) -> dict[str, str]:
    """Патчит mcp.py если нужно. Возвращает status: skipped|patched|missing."""
    mcp_py = mcp_routes_path(repo_dir)
    if not mcp_py.is_file():
        return {"status": "missing", "path": str(mcp_py), "message": "Файл mcp.py не найден"}

    text = mcp_py.read_text(encoding="utf-8")
    if is_patched(mcp_py):
        return {"status": "skipped", "path": str(mcp_py), "message": "Патч уже применён"}

    anchor = 'elif method == "tools/call":'
    if anchor not in text:
        return {
            "status": "error",
            "path": str(mcp_py),
            "message": f"Якорь {anchor!r} не найден — проверьте версию репозитория",
        }

    updated = text.replace(anchor, PATCH_BLOCK + "\n        " + anchor, 1)
    mcp_py.write_text(updated, encoding="utf-8")
    return {"status": "patched", "path": str(mcp_py), "message": "Патч Cursor MCP применён"}
