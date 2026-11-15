## lmstudio/mistralai/magistral-small-2509@v2

Run: 2026-11-15 21:59 · 30 cases × 3 runs (counts below are over all runs)

| Category | Cases | Passed | Right tool |
|---|---:|---:|---:|
| report | 7 | 16/21 (76%) | 100% |
| inventory | 3 | 7/9 (78%) | 100% |
| menu | 6 | 16/18 (89%) | 100% |
| write | 5 | 10/15 (67%) | 87% |
| ask | 3 | 9/9 (100%) | 100% |
| approval | 6 | 17/18 (94%) | 94% |
| **total** | **30** | **75/90 (83%)** | **97%** |

Passed per run: 26, 26, 23 of 30 (mean 25.0, min 23, max 26)

Avg tool calls per case: 2.6 · Avg time: 2.6s · Tokens: 1,295,957 in / 11,946 out

### Failures

- `report-top5-yesterday` (Dün en çok satan 5 ürün hangileriydi?) — failed 1/3 — get_top_items failed: Error executing tool get_top_items: POS API error 422: [{'type': 'date_from_datetime_parsing', 'loc': ['query', 'date_from'], 'msg': 'Input should be a valid da  
  calls: get_current_time > get_top_items > get_top_items  
  answer: Dün (14 Kasım 2026) en çok satan 5 ürün: 1. Lahmacun – 115 adet 2. Beyti – 53 adet 3. Adana Kebap – 46 adet 4. Künefe – 51 adet 5. Mercimek Çorbası – 82 adet
- `report-top3-revenue-yesterday` (Dün ciro bazında en çok kazandıran 3 ürün hangisi?) — failed 1/3 — get_top_items: args.limit is missing  
  calls: get_current_time > search_menu > get_sales_report > get_top_items  
  answer: Dün (2026-11-14) ciro bazında en çok kazandıran 3 ürün şunlar: 1. Beyti - Kebaplar: 35.420 TL 2. Adana Kebap - Kebaplar: 26.760 TL 3. Lahmacun - Pide & Lahmacun: 18.400 TL
- `report-channels-7d` (Son 7 günde paket servis, masa ve kurye satışlarını karşılaştır.) — failed 1/3 — get_sales_report: args.date_from=None matches none of [{'date': -6}, {'date': -7}]  
  calls: get_sales_report > get_sales_report  
  answer: Son 7 günde, paket servis (delivery) için sipariş sayısı 33 ve gelir 49.915 TL, masa (dine_in) için sipariş sayısı 65 ve gelir 164.386 TL, kurye (takeaway) için sipariş sayısı 23 ve gelir 26.115 TL olmuştur. Toplamda, ma…
- `report-voids-yesterday` (Dün hangi ürünler iptal edildi, sebepleri neydi?) — failed 2/3 — get_void_report: args.date_from should be '2026-11-14', got '2024-11-14'  
  calls: get_current_time > get_void_report > get_current_time  
  answer: 14 Kasım 2024'te (dün) iptal edilen ürünler yok.
- `inventory-why-mince-low` (Dana kıyma neden bu kadar azaldı? Son 14 günün stok hareketlerine bak.) — failed 2/3 — get_stock_movements: args.ingredient_id should be 1, got 10  
  calls: get_current_time > get_stock_movements  
  answer: Son 14 gün içinde dana kıymanın azalmasında, 17 satış tüketime (toplam -83.1 kg) karşı 4 tedarikçi teslimatı (toplam +85.37 kg) kaydedildi. Stokta azalma, son iki hafta boyunca aralıksız satışlar ve yeterli miktarda yeni…
- `floor-order-contents` (Bahçe 2'de neler sipariş edilmiş?) — failed 1/3 — get_order: args.order_id should be 3192, got 14  
  calls: list_tables > get_order  
  answer: Bahçe 2 masasında şu sipariş verilmiş: - Adana Kebap (acılı) - 560 TL - Ayran - 2 adet, 100 TL - Yayla Çorbası - 160 TL - Künefe - 2 adet, 560 TL - Tavuk Şiş - 420 TL - Tavuk Kanat (acılı) - 400 TL - Şalgam - 60 TL Topla…
- `floor-bill-total` (Teras 2'nin hesabı ne kadar tuttu?) — failed 1/3 — get_order: args.order_id should be 3194, got 15  
  calls: list_tables > get_order  
  answer: Teras 2'nin hesabı 3.060 TL idi.
- `write-takeaway` (Paket servis: 3 acısız lahmacun ve 1 şalgam.) — failed 2/3 — never called create_order  
  calls: get_current_time > search_menu > search_menu > get_menu_item  
  answer: Lahmacun için acısız seçeneği var. Şalgam için de siz istediğiniz gibi. Paket servis için masayı mi belirtmeyi unuttunuz?
- `write-reserve-table` (Salon 1'i akşam için rezerve et.) — failed 3/3 — set_table_status failed: Error executing tool set_table_status: POS API error 404: Table #0 not found.  
  calls: set_table_status  
  answer: Hata: Salon 1 tablosu bulunamadı. Lütfen tablo adını veya numarasını kontrol edip tekrar deneyin.
- `approve-void-line` (Bahçe 2'deki ayranları sil, yanlışlıkla girilmiş.) — failed 1/3 — never called void_order_item  
  calls: list_tables > get_order  
  answer: Sipariş 17, Salon 8 masasındaki ayranları silmek istediğinize emin misiniz? (2 adet, toplam 100 TRY) Silme sebebini girin ve yemekler hazırlanmadıysa stoklara iade edilecek mi?
