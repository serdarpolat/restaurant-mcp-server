## lmstudio/mistralai/magistral-small-2509@v5

Run: 2026-11-17 00:27 · 37 cases × 3 runs (counts below are over all runs)

| Category | Cases | Passed | Right tool |
|---|---:|---:|---:|
| report | 7 | 13/21 (62%) | 100% |
| inventory | 3 | 9/9 (100%) | 100% |
| menu | 6 | 16/18 (89%) | 94% |
| write | 6 | 17/18 (94%) | 100% |
| ask | 3 | 8/9 (89%) | 100% |
| approval | 6 | 18/18 (100%) | 100% |
| english | 6 | 16/18 (89%) | 94% |
| **total** | **37** | **97/111 (87%)** | **98%** |

Passed per run: 31, 33, 33 of 37 (mean 32.3, min 31, max 33)

Avg tool calls per case: 3.1 · Avg time: 3.0s · Tokens: 2,657,008 in / 14,999 out

### Failures

- `report-top5-yesterday` (Dün en çok satan 5 ürün hangileriydi?) — failed 3/3 — get_top_items failed: Error executing tool get_top_items: 2023-11-16 is more than a year ago; today is 2026-11-17. Did you mean 2026-11-16?  
  calls: get_current_time > get_top_items > get_current_time > get_top_items  
  answer: Dün en çok satan 5 ürün: 1. Çay - 132 adet 2. Ayran - 51 adet 3. Mercimek Çorbası - 49 adet 4. Lahmacun - 48 adet 5. Künefe - 36 adet
- `report-top3-revenue-yesterday` (Dün ciro bazında en çok kazandıran 3 ürün hangisi?) — failed 3/3 — get_top_items failed: Error executing tool get_top_items: 2024-11-16 is more than a year ago; today is 2026-11-17. Did you mean 2026-11-16?  
  calls: get_current_time > get_top_items > get_current_time > get_top_items  
  answer: Dün (16 Kasım 2026) ciro bazında en çok kazandıran 3 ürün: 1. Beyti - 197 TL 2. Adana Kebap - 136 TL 3. İskender - 114 TL
- `report-hourly-today` (Bugün saat saat satışlar nasıl gidiyor?) — failed 1/3 — get_sales_report: args.group_by should be 'hour', got 'day'  
  calls: get_current_time > search_menu > get_sales_report  
  answer: Bugün (2026-11-17) saat 00:21'de satışlar henüz başlamamıştır. Gün içi satışlar için lütfen daha sonra kontrol ediniz.
- `report-voids-yesterday` (Dün hangi ürünler iptal edildi, sebepleri neydi?) — failed 1/3 — get_void_report failed: Error executing tool get_void_report: 2024-11-16 is more than a year ago; today is 2026-11-17. Did you mean 2026-11-16?  
  calls: get_current_time > get_void_report > get_void_report  
  answer: Dün iptal edilen ürün yoktu.
- `floor-bill-total` (Teras 2'nin hesabı ne kadar tuttu?) — failed 2/3 — get_order failed: Error executing tool get_order: POS API error 404: Order #4711 not found.  
  calls: list_tables > get_order  
  answer: Teras 2 masada bir açık fatura yok. Hesap toplamı 0 TL'dir. Hesabı açmak ister misiniz?
- `write-new-dine-in` (Salon 3'e 2 acılı Adana ve 2 ayran aç.) — failed 1/3 — create_order: args.items should have 2 entries, got [{'menu_item_id': 7, 'quantity': 1, 'modifier_ids': [1], 'note': ''}, {'menu_item_id': 7, 'quantity': 1, 'modifier_ids': [1], 'note': ''}, {'menu_item_id': 30, 'quantity': 1, 'modifier_ids': [], 'note': ''}, {'menu_item_id': 30, 'quantity': 1, 'modifier_ids': [], 'note': ''}]  
  calls: get_current_time > list_tables > search_menu > search_menu > get_menu_item > get_menu_item > create_order  
  answer: Sipariş oluşturuldu: 2 Adana Kebap (Acılı), 2 Ayran. Toplam: 1.220₺ (sipariş #2983).
- `ask-spice-beyti` (Salon 6'ya bir Beyti aç.) — failed 1/3 — forbidden call: create_order; did not ask the user for the missing information  
  calls: list_tables > search_menu > get_menu_item > create_order  
  answer: Salon 6 masasına bir Beyti (Acılı) siparişi açıldı. Sipariş numarası: #2983, toplam tutar 640 TL.
- `en-takeaway` (Takeaway: three lahmacun, not spicy, and one turnip juice.) — failed 2/3 — create_order: args.items should have 2 entries, got [{'menu_item_id': 20, 'quantity': 1, 'modifier_ids': [3], 'note': ''}, {'menu_item_id': 20, 'quantity': 1, 'modifier_ids': [3], 'note': ''}, {'menu_item_id': 20, 'quantity': 1, 'modifier_ids': [3], 'note': ''}, {'menu_item_id': 33, 'quantity': 1, 'modifier_ids': [], 'note': ''}]  
  calls: search_menu > search_menu > get_menu_item > search_menu > create_order  
  answer: The takeaway order #2983 is open: three not spicy lahmacun (480 TRY) and one turnip juice (şalgam, 60 TRY), total 540 TRY.
