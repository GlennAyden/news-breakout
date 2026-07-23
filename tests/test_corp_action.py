from news_breakout.news.corp_action import (
    CATEGORY_PRIORITY, CAUTION_LINES, classify_corp_action)


def test_classifies_each_category():
    cases = [
        ("rights_issue", "PADI ajukan pencatatan saham baru hasil rights issue"),
        ("rights_issue", "Jadwal HMETD dan pelaksanaan penambahan modal"),
        ("private_placement", "HATM siapkan private placement 800 juta saham"),
        ("akuisisi", "BTN incar akuisisi kredit konsumer bank lain"),
        ("dividen", "ANTM bagikan dividen Rp5,05 triliun"),
        ("buyback", "Astra International ASII restu buyback saham Rp8 triliun"),
    ]
    for expected, title in cases:
        assert classify_corp_action(title) == expected, title


def test_routine_titles_return_none():
    for title in [
        "Laporan Bulanan Registrasi Pemegang Efek",
        "Laporan Hasil Pelaksanaan Konversi ESOP MSOP",
        "Pemanggilan Rapat Umum Pemegang Saham Luar Biasa",
        "Penyampaian Bukti Iklan",
        "",
    ]:
        assert classify_corp_action(title) is None, title


def test_priority_order_rights_beats_dividen_in_mixed_title():
    # a title mentioning both must classify as the more-material rights_issue
    assert classify_corp_action("Rights issue untuk danai dividen") == "rights_issue"
    assert CATEGORY_PRIORITY.index("rights_issue") < CATEGORY_PRIORITY.index("dividen")


def test_caution_lines_cover_bearish_only():
    assert set(CAUTION_LINES) == {"rights_issue", "private_placement", "akuisisi", "dividen"}
    assert "buyback" not in CAUTION_LINES
    assert CAUTION_LINES["rights_issue"].startswith("⚠️ Peringatan: rights issue")


def test_word_boundary_no_false_positive():
    # "dividennya" still matches (enclitic) but an unrelated substring must not
    assert classify_corp_action("Pembagian dividennya tahun ini") == "dividen"
    assert classify_corp_action("Laporan kinerja triwulan") is None
