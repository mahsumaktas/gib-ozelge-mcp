"""GIB ozelge description HTML'ini duz metne cevirir (stdlib, ek bagimlilik yok)."""

from __future__ import annotations

import re
from html.parser import HTMLParser

# Satir sonu ureten elementler
_NEWLINE_TAGS = {
    "p", "div", "table", "tr", "li", "ul", "ol", "br",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
}
# Hucre icerikleri arasina bosluk koyan elementler
_SPACE_TAGS = {"td", "th"}


class _TextExtractor(HTMLParser):
    """Tablo hucresi (td/th) icindeki bloklar bosluga, disindakiler satir sonuna donusur.

    Boylece "Sayı | : | E-... | 30.04.2026" gibi meta satirlari tek satirda kalir.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._cell_depth = 0

    def _break(self) -> None:
        self.parts.append(" " if self._cell_depth > 0 else "\n")

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SPACE_TAGS:
            self._cell_depth += 1
            self.parts.append(" ")
        elif tag in ("table", "tr"):
            self.parts.append("\n")
        elif tag in _NEWLINE_TAGS:
            self._break()

    def handle_endtag(self, tag: str) -> None:
        if tag in _SPACE_TAGS:
            self._cell_depth = max(0, self._cell_depth - 1)
            self.parts.append(" ")
        elif tag in ("table", "tr"):
            self.parts.append("\n")
        elif tag in _NEWLINE_TAGS:
            self._break()

    def handle_data(self, data: str) -> None:
        # Kaynak HTML'deki ham satir sonlari anlamsizdir; satir yapisini
        # yalnizca block tag'ler belirler.
        self.parts.append(data.replace("\n", " ").replace("\r", " "))


def html_to_text(raw: str | None) -> str:
    if not raw:
        return ""
    parser = _TextExtractor()
    parser.feed(raw)
    parser.close()
    text = "".join(parser.parts)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _tr_fold(s: str) -> str:
    """Turkce buyuk/kucuk harf esitligi icin katlama (İ->i, I->ı)."""
    return s.replace("İ", "i").replace("I", "ı").lower()


def find_snippet(text: str, query: str, radius: int = 150) -> str | None:
    """Sorgunun metinde ilk gectigi yerin cevresini dondurur; eslesme yoksa None.

    Cok kelimeli sorgu birebir bulunamazsa ilk anlamli (3+ harf) kelimeye duser.
    """
    if not text or not query:
        return None
    folded_text = _tr_fold(text)
    adaylar = [query.strip()]
    adaylar += [w for w in query.split() if len(w) >= 3]
    for aday in adaylar:
        idx = folded_text.find(_tr_fold(aday))
        if idx != -1:
            start = max(0, idx - radius)
            end = min(len(text), idx + len(aday) + radius)
            snippet = " ".join(text[start:end].split())
            prefix = "..." if start > 0 else ""
            suffix = "..." if end < len(text) else ""
            return f"{prefix}{snippet}{suffix}"
    return None
