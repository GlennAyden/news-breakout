from datetime import datetime
from zoneinfo import ZoneInfo

from news_breakout.news.idx_source import parse_disclosures

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 18, 9, 0, tzinfo=WIB)

SAMPLE = {
    "ResultCount": 2,
    "Replies": [
        {"pengumuman": {
            "Id2": "20260717-169",
            "NoPengumuman": "169/EXT/2026",
            "KodeEmiten": "PTPP ",
            "TglPengumuman": "2026-07-17T20:03:01",
            "JudulPengumuman": "Laporan Informasi atau Fakta Material Press Release",
        }},
        {"pengumuman": {
            "Id2": "20260717-170",
            "KodeEmiten": "BBRI",
            "TglPengumuman": "2026-07-17T15:00:00",
            "JudulPengumuman": "Pembagian Dividen Tunai",
        }},
        {"pengumuman": {"Id2": "", "JudulPengumuman": ""}},  # skipped: no id/title
    ],
}


def test_parse_extracts_fields_and_skips_empty():
    out = parse_disclosures(SAMPLE, now=NOW)
    assert len(out) == 2
    d0 = out[0]
    assert d0.ticker == "PTPP"           # trailing space stripped
    assert d0.title == "Laporan Informasi atau Fakta Material Press Release"
    assert d0.disclosure_id == "20260717-169"
    assert d0.timestamp.tzinfo is not None
    assert d0.timestamp.hour == 20
    assert out[1].ticker == "BBRI"


def test_parse_empty_replies():
    assert parse_disclosures({"Replies": []}, now=NOW) == []
    assert parse_disclosures({}, now=NOW) == []


def test_parse_tolerates_non_dict_records():
    data = {"Replies": [
        {"pengumuman": None},
        {"pengumuman": "oops"},
        "not-a-dict",
        {"pengumuman": {"Id2": "ok", "JudulPengumuman": "Dividen",
                        "TglPengumuman": "2026-07-17T10:00:00", "KodeEmiten": "BBRI"}},
    ]}
    out = parse_disclosures(data, now=NOW)
    assert len(out) == 1
    assert out[0].disclosure_id == "ok"


def test_parse_real_idx_field_shape():
    data = {"Replies": [{
        "pengumuman": {
            "Id2": "20260717-169", "NoPengumuman": "169",
            "Kode_Emiten": "PTPP                     ",
            "TglPengumuman": "2026-07-17T20:03:01",
            "JudulPengumuman": "Laporan Fakta Material",
        },
        "attachments": [
            {"FullSavePath": "https://www.idx.co.id/StaticData/x/a.pdf", "IsAttachment": False},
        ],
    }]}
    out = parse_disclosures(data, now=NOW)
    assert len(out) == 1
    assert out[0].ticker == "PTPP"                                   # Kode_Emiten, stripped
    assert out[0].url == "https://www.idx.co.id/StaticData/x/a.pdf"  # PDF attachment link
