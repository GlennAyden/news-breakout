from news_breakout.news.extract import lead_summary, fetch_article_text


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
