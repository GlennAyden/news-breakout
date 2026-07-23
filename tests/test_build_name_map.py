import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "build_name_map", Path("scripts/build_name_map.py")
)
bnm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bnm)


def test_normalize_strips_legal_words_and_punct():
    assert bnm.normalize_name("PT Aneka Tambang Tbk.") == "aneka tambang"
    assert bnm.normalize_name("PT Timah (Persero) Tbk") == "timah"


def test_build_map_skips_short_names_and_missing_tickers():
    records = [
        {"KodeEmiten": "ANTM", "NamaEmiten": "PT Aneka Tambang Tbk"},
        {"KodeEmiten": "ABC", "NamaEmiten": "PT AB Tbk"},        # name < 4 chars after strip
        {"KodeEmiten": "", "NamaEmiten": "PT Tanpa Kode Tbk"},   # no ticker
        {"Kode_Emiten": "TINS", "Nama_Emiten": "PT Timah Tbk"},  # alternate keys
    ]
    m = bnm.build_map(records)
    assert m == {"aneka tambang": "ANTM", "timah": "TINS"}
