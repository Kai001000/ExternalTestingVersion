# utils/data.py (完整文件)
from pathlib import Path
import re
import pandas as pd
import streamlit as st
import polars as pl

from .config import MART_WEEKLY_DIR, MART_MONTHLY_DIR, MART_DAILY_ROLLING_DIR, BASE_DIR


def list_dataset_labels() -> list[str]:
    labels = set()
    for p in MART_WEEKLY_DIR.glob("mart_weekly_nsw_*.parquet"):
        m = re.search(r"mart_weekly_nsw_(.+)\.parquet$", p.name)
        if m:
            labels.add(m.group(1))
    return sorted(labels)


def _normalize_level(level: str) -> str:
    if level is None:
        return "NSW"
    s = str(level).strip()
    if not s:
        return "NSW"
    s_low = s.lower()
    if s_low == "nsw":
        return "NSW"
    if s_low == "region":
        return "REGION"
    if s_low == "suburb":
        return "SUBURB"
    if s_low == "postcode":
        return "POSTCODE"
    if s_low.startswith("nsw"):
        return "NSW"
    if s_low.startswith("region"):
        return "REGION"
    if s_low.startswith("suburb"):
        return "SUBURB"
    if s_low.startswith("postcode"):
        return "POSTCODE"
    if "全州" in s or "statewide" in s_low:
        return "NSW"
    if "大悉尼" in s or "区域" in s or "greater sydney" in s_low or "rest of nsw" in s_low:
        return "REGION"
    if "城区" in s:
        return "SUBURB"
    if "邮编" in s:
        return "POSTCODE"
    s_up = s.upper()
    if s_up in {"NSW", "REGION", "SUBURB", "POSTCODE"}:
        return s_up
    return "NSW"


@st.cache_data(show_spinner=False)
def load_weekly(level: str, label: str) -> pd.DataFrame:
    level = _normalize_level(level)
    if level == "NSW":
        path = MART_WEEKLY_DIR / f"mart_weekly_nsw_{label}.parquet"
    elif level == "REGION":
        path = MART_WEEKLY_DIR / f"mart_weekly_region_{label}.parquet"
    elif level == "SUBURB":
        path = MART_WEEKLY_DIR / f"mart_weekly_suburb_{label}.parquet"
    elif level == "POSTCODE":
        path = MART_WEEKLY_DIR / f"mart_weekly_postcode_{label}.parquet"
    else:
        path = MART_WEEKLY_DIR / f"mart_weekly_nsw_{label}.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    if "event_week_start" in df.columns:
        df["event_week_start"] = pd.to_datetime(df["event_week_start"], errors="coerce")
    return df


@st.cache_data(show_spinner=False)
def load_monthly(level: str, label: str) -> pd.DataFrame:
    level = _normalize_level(level)
    if level == "NSW":
        path = MART_MONTHLY_DIR / f"mart_monthly_nsw_{label}.parquet"
    elif level == "REGION":
        path = MART_MONTHLY_DIR / f"mart_monthly_region_{label}.parquet"
    elif level == "SUBURB":
        path = MART_MONTHLY_DIR / f"mart_monthly_suburb_{label}.parquet"
    elif level == "POSTCODE":
        path = MART_MONTHLY_DIR / f"mart_monthly_postcode_{label}.parquet"
    else:
        path = MART_MONTHLY_DIR / f"mart_monthly_nsw_{label}.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    if "event_month_start" in df.columns:
        df["event_month_start"] = pd.to_datetime(df["event_month_start"], errors="coerce")
    return df


# ========== 加载每日滚动 mart (Polars) ==========
@st.cache_data(show_spinner=False)
def load_daily_rolling(level: str) -> pl.DataFrame:
    level = _normalize_level(level)
    if level == "NSW":
        path = MART_DAILY_ROLLING_DIR / "daily_rolling_nsw.parquet"
    elif level == "REGION":
        path = MART_DAILY_ROLLING_DIR / "daily_rolling_region.parquet"
    elif level == "SUBURB":
        path = MART_DAILY_ROLLING_DIR / "daily_rolling_suburb.parquet"
    elif level == "POSTCODE":
        path = MART_DAILY_ROLLING_DIR / "daily_rolling_postcode.parquet"
    else:
        return pl.DataFrame()
    if not path.exists():
        return pl.DataFrame()
    df = pl.read_parquet(path)
    df = df.with_columns(pl.col("date").cast(pl.Date))
    return df


def _clean_region_series(s: pd.Series) -> pd.Series:
    x = s.astype(str).str.strip()
    null_tokens = {"none", "nan", "na", "n/a", "null", "unknow", "unknown", ""}
    x = x.where(~x.str.lower().isin(null_tokens), "")
    x = x.where(~x.isin(["None", "nan", "NaN"]), "")
    return x


def _normalize_postcode(s: pd.Series) -> pd.Series:
    x = s.astype(str).str.strip()
    null_tokens = {"none", "nan", "na", "n/a", "null", "unknow", "unknown", ""}
    x = x.where(~x.str.lower().isin(null_tokens), "")
    x = x.str.replace(r"\.0$", "", regex=True).str.strip()
    x_digits = x.str.extract(r"(\d+)", expand=False).fillna("")
    x_digits = x_digits.where(x_digits == "", x_digits.str.zfill(4))
    return x_digits


def normalize_region_values(df: pd.DataFrame, level: str) -> pd.DataFrame:
    level = _normalize_level(level)
    d = df.copy()
    if "region" not in d.columns:
        d["region"] = "NSW" if level == "NSW" else ""
    if level == "POSTCODE":
        d["region"] = _normalize_postcode(d["region"])
    else:
        d["region"] = _clean_region_series(d["region"])
    return d


@st.cache_data(show_spinner=False)
def load_dim_suburb_postcode() -> pl.DataFrame:
    path = BASE_DIR / "Processed" / "dim" / "dim_suburb_postcode.csv"
    if not path.exists():
        return pl.DataFrame()
    df = pl.read_csv(path, schema_overrides={"suburb": pl.Utf8, "postcode": pl.Utf8})
    df = df.with_columns([
        pl.col("suburb").str.strip_chars(),
        pl.col("postcode").str.strip_chars().str.replace(r"\.0$", "").str.zfill(4),
    ])
    for c in ["primary_postcode_sales_rows", "suburb_total_sales_rows", "primary_postcode_share"]:
        if c in df.columns:
            df = df.with_columns(pl.col(c).cast(pl.Float64))
    df = df.filter(pl.col("suburb").is_not_null() & (pl.col("suburb") != ""))
    df = df.filter(pl.col("postcode").is_not_null() & (pl.col("postcode") != ""))
    return df


@st.cache_data(show_spinner=False)
def load_dim_postcode_gccsa() -> pl.DataFrame:
    """加载邮编→大悉尼/新州其他区域映射，仅保留所需列"""
    path = BASE_DIR / "Processed" / "dim" / "dim_postcode_gccsa.csv"
    if not path.exists():
        return pl.DataFrame()
    # 仅读取需要的列，避免因 postcode_name 列包含非数字导致解析错误
    df = pl.read_csv(
        path,
        columns=["postcode", "region_group"],
        schema_overrides={"postcode": pl.Utf8, "region_group": pl.Utf8}
    )
    df = df.with_columns([
        pl.col("postcode").str.strip_chars().str.replace(r"\.0$", "").str.zfill(4),
        pl.col("region_group").str.strip_chars(),
    ])
    # 过滤掉无效邮编
    df = df.filter(pl.col("postcode").is_not_null() & (pl.col("postcode") != ""))
    return df