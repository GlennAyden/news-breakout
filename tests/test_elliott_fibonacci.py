from news_breakout.signals.elliott.fibonacci import (
    retracements, extensions, projection, nearest_ratio, confluence,
)


def test_retracements_math():
    r = retracements(100.0, 200.0)          # leg of 100
    assert r[0.5] == 150.0
    assert abs(r[0.618] - 138.2) < 1e-9
    assert abs(r[0.382] - 161.8) < 1e-9


def test_extensions_math():
    e = extensions(100.0, 200.0)
    assert e[1.618] == 261.8
    assert e[2.0] == 300.0


def test_projection_measured_move():
    # wave A=100->140 (b-a=40), project 1.0 off c=130 -> 170
    assert projection(100.0, 140.0, 130.0, 1.0) == 170.0


def test_nearest_ratio_classifies_a_retrace():
    # price 138 on a 100->200 leg sits at ~0.62 retrace
    assert nearest_ratio(138.0, 100.0, 200.0, (0.5, 0.618, 0.786), tol=0.03) == 0.618
    # price far from any ratio -> None
    assert nearest_ratio(175.0, 100.0, 200.0, (0.5, 0.618), tol=0.02) is None


def test_confluence_counts_weighted_factors():
    score, factors = confluence(
        150.0, structure=150.4, sma=149.6, round_step=50.0,
        other_levels=(150.2,), tol=1.0,
    )
    assert score >= 5           # structure(2)+sma(2)+round(1)+cluster(2) within tol
    assert "structure" in factors and "sma" in factors
