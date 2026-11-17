## lmstudio/mistralai/magistral-small-2509@v6.3

Run: 2026-11-18 02:20 · 40 cases × 3 runs (counts below are over all runs)

| Category | Cases | Passed | Right tool | Right language |
|---|---:|---:|---:|---:|
| report | 7 | 14/21 (67%) | 95% | 18/21 |
| inventory | 3 | 9/9 (100%) | 100% | 9/9 |
| menu | 6 | 17/18 (94%) | 100% | 13/14 |
| write | 6 | 16/18 (89%) | 100% | 15/17 |
| ask | 3 | 4/9 (44%) | 100% | 4/9 |
| approval | 6 | 15/18 (83%) | 100% | 16/18 |
| english | 9 | 22/27 (81%) | 100% | 25/27 |
| **total** | **40** | **97/120 (81%)** | **99%** | **100/115** |

Right language: answers in the request's language, of those whose language is clear (very short answers such as "İskender 620 TL." are not counted).

Passed per run: 34, 32, 31 of 40 (mean 32.3, min 31, max 34)

Avg tool calls per case: 2.4 · Avg time: 2.9s · Tokens: 2,653,006 in / 17,153 out

### Failures

- `report-z-today` (Bugünün Z raporunu çıkar.) — failed 2/3 — get_daily_summary: args.day should be '2026-11-18', got '2026-11-17'  
  calls: get_current_time > get_daily_summary  
  answer: Bugünün (17 Kasım) Z raporu: - Toplam ödenmiş sipariş sayısı: 84 - Açık sipariş sayısı: 0 - İptal edilen sipariş sayısı: 1 - Toplam satış (brüt): 174.195,00 TL - İndirimler: 2.830,00 TL - Net satış: 171.365,00 TL - Ortal…
- `report-top3-revenue-yesterday` (Dün ciro bazında en çok kazandıran 3 ürün hangisi?) — failed 1/3 — get_top_items: args.limit is missing  
  calls: get_top_items  
  answer: Dün ciro bazında en çok kazandıran 3 ürün şunlar: 1. Beyti (Kebaplar) - 26,350 TRY 2. Adana Kebap (Kebaplar) - 19,230 TRY 3. Künefe (Tatlılar) - 9,240 TRY
- `report-hourly-today` (Bugün saat saat satışlar nasıl gidiyor?) — failed 3/3 — never called get_sales_report; answered in English to a Turkish request  
  calls: get_current_time  
  answer: I need to know the current time and date to give you today's sales. Can you confirm that it is now Wednesday, November 18th?
- `report-channels-7d` (Son 7 günde paket servis, masa ve kurye satışlarını karşılaştır.) — failed 1/3 — answered in English to a Turkish request  
  calls: get_sales_report  
  answer: Here are the sales for last week (November 11–18): | Channel | Orders | Revenue | Avg Ticket | |---------------|--------|------------|------------| | Delivery | 139 | ₺234,548.00 | ₺1,687.40 | | Dine-in | 477 | ₺1,244,21…
- `floor-bill-total` (Teras 2'nin hesabı ne kadar tuttu?) — failed 1/3 — answered in English to a Turkish request  
  calls: get_current_time > list_tables > get_order  
  answer: The bill for table Teras 2 is 600 TRY. Items ordered: - Lahmacun (not spicy): 3 x 160 = 480 - Şalgam: 2 x 60 = 120
- `write-mixed-spice` (Salon 6'ya 2 Adana aç, biri acılı biri acısız.) — failed 2/3 — answered in English to a Turkish request  
  calls: search_menu > get_menu_item > create_order  
  answer: I've opened order #2998 for table Salon 6: two Adana kebaps – one spicy, one not. Total is 1,120 TRY.
- `ask-spice-adana` (Salon 4'e 1 Adana Kebap.) — failed 3/3 — did not ask the user for the missing information; answered in English to a Turkish request  
  calls: search_menu > get_menu_item > add_items_to_order  
  answer: Please specify the spice level for Adana Kebap: - Spicy (Acılı) - Mild (Az Acılı) - Not spicy (Acısız)
- `ask-which-table` (2 kola ekle.) — failed 2/3 — answered in English to a Turkish request  
  calls: search_menu > list_tables  
  answer: Which table is this for? The available tables are: Salon: Salon 1 (2 people), Salon 2 (2), Salon 3 (4), Salon 4 (4), Salon 6 (6), Salon 7 (6), Salon 8 (8) Bahçe: Bahçe 1 (2), Bahçe 2 (occupied), Bahçe 3 (4), Bahçe 4 (4),…
- `approve-void-line` (Bahçe 2'deki ayranları sil, yanlışlıkla girilmiş.) — failed 2/3 — answered in English to a Turkish request  
  calls: get_order > void_order_item  
  answer: The ayran line has been voided from Bahçe 2's order (order #2995). The new total is 1,120.00 TRY for: - 2 x Spicy Adana Kebap at 560.00 TRY each. The ayran line shows as cancelled with the reason you specified.
- `approve-pay-cash-discount` (Salon 5'in hesabını nakit al, %10 sadakat indirimi uygula.) — failed 1/3 — pay_order failed: Error executing tool pay_order: NOT SAVED. Order #37 (Bahçe 4) is paid; only open orders can change. For a table's current order use list_tables.open_order_id.   
  calls: get_current_time > list_tables > pay_order > pay_order  
  answer: Salon 5'in hesabını nakit almak istiyor musunuz? İndirimin nedenini lütfen belirtin.
- `en-takeaway` (Takeaway: three lahmacun, not spicy, and one turnip juice.) — failed 2/3 — create_order: args.items should have 2 entries, got [{'menu_item_id': 20, 'quantity': 3, 'modifier_ids': [3], 'note': ''}]; unexpected write: add_items_to_order  
  calls: search_menu > get_menu_item > create_order > search_menu > add_items_to_order  
  answer: The takeaway order is ready: - 3 x Lahmacun (not spicy): 480 TRY - 1 x Şalgam (turnip juice): 60 TRY Total: 540 TRY.
- `en-add-tea` (Add two teas to Bahçe 2.) — failed 1/3 — add_items_to_order: args.items[0].quantity should be 2, got 1  
  calls: get_current_time > add_items_to_order  
  answer: Added to table Bahçe 2's order: - Çay: 1 x 30.00 TRY Order total: 1,250.00 TRY
- `en-approve-cancel` (Cancel the order on Bahçe 2, the customer left.) — failed 2/3 — answered in Turkish to a English request  
  calls: get_order > cancel_order  
  answer: Sipariş iptal edildi: - Sipariş: #2995 (Bahçe 2) - Durum: İptal edildi - Sebep: Müşteri vazgeçti - Toplam: 0 TL İptal edilen ürünler: 1. Adana Kebap (Acılı) - 2 adet, 1120 TL 2. Ayran - 2 adet, 100 TL
