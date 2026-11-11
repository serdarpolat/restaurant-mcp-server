# Restaurant MCP Server

> Connect AI assistants (Claude, etc.) to a realistic restaurant POS system through the
> [Model Context Protocol](https://modelcontextprotocol.io).

**Status:** 🚧 Work in progress

## What it does

Ask your AI assistant things like:

- "What were our best-selling items today?"
- "Which ingredients are running low?"
- "Add 2 Adana kebabs to table 5."

## Architecture

```
Claude Desktop  ──MCP──▶  pos_mcp (MCP server)  ──HTTP──▶  pos_api (mock POS, FastAPI)  ──▶  SQLite
```

- `src/pos_api` — a mock restaurant POS REST API with realistic seed data
- `src/pos_mcp` — the MCP server exposing POS capabilities as tools, resources and prompts

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"
uvicorn pos_api.main:app --reload
```

Then open http://127.0.0.1:8000/docs

## Roadmap

- [ ] Data model & seed data
- [ ] Mock POS API
- [ ] MCP server (read tools, write tools with confirmation)
- [ ] Tests & evals
- [ ] Docker
- [ ] Demo video

## License

MIT
