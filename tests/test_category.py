from news_breakout.news.category import drop_category

DROPS = ["tata_kelola", "pasar_opini"]


def test_tata_kelola_titles_dropped():
    for title in [
        "RUPST WIRG kembali buntu, tak satu agenda diputuskan",
        "Susunan direksi dan komisaris BRI terbaru hasil RUPSLB",
        "Direktur PGAS tiba-tiba borong saham di harga Rp1.490",
        "BTN RUPSLB September 2026, ada agenda perubahan pengurus",
    ]:
        assert drop_category(title, DROPS) == "tata_kelola", title


def test_pasar_opini_titles_dropped():
    for title in [
        "Intip 5 rekomendasi saham yang potensi kasih cuan hari ini",
        "Penyebab IHSG melesat 1% di akhir perdagangan",
        "Wall Street loyo, Nasdaq anjlok 1,4%",
        "Analis pasang target harga baru untuk BBCA",
    ]:
        assert drop_category(title, DROPS) == "pasar_opini", title


def test_corp_action_and_plain_titles_kept():
    for title in [
        "ANTM bagikan dividen Rp5,05 triliun",
        "ASII kantongi restu buyback saham Rp8 triliun",
        "TPIA ungkap progres proyek CA-EDC capai 72 persen",
        "Laba BBTN meroket 40,8% di paruh pertama 2026",
    ]:
        assert drop_category(title, DROPS) is None, title


def test_empty_drop_list_disables_filter():
    assert drop_category("RUPST WIRG kembali buntu", []) is None


def test_unknown_category_name_ignored():
    assert drop_category("RUPST WIRG kembali buntu", ["nonexistent"]) is None
