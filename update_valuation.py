#!/usr/bin/env python3

"""
Automatická aktualizace valuace S&P 500 vůči Foreign-Adjusted MZM Proxy.

ZDROJE S&P 500
--------------
1. sp500w.xlsx:
   dlouhá historická týdenní řada S&P 500
2. FRED SP500:
   novější denní řada; tam, kde existuje, má přednost

MĚNOVÁ METODIKA
---------------
MZM_proxy =
    M2MNS - RMFSL + MMMFFAQ027S / 1000

foreign_share =
    ROWCESQ027S / BOGZ1LM883164115Q

Foreign_adjusted_MZM_proxy =
    MZM_proxy / (1 - foreign_share)

Před rokem 1982 je pro historické prodloužení preferována
oficiální řada MZMSL.

VALUACE
-------
raw_ratio =
    S&P 500 / Foreign_adjusted_MZM_proxy

valuation_index =
    100 * raw_ratio / 0.15

Index 100 tedy odpovídá raw ratio = 0.15.

AKTUÁLNÍ BOD
------------
Používá:
- poslední dostupnou denní hodnotu S&P 500 z FRED,
- poslední dostupnou měsíční Foreign-Adjusted MZM Proxy.

Zdroj online dat:
Federal Reserve Bank of St. Louis, FRED API.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests


# ============================================================
# KONFIGURACE
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

OUTPUT_JSON = DATA_DIR / "mzm_ratio.json"

SP500_HISTORY_FILE = ROOT / "sp500w.xlsx"


# ------------------------------------------------------------
# FRED
# ------------------------------------------------------------

FRED_API_URL = (
    "https://api.stlouisfed.org/fred/series/observations"
)

FRED_API_KEY = "5d98eaaf2538550a208c098de8c7e3e5"


SERIES = {
    "M2MNS": "M2MNS",
    "RMFSL": "RMFSL",
    "SP500": "SP500",
    "MMMFFAQ027S": "MMMFFAQ027S",
    "MZMSL": "MZMSL",
    "ROWCESQ027S": "ROWCESQ027S",
    "BOGZ1LM883164115Q": "BOGZ1LM883164115Q",
}


FOREIGN_ADJUSTED_MZM_START_DATE = pd.Timestamp(
    "1982-01-01"
)

RATIO_REFERENCE_VALUE = 0.15


# ============================================================
# HELPERS
# ============================================================

def json_number(value, digits=None):

    if value is None:
        return None

    if pd.isna(value):
        return None

    number = float(value)

    if not np.isfinite(number):
        return None

    if digits is not None:
        number = round(
            number,
            digits,
        )

    return number


def json_date(value):

    if value is None:
        return None

    if pd.isna(value):
        return None

    return pd.Timestamp(
        value
    ).strftime(
        "%Y-%m-%d"
    )


def month_end(
    series: pd.Series,
    method="last",
) -> pd.Series:

    if method == "ffill":

        return (
            series
            .resample("ME")
            .ffill()
        )

    return (
        series
        .resample("ME")
        .last()
    )


# ============================================================
# FRED DOWNLOAD
# ============================================================

def fetch_fred(series_id: str) -> pd.Series:
    """
    Stáhne celou dostupnou historii jedné FRED řady.

    Při dočasném problému provede až 4 pokusy.
    """

    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "asc",
        "limit": 100000,
    }

    last_error = None

    for attempt in range(1, 5):

        try:

            print()
            print(
                f"{series_id}: pokus {attempt}/4"
            )

            response = requests.get(
                FRED_API_URL,
                params=params,
                timeout=(20, 90),
                headers={
                    "User-Agent":
                        "pkohout-sp500-valuace/2.0"
                },
            )

            response.raise_for_status()

            payload = response.json()

            if "observations" not in payload:
                raise RuntimeError(
                    f"{series_id}: API nevrátilo observations"
                )

            observations = payload["observations"]

            if not observations:
                raise RuntimeError(
                    f"{series_id}: žádná pozorování"
                )

            df = pd.DataFrame(
                observations
            )

            if "date" not in df.columns:
                raise RuntimeError(
                    f"{series_id}: chybí datum"
                )

            if "value" not in df.columns:
                raise RuntimeError(
                    f"{series_id}: chybí hodnota"
                )

            df["date"] = pd.to_datetime(
                df["date"],
                errors="coerce",
            )

            # FRED označuje missing values znakem "."
            df["value"] = pd.to_numeric(
                df["value"],
                errors="coerce",
            )

            df = (
                df
                .dropna(
                    subset=[
                        "date",
                        "value",
                    ]
                )
                .drop_duplicates(
                    subset="date",
                    keep="last",
                )
                .sort_values("date")
                .set_index("date")
            )

            result = df["value"].copy()
            result.name = series_id

            if result.empty:
                raise RuntimeError(
                    f"{series_id}: žádná použitelná data"
                )

            print(
                f"{series_id}: "
                f"{result.index[0].date()} až "
                f"{result.index[-1].date()}, "
                f"{len(result):,} pozorování, "
                f"poslední hodnota "
                f"{result.iloc[-1]:,.4f}"
            )

            return result

        except requests.exceptions.RequestException as error:

            last_error = error

            print(
                f"{series_id}: chyba spojení:"
            )

            print(error)

            if attempt < 4:

                wait_seconds = (
                    10 * attempt
                )

                print(
                    f"Čekám {wait_seconds} s..."
                )

                time.sleep(
                    wait_seconds
                )

        except ValueError as error:

            last_error = error

            print(
                f"{series_id}: chyba JSON:"
            )

            print(error)

            if attempt < 4:

                wait_seconds = (
                    10 * attempt
                )

                time.sleep(
                    wait_seconds
                )

        except Exception:
            raise

    raise RuntimeError(
        f"{series_id}: FRED se nepodařilo stáhnout "
        "ani po 4 pokusech."
    ) from last_error


# ============================================================
# HISTORICKÝ S&P 500
# ============================================================

def load_historical_sp500(
    filename: Path,
) -> pd.Series:
    """
    Načte týdenní historický S&P 500 ze sp500w.xlsx
    a převede jej na měsíční řadu.

    Použije poslední dostupný Close v každém měsíci.
    """

    print()
    print(
        "Načítám historický S&P 500:"
    )

    print(
        filename
    )

    if not filename.exists():
        raise FileNotFoundError(
            f"Chybí historický soubor: {filename}"
        )

    df = pd.read_excel(
        filename
    )

    required_columns = {
        "Date",
        "Close",
    }

    missing = (
        required_columns
        - set(df.columns)
    )

    if missing:
        raise RuntimeError(
            "sp500w.xlsx neobsahuje požadované sloupce: "
            + ", ".join(
                sorted(missing)
            )
        )

    df = df[
        [
            "Date",
            "Close",
        ]
    ].copy()

    df["Date"] = pd.to_datetime(
        df["Date"],
        errors="coerce",
    )

    df["Close"] = pd.to_numeric(
        df["Close"],
        errors="coerce",
    )

    df = (
        df
        .dropna(
            subset=[
                "Date",
                "Close",
            ]
        )
        .drop_duplicates(
            subset="Date",
            keep="last",
        )
        .sort_values(
            "Date"
        )
        .set_index(
            "Date"
        )
    )

    if df.empty:
        raise RuntimeError(
            "sp500w.xlsx neobsahuje použitelná data."
        )

    print(
        "Historický S&P 500:",
        df.index[0].date(),
        "až",
        df.index[-1].date(),
        f"({len(df):,} týdenních pozorování)",
    )

    monthly = (
        df["Close"]
        .resample("ME")
        .last()
    )

    monthly.name = (
        "SP500_historical"
    )

    print(
        "Měsíční historický S&P 500:",
        monthly.index[0].date(),
        "až",
        monthly.index[-1].date(),
    )

    return monthly


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=" * 72
    )

    print(
        "AUTOMATICKÁ AKTUALIZACE VALUACE S&P 500"
    )

    print(
        "=" * 72
    )


    # --------------------------------------------------------
    # HISTORICKÝ S&P 500
    # --------------------------------------------------------

    sp500_historical_monthly = (
        load_historical_sp500(
            SP500_HISTORY_FILE
        )
    )


    # --------------------------------------------------------
    # FRED DOWNLOAD
    # --------------------------------------------------------

    print()
    print(
        "Stahuji data z FRED API..."
    )

    raw = {}

    for name, series_id in SERIES.items():

        raw[name] = fetch_fred(
            series_id
        )

        # Šetrnější vůči API.
        time.sleep(
            0.5
        )


    # ========================================================
    # MĚNOVÉ ŘADY
    # ========================================================

    print()
    print(
        "Připravuji měnové řady..."
    )


    m2 = month_end(
        raw["M2MNS"]
    )

    rmf = month_end(
        raw["RMFSL"],
        method="ffill",
    )

    mmf = month_end(
        raw["MMMFFAQ027S"],
        method="ffill",
    )

    row_equities = month_end(
        raw["ROWCESQ027S"],
        method="ffill",
    )

    domestic_equities = month_end(
        raw["BOGZ1LM883164115Q"],
        method="ffill",
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
    # FORWARD-FILL NIŽŠÍCH FREKVENCÍ
    # --------------------------------------------------------

    lower_frequency_columns = [
        "RMFSL",
        "MMMFFAQ027S",
        "ROWCESQ027S",
        "BOGZ1LM883164115Q",
    ]

    data[
        lower_frequency_columns
    ] = (
        data[
            lower_frequency_columns
        ]
        .ffill()
    )


    data = (
        data
        .dropna(
            subset=[
                "M2MNS"
            ]
        )
        .copy()
    )


    # ========================================================
    # MZM PROXY
    # ========================================================

    data["MZM_proxy"] = (
        data["M2MNS"]
        - data["RMFSL"]
        + (
            data["MMMFFAQ027S"]
            / 1000.0
        )
    )


    # ========================================================
    # FOREIGN SHARE
    # ========================================================

    data["foreign_share"] = (
        data["ROWCESQ027S"]
        /
        data[
            "BOGZ1LM883164115Q"
        ]
    )


    invalid_share = (
        (
            data["foreign_share"]
            <= 0
        )
        |
        (
            data["foreign_share"]
            >= 1
        )
    )


    data.loc[
        invalid_share,
        "foreign_share",
    ] = np.nan


    # ========================================================
    # FOREIGN-ADJUSTED MZM
    # ========================================================

    data[
        "Foreign_adjusted_MZM_proxy"
    ] = (
        data[
            "MZM_proxy"
        ]
        /
        (
            1.0
            -
            data[
                "foreign_share"
            ]
        )
    )


    # ========================================================
    # HISTORICKÉ PRODLOUŽENÍ MZM
    # ========================================================

    extended_column = (
        "Foreign_adjusted_MZM_proxy_extended"
    )


    data[
        extended_column
    ] = (
        data[
            "Foreign_adjusted_MZM_proxy"
        ]
    )


    historical_mask = (
        data.index
        <
        FOREIGN_ADJUSTED_MZM_START_DATE
    )


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


    # ========================================================
    # S&P 500 — FRED + HISTORIE
    # ========================================================

    print()
    print(
        "Spojuji historický S&P 500 s FRED..."
    )


    sp500_daily = (
        raw[
            "SP500"
        ]
        .dropna()
        .sort_index()
    )


    if sp500_daily.empty:
        raise RuntimeError(
            "FRED SP500 nemá žádná použitelná data."
        )


    sp500_fred_monthly = (
        sp500_daily
        .resample("ME")
        .last()
    )


    sp500_fred_monthly.name = (
        "SP500_fred"
    )


    # FRED má přednost.
    # Historický XLSX doplní období,
    # které ve FRED chybí.
    sp500_combined = (
        sp500_fred_monthly
        .combine_first(
            sp500_historical_monthly
        )
    )


    sp500_combined.name = (
        "SP500_combined"
    )


    print(
        "Kombinovaný S&P 500:",
        sp500_combined.dropna().index[0].date(),
        "až",
        sp500_combined.dropna().index[-1].date(),
    )


    data = data.join(
        sp500_combined,
        how="left",
    )


    # ========================================================
    # HISTORICKÁ VALUACE
    # ========================================================

    data["raw_ratio"] = (
        data[
            "SP500_combined"
        ]
        /
        data[
            extended_column
        ]
    )


    data["index"] = (
        100.0
        *
        data[
            "raw_ratio"
        ]
        /
        RATIO_REFERENCE_VALUE
    )


    matched = (
        data[
            [
                "SP500_combined",
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


    if matched.empty:
        raise RuntimeError(
            "Nevznikla žádná společná historická "
            "pozorování S&P 500 a MZM."
        )


    # ========================================================
    # AKTUÁLNÍ SNAPSHOT
    # ========================================================

    latest_sp500_date = (
        sp500_daily.index[-1]
    )


    latest_sp500 = float(
        sp500_daily.iloc[-1]
    )


    latest_mzm_series = (
        data[
            extended_column
        ]
        .dropna()
        .sort_index()
    )


    if latest_mzm_series.empty:
        raise RuntimeError(
            "Foreign-Adjusted MZM Proxy je prázdná."
        )


    latest_mzm_date = (
        latest_mzm_series.index[-1]
    )


    latest_mzm = float(
        latest_mzm_series.iloc[-1]
    )


    current_raw_ratio = (
        latest_sp500
        /
        latest_mzm
    )


    current_index = (
        100.0
        *
        current_raw_ratio
        /
        RATIO_REFERENCE_VALUE
    )


    # ========================================================
    # HISTORIE PRO JSON
    # ========================================================

    history = []


    for date, row in matched.iterrows():

        history.append(
            {
                "date":
                    json_date(
                        date
                    ),

                "sp500":
                    json_number(
                        row[
                            "SP500_combined"
                        ],
                        6,
                    ),

                "foreign_adjusted_mzm":
                    json_number(
                        row[
                            extended_column
                        ],
                        6,
                    ),

                "raw_ratio":
                    json_number(
                        row[
                            "raw_ratio"
                        ],
                        9,
                    ),

                "index":
                    json_number(
                        row[
                            "index"
                        ],
                        6,
                    ),

                "kind":
                    "matched_monthly",
            }
        )


    # ========================================================
    # CHART POINTS
    # ========================================================

    chart_points = [
        dict(point)
        for point in history
    ]


    current_snapshot_appended = (
        False
    )


    if (
        not chart_points
        or
        pd.Timestamp(
            latest_sp500_date
        )
        >
        pd.Timestamp(
            chart_points[-1][
                "date"
            ]
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

        current_snapshot_appended = (
            True
        )


    # ========================================================
    # PRŮMĚRY
    # ========================================================

    end_date = pd.Timestamp(
        latest_sp500_date
    )


    five_year_start = (
        end_date
        -
        pd.DateOffset(
            years=5
        )
    )


    ten_year_start = (
        end_date
        -
        pd.DateOffset(
            years=10
        )
    )


    matched_5y = (
        matched[
            matched.index
            >= five_year_start
        ]
    )


    matched_10y = (
        matched[
            matched.index
            >= ten_year_start
        ]
    )


    five_year_average = (
        json_number(
            matched_5y[
                "index"
            ].mean(),
            6,
        )
        if not matched_5y.empty
        else None
    )


    ten_year_average = (
        json_number(
            matched_10y[
                "index"
            ].mean(),
            6,
        )
        if not matched_10y.empty
        else None
    )


    full_history_average = (
        json_number(
            matched[
                "index"
            ].mean(),
            6,
        )
    )


    # ========================================================
    # JSON
    # ========================================================

    payload = {

        "schema_version":
            5,

        "status":
            "ok",

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
            (
                "S&P 500 / "
                "Foreign-adjusted MZM "
                "proxy index"
            ),

        "history_start":
            json_date(
                matched.index[0]
            ),

        "history_end":
            json_date(
                matched.index[-1]
            ),

        "normalization": {

            "raw_ratio_reference":
                RATIO_REFERENCE_VALUE,

            "index_at_reference":
                100.0,

            "formula":
                (
                    "100 * raw_ratio / 0.15"
                ),
        },

        "averages": {

            "five_year":
                five_year_average,

            "ten_year":
                ten_year_average,

            "full_history":
                full_history_average,
        },

        # zpětná kompatibilita
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

        "history":
            history,

        "chart_points":
            chart_points,

        "data_sources": {

            "sp500_historical":
                "sp500w.xlsx",

            "sp500_current":
                "FRED SP500",

            "money":
                "FRED",

            "sp500_priority":
                (
                    "FRED where available; "
                    "sp500w.xlsx fills earlier history."
                ),
        },

        "methodology": {

            "mzm_proxy_formula":
                (
                    "M2MNS - RMFSL "
                    "+ MMMFFAQ027S / 1000"
                ),

            "foreign_share_formula":
                (
                    "ROWCESQ027S / "
                    "BOGZ1LM883164115Q"
                ),

            "foreign_adjusted_mzm_formula":
                (
                    "MZM_proxy / "
                    "(1 - foreign_share)"
                ),

            "historical_extension":
                (
                    "Before 1982, MZMSL is preferred "
                    "as the historical approximation."
                ),

            "sp500_history_note":
                (
                    "Historical S&P 500 is taken from "
                    "sp500w.xlsx and converted from weekly "
                    "observations to the final available close "
                    "of each month. FRED takes priority wherever "
                    "both sources overlap."
                ),

            "current_snapshot_note":
                (
                    "Current S&P 500 uses the latest "
                    "available daily FRED observation; "
                    "MZM uses the latest published "
                    "monthly value."
                ),

            "source":
                (
                    "Federal Reserve Bank of St. Louis, "
                    "FRED API, plus sp500w.xlsx"
                ),
        },
    }


    # ========================================================
    # SAVE
    # ========================================================

    OUTPUT_JSON.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )


    # ========================================================
    # DIAGNOSTIKA
    # ========================================================

    print()
    print(
        "=" * 72
    )

    print(
        "HOTOVO"
    )

    print(
        "=" * 72
    )


    print(
        "Výstup:",
        OUTPUT_JSON,
    )


    print(
        "Historie valuace:",
        json_date(
            matched.index[0]
        ),
        "až",
        json_date(
            matched.index[-1]
        ),
    )


    print(
        "Počet historických bodů:",
        len(
            history
        ),
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


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
