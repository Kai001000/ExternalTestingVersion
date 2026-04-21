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


def _make_suburb_key_series(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
         .str.strip()
         .str.lower()
         .str.replace(r"&", " and ", regex=True)
         .str.replace(r"[^a-z0-9]+", "_", regex=True)
         .str.replace(r"_+", "_", regex=True)
         .str.strip("_")
    )


def _infer_greater_sydney_postcodes(dim_postcode_gccsa: pd.DataFrame) -> set[str]:
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
    d[postcode_col] = _normalize_str(d[postcode_col]).str.replace(r"\.0$", "", regex=True).str.zfill(4)

    d = d[[suburb_col, postcode_col]].drop_duplicates()
    d = d.rename(columns={suburb_col: "_suburb_join", postcode_col: "postcode"})

    out = out.rename(columns={"region": "_suburb_join"}).merge(d, on="_suburb_join", how="left")
    out = out.rename(columns={"_suburb_join": "region"})
    out["postcode"] = out["postcode"].fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(4)
    return out


def _attach_region16(df: pd.DataFrame, dim_region16: pd.DataFrame | None) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        out["region16_name"] = ""
        out["region16_key"] = ""
        return out

    if dim_region16 is None or dim_region16.empty:
        out["region16_name"] = ""
        out["region16_key"] = ""
        return out

    d = dim_region16.copy()

    suburb_key_col = "suburb_key" if "suburb_key" in d.columns else None
    postcode_col = "postcode" if "postcode" in d.columns else None
    region_name_col = "region_name" if "region_name" in d.columns else None
    region_key_col = "region_key" if "region_key" in d.columns else None

    if suburb_key_col is None or postcode_col is None or region_name_col is None:
        out["region16_name"] = ""
        out["region16_key"] = ""
        return out

    out["postcode"] = out["postcode"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(4)
    out["_suburb_key"] = _make_suburb_key_series(out["region"])

    d[suburb_key_col] = d[suburb_key_col].astype(str).str.strip().str.lower()
    d[postcode_col] = d[postcode_col].astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(4)
    d[region_name_col] = d[region_name_col].astype(str).str.strip()

    keep_cols = [suburb_key_col, postcode_col, region_name_col]
    if region_key_col is not None:
        keep_cols.append(region_key_col)

    d = d[keep_cols].drop_duplicates()

    out = out.merge(
        d.rename(columns={
            suburb_key_col: "_suburb_key",
            postcode_col: "postcode",
            region_name_col: "region16_name",
            region_key_col: "region16_key" if region_key_col is not None else region_name_col
        }),
        on=["_suburb_key", "postcode"],
        how="left",
    )

    if "region16_key" not in out.columns:
        out["region16_key"] = ""

    out["region16_name"] = out["region16_name"].fillna("").astype(str)
    out["region16_key"] = out["region16_key"].fillna("").astype(str)

    out = out.drop(columns=["_suburb_key"], errors="ignore")
    return out


# =========================
# NEW: right-edge-only unstable rule
# =========================
def apply_right_edge_stability_rule(
    df: pd.DataFrame,
    group_cols: list[str],
    date_col: str = "date",
    raw_stable_col: str = "raw_stable",
    out_col: str = "stable",
) -> pd.DataFrame:
    """
    Rule:
    - First compute raw_stable point-by-point
    - Find the LAST raw_stable date in each group
    - Mark ALL points on or before that last raw_stable date as stable
    - Therefore unstable points can only appear on the RIGHT side

    Example:
      T T F T T F F  ->  T T T T T F F
    """
    if df is None or df.empty:
        out = pd.DataFrame() if df is None else df.copy()
        if not out.empty and out_col not in out.columns:
            out[out_col] = False
        return out

    out = df.copy()
    out[date_col] = _coerce_date(out[date_col])

    if raw_stable_col not in out.columns:
        out[raw_stable_col] = False

    out[raw_stable_col] = out[raw_stable_col].fillna(False).astype(bool)
    out[out_col] = False

    if not group_cols:
        stable_dates = out.loc[out[raw_stable_col], date_col].dropna()
        if stable_dates.empty:
            out[out_col] = False
        else:
            cutoff = stable_dates.max()
            out[out_col] = out[date_col] <= cutoff
        return out

    for _, idx in out.groupby(group_cols, dropna=False).groups.items():
        idx = list(idx)
        sub = out.loc[idx, [date_col, raw_stable_col]].copy()
        stable_dates = sub.loc[sub[raw_stable_col], date_col].dropna()

        if stable_dates.empty:
            out.loc[idx, out_col] = False
        else:
            cutoff = stable_dates.max()
            out.loc[idx, out_col] = out.loc[idx, date_col] <= cutoff

    return out


def _pick_latest_valid_row_per_region(d: pd.DataFrame, required_notna: list[str]) -> pd.DataFrame:
    if d.empty:
        return d
    dd = d.dropna(subset=required_notna).copy()
    if dd.empty:
        return dd
    dd = dd.sort_values(["region", "date"])
    return dd.groupby("region", as_index=False).tail(1)


def _pick_latest_stable_row_per_region(
    d: pd.DataFrame,
    stable_ratio: float,
    base_sales: dict[str, float] | None
) -> pd.DataFrame:
    """
    Stable rule updated:
    1) raw_stable = sales_28d >= base_sales * stable_ratio
    2) apply right-edge-only unstable rule
    3) pick latest stable row
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

    out["raw_stable"] = np.where(
        out["base_sales"] > 0,
        out["sales_28d"] >= out["base_sales"] * float(stable_ratio),
        True,
    )

    out = apply_right_edge_stability_rule(
        out,
        group_cols=["region"],
        date_col="date",
        raw_stable_col="raw_stable",
        out_col="is_stable",
    )

    stable = out[out["is_stable"]].copy()
    if stable.empty:
        return stable

    stable = stable.sort_values(["region", "date"])
    return stable.groupby("region", as_index=False).tail(1)


def _calc_change_at_anchor(
    series_df: pd.DataFrame,
    anchor_date: pd.Timestamp,
    lag_days: int,
    value_col: str = "rolling_median",
) -> float | None:
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
    if snapshot.empty:
        return snapshot

    out = snapshot.copy()
    out["mom"] = None
    out["qoq"] = None

    full_series = full_series.copy()
    full_series["date"] = _coerce_date(full_series["date"])

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
# New public: full suburb rank snapshot
# =========================
def build_suburb_rank_snapshot(
    daily_suburb: pd.DataFrame,
    dim_suburb_postcode: pd.DataFrame | None,
    dim_postcode_gccsa: pd.DataFrame | None,
    dim_region16: pd.DataFrame | None,
    dwelling: str,
    only_greater_sydney: bool = True,
    use_stable: bool = False,
    stable_ratio: float | None = None,
) -> pd.DataFrame:
    if daily_suburb is None or daily_suburb.empty:
        return pd.DataFrame()

    d = daily_suburb.copy()

    needed = ["date", "region", "dwelling_group", "rolling_median", "sales_28d"]
    for c in needed:
        if c not in d.columns:
            return pd.DataFrame()

    d["date"] = _coerce_date(d["date"])
    d["region"] = _normalize_str(d["region"])
    d["dwelling_group"] = _normalize_str(d["dwelling_group"])

    d = d.dropna(subset=["date"]).copy()
    d = d[d["dwelling_group"].str.upper() == str(dwelling).upper()].copy()
    if d.empty:
        return pd.DataFrame()

    d = _attach_suburb_postcode(d, dim_suburb_postcode if dim_suburb_postcode is not None else pd.DataFrame())

    if only_greater_sydney:
        gs_postcodes = _infer_greater_sydney_postcodes(dim_postcode_gccsa if dim_postcode_gccsa is not None else pd.DataFrame())
        if gs_postcodes:
            d = d[d["postcode"].astype(str).isin(gs_postcodes)].copy()

    if d.empty:
        return pd.DataFrame()

    d_valid = d.dropna(subset=["rolling_median"]).copy()
    if d_valid.empty:
        return pd.DataFrame()

    if use_stable:
        if stable_ratio is None:
            stable_ratio = 0.55
        snap = _pick_latest_stable_row_per_region(d_valid, stable_ratio=float(stable_ratio), base_sales=None)
    else:
        snap = _pick_latest_valid_row_per_region(d_valid, required_notna=["rolling_median"])

    if snap.empty:
        return pd.DataFrame()

    snap = _calc_mom_qoq_for_snapshot(
        full_series=d_valid,
        snapshot=snap,
        group_cols=["region", "dwelling_group"],
        value_col="rolling_median",
    )

    snap = _attach_region16(snap, dim_region16 if dim_region16 is not None else pd.DataFrame())

    out = snap[[
        "region",
        "postcode",
        "region16_name",
        "date",
        "rolling_median",
        "sales_28d",
        "mom",
        "qoq",
    ]].copy()

    out = out.rename(columns={
        "region": "Suburb",
        "postcode": "Postcode",
        "region16_name": "Market Region",
        "date": "As of",
        "rolling_median": "28d median",
        "sales_28d": "28d sales",
        "mom": "MoM",
        "qoq": "QoQ",
    })

    out["Postcode"] = out["Postcode"].fillna("").astype(str)
    out["Market Region"] = out["Market Region"].fillna("").astype(str)
    out["As of"] = _coerce_date(out["As of"])

    return out.reset_index(drop=True)


def filter_rank_snapshot_table(
    snapshot_df: pd.DataFrame,
    metric: str,
    selected_region16: list[str] | None = None,
    sales_min: int | None = None,
    sales_max: int | None = None,
    median_min: float | None = None,
    median_max: float | None = None,
    change_min: float | None = None,
    change_max: float | None = None,
) -> pd.DataFrame:
    if snapshot_df is None or snapshot_df.empty:
        return pd.DataFrame()

    metric = str(metric).strip()
    if metric not in {"MoM", "QoQ"}:
        metric = "MoM"

    d = snapshot_df.copy()

    d["28d sales"] = pd.to_numeric(d["28d sales"], errors="coerce")
    d["28d median"] = pd.to_numeric(d["28d median"], errors="coerce")
    d["MoM"] = pd.to_numeric(d["MoM"], errors="coerce")
    d["QoQ"] = pd.to_numeric(d["QoQ"], errors="coerce")
    d["As of"] = _coerce_date(d["As of"])

    if selected_region16:
        d = d[d["Market Region"].isin(selected_region16)].copy()

    if sales_min is not None:
        d = d[d["28d sales"].fillna(-np.inf) >= float(sales_min)].copy()
    if sales_max is not None:
        d = d[d["28d sales"].fillna(np.inf) <= float(sales_max)].copy()

    if median_min is not None:
        d = d[d["28d median"].fillna(-np.inf) >= float(median_min)].copy()
    if median_max is not None:
        d = d[d["28d median"].fillna(np.inf) <= float(median_max)].copy()

    if change_min is not None:
        d = d[d[metric].fillna(-np.inf) >= float(change_min)].copy()
    if change_max is not None:
        d = d[d[metric].fillna(np.inf) <= float(change_max)].copy()

    d = d.dropna(subset=[metric, "28d median"]).copy()
    if d.empty:
        return pd.DataFrame()

    d = d.sort_values(metric, ascending=False).reset_index(drop=True)

    out = d[["Suburb", "Postcode", "Market Region", "As of", "28d median", "28d sales", metric]].copy()
    out["As of"] = out["As of"].apply(fmt_date)
    out["28d median"] = out["28d median"].apply(fmt_float0)
    out["28d sales"] = out["28d sales"].apply(fmt_int)
    out[metric] = out[metric].apply(fmt_pct)

    return out


def build_stable_top_bottom_tables(
    daily_suburb: pd.DataFrame,
    dim_suburb_postcode: pd.DataFrame | None,
    dim_postcode_gccsa: pd.DataFrame | None,
    dwelling: str,
    change_kind: str = "mom",
    top_n: int = 5,
    only_greater_sydney: bool = True,
    use_stable: bool = False,
    stable_ratio: float | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    snap = build_suburb_rank_snapshot(
        daily_suburb=daily_suburb,
        dim_suburb_postcode=dim_suburb_postcode,
        dim_postcode_gccsa=dim_postcode_gccsa,
        dim_region16=None,
        dwelling=dwelling,
        only_greater_sydney=only_greater_sydney,
        use_stable=use_stable,
        stable_ratio=stable_ratio,
    )

    metric = "MoM" if str(change_kind).lower() == "mom" else "QoQ"
    full = filter_rank_snapshot_table(snap, metric=metric)
    if full.empty:
        return pd.DataFrame(), pd.DataFrame()

    top = full.head(int(top_n)).copy()
    bot = full.tail(int(top_n)).iloc[::-1].copy()
    return top, bot


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
            stable_ratio = 0.55
        snap = _pick_latest_stable_row_per_region(d_valid, stable_ratio=float(stable_ratio), base_sales=base_sales)
    else:
        snap = _pick_latest_valid_row_per_region(d_valid, required_notna=["rolling_median"])

    if snap.empty:
        return pd.DataFrame()

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
