# gib-ozelge-mcp Tasarım

Tarih: 2026-06-11

## Amaç

GİB özelgelerinde (18.355 kayıt) arama yapan, Claude Code'a stdio ile bağlanan MCP sunucusu.

## API Keşfi (canlı doğrulandı)

Endpoint: `POST https://gib.gov.tr/api/gibportal/mevzuat/ozelge/list?page&size&sortFieldName=ozelgeTarih&sortType`

| Body alanı | Davranış | Kanıt |
|---|---|---|
| `title` | Başlık + içerik tam metin | "konkordato" 64, "fizyoterapist" 5 sonuç; içerikte geçenler de dönüyor |
| `kanunId` | Kanun filtresi | 436 → 5602 KDV özelgesi |
| `ozelgeNo` | Tam eşleşme | Kısmi 0, tam değer 1 sonuç |
| `id` | Tek kayıt | id=38881 → 1 sonuç |
| tarih aralığı | YOK | 4 isim varyasyonu denendi, etkisiz |

Sabit body: `{"status":2,"deleted":false,"ktype":99}`. Kanun listesi endpoint'i yok (404) - kanunId 430-450 taramasıyla 15 kanun statik haritaya alındı.

## Mimari

- Python ≥3.10, FastMCP (`mcp` paketi) + `httpx`, stdio transport
- `client.py`: API çağrısı + hata sarmalama (`GibApiError`) + `KANUNLAR` haritası
- `htmlutil.py`: stdlib HTMLParser ile HTML→düz metin. Tablo hücresi içi bloklar boşlukla birleşir, satırı `tr` belirler; kaynak HTML newline'ları veri olarak yutulur
- `server.py`: 3 araç - `ozelge_ara` (kompakt liste, HTML içerik hariç = token tasarrufu), `ozelge_detay` (id ile tam temiz metin + ilgili maddeler), `kanun_listesi` (statik)
- Araçlar hata durumunda `{"hata": "..."}` JSON döndürür (MCP istemcisine anlaşılır mesaj)

## Değerlendirilen alternatifler

1. **Tüm veriyi indirip lokal indeks (SQLite/FTS)**: tarih filtresi ve daha iyi arama sağlar; reddedildi - 368 sayfa senkron yükü, bayatlama riski, YAGNI.
2. **TypeScript SDK**: reddedildi - kullanıcı ekosistemi Python ağırlıklı, ek değer yok.
3. **Seçilen**: ince Python proxy + sunucu tarafı arama.

## Test stratejisi

- `test_htmlutil.py`: offline, gerçek özelge HTML formatıyla (kaynak newline + girinti dahil)
- `test_live_api.py`: canlı API smoke (filtre davranışları + araç çıktı şemaları), `-m "not live"` ile atlanabilir
- `test_mcp_e2e.py`: gerçek stdio sunucusuna MCP el sıkışma + tool listesi + arama

## Bilinen sınırlar

- Resmi olmayan API; portal değişirse `GibApiError` açık mesaj verir
- ~~Tarih aralığı filtresi yok~~ (v2'de bulundu: `ozelgeStartDate/ozelgeEndDate`)
- `ozelgeNo` yalnızca tam eşleşme

---

# v2 Genişletme (2026-06-11, derin keşif sonrası)

## Yeni API keşfi (Next.js bundle analizi + canlı doğrulama)

Portal frontend chunk'ı (`2446-a1b7ddec837d8259.js`) tüm endpoint envanterini verdi:

| Keşif | Kanıt (canlı) |
|---|---|
| `ozelgeStartDate/ozelgeEndDate` body alanları, format `YYYY-MM-DDTHH:MM:SS` | Nisan 2026 → 16 özelge, sınır tarihler doğru |
| `maddeList:[{id}]` ile madde bazlı özelge filtresi | KDV m.17 (id 7355) → 960 özelge |
| `kanunIds:[...]` çoklu kanun | [440,441] → 416 = 279+137 |
| `kanun/filterList` POST `{kanunType:99}` → dinamik kanun listesi | 220 kanun (statik 15'lik harita çok eksikti) |
| `madde/findByKanunId` GET → kanunun tüm maddeleri | KDV → 109 madde |
| `madde/findById` GET → madde tam metni | m.17 → 42KB HTML |
| `mevzuat/mevzuatSearchAll` POST → tür bazlı sonuç sayımı | "enflasyon düzeltmesi" → {OZELGE:190, MADDE:26, TEBLIG:21, SIRKULER:29, KANUN:9, toplam:275} |
| `search/mevzuatLastAdded` GET → son eklenen mevzuat | 7 kayıt, tüm türlerden |
| 8 ek mevzuat türü list endpoint'i, hepsi `title` aramalı + `id` filtreli | teblig 2480, bkk 586, sirkuler 584, ic_genelge 322, cbk 236, genel_yazi 91, gerekce 93, yonetmelik 66 |
| Arama metnini `title+description+kanunNo` üçlüsüne kopyalamak gereksiz | üçlü = tek title (64=64) |
| `search/mevzuat` POST kabul etmiyor (405) | mevzuatSearchAll yeterli, atlandı |

Tür bazlı doğrulanmış sıralama alanları: ozelge=ozelgeTarih, sirkuler=sirkulerTarih,
yonetmelik/bkk/cbk=resmiGazeteTarih, genel_yazi/ic_genelge=tarih, teblig/gerekce=id.

## v2 Araç seti (9 araç)

1. `mevzuat_genel_arama(sorgu)` - tür bazlı sayım (yönlendirme aracı)
2. `ozelge_ara(...)` - + tarih aralığı, madde_id filtresi, sonuçlarda eşleşme bağlamı (snippet)
3. `mevzuat_ara(tur, ...)` - 8 ek tür için ortak arama
4. `mevzuat_detay(tur, id, kisim)` - ortak detay; ozelge_detay bunun tur="ozelge" hali;
   büyük metinler (madde 42KB) için karakter penceresi (kisim parametresi)
5. `kanun_listesi(filtre)` - dinamik 220 kanun, ad filtresi, statik fallback
6. `kanun_maddeleri(kanun_id)` - madde id+başlık listesi
7. `madde_detay(madde_id, kisim)` - kanun maddesi tam metni
8. `yeni_eklenenler()` - son eklenen mevzuat
9. `ozelge_detay(ozelge_id)` - geriye uyum için korunur (mevzuat_detay'a delege)

## Deep-research bulguları ve uygulanışı (2026-06-11, 103 agent / 21 kaynak / 24 doğrulanmış bulgu)

| Bulgu (kanıt: resmi MCP blog/spec/SDK README) | Uygulanan |
|---|---|
| Python SDK v2 stable 2026-07-27'de (breaking); resmi öneri `mcp>=1.27,<2` | pyproject pinlendi |
| FastMCP 1.x: dict dönüş tipi → otomatik structured output + geriye uyumlu TextContent | 9 aracın tümü `-> dict[str, Any]`; manuel json.dumps kaldırıldı |
| SEP-1303 (Final): doğrulama hataları isError:true tool result olmalı (model öz-düzeltme) | try/except kaldırıldı; ValueError/GibApiError/ToolError fırlar, FastMCP isError üretir; e2e'de doğrulandı |
| Connectors Directory zorunluluğu: tüm araçlarda title + readOnlyHint | `ToolAnnotations(readOnlyHint=True, openWorldHint=True)` + title tüm araçlarda |
| Spec 2026-07-28 final: protokol stateless oluyor | Sunucu zaten stateless proxy; uyumlu, değişiklik yok |
| Tool konsolidasyonu (GitHub MCP: 3 tool, %50 token tasarrufu) | mevzuat_ara/mevzuat_detay 8 türü 2 araçta toplar; 9 araç toplam |
| Arama yanıtlarında pagination+filtreleme+truncation; Claude Code 25k token cap | sayfa_boyutu<=50, detaylar 25.000 karakter pencereli (kisim) |
| Semantik kimlikler (çıplak ID yerine başlık/tarih/tür) | _ozet her kayıtta baslik+tarih+no+kanun döndürür |
| Çürütülen iddia (0-3): "standalone FastMCP typed return zorunluluğu" | FastMCP 3.x migration planında bu varsayıma dayanılmıyor |

Ertelenenler: response_format concise/detailed enum (mevcut çıktı zaten kompakt; YAGNI),
MCPB (.mcpb, uv server type) paketleme (dağıtım ihtiyacı doğunca), Tasks extension
(uzun iş yok). Tamamlayıcı ekosistem: saidsurucu/mevzuat-mcp (mevzuat.gov.tr),
saidsurucu/yargi-mcp (yargı kararları) - GİB özelge/mevzuat alanı bu projeyle kapanıyor.

## v2 kararları

- Snippet: arama sonucunda sorgunun ilk geçtiği yerin ±150 karakteri (description zaten
  response'ta geliyor, ek istek yok) - LLM'in hangi kaydı açacağına karar vermesini sağlar
- Token güvenliği: detay metinleri varsayılan 25.000 karakterde kesilir; `kisim` parametresi
  ile sonraki pencereler alınır; çıktıda toplam uzunluk + kalan bilgisi
- Tarih girdisi araçlarda `YYYY-MM-DD`; client portal davranışıyla `T00:00:00`/`T23:59:59` ekler
- Statik KANUNLAR haritası dinamik `kanun/filterList`'in fallback'i olarak kalır
