"""GIB mevzuat arama MCP sunucusu (stdio).

Kapsam: ozelge, teblig, sirkuler, yonetmelik, BKK, CBK, genel yazi, ic genelge,
kanun gerekceleri + kanun/madde metinleri + turler arasi genel arama.

Tasarim notlari (MCP 2025-11-25 best practices, 2026-06-11 arastirmasi):
- Tum araclar dict dondurur -> FastMCP otomatik structured output uretir
- Dogrulama/API hatalari exception olarak firlar -> istemciye isError:true
  tool result gider (SEP-1303: model kendini duzeltebilsin)
- Tum araclar salt okunur: ToolAnnotations(readOnlyHint=True)
- Sunucu stateless (2026-07-28 spec yonune uyumlu)
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from .client import (
    KANUNLAR_FALLBACK,
    MEVZUAT_TURLERI,
    GibApiError,
    kanun_filter_list,
    last_added,
    madde_by_id,
    madde_by_kanun,
    mevzuat_list,
    mevzuat_search_all,
)
from .htmlutil import _tr_fold, find_snippet, html_to_text

mcp = FastMCP("gib-mevzuat")

MAX_PAGE_SIZE = 50
PENCERE = 25_000  # detay metinleri icin karakter penceresi (token guvenligi)

_RO = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

# mevzuatSearchAll API anahtarlari -> bu sunucudaki tur adlari
_SAYIM_ESLEME = {
    "OZELGE": "ozelge",
    "TEBLIG": "teblig",
    "SIRKULER": "sirkuler",
    "YONETMELIKLER": "yonetmelik",
    "BKK": "bkk",
    "CBK": "cbk",
    "GENELYAZILAR": "genel_yazi",
    "ICGENELGE": "ic_genelge",
    "GEREKCE": "gerekce",
    "KANUN": "kanun",
    "MADDE": "madde",
}


def _ozet(tur: str, item: dict[str, Any], sorgu: str | None = None) -> dict[str, Any]:
    spec = MEVZUAT_TURLERI[tur]
    out: dict[str, Any] = {"id": item.get("id"), "baslik": item.get("title")}
    if spec["tarih_alani"]:
        out["tarih"] = (item.get(spec["tarih_alani"]) or "")[:10] or None
    if spec["no_alani"]:
        out["no"] = item.get(spec["no_alani"])
    if item.get("kanunId") is not None:
        out["kanun_id"] = item.get("kanunId")
    if item.get("kanunTitle"):
        out["kanun"] = item.get("kanunTitle")
    if item.get("siteLink"):
        out["link"] = item.get("siteLink")
    if sorgu:
        eslesme = find_snippet(html_to_text(item.get("description")), sorgu)
        if eslesme:
            out["eslesme"] = eslesme
    return out


def _pencerele(metin: str, kisim: int) -> dict[str, Any]:
    """Uzun metni PENCERE boyutlu kisimlara boler (kisim 1 tabanli)."""
    toplam = len(metin)
    toplam_kisim = max(1, -(-toplam // PENCERE))
    k = min(max(1, kisim), toplam_kisim)
    start = (k - 1) * PENCERE
    parca = metin[start : start + PENCERE]
    return {
        "icerik": parca,
        "toplam_uzunluk": toplam,
        "kisim": k,
        "toplam_kisim": toplam_kisim,
        "kalan": max(0, toplam - (start + len(parca))),
    }


def _sayfa_bilgisi(result: dict[str, Any], sayfa: int) -> dict[str, Any]:
    return {
        "toplam_sonuc": result.get("totalElements"),
        "toplam_sayfa": result.get("totalPages"),
        "sayfa": result.get("number", sayfa),
    }


@mcp.tool(title="GİB mevzuatında genel arama", annotations=_RO)
async def mevzuat_genel_arama(sorgu: str) -> dict[str, Any]:
    """Tüm GİB mevzuatında arar; hangi türde kaç sonuç olduğunu döndürür.

    Araştırmaya başlarken ilk çağrılacak araç: sonucuna göre ozelge_ara
    (tür=özelge) veya mevzuat_ara (diğer türler) ile ilgili türe inilir.
    "kanun" ve "madde" sayımları için kanun_listesi / kanun_maddeleri /
    madde_detay araçları kullanılır.

    Args:
        sorgu: Aranacak ifade (başlık + içerikte tam metin).

    Returns:
        toplam ve tür bazlı sayımlar (çoktan aza sıralı).
    """
    counts = await mevzuat_search_all(sorgu)
    sayimlar = {
        _SAYIM_ESLEME.get(k, k.lower()): v
        for k, v in counts.items()
        if k != "TOTALSEARCHCOUNT"
    }
    return {
        "sorgu": sorgu,
        "toplam": counts.get("TOTALSEARCHCOUNT", 0),
        "sayimlar": dict(sorted(sayimlar.items(), key=lambda x: -x[1])),
    }


@mcp.tool(title="Özelge ara", annotations=_RO)
async def ozelge_ara(
    sorgu: str = "",
    kanun_id: int | None = None,
    madde_id: int | None = None,
    ozelge_no: str = "",
    baslangic_tarihi: str = "",
    bitis_tarihi: str = "",
    sayfa: int = 0,
    sayfa_boyutu: int = 10,
    siralama: str = "DESC",
) -> dict[str, Any]:
    """GİB özelgelerinde (mukteza) arama yapar (18.000+ özelge).

    Args:
        sorgu: Tam metin arama; başlık VE içerikte geçen ifadeyi arar.
            Boş bırakılırsa filtrelerle listeleme yapılır.
        kanun_id: Kanun filtresi (kanun_listesi aracından; örn 436=KDV).
        madde_id: Belirli bir kanun maddesiyle ilişkili özelgeler
            (kanun_maddeleri aracından madde id'si alın).
        ozelge_no: Özelge sayısıyla TAM eşleşme; kısmi numara sonuç vermez.
        baslangic_tarihi: Özelge tarihi alt sınırı, YYYY-MM-DD.
        bitis_tarihi: Özelge tarihi üst sınırı, YYYY-MM-DD.
        sayfa: 0 tabanlı sayfa numarası.
        sayfa_boyutu: Sayfa başına sonuç (1-50).
        siralama: Özelge tarihine göre "DESC" (yeni→eski) veya "ASC".

    Returns:
        toplam_sonuc, sayfa bilgisi ve sonuçlar (id, tarih, no, kanun, baslik,
        link, eslesme=sorgunun geçtiği bağlam). Tam metin için ozelge_detay
        aracını çağırın.
    """
    size = min(max(1, sayfa_boyutu), MAX_PAGE_SIZE)
    result = await mevzuat_list(
        "ozelge",
        title=sorgu.strip() or None,
        kanun_id=kanun_id,
        madde_id=madde_id,
        ozelge_no=ozelge_no.strip() or None,
        start_date=baslangic_tarihi.strip() or None,
        end_date=bitis_tarihi.strip() or None,
        page=sayfa,
        size=size,
        sort_type=siralama,
    )
    out = _sayfa_bilgisi(result, sayfa)
    out["sonuclar"] = [
        _ozet("ozelge", x, sorgu.strip() or None) for x in result.get("content") or []
    ]
    return out


@mcp.tool(title="Mevzuat ara (tebliğ, sirküler, BKK...)", annotations=_RO)
async def mevzuat_ara(
    tur: str,
    sorgu: str = "",
    kanun_id: int | None = None,
    sayfa: int = 0,
    sayfa_boyutu: int = 10,
    siralama: str = "",
) -> dict[str, Any]:
    """Özelge dışındaki mevzuat türlerinde arama/listeleme yapar.

    Args:
        tur: teblig (genel tebliğler), sirkuler, yonetmelik, bkk (Bakanlar
            Kurulu Kararları), cbk (Cumhurbaşkanı Kararları), genel_yazi,
            ic_genelge, gerekce (kanun gerekçeleri). ozelge için ozelge_ara
            aracını kullanın (daha fazla filtre sunar).
        sorgu: Tam metin arama (başlık + içerik).
        kanun_id: Kanun filtresi (kanun_listesi aracından).
        sayfa: 0 tabanlı sayfa numarası.
        sayfa_boyutu: Sayfa başına sonuç (1-50).
        siralama: "DESC"/"ASC"; boş bırakılırsa tür için doğal sıralama.

    Returns:
        toplam_sonuc, sayfa bilgisi ve sonuçlar (id, baslik, tarih/no varsa,
        eslesme=sorgu bağlamı). Tam metin için mevzuat_detay çağırın.
    """
    size = min(max(1, sayfa_boyutu), MAX_PAGE_SIZE)
    result = await mevzuat_list(
        tur,
        title=sorgu.strip() or None,
        kanun_id=kanun_id,
        page=sayfa,
        size=size,
        sort_type=siralama.strip() or None,
    )
    out: dict[str, Any] = {"tur": tur, **_sayfa_bilgisi(result, sayfa)}
    out["sonuclar"] = [_ozet(tur, x, sorgu.strip() or None) for x in result.get("content") or []]
    return out


@mcp.tool(title="Mevzuat tam metni", annotations=_RO)
async def mevzuat_detay(tur: str, mevzuat_id: int, kisim: int = 1) -> dict[str, Any]:
    """Bir mevzuat kaydının tam metnini getirir (HTML temizlenmiş).

    Args:
        tur: ozelge, teblig, sirkuler, yonetmelik, bkk, cbk, genel_yazi,
            ic_genelge veya gerekce.
        mevzuat_id: Arama sonuçlarındaki "id" alanı.
        kisim: Uzun metinler 25.000 karakterlik kısımlara bölünür; 1'den
            başlar, çıktıdaki toplam_kisim/kalan alanlarına göre artırılır.

    Returns:
        meta (tarih, no, kanun, ilgili_maddeler varsa, link) + icerik.
    """
    result = await mevzuat_list(tur, item_id=mevzuat_id, page=0, size=1)
    content = result.get("content") or []
    if not content:
        raise ToolError(f"tur={tur} id={mevzuat_id} ile kayıt bulunamadı")

    item = content[0]
    detay = _ozet(tur, item)
    maddeler = [
        m.get("title")
        for m in item.get("maddeList") or []
        if isinstance(m, dict) and m.get("title")
    ]
    if maddeler:
        detay["ilgili_maddeler"] = maddeler
    detay.update(_pencerele(html_to_text(item.get("description")), kisim))
    return detay


@mcp.tool(title="Özelge tam metni", annotations=_RO)
async def ozelge_detay(ozelge_id: int, kisim: int = 1) -> dict[str, Any]:
    """Tek bir özelgenin tam metnini getirir (mevzuat_detay'ın özelge kısayolu).

    Args:
        ozelge_id: ozelge_ara sonuçlarındaki "id" alanı.
        kisim: Uzun metinlerde 25.000 karakterlik pencere numarası (1 tabanlı).

    Returns:
        meta bilgiler + HTML'den temizlenmiş tam metin (icerik).
    """
    return await mevzuat_detay(tur="ozelge", mevzuat_id=ozelge_id, kisim=kisim)


@mcp.tool(title="Vergi kanunları listesi", annotations=_RO)
async def kanun_listesi(filtre: str = "") -> dict[str, Any]:
    """Portaldaki vergi kanunlarını listeler (kanun_id filtreleri için kaynak).

    Args:
        filtre: Kanun adı veya numarasında geçen ifade (örn "katma değer",
            "5520"). Boş bırakılırsa tüm kanunlar (~220) döner.

    Returns:
        kanunlar[{kanun_id, kanun_no, ad}]. Liste portaldan canlı çekilir;
        erişilemezse en büyük 15 kanunluk yedek liste döner (kaynak alanı).
    """
    try:
        ham = await kanun_filter_list()
        kaynak = "canli"
    except GibApiError:
        ham = KANUNLAR_FALLBACK
        kaynak = "yedek-statik"

    kanunlar = [
        {"kanun_id": k.get("id"), "kanun_no": k.get("kanunNo"), "ad": k.get("title")}
        for k in ham
    ]
    f = _tr_fold(filtre.strip())
    if f:
        kanunlar = [
            k
            for k in kanunlar
            if f in _tr_fold(k["ad"] or "") or f in _tr_fold(str(k["kanun_no"] or ""))
        ]
    return {"kaynak": kaynak, "toplam": len(kanunlar), "kanunlar": kanunlar}


@mcp.tool(title="Kanun maddeleri listesi", annotations=_RO)
async def kanun_maddeleri(kanun_id: int, filtre: str = "") -> dict[str, Any]:
    """Bir kanunun madde listesini döndürür (madde_id kaynakları).

    Args:
        kanun_id: kanun_listesi aracından alınan kanun id'si (örn 436=KDV).
        filtre: Madde başlığında geçen ifade (örn "istisna", "Madde 17").

    Returns:
        maddeler[{madde_id, baslik}]. Madde tam metni için madde_detay,
        maddeyle ilgili özelgeler için ozelge_ara(madde_id=...) kullanılır.
    """
    ham = await madde_by_kanun(kanun_id)
    maddeler = [{"madde_id": m.get("id"), "baslik": m.get("title")} for m in ham]
    f = _tr_fold(filtre.strip())
    if f:
        maddeler = [m for m in maddeler if f in _tr_fold(m["baslik"] or "")]
    return {"kanun_id": kanun_id, "toplam": len(maddeler), "maddeler": maddeler}


@mcp.tool(title="Kanun maddesi tam metni", annotations=_RO)
async def madde_detay(madde_id: int, kisim: int = 1) -> dict[str, Any]:
    """Bir kanun maddesinin tam metnini getirir.

    Args:
        madde_id: kanun_maddeleri aracından alınan madde id'si.
        kisim: Uzun maddeler 25.000 karakterlik kısımlara bölünür (1 tabanlı);
            çıktıdaki toplam_kisim/kalan alanlarına göre artırılır.

    Returns:
        baslik, kanun bilgisi + temizlenmiş madde metni (icerik).
    """
    madde = await madde_by_id(madde_id)
    out: dict[str, Any] = {
        "madde_id": madde.get("id"),
        "baslik": madde.get("title"),
        "kanun_no": madde.get("kanunNo"),
        "kanun": madde.get("kanunNoTitle") or madde.get("kanunTitle"),
    }
    out.update(_pencerele(html_to_text(madde.get("description")), kisim))
    return out


@mcp.tool(title="Son eklenen mevzuat", annotations=_RO)
async def yeni_eklenenler() -> dict[str, Any]:
    """Portala son eklenen mevzuatı listeler (tüm türlerden).

    Returns:
        kayitlar[{tur, baslik, link, tarih varsa}].
    """
    items = await last_added()
    kayitlar = []
    for x in items:
        kayit = {
            "tur": x.get("entityType"),
            "baslik": (x.get("text") or x.get("kanunTitle") or "").strip(),
            "link": x.get("url"),
        }
        if x.get("resmiGazeteTarih"):
            kayit["tarih"] = str(x["resmiGazeteTarih"])[:10]
        kayitlar.append(kayit)
    return {"kayitlar": kayitlar}


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request):  # pragma: no cover - tek satirlik altyapi route'u
    from starlette.responses import PlainTextResponse

    return PlainTextResponse("ok")


def main() -> None:
    """Varsayilan stdio; PORT veya MCP_HTTP tanimliysa public HTTP modu.

    HTTP modu stateless'tir (her istek bagimsiz) - hem yatay olcekleme hem de
    2026-07-28 MCP spec'inin stateless cekirdegi ile uyumlu. Endpoint: /mcp
    """
    if os.environ.get("PORT") or os.environ.get("MCP_HTTP"):
        from mcp.server.transport_security import TransportSecuritySettings

        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = int(os.environ.get("PORT", "8080"))
        mcp.settings.stateless_http = True
        # DNS rebinding korumasi lokal sunuculari tarayici saldirisindan korur;
        # public modda Host kisiti istegi 421 ile dusurur (Render/Fly domain'i
        # localhost listesinde degil) - kapatilmali.
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
