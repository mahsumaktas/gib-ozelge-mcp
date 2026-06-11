"""html_to_text ve find_snippet testleri - ornekler gercek GIB ozelge HTML'inden."""

from gib_ozelge_mcp.htmlutil import find_snippet, html_to_text

# Gercek bir ozelge description'inin kisaltilmis hali.
# Kaynak HTML'deki gibi tag'ler arasi gercek newline + girinti iceriyor
# (GIB API'sinin dondurdugu format) - bunlar ciktiya sizmamali.
OZELGE_HTML = (
    '<table class="MsoNormalTable" border="0">\n <tbody>\n  <tr>\n'
    '   <td>\n    <p class="MsoHeader" align="center">&nbsp;</p></td>\n'
    '   <td>\n    <p align="center"><strong>T.C.</strong></p><strong> </strong>\n'
    '    <p align="center"><strong>GELİR İDARESİ BAŞKANLIĞI</strong></p>\n'
    '    <p align="center"><strong>İzmir Defterdarlığı</strong></p></td>\n'
    "  </tr>\n </tbody>\n</table>\n"
    '<p class="MsoNormal"><strong>&nbsp;</strong></p>\n'
    "<table>\n <tbody>\n  <tr>\n"
    '   <td>\n    <p>Sayı</p></td>\n'
    '   <td>\n    <p align="center">:</p></td>\n'
    "   <td>\n    <p>E-66813766-140[38-2026/9]-321949</p></td>\n"
    '   <td>\n    <p align="right">30.04.2026</p></td>\n'
    "  </tr>\n </tbody>\n</table>\n"
    '<p class="MsoBodyText">İlgide kayıtlı özelge talep formunuzdan,'
    " noter harçlarına tabi olduğu anlaşılmaktadır.</p>\n"
    "<p>Bilgi edinilmesini rica ederim.</p>"
)


def test_tags_stripped_and_text_preserved():
    text = html_to_text(OZELGE_HTML)
    assert "<" not in text and ">" not in text
    assert "T.C." in text
    assert "GELİR İDARESİ BAŞKANLIĞI" in text
    assert "Bilgi edinilmesini rica ederim." in text


def test_turkish_chars_preserved():
    text = html_to_text(OZELGE_HTML)
    assert "İzmir Defterdarlığı" in text
    assert "özelge talep formunuzdan" in text


def test_nbsp_resolved_no_stray_chars():
    text = html_to_text(OZELGE_HTML)
    assert "\xa0" not in text
    assert "&nbsp;" not in text


def test_body_paragraphs_on_separate_lines():
    text = html_to_text(OZELGE_HTML)
    lines = [l for l in text.split("\n") if l.strip()]
    # Tablo disindaki govde paragraflari ayri satirlarda olmali
    govde = next(l for l in lines if "İlgide kayıtlı" in l)
    kapanis = next(l for l in lines if "rica ederim" in l)
    assert govde != kapanis


def test_table_row_cells_joined_with_space():
    # Ayni tr icindeki hucreler tek satirda boslukla ayrilmali:
    # "Sayı : E-... 30.04.2026" gibi
    text = html_to_text(OZELGE_HTML)
    assert "E-66813766-140[38-2026/9]-321949" in text
    assert "321949 30.04.2026" in text
    sayi_line = next(l for l in text.split("\n") if "Sayı" in l)
    assert "E-66813766" in sayi_line


def test_no_excess_blank_lines():
    text = html_to_text(OZELGE_HTML)
    assert "\n\n\n" not in text


def test_empty_and_none_input():
    assert html_to_text("") == ""
    assert html_to_text(None) == ""


def test_plain_text_passthrough():
    assert html_to_text("duz metin") == "duz metin"


# ---------------- find_snippet ----------------

UZUN_METIN = (
    "Bu uzun bir mevzuat metnidir. " * 30
    + "Burada konkordato projesi kapsaminda yapilan islemler anlatilmaktadir. "
    + "Devam eden metin. " * 30
)


def test_snippet_finds_match_with_context():
    s = find_snippet(UZUN_METIN, "konkordato", radius=60)
    assert s is not None
    assert "konkordato" in s
    assert len(s) <= 60 * 2 + len("konkordato") + 10  # iki yonlu baglam + elipsler


def test_snippet_turkish_case_insensitive():
    metin = "İlgide kayıtlı özelge talep formunuzda İSTİSNA uygulaması sorulmaktadır."
    assert find_snippet(metin, "istisna") is not None
    assert find_snippet(metin, "İSTİSNA") is not None
    assert find_snippet("Islak imza ve ıslak zemin", "ISLAK") is not None


def test_snippet_no_match_returns_none():
    assert find_snippet(UZUN_METIN, "bulunamayacakkelime") is None


def test_snippet_multiword_falls_back_to_first_word():
    # API AND/phrase aramasi yapsa da metinde ifade birebir olmayabilir;
    # ilk anlamli kelime uzerinden baglam dondurulur
    s = find_snippet(UZUN_METIN, "konkordato ilanı")
    assert s is not None and "konkordato" in s


def test_snippet_empty_inputs():
    assert find_snippet("", "x") is None
    assert find_snippet("metin", "") is None
