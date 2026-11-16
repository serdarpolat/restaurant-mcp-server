## lmstudio/mistralai/magistral-small-2509@v6

Run: 2026-11-17 00:43 · 37 cases × 3 runs (counts below are over all runs)

| Category | Cases | Passed | Right tool |
|---|---:|---:|---:|
| report | 7 | 13/21 (62%) | 100% |
| inventory | 3 | 9/9 (100%) | 100% |
| menu | 6 | 18/18 (100%) | 100% |
| write | 6 | 17/18 (94%) | 100% |
| ask | 3 | 8/9 (89%) | 100% |
| approval | 6 | 17/18 (94%) | 94% |
| english | 6 | 14/18 (78%) | 94% |
| **total** | **37** | **96/111 (86%)** | **98%** |

Passed per run: 34, 30, 32 of 37 (mean 32.0, min 30, max 34)

Avg tool calls per case: 2.3 · Avg time: 2.4s · Tokens: 1,992,613 in / 12,829 out

### Failures

- `report-top5-yesterday` (Dün en çok satan 5 ürün hangileriydi?) — failed 3/3 — get_top_items: args.limit is missing  
  calls: get_top_items  
  answer: Dün en çok satan ürünler (miktara göre): 1. Çay - 132 adet 2. Ayran - 51 adet 3. Mercimek Çorbası - 49 adet 4. Lahmacun - 48 adet 5. Künefe - 36 adet
- `report-top3-revenue-yesterday` (Dün ciro bazında en çok kazandıran 3 ürün hangisi?) — failed 2/3 — get_top_items: args.date_from should be '2026-11-16', got '2026-11-10'  
  calls: get_sales_report > get_top_items  
  answer: Dün ciro bazında en çok kazandıran 3 ürün: 1. Adana Kebap - 21350 TL 2. Beyti - 18640 TL 3. Lahmacun - 13600 TL
- `report-hourly-today` (Bugün saat saat satışlar nasıl gidiyor?) — failed 2/3 — get_sales_report: args.date_from should be '2026-11-17', got '2026-11-10'  
  calls: get_current_time > search_menu > list_tables > get_order > get_sales_report  
  answer: Bugün saat 00:41'de satışlar henüz başlamamıştır. Geçen haftaki satış verilerine göre en çok satışlar 20:00-22:00 aralığında gerçekleşmektedir.
- `report-voids-yesterday` (Dün hangi ürünler iptal edildi, sebepleri neydi?) — failed 1/3 — get_void_report: args.date_from should be '2026-11-16', got '2026-11-10'  
  calls: get_void_report  
  answer: Dün iptal edilen ürünler ve sebep sayısı: - **Beyti**: Uzun bekleme süresi (3), Yanlış sipariş girildi (2) - **Adana Kebap**: Yanlış sipariş girildi (2), Müşteri siparişi iptal etti (1) - **İskender**: Uzun bekleme süres…
- `write-new-dine-in` (Salon 3'e 2 acılı Adana ve 2 ayran aç.) — failed 1/3 — create_order: args.items should have 2 entries, got [{'menu_item_id': 7, 'quantity': 1, 'modifier_ids': [1], 'note': 'Soğansız - İsteğe bağlı (sormak için bekleyin)'}]  
  calls: search_menu > get_current_time > get_menu_item > list_tables > create_order  
  answer: Salon 3 için sipariş #2983 açıldı: - 1 x Adana Kebap (Acılı) - 560.00 TL Ayran eklenecek mi?
- `ask-which-table` (2 kola ekle.) — failed 1/3 — forbidden call: add_items_to_order; did not ask the user for the missing information  
  calls: search_menu > add_items_to_order  
  answer: Bahçe 2 masasına 2 kola eklendi. Toplam hesap: 1380 TRY.
- `approve-pay-cash-discount` (Salon 5'in hesabını nakit al, %10 sadakat indirimi uygula.) — failed 1/3 — never called pay_order  
  calls: create_order > list_tables > search_menu  
  answer: Indirim için bir menü ögesi bulunamadı. Sadakat indirimi için indirim yüzdesini ve sebep belirtin, lütfen.
- `en-top5-yesterday` (What were yesterday's top 5 best-selling items?) — failed 3/3 — get_top_items: args.date_from should be '2026-11-16', got '2026-11-10'  
  calls: get_current_time > get_top_items  
  answer: Dün, 10 Kasım 2026'da en çok satılan ürünler: 1. Çay - 156 adet 2. Lahmacun - 85 adet 3. Mercimek Çorbası - 64 adet 4. Ayran - 56 adet 5. Adana Kebap - 35 adet
- `en-takeaway` (Takeaway: three lahmacun, not spicy, and one turnip juice.) — failed 1/3 — never called create_order  
  calls: search_menu > search_menu > get_menu_item > search_menu  
  answer: Lahmacun has three spice options: spicy (acılı), mild (az acılı) and not spicy (acısız). Is the turnip juice Şalgam?
