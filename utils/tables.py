# utils/tables.py
from __future__ import annotations

import pandas as pd
import numpy as np


# =========================
# Formatting helpers
# =========================
def fmt_float0(x) -> str:
    if x is None:
        return ""
    try:
        if isinstance(x, float) and np.isnan(x):
            return ""
        return f"{float(x):,.0f}"
    except Exception:
        return ""


def fmt_int(x) -> str:
    if x is None:
        return ""
    try:
        if isinstance(x, float) and np.isnan(x):
            return ""
        return f"{int(round(float(x))):,}"
    except Exception:
        return ""


def fmt_pct(x) -> str:
    if x is None:
        return ""
    try:
        if isinstance(x, float) and np.isnan(x):
            return ""
        return f"{float(x) * 100:.1f}%"
    except Exception:
        return ""


def fmt_date(x) -> str:
    if x is None:
        return ""
    try:
        d = pd.to_datetime(x)
        if pd.isna(d):
            return ""
        return d.strftime("%Y-%m-%d")
    except Exception:
        return ""


# =========================
# Internal utilities
# =========================
def _normalize_str(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip()


def _coerce_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce").dt.normalize()


def _infer_greater_sydney_postcodes(dim_postcode_gccsa: pd.DataFrame) -> set[str]:
    """
    Works with:
      - your current dim_postcode_gccsa.csv: columns ['postcode','region_group']
    Also supports other schemas.
    """
    if dim_postcode_gccsa is None or dim_postcode_gccsa.empty:
        return set()

    d = dim_postcode_gccsa.copy()

    pc_col = None
    for c in ["postcode", "post_code", "postal_code", "POA_CODE_2021", "poa_code", "poa"]:
        if c in d.columns:
            pc_col = c
            break
    if pc_col is None:
        return set()

    name_col = None
    for c in ["region_group", "gccsa_name", "gccsa", "name", "GCCSA_NAME_2021"]:
        if c in d.columns:
            name_col = c
            break
    if name_col is None:
        return set()

    d[pc_col] = _normalize_str(d[pc_col])
    d[name_col] = _normalize_str(d[name_col])

    # your file uses "Greater Sydney" / "Rest of NSW"
    mask = d[name_col].str.contains("Greater Sydney", case=False, na=False) | d[name_col].str.contains(
        "Sydney", case=False, na=False
    )
    return set(d.loc[mask, pc_col].dropna().astype(str).str.strip().tolist())


def _attach_suburb_postcode(daily_suburb: pd.DataFrame, dim_suburb_postcode: pd.DataFrame) -> pd.DataFrame:
    out = daily_suburb.copy()
    if out.empty:
        return out

    out["region"] = _normalize_str(out["region"])

    if dim_suburb_postcode is None or dim_suburb_postcode.empty:
        out["postcode"] = ""
        return out

    d = dim_suburb_postcode.copy()

    suburb_col = None
    for c in ["suburb", "SUBURB_NAME", "locality", "name"]:
        if c in d.columns:
            suburb_col = c
            break
    postcode_col = None
    for c in ["postcode", "post_code", "postal_code", "POA_CODE_2021", "poa_code", "poa"]:
        if c in d.columns:
            postcode_col = c
            break

    if suburb_col is None or postcode_col is None:
        out["postcode"] = ""
        return out

    d[suburb_col] = _normalize_str(d[suburb_col])
    d[postcode_col] = _normalize_str(d[postcode_col])

    d = d[[suburb_col, postcode_col]].drop_duplicates()
    d = d.rename(columns={suburb_col: "_suburb_join", postcode_col: "postcode"})
    out = out.rename(columns={"region": "_suburb_join"}).merge(d, on="_suburb_join", how="left")
    out = out.rename(columns={"_suburb_join": "region"})
    out["postcode"] = out["postcode"].fillna("").astype(str)
    return out


def _pick_latest_valid_row_per_region(d: pd.DataFrame, required_notna: list[str]) -> pd.DataFrame:
    if d.empty:
        return d
    dd = d.dropna(subset=required_notna).copy()
    if dd.empty:
        return dd
    dd = dd.sort_values(["region", "date"])
    return dd.groupby("region", as_index=False).tail(1)


def _pick_latest_stable_row_per_region(d: pd.DataFrame, stable_ratio: float, base_sales: dict[str, float] | None) -> pd.DataFrame:
    """
    Stable condition: sales_28d >= base_sales[region] * stable_ratio (if base_sales known and >0)
    If base_sales missing or 0 -> treat as stable.
    """
    if d.empty:
        return d

    out = d.copy()
    out["region"] = _normalize_str(out["region"])

    if base_sales is None:
        max_date = out["date"].max()
        one_year_ago = max_date - pd.DateOffset(years=1)
        base_df = out[out["date"] >= one_year_ago]
        base_sales = base_df.groupby("region")["sales_28d"].median().to_dict()

    out["base_sales"] = out["region"].map(base_sales).fillna(0)

    out["is_stable"] = np.where(
        out["base_sales"] > 0,
        out["sales_28d"] >= out["base_sales"] * float(stable_ratio),
        True,
    )

    stable = out[out["is_stable"]].copy()
    if stable.empty:
        return stable

    stable = stable.sort_values(["region", "date"])
    return stable.groupby("region", as_index=False).tail(1)


# ---------- NEW: Anchor-lag change calculator ----------
def _calc_change_at_anchor(
    series_df: pd.DataFrame,
    anchor_date: pd.Timestamp,
    lag_days: int,
    value_col: str = "rolling_median",
) -> float | None:
    """
    change = value(anchor_date) / value(anchor_date - lag_days) - 1
    Requires BOTH values present and non-null.
    """
    if series_df is None or series_df.empty or anchor_date is None:
        return None

    anchor_date = pd.to_datetime(anchor_date).normalize()
    target_date = anchor_date - pd.Timedelta(days=int(lag_days))

    a = series_df.loc[series_df["date"] == anchor_date, value_col]
    b = series_df.loc[series_df["date"] == target_date, value_col]
    if a.empty or b.empty:
        return None

    a_val = a.iloc[0]
    b_val = b.iloc[0]
    if pd.isna(a_val) or pd.isna(b_val) or float(b_val) == 0.0:
        return None

    return float(a_val) / float(b_val) - 1.0


def _calc_mom_qoq_for_snapshot(
    full_series: pd.DataFrame,
    snapshot: pd.DataFrame,
    group_cols: list[str],
    value_col: str = "rolling_median",
) -> pd.DataFrame:
    """
    For each row in snapshot, compute:
      mom = value(as_of) / value(as_of-28) - 1
      qoq = value(as_of) / value(as_of-84) - 1
    using the full_series within the same group.
    """
    if snapshot.empty:
        return snapshot

    out = snapshot.copy()
    out["mom"] = None
    out["qoq"] = None

    # Pre-split for speed
    full_series = full_series.copy()
    full_series["date"] = _coerce_date(full_series["date"])

    # group by keys -> compute
    for idx, row in out.iterrows():
        key = tuple(row[c] for c in group_cols)
        mask = np.ones(len(full_series), dtype=bool)
        for c, v in zip(group_cols, key):
            mask &= (full_series[c] == v)
        g = full_series.loc[mask, ["date", value_col]].dropna(subset=[value_col]).copy()
        if g.empty:
            continue
        g = g.sort_values("date")

        anchor_date = row["date"]
        out.at[idx, "mom"] = _calc_change_at_anchor(g, anchor_date, 28, value_col=value_col)
        out.at[idx, "qoq"] = _calc_change_at_anchor(g, anchor_date, 84, value_col=value_col)

    return out


# =========================
# Public: Stable top/bottom ranking tables (SUBURB)
# =========================
def build_stable_top_bottom_tables(
    daily_suburb: pd.DataFrame,
    dim_suburb_postcode: pd.DataFrame | None,
    dim_postcode_gccsa: pd.DataFrame | None,
    dwelling: str,
    change_kind: str = "mom",  # "mom" or "qoq"
    top_n: int = 5,
    only_greater_sydney: bool = True,
    use_stable: bool = False,
    stable_ratio: float | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Expected daily_suburb columns:
      - date, region, dwelling_group, rolling_median, sales_28d
    NOTE: We DO NOT rely on precomputed mom/qoq columns anymore.
    """
    if daily_suburb is None or daily_suburb.empty:
        return pd.DataFrame(), pd.DataFrame()

    d = daily_suburb.copy()

    needed = ["date", "region", "dwelling_group", "rolling_median", "sales_28d"]
    for c in needed:
        if c not in d.columns:
            return pd.DataFrame(), pd.DataFrame()

    d["date"] = _coerce_date(d["date"])
    d["region"] = _normalize_str(d["region"])
    d["dwelling_group"] = _normalize_str(d["dwelling_group"])

    d = d.dropna(subset=["date"]).copy()
    d = d[d["dwelling_group"].str.upper() == str(dwelling).upper()].copy()
    if d.empty:
        return pd.DataFrame(), pd.DataFrame()

    # join postcode for filtering & display
    d = _attach_suburb_postcode(d, dim_suburb_postcode if dim_suburb_postcode is not None else pd.DataFrame())

    if only_greater_sydney:
        gs_postcodes = _infer_greater_sydney_postcodes(dim_postcode_gccsa if dim_postcode_gccsa is not None else pd.DataFrame())
        if gs_postcodes:
            d = d[d["postcode"].astype(str).isin(gs_postcodes)].copy()

    if d.empty:
        return pd.DataFrame(), pd.DataFrame()

    # only keep valid rolling_median points for anchor logic
    d_valid = d.dropna(subset=["rolling_median"]).copy()
    if d_valid.empty:
        return pd.DataFrame(), pd.DataFrame()

    # choose snapshot rows
    if use_stable:
        if stable_ratio is None:
            stable_ratio = 0.6
        snap = _pick_latest_stable_row_per_region(d_valid, stable_ratio=float(stable_ratio), base_sales=None)
    else:
        snap = _pick_latest_valid_row_per_region(d_valid, required_notna=["rolling_median"])

    if snap.empty:
        return pd.DataFrame(), pd.DataFrame()

    # compute mom/qoq at snapshot anchors (YOUR desired definition)
    snap = _calc_mom_qoq_for_snapshot(
        full_series=d_valid,
        snapshot=snap,
        group_cols=["region", "dwelling_group"],
        value_col="rolling_median",
    )

    if change_kind not in ["mom", "qoq"]:
        change_kind = "mom"

    snap["change"] = snap[change_kind]
    snap = snap.dropna(subset=["change", "rolling_median"]).copy()
    if snap.empty:
        return pd.DataFrame(), pd.DataFrame()

    # rank
    snap = snap.sort_values("change", ascending=False)
    top = snap.head(int(top_n)).copy()
    bot = snap.tail(int(top_n)).sort_values("change", ascending=True).copy()

    def _pretty(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        out = df[["region", "postcode", "date", "rolling_median", "sales_28d", "change"]].copy()
        out = out.rename(columns={
            "region": "Suburb",
            "postcode": "Postcode",
            "date": "As of",
            "rolling_median": "28d median",
            "sales_28d": "28d sales",
            "change": change_kind.upper(),
        })
        out["As of"] = out["As of"].apply(fmt_date)
        out["28d median"] = out["28d median"].apply(fmt_float0)
        out["28d sales"] = out["28d sales"].apply(fmt_int)
        out[change_kind.upper()] = out[change_kind.upper()].apply(fmt_pct)
        return out

    return _pretty(top), _pretty(bot)


# =========================
# Public: Region overview table
# =========================
def build_region_overview_table(
    daily_df: pd.DataFrame,
    regions: list[str],
    dwelling: str,
    use_stable: bool = False,
    stable_ratio: float | None = None,
    base_sales: dict[str, float] | None = None,
) -> pd.DataFrame:
    """
    daily_df expected:
      date, region, dwelling_group, rolling_median, sales_28d
    NOTE: We compute MoM/QoQ using anchor-lag definition (no reliance on precomputed columns).
    """
    if daily_df is None or daily_df.empty:
        return pd.DataFrame()

    d = daily_df.copy()
    needed = ["date", "region", "dwelling_group", "rolling_median", "sales_28d"]
    for c in needed:
        if c not in d.columns:
            return pd.DataFrame()

    d["date"] = _coerce_date(d["date"])
    d["region"] = _normalize_str(d["region"])
    d["dwelling_group"] = _normalize_str(d["dwelling_group"])

    d = d.dropna(subset=["date"]).copy()
    d = d[d["dwelling_group"].str.upper() == str(dwelling).upper()].copy()
    if regions:
        regions_norm = [str(r).strip() for r in regions]
        d = d[d["region"].isin(regions_norm)].copy()

    if d.empty:
        return pd.DataFrame()

    d_valid = d.dropna(subset=["rolling_median"]).copy()
    if d_valid.empty:
        return pd.DataFrame()

    if use_stable:
        if stable_ratio is None:
            stable_ratio = 0.6
        snap = _pick_latest_stable_row_per_region(d_valid, stable_ratio=float(stable_ratio), base_sales=base_sales)
    else:
        snap = _pick_latest_valid_row_per_region(d_valid, required_notna=["rolling_median"])

    if snap.empty:
        return pd.DataFrame()

    # compute mom/qoq at snapshot anchors
    snap = _calc_mom_qoq_for_snapshot(
        full_series=d_valid,
        snapshot=snap,
        group_cols=["region", "dwelling_group"],
        value_col="rolling_median",
    )

    out = snap[["region", "date", "rolling_median", "sales_28d", "mom", "qoq"]].copy()
    out = out.rename(columns={
        "region": "Region",
        "date": "As of",
        "rolling_median": "28d median",
        "sales_28d": "28d sales",
        "mom": "MoM",
        "qoq": "QoQ",
    })

    out["As of"] = out["As of"].apply(fmt_date)
    out["28d median"] = out["28d median"].apply(fmt_float0)
    out["28d sales"] = out["28d sales"].apply(fmt_int)
    out["MoM"] = out["MoM"].apply(fmt_pct)
    out["QoQ"] = out["QoQ"].apply(fmt_pct)

    if regions:
        order = {r: i for i, r in enumerate([str(r).strip() for r in regions])}
        out["_ord"] = out["Region"].map(order).fillna(10_000).astype(int)
        out = out.sort_values("_ord").drop(columns=["_ord"])

    return out.reset_index(drop=True)