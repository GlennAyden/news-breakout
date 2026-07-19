from news_breakout.news.extract import lead_summary, fetch_article_text, strip_leading_title


# ---- strip_leading_title (pure) --------------------------------------------

def test_strip_leading_title_removes_headline_prefix():
    body = "Antam Tebar Dividen Rp120 Jakarta, CNBC - PT Aneka Tambang membagikan dividen."
    assert strip_leading_title(body, "Antam Tebar Dividen Rp120") == \
        "Jakarta, CNBC - PT Aneka Tambang membagikan dividen."


def test_strip_leading_title_case_insensitive_and_punctuation():
    body = "Habco Mau Private Placement? Jakarta - emiten logistik."
    assert strip_leading_title(body, "habco mau private placement?") == "Jakarta - emiten logistik."


def test_strip_leading_title_no_prefix_unchanged():
    body = "Jakarta - berita tanpa judul di depan."
    assert strip_leading_title(body, "Judul Lain") == "Jakarta - berita tanpa judul di depan."


def test_strip_leading_title_body_equals_title_returns_empty():
    assert strip_leading_title("Judul Saja", "Judul Saja") == ""


def test_strip_leading_title_empty_title_unchanged():
    assert strip_leading_title("Ada isi.", "") == "Ada isi."


def test_strip_leading_title_collapses_whitespace():
    assert strip_leading_title("  Judul   X   isinya di sini.", "Judul X") == "isinya di sini."


# ---- lead_summary (pure) ----------------------------------------------------

def test_lead_summary_takes_first_two_sentences():
    text = "Antam tebar dividen Rp120. Pembayaran awal Agustus. Rapat sudah setuju."
    out = lead_summary(text, 2)
    assert out == "Antam tebar dividen Rp120. Pembayaran awal Agustus."


def test_lead_summary_single_sentence_returns_it():
    assert lead_summary("Hanya satu kalimat saja", 2) == "Hanya satu kalimat saja"


def test_lead_summary_empty_returns_empty():
    assert lead_summary("", 2) == ""
    assert lead_summary(None, 2) == ""


def test_lead_summary_collapses_whitespace():
    assert lead_summary("  a\n\n  b.  c d.  ", 1) == "a b."


def test_lead_summary_truncates_to_max_chars():
    long = "kata " * 200  # one very long "sentence"
    out = lead_summary(long, 2, max_chars=50)
    assert len(out) <= 51 and out.endswith("…")


# ---- fetch_article_text (injected http_get + extractor) ---------------------

def test_fetch_article_text_extracts_body():
    out = fetch_article_text(
        "https://x/1",
        http_get=lambda u: "<html>..</html>",
        extractor=lambda html: "  isi artikel  ",
    )
    assert out == "isi artikel"


def test_fetch_article_text_http_failure_returns_empty():
    def boom(u):
        raise RuntimeError("net down")
    assert fetch_article_text("https://x/1", http_get=boom, extractor=lambda h: "x") == ""


def test_fetch_article_text_extractor_failure_returns_empty():
    def boom(html):
        raise ValueError("bad html")
    assert fetch_article_text("https://x/1", http_get=lambda u: "<html>", extractor=boom) == ""


def test_fetch_article_text_extractor_returns_none_becomes_empty():
    assert fetch_article_text("https://x/1", http_get=lambda u: "<html>",
                              extractor=lambda h: None) == ""
