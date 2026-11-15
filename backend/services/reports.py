"""Report generation: JSON, CSV, GeoJSON, PDF (reportlab)."""
import csv, io, json, uuid
from datetime import datetime, timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from ..config import REPORTS_DIR

def _f(x, nd=3):
    return "n/a" if x is None else (f"{x:.{nd}f}" if isinstance(x, (int, float)) else str(x))

def build(context: dict, results: dict, ai_text: str | None, title: str | None = None) -> dict:
    rid = uuid.uuid4().hex[:12]
    created = datetime.now(timezone.utc).isoformat()
    title = title or f"Environmental investigation: {context.get('short_name') or context.get('name')}"
    payload = {"report_id": rid, "title": title, "created": created, "context": context, "results": results,
               "ai_interpretation": ai_text,
               "methodology": ["Monthly values retrieved from NASA POWER (point or area-mean over POWER grid cells).",
                               "Monthly climatology computed from the record; anomalies = value − climatology; z = anomaly / monthly std.",
                               "Annual means require ≥9 valid months. OLS trend on annual means with lag-1 autocorrelation-adjusted CI/p.",
                               "Seasonal Mann-Kendall (Hirsch & Slack) on monthly values with Sen's slope; Pettitt change-point on annual means.",
                               "No causal attribution is performed."]}
    (REPORTS_DIR / f"{rid}.json").write_text(json.dumps(payload, default=str, indent=1))
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(["variable", "unit", "month", "value", "anomaly"])
    for var, r in results.get("variables", {}).items():
        if not r.get("available"): continue
        an = {a["t"]: a["v"] for a in r["anomalies"]["series"]}
        for p in r["series"]:
            w.writerow([var, r["unit"], p["t"], "" if p["v"] is None else p["v"], "" if an.get(p["t"]) is None else an.get(p["t"])])
    (REPORTS_DIR / f"{rid}.csv").write_text(buf.getvalue())
    geom = context.get("geometry") or {"type": "Point", "coordinates": [context["lon"], context["lat"]]}
    gj = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": geom,
          "properties": {"name": context.get("name"), "report_id": rid, "bbox": context.get("bbox")}}]}
    (REPORTS_DIR / f"{rid}.geojson").write_text(json.dumps(gj))
    _pdf(rid, payload)
    return {"report_id": rid, "title": title, "created": created,
            "files": {fmt: f"/api/reports/{rid}/{fmt}" for fmt in ("json", "csv", "geojson", "pdf")}}

def _pdf(rid, p):
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9, leading=12)
    h = ParagraphStyle("h", parent=ss["Heading2"], fontSize=12, spaceBefore=8)
    doc = SimpleDocTemplate(str(REPORTS_DIR / f"{rid}.pdf"), pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm)
    c = p["context"]; el = [Paragraph(p["title"], ss["Title"]),
          Paragraph(f"TerraTrend AI · report {rid} · generated {p['created']}", body), Spacer(1, 6),
          Paragraph("1. Location", h),
          Paragraph(f"{c.get('name')}<br/>Centroid {c.get('lat'):.4f}, {c.get('lon'):.4f} · bbox {c.get('bbox')} · aggregation: {p['results'].get('aggregation','n/a')}", body),
          Paragraph("2. Datasets", h), Paragraph("; ".join(p["results"].get("sources", [])), body),
          Paragraph("3. Statistical analysis", h)]
    rows = [["Variable", "Period", "Missing %", "Mean", "OLS /decade", "95% CI", "p (adj)", "MK seasonal", "Sen /decade"]]
    for var, r in p["results"].get("variables", {}).items():
        if not r.get("available"):
            rows.append([r.get("label", var), "unavailable", "", "", "", "", "", "", ""]); continue
        o, mk, cv, d = r["trend_ols"], r["trend_mk_seasonal"], r["coverage"], r["descriptive"]
        rows.append([f"{r['label']} ({r['unit']})", f"{cv['start']}–{cv['end']}", _f(cv["pct_missing"], 1), _f(d["mean"], 2),
                     _f(o.get("slope_per_decade")), f"{_f(o['ci95_per_decade'][0])} to {_f(o['ci95_per_decade'][1])}" if o.get("available") else "n/a",
                     _f(o.get("p_value")), mk.get("trend", "n/a"), _f(mk.get("sen_slope_per_decade"))])
    t = Table(rows, repeatRows=1)
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 6.5), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b1a2e")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]))
    el += [t, Paragraph("4. Detected anomalies (|z| ≥ 2)", h)]
    for var, r in p["results"].get("variables", {}).items():
        if r.get("available") and r["anomalies"]["flagged"]:
            el.append(Paragraph(f"<b>{r['label']}</b>: " + "; ".join(f"{a['t']} {a['anomaly']:+.2f} {r['unit']} (z {a['z']:.1f})" for a in r["anomalies"]["flagged"][:8]), body))
    el.append(Paragraph("5. Interpretation", h))
    txt = (p.get("ai_interpretation") or "No interpretation requested.").replace("**", "").replace("## ", "").replace("#", "")
    for para in txt.split("\n"):
        if para.strip(): el.append(Paragraph(para.replace("&", "&amp;").replace("<", "&lt;"), body))
    el.append(Paragraph("6. Methodology", h))
    for m in p["methodology"]: el.append(Paragraph("• " + m, body))
    el.append(Paragraph("7. Limitations", h))
    el.append(Paragraph(c.get("notes", ""), body))
    for var, r in p["results"].get("variables", {}).items():
        for cv in r.get("caveats", []): el.append(Paragraph("• " + cv, body))
    doc.build(el)