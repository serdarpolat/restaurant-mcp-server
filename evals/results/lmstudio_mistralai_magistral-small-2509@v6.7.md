## lmstudio/mistralai/magistral-small-2509@v6.7

Run: 2026-11-20 00:30 · 40 cases × 3 runs (counts below are over all runs)

| Category | Cases | Passed | Right tool | Right language | Answer = saved |
|---|---:|---:|---:|---:|---:|
| report | 7 | 19/21 (90%) | 100% | 20/21 | - |
| inventory | 3 | 8/9 (89%) | 100% | 8/9 | - |
| menu | 6 | 18/18 (100%) | 100% | 16/16 | - |
| write | 6 | 18/18 (100%) | 100% | 17/17 | 12/12 |
| ask | 3 | 9/9 (100%) | 100% | 9/9 | - |
| approval | 6 | 18/18 (100%) | 100% | 16/16 | - |
| english | 9 | 25/27 (93%) | 100% | 27/27 | 9/9 |
| **total** | **40** | **115/120 (96%)** | **100%** | **113/115** | **21/21** |

Right language: answers in the request's language, of those whose language is clear (very short answers such as "İskender 620 TL." are not counted). Answer = saved: of the answers that state quantities of an order the agent placed, those whose quantities match what the server saved.

Passed per run: 39, 38, 38 of 40 (mean 38.3, min 38, max 39)

Avg tool calls per case: 2.0 · Avg time: 3.1s · Tokens: 2,889,106 in / 17,398 out

### Failures

- `report-z-today` (Bugünün Z raporunu çıkar.) — failed 1/3 — answered in English to a Turkish request  
  calls: get_daily_summary  
  answer: Today's Z report: - Date: November 20, 2026 - Orders paid: 0 - Open orders: 3 - Cancelled orders: 0 - Gross sales: ₺0.00 - Discounts: ₺0.00 - Net sales: ₺0.00 - Average ticket: ₺0.00 Would you like to see details for ope…
- `report-top5-yesterday` (Dün en çok satan 5 ürün hangileriydi?) — failed 1/3 — get_top_items: args.limit is missing  
  calls: get_top_items  
  answer: Dün en çok satan 5 ürün şunlar: Çay (156), Lahmacun (85), Ayran (63), Mercimek Çorbası (56) ve Ezogelin Çorbası (35).
- `inventory-low-stock` (Stokta azalan malzemeler neler?) — failed 1/3 — answered in English to a Turkish request  
  calls: get_inventory > get_current_time  
  answer: The following items are below reorder level as of Friday, November 20: - Beef mince (kg): 23.43 (uses 32.55 per day) - Lavash bread (each): 172 (uses 218.71 per day) - Eggplant (kg): 5.52 (uses 3.39 per day) - Turkish co…
- `en-top5-yesterday` (What were yesterday's top 5 best-selling items?) — failed 2/3 — get_top_items: args.limit is missing  
  calls: get_current_time > get_top_items  
  answer: The top 5 best-selling items yesterday were: 1. **Lahmacun** - 85 pieces 2. **Beyti** - 29 pieces 3. **Adana Kebap** - 22 pieces 4. **Tavuk Şiş** - 23 pieces 5. **Künefe** - 32 pieces
