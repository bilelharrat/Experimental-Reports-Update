# MCP connector — firm memory in Claude Desktop / Claude Code

The research center ships a read-only [Model Context Protocol](https://modelcontextprotocol.io) server so any MCP client can query the firm's memory: memos, decisions, reference calls, founder updates, transcripts, comments, chat, portfolio and signal scores.

It runs over stdio with no extra dependencies:

```sh
uv run python scripts/bsh_mcp.py
```

## Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "bsh-research": {
      "command": "uv",
      "args": ["run", "--directory", "/ABSOLUTE/PATH/TO/bsh-research-center", "python", "scripts/bsh_mcp.py"]
    }
  }
}
```

## Claude Code

```sh
claude mcp add bsh-research -- uv run --directory /ABSOLUTE/PATH/TO/bsh-research-center python scripts/bsh_mcp.py
```

## Tools

| Tool | What it returns |
| --- | --- |
| `firm_search` | Ranked hits with excerpts across every record type |
| `list_companies` | Companies on the desk |
| `company_profile` | Unified public + private object for one company |
| `decisions` | Decision ledger with retrospectives |
| `portfolio_dashboard` | Positions, KPIs, marks, alerts, reserves |
| `signal_score` | Transparent score with formulas |
| `transcript` | One transcript with highlights, or a filtered list |
| `reference_calls` | Reference calls with strengths, concerns, quotes |

The server reads the same `data/` directory the app uses and never writes.
