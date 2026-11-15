## lmstudio/mistralai/magistral-small-2509@baseline

Run: 2026-11-15 17:29 · 30 cases × 3 runs (counts below are over all runs)

| Category | Cases | Passed | Right tool |
|---|---:|---:|---:|
| report | 7 | 19/21 (90%) | 100% |
| inventory | 3 | 7/9 (78%) | 100% |
| menu | 6 | 16/18 (89%) | 94% |
| write | 5 | 8/15 (53%) | 53% |
| ask | 3 | 7/9 (78%) | 100% |
| approval | 6 | 9/18 (50%) | 61% |
| **total** | **30** | **66/90 (73%)** | **83%** |

Passed per run: 23, 19, 24 of 30 (mean 22.0, min 19, max 24)

Avg tool calls per case: 2.5 · Avg time: 3.0s · Tokens: 1,191,933 in / 13,314 out

### Failures

- `report-top5-yesterday` (Dün en çok satan 5 ürün hangileriydi?) — failed 1/3 — get_top_items: args.date_from is missing  
  calls: get_current_time > search_menu > get_top_items  
  answer: Dün en çok satan 5 ürün: - Çay (İçecekler): 83 adet - Lahmacun (Pide & Lahmacun): 41 adet - Ayran (İçecekler): 38 adet - Mercimek Çorbası (Çorbalar): 31 adet - Beyti (Kebaplar): 24 adet
- `report-top3-revenue-yesterday` (Dün ciro bazında en çok kazandıran 3 ürün hangisi?) — failed 1/3 — get_top_items: args.date_from is missing  
  calls: get_current_time > get_top_items  
  answer: Dün (14 Kasım 2026) ciro bazında en çok kazandıran ürünler: 1. Beyti - 15.860₺ 2. Adana Kebap - 10.580₺ 3. İskender - 7.820₺
- `inventory-why-mince-low` (Dana kıyma neden bu kadar azaldı? Son 14 günün stok hareketlerine bak.) — failed 2/3 — get_stock_movements: args.ingredient_id should be 1, got 7  
  calls: get_current_time > search_menu > get_menu_item > get_stock_movements  
  answer: Dana kıyması son 14 gün içinde en fazla "Günlük satış tüketimi" sebebiyle azaldı. Toplam satışla düşen miktar 824 kg, alımlarla artan miktar ise 1077 kg oldu. Dolayısıyla stokta azalmanın başlıca nedeni artık satışlar.
- `menu-soups` (Çorba olarak neler var?) — failed 1/3 — search_menu: args.category should be 'Çorbalar', got 'çorbalar'  
  calls: search_menu  
  answer: Çorba seçenekleri: - Mercimek Çorbası (150 TL) – Tereyağlı, limonla servis edilir. - Ezogelin Çorbası (150 TL) – Bulgurlu, naneli geleneksel çorba. - Yayla Çorbası (160 TL) – Yoğurtlu, pirinçli, naneli.
- `floor-bill-total` (Teras 2'nin hesabı ne kadar tuttu?) — failed 1/3 — never called get_order  
  calls: get_current_time > list_tables > list_orders  
  answer: Teras 2 masasındaki hesabı 600 TL tutuyor.
- `write-new-dine-in` (Salon 3'e 2 acılı Adana ve 2 ayran aç.) — failed 2/3 — never called create_order  
  calls: get_current_time > list_tables > search_menu > get_menu_item > get_menu_item  
  answer: Salon 3 masası hazır. Siparişinize başlayalım. Adana Kebap için acı seviyesini belirtin: 1. Acılı 2. Az Acılı 3. Acısız Ayran için boyut seçin: 1. Standart (50 TL) 2. Büyük Boy (70 TL) Lütfen tercihlerinizi belirtin.
- `write-takeaway` (Paket servis: 3 acısız lahmacun ve 1 şalgam.) — failed 3/3 — never called create_order  
  calls: search_menu > get_menu_item > get_menu_item  
  answer: Lahmacun için acı seviyesi seçimi gerekli. Hangi acılıkta lahmacun istersiniz? 1. Acılı 2. Az Acılı 3. Acısız
- `write-add-items` (Bahçe 2'ye 2 çay ekle.) — failed 2/3 — never called add_items_to_order  
  calls: get_current_time > list_tables  
  answer: Table Bahçe 2 not found.
- `ask-spice-beyti` (Salon 6'ya bir Beyti aç.) — failed 1/3 — asked, but not about /(?i)ac[ıi]/  
  calls: get_current_time > list_tables  
  answer: Salon 6 serbest. Beyti için hangi seçeneğini istiyorsunuz? (Lüfer, Palamut, Midye, midye ve et, et)
- `ask-which-table` (2 kola ekle.) — failed 1/3 — asked, but not about /(?i)masa|paket|sipariş|table/  
  calls: get_current_time > search_menu  
  answer: I'm adding 2 cola (330ml) to the current order. Is that correct?
- `approve-cancel` (Bahçe 2'deki siparişi iptal et, müşteri gitti.) — failed 3/3 — never called cancel_order  
  calls: list_tables > get_order  
  answer: Bu siparişi iptal etmek ücretli olacak. Müşteri gitti, yemek hazırlanmış mı? (Evet/Hayır) Eğer evet, malzemeleri iptal edilmemesi gerekiyor.
- `approve-void-line` (Bahçe 2'deki ayranları sil, yanlışlıkla girilmiş.) — failed 2/3 — never called void_order_item  
  calls: get_current_time > list_tables > get_order  
  answer: The order at table Bahçe 2 has the following items: - Adana Kebap (Acılı) x2: 560 TL each - Ayran x2: 50 TL each Shall I cancel the 2 Ayarans? If so, was this a mistake or because the customer changed their mind? Also, d…
- `approve-pay-cash-discount` (Salon 5'in hesabını nakit al, %10 sadakat indirimi uygula.) — failed 1/3 — pay_order failed: Error executing tool pay_order: POS API error 409: Order #43 is paid; only open orders can change.  
  calls: get_current_time > list_tables > pay_order  
  answer: The table list shows that Salon 5 has an open order (ID 3125), so I'll use that to pay. I need the discount reason before proceeding, as it’s required for discounts. What was the reason for this loyalty discount?
- `approve-stock-purchase` (Tedarikçiden 10 kg dana kıyma geldi, stoğa işle.) — failed 3/3 — record_stock_purchase failed: Error executing tool record_stock_purchase: POS API error 404: Ingredient #34 not found.  
  calls: get_current_time > record_stock_purchase  
  answer: Dana kıymasını stoğa eklemek için id'ye ihtiyacım var. Adı nedir? (Örnek: "dana et", "kıyma" etc)
