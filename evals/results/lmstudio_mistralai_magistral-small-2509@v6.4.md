## lmstudio/mistralai/magistral-small-2509@v6.4

Run: 2026-11-18 02:45 · 40 cases × 3 runs (counts below are over all runs)

| Category | Cases | Passed | Right tool | Right language |
|---|---:|---:|---:|---:|
| report | 7 | 17/21 (81%) | 100% | 19/21 |
| inventory | 3 | 7/9 (78%) | 100% | 6/8 |
| menu | 6 | 18/18 (100%) | 100% | 14/14 |
| write | 6 | 17/18 (94%) | 100% | 16/16 |
| ask | 3 | 3/9 (33%) | 100% | 4/9 |
| approval | 6 | 17/18 (94%) | 100% | 16/17 |
| english | 9 | 25/27 (93%) | 96% | 27/27 |
| **total** | **40** | **104/120 (87%)** | **99%** | **102/112** |

Right language: answers in the request's language, of those whose language is clear (very short answers such as "İskender 620 TL." are not counted).

Passed per run: 34, 39, 31 of 40 (mean 34.7, min 31, max 39)

Avg tool calls per case: 2.4 · Avg time: 3.0s · Tokens: 2,862,345 in / 16,887 out

### Failures

- `report-top5-yesterday` (Dün en çok satan 5 ürün hangileriydi?) — failed 1/3 — get_top_items: args.sort should be 'quantity', got 'revenue'  
  calls: get_top_items  
  answer: Dün en çok satan 5 ürün şunlardı: Beyti (40 adet), Adana Kebap (33 adet), Künefe (33 adet), İskender (13 adet) ve Tavuk Şiş (17 adet).
- `report-top3-revenue-yesterday` (Dün ciro bazında en çok kazandıran 3 ürün hangisi?) — failed 1/3 — get_top_items: args.date_from is missing  
  calls: get_sales_report > get_top_items > get_sales_report > get_top_items  
  answer: Dün ciro bazında en çok kazandıran 3 ürün: 1. Beyti - 17.780 TL 2. İskender - 14.140 TL 3. Adana Kebap - 9.460 TL
- `report-hourly-today` (Bugün saat saat satışlar nasıl gidiyor?) — failed 2/3 — get_sales_report: args.group_by is missing; answered in English to a Turkish request  
  calls: get_sales_report  
  answer: Today's sales (18 November) are 0 orders and 0 TL in revenue.
- `inventory-low-stock` (Stokta azalan malzemeler neler?) — failed 2/3 — answered in English to a Turkish request  
  calls: get_inventory  
  answer: Here are the ingredients that need restocking: - Dana Kıyma: 28.12 kg (reorder level: 63.0 kg) - Lavash: 182 pieces (reorder level: 389 pieces) - Eggplant: 4.582 kg (reorder level: 7.0 kg) - Turkish Coffee: 0.484 kg (reo…
- `write-add-items` (Bahçe 2'ye 2 çay ekle.) — failed 1/3 — add_items_to_order: args.items[0].quantity should be 2, got 1  
  calls: search_menu > add_items_to_order  
  answer: 2 çay Bahçe 2 masasın siparişine eklendi. Toplam: 1.250,00 TRY.
- `ask-spice-adana` (Salon 4'e 1 Adana Kebap.) — failed 2/3 — asked, but not about /(?i)ac[ıi]/; answered in English to a Turkish request  
  calls: search_menu > list_tables > get_menu_item  
  answer: The menu has two options for Adana Kebap: spicy and mild (not spicy). For which one should I order?
- `ask-spice-beyti` (Salon 6'ya bir Beyti aç.) — failed 2/3 — answered in English to a Turkish request  
  calls: search_menu > get_menu_item  
  answer: The menu item Beyti has required options: the spice level (Acılı, Az Acılı or Acısız). For which of these would you like to order?
- `ask-which-table` (2 kola ekle.) — failed 2/3 — answered in English to a Turkish request  
  calls: list_tables  
  answer: Which table should the order be added to? (Salon 5, Bahçe 2 or Teras 2)
- `approve-void-line` (Bahçe 2'deki ayranları sil, yanlışlıkla girilmiş.) — failed 1/3 — answered in English to a Turkish request  
  calls: get_order > void_order_item  
  answer: The ayran items from table Bahçe 2 have been successfully voided. The order total is now 1,120.00 TRY for two Adana kebabs (spicy).
- `en-top5-yesterday` (What were yesterday's top 5 best-selling items?) — failed 1/3 — get_top_items: args.limit is missing  
  calls: get_current_time > get_top_items  
  answer: Here are the top 5 best-selling items from yesterday: 1. Beyti (Kebaplar) - 40 orders 2. Adana Kebap (Kebaplar) - 33 orders 3. Künefe (Tatlılar) - 33 orders 4. İskender (Kebaplar) - 13 orders 5. Tavuk Şiş (Kebaplar) - 17…
- `en-approve-void-line` (Remove the ayrans from Bahçe 2, they were entered by mistake.) — failed 1/3 — never called void_order_item  
  calls: get_order  
  answer: The order for table Bahçe 2 has two ayrans that need to be removed. Let me void them. Which reason should I use?
