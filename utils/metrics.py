# utils/metrics.py
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ROLL_WINDOWS


def coerce_numeric_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    d = df.copy()
    for c in cols:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def filter_price_range(
    df: pd.DataFrame,
    price_cols: list[str],
    price_min_exclusive: int,
    price_max: int
) -> pd.DataFrame:
    d = df.copy()
    for c in price_cols:
        if c in d.columns:
            d = d[d[c].isna() | ((d[c] > price_min_exclusive) & (d[c] <= price_max))]
    return d


def add_rolling_medians(weekly: pd.DataFrame) -> pd.DataFrame:
    """
    Adds rolling medians over weekly_median_price.
    Requires:
      - event_week_start
      - region
      - dwelling_group
      - weekly_median_price
    Adds:
      - roll4_median
      - roll13_median
    """
    d = weekly.copy()

    if "event_week_start" in d.columns:
        d["event_week_start"] = pd.to_datetime(d["event_week_start"], errors="coerce")

    needed = {"event_week_start", "region", "dwelling_group", "weekly_median_price"}
    missing = needed - set(d.columns)
    if missing:
        # fail soft: return as-is
        return d

    d = d.sort_values(["region", "dwelling_group", "event_week_start"])

    def _roll_median(s: pd.Series, win: int) -> pd.Series:
        return s.rolling(win, min_periods=win).median()

    # roll4
    if "roll4_median" not in d.columns:
        d["roll4_median"] = (
            d.groupby(["region", "dwelling_group"])["weekly_median_price"]
            .transform(lambda s: _roll_median(s, ROLL_WINDOWS.get("roll4", 4)))
        )

    # roll13
    if "roll13_median" not in d.columns:
        d["roll13_median"] = (
            d.groupby(["region", "dwelling_group"])["weekly_median_price"]
            .transform(lambda s: _roll_median(s, ROLL_WINDOWS.get("roll13", 13)))
        )

    return d


def ensure_stability_columns(
    weekly: pd.DataFrame,
    *,
    min_sales: int = 10,
    mom_weeks: int = 4,
    qoq_weeks: int = 13,
    mom_abs_max: float = 0.03,
    qoq_abs_max: float = 0.06,
) -> pd.DataFrame:
    """
    Make sure the dataframe has ALL "stable" columns used by charts AND tables.

    Requires (soft):
      - event_week_start
      - region
      - dwelling_group
      - weekly_sales_count
      - weekly_median_price

    Produces:
      - roll4_median, roll13_median (if missing)
      - mom_pct: roll13_median pct_change(mom_weeks)
      - qoq_pct: roll13_median pct_change(qoq_weeks)
      - is_stable: (sales>=min_sales) & abs(mom)<=mom_abs_max & abs(qoq)<=qoq_abs_max
      - stable_mom: mom_pct where stable else NaN
      - stable_qoq: qoq_pct where stable else NaN
      - stable_28_median: roll4_median where stable else NaN
      - stable_28_sales: weekly_sales_count where stable else NaN
      - stable_week: event_week_start where stable else NaT
    """
    d = weekly.copy()

    if "event_week_start" in d.columns:
        d["event_week_start"] = pd.to_datetime(d["event_week_start"], errors="coerce")

    # Coerce important numerics
    d = coerce_numeric_cols(
        d,
        ["weekly_sales_count", "weekly_median_price", "roll4_median", "roll13_median"],
    )

    # Add rolling medians if missing
    if "roll4_median" not in d.columns or "roll13_median" not in d.columns:
        d = add_rolling_medians(d)

    needed = {"region", "dwelling_group", "event_week_start", "roll13_median"}
    if not needed.issubset(d.columns):
        # Can't compute stability reliably; still return with placeholders
        for col in [
            "mom_pct", "qoq_pct", "is_stable",
            "stable_mom", "stable_qoq",
            "stable_28_median", "stable_28_sales",
            "stable_week",
        ]:
            if col not in d.columns:
                d[col] = np.nan
        return d

    d = d.sort_values(["region", "dwelling_group", "event_week_start"])

    # pct changes from roll13 (more stable baseline)
    d["mom_pct"] = (
        d.groupby(["region", "dwelling_group"])["roll13_median"]
        .pct_change(mom_weeks)
    )
    d["qoq_pct"] = (
        d.groupby(["region", "dwelling_group"])["roll13_median"]
        .pct_change(qoq_weeks)
    )

    if "weekly_sales_count" not in d.columns:
        d["weekly_sales_count"] = np.nan

    # stable flag
    d["is_stable"] = (
        (d["weekly_sales_count"] >= min_sales)
        & d["mom_pct"].abs().le(mom_abs_max)
        & d["qoq_pct"].abs().le(qoq_abs_max)
    )

    # stable outputs for lines/tables
    d["stable_mom"] = np.where(d["is_stable"], d["mom_pct"], np.nan)
    d["stable_qoq"] = np.where(d["is_stable"], d["qoq_pct"], np.nan)
    d["stable_28_median"] = np.where(d["is_stable"], d.get("roll4_median"), np.nan)
    d["stable_28_sales"] = np.where(d["is_stable"], d["weekly_sales_count"], np.nan)
    d["stable_week"] = np.where(d["is_stable"], d["event_week_start"], pd.NaT)

    return d