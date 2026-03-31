from html import escape

import numpy as np
import pandas as pd
import polars as pl
import streamlit as st

from utils.charts import build_band_chart, build_interactive_chart
from utils.config import BASE_DIR, IS_EXTERNAL_MODE
from utils.data import ANALYTICS_PRICE_MAX, ANALYTICS_PRICE_MIN, add_underlying_trend, load_daily_rolling, load_dim_postcode_gccsa, load_dim_region16, load_dim_suburb_postcode, load_filtered_fact_sales
from utils.i18n import ensure_lang, t
from utils.tables import apply_right_edge_stability_rule, fmt_date, fmt_float0, fmt_int, fmt_pct
from utils.ui import inject_app_theme, sidebar_common

st.markdown(
    """
    <style>
    [data-testid="stHeader"] {
        height: 0rem;
        min-height: 0rem;
        padding: 0;
    }
    [data-testid="stToolbar"] {
        display: none;
    }
    section[data-testid="stMain"] > div:first-child {
        padding-top: 1.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


PRICE_BANDS = [
    (0, 750_000, "<750k"),
    (750_000, 1_200_000, "750k-1.2M"),
    (1_200_000, 2_000_000, "1.2M-2M"),
    (2_000_000, 3_000_000, "2M-3M"),
    (3_000_000, float("inf"), ">3M"),
]
BAND_NAMES = [band[2] for band in PRICE_BANDS]
STABLE_RATIO = 0.6
LONG_TREND_MIN_MEDIAN_SALES = 20
LOWER_GEO_LONG_TREND_MIN_MEDIAN_SALES = 5
TIME_OPTIONS = ["1 Month", "3 Month", "6 Month", "YTD", "1 Year", "3 Year", "5 Year", "10 Year", "Max"]
LINE_DISPLAY_MODES = [t("display_mode_dual"), t("display_mode_short"), t("display_mode_long")]


def _inject_market_view_css():
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1240px;
            padding-top: 1.2rem;
            padding-bottom: 2.6rem;
        }
        .mv-title {
            font-size: 2.1rem;
            font-weight: 800;
            color: #1f2937;
            line-height: 1.15;
            margin: 0;
        }
        .mv-subtitle {
            color: #6b7280;
            font-size: 0.96rem;
            margin-top: 0.35rem;
            margin-bottom: 0.85rem;
        }
        .mv-badge {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            background: #e0efff;
            color: #175cd3;
            border: 1px solid #b2ddff;
            padding: 0.38rem 0.78rem;
            font-size: 0.86rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .mv-filter-label {
            color: #6b7280;
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            margin-bottom: 0.2rem;
        }
        .mv-divider {
            height: 2.4rem;
            width: 1px;
            background: rgba(148, 163, 184, 0.35);
            margin: 1.55rem auto 0 auto;
        }
        .mv-card-header-row {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            margin-bottom: 0.8rem;
        }
        .mv-card-actions {
            display: flex;
            align-items: flex-end;
            gap: 0.75rem;
            flex-wrap: wrap;
            min-width: 360px;
        }
        .mv-inline-filter {
            min-width: 160px;
        }
        .mv-kpi-card {
            background: #ffffff;
            border: 1px solid rgba(15, 23, 42, 0.06);
            border-radius: 20px;
            padding: 1rem 1.05rem;
            min-height: 138px;
        }
        .mv-kpi-label {
            color: #64748b;
            font-size: 0.83rem;
            font-weight: 700;
            margin-bottom: 0.45rem;
        }
        .mv-kpi-value {
            color: #0f172a;
            font-size: 1.75rem;
            font-weight: 800;
            line-height: 1.1;
        }
        .mv-kpi-sub {
            margin-top: 0.5rem;
            color: #64748b;
            font-size: 0.9rem;
        }
        .mv-section-title {
            color: #111827;
            font-size: 1.3rem;
            font-weight: 800;
            margin-bottom: 0.2rem;
        }
        .mv-section-subtitle {
            color: #6b7280;
            font-size: 0.92rem;
            margin-bottom: 0.8rem;
        }
        .mv-stat-card {
            background: #f8fafc;
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 16px;
            padding: 0.8rem 0.9rem;
        }
        .mv-stat-label {
            color: #64748b;
            font-size: 0.78rem;
            font-weight: 700;
            margin-bottom: 0.25rem;
        }
        .mv-stat-value {
            color: #111827;
            font-size: 1.08rem;
            font-weight: 800;
        }
        .mv-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
            border-radius: 999px;
            padding: 0.14rem 0.52rem;
            font-size: 0.82rem;
            font-weight: 700;
        }
        .mv-pill-up {
            color: #027a48;
            background: #ecfdf3;
        }
        .mv-pill-down {
            color: #b42318;
            background: #fef3f2;
        }
        .mv-pill-flat {
            color: #475467;
            background: #f2f4f7;
        }
        .mv-metrics-hero,
        .mv-support-card {
            background: var(--color-background-secondary, rgba(255, 255, 255, 0.72));
            border: 0;
            box-shadow: none;
        }
        .mv-metrics-hero {
            border-radius: var(--border-radius-lg, 24px);
            padding: 1.2rem 1.3rem 1.05rem 1.3rem;
        }
        .mv-metrics-top {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
        }
        .mv-metrics-label {
            color: var(--color-text-secondary, #6b7280);
            font-size: 0.84rem;
            font-weight: 400;
            margin-bottom: 0.3rem;
        }
        .mv-hero-value {
            color: var(--color-text-primary, #111827);
            font-size: 34px;
            font-weight: 500;
            letter-spacing: -0.02em;
            line-height: 1.05;
        }
        .mv-hero-point {
            color: var(--color-text-primary, #111827);
            font-size: 15px;
            font-weight: 500;
            text-align: right;
            line-height: 1.3;
        }
        .mv-hero-divider {
            border-top: 0.5px solid var(--color-border-tertiary, rgba(148, 163, 184, 0.35));
            margin: 14px 0;
        }
        .mv-hero-bottom {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 10px;
            align-items: stretch;
        }
        .mv-hero-meta-label,
        .mv-support-label,
        .mv-support-sub {
            color: var(--color-text-secondary, #6b7280);
        }
        .mv-hero-meta-label,
        .mv-support-label {
            font-size: 13px;
            font-weight: 400;
            margin-bottom: 0.25rem;
        }
        .mv-hero-meta-value,
        .mv-support-value,
        .mv-support-range-value {
            color: var(--color-text-primary, #111827);
            font-weight: 500;
        }
        .mv-hero-meta-value {
            font-size: 1rem;
            line-height: 1.25;
        }
        .mv-hero-meta-sub,
        .mv-support-sub {
            font-size: 13px;
            font-weight: 400;
            margin-top: 0.18rem;
            line-height: 1.3;
        }
        .mv-support-card {
            border-radius: var(--border-radius-md, 18px);
            padding: 18px 20px;
            min-height: 128px;
            height: 100%;
        }
        .mv-compact-card {
            background: var(--color-background-secondary, rgba(255, 255, 255, 0.72));
            border: 0;
            box-shadow: none;
            border-radius: var(--border-radius-md, 18px);
            padding: 0.05rem 0.1rem 0.15rem 0.1rem;
            min-height: 128px;
        }
        .mv-support-value {
            font-size: 22px;
            line-height: 1.1;
        }
        .mv-yoy-value {
            font-size: 26px;
            line-height: 1.1;
            font-weight: 600;
        }
        .mv-yoy-up {
            color: #027a48;
        }
        .mv-yoy-down {
            color: #b42318;
        }
        .mv-yoy-flat {
            color: #475467;
        }
        .mv-support-range {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.8rem;
            margin-top: 0.55rem;
        }
        .mv-support-range-caption {
            color: var(--color-text-secondary, #6b7280);
            font-size: 13px;
            font-weight: 400;
            margin-bottom: 0.18rem;
        }
        .mv-support-range-value {
            font-size: 22px;
            line-height: 1.25;
        }
        .mv-band-summary {
            background: var(--color-background-secondary, #f8fafc);
            border: 0;
            border-radius: var(--border-radius-md, 16px);
            padding: 12px 14px;
            min-height: 0;
        }
        .mv-band-label {
            color: var(--color-text-tertiary, #6b7280);
            font-size: 13px;
            font-weight: 500;
            letter-spacing: 0.02em;
        }
        .mv-band-value {
            color: var(--color-text-primary, #111827);
            font-size: 20px;
            font-weight: 500;
            margin-top: 4px;
            line-height: 1.2;
        }
        .mv-band-summary-descriptor {
            color: var(--color-text-tertiary, #6b7280);
            font-size: 12px;
            font-weight: 400;
            margin-top: 12px;
        }
        .mv-band-yoy-row {
            margin-top: 8px;
        }
        .mv-band-yoy-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            border-radius: 4px;
            padding: 2px 7px;
            font-size: 13px;
            font-weight: 500;
            line-height: 1.2;
        }
        .mv-band-yoy-pill-up {
            background: #EAF3DE;
            color: #3B6D11;
        }
        .mv-band-yoy-pill-down {
            background: #FCEBEB;
            color: #A32D2D;
        }
        .mv-band-yoy-pill-flat {
            background: var(--color-background-primary, #ffffff);
            color: var(--color-text-secondary, #6b7280);
            border: 0.5px solid var(--color-border-secondary, rgba(148, 163, 184, 0.45));
        }
        .mv-band-yoy-arrow {
            width: 0;
            height: 0;
            display: inline-block;
        }
        .mv-band-yoy-arrow-up {
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-bottom: 6px solid currentColor;
        }
        .mv-band-yoy-arrow-down {
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 6px solid currentColor;
        }
        .mv-band-yoy-arrow-flat {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: currentColor;
        }
        .mv-band-summary-sub {
            color: var(--color-text-secondary, #6b7280);
            font-size: 12px;
            font-weight: 400;
            margin-top: 8px;
        }
        .mv-card-grid {
            display: grid;
            gap: 10px;
            align-items: stretch;
        }
        .mv-card-grid-3 {
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }
        .mv-card-grid-2 {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
        .mv-card-grid .mv-support-card {
            min-width: 0;
        }
        .mv-band-filter-shell {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            margin-top: 8px;
            margin-bottom: 8px;
        }
        .mv-band-filter-left,
        .mv-band-filter-right {
            display: flex;
            align-items: center;
            gap: 10px;
            min-width: 0;
        }
        .mv-band-filter-left {
            flex: 1 1 auto;
        }
        .mv-band-filter-right {
            flex: 0 0 auto;
        }
        .mv-band-inline-label {
            color: var(--color-text-tertiary, #6b7280);
            font-size: 12px;
            font-weight: 400;
            white-space: nowrap;
        }
        .mv-band-filter-left .stMultiSelect,
        .mv-band-filter-right .stSelectbox {
            flex: 1 1 auto;
            min-width: 0;
            margin-bottom: 0;
        }
        .mv-band-filter-right .stSelectbox {
            width: 170px;
        }
        .stMultiSelect [data-baseweb="select"] > div {
            min-height: auto;
            padding-top: 0;
            padding-bottom: 0;
            gap: 6px;
            align-items: center;
        }
        .stMultiSelect [data-baseweb="tag"] {
            background: #FCEBEB;
            color: #A32D2D;
            border: 0.5px solid #F09595;
            border-radius: 6px;
            padding: 3px 10px;
            font-size: 12px;
            font-weight: 500;
            line-height: 1.2;
        }
        .stMultiSelect [data-baseweb="tag"] span,
        .stMultiSelect [data-baseweb="tag"] div {
            color: inherit;
            font-size: inherit;
            font-weight: inherit;
        }
        .stMultiSelect [data-baseweb="select"] input {
            min-width: 24px !important;
            width: 24px !important;
        }
        .stMultiSelect [data-baseweb="select"] svg {
            display: none;
        }
        .stMultiSelect [data-baseweb="select"] > div::after {
            content: "+";
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            border: 0.5px dashed var(--color-border-secondary, rgba(148, 163, 184, 0.45));
            border-radius: 6px;
            background: transparent;
            color: var(--color-text-secondary, #6b7280);
            font-size: 14px;
            font-weight: 500;
            flex: 0 0 24px;
        }
        @media (max-width: 900px) {
            .mv-band-filter-shell {
                flex-direction: column;
                align-items: stretch;
            }
            .mv-band-filter-right {
                justify-content: space-between;
            }
            .mv-band-filter-right .stSelectbox {
                width: 100%;
                max-width: 220px;
            }
        }
        .mv-rank-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.92rem;
        }
        .mv-rank-table th {
            text-align: left;
            color: #64748b;
            font-size: 0.78rem;
            font-weight: 800;
            padding: 0.55rem 0.45rem;
            border-bottom: 1px solid rgba(148, 163, 184, 0.25);
        }
        .mv-rank-table td {
            padding: 0.7rem 0.45rem;
            border-bottom: 1px solid rgba(148, 163, 184, 0.16);
            color: #111827;
            vertical-align: middle;
        }
        .mv-rank-table tr:last-child td {
            border-bottom: 0;
        }
        .mv-muted {
            color: #6b7280;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.45rem;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.25);
            background: #f8fafc;
        }
        .stTabs [aria-selected="true"] {
            background: #eff6ff;
            border-color: #93c5fd;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _preset_start_end(min_date: pd.Timestamp, max_date: pd.Timestamp, preset: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    maxd = pd.to_datetime(max_date).normalize()
    mind = pd.to_datetime(min_date).normalize()
    if preset == "Max":
        return mind, maxd
    if preset == "YTD":
        return max(pd.Timestamp(year=maxd.year, month=1, day=1), mind), maxd
    mapping = {
        "1 Month": pd.DateOffset(months=1),
        "3 Month": pd.DateOffset(months=3),
        "6 Month": pd.DateOffset(months=6),
        "1 Year": pd.DateOffset(years=1),
        "3 Year": pd.DateOffset(years=3),
        "5 Year": pd.DateOffset(years=5),
        "10 Year": pd.DateOffset(years=10),
    }
    return max(maxd - mapping.get(preset, pd.DateOffset(years=1)), mind), maxd


def _preset_label(preset: str) -> str:
    return {
        "1 Month": "过去1个月",
        "3 Month": "过去3个月",
        "6 Month": "过去6个月",
        "YTD": "今年以来",
        "1 Year": "过去12个月",
        "3 Year": "过去3年",
        "5 Year": "过去5年",
        "10 Year": "过去10年",
        "Max": "全部时间",
    }.get(preset, preset)


@st.cache_data(ttl=3600, show_spinner=False)
def _latest_dat_folder_label() -> str:
    dat_root = BASE_DIR / "RawData" / "DAT"
    if not dat_root.exists():
        return "N/A"
    year_dirs = sorted(path for path in dat_root.iterdir() if path.is_dir() and path.name.isdigit())
    if not year_dirs:
        return "N/A"
    latest_year = year_dirs[-1]
    folders = sorted(path.name for path in latest_year.iterdir() if path.is_dir())
    if not folders:
        return latest_year.name
    latest_folder = folders[-1]
    if len(latest_folder) == 8 and latest_folder.isdigit():
        return f"{latest_folder[:4]}-{latest_folder[4:6]}-{latest_folder[6:]}"
    return latest_folder


def _level_label(level: str) -> str:
    return {
        "NSW": "NSW",
        "REGION": "区域",
        "REGION16": "16区",
        "AREA": "Suburb / Postcode",
    }.get(level, level)


def _format_currency(value) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"${fmt_float0(value)}"


def _trend_pill(value) -> str:
    if value is None or pd.isna(value):
        return '<span class="mv-pill mv-pill-flat">N/A</span>'
    value = float(value)
    if value > 0:
        arrow = "&#9650;"
        cls = "mv-pill-up"
    elif value < 0:
        arrow = "&#9660;"
        cls = "mv-pill-down"
    else:
        arrow = "&bull;"
        cls = "mv-pill-flat"
    return f'<span class="mv-pill {cls}">{arrow} {escape(fmt_pct(value))}</span>'


def _trend_value_html(value) -> str:
    if value is None or pd.isna(value):
        return '<div class="mv-support-value mv-yoy-flat">N/A</div>'
    value = float(value)
    if value > 0:
        arrow = "▲"
        cls = "mv-yoy-up"
    elif value < 0:
        arrow = "▼"
        cls = "mv-yoy-down"
    else:
        arrow = "•"
        cls = "mv-yoy-flat"
    return f'<div class="mv-support-value mv-yoy-value {cls}">{arrow} {escape(fmt_pct(value))}</div>'


def _band_yoy_pill_html(value) -> str:
    if isinstance(value, str):
        if value == "insufficient_history":
            return '<span class="mv-band-yoy-pill mv-band-yoy-pill-flat"><span class="mv-band-yoy-arrow mv-band-yoy-arrow-flat"></span>Insufficient history</span>'
        return f'<span class="mv-band-yoy-pill mv-band-yoy-pill-flat"><span class="mv-band-yoy-arrow mv-band-yoy-arrow-flat"></span>{escape(value)}</span>'
    if value is None or pd.isna(value):
        return '<span class="mv-band-yoy-pill mv-band-yoy-pill-flat"><span class="mv-band-yoy-arrow mv-band-yoy-arrow-flat"></span>N/A</span>'
    value = float(value)
    if value > 0:
        pill_cls = "mv-band-yoy-pill-up"
        arrow_cls = "mv-band-yoy-arrow-up"
    elif value < 0:
        pill_cls = "mv-band-yoy-pill-down"
        arrow_cls = "mv-band-yoy-arrow-down"
    else:
        pill_cls = "mv-band-yoy-pill-flat"
        arrow_cls = "mv-band-yoy-arrow-flat"
    return f'<span class="mv-band-yoy-pill {pill_cls}"><span class="mv-band-yoy-arrow {arrow_cls}"></span>{escape(fmt_pct(value))}</span>'


def _dwelling_label(dwelling: str) -> str:
    return {"HOUSE": "House", "UNIT": "Unit"}.get(dwelling, dwelling.title())


def _render_metric_card(container, label: str, body_html: str, subtext: str | None = None, *, body_caption: str | None = None):
    with container:
        card = st.container(border=True)
        with card:
            st.markdown(
                f"""
                <div class="mv-support-label">{escape(label)}</div>
                {body_html}
                """,
                unsafe_allow_html=True,
            )
            if body_caption:
                st.caption(body_caption)
            if subtext:
                st.caption(subtext)


def _render_equal_width_metric_grid(cards: list[tuple[str, str, str | None]], columns_count: int):
    grid_class = "mv-card-grid-3" if columns_count == 3 else "mv-card-grid-2"
    card_html = []
    for label, body_html, subtext in cards:
        sub_html = f'<div class="mv-support-sub">{escape(subtext)}</div>' if subtext else ""
        card_html.append(
            f"""
            <div class="mv-support-card">
              <div class="mv-support-label">{escape(label)}</div>
              {body_html}
              {sub_html}
            </div>
            """
        )
    st.markdown(f'<div class="mv-card-grid {grid_class}">{"".join(card_html)}</div>', unsafe_allow_html=True)


def _empty_focus_metrics() -> dict[str, object]:
    return {
        "latest_median": None,
        "latest_point": None,
        "range_high": None,
        "range_low": None,
        "stable_yoy": None,
        "sales": None,
    }


def _build_focus_metrics(summary_full_df: pd.DataFrame, summary_visible_df: pd.DataFrame) -> dict[str, object]:
    stable_full_df = summary_full_df[summary_full_df["stable"].fillna(False) & summary_full_df["rolling_median"].notna()].copy()
    if stable_full_df.empty:
        return _empty_focus_metrics()
    stable_full_df["date"] = pd.to_datetime(stable_full_df["date"], errors="coerce").dt.normalize()
    stable_full_df = stable_full_df[stable_full_df["date"].notna()].copy()
    if stable_full_df.empty:
        return _empty_focus_metrics()
    stable_full_df = stable_full_df.sort_values("date")
    latest = stable_full_df.iloc[-1]
    yoy_ref = stable_full_df[["region", "date", "rolling_median"]].rename(columns={"rolling_median": "median_365d"})
    yoy_ref["date"] = pd.to_datetime(yoy_ref["date"], errors="coerce").dt.normalize() + pd.Timedelta(days=365)
    latest_key = pd.DataFrame(
        {
            "region": [latest["region"]],
            "date": [pd.to_datetime(latest["date"], errors="coerce").normalize()],
        }
    )
    latest_key["date"] = pd.to_datetime(latest_key["date"], errors="coerce").dt.normalize()
    latest_with_yoy = latest_key.merge(yoy_ref, on=["region", "date"], how="left")
    median_365d = latest_with_yoy["median_365d"].iloc[0] if not latest_with_yoy.empty else None
    stable_yoy = None
    if median_365d is not None and not pd.isna(median_365d) and float(median_365d) != 0:
        stable_yoy = latest["rolling_median"] / median_365d - 1.0
    stable_visible_df = summary_visible_df[summary_visible_df["stable"].fillna(False) & summary_visible_df["rolling_median"].notna()].copy()
    range_high = None
    range_low = None
    if not stable_visible_df.empty:
        range_high = stable_visible_df["rolling_median"].max()
        range_low = stable_visible_df["rolling_median"].min()
    return {
        "latest_median": latest["rolling_median"],
        "latest_point": latest["date"],
        "range_high": range_high,
        "range_low": range_low,
        "stable_yoy": stable_yoy,
        "sales": latest.get("sales_28d"),
    }


def _render_main_kpis(metrics: dict[str, object], region_label: str, preset: str, dwelling: str, stable_ratio: float, pipeline_update_label: str):
    latest_point = fmt_date(metrics["latest_point"]) if metrics["latest_point"] is not None and not pd.isna(metrics["latest_point"]) else "N/A"
    context_label = f"{_preset_label(preset)} · {_dwelling_label(dwelling)}"
    hero_html = f"""
    <div class="mv-metrics-hero">
      <div class="mv-metrics-top">
        <div>
          <div class="mv-metrics-label">最新稳定中位价</div>
          <div class="mv-hero-value">{escape(_format_currency(metrics["latest_median"]))}</div>
          <div style="margin-top: 0.55rem;">{_trend_pill(metrics["stable_yoy"])}</div>
        </div>
        <div style="text-align: right;">
          <div class="mv-metrics-label">最新稳定点</div>
          <div class="mv-hero-point">{escape(latest_point)}</div>
        </div>
      </div>
      <div class="mv-hero-divider"></div>
      <div class="mv-hero-bottom">
        <div>
          <div class="mv-hero-meta-label">区域</div>
          <div class="mv-hero-meta-value">{escape(region_label)}</div>
          <div class="mv-hero-meta-sub">{escape(context_label)}</div>
        </div>
        <div>
          <div class="mv-hero-meta-label">稳定阈值</div>
          <div class="mv-hero-meta-value">{escape(fmt_pct(stable_ratio))}</div>
          <div class="mv-hero-meta-sub">最小稳定评分</div>
        </div>
        <div>
          <div class="mv-hero-meta-label">数据更新时间</div>
          <div class="mv-hero-meta-value">{escape(pipeline_update_label)}</div>
          <div class="mv-hero-meta-sub">最新数据目录</div>
        </div>
      </div>
    </div>
    """
    st.markdown(hero_html, unsafe_allow_html=True)

    range_low = _format_currency(metrics["range_low"])
    range_high = _format_currency(metrics["range_high"])
    range_body = f"""
    <div class="mv-support-range">
      <div>
        <div class="mv-support-range-caption">最低价</div>
        <div class="mv-support-range-value">{escape(range_low)}</div>
      </div>
      <div>
        <div class="mv-support-range-caption">最高价</div>
        <div class="mv-support-range-value">{escape(range_high)}</div>
      </div>
    </div>
    """
    sales_text = fmt_int(metrics["sales"]) if metrics["sales"] is not None and not pd.isna(metrics["sales"]) else "N/A"
    sales_body = f'<div class="mv-support-value">{escape(sales_text)}</div>'
    support_cols = st.columns(2)
    _render_metric_card(support_cols[0], "稳定价格区间", range_body, "当前区域稳定价格范围")
    _render_metric_card(support_cols[1], "28天成交量", sales_body, "最新稳定点滚动成交量")


def _render_main_kpis_compact(metrics: dict[str, object], region_label: str, preset: str, dwelling: str):
    latest_point = fmt_date(metrics["latest_point"]) if metrics["latest_point"] is not None and not pd.isna(metrics["latest_point"]) else None
    context_label = f"{_preset_label(preset)} · {_dwelling_label(dwelling)}"

    top_cols = st.columns(3)
    region_body = f'<div class="mv-support-value">{escape(region_label)}</div>'
    median_date_html = f'<div class="mv-support-sub">截至 {escape(latest_point)}</div>' if latest_point else ""
    median_body = f'<div class="mv-support-value">{escape(_format_currency(metrics["latest_median"]))}</div>{median_date_html}'
    yoy_body = _trend_value_html(metrics["stable_yoy"])
    _render_metric_card(top_cols[0], "区域", region_body, context_label)
    _render_metric_card(top_cols[1], "最新稳定中位价", median_body)
    _render_metric_card(top_cols[2], "稳定同比", yoy_body)

    range_low = _format_currency(metrics["range_low"])
    range_high = _format_currency(metrics["range_high"])
    range_body = f"""
    <div class="mv-support-range">
      <div>
        <div class="mv-support-range-caption">最低价</div>
        <div class="mv-support-range-value">{escape(range_low)}</div>
      </div>
      <div>
        <div class="mv-support-range-caption">最高价</div>
        <div class="mv-support-range-value">{escape(range_high)}</div>
      </div>
    </div>
    """
    sales_text = fmt_int(metrics["sales"]) if metrics["sales"] is not None and not pd.isna(metrics["sales"]) else "N/A"
    sales_body = f'<div class="mv-support-value">{escape(sales_text)}</div>'
    support_cols = st.columns(2)
    _render_metric_card(support_cols[0], "稳定价格区间", range_body, "当前区域稳定价格范围")
    _render_metric_card(support_cols[1], "28天成交量", sales_body, "最新稳定点滚动成交量")


def _render_main_kpis_clean(metrics: dict[str, object], region_label: str, preset: str, dwelling: str):
    latest_point = fmt_date(metrics["latest_point"]) if metrics["latest_point"] is not None and not pd.isna(metrics["latest_point"]) else None
    context_label = f"{_preset_label(preset)} · {_dwelling_label(dwelling)}"
    latest_median_text = _format_currency(metrics["latest_median"])
    stable_yoy = metrics["stable_yoy"]
    if stable_yoy is None or pd.isna(stable_yoy):
        yoy_text = "— N/A"
    else:
        stable_yoy = float(stable_yoy)
        if stable_yoy > 0:
            yoy_text = f"▲ +{stable_yoy * 100:.1f}%"
        elif stable_yoy < 0:
            yoy_text = f"▼ {stable_yoy * 100:.1f}%"
        else:
            yoy_text = "— 0.0%"

    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.caption("区域")
            st.markdown(f"### {region_label}")
            st.caption(context_label)
    with c2:
        with st.container(border=True):
            st.caption("最新稳定中位价")
            st.markdown(f"### {latest_median_text}")
            st.caption(f"截至 {latest_point}" if latest_point else "截至 N/A")
    with c3:
        with st.container(border=True):
            st.caption("稳定同比")
            st.markdown(f"### {yoy_text}")
            st.caption("vs 去年同日稳定点")

    range_low = _format_currency(metrics["range_low"])
    range_high = _format_currency(metrics["range_high"])
    sales_text = fmt_int(metrics["sales"]) if metrics["sales"] is not None and not pd.isna(metrics["sales"]) else "N/A"

    c4, c5 = st.columns(2)
    with c4:
        with st.container(border=True):
            st.caption("稳定价格区间")
            col_low, col_high = st.columns(2)
            with col_low:
                st.caption("最低价")
                st.markdown(f"**{range_low}**")
            with col_high:
                st.caption("最高价")
                st.markdown(f"**{range_high}**")
            st.caption("当前区域稳定价格范围")
    with c5:
        with st.container(border=True):
            st.caption("28天成交量")
            st.markdown(f"### {sales_text}")
            st.caption("最新稳定点滚动成交")
@st.cache_data(ttl=3600, show_spinner=False)
def load_price_band_data(dwelling: str) -> pl.DataFrame:
    fact = load_filtered_fact_sales()
    if fact.is_empty():
        return pl.DataFrame()
    fact = fact.filter(
        pl.col("dwelling_group") == dwelling,
        pl.col("purchase_price").is_not_null(),
        pl.col("purchase_price") >= ANALYTICS_PRICE_MIN,
        pl.col("purchase_price") <= ANALYTICS_PRICE_MAX,
    )
    if fact.is_empty():
        return pl.DataFrame()

    def assign_band(price):
        for low, high, name in PRICE_BANDS:
            if low <= price < high:
                return name
        return "Unknown"

    fact = fact.with_columns(pl.col("purchase_price").map_elements(assign_band, return_dtype=pl.Utf8).alias("price_band"))
    fact = fact.filter(pl.col("price_band") != "Unknown")
    daily = fact.group_by(["date", "price_band"]).agg(pl.col("purchase_price").alias("prices"))
    if daily.is_empty():
        return pl.DataFrame()

    all_dates = pl.date_range(daily["date"].min(), daily["date"].max(), interval="1d", eager=True).cast(pl.Date)
    full = daily.join(pl.DataFrame({"date": all_dates, "dummy": 1}), on="date", how="right").with_columns(pl.lit(1).alias("dummy2"))
    full = full.join(pl.DataFrame({"price_band": BAND_NAMES, "dummy": 1}), on="dummy", how="left").drop(["dummy", "dummy2"])
    full = full.with_columns(pl.when(pl.col("prices").is_null()).then(pl.lit([])).otherwise(pl.col("prices")).alias("prices"))

    results = []
    for band in BAND_NAMES:
        band_pd = full.filter(pl.col("price_band") == band).sort("date").to_pandas().set_index("date")
        if band_pd.empty:
            continue
        rolling_medians = []
        sales_28d = []
        for date in band_pd.index:
            window = band_pd.loc[date - pd.Timedelta(days=27):date]
            flat_prices = [price for chunk in window["prices"].tolist() for price in chunk]
            sales = len(flat_prices)
            rolling_medians.append(np.median(flat_prices) if sales >= 5 else np.nan)
            sales_28d.append(sales)
        band_pd["rolling_median"] = rolling_medians
        band_pd["sales_28d"] = sales_28d
        band_pd["mom"] = band_pd["rolling_median"].pct_change(28)
        band_pd["qoq"] = band_pd["rolling_median"].pct_change(84)
        band_frame = band_pd.reset_index()[["date", "price_band", "rolling_median", "sales_28d", "mom", "qoq"]]
        results.append(pl.DataFrame(band_frame.to_dict(orient="list")))
    return pl.concat(results) if results else pl.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def get_area_options():
    daily_suburb = load_daily_rolling("SUBURB")
    daily_postcode = load_daily_rolling("POSTCODE")
    dim_suburb_postcode = load_dim_suburb_postcode()
    area_items = []
    if not daily_suburb.is_empty() and not dim_suburb_postcode.is_empty():
        suburb_map = dict(zip(dim_suburb_postcode["suburb"].str.strip_chars().to_list(), dim_suburb_postcode["postcode"].str.strip_chars().to_list()))
        for suburb in daily_suburb["region"].unique().to_list():
            postcode = suburb_map.get(suburb, "")
            area_items.append((f"{suburb} ({postcode})" if postcode else suburb, suburb))
    if not daily_postcode.is_empty():
        for postcode in daily_postcode["region"].unique().to_list():
            area_items.append((f"Postcode {postcode}", postcode))
    return sorted(area_items, key=lambda item: item[0])


def _load_level_daily(level: str) -> pl.DataFrame:
    if level == "NSW":
        return load_daily_rolling("NSW")
    if level == "REGION":
        return load_daily_rolling("REGION")
    if level == "REGION16":
        return load_daily_rolling("REGION16")
    if level == "AREA":
        return pl.concat([load_daily_rolling("SUBURB"), load_daily_rolling("POSTCODE")])
    return pl.DataFrame()


def _resolve_region_options(level: str, daily: pl.DataFrame):
    if level == "NSW":
        return ["NSW"], {"NSW": "NSW"}
    if level in {"REGION", "REGION16"}:
        options = daily["region"].unique().sort().to_list() if not daily.is_empty() else []
        return options, {option: option for option in options}
    area_items = get_area_options()
    labels = [item[0] for item in area_items]
    return labels, dict(area_items)


def _ensure_default_region(level: str, region_options: list[str]):
    if level == "NSW" or not region_options:
        return
    if level in {"REGION", "REGION16"}:
        key = f"mv_chart_region_{level.lower()}"
    else:
        key = "mv_chart_region_area"
    if st.session_state.get(key) not in region_options:
        st.session_state[key] = region_options[0]


def _pick_default_area_label(
    daily: pl.DataFrame,
    region_options: list[str],
    region_value_map: dict[str, str],
    *,
    dwelling: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> str | None:
    if not region_options or daily.is_empty():
        return region_options[0] if region_options else None

    visible_regions = set(
        daily.filter(
            (pl.col("dwelling_group") == dwelling)
            & (pl.col("date") >= start_ts)
            & (pl.col("date") <= end_ts)
        )["region"].unique().to_list()
    )
    if not visible_regions:
        return region_options[0]

    for label in region_options:
        value = region_value_map.get(label)
        if value in visible_regions:
            return label
    return region_options[0]


def _area_label_has_visible_rows(
    daily: pl.DataFrame,
    region_value_map: dict[str, str],
    label: str | None,
    *,
    dwelling: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> bool:
    if not label:
        return False
    value = region_value_map.get(label)
    if not value:
        return False
    return not daily.filter(
        (pl.col("dwelling_group") == dwelling)
        & (pl.col("region") == value)
        & (pl.col("date") >= start_ts)
        & (pl.col("date") <= end_ts)
    ).is_empty()


def _resolve_region_selection(level: str, region_value_map: dict[str, str]):
    if level == "NSW":
        return ["NSW"], "NSW"
    if level in {"REGION", "REGION16"}:
        selected = st.session_state.get(f"mv_chart_region_{level.lower()}")
        return ([selected] if selected else []), selected or "未选择区域"
    selected_label = st.session_state.get("mv_chart_region_area")
    selected_value = region_value_map.get(selected_label) if selected_label else None
    return ([selected_value] if selected_value else []), selected_label or "未选择区域"


def _render_topbar(badge_date):
    st.title(t("market_view_title"))
    st.caption(t("market_view_note"))
    st.markdown(
        f'<div><span class="mv-badge">{escape(t("data_as_of"))} {escape(fmt_date(badge_date))}</span></div>',
        unsafe_allow_html=True,
    )


def _render_page_filter_bar(min_date, max_date):
    filter_cols = st.columns([1.5, 1.3, 1.1] if not IS_EXTERNAL_MODE else [1.7, 1.5])
    with filter_cols[0]:
        st.markdown(f'<div class="mv-filter-label">{escape(t("time_range"))}</div>', unsafe_allow_html=True)
        default_preset = TIME_OPTIONS.index("1 Year") if "1 Year" in TIME_OPTIONS else 0
        preset = st.selectbox(t("time_range"), TIME_OPTIONS, index=default_preset, key="mv_preset", label_visibility="collapsed")
    start_ts, end_ts = _preset_start_end(min_date, max_date, preset)
    with filter_cols[1]:
        st.markdown(f'<div class="mv-filter-label">{escape(t("data_level"))}</div>', unsafe_allow_html=True)
        level = st.selectbox(t("data_level"), ["NSW", "REGION", "REGION16", "AREA"], index=0, key="mv_level", label_visibility="collapsed")
    stable_ratio = STABLE_RATIO
    if not IS_EXTERNAL_MODE:
        with filter_cols[2]:
            st.markdown(f'<div class="mv-filter-label">{escape(t("stable_ratio"))}</div>', unsafe_allow_html=True)
            stable_ratio = st.slider(t("stable_ratio"), 0.0, 1.0, STABLE_RATIO, 0.05, key="mv_stable_ratio", label_visibility="collapsed")
    return level, preset, start_ts, end_ts, stable_ratio


def _calc_band_summary(filtered: pl.DataFrame, stable_ratio: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    if filtered.is_empty():
        return pd.DataFrame(), pd.DataFrame(columns=["band", "median", "yoy"])
    global_max = filtered["date"].max()
    one_year_ago = global_max - pd.DateOffset(years=1)
    base_data = filtered.filter(pl.col("date") >= one_year_ago)
    base_sales = {}
    for band in BAND_NAMES:
        band_base = base_data.filter(pl.col("price_band") == band)
        base_sales[band] = band_base["sales_28d"].median() if band_base.height > 0 else 0

    chart_df = filtered.to_pandas()
    chart_df["date"] = pd.to_datetime(chart_df["date"]).dt.normalize()
    chart_df["base_sales"] = chart_df["price_band"].map(base_sales).fillna(0)
    chart_df["raw_stable"] = chart_df["sales_28d"] >= chart_df["base_sales"] * stable_ratio
    chart_df = apply_right_edge_stability_rule(chart_df, ["price_band"], "date", "raw_stable", "stable")

    rows = []
    for band in chart_df["price_band"].dropna().astype(str).unique().tolist():
        band_df = chart_df[(chart_df["price_band"] == band) & chart_df["stable"].fillna(False) & chart_df["rolling_median"].notna()].copy()
        if band_df.empty:
            print(f"[MarketView YoY] band={band} latest_stable_date=None target_date=None match_found=False reason=no_stable_points")
            rows.append({"band": band, "median": None, "yoy": "insufficient_history"})
            continue
        band_df = band_df.sort_values("date")
        latest = band_df.iloc[-1]
        latest_date = pd.to_datetime(latest["date"]).normalize()
        target_date = latest_date - pd.Timedelta(days=365)
        ref_df = band_df.assign(date_gap=(band_df["date"] - target_date).abs())
        ref_df = ref_df[ref_df["date_gap"] <= pd.Timedelta(days=14)].sort_values(["date_gap", "date"])
        yoy = "insufficient_history"
        match_found = not ref_df.empty
        if not ref_df.empty:
            ref_price = ref_df.iloc[0]["rolling_median"]
            if pd.notna(ref_price) and float(ref_price) != 0:
                yoy = float(latest["rolling_median"]) / float(ref_price) - 1.0
            else:
                yoy = None
        print(
            f"[MarketView YoY] band={band} "
            f"latest_stable_date={latest_date.date()} "
            f"target_date={target_date.date()} "
            f"match_found={match_found}"
        )
        rows.append({"band": band, "median": latest["rolling_median"], "yoy": yoy})
    return chart_df, pd.DataFrame(rows)


def _with_underlying_trend(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame() if frame is None else frame.copy()
    return add_underlying_trend(
        frame,
        group_cols=group_cols,
        date_col="event_time",
        value_col="value",
        out_col="underlying_trend",
        tail_col="underlying_trend_tail",
        window_days=91,
    )


def _long_trend_min_median_sales(level: str) -> float:
    normalized = str(level or "").strip().upper()
    if normalized in {"AREA", "SUBURB", "POSTCODE"}:
        return float(LOWER_GEO_LONG_TREND_MIN_MEDIAN_SALES)
    return float(LONG_TREND_MIN_MEDIAN_SALES)


def _with_conditional_underlying_trend(
    frame: pd.DataFrame,
    *,
    group_cols: list[str],
    sales_col: str = "sales_28d",
    min_median_sales: float,
) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame() if frame is None else frame.copy()

    out = frame.copy()
    out["underlying_trend"] = np.nan
    out["underlying_trend_tail"] = False
    if sales_col not in out.columns:
        return out

    if not group_cols:
        eligible = pd.to_numeric(out[sales_col], errors="coerce").median() >= float(min_median_sales)
        return _with_underlying_trend(out, []) if eligible else out

    sales_median = (
        out.groupby(group_cols, dropna=False)[sales_col]
        .median()
        .reset_index(name="_median_sales_28d")
    )
    eligible_groups = sales_median.loc[sales_median["_median_sales_28d"] >= float(min_median_sales), group_cols].copy()
    if eligible_groups.empty:
        return out

    eligible_frame = out.merge(eligible_groups, on=group_cols, how="inner")
    if eligible_frame.empty:
        return out

    eligible_frame = _with_underlying_trend(eligible_frame, group_cols)
    keep_cols = group_cols + ["event_time", "underlying_trend", "underlying_trend_tail"]
    out = out.merge(
        eligible_frame[keep_cols],
        on=group_cols + ["event_time"],
        how="left",
        suffixes=("", "_eligible"),
    )
    out["underlying_trend"] = out["underlying_trend_eligible"].combine_first(out["underlying_trend"])
    out["underlying_trend_tail"] = out["underlying_trend_tail_eligible"].fillna(out["underlying_trend_tail"]).astype(bool)
    return out.drop(columns=["underlying_trend_eligible", "underlying_trend_tail_eligible"])


def _build_market_view_plot_df(
    df_scope: pd.DataFrame,
    *,
    base_sales: dict[str, float],
    stable_ratio: float,
    level: str,
) -> pd.DataFrame:
    frame = df_scope[["date", "region", "rolling_median", "sales_28d"]].rename(
        columns={"date": "event_time", "rolling_median": "value"}
    )
    frame["event_time"] = pd.to_datetime(frame["event_time"], errors="coerce").dt.normalize()
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["sales_28d"] = pd.to_numeric(frame["sales_28d"], errors="coerce")
    frame["base_sales"] = frame["region"].map(base_sales).fillna(0)
    frame["raw_stable"] = frame["sales_28d"] >= frame["base_sales"] * stable_ratio
    frame = frame[frame["event_time"].notna() & frame["value"].notna()].copy()

    # `stable` is a page-level derived flag and should exist for every level.
    if "stable" not in frame.columns:
        frame["stable"] = False
    if not frame.empty:
        frame = apply_right_edge_stability_rule(frame, ["region"], "event_time", "raw_stable", "stable")

    frame = _with_conditional_underlying_trend(
        frame,
        group_cols=["region"] if level != "NSW" else [],
        min_median_sales=_long_trend_min_median_sales(level),
    )

    return frame


def _build_market_view_stable_lookup(plot_df_all: pd.DataFrame) -> pd.DataFrame:
    if plot_df_all.empty:
        return pd.DataFrame(columns=["event_time", "region", "stable"])
    stable_lookup = plot_df_all.copy()
    if "stable" not in stable_lookup.columns:
        stable_lookup["stable"] = False
    return stable_lookup[["event_time", "region", "stable"]].drop_duplicates()


def main():
    ensure_lang()
    inject_app_theme()
    _inject_market_view_css()

    with st.sidebar:
        opts = sidebar_common()
    dwelling = opts["dwelling"]

    seed_daily = load_daily_rolling("NSW")
    if seed_daily.is_empty():
        st.error(t("market_view_missing_daily"))
        return
    min_date = seed_daily["date"].min()
    max_date = seed_daily["date"].max()
    _render_topbar(max_date)
    level, preset, start_ts, end_ts, stable_ratio = _render_page_filter_bar(min_date, max_date)
    current_daily = _load_level_daily(level)
    if current_daily.is_empty():
        st.error(t("no_data"))
        return
    current_daily = current_daily.with_columns(pl.col("region").cast(pl.Utf8).str.strip_chars())
    region_options, region_value_map = _resolve_region_options(level, current_daily)
    _ensure_default_region(level, region_options)
    if level == "AREA" and region_options:
        area_key = "mv_chart_region_area"
        if not _area_label_has_visible_rows(
            current_daily,
            region_value_map,
            st.session_state.get(area_key),
            dwelling=dwelling,
            start_ts=start_ts,
            end_ts=end_ts,
        ):
            st.session_state[area_key] = _pick_default_area_label(
                current_daily,
                region_options,
                region_value_map,
                dwelling=dwelling,
                start_ts=start_ts,
                end_ts=end_ts,
            )
    regions_selected, region_label = _resolve_region_selection(level, region_value_map)
    with st.spinner(t("loading_market_view")):
        daily = current_daily
        if level != "NSW" and not regions_selected:
            st.warning(t("select_region"))
            return

        df_scope = daily.filter(pl.col("dwelling_group") == dwelling).to_pandas()
        df_scope["date"] = pd.to_datetime(df_scope["date"]).dt.normalize()
        if level != "NSW":
            df_scope = df_scope[df_scope["region"].isin(regions_selected)]
        if df_scope.empty:
            st.info(t("no_data"))
            return

        one_year_ago = pd.to_datetime(daily["date"].max()) - pd.DateOffset(years=1)
        base_df = daily.filter((pl.col("dwelling_group") == dwelling) & (pl.col("date") >= one_year_ago)).to_pandas()
        base_sales = base_df.groupby("region")["sales_28d"].median().to_dict()

        plot_df_all = _build_market_view_plot_df(
            df_scope,
            base_sales=base_sales,
            stable_ratio=stable_ratio,
            level=level,
        )
        stable_lookup = _build_market_view_stable_lookup(plot_df_all)

        summary_full_df = df_scope[["date", "region", "rolling_median", "sales_28d"]].merge(
            stable_lookup,
            left_on=["date", "region"],
            right_on=["event_time", "region"],
            how="left",
        )
        summary_visible_df = summary_full_df[(summary_full_df["date"] >= start_ts) & (summary_full_df["date"] <= end_ts)].copy()
        if summary_visible_df.empty:
            st.info(t("no_data"))
            return
        focus_metrics = _build_focus_metrics(summary_full_df, summary_visible_df)
        plot_df = plot_df_all[(plot_df_all["event_time"] >= start_ts) & (plot_df_all["event_time"] <= end_ts)].copy()

        chart_card = st.container(border=True)
        with chart_card:
            header_cols = st.columns([3.3, 1.5, 1.35])
            header_cols[0].markdown(
                f'<div class="mv-section-title">{escape(t("rolling_median_trend"))}</div>'
                f'<div class="mv-section-subtitle">{escape(t("rolling_median_trend_note"))}</div>',
                unsafe_allow_html=True,
            )
            with header_cols[1]:
                st.markdown(f'<div class="mv-filter-label">{escape(t("region"))}</div>', unsafe_allow_html=True)
                if level == "NSW":
                    st.text_input(t("region"), value="NSW", disabled=True, label_visibility="collapsed", key="mv_chart_region_nsw")
                elif level in {"REGION", "REGION16"}:
                    st.selectbox(t("region"), options=region_options, key=f"mv_chart_region_{level.lower()}", label_visibility="collapsed")
                else:
                    st.selectbox(t("region"), options=region_options, key="mv_chart_region_area", label_visibility="collapsed", placeholder=t("search_suburb_or_postcode"))
            with header_cols[2]:
                st.markdown(f'<div class="mv-filter-label">{escape(t("display_mode"))}</div>', unsafe_allow_html=True)
                chart_display_mode = st.selectbox(t("display_mode"), LINE_DISPLAY_MODES, index=0, key="mv_chart_display_mode", label_visibility="collapsed")
            chart = build_interactive_chart(
                plot_df,
                level=level,
                time_col="event_time",
                time_title=t("axis_week"),
                include_sales=True,
                sales_col="sales_28d",
                sales_title=t("sales_28d"),
                stable_col="stable",
                trend_col="underlying_trend",
                display_mode=chart_display_mode,
            )
            st.plotly_chart(chart, use_container_width=True, config={"displayModeBar": False, "responsive": True})

        st.markdown(f"### {t('core_metrics')}")
        _render_main_kpis_clean(
            focus_metrics,
            region_label=region_label,
            preset=preset,
            dwelling=dwelling,
        )

        band_card = st.container(border=True)
        with band_card:
            band_data = load_price_band_data(dwelling)
            st.markdown(
                f'<div class="mv-section-title">{escape(t("price_band_trend"))}</div>'
                f'<div class="mv-section-subtitle">{escape(t("price_band_trend_note"))}</div>',
                unsafe_allow_html=True,
            )
            if band_data.is_empty():
                st.info(t("market_view_no_band_data"))
            else:
                filtered_band = band_data.filter((pl.col("date") >= start_ts) & (pl.col("date") <= end_ts))
                available_bands = band_data["price_band"].unique().to_list()
                filter_cols = st.columns([4.0, 1.7])
                with filter_cols[0]:
                    left_cols = st.columns([0.38, 1.0], gap="small")
                    with left_cols[0]:
                        st.markdown(f'<div class="mv-band-inline-label" style="padding-top: 8px;">{escape(t("price_band"))}</div>', unsafe_allow_html=True)
                    with left_cols[1]:
                        selected_bands = st.multiselect(t("price_band"), options=available_bands, default=available_bands, key=f"band_select_{dwelling}", label_visibility="collapsed")
                with filter_cols[1]:
                    right_cols = st.columns([0.42, 1.0], gap="small")
                    with right_cols[0]:
                        st.markdown(f'<div class="mv-band-inline-label" style="padding-top: 8px; text-align: right;">{escape(t("display_mode"))}</div>', unsafe_allow_html=True)
                    with right_cols[1]:
                        band_display_mode = st.selectbox(t("display_mode"), LINE_DISPLAY_MODES, index=0, key=f"band_display_mode_{dwelling}", label_visibility="collapsed")
                filtered_band = filtered_band.filter(pl.col("price_band").is_in(selected_bands)) if selected_bands else pl.DataFrame()
                summary_band = band_data.filter(pl.col("price_band").is_in(selected_bands)) if selected_bands else pl.DataFrame()
                chart_band_df, _ = _calc_band_summary(filtered_band, stable_ratio)
                _, band_summary = _calc_band_summary(summary_band, stable_ratio)
                if chart_band_df.empty:
                    st.info(t("market_view_no_band_filtered_data"))
                else:
                    chart_band_df = chart_band_df.rename(columns={"date": "event_time", "rolling_median": "value"})
                    chart_band_df = _with_underlying_trend(chart_band_df, ["price_band"])
                    fig = build_band_chart(
                        chart_band_df,
                        "value",
                        "event_time",
                        "price_band",
                        "sales_28d",
                        "stable",
                        trend_col="underlying_trend",
                        display_mode=band_display_mode,
                    )
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True})
                    shown_bands = [band for band in selected_bands if band in band_summary["band"].tolist()]
                    st.markdown(f'<div class="mv-band-summary-descriptor">{escape(t("all_price_bands_yoy"))}</div>', unsafe_allow_html=True)
                    band_cols = st.columns(max(len(shown_bands), 1))
                    for col, band in zip(band_cols, shown_bands):
                        row = band_summary[band_summary["band"] == band]
                        median = row["median"].iloc[0] if not row.empty else None
                        yoy = row["yoy"].iloc[0] if not row.empty else None
                        col.markdown(
                            f"""
                            <div class="mv-band-summary">
                              <div class="mv-band-label">{escape(band)}</div>
                              <div class="mv-band-value">{escape(_format_currency(median))}</div>
                              <div class="mv-band-yoy-row">{_band_yoy_pill_html(yoy)}</div>
                              <div class="mv-band-summary-sub">{escape(t("vs_same_date_last_year"))}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
if __name__ == "__main__":
    main()
