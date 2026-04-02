from html import escape

import numpy as np
import pandas as pd
import streamlit as st

from pages._ranking_cache import load_ranking_snapshot
from utils.config import IS_EXTERNAL_MODE
from utils.data import load_daily_rolling
from utils.i18n import ensure_lang, t
from utils.perf import PagePerf, render_internal_timing_summary
from utils.ranking_view import render_rank_table
from utils.tables import fmt_date
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


def _inject_css():
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1280px;
            padding-top: 1.2rem;
            padding-bottom: 2.6rem;
        }
        .rk-title {
            font-size: 2.05rem;
            font-weight: 800;
            color: #111827;
            margin: 0;
        }
        .rk-subtitle {
            color: #6b7280;
            font-size: 0.95rem;
            margin-top: 0.35rem;
            margin-bottom: 0.8rem;
        }
        .rk-badge {
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
        .rk-filter-label {
            color: #6b7280;
            font-size: 0.76rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
        }
        .rk-divider {
            height: 2.4rem;
            width: 1px;
            background: rgba(148, 163, 184, 0.35);
            margin: 1.55rem auto 0 auto;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _safe_bounds(snapshot_df: pd.DataFrame):
    if snapshot_df.empty:
        return {
            "region16_options": [t("ranking_all_regions")],
            "sales": (0, 100),
            "median": (0.0, 5_000_000.0),
            "stable_yoy": (-100.0, 100.0),
        }
    sales = pd.to_numeric(snapshot_df["28d sales"], errors="coerce")
    median = pd.to_numeric(snapshot_df["28d median"], errors="coerce")
    stable_yoy = pd.to_numeric(snapshot_df["Stable YoY"], errors="coerce") * 100.0
    regions = sorted([x for x in snapshot_df["Region16"].dropna().astype(str).unique().tolist() if x.strip()])
    return {
        "region16_options": [t("ranking_all_regions")] + regions,
        "sales": (0, max(int(np.nanmax(sales)) if sales.notna().any() else 100, 1)),
        "median": (0.0, max(float(np.nanmax(median)) if median.notna().any() else 5_000_000.0, 1.0)),
        "stable_yoy": (
            float(np.floor(np.nanmin(stable_yoy))) if stable_yoy.notna().any() else -100.0,
            float(np.ceil(np.nanmax(stable_yoy))) if stable_yoy.notna().any() else 100.0,
        ),
    }


def _number_range(label: str, min_value, max_value, default_min, default_max, key_prefix: str, step):
    col1, col2 = st.columns(2)
    with col1:
        min_input = st.number_input(
            f"{label} {t('min_value')}",
            min_value=min_value,
            max_value=max_value,
            value=default_min,
            step=step,
            key=f"{key_prefix}_min",
            label_visibility="collapsed",
        )
    with col2:
        max_input = st.number_input(
            f"{label} {t('max_value')}",
            min_value=min_value,
            max_value=max_value,
            value=default_max,
            step=step,
            key=f"{key_prefix}_max",
            label_visibility="collapsed",
        )
    return min(min_input, max_input), max(min_input, max_input)


def _prepare_snapshot(snapshot_df: pd.DataFrame) -> pd.DataFrame:
    if snapshot_df is None or snapshot_df.empty:
        return pd.DataFrame()
    df = snapshot_df.copy()
    df["28d median"] = pd.to_numeric(df["28d median"], errors="coerce")
    df["28d sales"] = pd.to_numeric(df["28d sales"], errors="coerce")
    df["Stable YoY"] = pd.to_numeric(df["Stable YoY"], errors="coerce")
    df["As of"] = pd.to_datetime(df["As of"], errors="coerce")
    return df


def _filter_snapshot(snapshot_df: pd.DataFrame, region16, median_range, sales_range, stable_yoy_range):
    df = snapshot_df.copy()
    if region16 != t("ranking_all_regions"):
        df = df[df["Region16"] == region16].copy()
    return df[
        df["28d median"].between(float(median_range[0]), float(median_range[1]), inclusive="both")
        & df["28d sales"].between(float(sales_range[0]), float(sales_range[1]), inclusive="both")
        & (df["Stable YoY"] * 100.0).between(float(stable_yoy_range[0]), float(stable_yoy_range[1]), inclusive="both")
    ].copy()


def main():
    perf = PagePerf("ranking")
    ensure_lang()
    if IS_EXTERNAL_MODE:
        inject_app_theme()
        _inject_css()
        st.markdown(f'<div class="rk-title">{escape(t("ranking_title"))}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="rk-subtitle">{escape("Ranking is available in internal mode only.")}</div>',
            unsafe_allow_html=True,
        )
        st.info("This page is not available in the external demo.")
        timing_payload = perf.log(mode="external_placeholder")
        render_internal_timing_summary(timing_payload, enabled=False)
        return
    inject_app_theme()
    _inject_css()

    with st.sidebar:
        opts = sidebar_common()
    dwelling = opts["dwelling"]

    stable_label = t("stable")
    standard_label = t("standard")
    descending_label = t("descending")
    ascending_label = t("ascending")

    mode = st.session_state.get("rk_mode", stable_label)
    if mode not in {stable_label, standard_label}:
        mode = stable_label
        st.session_state["rk_mode"] = mode
    calibre = "stable" if mode == stable_label else "normal"

    with perf.track("source_data_load"):
        snapshot = _prepare_snapshot(load_ranking_snapshot(dwelling, calibre, 0.6 if calibre == "stable" else None))
        bounds = _safe_bounds(snapshot)
        max_date = load_daily_rolling("NSW")["date"].max()

    region_title = st.session_state.get("rk_region16", t("ranking_all_regions"))
    display_region_title = region_title if region_title != t("ranking_all_regions") else t("ranking_all_regions")
    title_col, badge_col = st.columns([6, 2])
    title_col.markdown(
        f'<div class="rk-title">{escape(t("ranking_title"))} · {escape(display_region_title)}</div>'
        f'<div class="rk-subtitle">{escape(t("ranking_subtitle"))}</div>',
        unsafe_allow_html=True,
    )
    badge_col.markdown(
        f'<div style="text-align:right;"><span class="rk-badge">{escape(t("data_as_of"))} {escape(fmt_date(max_date))}</span></div>',
        unsafe_allow_html=True,
    )

    widths = [1.4, 0.06, 1.3, 0.06, 1.8, 0.06, 2.2, 0.06, 2.0, 0.06, 2.0]
    cols = st.columns(widths)
    with cols[0]:
        st.markdown(f'<div class="rk-filter-label">{escape(t("calibre"))}</div>', unsafe_allow_html=True)
        mode = st.radio(t("calibre"), [stable_label, standard_label], horizontal=True, label_visibility="collapsed", key="rk_mode")
    cols[1].markdown('<div class="rk-divider"></div>', unsafe_allow_html=True)
    with cols[2]:
        st.markdown(f'<div class="rk-filter-label">{escape(t("sort"))}</div>', unsafe_allow_html=True)
        sort_order = st.selectbox(t("sort"), [descending_label, ascending_label], label_visibility="collapsed", key="rk_sort")
    cols[3].markdown('<div class="rk-divider"></div>', unsafe_allow_html=True)
    with cols[4]:
        st.markdown(f'<div class="rk-filter-label">{escape(t("region"))}</div>', unsafe_allow_html=True)
        selected_region16 = st.selectbox(t("region"), bounds["region16_options"], label_visibility="collapsed", key="rk_region16")
    cols[5].markdown('<div class="rk-divider"></div>', unsafe_allow_html=True)
    with cols[6]:
        st.markdown(f'<div class="rk-filter-label">{escape(t("median_range"))}</div>', unsafe_allow_html=True)
        median_range = _number_range(t("median_price"), 0.0, float(bounds["median"][1]), 0.0, float(bounds["median"][1]), "rk_median", 50000.0)
    cols[7].markdown('<div class="rk-divider"></div>', unsafe_allow_html=True)
    with cols[8]:
        st.markdown(f'<div class="rk-filter-label">{escape(t("sales_volume"))}</div>', unsafe_allow_html=True)
        sales_range = _number_range(t("sales_volume"), 0, int(bounds["sales"][1]), 0, int(bounds["sales"][1]), "rk_sales", 1)
    cols[9].markdown('<div class="rk-divider"></div>', unsafe_allow_html=True)
    with cols[10]:
        st.markdown(f'<div class="rk-filter-label">{escape(t("stable_yoy_range"))}</div>', unsafe_allow_html=True)
        stable_yoy_range = _number_range(
            t("stable_yoy"),
            float(bounds["stable_yoy"][0]),
            float(bounds["stable_yoy"][1]),
            float(bounds["stable_yoy"][0]),
            float(bounds["stable_yoy"][1]),
            "rk_stable_yoy",
            0.1,
        )

    calibre = "stable" if st.session_state.get("rk_mode", stable_label) == stable_label else "normal"
    with perf.track("filter_application"):
        filtered = _filter_snapshot(snapshot, selected_region16, median_range, sales_range, stable_yoy_range)
    ascending = sort_order == ascending_label

    with perf.track("ranking_table_prep"):
        render_rank_table(
            filtered.dropna(subset=["Stable YoY", "28d median"]).sort_values("Stable YoY", ascending=ascending).reset_index(drop=True),
            "Stable YoY",
            include_asof=True,
            stable_mode=(calibre == "stable"),
            height=720,
            empty_message=t("ranking_empty"),
        )

    timing_payload = perf.log(
        dwelling=dwelling,
        calibre=calibre,
        rows=int(len(filtered)),
    )
    render_internal_timing_summary(timing_payload, enabled=not IS_EXTERNAL_MODE)


if __name__ == "__main__":
    main()
