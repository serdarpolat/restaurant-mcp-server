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
python -m pos_api.db.seed --reset   # generate 90 days of realistic data
uvicorn pos_api.main:app --reload
```

Then open http://127.0.0.1:8000/docs

## The data

A synthetic but realistic Turkish kebab restaurant (37 menu items, 15 tables, ~9,000 orders
over 90 days). The seed data follows real-world patterns so analytical questions have
meaningful answers:

- Lunch and dinner peaks, busier Fridays and weekends, a public-holiday spike (Oct 29)
- Seasonality: cold drinks fade, soups and tea rise as summer turns to autumn
- A menu-wide price increase ~45 days ago (historical order prices are preserved)
- A rising-star menu item and a top-performing waiter
- Voided items and cancelled orders with reasons
- A full stock ledger (sales, purchases, waste) and a supplier delay leaving some
  ingredients below their reorder level

**Privacy by design:** there is no customer table; no personal data is stored.
Timestamps are timezone-aware (`RESTAURANT_TZ`, default `Europe/Istanbul`).

## Roadmap

- [x] Data model & seed data
- [ ] Mock POS API
- [ ] MCP server (read tools, write tools with confirmation)
- [ ] Tests & evals
- [ ] Docker
- [ ] Demo video

## License

MIT
