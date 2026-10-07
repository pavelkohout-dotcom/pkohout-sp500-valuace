#!/usr/bin/env python3
"""
Automatická aktualizace valuace S&P 500 vůči Foreign-Adjusted MZM Proxy.

Metodika navazuje na mzm_claude_2_charts_wix_export.py:
    MZM_proxy = M2MNS - RMFSL + MMMFFAQ027S / 1000
    foreign_share = ROWCESQ027S / BOGZ1LM883164115Q
    Foreign_adjusted_MZM_proxy = MZM_proxy / (1 - foreign_share)
    valuation_raw = SP500 / Foreign_adjusted_MZM_proxy
    valuation_index = 100 * valuation_raw / 0.15

Historický graf:
- měsíční S&P 500 (poslední dostupné pozorování v měsíci)
- měsíční Foreign-Adjusted MZM Proxy
- posledních 5 let

Aktuální bod:
- poslední dostupné denní pozorování S&P 500
- poslední dostupný měsíční Foreign-Adjusted MZM Proxy
- datum čitatele i jmenovatele se exportuje zvlášť

Zdroj dat: FRED CSV endpoint (bez API klíče).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

OUTPUT_JSON = DATA_DIR / "mzm_ratio.json"

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"

SERIES = {
    "M2MNS": "M2MNS",
    "RMFSL": "RMFSL",
    "SP500": "SP500",
    "MMMFFAQ027S": "MMMFFAQ027S",
    "MZMSL": "MZMSL",
    "ROWCESQ027S": "ROWCESQ027S",
    "BOGZ1LM883164115Q": "BOGZ1LM883164115Q",
}

FOREIGN_ADJUSTED_MZM_START_DATE = pd.Timestamp("1982-01-01")
RATIO_REFERENCE_VALUE = 0.15
HISTORY_YEARS = 5


def fetch_fred(series_id: str) -> pd.Series:
    """Stáhne jednu FRED řadu z veřejného CSV endpointu."""
    url = FRED_CSV.format(series=series_id)
    response = requests.get(
        url,
        timeout=180,
        headers={"User-Agent": "pkohout-valuace-sp500/1.0"},
    )
    response.raise_for_status()

    from io import StringIO
    df = pd.read_csv(StringIO(response.text))

    if "observation_date" not in df.columns:
        raise RuntimeError(f"{series_id}: chybí sloupec observation_date")

    value_columns = [c for c in df.columns if c != "observation_date"]
    if not value_columns:
        raise RuntimeError(f"{series_id}: chybí datový sloupec")

    value_col = value_columns[0]
    df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce")
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df = df.dropna(subset=["observation_date"]).set_index("observation_date").sort_index()

    s = df[value_col].dropna()
    s.name = series_id

    if s.empty:
        raise RuntimeError(f"{series_id}: FRED nevrátil žádná použitelná data")

    print(
        f"{series_id}: {s.index[0].date()} až {s.index[-1].date()}, "
        f"poslední hodnota {s.iloc[-1]:,.4f}"
    )
    return s


def json_number(value, digits=None):
    if value is None or pd.isna(value):
        return None
    number = float(value)
    if not np.isfinite(number):
        return None
    return round(number, digits) if digits is not None else number


def json_date(value):
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def month_end(series: pd.Series, method="last") -> pd.Series:
    if method == "ffill":
        return series.resample("ME").ffill()
    return series.resample("ME").last()


def main():
    print("Stahuji data z FRED...")
    raw = {name: fetch_fred(series_id) for name, series_id in SERIES.items()}

    # Zachování metodiky původního skriptu.
    m2 = month_end(raw["M2MNS"])
    rmf = month_end(raw["RMFSL"], "ffill")
    mmf = month_end(raw["MMMFFAQ027S"], "ffill")
    row_eq = month_end(raw["ROWCESQ027S"], "ffill")
    domestic_eq = month_end(raw["BOGZ1LM883164115Q"], "ffill")
    mzmsl = month_end(raw["MZMSL"])

    data = pd.concat(
        [m2, rmf, mmf, row_eq, domestic_eq, mzmsl],
        axis=1
    )

    data.columns = [
        "M2MNS",
        "RMFSL",
        "MMMFFAQ027S",
        "ROWCESQ027S",
        "BOGZ1LM883164115Q",
        "MZMSL",
    ]

    lower_frequency = [
        "RMFSL",
        "MMMFFAQ027S",
        "ROWCESQ027S",
        "BOGZ1LM883164115Q",
    ]
    data[lower_frequency] = data[lower_frequency].ffill()

    # Řádky bez M2MNS nemohou vytvořit MZM proxy.
    data = data.dropna(subset=["M2MNS"]).copy()

    data["MZM_proxy"] = (
        data["M2MNS"]
        - data["RMFSL"]
        + data["MMMFFAQ027S"] / 1000.0
    )

    data["foreign_share"] = (
        data["ROWCESQ027S"] / data["BOGZ1LM883164115Q"]
    )

    data.loc[
        (data["foreign_share"] <= 0) | (data["foreign_share"] >= 1),
        "foreign_share"
    ] = np.nan

    data["Foreign_adjusted_MZM_proxy"] = (
        data["MZM_proxy"] / (1.0 - data["foreign_share"])
    )

    # Zachování historického rozšíření z původního skriptu:
    # před 1982 preferujeme oficiální MZM.
    extended = "Foreign_adjusted_MZM_proxy_extended"
    data[extended] = data["Foreign_adjusted_MZM_proxy"]

    historical_mask = data.index < FOREIGN_ADJUSTED_MZM_START_DATE
    data.loc[historical_mask, extended] = (
        data.loc[historical_mask, "MZMSL"].combine_first(
            data.loc[historical_mask, "Foreign_adjusted_MZM_proxy"]
        )
    )

    # Měsíční S&P 500 pro historický graf.
    sp500_daily = raw["SP500"].dropna()
    sp500_monthly = sp500_daily.resample("ME").last()
    sp500_monthly.name = "SP500"

    data = data.join(sp500_monthly, how="left")

    data["raw_ratio"] = data["SP500"] / data[extended]
    data["index"] = 100.0 * data["raw_ratio"] / RATIO_REFERENCE_VALUE

    matched = data[["SP500", extended, "raw_ratio", "index"]].dropna(
        subset=["raw_ratio", "index"]
    ).sort_index()

    latest_sp500_date = sp500_daily.index[-1]
    latest_sp500 = float(sp500_daily.iloc[-1])

    latest_mzm_series = data[extended].dropna()
    latest_mzm_date = latest_mzm_series.index[-1]
    latest_mzm = float(latest_mzm_series.iloc[-1])

    current_raw_ratio = latest_sp500 / latest_mzm
    current_index = 100.0 * current_raw_ratio / RATIO_REFERENCE_VALUE

    five_year_end = pd.Timestamp(latest_sp500_date)
    five_year_start = five_year_end - pd.DateOffset(years=HISTORY_YEARS)
    matched_5y = matched[matched.index >= five_year_start].copy()

    history = []
    for date, row in matched_5y.iterrows():
        history.append(
            {
                "date": json_date(date),
                "sp500": json_number(row["SP500"], 6),
                "foreign_adjusted_mzm": json_number(row[extended], 6),
                "raw_ratio": json_number(row["raw_ratio"], 9),
                "index": json_number(row["index"], 6),
                "kind": "matched_monthly",
            }
        )

    chart_points = [dict(x) for x in history]
    current_snapshot_appended = False

    if (
        not chart_points
        or pd.Timestamp(latest_sp500_date)
        > pd.Timestamp(chart_points[-1]["date"])
    ):
        chart_points.append(
            {
                "date": json_date(latest_sp500_date),
                "sp500": json_number(latest_sp500, 6),
                "foreign_adjusted_mzm_date": json_date(latest_mzm_date),
                "foreign_adjusted_mzm": json_number(latest_mzm, 6),
                "raw_ratio": json_number(current_raw_ratio, 9),
                "index": json_number(current_index, 6),
                "kind": "current_snapshot",
            }
        )
        current_snapshot_appended = True

    five_year_average = (
        json_number(matched_5y["index"].mean(), 6)
        if not matched_5y.empty
        else None
    )

    payload = {
        "schema_version": 2,
        "status": "ok",
        "generated_utc": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "series_name": "S&P 500 / Foreign-adjusted MZM proxy index",
        "window": {
            "start": json_date(five_year_start),
            "end": json_date(five_year_end),
            "years": HISTORY_YEARS,
        },
        "normalization": {
            "raw_ratio_reference": RATIO_REFERENCE_VALUE,
            "index_at_reference": 100.0,
            "formula": "100 * raw_ratio / 0.15",
        },
        "five_year_monthly_average": five_year_average,
        "current_snapshot_appended_to_chart": current_snapshot_appended,
        "current_snapshot": {
            "sp500_date": json_date(latest_sp500_date),
            "sp500": json_number(latest_sp500, 6),
            "foreign_adjusted_mzm_date": json_date(latest_mzm_date),
            "foreign_adjusted_mzm": json_number(latest_mzm, 6),
            "raw_ratio": json_number(current_raw_ratio, 9),
            "index": json_number(current_index, 6),
            "mixed_vintage": (
                pd.Timestamp(latest_sp500_date)
                != pd.Timestamp(latest_mzm_date)
            ),
        },
        "history": history,
        "chart_points": chart_points,
        "methodology": {
            "mzm_proxy_formula": "M2MNS - RMFSL + MMMFFAQ027S / 1000",
            "foreign_share_formula": "ROWCESQ027S / BOGZ1LM883164115Q",
            "foreign_adjusted_mzm_formula": "MZM_proxy / (1 - foreign_share)",
            "historical_extension": (
                "Before 1982, MZMSL is preferred as the historical "
                "approximation; calculated Foreign-adjusted MZM is fallback."
            ),
            "matched_history_note": (
                "Historical points use matched month-end S&P 500 and "
                "Foreign-adjusted MZM observations."
            ),
            "current_snapshot_note": (
                "The current point combines the latest available daily S&P 500 "
                "observation with the latest published monthly MZM denominator. "
                "Both dates are exported explicitly."
            ),
            "source": "Federal Reserve Bank of St. Louis, FRED",
        },
    }

    OUTPUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )

    print()
    print(f"Hotovo: {OUTPUT_JSON}")
    print(f"S&P 500: {latest_sp500:,.2f} k {json_date(latest_sp500_date)}")
    print(
        "Foreign-Adjusted MZM:",
        f"{latest_mzm:,.2f}",
        "k",
        json_date(latest_mzm_date),
    )
    print(f"Valuační index: {current_index:.2f}")


if __name__ == "__main__":
    main()
