from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from news_breakout.news.portal import PortalNews
from news_breakout.news.portal_html import (
    _clean,
    _parse_indo_date,
    parse_bisnis,
    parse_emitennews,
    parse_investor,
)

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 18, 12, 0, tzinfo=WIB)


# ---- _clean -----------------------------------------------------------------

def test_clean_strips_tags():
    assert _clean("<p>Hello <b>World</b></p>") == "Hello World"


def test_clean_decodes_named_entities():
    assert _clean("Rp1&nbsp;triliun &amp; naik &lt;signifikan&gt; &quot;besar&quot;&#39;s") == \
        'Rp1 triliun & naik <signifikan> "besar"\'s'


def test_clean_decodes_numeric_entities():
    assert _clean("Astra&#8230;") == "Astra…"
    assert _clean("A&#x26;B") == "A&B"


def test_clean_collapses_whitespace_and_strips():
    assert _clean("  <p>foo</p>\n\n   <p>bar</p>  ") == "foo bar"


# ---- _parse_indo_date --------------------------------------------------------

def test_parse_indo_date_baru_saja_returns_now():
    assert _parse_indo_date("baru saja", NOW) == NOW


def test_parse_indo_date_relative_jam_yang_lalu():
    dt = _parse_indo_date("3 jam yang lalu", NOW)
    assert dt == NOW - timedelta(hours=3)


def test_parse_indo_date_relative_menit_yang_lalu():
    dt = _parse_indo_date("45 menit yang lalu", NOW)
    assert dt == NOW - timedelta(minutes=45)


def test_parse_indo_date_relative_detik_yang_lalu():
    dt = _parse_indo_date("30 detik yang lalu", NOW)
    assert dt == NOW - timedelta(seconds=30)


def test_parse_indo_date_relative_hari_yang_lalu():
    dt = _parse_indo_date("2 hari yang lalu", NOW)
    assert dt == NOW - timedelta(days=2)


def test_parse_indo_date_relative_minggu_yang_lalu():
    dt = _parse_indo_date("1 minggu yang lalu", NOW)
    assert dt == NOW - timedelta(weeks=1)


def test_parse_indo_date_absolute_indo_month_pipe_time():
    dt = _parse_indo_date("17 Juli 2026 | 15:30", NOW)
    assert dt == datetime(2026, 7, 17, 15, 30, tzinfo=WIB)


def test_parse_indo_date_absolute_indo_month_comma_time():
    dt = _parse_indo_date("17 Jul 2026, 15:30", NOW)
    assert dt == datetime(2026, 7, 17, 15, 30, tzinfo=WIB)


def test_parse_indo_date_absolute_slash_format():
    dt = _parse_indo_date("17/07/2026, 15:30", NOW)
    assert dt == datetime(2026, 7, 17, 15, 30, tzinfo=WIB)


def test_parse_indo_date_unparseable_returns_now():
    assert _parse_indo_date("tanggal tidak diketahui", NOW) == NOW


def test_parse_indo_date_empty_returns_now():
    assert _parse_indo_date("", NOW) == NOW


# ---- parse_emitennews ---------------------------------------------------------

EMITEN_HTML = """
<div class="search-result-wrapper">
    <a href="https://emitennews.com/news/pengendali-koka-tanda-tangani-jual-beli-saham" class="news-card-2 search-result-item">
        <div class="news-card-2-img">
            <img src="https://ap-south-1.linodeobjects.com/thumb1.jpeg" alt="Pengendali KOKA Tanda Tangani Jual Beli Saham" title="Ilustrasi">
        </div>
        <div class="news-card-2-content title-category">
            <p class="fs-16">Pengendali KOKA Tanda Tangani Jual Beli Saham</p>
            <div class="label">
                <span class="small">3 jam yang lalu</span>
            </div>
        </div>
    </a>
    <a href="https://emitennews.com/news/tempo-scan-pacific-tspc-ungkap-rencana" class="news-card-2 search-result-item">
        <div class="news-card-2-img">
            <img src="https://ap-south-1.linodeobjects.com/thumb2.jpg" alt="Tempo Scan Pacific" title="Suasana">
        </div>
        <div class="news-card-2-content title-category">
            <p class="fs-16">Tempo Scan Pacific (TSPC) Ungkap Rencana Bentuk Perusahaan Patungan</p>
            <div class="label">
                <span class="small">7 jam yang lalu</span>
            </div>
        </div>
    </a>
</div>
"""

EMITEN_HTML_MISSING_TITLE = """
<a href="https://emitennews.com/news/tanpa-judul" class="news-card-2 search-result-item">
    <div class="news-card-2-img">
        <img src="https://example.com/thumb.jpg" alt="x">
    </div>
    <div class="news-card-2-content title-category">
        <div class="label">
            <span class="small">1 jam yang lalu</span>
        </div>
    </div>
</a>
"""


def test_parse_emitennews_extracts_title_link_and_relative_date():
    items = parse_emitennews(EMITEN_HTML, "emitennews.com", now=NOW)
    assert len(items) == 2
    first = items[0]
    assert isinstance(first, PortalNews)
    assert first.title == "Pengendali KOKA Tanda Tangani Jual Beli Saham"
    assert first.url == "https://emitennews.com/news/pengendali-koka-tanda-tangani-jual-beli-saham"
    assert first.source == "emitennews.com"
    assert first.timestamp == NOW - timedelta(hours=3)
    second = items[1]
    assert second.title == "Tempo Scan Pacific (TSPC) Ungkap Rencana Bentuk Perusahaan Patungan"
    assert second.timestamp == NOW - timedelta(hours=7)


def test_parse_emitennews_skips_items_without_title():
    items = parse_emitennews(EMITEN_HTML_MISSING_TITLE, "emitennews.com", now=NOW)
    assert items == []


def test_parse_emitennews_defaults_to_now_when_no_date():
    html = EMITEN_HTML_MISSING_TITLE.replace(
        '<div class="label">\n            <span class="small">1 jam yang lalu</span>\n        </div>',
        '<p class="fs-16">Tanpa Tanggal</p>',
    )
    items = parse_emitennews(html, "emitennews.com", now=NOW)
    assert len(items) == 1
    assert items[0].timestamp == NOW


# ---- parse_bisnis --------------------------------------------------------------

BISNIS_HTML = """
<div class="artItem">
  <div class="art--col">
    <a href="https://market.bisnis.com/read/20260718/7/1989092/intip-metodologi-anyar-msci" class="artLink artLinkImg">
      <div class="artImg"><img src="x.jpg" alt="Intip Metodologi"></div>
    </a>
    <div class="artContent">
      <div class="artContentWrap">
        <div class="artChannel"><a href="https://market.bisnis.com/x">Bursa &amp; Saham</a></div>
        <div class="artDate">
          3 jam yang lalu
        </div>
      </div>
      <a href="https://market.bisnis.com/read/20260718/7/1989092/intip-metodologi-anyar-msci" class="artLink">
        <h4 class="artTitle">
          Intip Metodologi Anyar MSCI Jegal Saham dengan Volatilitas Tinggi
        </h4>
      </a>
    </div>
  </div>
</div>
<div class="artItem">
  <div class="art--col">
    <a href="https://market.bisnis.com/read/20260718/7/1989072/bmri-bbca-hingga-bbri" class="artLink artLinkImg">
      <div class="artImg"><img src="y.jpg" alt="BMRI BBCA"></div>
    </a>
    <div class="artContent">
      <div class="artContentWrap">
        <div class="artChannel"><a href="https://market.bisnis.com/y">Bursa &amp; Saham</a></div>
        <div class="artDate">
          7 jam yang lalu
        </div>
      </div>
      <a href="https://market.bisnis.com/read/20260718/7/1989072/bmri-bbca-hingga-bbri" class="artLink">
        <h4 class="artTitle">
          BMRI, BBCA hingga BBRI Sokong IHSG Sepekan Melesat 4,24%
        </h4>
      </a>
    </div>
  </div>
</div>
"""


def test_parse_bisnis_extracts_title_link_and_date():
    items = parse_bisnis(BISNIS_HTML, "market.bisnis.com", now=NOW)
    assert len(items) == 2
    first = items[0]
    assert isinstance(first, PortalNews)
    assert first.title == "Intip Metodologi Anyar MSCI Jegal Saham dengan Volatilitas Tinggi"
    assert first.url == "https://market.bisnis.com/read/20260718/7/1989092/intip-metodologi-anyar-msci"
    assert first.source == "market.bisnis.com"
    assert first.timestamp == NOW - timedelta(hours=3)
    second = items[1]
    assert second.title == "BMRI, BBCA hingga BBRI Sokong IHSG Sepekan Melesat 4,24%"
    assert second.timestamp == NOW - timedelta(hours=7)


BISNIS_SECONDARY_LIST_HTML = """
<a href="https://market.bisnis.com/read/20260718/1/1/a" class="artLink"><h4 class="artTitle">Judul Bersih A</h4></a>
<a href="https://market.bisnis.com/read/20260718/2/2/b" class="artLink"><h4 class="artTitle">Judul Bersih B</h4><div class="artDate">2 jam yang lalu</div></a>
"""


def test_parse_bisnis_secondary_list_template_does_not_swallow_html():
    items = parse_bisnis(BISNIS_SECONDARY_LIST_HTML, "market.bisnis.com", now=NOW)
    assert len(items) == 2
    assert items[0].title == "Judul Bersih A"
    assert items[1].title == "Judul Bersih B"
    assert len(items[0].title) <= 20
    assert len(items[1].title) <= 20


def test_parse_bisnis_defaults_to_now_when_no_date_in_window():
    html = """
<a href="https://market.bisnis.com/read/1/no-date" class="artLink">
    <h4 class="artTitle">Berita Tanpa Tanggal</h4>
</a>
"""
    items = parse_bisnis(html, "market.bisnis.com", now=NOW)
    assert len(items) == 1
    assert items[0].timestamp == NOW


# ---- parse_investor -------------------------------------------------------------

INVESTOR_HTML = """
<div class="col-4 position-relative">
  <a href="/market/447045/dupoin-futures-resmikan-head-office-baru" class="stretched-link">
    <div class="ratio ratio-16x9 rounded-3 overflow-hidden mb-2">
      <img src="https://img2.beritasatu.com/thumb1.webp" class="lazy" alt="Dupoin Futures Resmikan Head Office Baru">
    </div>
  </a>
  <h3 class="h6 text-white text-truncate-2-lines">Dupoin Futures Resmikan Head Office Baru</h3>
</div>
<div class="col-4 position-relative">
  <a href="/market/447044/pgeo-tanggapi-berita-soal-geo-dipa" class="stretched-link">
    <div class="ratio ratio-16x9 rounded-3 overflow-hidden mb-2">
      <img src="https://img2.beritasatu.com/thumb2.webp" class="lazy" alt="PGEO Tanggapi Berita soal Geo Dipa">
    </div>
  </a>
  <h3 class="h6 text-white text-truncate-2-lines">PGEO Tanggapi Berita soal Geo Dipa</h3>
</div>
<div class="col-4 position-relative">
  <a href="/finance/447036/jamkrindo-perluas-akses-literasi-anak" class="stretched-link">
    <div class="ratio ratio-16x9 rounded-3 overflow-hidden mb-2">
      <img src="https://img2.beritasatu.com/thumb3.webp" class="lazy" alt="Jamkrindo Perluas Akses Literasi Anak">
    </div>
  </a>
  <h3 class="h6 text-white text-truncate-2-lines">Jamkrindo Perluas Akses Literasi Anak</h3>
</div>
"""


def test_parse_investor_extracts_title_from_img_alt_and_prepends_host():
    items = parse_investor(INVESTOR_HTML, "investor.id", now=NOW)
    assert len(items) == 2
    first = items[0]
    assert isinstance(first, PortalNews)
    assert first.title == "Dupoin Futures Resmikan Head Office Baru"
    assert first.url == "https://investor.id/market/447045/dupoin-futures-resmikan-head-office-baru"
    assert first.source == "investor.id"
    assert first.timestamp == NOW
    second = items[1]
    assert second.title == "PGEO Tanggapi Berita soal Geo Dipa"
    assert second.url == "https://investor.id/market/447044/pgeo-tanggapi-berita-soal-geo-dipa"


def test_parse_investor_ignores_non_market_paths():
    html = """
<a href="/finance/447036/jamkrindo-perluas-akses-literasi-anak" class="stretched-link">
  <img src="x.webp" alt="Jamkrindo Perluas Akses Literasi Anak">
</a>
"""
    items = parse_investor(html, "investor.id", now=NOW)
    assert items == []
