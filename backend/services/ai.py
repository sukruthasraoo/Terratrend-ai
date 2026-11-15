"""TerraTrend Intelligence. The interpreter never sees raw user text alone: it is
always handed the computed statistics and must cite them. If no ANTHROPIC_API_KEY is
set, a deterministic rule-based interpreter builds the explanation from the same numbers."""
import json, httpx
from ..config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

SYSTEM = """You are TerraTrend Intelligence, a scientific interpreter inside an Earth-observation platform.
You are given an investigation context (location, variables, datasets) and the exact statistics computed by the platform's
analysis engine. Answer the user's question using ONLY those numbers. Rules:
- Never invent measurements, trends, p-values, dataset names or citations. If something is not in the provided data, say it is unavailable.
- Distinguish anomalies from trends, correlation from causation, reanalysis/model products from direct satellite observations.
- Quote slopes with units and the confidence interval / p-value given. Say whether a trend is statistically significant at 0.05.
- Possible explanations must be labelled as hypotheses, not findings.
- End with 'Uncertainty & limitations' and 'Sources' sections listing the datasets in the context.
Write in concise, plain scientific prose with short headed sections: Discovery, Location & period, Measured results, Statistical findings, Interpretation, Possible explanations (hypotheses), Uncertainty & limitations, Sources."""


def _fmt(x, nd=2):
    return "n/a" if x is None else f"{x:.{nd}f}"


def rule_based(question: str, context: dict, results: dict) -> str:
    loc = context.get("name", "the selected location")
    lines = [f"## Discovery: environmental record for {context.get('short_name', loc)}",
             f"**Location & period.** {loc}. Aggregation: {results.get('aggregation', 'n/a')}.",
             "", "**Measured results & statistical findings.**"]
    any_var = False
    for var, r in results.get("variables", {}).items():
        if not r.get("available"):
            lines.append(f"- {r.get('label', var)}: unavailable ({r.get('reason', 'no data')}).")
            continue
        any_var = True
        d, o, mk, cov = r["descriptive"], r["trend_ols"], r["trend_mk_seasonal"], r["coverage"]
        u = r["unit"]
        s = f"- **{r['label']}** ({cov['start']} to {cov['end']}, {cov['pct_missing']}% missing): mean {_fmt(d['mean'])} {u}, range {_fmt(d['min'])}–{_fmt(d['max'])} {u}."
        if o.get("available"):
            sig = "statistically significant" if o["significant_05"] else "not statistically significant"
            s += (f" OLS trend {_fmt(o['slope_per_decade'], 3)} {u}/decade (95% CI {_fmt(o['ci95_per_decade'][0], 3)} to "
                  f"{_fmt(o['ci95_per_decade'][1], 3)}; p = {_fmt(o['p_value'], 3)}, {sig}, autocorrelation-adjusted).")
        if mk.get("available"):
            s += f" Seasonal Mann-Kendall: {mk['trend']} (p = {_fmt(mk['p_value'], 3)}; Sen's slope {_fmt(mk['sen_slope_per_decade'], 3)} {u}/decade)."
        cp = r.get("change_point", {})
        if cp.get("available") and cp.get("significant_05"):
            s += f" Pettitt test suggests a shift around {cp['change_point']} (mean {_fmt(cp['mean_before'])} → {_fmt(cp['mean_after'])} {u}, p = {_fmt(cp['p_value'], 3)})."
        fl = r["anomalies"]["flagged"][:3]
        if fl:
            s += " Largest anomalies: " + "; ".join(f"{f['t']} ({'+' if f['anomaly']>0 else ''}{_fmt(f['anomaly'])} {u}, z = {_fmt(f['z'], 1)})" for f in fl) + "."
        lines.append(s)
    if not any_var:
        lines.append("No variable in this investigation currently has data, so no interpretation can be made.")
    lines += ["", "**Interpretation.** The statements above are direct readings of the computed statistics. A trend is only treated as real where the autocorrelation-adjusted p-value is below 0.05; otherwise the record is consistent with no change.",
              "", "**Possible explanations (hypotheses, not findings).** Candidate drivers for changes of this kind include regional warming, land-use and urban growth, variability in monsoon or ENSO phases, and changes in aerosol loading. None of these is tested here; establishing attribution needs dedicated studies.",
              "", "**Uncertainty & limitations.** NASA POWER is a reanalysis-based product on a ~0.5° grid, so it represents grid-cell means rather than station observations and can differ from local measurements, especially for precipitation. Missing months reduce statistical power. Comparisons between regions use a paired test whose p-value is inflated by autocorrelation.",
              "", "**Sources.** " + "; ".join(results.get("sources", ["NASA POWER (https://power.larc.nasa.gov/)"])),
              "", "_Interpreter: rule-based (set ANTHROPIC_API_KEY to enable the Claude-powered interpreter)._"]
    return "\n".join(lines)


async def interpret(question: str, context: dict, results: dict) -> dict:
    if not ANTHROPIC_API_KEY:
        return {"engine": "rule-based", "answer": rule_based(question, context, results)}
    slim = json.loads(json.dumps(results, default=str))
    for v in slim.get("variables", {}).values():   # strip bulky series before sending
        for k in ("series", "anomalies"):
            if k in v and isinstance(v[k], dict): v[k] = {kk: vv for kk, vv in v[k].items() if kk != "series"}
            elif k in v: v.pop(k, None)
    body = {"model": ANTHROPIC_MODEL, "max_tokens": 1500, "system": SYSTEM,
            "messages": [{"role": "user", "content": f"Question: {question}\n\nInvestigation context:\n{json.dumps(context, default=str)[:4000]}\n\nComputed statistics (authoritative):\n{json.dumps(slim, default=str)[:60000]}"}]}
    try:
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post("https://api.anthropic.com/v1/messages", json=body,
                             headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json().get("content", []))
            return {"engine": ANTHROPIC_MODEL, "answer": text}
    except Exception as e:
        return {"engine": "rule-based (API error: %s)" % str(e)[:120], "answer": rule_based(question, context, results)}