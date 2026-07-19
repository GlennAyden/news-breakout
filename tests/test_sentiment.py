from news_breakout.news.sentiment import classify, _normalize_label


def test_normalize_label_variants():
    assert _normalize_label("positive") == "positif"
    assert _normalize_label("LABEL positif") == "positif"
    assert _normalize_label("negative") == "negatif"
    assert _normalize_label("neutral") == "netral"
    assert _normalize_label("netral") == "netral"
    assert _normalize_label("") == ""
    assert _normalize_label("weird") == ""


def test_classify_confident_positive():
    runner = lambda texts: [{"label": "positive", "score": 0.92}]
    assert classify(["x"], runner=runner) == ["positif"]


def test_classify_confident_negative():
    runner = lambda texts: [{"label": "negative", "score": 0.81}]
    assert classify(["x"], runner=runner) == ["negatif"]


def test_classify_low_confidence_becomes_netral():
    runner = lambda texts: [{"label": "positive", "score": 0.40}]
    assert classify(["x"], runner=runner, min_confidence=0.6) == ["netral"]


def test_classify_neutral_label_is_netral():
    runner = lambda texts: [{"label": "neutral", "score": 0.99}]
    assert classify(["x"], runner=runner) == ["netral"]


def test_classify_runner_exception_degrades_to_empty():
    def boom(texts):
        raise RuntimeError("subprocess died")
    assert classify(["a", "b"], runner=boom) == ["", ""]


def test_classify_length_mismatch_degrades_to_empty():
    runner = lambda texts: [{"label": "positive", "score": 0.9}]  # 1 for 2 inputs
    assert classify(["a", "b"], runner=runner) == ["", ""]


def test_classify_empty_input_returns_empty_list():
    assert classify([], runner=lambda t: []) == []


def test_classify_malformed_item_non_dict():
    runner = lambda texts: ["oops", {"label": "positive", "score": 0.9}]
    assert classify(["a", "b"], runner=runner) == ["netral", "positif"]


def test_classify_malformed_item_non_numeric_score():
    runner = lambda texts: [{"label": "positive", "score": "high"}, {"label": "negative", "score": 0.85}]
    assert classify(["a", "b"], runner=runner) == ["netral", "negatif"]


def test_classify_score_exactly_at_threshold():
    runner = lambda texts: [{"label": "positive", "score": 0.6}]
    assert classify(["x"], runner=runner, min_confidence=0.6) == ["positif"]
