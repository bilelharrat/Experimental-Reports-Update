"""Minimal MCP (Model Context Protocol) stdio server exposing the firm's memory as tools.

Speaks JSON-RPC 2.0 over newline-delimited stdio — the transport Claude Desktop and
Claude Code use for local servers — with no third-party dependency. Read-only by design.
Run: `uv run python scripts/bsh_mcp.py`; see docs/mcp-connector.md.
"""
from __future__ import annotations

import json
import sys
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "bsh-research-center", "version": "1.0.0"}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "firm_search",
        "description": "Search everything the firm has written: memos, decisions, reference calls, founder updates, transcripts, comments and chat.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "kinds": {"type": "array", "items": {"type": "string"}}, "company_id": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]},
    },
    {
        "name": "list_companies",
        "description": "List companies on the desk with id, name, ticker and status.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
    },
    {
        "name": "company_profile",
        "description": "Unified public + private profile for one company: quote, position, KPIs, thesis fit, pipeline stage, latest decision, counts.",
        "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string"}}, "required": ["company_id"]},
    },
    {
        "name": "decisions",
        "description": "Decision ledger for a company (invest / pass / watch with explanations and retrospectives).",
        "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string"}}, "required": ["company_id"]},
    },
    {
        "name": "portfolio_dashboard",
        "description": "Private portfolio: positions, latest KPIs, marks, alerts and reserves.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "signal_score",
        "description": "Transparent signal score with every component's formula and basis.",
        "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string"}}, "required": ["company_id"]},
    },
    {
        "name": "transcript",
        "description": "Full text and highlights of one transcript, or list transcripts when no id is given.",
        "inputSchema": {"type": "object", "properties": {"transcript_id": {"type": "string"}, "company_id": {"type": "string"}, "query": {"type": "string"}}},
    },
    {
        "name": "reference_calls",
        "description": "Reference calls logged for a company with strengths, concerns and quotes.",
        "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string"}}, "required": ["company_id"]},
    },
]


def _call(name: str, args: dict) -> Any:
    if name == "firm_search":
        from . import firm_search

        return firm_search.search(str(args.get("query") or ""), kinds=args.get("kinds") or None, company_id=args.get("company_id") or None, limit=int(args.get("limit") or 20))
    if name == "list_companies":
        from . import storage

        q = str(args.get("query") or "").lower()
        rows = [{"id": c.get("id"), "name": c.get("name"), "ticker": c.get("ticker"), "status": c.get("status")} for c in storage.list_companies()]
        return [r for r in rows if not q or q in str(r["name"] or "").lower() or q in str(r["id"] or "").lower()]
    if name == "company_profile":
        from . import company_profile

        return company_profile.build_profile(str(args.get("company_id") or ""), include_quote=False)
    if name == "decisions":
        from . import decisions_store

        return decisions_store.list_decisions(str(args.get("company_id") or ""))
    if name == "portfolio_dashboard":
        from . import portfolio

        return portfolio.dashboard()
    if name == "signal_score":
        from . import signal_score

        return signal_score.compute(str(args.get("company_id") or ""))
    if name == "transcript":
        from . import transcripts

        if args.get("transcript_id"):
            item = transcripts.get_transcript(str(args["transcript_id"]))
            return item or {"error": "not found"}
        return transcripts.list_transcripts(company_id=args.get("company_id") or None, q=str(args.get("query") or ""))
    if name == "reference_calls":
        from . import ic_room

        return ic_room.list_reference_calls(str(args.get("company_id") or ""))
    raise KeyError(name)


def handle_message(message: dict) -> dict | None:
    """Return the JSON-RPC response for one request, or None for notifications."""
    msg_id = message.get("id")
    method = str(message.get("method") or "")
    params = message.get("params") or {}
    if method.startswith("notifications/"):
        return None

    def ok(result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def err(code: int, text: str) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": text}}

    if method == "initialize":
        return ok({"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        name = str(params.get("name") or "")
        args = params.get("arguments") or {}
        try:
            result = _call(name, args if isinstance(args, dict) else {})
        except KeyError:
            return err(-32602, f"Unknown tool: {name}")
        except Exception as exc:  # noqa: BLE001
            return ok({"content": [{"type": "text", "text": f"Tool failed: {exc}"}], "isError": True})
        return ok({"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}]})
    return err(-32601, f"Method not found: {method}")


def serve(stdin=None, stdout=None) -> None:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}) + "\n")
            stdout.flush()
            continue
        response = handle_message(message)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()
