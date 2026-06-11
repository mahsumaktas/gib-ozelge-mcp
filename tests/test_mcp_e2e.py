"""MCP protokolu uzerinden uctan uca testler: stdio ve streamable HTTP."""

import asyncio
import json
import os
import subprocess
import sys
import time

import pytest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

pytestmark = pytest.mark.live

EXPECTED_TOOLS = {
    "mevzuat_genel_arama",
    "ozelge_ara",
    "ozelge_detay",
    "mevzuat_ara",
    "mevzuat_detay",
    "kanun_listesi",
    "kanun_maddeleri",
    "madde_detay",
    "yeni_eklenenler",
}


def test_stdio_handshake_tools_and_search():
    async def run() -> None:
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "gib_ozelge_mcp.server"]
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = await session.list_tools()
                assert {t.name for t in tools.tools} == EXPECTED_TOOLS
                # Tum araclar salt okunur isaretlenmis olmali (annotations)
                for t in tools.tools:
                    assert t.annotations and t.annotations.readOnlyHint is True, t.name

                result = await session.call_tool(
                    "ozelge_ara", {"sorgu": "konkordato", "sayfa_boyutu": 3}
                )
                assert not result.isError
                # Structured output (outputSchema'li tool) + geriye uyumlu text blogu
                assert result.structuredContent is not None
                assert result.structuredContent["toplam_sonuc"] > 0
                out = json.loads(result.content[0].text)
                assert len(out["sonuclar"]) == 3

                # SEP-1303: gecersiz girdi isError:true tool result olmali
                bad = await session.call_tool("mevzuat_ara", {"tur": "kararname"})
                assert bad.isError
                assert "Gecerli turler" in bad.content[0].text

    asyncio.run(run())


def test_streamable_http_handshake_and_tool_call():
    """PORT env'i ile sunucu HTTP modunda acilir; deploy edilen yol birebir bu."""
    port = "8765"
    env = {**os.environ, "PORT": port}
    proc = subprocess.Popen(
        [sys.executable, "-m", "gib_ozelge_mcp.server"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    async def run() -> None:
        import httpx

        health = httpx.get(f"http://127.0.0.1:{port}/healthz")
        assert health.status_code == 200 and health.text == "ok"

        # Public mod: yabanci Host basligi 421 YEMEMELI (reverse proxy arkasinda
        # gercek domain ile gelir; DNS rebinding korumasi public modda kapali)
        init_body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "probe", "version": "0"},
            },
        }
        foreign = httpx.post(
            f"http://127.0.0.1:{port}/mcp",
            json=init_body,
            headers={
                "Host": "ornek-public-domain.onrender.com",
                "Accept": "application/json, text/event-stream",
            },
        )
        assert foreign.status_code != 421, "yabanci Host 421 yedi: public mod kirik"

        url = f"http://127.0.0.1:{port}/mcp"
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert {t.name for t in tools.tools} == EXPECTED_TOOLS
                result = await session.call_tool("kanun_listesi", {"filtre": "5520"})
                assert not result.isError
                assert result.structuredContent["toplam"] >= 1

    try:
        son_hata = None
        for _ in range(20):  # sunucunun acilmasini bekle (max ~10s)
            time.sleep(0.5)
            try:
                asyncio.run(run())
                break
            except Exception as exc:  # baglanti reddi vb. -> tekrar dene
                son_hata = exc
        else:
            raise AssertionError(f"HTTP sunucusuna baglanilamadi: {son_hata}")
    finally:
        proc.terminate()
        proc.wait(timeout=10)
