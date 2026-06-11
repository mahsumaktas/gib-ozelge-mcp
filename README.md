# gib-ozelge-mcp

GİB (Gelir İdaresi Başkanlığı) mevzuatında arama yapan MCP sunucusu.
`gib.gov.tr` portal API'sini kullanır: 18.000+ özelge, 2.400+ tebliğ, sirküler,
yönetmelik, BKK/CBK, genel yazı, iç genelge, kanun gerekçeleri ve kanun maddeleri.

## Public sunucu (claude.ai / Claude Desktop connector)

Sunucu streamable HTTP ile public çalışır. claude.ai veya Claude Desktop'ta
**Settings > Connectors > Add custom connector** alanına URL'i yapıştırın:

```
https://gib-mevzuat-mcp.onrender.com/mcp
```

Not: Ücretsiz Render instance'ı 15 dk hareketsizlikte uyur; ilk istek ~50 sn
sürebilir. Kendi kopyanızı tek tıkla kurmak için:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/mahsumaktas/gib-ozelge-mcp)

Kendi sunucunuzu çalıştırmak için: `PORT=8080 uv run gib-ozelge-mcp`
(`/mcp` endpoint'i, stateless streamable HTTP; `/healthz` sağlık kontrolü).
Fly.io için hazır `fly.toml` ve her platform için `Dockerfile` repodadır.

## Araçlar (9)

| Araç | İşlev |
|------|-------|
| `mevzuat_genel_arama` | Tüm türlerde arar, tür bazlı sonuç sayımı döndürür (yönlendirme) |
| `ozelge_ara` | Özelge araması: tam metin, kanun, madde, tarih aralığı, özelge no; sonuçlarda eşleşme bağlamı |
| `ozelge_detay` | Özelgenin tam metni (HTML temizlenmiş) |
| `mevzuat_ara` | Tebliğ, sirküler, yönetmelik, BKK, CBK, genel yazı, iç genelge, gerekçe araması |
| `mevzuat_detay` | Herhangi bir mevzuat kaydının tam metni |
| `kanun_listesi` | ~220 vergi kanunu (canlı; ad/no filtresi) |
| `kanun_maddeleri` | Bir kanunun madde listesi (başlık filtresi) |
| `madde_detay` | Kanun maddesinin tam metni (uzun metinlerde kısım penceresi) |
| `yeni_eklenenler` | Portala son eklenen mevzuat |

Tipik akış: `mevzuat_genel_arama("enflasyon düzeltmesi")` → hangi türde kaç sonuç →
`ozelge_ara` / `mevzuat_ara` ile listele (eşleşme bağlamına bak) → `*_detay` ile tam metin.
Madde odaklı akış: `kanun_listesi("katma değer")` → `kanun_maddeleri(436, "istisna")` →
`madde_detay(7355)` veya `ozelge_ara(madde_id=7355)`.

## Kurulum

```bash
cd gib-ozelge-mcp
uv sync
```

## Claude Code'a ekleme

```bash
claude mcp add gib-ozelge -- uv run --directory /Users/mahsum/Projects/gib-ozelge-mcp gib-ozelge-mcp
```

## Claude Desktop'a ekleme

`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "gib-ozelge": {
      "command": "/opt/homebrew/bin/uv",
      "args": ["run", "--directory", "/Users/mahsum/Projects/gib-ozelge-mcp", "gib-ozelge-mcp"]
    }
  }
}
```

GUI uygulamaları homebrew PATH'ini görmediği için `uv` tam yoluyla yazılmalıdır.
Değişiklik sonrası Claude Desktop tamamen kapatılıp açılmalıdır (Cmd+Q).

## Test

```bash
uv run pytest               # tamami (canli API + MCP e2e dahil)
uv run pytest -m "not live" # sadece offline testler
```

## API notları (2026-06-11 canlı doğrulama)

- Taban: `https://gib.gov.tr/api/gibportal/` - resmi olmayan portal API'si
- Ortak filtreler: `title` (başlık+içerik tam metin), `kanunId`, `id`
- Özelgeye özel: `ozelgeNo` (tam eşleşme), `maddeList:[{id}]`,
  `ozelgeStartDate/ozelgeEndDate` (`YYYY-MM-DDTHH:MM:SS`)
- Endpoint envanteri portal Next.js bundle analiziyle çıkarıldı; ayrıntı ve
  kanıtlar: `docs/superpowers/specs/2026-06-11-gib-ozelge-mcp-design.md`
- Portal yapısı değişirse araçlar `{"hata": "..."}` döndürür, sessiz bozulmaz
