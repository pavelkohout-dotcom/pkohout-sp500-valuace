#!/usr/bin/env python3

"""
Automatická aktualizace valuace S&P 500 vůči Foreign-Adjusted MZM Proxy.

Metodika:

    MZM_proxy = M2MNS - RMFSL + MMMFFAQ027S / 1000

    foreign_share =
        ROWCESQ027S / BOGZ1LM883164115Q

    Foreign_adjusted_MZM_proxy =
        MZM_proxy / (1 - foreign_share)

    valuation_raw =
        SP500 / Foreign_adjusted_MZM_proxy

    valuation_index =
        100 * valuation_raw / 0.15

Historie:
- zachovává se celá dostupná historická řada;
- S&P 500 je pro historický graf převeden na měsíční poslední pozorování;
- aktuální bod používá poslední dostupnou denní hodnotu S&P 500;
- měnový jmenovatel používá poslední dostupnou hodnotu
  Foreign-Adjusted MZM Proxy.

Zdroj:
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


# ------------------------------------------------------------
# FRED API
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
# FRED DOWNLOAD
# ============================================================

def fetch_fred(series_id: str) -> pd.Series:
    """
    Stáhne celou dostupnou historii jedné FRED řady.

    Používá oficiální JSON API:
    /fred/series/observations

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
                        "pkohout-sp500-valuace/1.0"
                },
            )

            response.raise_for_status()

            payload = response.json()

            if "observations" not in payload:
                raise RuntimeError(
                    f"{series_id}: API nevrátilo pole observations"
                )

            observations = payload["observations"]

            if not observations:
                raise RuntimeError(
                    f"{series_id}: FRED nevrátil žádná pozorování"
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

            # FRED používá "." pro missing value.
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

            series = df["value"].copy()

            series.name = series_id

            if series.empty:
                raise RuntimeError(
                    f"{series_id}: po odstranění missing values "
                    "nezůstala žádná data"
                )

            print(
                f"{series_id}: "
                f"{series.index[0].date()} až "
                f"{series.index[-1].date()}, "
                f"počet {len(series):,}, "
                f"poslední hodnota "
                f"{series.iloc[-1]:,.4f}"
            )

            return series

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
            requests.exceptions.JSONDecodeError,
        ) as error:

            last_error = error

            print(
                f"{series_id}: dočasná chyba:"
            )

            print(error)

            if attempt < 4:

                wait_seconds = (
                    10 * attempt
                )

                print(
                    f"{series_id}: čekám "
                    f"{wait_seconds} sekund..."
                )

                time.sleep(
                    wait_seconds
                )

        except Exception:
            # Logické / datové chyby nechceme maskovat
            # čtyřmi identickými pokusy.
            raise

    raise RuntimeError(
        f"{series_id}: FRED se nepodařilo stáhnout "
        "ani po 4 pokusech."
    ) from last_error


# ============================================================
# JSON HELPERS
# ============================================================

def json_number(
    value,
    digits=None,
):

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


# ============================================================
# MONTHLY RESAMPLING
# ============================================================

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

    print()
    print(
        "Stahuji celou dostupnou historii z FRED API..."
    )


    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    raw = {}

    for name, series_id in SERIES.items():

        raw[name] = fetch_fred(
            series_id
        )

        # mírné šetření API
        time.sleep(0.5)


    # --------------------------------------------------------
    # MONTHLY SERIES
    # --------------------------------------------------------

    print()
    print(
        "Připravuji měsíční řady..."
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
    # FORWARD FILL
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


    # --------------------------------------------------------
    # MZM PROXY
    # --------------------------------------------------------

    data["MZM_proxy"] = (
        data["M2MNS"]
        - data["RMFSL"]
        + data["MMMFFAQ027S"]
        / 1000.0
    )


    # --------------------------------------------------------
    # FOREIGN OWNERSHIP SHARE
    # --------------------------------------------------------

    data["foreign_share"] = (
        data["ROWCESQ027S"]
        / data[
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


    # --------------------------------------------------------
    # FOREIGN-ADJUSTED MZM
    # --------------------------------------------------------

    data[
        "Foreign_adjusted_MZM_proxy"
    ] = (
        data["MZM_proxy"]
        /
        (
            1.0
            - data["foreign_share"]
        )
    )


    # --------------------------------------------------------
    # HISTORICAL EXTENSION
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # S&P 500
    # --------------------------------------------------------

    sp500_daily = (
        raw["SP500"]
        .dropna()
        .sort_index()
    )


    if sp500_daily.empty:

        raise RuntimeError(
            "S&P 500 nemá žádná použitelná data."
        )


    sp500_monthly = (
        sp500_daily
        .resample("ME")
        .last()
    )


    sp500_monthly.name = (
        "SP500"
    )


    data = data.join(
        sp500_monthly,
        how="left",
    )


    # --------------------------------------------------------
    # VALUATION
    # --------------------------------------------------------

    data["raw_ratio"] = (
        data["SP500"]
        /
        data[
            extended_column
        ]
    )


    data["index"] = (
        100.0
        *
        data["raw_ratio"]
        /
        RATIO_REFERENCE_VALUE
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


    if matched.empty:

        raise RuntimeError(
            "Nevznikla žádná společná historická "
            "pozorování S&P 500 a MZM proxy."
        )


    # --------------------------------------------------------
    # CURRENT S&P 500
    # --------------------------------------------------------

    latest_sp500_date = (
        sp500_daily.index[-1]
    )


    latest_sp500 = float(
        sp500_daily.iloc[-1]
    )


    # --------------------------------------------------------
    # CURRENT MZM
    # --------------------------------------------------------

    latest_mzm_series = (
        data[
            extended_column
        ]
        .dropna()
        .sort_index()
    )


    if latest_mzm_series.empty:

        raise RuntimeError(
            "Foreign-Adjusted MZM Proxy "
            "nemá žádná použitelná data."
        )


    latest_mzm_date = (
        latest_mzm_series.index[-1]
    )


    latest_mzm = float(
        latest_mzm_series.iloc[-1]
    )


    # --------------------------------------------------------
    # CURRENT RATIO
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # COMPLETE HISTORICAL SERIES
    # --------------------------------------------------------

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
                        row["SP500"],
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
                        row["index"],
                        6,
                    ),

                "kind":
                    "matched_monthly",
            }
        )


    # --------------------------------------------------------
    # CHART POINTS
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # AVERAGES
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # PAYLOAD
    # --------------------------------------------------------

    payload = {

        "schema_version":
            4,

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
                    "Before 1982, "
                    "MZMSL is preferred "
                    "as the historical "
                    "approximation."
                ),

            "current_snapshot_note":
                (
                    "Current S&P 500 "
                    "uses the latest "
                    "available daily observation; "
                    "MZM uses the latest "
                    "published monthly value."
                ),

            "source":
                (
                    "Federal Reserve Bank "
                    "of St. Louis, FRED API"
                ),
        },
    }


    # --------------------------------------------------------
    # SAVE JSON
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
    # DIAGNOSTICS
    # --------------------------------------------------------

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
        "Historie:",
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


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
