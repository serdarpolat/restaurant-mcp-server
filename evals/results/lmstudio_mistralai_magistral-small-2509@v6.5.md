## lmstudio/mistralai/magistral-small-2509@v6.5

Run: 2026-11-18 18:15 · 40 cases × 3 runs (counts below are over all runs)

| Category | Cases | Passed | Right tool | Right language | Answer = saved |
|---|---:|---:|---:|---:|---:|
| report | 7 | 14/21 (67%) | 100% | 16/21 | - |
| inventory | 3 | 9/9 (100%) | 100% | 8/8 | - |
| menu | 6 | 16/18 (89%) | 100% | 11/13 | - |
| write | 6 | 17/18 (94%) | 100% | 18/18 | 12/12 |
| ask | 3 | 9/9 (100%) | 100% | 9/9 | - |
| approval | 6 | 18/18 (100%) | 100% | 18/18 | - |
| english | 9 | 24/27 (89%) | 100% | 27/27 | 7/7 |
| **total** | **40** | **107/120 (89%)** | **100%** | **107/114** | **19/19** |

Right language: answers in the request's language, of those whose language is clear (very short answers such as "İskender 620 TL." are not counted). Answer = saved: of the answers that state quantities of an order the agent placed, those whose quantities match what the server saved.

Passed per run: 36, 35, 36 of 40 (mean 35.7, min 35, max 36)

Avg tool calls per case: 1.9 · Avg time: 3.2s · Tokens: 2,573,749 in / 17,913 out

### Failures

- `report-z-today` (Bugünün Z raporunu çıkar.) — failed 1/3 — answered in English to a Turkish request  
  calls: get_daily_summary  
  answer: Here is the daily Z report for today (November 18, 2026): **Orders:** - Paid: 44 - Open: 3 - Cancelled: 1 **Sales:** - Gross sales: 100,285 TRY - Discounts: 1,398 TRY - Net sales: 98,887 TRY - Average ticket: 2,247.43 TR…
- `report-top5-yesterday` (Dün en çok satan 5 ürün hangileriydi?) — failed 1/3 — get_top_items: args.sort should be 'quantity', got 'revenue'  
  calls: get_top_items  
  answer: Dün en çok satan ürünler (gelir başına): - Beyti: 40 adet, 26,350 TRY - Adana Kebap: 33 adet, 19,230 TRY - Künefe: 33 adet, 9,240 TRY - İskender: 13 adet, 8,560 TRY - Tavuk Şiş: 17 adet, 7,890 TRY
- `report-top3-revenue-yesterday` (Dün ciro bazında en çok kazandıran 3 ürün hangisi?) — failed 1/3 — get_top_items: args.limit is missing  
  calls: get_sales_report > get_top_items  
  answer: Dün ciro bazında en çok kazandıran 3 ürün: 1. Beyti - 26,350 TRY 2. Adana Kebap - 19,230 TRY 3. Künefe - 9,240 TRY
- `report-hourly-today` (Bugün saat saat satışlar nasıl gidiyor?) — failed 2/3 — answered in English to a Turkish request  
  calls: get_sales_report  
  answer: Today's sales by hour (as of the current time): - 11:00 - 2 orders, ₺4,365 - 12:00 - 10 orders, ₺25,880 - 13:00 - 13 orders, ₺32,100 - 14:00 - 6 orders, ₺12,030 - 15:00 - 7 orders, ₺15,722 - 16:00 - 5 orders, ₺7,200 - 17…
- `report-channels-7d` (Son 7 günde paket servis, masa ve kurye satışlarını karşılaştır.) — failed 2/3 — answered in English to a Turkish request  
  calls: get_sales_report  
  answer: Here are the sales for the last 7 days (November 11 to November 18, 2026) by channel: - **Delivery (kurye):** - Orders: 151 - Revenue: ₺254,593 - Average ticket: ₺1,686.05 - **Dine-in (masa):** - Orders: 503 - Revenue: ₺…
- `menu-soups` (Çorba olarak neler var?) — failed 2/3 — answered in English to a Turkish request  
  calls: search_menu  
  answer: The following soups are available: - Mercimek Çorbası (Lentil Soup) - 150 TRY: Creamy lentil soup served with olive oil and lemon. - Ezogelin Çorbası (Ezo Gelin Soup) - 150 TRY: Traditional bulgur and mint soup. - Yayla …
- `write-new-dine-in` (Salon 3'e 2 acılı Adana ve 2 ayran aç.) — failed 1/3 — create_order failed: Error executing tool create_order: NOT SAVED. Quantities do not match the user's message: the user said 2 x Adana Kebap, but the lines add up to 1. Send the qua  
  calls: search_menu > create_order > create_order > create_order  
  answer: Açıldı: Salon 3 için sipariş #3044. - 2 x Adana Kebap (Acılı), soğansız: 2 x 560.0 = 1,120.0 TL - 2 x Ayran: 2 x 50.0 = 100.0 TL Toplam: 1,220.0 TL
- `en-top5-yesterday` (What were yesterday's top 5 best-selling items?) — failed 1/3 — get_top_items: args.sort should be 'quantity', got 'revenue'  
  calls: get_current_time > get_top_items  
  answer: Here are yesterday's top 5 best-selling items by revenue: 1. Beyti - 26,350 TRY (40 sold) 2. Adana Kebap - 19,230 TRY (33 sold) 3. Künefe - 9,240 TRY (33 sold) 4. İskender - 8,560 TRY (13 sold) 5. Tavuk Şiş - 7,890 TRY (…
- `en-takeaway` (Takeaway: three lahmacun, not spicy, and one turnip juice.) — failed 2/3 — create_order failed: Error executing tool create_order: NOT SAVED. Line 2 ('Turnip Juice'): No menu item is called 'Turnip Juice'. Use search_menu. (Answer the user in English.)  
  calls: create_order > search_menu  
  answer: Takeaway: three lahmacun, not spicy, and one turnip juice. I don’t know which drink you meant – we have “Şalgam” (turnip juice) but nothing called “Turnip Juice”. Is the order correct? - 3 x Lahmacun, not spicy - 1 x Şal…
