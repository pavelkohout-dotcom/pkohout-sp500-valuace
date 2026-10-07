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
- zachovává celou dostupnou historii,
- měsíční S&P 500,
- měsíční Foreign-Adjusted MZM Proxy.

Aktuální bod:
- poslední dostupná denní hodnota S&P 500,
- poslední dostupná měsíční hodnota Foreign-Adjusted MZM Proxy.

Zdroj dat:
Federal Reserve Bank of St. Louis, FRED CSV endpoint.

Při timeoutu nebo dočasném výpadku FRED se stahování automaticky opakuje.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

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

# Valuační index = 100 při raw ratio = 0.15
RATIO_REFERENCE_VALUE = 0.15


# ------------------------------------------------------------
# FRED download
# ------------------------------------------------------------

def fetch_fred(series_id: str) -> pd.Series:
    """
    Stáhne jednu FRED řadu z veřejného CSV endpointu.

    Při timeoutu, HTTP chybě nebo dočasném problému s připojením
    provede až 4 pokusy.

    Celá historie řady se zachovává.
    """

    url = FRED_CSV.format(series=series_id)

    last_error = None

    for attempt in range(1, 5):

        try:
            print()
            print(f"{series_id}: pokus {attempt}/4")
            print(f"{series_id}: stahuji {url}")

            response = requests.get(
                url,
                timeout=180,
                headers={
                    "User-Agent": "pkohout-valuace-sp500/1.0"
                },
            )

            response.raise_for_status()

            df = pd.read_csv(
                StringIO(response.text)
            )

            if "observation_date" not in df.columns:
                raise RuntimeError(
                    f"{series_id}: chybí sloupec observation_date"
                )

            value_columns = [
                column
                for column in df.columns
                if column != "observation_date"
            ]

            if not value_columns:
                raise RuntimeError(
                    f"{series_id}: chybí datový sloupec"
                )

            value_column = value_columns[0]

            df["observation_date"] = pd.to_datetime(
                df["observation_date"],
                errors="coerce",
            )

            df[value_column] = pd.to_numeric(
                df[value_column],
                errors="coerce",
            )

            df = (
                df
                .dropna(subset=["observation_date"])
                .set_index("observation_date")
                .sort_index()
            )

            series = df[value_column].dropna()
            series.name = series_id

            if series.empty:
                raise RuntimeError(
                    f"{series_id}: FRED nevrátil žádná použitelná data"
                )

            print(
                f"{series_id}: "
                f"{series.index[0].date()} až "
                f"{series.index[-1].date()}, "
                f"poslední hodnota {series.iloc[-1]:,.4f}"
            )

            return series

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
        ) as error:

            last_error = error

            print(
                f"{series_id}: dočasná chyba při stahování:"
            )
            print(error)

            if attempt < 4:

                wait_seconds = attempt * 15

                print(
                    f"{series_id}: čekám {wait_seconds} sekund "
                    "a zkouším znovu..."
                )

                time.sleep(wait_seconds)

    raise RuntimeError(
        f"{series_id}: FRED se nepodařilo stáhnout ani po 4 pokusech."
    ) from last_error


# ------------------------------------------------------------
# JSON helpers
# ------------------------------------------------------------

def json_number(value, digits=None):

    if value is None or pd.isna(value):
        return None

    number = float(value)

    if not np.isfinite(number):
        return None

    if digits is not None:
        number = round(number, digits)

    return number


def json_date(value):

    if value is None or pd.isna(value):
        return None

    return pd.Timestamp(value).strftime("%Y-%m-%d")


# ------------------------------------------------------------
# Resampling helper
# ------------------------------------------------------------

def month_end(series: pd.Series, method="last") -> pd.Series:

    if method == "ffill":
        return series.resample("ME").ffill()

    return series.resample("ME").last()


# ------------------------------------------------------------
# Main calculation
# ------------------------------------------------------------

def main():

    print("=" * 70)
    print("AUTOMATICKÁ AKTUALIZACE VALUACE S&P 500")
    print("=" * 70)

    print()
    print("Stahuji data z FRED...")

    raw = {}

    for name, series_id in SERIES.items():

        raw[name] = fetch_fred(series_id)

        # Krátká pauza mezi jednotlivými FRED dotazy.
        time.sleep(2)


    # --------------------------------------------------------
    # Monthly alignment
    # --------------------------------------------------------

    print()
    print("Připravuji měsíční řady...")

    m2 = month_end(
        raw["M2MNS"]
    )

    rmf = month_end(
        raw["RMFSL"],
        "ffill",
    )

    mmf = month_end(
        raw["MMMFFAQ027S"],
        "ffill",
    )

    row_equities = month_end(
        raw["ROWCESQ027S"],
        "ffill",
    )

    domestic_equities = month_end(
        raw["BOGZ1LM883164115Q"],
        "ffill",
    )

    mzmsl = month_end(
        raw["MZMSL"]
    )


    data = pd.concat(
        [
            m2,
            rmf,
            mmf,
            row_equities,
            domestic_equities,
            mzmsl,
        ],
        axis=1,
    )

    data.columns = [
        "M2MNS",
        "RMFSL",
        "MMMFFAQ027S",
        "ROWCESQ027S",
        "BOGZ1LM883164115Q",
        "MZMSL",
    ]


    # --------------------------------------------------------
    # Forward-fill lower-frequency components
    # --------------------------------------------------------

    lower_frequency_columns = [
        "RMFSL",
        "MMMFFAQ027S",
        "ROWCESQ027S",
        "BOGZ1LM883164115Q",
    ]

    data[lower_frequency_columns] = (
        data[lower_frequency_columns].ffill()
    )

    # MZM proxy lze vytvořit pouze tam,
    # kde existuje M2MNS.
    data = data.dropna(
        subset=["M2MNS"]
    ).copy()


    # --------------------------------------------------------
    # MZM proxy
    # --------------------------------------------------------

    data["MZM_proxy"] = (
        data["M2MNS"]
        - data["RMFSL"]
        + data["MMMFFAQ027S"] / 1000.0
    )


    # --------------------------------------------------------
    # Foreign ownership share
    # --------------------------------------------------------

    data["foreign_share"] = (
        data["ROWCESQ027S"]
        / data["BOGZ1LM883164115Q"]
    )

    # Bezpečnostní kontrola.
    data.loc[
        (
            (data["foreign_share"] <= 0)
            | (data["foreign_share"] >= 1)
        ),
        "foreign_share",
    ] = np.nan


    # --------------------------------------------------------
    # Foreign-adjusted MZM proxy
    # --------------------------------------------------------

    data["Foreign_adjusted_MZM_proxy"] = (
        data["MZM_proxy"]
        / (1.0 - data["foreign_share"])
    )


    # --------------------------------------------------------
    # Historical extension
    # --------------------------------------------------------

    extended_column = (
        "Foreign_adjusted_MZM_proxy_extended"
    )

    data[extended_column] = (
        data["Foreign_adjusted_MZM_proxy"]
    )

    historical_mask = (
        data.index
        < FOREIGN_ADJUSTED_MZM_START_DATE
    )

    # Před rokem 1982 preferujeme oficiální MZM.
    # Pokud chybí, použijeme vypočtenou proxy.
    data.loc[
        historical_mask,
        extended_column,
    ] = (
        data.loc[
            historical_mask,
            "MZMSL",
        ]
        .combine_first(
            data.loc[
                historical_mask,
                "Foreign_adjusted_MZM_proxy",
            ]
        )
    )


    # --------------------------------------------------------
    # S&P 500
    # --------------------------------------------------------

    print()
    print("Připravuji S&P 500...")

    sp500_daily = (
        raw["SP500"]
        .dropna()
        .sort_index()
    )

    sp500_monthly = (
        sp500_daily
        .resample("ME")
        .last()
    )

    sp500_monthly.name = "SP500"

    data = data.join(
        sp500_monthly,
        how="left",
    )


    # --------------------------------------------------------
    # Historical valuation ratio
    # --------------------------------------------------------

    data["raw_ratio"] = (
        data["SP500"]
        / data[extended_column]
    )

    data["index"] = (
        100.0
        * data["raw_ratio"]
        / RATIO_REFERENCE_VALUE
    )


    matched = (
        data[
            [
                "SP500",
                extended_column,
                "raw_ratio",
                "index",
            ]
        ]
        .dropna(
            subset=[
                "raw_ratio",
                "index",
            ]
        )
        .sort_index()
    )


    # --------------------------------------------------------
    # Current snapshot
    # --------------------------------------------------------

    latest_sp500_date = (
        sp500_daily.index[-1]
    )

    latest_sp500 = float(
        sp500_daily.iloc[-1]
    )

    latest_mzm_series = (
        data[extended_column]
        .dropna()
        .sort_index()
    )

    latest_mzm_date = (
        latest_mzm_series.index[-1]
    )

    latest_mzm = float(
        latest_mzm_series.iloc[-1]
    )

    current_raw_ratio = (
        latest_sp500
        / latest_mzm
    )

    current_index = (
        100.0
        * current_raw_ratio
        / RATIO_REFERENCE_VALUE
    )


    # --------------------------------------------------------
    # Export complete history
    # --------------------------------------------------------

    print()
    print("Vytvářím historickou řadu...")

    history = []

    for date, row in matched.iterrows():

        history.append(
            {
                "date": json_date(date),

                "sp500": json_number(
                    row["SP500"],
                    6,
                ),

                "foreign_adjusted_mzm":
                    json_number(
                        row[extended_column],
                        6,
                    ),

                "raw_ratio":
                    json_number(
                        row["raw_ratio"],
                        9,
                    ),

                "index":
                    json_number(
                        row["index"],
                        6,
                    ),

                "kind":
                    "matched_monthly",
            }
        )


    # --------------------------------------------------------
    # Current point
    # --------------------------------------------------------

    chart_points = [
        dict(point)
        for point in history
    ]

    current_snapshot_appended = False

    if (
        not chart_points
        or pd.Timestamp(latest_sp500_date)
        > pd.Timestamp(
            chart_points[-1]["date"]
        )
    ):

        chart_points.append(
            {
                "date":
                    json_date(
                        latest_sp500_date
                    ),

                "sp500":
                    json_number(
                        latest_sp500,
                        6,
                    ),

                "foreign_adjusted_mzm_date":
                    json_date(
                        latest_mzm_date
                    ),

                "foreign_adjusted_mzm":
                    json_number(
                        latest_mzm,
                        6,
                    ),

                "raw_ratio":
                    json_number(
                        current_raw_ratio,
                        9,
                    ),

                "index":
                    json_number(
                        current_index,
                        6,
                    ),

                "kind":
                    "current_snapshot",
            }
        )

        current_snapshot_appended = True


    # --------------------------------------------------------
    # 5-year average
    # --------------------------------------------------------

    five_year_end = pd.Timestamp(
        latest_sp500_date
    )

    five_year_start = (
        five_year_end
        - pd.DateOffset(years=5)
    )

    matched_5y = matched[
        matched.index >= five_year_start
    ]

    if not matched_5y.empty:

        five_year_average = json_number(
            matched_5y["index"].mean(),
            6,
        )

    else:

        five_year_average = None


    # --------------------------------------------------------
    # 10-year average
    # --------------------------------------------------------

    ten_year_start = (
        five_year_end
        - pd.DateOffset(years=10)
    )

    matched_10y = matched[
        matched.index >= ten_year_start
    ]

    if not matched_10y.empty:

        ten_year_average = json_number(
            matched_10y["index"].mean(),
            6,
        )

    else:

        ten_year_average = None


    # --------------------------------------------------------
    # Full-history average
    # --------------------------------------------------------

    if not matched.empty:

        full_history_average = json_number(
            matched["index"].mean(),
            6,
        )

    else:

        full_history_average = None


    # --------------------------------------------------------
    # JSON payload
    # --------------------------------------------------------

    payload = {

        "schema_version": 3,

        "status": "ok",

        "generated_utc":
            datetime.now(
                timezone.utc
            )
            .isoformat(
                timespec="seconds"
            )
            .replace(
                "+00:00",
                "Z",
            ),

        "series_name":
            "S&P 500 / Foreign-adjusted MZM proxy index",

        "history_start":
            json_date(
                matched.index[0]
                if not matched.empty
                else None
            ),

        "history_end":
            json_date(
                matched.index[-1]
                if not matched.empty
                else None
            ),

        "normalization": {

            "raw_ratio_reference":
                RATIO_REFERENCE_VALUE,

            "index_at_reference":
                100.0,

            "formula":
                "100 * raw_ratio / 0.15",
        },

        "averages": {

            "five_year":
                five_year_average,

            "ten_year":
                ten_year_average,

            "full_history":
                full_history_average,
        },

        # Pro zpětnou kompatibilitu
        # s předchozí verzí HTML.
        "five_year_monthly_average":
            five_year_average,

        "current_snapshot_appended_to_chart":
            current_snapshot_appended,

        "current_snapshot": {

            "sp500_date":
                json_date(
                    latest_sp500_date
                ),

            "sp500":
                json_number(
                    latest_sp500,
                    6,
                ),

            "foreign_adjusted_mzm_date":
                json_date(
                    latest_mzm_date
                ),

            "foreign_adjusted_mzm":
                json_number(
                    latest_mzm,
                    6,
                ),

            "raw_ratio":
                json_number(
                    current_raw_ratio,
                    9,
                ),

            "index":
                json_number(
                    current_index,
                    6,
                ),

            "mixed_vintage":
                (
                    pd.Timestamp(
                        latest_sp500_date
                    )
                    !=
                    pd.Timestamp(
                        latest_mzm_date
                    )
                ),
        },

        # Celá dostupná historická řada.
        "history":
            history,

        # Celá historie + případný aktuální denní bod.
        "chart_points":
            chart_points,

        "methodology": {

            "mzm_proxy_formula":
                (
                    "M2MNS - RMFSL "
                    "+ MMMFFAQ027S / 1000"
                ),

            "foreign_share_formula":
                (
                    "ROWCESQ027S "
                    "/ BOGZ1LM883164115Q"
                ),

            "foreign_adjusted_mzm_formula":
                (
                    "MZM_proxy "
                    "/ (1 - foreign_share)"
                ),

            "historical_extension":
                (
                    "Before 1982, MZMSL is preferred "
                    "as the historical approximation; "
                    "calculated Foreign-adjusted MZM "
                    "is used as fallback."
                ),

            "matched_history_note":
                (
                    "Historical points use "
                    "month-end S&P 500 and "
                    "Foreign-adjusted MZM observations."
                ),

            "current_snapshot_note":
                (
                    "The current point combines the "
                    "latest available daily S&P 500 "
                    "observation with the latest "
                    "published monthly MZM denominator. "
                    "Both dates are exported explicitly."
                ),

            "source":
                (
                    "Federal Reserve Bank "
                    "of St. Louis, FRED"
                ),
        },
    }


    # --------------------------------------------------------
    # Save JSON
    # --------------------------------------------------------

    OUTPUT_JSON.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )


    # --------------------------------------------------------
    # Diagnostics
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("HOTOVO")
    print("=" * 70)

    print(
        "JSON:",
        OUTPUT_JSON,
    )

    print(
        "Historie:",
        json_date(
            matched.index[0]
            if not matched.empty
            else None
        ),
        "až",
        json_date(
            matched.index[-1]
            if not matched.empty
            else None
        ),
    )

    print(
        "Počet historických bodů:",
        len(history),
    )

    print(
        "S&P 500:",
        f"{latest_sp500:,.2f}",
        "k",
        json_date(
            latest_sp500_date
        ),
    )

    print(
        "Foreign-Adjusted MZM:",
        f"{latest_mzm:,.2f}",
        "k",
        json_date(
            latest_mzm_date
        ),
    )

    print(
        "Raw ratio:",
        f"{current_raw_ratio:.6f}",
    )

    print(
        "Valuační index:",
        f"{current_index:.2f}",
    )

    print(
        "5letý průměr:",
        five_year_average,
    )

    print(
        "10letý průměr:",
        ten_year_average,
    )

    print(
        "Průměr celé historie:",
        full_history_average,
    )


# ------------------------------------------------------------
# Run
# ------------------------------------------------------------

if __name__ == "__main__":
    main()
