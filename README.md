# Restaurant MCP Server

[![CI](https://github.com/serdarpolat/restaurant-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/serdarpolat/restaurant-mcp-server/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

> Connect AI assistants (Claude, etc.) to a realistic restaurant POS system through the
> [Model Context Protocol](https://modelcontextprotocol.io).

Ask your AI assistant things like:

- "What were our best-selling items today?"
- "Which ingredients are running low, and why is the minced meat almost gone?"
- "Add 2 Adana kebabs and 2 ayran to a free table." (it asks for the spice level)
- "Cancel that order." (it asks *you* to approve first)

## Try it in 2 minutes

Pick one. Each option creates its own demo database (90 days of realistic sales) on first
start, which takes about 15 seconds. The demo data is regenerated when it is more than a day
old, so "today" always has sales.

### Option 1: Claude Desktop, zero setup (recommended)

Needs only [uv](https://docs.astral.sh/uv/getting-started/installation/) and git. Add this to
`claude_desktop_config.json` (Windows: `%APPDATA%\Claude\`, macOS:
`~/Library/Application Support/Claude/`) and restart Claude Desktop:

```json
{
  "mcpServers": {
    "restaurant-pos": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/serdarpolat/restaurant-mcp-server",
        "restaurant-pos-mcp"
      ]
    }
  }
}
```

No API to start: in this mode the POS API runs embedded inside the MCP server process.

### Option 2: Docker

```bash
git clone https://github.com/serdarpolat/restaurant-mcp-server
cd restaurant-mcp-server
docker compose up
```

- POS API with interactive docs: http://localhost:8000/docs
- MCP server over Streamable HTTP: http://localhost:8001/mcp

### Option 3: From source

```bash
git clone https://github.com/serdarpolat/restaurant-mcp-server
cd restaurant-mcp-server
uv sync --extra dev
uv run pytest                 # 32 tests
uv run restaurant-pos-api     # http://127.0.0.1:8000/docs
uv run restaurant-pos-mcp     # MCP server over stdio
```

Without uv: `python -m venv .venv`, activate it, then `pip install -e ".[dev]"` and run the
same commands without `uv run`.

## Architecture

```
                         stdio / Streamable HTTP
Claude Desktop  ──MCP──▶  pos_mcp (MCP server)  ──HTTP──▶  pos_api (FastAPI)  ──▶  SQLite
                          20 tools, approvals             business rules, audit log
```

- `src/pos_api` — a mock restaurant POS REST API with realistic seed data.
- `src/pos_mcp` — the MCP server. It holds no business logic and never touches the database;
  it only calls the API (over HTTP when `POS_API_URL` is set, in-process otherwise).

## The MCP server

20 tools, 1 resource and 2 prompts, built with the MCP Python SDK 2.x.

| Kind | Tools |
|---|---|
| Read (13) | `get_current_time`, `search_menu`, `get_menu_item`, `list_tables`, `list_orders`, `get_order`, `get_daily_summary`, `get_sales_report`, `get_top_items`, `get_staff_performance`, `get_void_report`, `get_inventory`, `get_stock_movements` |
| Write (3) | `create_order`, `add_items_to_order`, `set_table_status` |
| Write, needs approval (4) | `void_order_item`, `cancel_order`, `pay_order`, `record_stock_purchase` |

Resource: `restaurant://menu` · Prompts: `daily_briefing`, `stock_investigation`

### Human-in-the-loop for risky actions

Cancelling, voiding, taking payment and changing stock never run on the model's say-so alone:

1. **Elicitation.** If the client supports it, the server asks the *user* to approve through
   the client's own UI, with a preview such as
   `Cancel order #9457 (Bahçe 3, 4 lines, 1,640.00 TRY). Reason: ...`. The model cannot answer
   for the user.
2. **Preview + token fallback.** Otherwise the first call changes nothing and returns the
   preview plus a short-lived token bound to the exact arguments. Only a second call with that
   token executes, so what runs is exactly what was previewed. (In this mode, asking the user
   in between relies on the model following the tool instructions; elicitation is the hard
   guarantee.)

Every write is recorded in the audit log with the actor `mcp:assistant`.

## The POS API

Run `restaurant-pos-api` and open http://127.0.0.1:8000/docs for the interactive docs.

| Area | Endpoints |
|---|---|
| Menu | `GET /menu/categories`, `GET /menu/items?search=`, `GET /menu/items/{id}` |
| Tables | `GET /tables?status=`, `GET /tables/{id}`, `PATCH /tables/{id}` |
| Orders | `GET /orders`, `GET /orders/{id}`, `POST /orders`, `POST /orders/{id}/items`, `POST /orders/{id}/items/{item_id}/void`, `POST /orders/{id}/pay`, `POST /orders/{id}/cancel` |
| Inventory | `GET /inventory/ingredients?below_reorder=`, `GET /inventory/ingredients/{id}/movements`, `POST /inventory/purchases` |
| Reports | `GET /reports/sales?group_by=day\|hour\|weekday\|channel`, `GET /reports/top-items`, `GET /reports/staff`, `GET /reports/voids`, `GET /reports/daily-summary` |
| Audit | `GET /audit-log` |

Design choices that matter when an AI agent is the client:

- **Errors that help the agent recover.** A missing required option returns the valid
  choices (`'Adana Kebap' needs 1-1 choice(s) for 'Acı Seviyesi'. Options: Acılı (id=1), ...`),
  so the agent can ask the user instead of guessing.
- **Business rules live in the API, not in the prompt.** One open order per table, no
  overselling stock, discounts need a reason, paid orders are immutable.
- **Turkish-aware search.** `iskender` finds `İskender`, `cay` finds `Çay`.
- **Audit trail.** Every write records who did it (`X-Actor` header) in the audit log.
- **Local time everywhere.** The DB stores UTC; reports group by the restaurant's local day.

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
- [x] Mock POS API
- [x] MCP server (read tools, write tools with confirmation)
- [x] Tests, CI (Linux + Windows), Docker, uv
- [ ] Evals: does the model pick the right tool?
- [ ] Demo video

## License

MIT
