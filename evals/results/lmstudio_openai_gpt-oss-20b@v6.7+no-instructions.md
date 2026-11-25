## lmstudio/openai/gpt-oss-20b@v6.7+no-instructions

Run: 2026-11-26 00:52 · 40 cases × 3 runs (counts below are over all runs) · server instructions OFF (model sees tool descriptions and results only)

| Category | Cases | Passed | Right tool | Right language | Answer = saved |
|---|---:|---:|---:|---:|---:|
| report | 7 | 18/21 (86%) | 100% | 21/21 | - |
| inventory | 3 | 8/9 (89%) | 89% | 8/8 | - |
| menu | 6 | 18/18 (100%) | 100% | 16/16 | - |
| write | 6 | 9/18 (50%) | 72% | 18/18 | 3/3 |
| ask | 3 | 7/9 (78%) | 100% | 9/9 | - |
| approval | 6 | 14/18 (78%) | 78% | 17/18 | - |
| english | 9 | 16/27 (59%) | 89% | 18/24 | 6/6 |
| **total** | **40** | **90/120 (75%)** | **89%** | **107/114** | **9/9** |

Right language: answers in the request's language, of those whose language is clear (very short answers such as "İskender 620 TL." are not counted). Answer = saved: of the answers that state quantities of an order the agent placed, those whose quantities match what the server saved.

Passed per run: 26, 33, 31 of 40 (mean 30.0, min 26, max 33)

Avg tool calls per case: 1.5 · Avg time: 2.8s · Tokens: 1,287,015 in / 28,197 out

### Failures

- `report-channels-7d` (Son 7 günde paket servis, masa ve kurye satışlarını karşılaştır.) — failed 1/3 — get_sales_report: args.group_by should be 'channel', got 'day'  
  calls: get_sales_report  
  answer: Üzgünüm, şu anda sadece tarih bazlı satış raporu alabiliyorum; kanal (paket servis, masa ve kurye) bazında ayrım yapacak bir araç bulunmuyor. Paket servis, masa ve kurye satışlarını karşılaştırmak için bu kanallara göre …
- `report-voids-yesterday` (Dün hangi ürünler iptal edildi, sebepleri neydi?) — failed 2/3 — get_void_report: args.date_from should be '2026-11-25', got '2026-11-26'  
  calls: get_void_report  
  answer: Bugün iptal edilen ürün bulunmadı. Dün tarihli bir rapor görmek istiyor musunuz?
- `inventory-why-mince-low` (Dana kıyma neden bu kadar azaldı? Son 14 günün stok hareketlerine bak.) — failed 1/3 — never called get_stock_movements  
  calls: get_inventory  
  answer: -
- `write-new-dine-in` (Salon 3'e 2 acılı Adana ve 2 ayran aç.) — failed 3/3 — create_order failed: Error executing tool create_order: NOT SAVED. Line 1 ('Acılı Adana'): No menu item is called 'Acılı Adana'. Use search_menu. (Answer the user in Turkish.)  
  calls: create_order  
  answer: Üzgünüm, “Acılı Adana” menüde bulunamadı. Lütfen hangi adıyla listelendiğini ya da benzer bir isim belirtir misiniz?
- `write-takeaway` (Paket servis: 3 acısız lahmacun ve 1 şalgam.) — failed 2/3 — never called create_order  
  calls: no tool calls  
  answer: **Lahmacun için baharat seviyesini belirtmeniz gerekiyor.** (örn.: “acısız”, “az acı”, “orta acı” vb.) Bu bilgiyle siparişinizi oluşturabilirim.
- `write-free-reserved-table` (Teras 1'deki rezervasyon iptal oldu, masayı boşa çıkar.) — failed 2/3 — never called set_table_status  
  calls: list_tables  
  answer: Maalesef “Teras 1” tablosu sistemde bulunamadı. Lütfen hangi tablo numarasını boşaltmak istediğinizi belirtir misiniz?
- `write-mixed-spice` (Salon 6'ya 2 Adana aç, biri acılı biri acısız.) — failed 2/3 — never called add_items_to_order or create_order  
  calls: search_menu  
  answer: **Adana Kebap** seçeneğinde bahsedilen “acılı” ve “acıksız” için **baharat seviyesi** opsiyonu var. Salon 6’ya şu iki satırı eklemek istiyorum: 1. 1 adet Adana Kebap – acılı 2. 1 adet Adana Kebap – acısız Bu istek doğru …
- `ask-spice-adana` (Salon 4'e 1 Adana Kebap.) — failed 2/3 — asked, but not about /(?i)ac[ıi]/  
  calls: no tool calls  
  answer: Adana Kebabı için hangi baharat seviyesini tercih edersiniz (az, orta, çok)?
- `approve-cancel` (Bahçe 2'deki siparişi iptal et, müşteri gitti.) — failed 1/3 — never called cancel_order  
  calls: get_order  
  answer: Siparişi iptal etmek için lütfen iptale sebebini belirtin: örneğin “Müşteri vazgeçti” veya “Kasa hatası”.
- `approve-cancel-restock` (Teras 2'nin siparişini iptal et; mutfağa gitmeden vazgeçtiler, malzemeleri stoğa geri ekle.) — failed 1/3 — never called cancel_order  
  calls: list_tables  
  answer: Üzgünüm, “Teras 2” adında bir masa şu anda sistemde görünmüyor. Lütfen doğru masanın adını veya numarasını belirtir misiniz?
- `approve-void-line` (Bahçe 2'deki ayranları sil, yanlışlıkla girilmiş.) — failed 1/3 — never called void_order_item; answered in English to a Turkish request  
  calls: get_order  
  answer: Sure! I’ll void the two “Ayran” items for **Bahçe 2**. Would you like me to proceed?
- `approve-pay-card` (Salon 5'in hesabını kredi kartıyla kapat.) — failed 1/3 — never called pay_order  
  calls: list_tables  
  answer: Salon 5 için bir sipariş bulunamadı. Lütfen kapatmak istediğiniz tablonun açık bir hesabının var mı, yoksa başka bir tabloda mı işlem yapmak istiyorsunuz?
- `en-top5-yesterday` (What were yesterday's top 5 best-selling items?) — failed 2/3 — answered in Turkish to a English request  
  calls: get_top_items  
  answer: **Yarınki en çok satan 5 ürün (2026‑11‑25):** | Sıra | Ürün | Kategori | Satış Miktarı | Gelir (TL) | |------|---------------|-------------------|--------------|------------| | 1 | Çay | İçecekler | 158 | 4 740,00 | | 2 …
- `en-new-dine-in-mixed` (Start an order on Salon 4: two Adana kebabs, one spicy and one not spicy.) — failed 1/3 — create_order failed: Error executing tool create_order: NOT SAVED. Nothing was ordered: the user has to decide. Do not choose for them and do not call again until they answer. Ask t  
  calls: search_menu > get_menu_item > create_order  
  answer: **Spice level for the 2 Adana Kebap:** Acılı (spicy), Az Acılı (mild) or Acısız (not spicy)? If they differ, please specify which is which, e.g. “one Acılı, one Acısız”.
- `en-takeaway` (Takeaway: three lahmacun, not spicy, and one turnip juice.) — failed 1/3 — never called create_order  
  calls: search_menu > get_menu_item > search_menu  
  answer: I couldn’t find a “turp suyu” (turnip juice) on the menu. Could you please let me know the exact name of that drink, or if it’s a special/seasonal item? Once I have the correct name, I’ll add the three non‑spicy lahmacun…
- `en-add-tea` (Add two teas to Bahçe 2.) — failed 1/3 — add_items_to_order failed: Error executing tool add_items_to_order: NOT SAVED. Quantity: the user said 2 x Çay, but the lines add up to 4. Call again with exactly these items (the rest un  
  calls: search_menu > add_items_to_order  
  answer: It looks like you requested “Add two teas to Bahçe 2,” but the system interpreted that as four tea items (two separate lines of two each). Could you confirm whether you want a total of 2 teas or 4? Once I have your confi…
- `en-ask-spice` (Open one Adana kebab on Salon 4.) — failed 3/3 — answered in Turkish to a English request  
  calls: search_menu > get_menu_item  
  answer: Adana Kebap için acılık seviyesini belirtmeniz gerekiyor. Lütfen aşağıdaki seçeneklerden birini seçiniz: - **Acılı** - **Az Acılı** - **Acısız** Hangi seçeneği tercih edersiniz?
- `en-approve-cancel` (Cancel the order on Bahçe 2, the customer left.) — failed 2/3 — never called cancel_order  
  calls: get_order  
  answer: Sure, I can cancel the order for Bahçe 2. Could you let me know why it’s being cancelled (e.g., “the customer left” or any other reason)?
- `en-approve-void-line` (Remove the ayrans from Bahçe 2, they were entered by mistake.) — failed 1/3 — answered in Turkish to a English request  
  calls: get_order > void_order_item  
  answer: Ayranlar Bahçe 2’den silindi. Yeni toplam 1 120,00 TRY olarak güncellendi. Başka bir işlem ister misiniz?
