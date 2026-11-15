"""Run: python tests/test_analysis.py"""
import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from backend.analysis.stats import analyse_variable, compare

def synth(slope, n_years=30, seed=0, noise=0.4):
    rng = np.random.default_rng(seed)
    return [{"t": f"{1990 + i // 12}-{i % 12 + 1:02d}", "v": 20 + 5 * math.sin(i / 12 * 2 * math.pi) + slope * i / 12 + rng.normal(0, noise)} for i in range(n_years * 12)]

def test_trend_recovered():
    r = analyse_variable(synth(0.05), "°C", "T")
    assert r["available"]
    assert abs(r["trend_ols"]["slope_per_decade"] - 0.5) < 0.15
    assert r["trend_ols"]["significant_05"]
    assert r["trend_mk_seasonal"]["trend"] == "increasing"

def test_no_trend_not_flagged():
    r = analyse_variable(synth(0.0, seed=3), "mm/day", "P")
    assert not r["trend_ols"]["significant_05"]

def test_missing_data_reported():
    pts = synth(0.0); del pts[100:130]
    r = analyse_variable(pts, "°C", "T")
    assert r["coverage"]["n_missing"] == 30

def test_opposite_trends():
    a = analyse_variable(synth(0.05, seed=1), "°C", "T"); b = analyse_variable(synth(-0.05, seed=2), "°C", "T")
    assert compare(a, b)["opposite_trends"] is True

if __name__ == "__main__":
    for f in (test_trend_recovered, test_no_trend_not_flagged, test_missing_data_reported, test_opposite_trends):
        f(); print("ok", f.__name__)