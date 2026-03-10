# pages/1_Market_View.py
import pandas as pd
import streamlit as st
import polars as pl
import numpy as np

from utils.i18n import t, ensure_lang
from utils.config import (
    PRICE_MAX,
    PRICE_MIN_EXCLUSIVE,
    TOP_N_RANK,
    BASE_DIR,
)
from utils.data import (
    load_daily_rolling,
    load_dim_suburb_postcode,
    load_dim_postcode_gccsa,
)
from utils.charts import build_interactive_chart, build_band_chart
from utils.tables import (
    fmt_float0,
    fmt_int,
    fmt_pct,
    fmt_date,
    build_stable_top_bottom_tables,
    build_region_overview_table,
)
from utils.ui import sidebar_common

# ========== 价格分档阈值 ==========
PRICE_BANDS = [
    (0, 750_000, "<750k"),
    (750_000, 1_200_000, "750k-1.2M"),
    (1_200_000, 2_000_000, "1.2M-2M"),
    (2_000_000, 3_000_000, "2M-3M"),
    (3_000_000, float("inf"), ">3M"),
]
BAND_NAMES = [b[2] for b in PRICE_BANDS]

STABLE_RATIO = 0.6  # 默认值，可在侧边栏调整

# ✅ 稳定排名：先取更多候选，再按 min_sales 过滤后截取 top5/bot5
STABLE_RANK_CANDIDATES = max(TOP_N_RANK * 30, 200)


# ========== 工具函数 ==========
def _preset_start_end(min_date: pd.Timestamp, max_date: pd.Timestamp, preset: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    maxd = pd.to_datetime(max_date).normalize()
    mind = pd.to_datetime(min_date).normalize()

    if preset == "Max":
        return mind, maxd
    if preset == "YTD":
        start = pd.Timestamp(year=maxd.year, month=1, day=1)
        return max(start, mind), maxd

    mapping = {
        "1 Month": pd.DateOffset(months=1),
        "3 Month": pd.DateOffset(months=3),
        "6 Month": pd.DateOffset(months=6),
        "1 Year": pd.DateOffset(years=1),
        "3 Year": pd.DateOffset(years=3),
        "5 Year": pd.DateOffset(years=5),
        "10 Year": pd.DateOffset(years=10),
    }
    offset = mapping.get(preset)
    if offset is None:
        return mind, maxd
    start = maxd - offset
    if start < mind:
        start = mind
    return start, maxd


def _show_loading_overlay(ph: st.delta_generator.DeltaGenerator, message: str):
    ph.markdown(
        f"""
        <style>
        .oai-overlay {{
            position: fixed;
            inset: 0;
            background: rgba(245, 246, 248, 0.82);
            z-index: 999999;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .oai-card {{
            background: rgba(255,255,255,0.95);
            border-radius: 18px;
            padding: 28px 30px;
            box-shadow: 0 12px 36px rgba(0,0,0,0.14);
            min-width: 340px;
            max-width: 560px;
            text-align: center;
        }}
        .oai-spinner {{
            width: 58px;
            height: 58px;
            border: 7px solid rgba(0,0,0,0.10);
            border-top-color: rgba(0,0,0,0.58);
            border-radius: 50%;
            animation: oai-spin 0.9s linear infinite;
            margin: 0 auto 14px auto;
        }}
        @keyframes oai-spin {{
            from {{ transform: rotate(0deg); }}
            to {{ transform: rotate(360deg); }}
        }}
        .oai-msg {{
            font-size: 16px;
            line-height: 1.35;
        }}
        .oai-sub {{
            margin-top: 6px;
            font-size: 12px;
            opacity: 0.65;
        }}
        </style>

        <div class="oai-overlay">
          <div class="oai-card">
            <div class="oai-spinner"></div>
            <div class="oai-msg">{message}</div>
            <div class="oai-sub">This may take a few seconds…</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _safe_df(x) -> pd.DataFrame:
    """防止把 DeltaGenerator / None / 乱七八糟的东西当 DataFrame 展示出来。"""
    return x if isinstance(x, pd.DataFrame) else pd.DataFrame()


def _detect_sales_col(df: pd.DataFrame) -> str | None:
    """尽量鲁棒地找到销量列名（不同语言/格式都尽量兼容）。"""
    if df is None or df.empty:
        return None

    candidates = [
        "28d sales", "28d_sales", "sales_28d", "Sales 28d", "28D Sales",
        "28天总销量", "28天销量", "销量", "sales"
    ]
    cols = list(df.columns)

    for c in candidates:
        if c in cols:
            return c

    low_map = {c: str(c).lower() for c in cols}
    for orig, low in low_map.items():
        if "销量" in str(orig):
            return orig
        if "sales" in low and ("28" in low or "d" in low or "day" in low):
            return orig

    for orig, low in low_map.items():
        if "sales" in low:
            return orig

    return None


def _filter_min_sales_and_trim(df: pd.DataFrame, min_sales: int, top_n: int) -> pd.DataFrame:
    """过滤销量阈值后，保留前 top_n 行（保持原排序，不重新排序）。"""
    if df is None or df.empty:
        return pd.DataFrame()

    sales_col = _detect_sales_col(df)
    if sales_col is None:
        return pd.DataFrame()

    out = df.copy()
    out[sales_col] = pd.to_numeric(out[sales_col], errors="coerce")
    out = out[out[sales_col].fillna(0) >= min_sales]
    if out.empty:
        return pd.DataFrame()

    return out.head(top_n)


# ========== 排名数据（严禁在 cache 函数里 st.xxx） ==========
@st.cache_data(ttl=3600, show_spinner=False)
def get_rank_tables(dwelling: str, stable_ratio: float, min_stable_sales_28d: int):
    daily_suburb = load_daily_rolling("SUBURB")
    if daily_suburb.is_empty():
        return (pd.DataFrame(),) * 8

    dim_suburb_postcode = load_dim_suburb_postcode()
    dim_postcode_gccsa = load_dim_postcode_gccsa()

    daily_suburb_pd = daily_suburb.to_pandas()
    dim_suburb_postcode_pd = dim_suburb_postcode.to_pandas() if not dim_suburb_postcode.is_empty() else pd.DataFrame()
    dim_postcode_gccsa_pd = dim_postcode_gccsa.to_pandas() if not dim_postcode_gccsa.is_empty() else pd.DataFrame()

    # 普通排名（保持原逻辑）
    top_mom, bot_mom = build_stable_top_bottom_tables(
        daily_suburb=daily_suburb_pd,
        dim_suburb_postcode=dim_suburb_postcode_pd,
        dim_postcode_gccsa=dim_postcode_gccsa_pd,
        dwelling=dwelling,
        change_kind="mom",
        top_n=TOP_N_RANK,
        only_greater_sydney=True,
        use_stable=False,
    )
    top_qoq, bot_qoq = build_stable_top_bottom_tables(
        daily_suburb=daily_suburb_pd,
        dim_suburb_postcode=dim_suburb_postcode_pd,
        dim_postcode_gccsa=dim_postcode_gccsa_pd,
        dwelling=dwelling,
        change_kind="qoq",
        top_n=TOP_N_RANK,
        only_greater_sydney=True,
        use_stable=False,
    )

    # 稳定排名：先取更多候选，再按销量阈值过滤截取
    top_mom_s_raw, bot_mom_s_raw = build_stable_top_bottom_tables(
        daily_suburb=daily_suburb_pd,
        dim_suburb_postcode=dim_suburb_postcode_pd,
        dim_postcode_gccsa=dim_postcode_gccsa_pd,
        dwelling=dwelling,
        change_kind="mom",
        top_n=STABLE_RANK_CANDIDATES,
        only_greater_sydney=True,
        use_stable=True,
        stable_ratio=stable_ratio,
    )
    top_qoq_s_raw, bot_qoq_s_raw = build_stable_top_bottom_tables(
        daily_suburb=daily_suburb_pd,
        dim_suburb_postcode=dim_suburb_postcode_pd,
        dim_postcode_gccsa=dim_postcode_gccsa_pd,
        dwelling=dwelling,
        change_kind="qoq",
        top_n=STABLE_RANK_CANDIDATES,
        only_greater_sydney=True,
        use_stable=True,
        stable_ratio=stable_ratio,
    )

    top_mom_s = _filter_min_sales_and_trim(top_mom_s_raw, min_stable_sales_28d, TOP_N_RANK)
    bot_mom_s = _filter_min_sales_and_trim(bot_mom_s_raw, min_stable_sales_28d, TOP_N_RANK)
    top_qoq_s = _filter_min_sales_and_trim(top_qoq_s_raw, min_stable_sales_28d, TOP_N_RANK)
    bot_qoq_s = _filter_min_sales_and_trim(bot_qoq_s_raw, min_stable_sales_28d, TOP_N_RANK)

    return tuple(
        map(
            _safe_df,
            (top_mom, bot_mom, top_qoq, bot_qoq, top_mom_s, bot_mom_s, top_qoq_s, bot_qoq_s),
        )
    )


def _render_rank_block_suburb(dwelling: str, stable_ratio: float, min_stable_sales_28d: int):
    st.markdown("### 稳定排名（仅 Greater Sydney 城区）")
    st.caption("左侧为普通排名，右侧为稳定排名（销量达到基准阈值的点）。")

    tabs = st.tabs(["普通排名", "稳定排名"])

    top_m, bot_m, top_q, bot_q, top_m_s, bot_m_s, top_q_s, bot_q_s = get_rank_tables(
        dwelling, stable_ratio, min_stable_sales_28d
    )

    with tabs[0]:
        st.markdown("**MoM（28天滚动中位价环比28天前）**")
        c1, c2 = st.columns(2)
        with c1:
            st.caption(f"涨幅前 {TOP_N_RANK}")
            if top_m.empty:
                st.info("无数据（可能 SUBURB 日滚动表为空，或 Greater Sydney 映射未命中）")
            else:
                st.dataframe(top_m, use_container_width=True, hide_index=True)
        with c2:
            st.caption(f"跌幅前 {TOP_N_RANK}")
            if bot_m.empty:
                st.info("无数据（可能 SUBURB 日滚动表为空，或 Greater Sydney 映射未命中）")
            else:
                st.dataframe(bot_m, use_container_width=True, hide_index=True)

        st.markdown("**QoQ（28天滚动中位价环比84天前）**")
        c3, c4 = st.columns(2)
        with c3:
            st.caption(f"涨幅前 {TOP_N_RANK}")
            if top_q.empty:
                st.info("无数据")
            else:
                st.dataframe(top_q, use_container_width=True, hide_index=True)
        with c4:
            st.caption(f"跌幅前 {TOP_N_RANK}")
            if bot_q.empty:
                st.info("无数据")
            else:
                st.dataframe(bot_q, use_container_width=True, hide_index=True)

    with tabs[1]:
        st.markdown("**稳定 MoM（28天滚动中位价环比28天前）**")
        st.caption(f"仅纳入 28d sales ≥ {min_stable_sales_28d} 的 suburb，然后取前 {TOP_N_RANK} / 后 {TOP_N_RANK}。")
        c1, c2 = st.columns(2)
        with c1:
            st.caption(f"涨幅前 {TOP_N_RANK}")
            if top_m_s.empty:
                st.info("无数据（尝试降低 stable_ratio 或降低销量阈值）")
            else:
                st.dataframe(top_m_s, use_container_width=True, hide_index=True)
        with c2:
            st.caption(f"跌幅前 {TOP_N_RANK}")
            if bot_m_s.empty:
                st.info("无数据（尝试降低 stable_ratio 或降低销量阈值）")
            else:
                st.dataframe(bot_m_s, use_container_width=True, hide_index=True)

        st.markdown("**稳定 QoQ（28天滚动中位价环比84天前）**")
        st.caption(f"仅纳入 28d sales ≥ {min_stable_sales_28d} 的 suburb，然后取前 {TOP_N_RANK} / 后 {TOP_N_RANK}。")
        c3, c4 = st.columns(2)
        with c3:
            st.caption(f"涨幅前 {TOP_N_RANK}")
            if top_q_s.empty:
                st.info("无数据（尝试降低 stable_ratio 或降低销量阈值）")
            else:
                st.dataframe(top_q_s, use_container_width=True, hide_index=True)
        with c4:
            st.caption(f"跌幅前 {TOP_N_RANK}")
            if bot_q_s.empty:
                st.info("无数据（尝试降低 stable_ratio 或降低销量阈值）")
            else:
                st.dataframe(bot_q_s, use_container_width=True, hide_index=True)


# ========== 价格分档模块 ==========
@st.cache_data(ttl=3600, show_spinner=False)
def load_price_band_data(dwelling: str) -> pl.DataFrame:
    from pathlib import Path
    FACT_DIR = BASE_DIR / "Processed" / "fact_sales"
    years = sorted([int(p.stem.split("_")[-1]) for p in FACT_DIR.glob("fact_sales_*.parquet") if p.stem.split("_")[-1].isdigit()])
    if not years:
        return pl.DataFrame()

    recent_years = years[-5:]
    dfs = []
    for y in recent_years:
        path = FACT_DIR / f"fact_sales_{y}.parquet"
        df = pl.read_parquet(path)
        dfs.append(df)
    fact = pl.concat(dfs)

    fact = fact.filter(
        pl.col("dwelling_group") == dwelling,
        pl.col("purchase_price").is_not_null(),
        pl.col("purchase_price") > PRICE_MIN_EXCLUSIVE,
        pl.col("purchase_price") <= PRICE_MAX,
    )

    if fact.height == 0:
        return pl.DataFrame()

    if fact["contract_date"].dtype != pl.Date:
        fact = fact.with_columns(pl.col("contract_date").cast(pl.Date))
    fact = fact.with_columns(pl.col("contract_date").alias("date")).filter(pl.col("date").is_not_null())

    def assign_band(price):
        for low, high, name in PRICE_BANDS:
            if low <= price < high:
                return name
        return "Unknown"

    fact = fact.with_columns(
        pl.col("purchase_price")
        .map_elements(assign_band, return_dtype=pl.Utf8)
        .alias("price_band")
    )

    fact = fact.filter(pl.col("price_band") != "Unknown")

    daily = fact.group_by(["date", "price_band"]).agg(pl.col("purchase_price").alias("prices"))
    if daily.height == 0:
        return pl.DataFrame()

    all_dates = pl.date_range(
        daily["date"].min(),
        daily["date"].max(),
        interval="1d",
        eager=True
    ).cast(pl.Date)
    all_bands = BAND_NAMES

    full = daily.join(
        pl.DataFrame({"date": all_dates, "dummy": 1}),
        on="date",
        how="right"
    ).with_columns(pl.lit("dummy").alias("dummy2"))
    full = full.join(
        pl.DataFrame({"price_band": all_bands, "dummy": 1}),
        on="dummy",
        how="left"
    ).drop(["dummy", "dummy2"])

    full = full.with_columns(
        pl.when(pl.col("prices").is_null())
        .then(pl.lit([]))
        .otherwise(pl.col("prices"))
        .alias("prices")
    )

    results = []
    for band in all_bands:
        band_data = full.filter(pl.col("price_band") == band).sort("date")
        if band_data.is_empty():
            continue
        band_pd = band_data.to_pandas().set_index("date").sort_index()

        rolling_medians = []
        sales_28d = []
        dates = band_pd.index
        for date in dates:
            start_date = date - pd.Timedelta(days=27)
            window = band_pd.loc[start_date:date]
            prices = window["prices"].tolist()
            flat_prices = [p for sublist in prices for p in sublist]
            sales = len(flat_prices)
            median = np.median(flat_prices) if sales >= 5 else np.nan
            rolling_medians.append(median)
            sales_28d.append(sales)

        band_pd["rolling_median"] = rolling_medians
        band_pd["sales_28d"] = sales_28d
        band_pd["mom"] = band_pd["rolling_median"].pct_change(28)
        band_pd["qoq"] = band_pd["rolling_median"].pct_change(84)

        band_pd = band_pd.reset_index()[["date", "price_band", "rolling_median", "sales_28d", "mom", "qoq"]]
        results.append(pl.from_pandas(band_pd))

    if not results:
        return pl.DataFrame()
    return pl.concat(results)


def _render_price_band_block(dwelling: str, stable_ratio: float):
    st.markdown("### 价格区间趋势（NSW，独立于筛选器）")
    st.caption("基于 NSW 成交数据，展示各价格区间的每日28天滚动中位数。")

    data = load_price_band_data(dwelling)
    if data.is_empty():
        st.info(f"暂无价格区间数据（{dwelling}）。请检查 fact_sales 或数据量。")
        return

    band_preset = st.selectbox(
        "时间范围（价格区间）",
        options=["1 Month", "3 Month", "6 Month", "YTD", "1 Year", "3 Year", "5 Year", "10 Year", "Max"],
        index=4,
        key=f"band_time_{dwelling}"
    )

    global_min = data["date"].min()
    global_max = data["date"].max()
    start_ts, end_ts = _preset_start_end(global_min, global_max, band_preset)

    # 当前时间范围数据（用于展示 + 选 stable/latest）
    filtered = data.filter((pl.col("date") >= start_ts) & (pl.col("date") <= end_ts))

    # ===== 基准销量（过去一年 median）=====
    one_year_ago = global_max - pd.DateOffset(years=1)
    base_data = data.filter(pl.col("date") >= one_year_ago)
    base_sales = {}
    for band in BAND_NAMES:
        band_base = base_data.filter(pl.col("price_band") == band)
        base_sales[band] = band_base["sales_28d"].median() if band_base.height > 0 else 0

    # ====== 关键：用“排名表同口径”的方式计算 MoM/QoQ ======
    # 以 anchor_date 为锚点，取 anchor 与 anchor-28/84 的 rolling_median 做比值
    def _calc_change_from_anchor(band_df: pd.DataFrame, anchor_date, lag_days: int) -> float | None:
        if band_df.empty or anchor_date is None:
            return None
        anchor_date = pd.to_datetime(anchor_date).normalize()
        target_date = anchor_date - pd.Timedelta(days=lag_days)

        # band_df['date'] 已经是 date 类型（pd datetime64），但这里再保险
        # 取两天的值（rolling_median 必须非空）
        a = band_df.loc[band_df["date"] == anchor_date, "rolling_median"]
        b = band_df.loc[band_df["date"] == target_date, "rolling_median"]

        if a.empty or b.empty:
            return None
        a_val = a.iloc[0]
        b_val = b.iloc[0]
        if pd.isna(a_val) or pd.isna(b_val) or b_val == 0:
            return None
        return float(a_val) / float(b_val) - 1.0

    # 表格
    table_rows = []

    for band in BAND_NAMES:
        band_pl = filtered.filter(pl.col("price_band") == band)

        # 只考虑 rolling_median 非空的行（和 ranking 表一致：有效点）
        band_pl_valid = band_pl.filter(pl.col("rolling_median").is_not_null())

        if band_pl_valid.height == 0:
            table_rows.append({
                "价格区间": band,
                "截止日": "",
                "28天滚动中位价": "",
                "28天总销量": "",
                "MoM": "",
                "QoQ": "",
                "稳定截止日": "",
                "稳定28天滚动中位价": "",
                "稳定28天总销量": "",
                "稳定MoM": "",
                "稳定QoQ": "",
            })
            continue

        band_pd = band_pl_valid.sort("date").to_pandas()
        # 确保 date 归一化
        band_pd["date"] = pd.to_datetime(band_pd["date"]).dt.normalize()

        # ---------- 普通（latest 有效点）----------
        latest_row = band_pd.iloc[-1]
        latest_date = latest_row["date"]
        latest_median = latest_row["rolling_median"]
        latest_sales = latest_row["sales_28d"]

        mom = _calc_change_from_anchor(band_pd, latest_date, 28)
        qoq = _calc_change_from_anchor(band_pd, latest_date, 84)

        # ---------- 稳定（latest stable 有效点）----------
        threshold = base_sales.get(band, 0) * float(stable_ratio)
        if base_sales.get(band, 0) > 0:
            stable_pd = band_pd[band_pd["sales_28d"] >= threshold].copy()
        else:
            # 没有基准销量：视为全可稳定（沿用你之前逻辑）
            stable_pd = band_pd.copy()

        if stable_pd.empty:
            stable_date = None
            stable_median = None
            stable_sales = None
            stable_mom = None
            stable_qoq = None
        else:
            stable_row = stable_pd.iloc[-1]
            stable_date = stable_row["date"]
            stable_median = stable_row["rolling_median"]
            stable_sales = stable_row["sales_28d"]

            # ✅ 这里用“稳定锚点 vs 稳定锚点-28/84”的同口径算法
            stable_mom = _calc_change_from_anchor(band_pd, stable_date, 28)
            stable_qoq = _calc_change_from_anchor(band_pd, stable_date, 84)

        table_rows.append({
            "价格区间": band,

            "截止日": fmt_date(latest_date),
            "28天滚动中位价": fmt_float0(latest_median),
            "28天总销量": fmt_int(latest_sales),
            "MoM": fmt_pct(mom),
            "QoQ": fmt_pct(qoq),

            "稳定截止日": fmt_date(stable_date),
            "稳定28天滚动中位价": fmt_float0(stable_median),
            "稳定28天总销量": fmt_int(stable_sales),
            "稳定MoM": fmt_pct(stable_mom),
            "稳定QoQ": fmt_pct(stable_qoq),
        })

    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

    # ===== 图表（保持原逻辑，stable 仍用于虚线显示）=====
    st.markdown("**各价格区间28天滚动中位价趋势**")
    available_bands = filtered["price_band"].unique().to_list()
    if len(available_bands) == 0:
        st.info("无图表数据。")
        return

    selected_bands = st.multiselect(
        "选择要显示的价格区间",
        options=sorted(available_bands),
        default=sorted(available_bands),
        key=f"band_select_{dwelling}"
    )
    if not selected_bands:
        st.info("请至少选择一个价格区间。")
        return

    chart_df = filtered.filter(pl.col("price_band").is_in(selected_bands)).to_pandas()
    chart_df = chart_df[["date", "price_band", "rolling_median", "sales_28d"]].rename(
        columns={"date": "event_time", "rolling_median": "value"}
    )
    chart_df = chart_df.dropna(subset=["value"])
    if chart_df.empty:
        st.info("所选区间在时间范围内无数据。")
        return

    chart_df["base_sales"] = chart_df["price_band"].map(base_sales)
    chart_df["stable"] = chart_df["sales_28d"] >= chart_df["base_sales"] * stable_ratio

    chart = build_band_chart(
        chart_df,
        value_col="value",
        time_col="event_time",
        band_col="price_band",
        sales_col="sales_28d",
        stable_col="stable",
    )
    st.altair_chart(chart, use_container_width=True)


# ========== AREA 层级辅助 ==========
@st.cache_data(ttl=3600, show_spinner=False)
def get_area_options():
    daily_suburb = load_daily_rolling("SUBURB")
    daily_postcode = load_daily_rolling("POSTCODE")
    dim_suburb_postcode = load_dim_suburb_postcode()

    area_items = []
    if not daily_suburb.is_empty() and not dim_suburb_postcode.is_empty():
        suburbs = daily_suburb["region"].unique().to_list()
        suburb_map = dict(zip(
            dim_suburb_postcode["suburb"].str.strip_chars().to_list(),
            dim_suburb_postcode["postcode"].str.strip_chars().to_list()
        ))
        for s in suburbs:
            pc = suburb_map.get(s, "")
            label = f"{s} ({pc})" if pc else s
            area_items.append((label, s))
    if not daily_postcode.is_empty():
        postcodes = daily_postcode["region"].unique().to_list()
        for pc in postcodes:
            label = f"Postcode {pc}"
            area_items.append((label, pc))
    area_items = sorted(area_items, key=lambda x: x[0])
    return area_items


# ========== 主函数 ==========
def main():
    st.set_page_config(page_title="Market View", layout="wide")
    ensure_lang()

    with st.sidebar:
        st.markdown("---")
        stable_ratio = st.slider("稳定阈值 (stable_ratio)", 0.0, 1.0, STABLE_RATIO, 0.05, key="stable_ratio")

        # ✅ NEW: 稳定排名销量阈值作为可输入 filter
        min_stable_sales_28d = st.number_input(
            "稳定排名最小销量（28d sales ≥）",
            min_value=0,
            max_value=10_000,
            value=20,
            step=1,
            help="只影响“稳定排名”榜单：仅纳入 28 天总销量 >= 该阈值的 suburb，然后取前五/后五。",
            key="min_stable_sales_28d",
        )

        opts = sidebar_common()

    level = opts["level"]
    dwelling = opts["dwelling"]

    st.title(t("app_title"))

    overlay = st.empty()
    _show_loading_overlay(overlay, t("loading"))

    try:
        if level == "NSW":
            daily = load_daily_rolling("NSW")
        elif level == "REGION":
            daily = load_daily_rolling("REGION")
        elif level == "AREA":
            daily_suburb = load_daily_rolling("SUBURB")
            daily_postcode = load_daily_rolling("POSTCODE")
            daily = pl.concat([daily_suburb, daily_postcode])
        else:
            daily = pl.DataFrame()

        if len(daily) == 0:
            st.error("无每日滚动数据，请先运行 build_mart_daily_rolling.py")
            return

        daily = daily.with_columns(pl.col("region").cast(pl.Utf8).str.strip_chars())
        min_date = daily["date"].min()
        max_date = daily["date"].max()

        if level == "AREA":
            area_items = get_area_options()
            area_labels = [item[0] for item in area_items]
            area_value_map = dict(area_items)
        else:
            area_labels = []
            area_value_map = {}

    finally:
        overlay.empty()

    if min_date is None or max_date is None:
        st.error(t("no_data"))
        return

    # 区域选择
    if level == "NSW":
        regions_selected = ["NSW"]
    elif level == "REGION":
        regions = daily["region"].unique().sort().to_list()
        regions_selected = st.multiselect(
            t("region_select"),
            options=regions,
            default=[],
            key="region_select_region"
        )
    else:  # AREA
        selected_labels = st.multiselect(
            t("region_select"),
            options=area_labels,
            default=[],
            key="region_select_area",
            placeholder="输入 suburb 或 postcode 搜索..."
        )
        regions_selected = [area_value_map[lbl] for lbl in selected_labels]

    # 主图时间预设
    st.caption(t("basic_time_hint"))
    preset = st.selectbox(
        t("time_preset"),
        options=["1 Month", "3 Month", "6 Month", "YTD", "1 Year", "3 Year", "5 Year", "10 Year", "Max"],
        index=4,
        key="time_preset",
    )
    start_ts, end_ts = _preset_start_end(min_date, max_date, preset)

    st.subheader(t("main_chart"))

    if level != "NSW" and len(regions_selected) == 0:
        st.warning(t("warning_region"))
        return

    # 过滤图表数据
    df_chart = daily.filter(pl.col("dwelling_group") == dwelling).to_pandas()
    df_chart = df_chart[(df_chart["date"] >= start_ts) & (df_chart["date"] <= end_ts)]
    if level != "NSW":
        df_chart = df_chart[df_chart["region"].isin(regions_selected)]

    if df_chart.empty:
        st.info(t("no_data"))
        return

    plot_df = df_chart[["date", "region", "rolling_median", "sales_28d"]].copy()
    plot_df.rename(columns={"date": "event_time", "rolling_median": "value"}, inplace=True)
    plot_df["series"] = "28天滚动中位价"
    plot_df = plot_df[plot_df["value"].notna()].copy()
    if plot_df.empty:
        st.info(t("no_data"))
        return

    # 计算基准销量
    one_year_ago = max_date - pd.DateOffset(years=1)
    base_df = daily.filter(pl.col("date") >= one_year_ago).to_pandas()
    base_sales = base_df.groupby("region")["sales_28d"].median().to_dict()
    plot_df["base_sales"] = plot_df["region"].map(base_sales).fillna(0)
    plot_df["stable"] = plot_df["sales_28d"] >= plot_df["base_sales"] * stable_ratio

    chart = build_interactive_chart(
        plot_df,
        level=level,
        time_col="event_time",
        time_title=t("axis_week"),
        time_format="%b %Y",
        include_sales=True,
        sales_col="sales_28d",
        sales_title="28天总销量",
        stable_col="stable",
    )
    st.altair_chart(chart, use_container_width=True)

    # 区域概览表
    st.markdown("---")
    st.subheader("区域概览（基于28天滚动数据）")
    st.caption("左侧为普通值，右侧为稳定值（销量达到基准阈值的点）。")

    tab1, tab2 = st.tabs(["普通概览", "稳定概览"])
    with tab1:
        df_overview = build_region_overview_table(
            daily_df=daily.to_pandas(),
            regions=regions_selected if level != "NSW" else ["NSW"],
            dwelling=dwelling,
            use_stable=False,
        )
        if df_overview.empty:
            st.info(t("no_data"))
        else:
            st.dataframe(df_overview, use_container_width=True, hide_index=True)

    with tab2:
        df_stable_overview = build_region_overview_table(
            daily_df=daily.to_pandas(),
            regions=regions_selected if level != "NSW" else ["NSW"],
            dwelling=dwelling,
            use_stable=True,
            stable_ratio=stable_ratio,
            base_sales=base_sales if level != "NSW" else None
        )
        if df_stable_overview.empty:
            st.info("无稳定数据（尝试降低稳定阈值）")
        else:
            st.dataframe(df_stable_overview, use_container_width=True, hide_index=True)

    # 排名表
    st.markdown("---")
    tab_house, tab_unit = st.tabs(["House", "Unit"])
    with tab_house:
        _render_rank_block_suburb("HOUSE", stable_ratio, int(min_stable_sales_28d))
    with tab_unit:
        _render_rank_block_suburb("UNIT", stable_ratio, int(min_stable_sales_28d))

    # 价格分档模块
    st.markdown("---")
    st.subheader("价格区间分析（NSW）")
    tab_band_house, tab_band_unit = st.tabs(["House", "Unit"])
    with tab_band_house:
        _render_price_band_block("HOUSE", stable_ratio)
    with tab_band_unit:
        _render_price_band_block("UNIT", stable_ratio)


if __name__ == "__main__":
    main()