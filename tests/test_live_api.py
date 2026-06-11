"""Canli GIB API smoke testleri (network gerektirir).

Atlamak icin: uv run pytest -m "not live"
Dogrulama degerleri 2026-06-11'de canli API'den alindi.
"""

import asyncio
import json

import pytest

from gib_ozelge_mcp import server
from gib_ozelge_mcp.client import (
    kanun_filter_list,
    last_added,
    madde_by_id,
    madde_by_kanun,
    mevzuat_list,
    mevzuat_search_all,
)

pytestmark = pytest.mark.live

KNOWN_ID = 38881
KNOWN_OZELGE_NO = "E-66813766-140[38-2026/9]-321949"
KDV_KANUN_ID = 436
KDV_MADDE_17_ID = 7355


# ---------------- client katmani ----------------

def test_client_search_finds_results():
    result = asyncio.run(mevzuat_list("ozelge", title="konkordato", size=5))
    assert result["totalElements"] > 0
    assert len(result["content"]) > 0


def test_client_kanun_filter_applied():
    result = asyncio.run(mevzuat_list("ozelge", kanun_id=KDV_KANUN_ID, size=5))
    assert all(x["kanunId"] == KDV_KANUN_ID for x in result["content"])


def test_client_date_range_filter():
    result = asyncio.run(
        mevzuat_list("ozelge", start_date="2026-04-01", end_date="2026-04-30", size=50)
    )
    # 2026-06-11 itibariyle Nisan 2026'da 16 ozelge vardi; en az o kadar olmali
    assert result["totalElements"] >= 16
    tarihler = [x["ozelgeTarih"][:10] for x in result["content"]]
    assert all("2026-04-01" <= t <= "2026-04-30" for t in tarihler)


def test_client_madde_filter():
    result = asyncio.run(mevzuat_list("ozelge", madde_id=KDV_MADDE_17_ID, size=2))
    assert result["totalElements"] > 100  # KDV m.17: 960 ozelge (2026-06-11)


def test_client_date_filter_rejected_for_other_types():
    with pytest.raises(ValueError):
        asyncio.run(mevzuat_list("teblig", start_date="2026-01-01"))


def test_client_teblig_search():
    result = asyncio.run(mevzuat_list("teblig", title="enflasyon", size=3))
    assert result["totalElements"] >= 10
    assert result["content"][0]["title"]


def test_client_all_types_reachable():
    for tur in ["sirkuler", "yonetmelik", "bkk", "cbk", "genel_yazi", "ic_genelge", "gerekce"]:
        result = asyncio.run(mevzuat_list(tur, size=1))
        assert result["totalElements"] > 0, f"{tur} bos dondu"


def test_client_unknown_type_rejected():
    with pytest.raises(ValueError):
        asyncio.run(mevzuat_list("kararname"))


def test_client_kanun_filter_list_dynamic():
    kanunlar = asyncio.run(kanun_filter_list())
    assert len(kanunlar) >= 200  # 2026-06-11: 220 kanun
    ids = {k["id"] for k in kanunlar}
    assert KDV_KANUN_ID in ids


def test_client_madde_by_kanun():
    maddeler = asyncio.run(madde_by_kanun(KDV_KANUN_ID))
    assert len(maddeler) >= 100  # KDV: 109 madde
    assert any("Madde 17" in (m.get("title") or "") for m in maddeler)


def test_client_madde_by_id():
    madde = asyncio.run(madde_by_id(KDV_MADDE_17_ID))
    assert "Madde 17" in madde["title"]
    assert len(madde["description"]) > 10000  # 42KB HTML


def test_client_search_all_counts():
    counts = asyncio.run(mevzuat_search_all("enflasyon düzeltmesi"))
    assert counts["TOTALSEARCHCOUNT"] > 0
    assert counts["OZELGE"] > 0


def test_client_last_added():
    items = asyncio.run(last_added())
    assert len(items) > 0
    assert items[0].get("url")


# ---------------- MCP araclari (dict dondurur, hatalar exception) ----------------

def test_tool_ozelge_ara_compact_output_with_snippet():
    out = asyncio.run(server.ozelge_ara(sorgu="fizyoterapist", sayfa_boyutu=5))
    assert out["toplam_sonuc"] >= 1
    ilk = out["sonuclar"][0]
    assert {"id", "tarih", "no", "kanun_id", "kanun", "baslik", "link"} <= set(ilk)
    # Snippet: sorgu icerikte gectiginde eslesme baglami verilmeli
    assert any("fizyoterapist" in (s.get("eslesme") or "").lower() for s in out["sonuclar"])
    # Kompakt cikti: ham HTML listede yer almamali
    assert "description" not in json.dumps(out)


def test_tool_ozelge_ara_date_range():
    out = asyncio.run(
        server.ozelge_ara(baslangic_tarihi="2026-04-01", bitis_tarihi="2026-04-30", sayfa_boyutu=50)
    )
    assert out["toplam_sonuc"] >= 16
    assert all("2026-04" in s["tarih"] for s in out["sonuclar"])


def test_tool_ozelge_detay_clean_text():
    out = asyncio.run(server.ozelge_detay(KNOWN_ID))
    assert out["no"] == KNOWN_OZELGE_NO
    assert out["tarih"] == "2026-04-30"
    assert "<" not in out["icerik"]
    assert "GELİR İDARESİ BAŞKANLIĞI" in out["icerik"]


def test_tool_ozelge_detay_not_found_raises():
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        asyncio.run(server.ozelge_detay(999999999))


def test_tool_invalid_type_raises_for_self_correction():
    # SEP-1303: dogrulama hatasi acik mesajli exception olmali (isError:true'ya doner)
    with pytest.raises(ValueError, match="Gecerli turler"):
        asyncio.run(server.mevzuat_ara(tur="kararname"))


def test_tool_mevzuat_ara_teblig():
    out = asyncio.run(server.mevzuat_ara(tur="teblig", sorgu="enflasyon", sayfa_boyutu=3))
    assert out["toplam_sonuc"] >= 10
    assert out["sonuclar"][0]["baslik"]


def test_tool_mevzuat_detay_teblig():
    listed = asyncio.run(server.mevzuat_ara(tur="teblig", sorgu="enflasyon", sayfa_boyutu=1))
    tid = listed["sonuclar"][0]["id"]
    out = asyncio.run(server.mevzuat_detay(tur="teblig", mevzuat_id=tid))
    assert out["id"] == tid
    assert len(out["icerik"]) > 100
    assert "<" not in out["icerik"]


def test_tool_madde_detay_windowing():
    out = asyncio.run(server.madde_detay(KDV_MADDE_17_ID))
    assert "Madde 17" in out["baslik"]
    assert out["toplam_uzunluk"] > len(out["icerik"]) or out["kalan"] == 0
    if out["kalan"] > 0:
        out2 = asyncio.run(server.madde_detay(KDV_MADDE_17_ID, kisim=2))
        assert out2["icerik"] and out2["icerik"] != out["icerik"]


def test_tool_kanun_listesi_dynamic_with_filter():
    out = asyncio.run(server.kanun_listesi(filtre="katma değer"))
    adlar = [k["ad"] for k in out["kanunlar"]]
    assert any("KATMA DEĞER" in a for a in adlar)
    assert len(adlar) < 50  # filtre uygulanmis olmali


def test_tool_kanun_maddeleri():
    out = asyncio.run(server.kanun_maddeleri(KDV_KANUN_ID))
    assert out["toplam"] >= 100
    assert any("Madde 17" in (m["baslik"] or "") for m in out["maddeler"])


def test_tool_mevzuat_genel_arama():
    out = asyncio.run(server.mevzuat_genel_arama("enflasyon düzeltmesi"))
    assert out["toplam"] > 0
    assert out["sayimlar"]["ozelge"] > 0


def test_tool_yeni_eklenenler():
    out = asyncio.run(server.yeni_eklenenler())
    assert len(out["kayitlar"]) > 0
