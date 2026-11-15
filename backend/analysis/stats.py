"""Scientific analysis engine: descriptive stats, climatology anomalies, OLS trend with
autocorrelation-adjusted CI, Mann-Kendall (seasonal and non-seasonal) with Sen's slope,
Pettitt change-point test, seasonal cycle, missing-data assessment.

Every function returns plain dicts so results are serialisable and traceable."""
from __future__ import annotations
import math
import numpy as np
import pandas as pd
from scipy import stats as sps


def to_series(points: list[dict]) -> pd.Series:
    if not points:
        return pd.Series(dtype=float)
    idx = pd.to_datetime([p["t"] for p in points])
    s = pd.Series([p["v"] for p in points], index=idx, dtype=float).sort_index()
    full = pd.date_range(s.index.min(), s.index.max(), freq="MS")
    return s.reindex(full)


def coverage(s: pd.Series) -> dict:
    n = len(s); miss = int(s.isna().sum())
    return {"n_expected": n, "n_valid": n - miss, "n_missing": miss,
            "pct_missing": round(100 * miss / n, 2) if n else None,
            "start": s.index.min().strftime("%Y-%m") if n else None,
            "end": s.index.max().strftime("%Y-%m") if n else None}


def descriptive(s: pd.Series) -> dict:
    v = s.dropna()
    if v.empty: return {}
    return {"mean": float(v.mean()), "std": float(v.std(ddof=1)) if len(v) > 1 else None,
            "min": float(v.min()), "min_at": v.idxmin().strftime("%Y-%m"),
            "max": float(v.max()), "max_at": v.idxmax().strftime("%Y-%m"),
            "median": float(v.median()), "n": int(len(v))}


def climatology(s: pd.Series, base_start: int | None = None, base_end: int | None = None) -> dict:
    """Monthly climatology from a baseline period (default: full record)."""
    v = s.dropna()
    if base_start and base_end:
        b = v[(v.index.year >= base_start) & (v.index.year <= base_end)]
        if len(b) >= 24: v = b
    clim = v.groupby(v.index.month).mean()
    sd = v.groupby(v.index.month).std(ddof=1)
    return {"baseline": [int(v.index.year.min()), int(v.index.year.max())],
            "monthly_mean": {int(m): float(x) for m, x in clim.items()},
            "monthly_std": {int(m): (float(x) if not math.isnan(x) else None) for m, x in sd.items()}}


def anomalies(s: pd.Series, clim: dict, z_threshold: float = 2.0) -> dict:
    mm = clim["monthly_mean"]; msd = clim["monthly_std"]
    an = s.copy()
    for i, (t, val) in enumerate(s.items()):
        m = int(t.month)
        an.iloc[i] = val - mm.get(m, np.nan) if pd.notna(val) else np.nan
    z = pd.Series(index=s.index, dtype=float)
    for i, t in enumerate(s.index):
        sd = msd.get(int(t.month)) or np.nan
        z.iloc[i] = an.iloc[i] / sd if sd and sd > 0 else np.nan
    flagged = [{"t": t.strftime("%Y-%m"), "anomaly": float(a), "z": float(zz)}
               for t, a, zz in zip(s.index, an, z) if pd.notna(zz) and abs(zz) >= z_threshold]
    flagged.sort(key=lambda d: -abs(d["z"]))
    return {"series": [{"t": t.strftime("%Y-%m"), "v": (None if pd.isna(a) else float(a))} for t, a in an.items()],
            "flagged": flagged[:25], "z_threshold": z_threshold, "n_flagged": len(flagged),
            "method": "value minus monthly climatological mean; z = anomaly / monthly std of baseline"}


def annual_means(s: pd.Series, min_months: int = 9) -> dict:
    g = s.groupby(s.index.year)
    out = []
    for y, grp in g:
        if grp.notna().sum() >= min_months:
            out.append({"t": f"{int(y)}", "v": float(grp.mean()), "n_months": int(grp.notna().sum())})
    return {"series": out, "rule": f"years with ≥{min_months} valid months"}


def ols_trend(points: list[dict], per: str = "year") -> dict:
    """OLS trend with standard CI and an effective-sample-size correction for lag-1 autocorrelation."""
    pts = [p for p in points if p.get("v") is not None]
    if len(pts) < 5: return {"available": False, "reason": "fewer than 5 points"}
    x = np.array([float(p["t"][:4]) + ((int(p["t"][5:7]) - 0.5) / 12 if len(p["t"]) >= 7 else 0.0) for p in pts])
    y = np.array([p["v"] for p in pts], dtype=float)
    res = sps.linregress(x, y)
    resid = y - (res.intercept + res.slope * x)
    r1 = float(np.corrcoef(resid[:-1], resid[1:])[0, 1]) if len(resid) > 3 else 0.0
    n = len(y); n_eff = n * (1 - r1) / (1 + r1) if abs(r1) < 1 else n
    n_eff = max(3.0, min(n, n_eff))
    se_adj = res.stderr * math.sqrt(n / n_eff)
    t_adj = res.slope / se_adj if se_adj > 0 else 0.0
    p_adj = 2 * sps.t.sf(abs(t_adj), df=max(1, n_eff - 2))
    ci = sps.t.ppf(0.975, df=max(1, n_eff - 2)) * se_adj
    span = x.max() - x.min()
    return {"available": True, "method": "ordinary least squares; CI/p adjusted for lag-1 autocorrelation (effective n)",
            "slope_per_year": float(res.slope), "slope_per_decade": float(res.slope * 10),
            "ci95_per_decade": [float((res.slope - ci) * 10), float((res.slope + ci) * 10)],
            "p_value": float(p_adj), "p_value_unadjusted": float(res.pvalue), "r_squared": float(res.rvalue ** 2),
            "lag1_autocorrelation": r1, "n": n, "n_effective": round(n_eff, 1),
            "total_change_over_record": float(res.slope * span), "span_years": float(span),
            "significant_05": bool(p_adj < 0.05), "start": pts[0]["t"], "end": pts[-1]["t"]}


def _mk_stat(x: np.ndarray):
    n = len(x); s = 0
    for i in range(n - 1):
        s += np.sum(np.sign(x[i + 1:] - x[i]))
    _, counts = np.unique(x, return_counts=True)
    var = (n * (n - 1) * (2 * n + 5) - np.sum(counts * (counts - 1) * (2 * counts + 5))) / 18.0
    return float(s), float(var)


def mann_kendall(points: list[dict], seasonal: bool = False) -> dict:
    """Mann-Kendall trend test (Hamed & Rao autocorrelation correction for the non-seasonal case,
    Hirsch–Slack seasonal variant when seasonal=True) with Sen's slope estimator."""
    pts = [p for p in points if p.get("v") is not None]
    if len(pts) < 8: return {"available": False, "reason": "fewer than 8 points"}
    if seasonal:
        by_m: dict[int, list] = {}
        for p in pts: by_m.setdefault(int(p["t"][5:7]), []).append(p["v"])
        S = 0.0; V = 0.0
        for vals in by_m.values():
            if len(vals) >= 3:
                s_, v_ = _mk_stat(np.array(vals)); S += s_; V += v_
        method = "seasonal Mann-Kendall (Hirsch & Slack), Sen's slope per season"
        slopes = []
        for m, vals in by_m.items():
            ts = [float(p["t"][:4]) for p in pts if int(p["t"][5:7]) == m]
            for i in range(len(vals)):
                for j in range(i + 1, len(vals)):
                    if ts[j] != ts[i]: slopes.append((vals[j] - vals[i]) / (ts[j] - ts[i]))
    else:
        x = np.array([p["v"] for p in pts], dtype=float)
        S, V = _mk_stat(x)
        n = len(x); r = pd.Series(x).rank().values
        d = r - np.polyval(np.polyfit(np.arange(n), r, 1), np.arange(n))
        acf = [1.0]
        for k in range(1, min(n // 4, 20)):
            c = np.corrcoef(d[:-k], d[k:])[0, 1]
            acf.append(float(c) if not math.isnan(c) else 0.0)
        corr = 1 + 2 / (n * (n - 1) * (n - 2)) * sum((n - k) * (n - k - 1) * (n - k - 2) * acf[k]
                                                     for k in range(1, len(acf)) if abs(acf[k]) > 1.96 / math.sqrt(n))
        V = V * max(corr, 1e-9)
        method = "Mann-Kendall with Hamed & Rao (1998) autocorrelation correction, Sen's slope"
        t = np.array([float(p["t"][:4]) + (int(p["t"][5:7]) - 0.5) / 12 if len(p["t"]) >= 7 else float(p["t"][:4]) for p in pts])
        slopes = [(x[j] - x[i]) / (t[j] - t[i]) for i in range(len(x)) for j in range(i + 1, len(x)) if t[j] != t[i]]
    if V <= 0: return {"available": False, "reason": "zero variance"}
    z = (S - 1) / math.sqrt(V) if S > 0 else (S + 1) / math.sqrt(V) if S < 0 else 0.0
    p = 2 * (1 - sps.norm.cdf(abs(z)))
    sen = float(np.median(slopes)) if slopes else None
    return {"available": True, "method": method, "S": S, "z": float(z), "p_value": float(p),
            "trend": "increasing" if p < 0.05 and z > 0 else "decreasing" if p < 0.05 and z < 0 else "no significant trend",
            "sen_slope_per_year": sen, "sen_slope_per_decade": (sen * 10 if sen is not None else None), "n": len(pts)}


def pettitt(points: list[dict]) -> dict:
    """Pettitt (1979) non-parametric single change-point test on annual means."""
    pts = [p for p in points if p.get("v") is not None]
    n = len(pts)
    if n < 10: return {"available": False, "reason": "fewer than 10 annual values"}
    x = np.array([p["v"] for p in pts])
    r = sps.rankdata(x); U = 2 * np.cumsum(r) - np.arange(1, n + 1) * (n + 1)
    K = int(np.argmax(np.abs(U))); Kstat = float(np.abs(U[K]))
    p = float(2 * math.exp(-6 * Kstat ** 2 / (n ** 3 + n ** 2)))
    return {"available": True, "method": "Pettitt test on annual means", "change_point": pts[K]["t"], "statistic": Kstat,
            "p_value": min(1.0, p), "significant_05": p < 0.05,
            "mean_before": float(np.mean(x[:K + 1])), "mean_after": float(np.mean(x[K + 1:])) if K + 1 < n else None}


def seasonal_profile(s: pd.Series) -> dict:
    v = s.dropna()
    if v.empty: return {}
    recent_cut = v.index.max().year - 9
    early = v[v.index.year < recent_cut]; late = v[v.index.year >= recent_cut]
    prof = {}
    for m in range(1, 13):
        e = early[early.index.month == m]; l = late[late.index.month == m]
        prof[m] = {"early_mean": float(e.mean()) if len(e) else None, "recent_mean": float(l.mean()) if len(l) else None,
                   "n_early": int(len(e)), "n_recent": int(len(l))}
    return {"split_year": int(recent_cut), "months": prof,
            "note": "early = all years before the last 10; recent = last 10 years"}


def analyse_variable(points: list[dict], unit: str, label: str, base_start=None, base_end=None) -> dict:
    s = to_series(points)
    if s.dropna().empty:
        return {"available": False, "reason": "no valid observations", "label": label, "unit": unit}
    cov = coverage(s); desc = descriptive(s); clim = climatology(s, base_start, base_end)
    an = anomalies(s, clim); ann = annual_means(s)
    ols = ols_trend(ann["series"]); mk = mann_kendall(points, seasonal=True); mk_ann = mann_kendall(ann["series"], seasonal=False)
    cp = pettitt(ann["series"]); seas = seasonal_profile(s)
    pct = None
    if ols.get("available") and desc.get("mean") and unit not in ("°C",):
        pct = 100 * ols["total_change_over_record"] / desc["mean"] if desc["mean"] else None
    return {"available": True, "label": label, "unit": unit, "coverage": cov, "descriptive": desc,
            "climatology": clim, "anomalies": an, "annual": ann, "trend_ols": ols,
            "trend_mk_seasonal": mk, "trend_mk_annual": mk_ann, "change_point": cp, "seasonal": seas,
            "percent_change_over_record": pct,
            "series": [{"t": t.strftime("%Y-%m"), "v": (None if pd.isna(v) else float(v))} for t, v in s.items()],
            "caveats": ["Anomalies are relative to this record's own monthly climatology unless a baseline was set.",
                        "Trend significance uses autocorrelation-adjusted tests; small samples lower power.",
                        "Correlation between variables is not evidence of causation."]}


def compare(a: dict, b: dict) -> dict:
    """Compare two analysed variables with identical definitions."""
    if not (a.get("available") and b.get("available")):
        return {"available": False}
    oa, ob = a["trend_ols"], b["trend_ols"]
    opp = (oa.get("available") and ob.get("available") and oa["significant_05"] and ob["significant_05"]
           and (oa["slope_per_decade"] > 0) != (ob["slope_per_decade"] > 0))
    sa, sb = to_series(a["series"]).dropna(), to_series(b["series"]).dropna()
    common = sa.index.intersection(sb.index)
    diff = (sa[common] - sb[common])
    w = None
    if len(common) >= 12:
        t = sps.ttest_rel(sa[common], sb[common])
        w = {"method": "paired t-test on common months (note: autocorrelation inflates significance)",
             "mean_difference_A_minus_B": float(diff.mean()), "t": float(t.statistic), "p_value": float(t.pvalue), "n_common_months": int(len(common))}
    return {"available": True, "mean_difference_A_minus_B": float(diff.mean()) if len(common) else None,
            "difference_test": w, "opposite_trends": bool(opp),
            "trend_A_per_decade": oa.get("slope_per_decade"), "trend_B_per_decade": ob.get("slope_per_decade"),
            "p_A": oa.get("p_value"), "p_B": ob.get("p_value"),
            "note": "Opposite trends are reported as an observation, not as evidence of any causal link."}