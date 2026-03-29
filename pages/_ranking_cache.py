import pandas as pd
import polars as pl
import streamlit as st

from utils.data import load_daily_rolling, load_dim_postcode_gccsa, load_dim_region16, load_dim_suburb_postcode
from utils.tables import _infer_greater_sydney_postcodes, _make_suburb_key_series


STABLE_RATIO = 0.6
NEEDED_COLS = ["date", "region", "dwelling_group", "rolling_median", "sales_28d"]


def _normalize_postcode_expr(expr: pl.Expr) -> pl.Expr:
    return (
        expr.cast(pl.Utf8)
        .str.strip_chars()
        .str.replace(r"\.0$", "")
        .str.zfill(4)
    )


@st.cache_data(ttl=3600, show_spinner=False)
def load_rank_base_frame(dwelling: str) -> pd.DataFrame:
    daily_suburb = load_daily_rolling("SUBURB")
    if daily_suburb.is_empty():
        return pd.DataFrame()

    daily = (
        daily_suburb
        .select(NEEDED_COLS)
        .filter(
            pl.col("dwelling_group") == dwelling,
            pl.col("rolling_median").is_not_null(),
            pl.col("date").is_not_null(),
            pl.col("region").is_not_null(),
        )
        .with_columns(
            pl.col("date").cast(pl.Date),
            pl.col("region").cast(pl.Utf8).str.strip_chars(),
            pl.col("dwelling_group").cast(pl.Utf8).str.strip_chars(),
        )
    )
    if daily.is_empty():
        return pd.DataFrame()

    dim_suburb_postcode = load_dim_suburb_postcode()
    if not dim_suburb_postcode.is_empty():
        suburb_map = (
            dim_suburb_postcode
            .select(
                pl.col("suburb").cast(pl.Utf8).str.strip_chars().alias("region"),
                _normalize_postcode_expr(pl.col("postcode")).alias("postcode"),
            )
            .unique()
        )
        daily = daily.join(suburb_map, on="region", how="left")
    else:
        daily = daily.with_columns(pl.lit("").alias("postcode"))

    dim_postcode_gccsa = load_dim_postcode_gccsa()
    if not dim_postcode_gccsa.is_empty():
        gs_postcodes = sorted(_infer_greater_sydney_postcodes(dim_postcode_gccsa.to_pandas()))
        if gs_postcodes:
            daily = daily.filter(pl.col("postcode").is_in(gs_postcodes))

    if daily.is_empty():
        return pd.DataFrame()

    return daily.to_pandas()


def _latest_snapshot(base_df: pd.DataFrame) -> pd.DataFrame:
    if base_df.empty:
        return pd.DataFrame()
    return (
        base_df
        .sort_values(["region", "date"], kind="stable")
        .groupby("region", as_index=False, sort=False)
        .tail(1)
        .reset_index(drop=True)
    )


def _latest_stable_snapshot(base_df: pd.DataFrame, stable_ratio: float) -> pd.DataFrame:
    if base_df.empty:
        return pd.DataFrame()

    frame = base_df.copy()
    max_date = frame["date"].max()
    one_year_ago = max_date - pd.DateOffset(years=1)
    base_sales = (
        frame.loc[frame["date"] >= one_year_ago]
        .groupby("region", sort=False)["sales_28d"]
        .median()
        .rename("base_sales")
    )

    frame = frame.join(base_sales, on="region")
    threshold = frame["base_sales"] * float(stable_ratio)
    frame["raw_stable"] = frame["base_sales"].gt(0) & frame["sales_28d"].ge(threshold)
    frame.loc[frame["base_sales"].le(0) | frame["base_sales"].isna(), "raw_stable"] = True

    cutoffs = (
        frame.loc[frame["raw_stable"], ["region", "date"]]
        .groupby("region", sort=False)["date"]
        .max()
        .rename("stable_cutoff")
    )
    frame = frame.join(cutoffs, on="region")
    stable = frame.loc[frame["stable_cutoff"].notna() & frame["date"].le(frame["stable_cutoff"])].copy()
    if stable.empty:
        return pd.DataFrame()

    return (
        stable
        .sort_values(["region", "date"], kind="stable")
        .groupby("region", as_index=False, sort=False)
        .tail(1)
        .reset_index(drop=True)
    )


def _mark_stable_rows(base_df: pd.DataFrame, stable_ratio: float) -> pd.DataFrame:
    if base_df.empty:
        return pd.DataFrame()

    frame = base_df.copy()
    max_date = frame["date"].max()
    one_year_ago = max_date - pd.DateOffset(years=1)
    base_sales = (
        frame.loc[frame["date"] >= one_year_ago]
        .groupby("region", sort=False)["sales_28d"]
        .median()
        .rename("base_sales")
    )

    frame = frame.join(base_sales, on="region")
    threshold = frame["base_sales"] * float(stable_ratio)
    frame["raw_stable"] = frame["base_sales"].gt(0) & frame["sales_28d"].ge(threshold)
    frame.loc[frame["base_sales"].le(0) | frame["base_sales"].isna(), "raw_stable"] = True

    cutoffs = (
        frame.loc[frame["raw_stable"], ["region", "date"]]
        .groupby("region", sort=False)["date"]
        .max()
        .rename("stable_cutoff")
    )
    frame = frame.join(cutoffs, on="region")
    frame["is_stable"] = frame["stable_cutoff"].notna() & frame["date"].le(frame["stable_cutoff"])
    return frame


def _attach_change_columns(base_df: pd.DataFrame, snapshot_df: pd.DataFrame, stable_ratio: float) -> pd.DataFrame:
    if snapshot_df.empty:
        return snapshot_df

    stable_series = _mark_stable_rows(base_df, stable_ratio)
    stable_series = stable_series.loc[stable_series["is_stable"], ["region", "date", "rolling_median"]].copy()
    stable_series = stable_series.rename(columns={"rolling_median": "stable_anchor_median"})

    yoy_ref = stable_series.rename(columns={"stable_anchor_median": "median_365d"})
    yoy_ref["date"] = yoy_ref["date"] + pd.Timedelta(days=365)

    out = snapshot_df.merge(stable_series.rename(columns={"stable_anchor_median": "current_stable_median"}), on=["region", "date"], how="left")
    out = out.merge(yoy_ref, on=["region", "date"], how="left")

    out["stable_yoy"] = out["current_stable_median"] / out["median_365d"] - 1.0
    out.loc[
        out["current_stable_median"].isna() | out["median_365d"].isna() | out["median_365d"].eq(0),
        "stable_yoy",
    ] = pd.NA

    return out.drop(columns=["current_stable_median", "median_365d"], errors="ignore")


def _attach_region16(snapshot_df: pd.DataFrame) -> pd.DataFrame:
    if snapshot_df.empty:
        return snapshot_df.assign(region_name="")

    dim_region16 = load_dim_region16()
    if dim_region16.is_empty():
        return snapshot_df.assign(region_name="")

    mapping = dim_region16.to_pandas().copy()
    if not {"suburb_key", "postcode", "region_name"}.issubset(mapping.columns):
        return snapshot_df.assign(region_name="")

    mapping["suburb_key"] = mapping["suburb_key"].astype(str).str.strip().str.lower()
    mapping["postcode"] = mapping["postcode"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(4)
    mapping["region_name"] = mapping["region_name"].astype(str).str.strip()
    mapping = mapping[["suburb_key", "postcode", "region_name"]].drop_duplicates()

    out = snapshot_df.copy()
    out["suburb_key"] = _make_suburb_key_series(out["region"])
    out["postcode"] = out["postcode"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(4)
    out = out.merge(mapping, on=["suburb_key", "postcode"], how="left")
    out["region_name"] = out["region_name"].fillna("")
    return out.drop(columns=["suburb_key"], errors="ignore")


@st.cache_data(ttl=3600, show_spinner=False)
def load_ranking_snapshot(dwelling: str, calibre: str, stable_ratio: float | None = None):
    base_df = load_rank_base_frame(dwelling)
    if base_df.empty:
        return pd.DataFrame()

    base_df = base_df.copy()
    base_df["date"] = pd.to_datetime(base_df["date"], errors="coerce").dt.normalize()
    base_df = base_df.dropna(subset=["date", "rolling_median"]).copy()
    if base_df.empty:
        return pd.DataFrame()

    if calibre == "stable":
        snapshot = _latest_stable_snapshot(base_df, STABLE_RATIO if stable_ratio is None else float(stable_ratio))
    else:
        snapshot = _latest_snapshot(base_df)

    if snapshot.empty:
        return pd.DataFrame()

    effective_stable_ratio = STABLE_RATIO if stable_ratio is None else float(stable_ratio)
    snapshot = _attach_change_columns(base_df, snapshot, effective_stable_ratio)
    snapshot = _attach_region16(snapshot)

    out = snapshot.rename(
        columns={
            "region": "Suburb",
            "postcode": "Postcode",
            "region_name": "Region16",
            "date": "As of",
            "rolling_median": "28d median",
            "sales_28d": "28d sales",
            "stable_yoy": "Stable YoY",
        }
    )

    out["Postcode"] = out["Postcode"].fillna("").astype(str)
    out["Region16"] = out["Region16"].fillna("").astype(str)
    out["As of"] = pd.to_datetime(out["As of"], errors="coerce").dt.normalize()

    return out[
        ["Suburb", "Postcode", "Region16", "As of", "28d median", "28d sales", "Stable YoY"]
    ].reset_index(drop=True)


def load_ranking_table(dwelling: str, calibre: str):
    return load_ranking_snapshot(dwelling, calibre, STABLE_RATIO if calibre == "stable" else None)


def warm_ranking_cache():
    for dwelling in ("HOUSE", "UNIT"):
        load_rank_base_frame(dwelling)
        for calibre in ("stable", "normal"):
            load_ranking_snapshot(dwelling, calibre, STABLE_RATIO if calibre == "stable" else None)
