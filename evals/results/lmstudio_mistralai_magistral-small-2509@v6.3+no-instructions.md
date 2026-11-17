## lmstudio/mistralai/magistral-small-2509@v6.3+no-instructions

Run: 2026-11-18 02:26 · 40 cases × 3 runs (counts below are over all runs) · server instructions OFF (model sees tool descriptions and results only)

| Category | Cases | Passed | Right tool | Right language |
|---|---:|---:|---:|---:|
| report | 7 | 18/21 (86%) | 90% | 21/21 |
| inventory | 3 | 9/9 (100%) | 100% | 9/9 |
| menu | 6 | 18/18 (100%) | 100% | 16/16 |
| write | 6 | 16/18 (89%) | 100% | 18/18 |
| ask | 3 | 7/9 (78%) | 100% | 7/9 |
| approval | 6 | 15/18 (83%) | 89% | 17/18 |
| english | 9 | 15/27 (56%) | 81% | 21/27 |
| **total** | **40** | **98/120 (82%)** | **92%** | **109/118** |

Right language: answers in the request's language, of those whose language is clear (very short answers such as "İskender 620 TL." are not counted).

Passed per run: 32, 32, 34 of 40 (mean 32.7, min 32, max 34)

Avg tool calls per case: 2.1 · Avg time: 2.6s · Tokens: 2,391,055 in / 14,574 out

### Failures

- `report-hourly-today` (Bugün saat saat satışlar nasıl gidiyor?) — failed 2/3 — get_sales_report: args.group_by is missing  
  calls: get_sales_report  
  answer: Bugün (2023-10-05) saatlik satış verileri şu anda mevcut değil. Lütfen daha sonra tekrar kontrol edin.
- `report-voids-yesterday` (Dün hangi ürünler iptal edildi, sebepleri neydi?) — failed 1/3 — never called get_void_report  
  calls: get_current_time > list_orders > get_order  
  answer: Dün, Bahçe 2 masasından iptal edilen ürünler ve sebepleri: 1. Kaşarlı Köfte - Mükerrer sipariş 2. Şalgam - Müşteri siparişi iptal etti 3. Yayla Çorbası - Mükerrer sipariş 4. Fıstıklı Baklava - Mükerrer sipariş 5. Çay (5 …
- `write-new-dine-in` (Salon 3'e 2 acılı Adana ve 2 ayran aç.) — failed 2/3 — create_order: args.items[0].quantity should be 2, got 1  
  calls: create_order  
  answer: Siparişiniz alındı: - **Salon 3** için #2998 numaralı sipariş - 1 Adana Kebap (Acılı) - 560₺ - 1 Ayran - 50₺ Toplam: **610₺** Lütfen 1 kase ayran daha isteniyorsa bildirin.
- `ask-spice-beyti` (Salon 6'ya bir Beyti aç.) — failed 1/3 — asked, but not about /(?i)ac[ıi]/; answered in English to a Turkish request  
  calls: search_menu > get_menu_item  
  answer: The Beyti has options for spice level (spicy, mild or not spicy) and portion size (optional 1.5 portions). What is the spice level?
- `ask-which-table` (2 kola ekle.) — failed 1/3 — answered in English to a Turkish request  
  calls: list_tables  
  answer: I see that tables Salon 5, Bahçe 2 and Teras 2 are occupied. Which table would you like to add the colas to?
- `approve-void-line` (Bahçe 2'deki ayranları sil, yanlışlıkla girilmiş.) — failed 1/3 — void_order_item failed: Error executing tool void_order_item: NOT SAVED. Order #138 (delivery) is paid; only open orders can change. For a table's current order use list_tables.open_or  
  calls: void_order_item > list_orders > get_current_time  
  answer: Yanlışlıkla, ayranlar zaten ödendiği için silinemez. Ne yapmamı istersiniz?
- `approve-pay-cash-discount` (Salon 5'in hesabını nakit al, %10 sadakat indirimi uygula.) — failed 2/3 — never called pay_order; answered in English to a Turkish request  
  calls: get_current_time > list_tables > get_order  
  answer: The bill for Salon 5 is 700 TL. You want to apply a 10% discount. Before proceeding with the payment, please confirm: - Payment method: Cash (as you said) - Discount: 10% (70 TL) → Total: 630 TL - Reason for discount: Lo…
- `en-top5-yesterday` (What were yesterday's top 5 best-selling items?) — failed 1/3 — get_top_items: args.limit is missing  
  calls: get_current_time > get_top_items  
  answer: Yesterday's top 5 best-selling items were: 1. Beyti (40 servings) 2. Adana Kebap (33 servings) 3. Künefe (33 servings) 4. Lahmacun (44 servings) 5. Mercimek Çorbası (41 servings)
- `en-new-dine-in-mixed` (Start an order on Salon 4: two Adana kebabs, one spicy and one not spicy.) — failed 1/3 — answered in Turkish to a English request  
  calls: search_menu > list_tables > get_menu_item > create_order  
  answer: Açıldı: Salon 4 için #2998 numaralı sipariş. İçerik: - Adana Kebap (Acılı): 1 × 560,00 TL - Adana Kebap (Acısız): 1 × 560,00 TL Toplam: 1.120,00 TRY.
- `en-takeaway` (Takeaway: three lahmacun, not spicy, and one turnip juice.) — failed 3/3 — never called create_order  
  calls: search_menu > search_menu > get_menu_item > search_menu  
  answer: Do you mean turnip juice or Şalgam?
- `en-approve-cancel` (Cancel the order on Bahçe 2, the customer left.) — failed 3/3 — never called cancel_order  
  calls: list_tables > get_order  
  answer: The order at Bahçe 2 is as follows: - 2 Adana Kebap (spicy) at 560 TL each: **1120 TL** - 2 Ayran at 50 TL each: **100 TL** - Total: **1220 TL** I will now cancel this order. Please confirm if the food has already been p…
- `en-approve-void-line` (Remove the ayrans from Bahçe 2, they were entered by mistake.) — failed 2/3 — answered in Turkish to a English request  
  calls: void_order_item > list_orders > get_order > void_order_item  
  answer: İptal edildi: Bahçe masasından iki ayran silindi. Sipariş toplamı 1,120 TRY.
- `en-approve-pay-card` (Close the bill for Salon 5, paid by card.) — failed 2/3 — answered in Turkish to a English request  
  calls: list_tables > get_order > pay_order  
  answer: Ödeme tamamlandı ve masanın hesabı kapatıldı. **Hesap Özeti:** - İskender: 1 adet × 620.00 TRY = 620.00 TRY - Kola: 1 adet × 80.00 TRY = 80.00 TRY - **Toplam:** 700.00 TRY Ödeme yöntemi: Kart
