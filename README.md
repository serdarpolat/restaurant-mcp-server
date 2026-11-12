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
- `src/pos_mcp` — the MCP server exposing POS capabilities as tools, resources and prompts.
  It holds no business logic and never touches the database; it only calls the API.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"
python -m pos_api.db.seed --reset   # generate 90 days of realistic data
uvicorn pos_api.main:app --reload
pytest                               # 31 tests
```

Then open http://127.0.0.1:8000/docs

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

### Use it from Claude Desktop

1. Start the POS API: `uvicorn pos_api.main:app`
2. Add the server to `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or
   `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS), using the
   Python of your virtual environment:

```json
{
  "mcpServers": {
    "restaurant-pos": {
      "command": "C:\\path\\to\\restaurant-mcp-server\\.venv\\Scripts\\python.exe",
      "args": ["-m", "pos_mcp.server"],
      "env": { "POS_API_URL": "http://127.0.0.1:8000" }
    }
  }
}
```

3. Restart Claude Desktop and try:
   - "Bugün en çok satan 5 ürün ne?"
   - "Hangi malzemeler kritik seviyede? Kıyma neden azaldı?"
   - "Boş bir masaya 2 Adana ve 2 ayran yaz." (it should ask you for the spice level)

## The POS API

Run `uvicorn pos_api.main:app --reload` and open http://127.0.0.1:8000/docs for the
interactive docs.

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
- [ ] Tests & evals
- [ ] Docker
- [ ] Demo video

## License

MIT
