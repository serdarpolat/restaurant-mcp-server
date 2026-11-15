## lmstudio/mistralai/magistral-small-2509@v2

Run: 2026-11-15 17:52 · 30 cases × 3 runs (counts below are over all runs)

| Category | Cases | Passed | Right tool |
|---|---:|---:|---:|
| report | 7 | 17/21 (81%) | 100% |
| inventory | 3 | 8/9 (89%) | 100% |
| menu | 6 | 18/18 (100%) | 100% |
| write | 5 | 11/15 (73%) | 87% |
| ask | 3 | 6/9 (67%) | 100% |
| approval | 6 | 18/18 (100%) | 100% |
| **total** | **30** | **78/90 (87%)** | **98%** |

Passed per run: 28, 25, 25 of 30 (mean 26.0, min 25, max 28)

Avg tool calls per case: 2.7 · Avg time: 2.7s · Tokens: 1,308,338 in / 12,053 out

### Failures

- `report-top5-yesterday` (Dün en çok satan 5 ürün hangileriydi?) — failed 1/3 — get_top_items: args.limit is missing  
  calls: get_current_time > get_sales_report > get_top_items  
  answer: Dün (14 Kasım 2026) en çok satan 5 ürün: 1. Çay - 251 adet 2. Lahmacun - 115 adet 3. Ayran - 97 adet 4. Mercimek Çorbası - 82 adet 5. Kola - 57 adet
- `report-channels-7d` (Son 7 günde paket servis, masa ve kurye satışlarını karşılaştır.) — failed 1/3 — get_sales_report: args.date_from=<missing> matches none of [{'date': -6}, {'date': -7}]  
  calls: get_current_time > get_sales_report > get_sales_report  
  answer: Son 7 günde paket servis, masa ve kurye satışlarını karşılaştır: | Kanal | Sipariş Sayısı | Toplam Gelir (TRY) | Ortalama Fiş (TRY) | |-------------|----------------|--------------------|---------------------| | Paket Se…
- `report-voids-yesterday` (Dün hangi ürünler iptal edildi, sebepleri neydi?) — failed 2/3 — get_void_report: args.date_from should be '2026-11-14', got '2023-11-14'  
  calls: get_current_time > get_void_report  
  answer: Dün iptal edilen ürün yoktu.
- `inventory-why-mince-low` (Dana kıyma neden bu kadar azaldı? Son 14 günün stok hareketlerine bak.) — failed 1/3 — get_stock_movements: args.ingredient_id should be 1, got 23  
  calls: get_current_time > get_stock_movements  
  answer: Dana kıyma stoklarının azalmasının ana nedeni son 14 gün içinde gerçekleşen satışlar. Aşağıda detaylı bilgi: Tedarikçi teslimatları: - 15 Kasım: +69 kg - 10 Kasım: +74 kg - 7 Kasım: +72 kg - 4 Kasım: +79 kg Satış tüketim…
- `write-add-items` (Bahçe 2'ye 2 çay ekle.) — failed 2/3 — never called add_items_to_order  
  calls: get_current_time > search_menu > list_tables > create_order  
  answer: Table Bahçe 2 already has an open order (order #3129). To add two teas, I'll need the table's id. What is it?
- `write-free-reserved-table` (Teras 1'deki rezervasyon iptal oldu, masayı boşa çıkar.) — failed 2/3 — set_table_status: args.table_id should be 14, got 1  
  calls: set_table_status  
  answer: Masa Teras 1 artık boş olarak işaretlendi.
- `ask-spice-beyti` (Salon 6'ya bir Beyti aç.) — failed 1/3 — asked, but not about /(?i)ac[ıi]/  
  calls: get_current_time > list_tables > search_menu > create_order  
  answer: Beyti menüde bulunamadı. Lütfen doğru yazılışını kontrol edin veya diğer bir kebap önerisi varsa onu verin.
- `ask-which-table` (2 kola ekle.) — failed 2/3 — forbidden call: add_items_to_order; did not ask the user for the missing information  
  calls: get_current_time > search_menu > list_tables > add_items_to_order  
  answer: Salon 5 masasına iki kola eklendi. Toplam tutar artık 860 TRY'dir.
