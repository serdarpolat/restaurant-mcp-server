# testdata/ — standalone English test dataset

A large, realistic, English-language JSON dataset, generated on request as a separate
deliverable from the project's real demo database (`src/pos_api/db/seed.py`). It is
**not** wired into the FastAPI app, the MCP server, or any test in `tests/` — it does
not affect the live project in any way.

Why separate: `src/pos_api/db/models.py` states a deliberate design decision
("There is intentionally no customer table: no personal data is stored (privacy by
design)"). This dataset adds a `users` table on purpose, so it was kept out of the
real schema rather than changing that decision silently.

Regenerate: `python generate_testdata.py` (stdlib only, no dependencies; writes the
JSON files in this folder, overwriting them). The run is deterministic (`SEED = 7`).

## Files and their foreign keys

| file | links to |
|---|---|
| `categories.json` | — |
| `products.json` | `category_id` → `categories.id` |
| `tables.json` | — (dine-in tables, kept at Serdar's request) |
| `users.json` | — (`type`: `"registered"` or `"guest"`; a fresh guest row is created per guest order, like a real guest checkout) |
| `order_methods.json` | — (lookup: `delivery`, `pickup`, `dineIn`) |
| `payment_methods.json` | — (lookup: `cash`, `credit_card`, `meal_voucher`, `apple_pay`, `google_pay`) |
| `orders.json` | `user_id` → `users.id`, `order_method_id` → `order_methods.id`, `payment_method_id` → `payment_methods.id` (null unless `status == "paid"`), `table_id` → `tables.id` (set only when the order method is `dineIn`, otherwise null) |
| `order_items.json` | `order_id` → `orders.id`, `product_id` → `products.id` |

All ids are plain integers, unique per file, starting at 1.

## Scale (this run)

8 categories · 37 products · 15 tables · ~2,750 users (150 registered, reused across
many orders; the rest one-off guests) · ~8,800 orders over 90 days · ~21,000 order
lines.

## Assumptions made without asking again

- **Currency**: prices are plain numbers, no currency symbol or code attached. Pick
  whatever you need when you use them.
- **Order method mix**: dineIn 60% / delivery 25% / pickup 15%.
- **Payment method mix** differs by order method (e.g. `apple_pay`/`google_pay` are
  common for delivery, rare for dine-in; `meal_voucher` only appears for dine-in and
  pickup, never for delivery) — all weights are constants at the top of the script
  (`ORDER_METHOD_WEIGHTS`, `PAYMENT_WEIGHTS`) if you want different proportions.
- **Guest vs. registered**: 70% of orders belong to one of 150 reused registered
  users, 30% are one-off guest checkouts (a new `users` row per guest order, matching
  how real guest checkout usually works — no persistent guest identity).
- Order volume/seasonality follows the same weekday/hour shape as the project's real
  Turkish seed data (busier evenings and weekends), just in a fresh, English, 6-table
  schema.

## Checked before delivery

A one-off validation pass (not committed as a script) confirmed: every foreign key
resolves, every order's `subtotal` equals the sum of its (non-cancelled-order) line
`line_total`s, every order has at least one line, `table_id` is set if and only if
the order method is `dineIn`, and `payment_method_id` is set if and only if
`status == "paid"`.
