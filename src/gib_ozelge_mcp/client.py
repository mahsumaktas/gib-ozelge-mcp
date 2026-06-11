"""GIB portal mevzuat API istemcisi.

Resmi olmayan API: www.gib.gov.tr mevzuat arama sayfasinin kullandigi endpoint'ler.
Endpoint envanteri portal Next.js bundle analizinden cikarildi, tum davranislar
2026-06-11'de canli API'ye karsi dogrulandi (bkz. docs/superpowers/specs/).

Ortak body filtreleri (tum mevzuat turleri): title (tam metin), kanunId, id.
Yalnizca ozelge: ozelgeNo (tam eslesme), maddeList[{id}], ozelgeStartDate/EndDate
(format: YYYY-MM-DDTHH:MM:SS).
"""

from __future__ import annotations

from typing import Any

import httpx

API_BASE = "https://gib.gov.tr/api/gibportal/"

# Portal arama sayfasinin gonderdigi sabit filtre (status=2: yayimlanmis)
_BASE_BODY = {"status": 2, "deleted": False, "ktype": 99}

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://www.gib.gov.tr",
    "Referer": "https://www.gib.gov.tr/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    ),
}

TIMEOUT_SECONDS = 30.0

# Tur -> (endpoint, dogrulanmis sort alani, varsayilan yon, tarih alani, belge no alani)
# Sort alanlari canli probe ile dogrulandi; portal default'lariyla uyumlu.
MEVZUAT_TURLERI: dict[str, dict[str, Any]] = {
    "ozelge": {
        "endpoint": "mevzuat/ozelge/list",
        "sort_field": "ozelgeTarih",
        "sort_default": "DESC",
        "tarih_alani": "ozelgeTarih",
        "no_alani": "ozelgeNo",
        "aciklama": "Özelgeler (mukteza)",
    },
    "teblig": {
        "endpoint": "mevzuat/teblig/list",
        "sort_field": "id",
        "sort_default": "DESC",
        "tarih_alani": "resmiGazeteTarih",
        "no_alani": "resmiGazeteSayi",
        "aciklama": "Genel tebliğler",
    },
    "sirkuler": {
        "endpoint": "mevzuat/sirkuler/list",
        "sort_field": "sirkulerTarih",
        "sort_default": "DESC",
        "tarih_alani": "sirkulerTarih",
        "no_alani": "sirkulerNo",
        "aciklama": "Sirküler",
    },
    "yonetmelik": {
        "endpoint": "mevzuat/yonetmelikler/list",
        "sort_field": "resmiGazeteTarih",
        "sort_default": "DESC",
        "tarih_alani": "resmiGazeteTarih",
        "no_alani": "resmiGazeteSayi",
        "aciklama": "Yönetmelikler",
    },
    "bkk": {
        "endpoint": "mevzuat/bkk/list",
        "sort_field": "resmiGazeteTarih",
        "sort_default": "DESC",
        "tarih_alani": "resmiGazeteTarih",
        "no_alani": "no",
        "aciklama": "Bakanlar Kurulu Kararları",
    },
    "cbk": {
        "endpoint": "mevzuat/cbk/list",
        "sort_field": "resmiGazeteTarih",
        "sort_default": "DESC",
        "tarih_alani": "resmiGazeteTarih",
        "no_alani": "no",
        "aciklama": "Cumhurbaşkanı Kararları",
    },
    "genel_yazi": {
        "endpoint": "mevzuat/genelYazilar/list",
        "sort_field": "tarih",
        "sort_default": "DESC",
        "tarih_alani": "tarih",
        "no_alani": "sayi",
        "aciklama": "Genel yazılar",
    },
    "ic_genelge": {
        "endpoint": "mevzuat/icGenelge/list",
        "sort_field": "id",
        "sort_default": "DESC",
        "tarih_alani": "tarih",
        "no_alani": None,
        "aciklama": "İç genelgeler",
    },
    "gerekce": {
        "endpoint": "mevzuat/gerekce/list",
        "sort_field": "id",
        "sort_default": "ASC",
        "tarih_alani": None,
        "no_alani": None,
        "aciklama": "Kanun gerekçeleri",
    },
}

# kanun/filterList erisilemezse kullanilacak yedek harita (en buyuk 15 kanun, 2026-06-11)
KANUNLAR_FALLBACK = [
    {"id": 433, "kanunNo": "193", "title": "GELİR VERGİSİ KANUNU"},
    {"id": 434, "kanunNo": "213", "title": "VERGİ USUL KANUNU"},
    {"id": 435, "kanunNo": "5520", "title": "KURUMLAR VERGİSİ KANUNU"},
    {"id": 436, "kanunNo": "3065", "title": "KATMA DEĞER VERGİSİ KANUNU"},
    {"id": 437, "kanunNo": "4760", "title": "ÖZEL TÜKETİM VERGİSİ KANUNU"},
    {"id": 438, "kanunNo": "488", "title": "DAMGA VERGİSİ KANUNU"},
    {"id": 439, "kanunNo": "492", "title": "HARÇLAR KANUNU"},
    {"id": 440, "kanunNo": "7338", "title": "VERASET VE İNTİKAL VERGİSİ KANUNU"},
    {"id": 441, "kanunNo": "197", "title": "MOTORLU TAŞITLAR VERGİSİ KANUNU"},
    {"id": 443, "kanunNo": "3100", "title": "KDV MÜKELLEFLERİNİN ÖDEME KAYDEDİCİ CİHAZLARI KULLANMALARI MECBURİYETİ HAKKINDA KANUN"},
    {"id": 444, "kanunNo": "3568", "title": "SERBEST MUHASEBECİ MALİ MÜŞAVİRLİK VE YEMİNLİ MALİ MÜŞAVİRLİK KANUNU"},
    {"id": 445, "kanunNo": "6802", "title": "GİDER VERGİLERİ KANUNU"},
    {"id": 446, "kanunNo": "210", "title": "DEĞERLİ KAĞITLAR KANUNU"},
    {"id": 447, "kanunNo": "1319", "title": "EMLAK VERGİSİ KANUNU"},
    {"id": 449, "kanunNo": "2464", "title": "BELEDİYE GELİRLERİ KANUNU"},
]


class GibApiError(RuntimeError):
    """GIB API'ye ulasilamadi veya beklenmeyen cevap dondu."""


async def _request(
    path: str,
    *,
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """API cagrisi yapar, resultContainer'i dondurur. body=None ise GET."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, headers=_HEADERS) as client:
            if body is None:
                resp = await client.get(API_BASE + path, params=params)
            else:
                resp = await client.post(API_BASE + path, params=params, json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise GibApiError(f"GIB API istegi basarisiz ({path}): {exc}") from exc
    except ValueError as exc:
        raise GibApiError(f"GIB API JSON disi cevap dondu ({path}): {exc}") from exc

    result = data.get("resultContainer")
    if result is None:
        raise GibApiError(
            f"Beklenmeyen API cevabi ({path}, status={data.get('status')},"
            f" mesaj={data.get('statusMessage')}); portal yapisi degismis olabilir"
        )
    return result


def _normalize_date(value: str, end_of_day: bool) -> str:
    """'YYYY-MM-DD' girdisini portal formatina cevirir (T00:00:00 / T23:59:59)."""
    value = value.strip()
    if "T" in value:
        return value
    return f"{value}T23:59:59" if end_of_day else f"{value}T00:00:00"


async def mevzuat_list(
    tur: str = "ozelge",
    *,
    title: str | None = None,
    kanun_id: int | None = None,
    item_id: int | None = None,
    ozelge_no: str | None = None,
    madde_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 0,
    size: int = 10,
    sort_type: str | None = None,
) -> dict[str, Any]:
    """Secilen mevzuat turunde listeleme/arama yapar; resultContainer dondurur.

    ozelge_no, madde_id, start_date, end_date yalnizca tur='ozelge' icin gecerlidir.
    """
    spec = MEVZUAT_TURLERI.get(tur)
    if spec is None:
        raise ValueError(
            f"Bilinmeyen mevzuat turu: {tur!r}. Gecerli turler: {', '.join(MEVZUAT_TURLERI)}"
        )

    ozelge_only = {
        "ozelge_no": ozelge_no,
        "madde_id": madde_id,
        "start_date": start_date,
        "end_date": end_date,
    }
    if tur != "ozelge":
        kullanilmis = [k for k, v in ozelge_only.items() if v]
        if kullanilmis:
            raise ValueError(
                f"{', '.join(kullanilmis)} filtreleri yalnizca tur='ozelge' icin gecerlidir"
            )

    body: dict[str, Any] = dict(_BASE_BODY)
    if title:
        body["title"] = title
    if kanun_id is not None:
        body["kanunId"] = kanun_id
    if item_id is not None:
        body["id"] = item_id
    if ozelge_no:
        body["ozelgeNo"] = ozelge_no
    if madde_id is not None:
        body["maddeList"] = [{"id": madde_id}]
    if start_date:
        body["ozelgeStartDate"] = _normalize_date(start_date, end_of_day=False)
    if end_date:
        body["ozelgeEndDate"] = _normalize_date(end_date, end_of_day=True)

    yon = (sort_type or spec["sort_default"]).upper()
    params = {
        "page": max(0, page),
        "size": size,
        "sortFieldName": spec["sort_field"],
        "sortType": "ASC" if yon == "ASC" else "DESC",
    }

    result = await _request(spec["endpoint"], body=body, params=params)
    if "content" not in result:
        raise GibApiError(f"Beklenmeyen cevap: content alani yok ({spec['endpoint']})")
    return result


async def mevzuat_search_all(query: str) -> dict[str, int]:
    """Tum mevzuat turlerinde arar; tur bazli sonuc sayimlarini dondurur."""
    body = dict(_BASE_BODY)
    body.update({"title": query, "description": query, "kanunNo": query, "kanunIds": []})
    result = await _request(
        "mevzuat/mevzuatSearchAll",
        body=body,
        params={"page": 0, "sortFieldName": "id", "sortType": "ASC"},
    )
    if not isinstance(result, dict):
        raise GibApiError("mevzuatSearchAll beklenmeyen cevap dondurdu")
    return {k: v for k, v in result.items() if isinstance(v, int)}


async def kanun_filter_list() -> list[dict[str, Any]]:
    """Portaldaki tum vergi kanunlarini dondurur (id, kanunNo, title)."""
    result = await _request(
        "mevzuat/kanun/filterList",
        body={"kanunType": 99},
        params={"page": 0, "size": 1000, "sortFieldName": "priority", "sortType": "ASC"},
    )
    return result.get("content") or []


async def madde_by_kanun(kanun_id: int) -> list[dict[str, Any]]:
    """Bir kanunun tum maddelerini dondurur."""
    result = await _request(
        "mevzuat/madde/findByKanunId",
        params={
            "kanunId": kanun_id,
            "status": 2,
            "page": 0,
            "size": 2000,
            "sortFieldName": "id",
            "sortType": "ASC",
        },
    )
    return result.get("content") or []


async def madde_by_id(madde_id: int) -> dict[str, Any]:
    """Tek bir kanun maddesinin tam icerigini dondurur."""
    result = await _request(
        "mevzuat/madde/findById",
        params={
            "maddeId": madde_id,
            "status": 2,
            "page": 0,
            "sortFieldName": "id",
            "sortType": "DESC",
        },
    )
    # Bu endpoint content listesi degil dogrudan madde objesi dondurur
    if not result.get("title"):
        raise GibApiError(f"maddeId={madde_id} ile madde bulunamadi")
    return result


async def last_added() -> list[dict[str, Any]]:
    """Portala son eklenen mevzuati dondurur (tum turlerden)."""
    result = await _request("search/mevzuatLastAdded")
    return result.get("results") or []
