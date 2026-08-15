#!/usr/bin/env python3
"""
UK Low-Pay Sector Stress Index (LPS) — live data pipeline.

Tracks employment momentum in the UK's two largest low-pay sectors —
retail/wholesale and accommodation/food service — around each April
National Living Wage uprating, and combines it with the size of that
year's wage increase into a single 0-100 stress score.

Run manually:    python3 fetch_and_score.py
Run on schedule: see .github/workflows/update-lps.yml
"""

import csv
import io
import json
import re
import sys
from datetime import datetime, timezone
from urllib.request import urlopen, Request

HEADERS = {"User-Agent": "Mozilla/5.0 (UK-LPS student project; contact via GitHub)"}

ONS_SERIES = {
    # UK Workforce Jobs SA : G Wholesale & retail trade; repair of motor (thousands)
    "retail": "https://www.ons.gov.uk/generator?format=csv&uri=/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/timeseries/jws3/lms",
    # UK Workforce Jobs SA : I Accommodation & food service activities (thousands)
    "hospitality": "https://www.ons.gov.uk/generator?format=csv&uri=/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/timeseries/jws5/lms",
}

# National Living Wage history (£/hr, 21+ rate from Apr 2024; 23+ before that).
# Published by the Low Pay Commission / HM Treasury each Autumn Budget for the
# following April. Update this dict by hand once a year when the new rate is announced.
NLW_HISTORY = {
    "2021-04": 8.91,
    "2022-04": 9.50,
    "2023-04": 10.42,
    "2024-04": 11.44,
    "2025-04": 12.21,
    "2026-04": 12.71,
}

QUARTER_RE = re.compile(r"^(\d{4})\s*Q([1-4])$")


def fetch(url):
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_ons_quarterly(raw_csv):
    reader = csv.reader(io.StringIO(raw_csv))
    quarterly = {}
    for row in reader:
        if len(row) < 2:
            continue
        period, value = row[0].strip().strip('"'), row[1].strip().strip('"')
        try:
            v = float(value)
        except ValueError:
            continue
        m = QUARTER_RE.match(period)
        if m:
            y, q = m.groups()
            quarterly[f"{y}Q{q}"] = v
    return quarterly


def latest_key(d):
    return sorted(d.keys())[-1]


def prev_year_key(qkey):
    y, q = qkey.split("Q")
    return f"{int(y)-1}Q{q}"


def prev_quarter_key(qkey):
    y, q = int(qkey[:4]), int(qkey[-1])
    if q == 1:
        return f"{y-1}Q4"
    return f"{y}Q{q-1}"


def clip(lo, hi, x):
    return max(lo, min(hi, x))


def latest_nlw_uprating():
    key = sorted(NLW_HISTORY.keys())[-1]
    prev = sorted(NLW_HISTORY.keys())[-2]
    pct = (NLW_HISTORY[key] - NLW_HISTORY[prev]) / NLW_HISTORY[prev] * 100
    return key, NLW_HISTORY[key], pct


def main():
    print("Fetching ONS sector employment series...")
    retail = parse_ons_quarterly(fetch(ONS_SERIES["retail"]))
    hosp = parse_ons_quarterly(fetch(ONS_SERIES["hospitality"]))

    r_key = latest_key(retail)
    h_key = latest_key(hosp)

    r_latest, r_yr_ago = retail[r_key], retail.get(prev_year_key(r_key))
    h_latest, h_yr_ago = hosp[h_key], hosp.get(prev_year_key(h_key))
    r_prev_q = retail.get(prev_quarter_key(r_key))
    h_prev_q = hosp.get(prev_quarter_key(h_key))

    retail_yoy = (r_latest - r_yr_ago) / r_yr_ago * 100 if r_yr_ago else 0.0
    hosp_yoy = (h_latest - h_yr_ago) / h_yr_ago * 100 if h_yr_ago else 0.0
    retail_qoq = (r_latest - r_prev_q) / r_prev_q * 100 if r_prev_q else 0.0
    hosp_qoq = (h_latest - h_prev_q) / h_prev_q * 100 if h_prev_q else 0.0

    nlw_key, nlw_rate, nlw_pct = latest_nlw_uprating()

    s_retail = clip(0, 100, 50 - retail_yoy * 10)
    s_hosp = clip(0, 100, 50 - hosp_yoy * 10)
    s_trend = clip(0, 100, 50 - ((retail_qoq + hosp_qoq) / 2) * 10)
    s_wage = clip(0, 100, (nlw_pct / 8) * 100)

    weights = {
        "retail_momentum": 0.30,
        "hospitality_momentum": 0.30,
        "quarterly_trend": 0.20,
        "wage_pressure": 0.20,
    }
    scores = {
        "retail_momentum": s_retail,
        "hospitality_momentum": s_hosp,
        "quarterly_trend": s_trend,
        "wage_pressure": s_wage,
    }
    lps = sum(scores[k] * weights[k] for k in weights)

    def band(score):
        if score < 25: return "Low Stress"
        if score < 50: return "Moderate Stress"
        if score < 75: return "Elevated Stress"
        return "High Stress"

    def thin(d, min_key="2000Q1"):
        return {k: v for k, v in d.items() if k >= min_key}

    out = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "lps_score": round(lps, 1),
        "lps_band": band(lps),
        "inputs": {
            "retail_jobs_latest_thousands": r_latest, "retail_period": r_key,
            "retail_yoy_pct": round(retail_yoy, 2), "retail_qoq_pct": round(retail_qoq, 2),
            "hospitality_jobs_latest_thousands": h_latest, "hospitality_period": h_key,
            "hospitality_yoy_pct": round(hosp_yoy, 2), "hospitality_qoq_pct": round(hosp_qoq, 2),
            "latest_nlw_effective": nlw_key, "latest_nlw_rate_gbp": nlw_rate, "latest_nlw_increase_pct": round(nlw_pct, 2),
        },
        "sub_scores": {k: round(v, 1) for k, v in scores.items()},
        "weights": weights,
        "nlw_history": NLW_HISTORY,
        "chart_data": {
            "retail_jobs_quarterly": thin(retail),
            "hospitality_jobs_quarterly": thin(hosp),
        },
    }

    with open("data.json", "w") as f:
        json.dump(out, f, indent=2)

    print(f"LPS = {lps:.1f} ({band(lps)}) — data.json written.")


if __name__ == "__main__":
    main()
