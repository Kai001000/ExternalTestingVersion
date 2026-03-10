# app_median_price未分解版本.py
from pathlib import Path
import re
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt

# =====================
# Paths
# =====================
BASE_DIR = Path(r"C:\Users\jonat\PycharmProjects\NSWpropertyData")
MART_WEEKLY_DIR = BASE_DIR / "Processed" / "mart_weekly"
MART_MONTHLY_DIR = BASE_DIR / "Processed" / "mart_monthly"

PRICE_MAX = 100_000_000
PRICE_MIN_EXCLUSIVE = 0

ROLL_WINDOWS = {
    "roll4": 4,
    "roll13": 13,
}

# =====================
# i18n
# =====================
I18N = {
    "zh": {
        "app_title": "NSW 房产周度价格仪表盘（House / Unit）",
        "sidebar_title": "控制面板",
        "lang": "语言 / Language",
        "lang_zh": "中文",
        "lang_en": "English",

        "advanced": "高级选项",
        "dataset_label": "数据范围（自动识别）",

        "data_level": "数据层级",
        "level_nsw": "NSW（全州）",
        "level_region": "Region（Greater Sydney / Rest of NSW）",
        "level_suburb": "Suburb（城区）",
        "level_postcode": "Postcode（邮编）",

        "dwelling_group": "房产类型（单选）",

        "chart_range": "图表周起始时间范围（只影响图，不影响表）",
        "show_lines": "图上显示哪些线",
        "show_weekly_raw": "每周中位价（Raw Weekly Median）",
        "show_roll13": "13周滚动中位价（13W Rolling Median）",
        "show_roll4": "4周滚动中位价（4W Rolling Median）",
        "show_signal": "价格信号（Price Signal）",

        "show_kpi": "显示变化率指标（% Change）",
        "kpi_title": "变化率（基于 Rolling Median）",
        "kpi_hint": "4W% = 最新 / 4周前 - 1；13W% = 最新 / 13周前 - 1（按所选区域分别计算）。",

        "region_select": "选择区域（可多选；多选会显示多条线）",
        "warning_region": "请至少选择一个区域，或切换到 NSW 层级查看全州。",

        "main_chart": "价格走势（按周，按 Contract Date 归周）",
        "summary_title": "区域概览（不受图表时间范围影响）",
        "summary_hint": "NSW 层级会自动显示全州；其它层级需要选择区域。",

        "budget_title": "预算筛选（独立功能，不依赖图表选择）",
        "budget_hint": "只在 Region / Suburb / Postcode 层级生效。预算匹配与排序基于“最新价格信号（Signal）”；月度指标用于衡量流动性与波动。",
        "budget_min": "预算下限（AUD）",
        "budget_max": "预算上限（AUD）",
        "budget_topn": "显示前 N 条（按最新 Signal 从低到高）",
        "budget_table_note": "提示：这张表不受图表范围、区域选择影响。",

        "col_region": "区域",
        "col_dwelling": "类型",

        "col_latest_week": "最新周起始日",
        "col_latest_weekly_median": "最新周中位价",

        "col_latest_signal": "最新价格信号",
        "col_latest_conf": "信号可信度",
        "col_latest_signal_n": "信号成交数",
        "col_latest_signal_span": "信号跨度（天）",

        "col_52w_high_median": "近52周中位价最高（Median）",
        "col_52w_high_median_week": "最高发生周（Median）",
        "col_52w_low_median": "近52周中位价最低（Median）",
        "col_52w_low_median_week": "最低发生周（Median）",

        "col_52w_high_signal": "近52周价格信号最高（Signal）",
        "col_52w_high_signal_week": "最高发生周（Signal）",
        "col_52w_low_signal": "近52周价格信号最低（Signal）",
        "col_52w_low_signal_week": "最低发生周（Signal）",

        "no_data": "没有数据（请检查 mart 文件是否存在，或筛选条件是否过严）。",
        "need_level_budget": "预算表只在 Region / Suburb / Postcode 层级可用。",
        "need_level_summary": "概览表：NSW 会自动显示全州；其它层级需要选择区域。",
        "bad_schema_weekly": "weekly mart 文件结构不符合预期（缺少必要字段）。请先重新 build weekly mart。",
        "bad_schema_monthly": "monthly mart 文件结构不符合预期。请先 build monthly mart。",
        "pick_series": "至少勾选一条线（Raw / 4W / 13W / Signal）才能显示图表。",
        "budget_invalid": "budget_max 必须 >= budget_min",
        "axis_price": "价格（AUD）",
        "axis_week": "周起始日（Monday）",
        "series": "线条",

        "kpi_col_4w": "4W % 变化",
        "kpi_col_13w": "13W % 变化",
    },
    "en": {
        "app_title": "NSW Weekly Price Dashboard (House / Unit)",
        "sidebar_title": "Controls",
        "lang": "Language / 语言",
        "lang_zh": "中文",
        "lang_en": "English",

        "advanced": "Advanced",
        "dataset_label": "Dataset range (auto-detected)",

        "data_level": "Data level",
        "level_nsw": "NSW (Statewide)",
        "level_region": "Region (Greater Sydney / Rest of NSW)",
        "level_suburb": "Suburb",
        "level_postcode": "Postcode",

        "dwelling_group": "Dwelling group (single select)",

        "chart_range": "Chart week-start range (chart only; tables unaffected)",
        "show_lines": "Lines to show",
        "show_weekly_raw": "Raw weekly median",
        "show_roll13": "13-week rolling median",
        "show_roll4": "4-week rolling median",
        "show_signal": "Price signal",

        "show_kpi": "Show % change KPIs",
        "kpi_title": "% change (based on rolling median)",
        "kpi_hint": "4W% = latest / 4 weeks ago - 1; 13W% = latest / 13 weeks ago - 1 (per selected region).",

        "region_select": "Select regions (multi-select; multiple lines)",
        "warning_region": "Please select at least one region, or switch to NSW level.",

        "main_chart": "Price trend (weekly; week assigned by contract date)",
        "summary_title": "Area summary (NOT affected by chart date range)",
        "summary_hint": "NSW shows statewide automatically; other levels require selecting regions.",

        "budget_title": "Budget filter (independent; not linked to chart selection)",
        "budget_hint": "Only valid for Region/Suburb/Postcode. Budget match & sorting use the latest SIGNAL; monthly stats help assess liquidity/dispersion.",
        "budget_min": "Budget min (AUD)",
        "budget_max": "Budget max (AUD)",
        "budget_topn": "Show top N rows (sorted by latest signal asc)",
        "budget_table_note": "Note: This table is not affected by chart range or region selection.",

        "col_region": "Region",
        "col_dwelling": "Dwelling",

        "col_latest_week": "Latest week_start",
        "col_latest_weekly_median": "Latest weekly median",

        "col_latest_signal": "Latest price signal",
        "col_latest_conf": "Signal confidence",
        "col_latest_signal_n": "Signal sales used",
        "col_latest_signal_span": "Signal span (days)",

        "col_52w_high_median": "52W high (Median)",
        "col_52w_high_median_week": "High week (Median)",
        "col_52w_low_median": "52W low (Median)",
        "col_52w_low_median_week": "Low week (Median)",

        "col_52w_high_signal": "52W high (Signal)",
        "col_52w_high_signal_week": "High week (Signal)",
        "col_52w_low_signal": "52W low (Signal)",
        "col_52w_low_signal_week": "Low week (Signal)",

        "no_data": "No data. Check mart files or filters.",
        "need_level_budget": "Budget table is only available for Region/Suburb/Postcode level.",
        "need_level_summary": "Summary: NSW shows statewide automatically; other levels require selecting regions.",
        "bad_schema_weekly": "weekly mart schema is unexpected. Please rebuild weekly mart.",
        "bad_schema_monthly": "monthly mart schema is unexpected. Please build monthly mart first.",
        "pick_series": "Select at least one series (Raw/4W/13W/Signal) to show the chart.",
        "budget_invalid": "budget_max must be >= budget_min",
        "axis_price": "Price (AUD)",
        "axis_week": "Week start (Monday)",
        "series": "Series",

        "kpi_col_4w": "4W % change",
        "kpi_col_13w": "13W % change",
    },
}


def t(key: str) -> str:
    lang = st.session_state.get("lang", "zh")
    return I18N[lang][key]


# =====================
# Formatting helpers
# =====================
def fmt_int(x):
    if pd.isna(x):
        return ""
    try:
        return f"{int(x):,}"
    except:
        return ""


def fmt_float0(x):
    if pd.isna(x):
        return ""
    try:
        return f"{float(x):,.0f}"
    except:
        return ""


def fmt_pct(x):
    if pd.isna(x):
        return ""
    try:
        return f"{float(x) * 100:.1f}%"
    except:
        return ""


# =====================
# Display-only guards
# =====================
def coerce_numeric_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    d = df.copy()
    for c in cols:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def filter_price_range(df: pd.DataFrame, price_cols: list[str]) -> pd.DataFrame:
    d = df.copy()
    for c in price_cols:
        if c in d.columns:
            d = d[d[c].isna() | ((d[c] > PRICE_MIN_EXCLUSIVE) & (d[c] <= PRICE_MAX))]
    return d


# =====================
# Mart discovery
# =====================
def list_dataset_labels() -> list[str]:
    labels = set()
    for p in MART_WEEKLY_DIR.glob("mart_weekly_nsw_*.parquet"):
        m = re.search(r"mart_weekly_nsw_(.+)\.parquet$", p.name)
        if m:
            labels.add(m.group(1))
    return sorted(labels)


@st.cache_data(show_spinner=False)
def load_weekly(level: str, label: str) -> pd.DataFrame:
    if level == "NSW":
        path = MART_WEEKLY_DIR / f"mart_weekly_nsw_{label}.parquet"
    elif level == "REGION":
        path = MART_WEEKLY_DIR / f"mart_weekly_region_{label}.parquet"
    elif level == "SUBURB":
        path = MART_WEEKLY_DIR / f"mart_weekly_suburb_{label}.parquet"
    elif level == "POSTCODE":
        path = MART_WEEKLY_DIR / f"mart_weekly_postcode_{label}.parquet"
    else:
        raise ValueError("Bad level")

    if not path.exists():
        return pd.DataFrame()

    df = pd.read_parquet(path)
    if "event_week_start" in df.columns:
        df["event_week_start"] = pd.to_datetime(df["event_week_start"])
    return df


@st.cache_data(show_spinner=False)
def load_monthly(level: str, label: str) -> pd.DataFrame:
    if level == "NSW":
        path = MART_MONTHLY_DIR / f"mart_monthly_nsw_{label}.parquet"
    elif level == "REGION":
        path = MART_MONTHLY_DIR / f"mart_monthly_region_{label}.parquet"
    elif level == "SUBURB":
        path = MART_MONTHLY_DIR / f"mart_monthly_suburb_{label}.parquet"
    elif level == "POSTCODE":
        path = MART_MONTHLY_DIR / f"mart_monthly_postcode_{label}.parquet"
    else:
        raise ValueError("Bad level")

    if not path.exists():
        return pd.DataFrame()

    df = pd.read_parquet(path)
    if "event_month_start" in df.columns:
        df["event_month_start"] = pd.to_datetime(df["event_month_start"])
    return df


def normalize_region_values(df: pd.DataFrame, level: str) -> pd.DataFrame:
    d = df.copy()

    if "region" not in d.columns:
        if level == "NSW":
            d["region"] = "NSW"

    if "region" in d.columns:
        d["region"] = d["region"].astype(str).str.strip()
        d.loc[d["region"].isin(["None", "nan", "NaN"]), "region"] = ""
        if level == "POSTCODE":
            d["region"] = d["region"].str.replace(r"\.0$", "", regex=True)

    return d


# =====================
# Rolling metrics (computed in app; no ETL change)
# =====================
def add_rolling_medians(weekly: pd.DataFrame) -> pd.DataFrame:
    """
    Adds:
      - roll4_median: rolling(4) median of weekly_median_price
      - roll13_median: rolling(13) median of weekly_median_price

    Note:
      - rolling is done per (region, dwelling_group) and sorted by event_week_start.
      - min_periods = window (strict) to avoid misleading early values.
    """
    d = weekly.copy()
    d = d.sort_values(["region", "dwelling_group", "event_week_start"]).copy()

    def _roll(g: pd.DataFrame) -> pd.DataFrame:
        g = g.sort_values("event_week_start").copy()
        s = pd.to_numeric(g["weekly_median_price"], errors="coerce")
        g["roll4_median"] = s.rolling(ROLL_WINDOWS["roll4"], min_periods=ROLL_WINDOWS["roll4"]).median()
        g["roll13_median"] = s.rolling(ROLL_WINDOWS["roll13"], min_periods=ROLL_WINDOWS["roll13"]).median()
        return g

    d = d.groupby(["region", "dwelling_group"], group_keys=False).apply(_roll)
    return d


def build_kpi_table(weekly_with_roll: pd.DataFrame, regions: list[str], dwelling: str) -> pd.DataFrame:
    """
    KPI based on rolling medians:
      - 4W % change = latest roll4 / roll4.shift(4) - 1
      - 13W % change = latest roll13 / roll13.shift(13) - 1
    """
    w = weekly_with_roll[
        (weekly_with_roll["dwelling_group"] == dwelling) &
        (weekly_with_roll["region"].isin(regions))
    ].copy()
    if w.empty:
        return pd.DataFrame()

    out_rows = []
    for r in regions:
        g = w[w["region"] == r].sort_values("event_week_start").copy()
        if g.empty:
            continue

        g["roll4_prev4"] = g["roll4_median"].shift(4)
        g["roll13_prev13"] = g["roll13_median"].shift(13)

        latest = g.iloc[-1]
        v4 = latest.get("roll4_median")
        v4p = latest.get("roll4_prev4")
        v13 = latest.get("roll13_median")
        v13p = latest.get("roll13_prev13")

        ch4 = (v4 / v4p - 1) if pd.notna(v4) and pd.notna(v4p) and v4p != 0 else np.nan
        ch13 = (v13 / v13p - 1) if pd.notna(v13) and pd.notna(v13p) and v13p != 0 else np.nan

        out_rows.append({
            t("col_region"): r,
            t("col_dwelling"): dwelling,
            t("col_latest_week"): pd.to_datetime(latest["event_week_start"]).date(),
            t("kpi_col_4w"): ch4,
            t("kpi_col_13w"): ch13,
        })

    out = pd.DataFrame(out_rows)
    if out.empty:
        return out

    out[t("kpi_col_4w")] = out[t("kpi_col_4w")].apply(fmt_pct)
    out[t("kpi_col_13w")] = out[t("kpi_col_13w")].apply(fmt_pct)
    return out


# =====================
# Summary helpers
# =====================
def build_selected_summary(weekly_df: pd.DataFrame, regions: list[str], dwelling: str) -> pd.DataFrame:
    w = weekly_df[(weekly_df["dwelling_group"] == dwelling) & (weekly_df["region"].isin(regions))].copy()
    if w.empty:
        return pd.DataFrame()

    out_rows = []
    for r in regions:
        wr = w[w["region"] == r].sort_values("event_week_start").copy()
        if wr.empty:
            continue

        latest_week = wr.iloc[-1]
        tail52 = wr.tail(52).copy()

        high_median_row = low_median_row = None
        t52m = tail52.dropna(subset=["weekly_median_price"])
        if not t52m.empty:
            high_median_row = t52m.loc[t52m["weekly_median_price"].idxmax()]
            low_median_row = t52m.loc[t52m["weekly_median_price"].idxmin()]

        high_signal_row = low_signal_row = None
        t52s = tail52.dropna(subset=["signal_price"])
        if not t52s.empty:
            high_signal_row = t52s.loc[t52s["signal_price"].idxmax()]
            low_signal_row = t52s.loc[t52s["signal_price"].idxmin()]

        row = {
            t("col_region"): r,
            t("col_dwelling"): dwelling,

            t("col_latest_week"): latest_week["event_week_start"].date(),
            t("col_latest_weekly_median"): latest_week.get("weekly_median_price"),

            t("col_latest_signal"): latest_week.get("signal_price"),
            t("col_latest_conf"): latest_week.get("signal_confidence"),
            t("col_latest_signal_n"): latest_week.get("signal_n_sales"),
            t("col_latest_signal_span"): latest_week.get("signal_span_days"),
        }

        if high_median_row is not None:
            row[t("col_52w_high_median")] = high_median_row["weekly_median_price"]
            row[t("col_52w_high_median_week")] = high_median_row["event_week_start"].date()
        else:
            row[t("col_52w_high_median")] = None
            row[t("col_52w_high_median_week")] = None

        if low_median_row is not None:
            row[t("col_52w_low_median")] = low_median_row["weekly_median_price"]
            row[t("col_52w_low_median_week")] = low_median_row["event_week_start"].date()
        else:
            row[t("col_52w_low_median")] = None
            row[t("col_52w_low_median_week")] = None

        if high_signal_row is not None:
            row[t("col_52w_high_signal")] = high_signal_row["signal_price"]
            row[t("col_52w_high_signal_week")] = high_signal_row["event_week_start"].date()
        else:
            row[t("col_52w_high_signal")] = None
            row[t("col_52w_high_signal_week")] = None

        if low_signal_row is not None:
            row[t("col_52w_low_signal")] = low_signal_row["signal_price"]
            row[t("col_52w_low_signal_week")] = low_signal_row["event_week_start"].date()
        else:
            row[t("col_52w_low_signal")] = None
            row[t("col_52w_low_signal_week")] = None

        out_rows.append(row)

    df_out = pd.DataFrame(out_rows)
    if df_out.empty:
        return df_out

    money_cols = [
        t("col_latest_weekly_median"),
        t("col_latest_signal"),
        t("col_52w_high_median"),
        t("col_52w_low_median"),
        t("col_52w_high_signal"),
        t("col_52w_low_signal"),
    ]
    int_cols = [t("col_latest_signal_n"), t("col_latest_signal_span")]

    for c in money_cols:
        if c in df_out.columns:
            df_out[c] = df_out[c].apply(fmt_float0)
    for c in int_cols:
        if c in df_out.columns:
            df_out[c] = df_out[c].apply(fmt_int)

    return df_out


def build_budget_table(
    weekly_df: pd.DataFrame,
    monthly_df: pd.DataFrame,
    dwelling: str,
    budget_min: int,
    budget_max: int,
    topn: int
) -> pd.DataFrame:
    w = weekly_df[weekly_df["dwelling_group"] == dwelling].copy()
    m = monthly_df[monthly_df["dwelling_group"] == dwelling].copy()

    if w.empty or m.empty:
        return pd.DataFrame()

    w_latest = w.sort_values("event_week_start").groupby("region", as_index=False).tail(1).copy()
    m_latest = m.sort_values("event_month_start").groupby("region", as_index=False).tail(1).copy()

    j = w_latest.merge(m_latest, on=["region", "dwelling_group"], how="left")

    j = j[
        j["signal_price"].notna()
        & (j["signal_price"] >= budget_min)
        & (j["signal_price"] <= budget_max)
    ].copy()

    if j.empty:
        return pd.DataFrame()

    j = j.sort_values("signal_price").head(topn)

    out = pd.DataFrame({
        t("col_region"): j["region"],
        t("col_dwelling"): j["dwelling_group"],

        t("col_latest_week"): pd.to_datetime(j["event_week_start"]).dt.date,
        t("col_latest_signal"): j.get("signal_price"),
        t("col_latest_conf"): j.get("signal_confidence"),
        t("col_latest_signal_n"): j.get("signal_n_sales"),
        t("col_latest_signal_span"): j.get("signal_span_days"),

        "Month start": pd.to_datetime(j["event_month_start"]).dt.date if "event_month_start" in j.columns else None,
        "Monthly median": j.get("monthly_median_price"),
        "Monthly sales": j.get("monthly_sales_count"),
        "Monthly max": j.get("monthly_max_price"),
        "Monthly min": j.get("monthly_min_price"),
    })

    if st.session_state.get("lang", "zh") == "zh":
        out.rename(columns={
            "Month start": "最新月起始日",
            "Monthly median": "最新月中位价",
            "Monthly sales": "最新月成交量",
            "Monthly max": "最新月最高成交价",
            "Monthly min": "最新月最低成交价",
        }, inplace=True)
        m_money = ["最新月中位价", "最新月最高成交价", "最新月最低成交价"]
        m_int = ["最新月成交量"]
    else:
        out.rename(columns={
            "Month start": "Latest month_start",
            "Monthly median": "Latest monthly median",
            "Monthly sales": "Latest monthly sales",
            "Monthly max": "Latest monthly max",
            "Monthly min": "Latest monthly min",
        }, inplace=True)
        m_money = ["Latest monthly median", "Latest monthly max", "Latest monthly min"]
        m_int = ["Latest monthly sales"]

    for c in [t("col_latest_signal")] + m_money:
        if c in out.columns:
            out[c] = out[c].apply(fmt_float0)

    for c in [t("col_latest_signal_n"), t("col_latest_signal_span")] + m_int:
        if c in out.columns:
            out[c] = out[c].apply(fmt_int)

    return out


# =====================
# Chart helper
# =====================
def build_interactive_chart(plot_df: pd.DataFrame, level: str) -> alt.Chart:
    plot_df = plot_df.copy()
    plot_df["value"] = pd.to_numeric(plot_df["value"], errors="coerce").round(0)

    for c in ["signal_n_sales", "signal_span_days"]:
        if c in plot_df.columns:
            plot_df[c] = pd.to_numeric(plot_df[c], errors="coerce")

    hover = alt.selection_point(
        fields=["event_week_start", "region", "series"],
        nearest=True,
        on="mouseover",
        empty=False,
        clear="mouseout",
    )

    y_enc = alt.Y("value:Q", title=t("axis_price"), axis=alt.Axis(format=",.0f"))
    x_enc = alt.X("event_week_start:T", title=t("axis_week"))

    base_tt = [
        alt.Tooltip("event_week_start:T", title=t("axis_week")),
        alt.Tooltip("region:N", title=t("col_region")),
        alt.Tooltip("series:N", title=t("series")),
        alt.Tooltip("value:Q", title=t("axis_price"), format=",.0f"),
    ]

    signal_tt = base_tt + [
        alt.Tooltip("signal_confidence:N", title=t("col_latest_conf")),
        alt.Tooltip("signal_n_sales:Q", title=t("col_latest_signal_n"), format="d"),
        alt.Tooltip("signal_span_days:Q", title=t("col_latest_signal_span"), format="d"),
    ]

    layers = []

    for sname in plot_df["series"].dropna().unique().tolist():
        sdf = plot_df[plot_df["series"] == sname].copy()
        if sdf.empty:
            continue

        if level == "NSW":
            color = alt.Color("series:N", title=None)
        else:
            color = alt.Color("region:N", title=t("col_region"))

        # Style: make rolling medians smoother visually (dashed difference optional)
        if sname in [t("show_roll13")]:
            dash = alt.value([1, 0])
        elif sname in [t("show_roll4")]:
            dash = alt.value([4, 2])
        elif sname in [t("show_signal")]:
            dash = alt.value([6, 3])
        else:
            dash = alt.value([1, 0])

        tt = signal_tt if sname == t("show_signal") else base_tt

        line = alt.Chart(sdf).mark_line().encode(
            x=x_enc,
            y=y_enc,
            color=color,
            strokeDash=dash,
            tooltip=tt,
        )

        pts = alt.Chart(sdf).mark_circle(size=55).encode(
            x="event_week_start:T",
            y="value:Q",
            color=color,
            opacity=alt.condition(hover, alt.value(1), alt.value(0)),
            tooltip=tt,
        ).add_params(hover)

        layers += [line, pts]

    rule = alt.Chart(plot_df).mark_rule().encode(
        x="event_week_start:T",
        opacity=alt.condition(hover, alt.value(0.35), alt.value(0))
    ).transform_filter(hover)

    return alt.layer(*layers, rule).properties(height=420).interactive()


# =====================
# Streamlit UI
# =====================
def main():
    st.set_page_config(page_title="NSW Price", layout="wide")

    if "lang" not in st.session_state:
        st.session_state["lang"] = "zh"

    labels = list_dataset_labels()
    if not labels:
        st.error(t("no_data"))
        return

    default_label = labels[-1]

    with st.sidebar:
        st.title(t("sidebar_title"))

        st.radio(
            t("lang"),
            options=["zh", "en"],
            format_func=lambda x: I18N[x]["lang_zh"] if x == "zh" else I18N[x]["lang_en"],
            horizontal=True,
            key="lang",
        )

        st.markdown("---")

        with st.expander(t("advanced"), expanded=False):
            st.selectbox(t("dataset_label"), labels, index=len(labels) - 1, key="dataset_label")
        if "dataset_label" not in st.session_state:
            st.session_state["dataset_label"] = default_label
        label = st.session_state.get("dataset_label", default_label)

        level = st.selectbox(
            t("data_level"),
            options=["NSW", "REGION", "SUBURB", "POSTCODE"],
            format_func=lambda x: (
                t("level_nsw") if x == "NSW"
                else (t("level_region") if x == "REGION"
                      else (t("level_suburb") if x == "SUBURB" else t("level_postcode")))
            ),
            key="data_level"
        )

        dwelling = st.radio(
            t("dwelling_group"),
            options=["HOUSE", "UNIT"],
            horizontal=True,
            key="dwelling_group"
        )

        st.markdown("---")
        st.caption(t("show_lines"))
        show_raw = st.checkbox(t("show_weekly_raw"), value=True, key="show_weekly_raw")
        show_r13 = st.checkbox(t("show_roll13"), value=True, key="show_roll13")
        show_r4 = st.checkbox(t("show_roll4"), value=False, key="show_roll4")
        show_signal = st.checkbox(t("show_signal"), value=False, key="show_signal")

        st.markdown("---")
        show_kpi = st.checkbox(t("show_kpi"), value=True, key="show_kpi")

    st.title(t("app_title"))

    weekly = load_weekly(level, label)
    if weekly.empty:
        st.error(t("no_data"))
        return
    weekly = normalize_region_values(weekly, level)

    monthly = load_monthly(level, label)
    if monthly.empty:
        st.error(t("bad_schema_monthly"))
        return
    monthly = normalize_region_values(monthly, level)

    required_weekly = {
        "event_week_start", "region", "dwelling_group",
        "weekly_sales_count", "weekly_median_price", "weekly_max_price", "weekly_min_price",
        "signal_price", "signal_confidence", "signal_n_sales", "signal_span_days"
    }
    missing_weekly = required_weekly - set(weekly.columns)
    if missing_weekly:
        st.error(t("bad_schema_weekly"))
        st.write("Missing:", sorted(list(missing_weekly)))
        st.write("Columns:", list(weekly.columns))
        return

    required_monthly = {
        "event_month_start", "region", "dwelling_group",
        "monthly_sales_count", "monthly_median_price", "monthly_max_price", "monthly_min_price",
    }
    missing_monthly = required_monthly - set(monthly.columns)
    if missing_monthly:
        st.error(t("bad_schema_monthly"))
        st.write("Missing:", sorted(list(missing_monthly)))
        st.write("Columns:", list(monthly.columns))
        return

    weekly = coerce_numeric_cols(
        weekly,
        ["weekly_median_price", "weekly_max_price", "weekly_min_price", "weekly_sales_count",
         "signal_price", "signal_n_sales", "signal_span_days"]
    )
    weekly = filter_price_range(weekly, ["weekly_median_price", "weekly_max_price", "weekly_min_price", "signal_price"])

    monthly = coerce_numeric_cols(
        monthly,
        ["monthly_median_price", "monthly_max_price", "monthly_min_price", "monthly_sales_count"]
    )
    monthly = filter_price_range(monthly, ["monthly_median_price", "monthly_max_price", "monthly_min_price"])

    # --- Rolling in-app (no ETL change) ---
    weekly = add_rolling_medians(weekly)

    min_date = pd.to_datetime(weekly["event_week_start"]).min().date()
    max_date = pd.to_datetime(weekly["event_week_start"]).max().date()

    # --- Region selection ---
    if level == "NSW":
        regions_selected = ["NSW"]
    else:
        regions = sorted([r for r in weekly["region"].dropna().astype(str).unique().tolist() if r.strip() != ""])
        regions_selected = st.multiselect(
            t("region_select"),
            options=regions,
            default=[],
            key=f"region_select_{level}"
        )

    start_date, end_date = st.slider(
        t("chart_range"),
        min_value=min_date,
        max_value=max_date,
        value=(min_date, max_date),
        key="chart_range"
    )

    # ============ MAIN CHART ============
    st.subheader(t("main_chart"))

    if level != "NSW" and len(regions_selected) == 0:
        st.warning(t("warning_region"))
    else:
        if not (show_raw or show_r4 or show_r13 or show_signal):
            st.info(t("pick_series"))
        else:
            df_chart = weekly[weekly["dwelling_group"] == dwelling].copy()
            df_chart = df_chart[
                (df_chart["event_week_start"].dt.date >= start_date) &
                (df_chart["event_week_start"].dt.date <= end_date)
            ].copy()

            if level != "NSW":
                df_chart = df_chart[df_chart["region"].isin(regions_selected)].copy()

            if df_chart.empty:
                st.info(t("no_data"))
            else:
                lines = []

                if show_raw:
                    tmp = df_chart[["event_week_start", "region", "weekly_median_price"]].copy()
                    tmp["series"] = t("show_weekly_raw")
                    tmp.rename(columns={"weekly_median_price": "value"}, inplace=True)
                    tmp["signal_confidence"] = None
                    tmp["signal_n_sales"] = None
                    tmp["signal_span_days"] = None
                    lines.append(tmp)

                if show_r13:
                    tmp = df_chart[["event_week_start", "region", "roll13_median"]].copy()
                    tmp["series"] = t("show_roll13")
                    tmp.rename(columns={"roll13_median": "value"}, inplace=True)
                    tmp["signal_confidence"] = None
                    tmp["signal_n_sales"] = None
                    tmp["signal_span_days"] = None
                    lines.append(tmp)

                if show_r4:
                    tmp = df_chart[["event_week_start", "region", "roll4_median"]].copy()
                    tmp["series"] = t("show_roll4")
                    tmp.rename(columns={"roll4_median": "value"}, inplace=True)
                    tmp["signal_confidence"] = None
                    tmp["signal_n_sales"] = None
                    tmp["signal_span_days"] = None
                    lines.append(tmp)

                if show_signal:
                    tmp = df_chart[[
                        "event_week_start", "region", "signal_price",
                        "signal_confidence", "signal_n_sales", "signal_span_days"
                    ]].copy()
                    tmp["series"] = t("show_signal")
                    tmp.rename(columns={"signal_price": "value"}, inplace=True)
                    lines.append(tmp)

                plot_df = pd.concat(lines, ignore_index=True) if lines else pd.DataFrame()
                plot_df = plot_df[plot_df["value"].notna()].copy()

                if plot_df.empty:
                    st.info(t("no_data"))
                else:
                    chart = build_interactive_chart(plot_df, level)
                    st.altair_chart(chart, use_container_width=True)

    # ============ KPI TABLE ============
    if show_kpi and (level == "NSW" or len(regions_selected) > 0):
        st.markdown("---")
        st.subheader(t("kpi_title"))
        st.caption(t("kpi_hint"))

        kpi_regions = ["NSW"] if level == "NSW" else regions_selected
        df_kpi = build_kpi_table(weekly, kpi_regions, dwelling)
        if df_kpi.empty:
            st.info(t("no_data"))
        else:
            st.dataframe(df_kpi, use_container_width=True)

    # ============ SUMMARY TABLE ============
    st.markdown("---")
    st.subheader(t("summary_title"))
    st.caption(t("summary_hint"))

    if level == "NSW":
        df_summary = build_selected_summary(weekly, ["NSW"], dwelling)
        if df_summary.empty:
            st.info(t("no_data"))
        else:
            st.dataframe(df_summary, use_container_width=True)
    else:
        if len(regions_selected) > 0:
            df_summary = build_selected_summary(weekly, regions_selected, dwelling)
            if df_summary.empty:
                st.info(t("no_data"))
            else:
                st.dataframe(df_summary, use_container_width=True)
        else:
            st.info(t("need_level_summary"))

    # ============ BUDGET TABLE ============
    st.markdown("---")
    st.subheader(t("budget_title"))
    st.caption(t("budget_hint"))

    if level in ["REGION", "SUBURB", "POSTCODE"]:
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            budget_min = st.number_input(t("budget_min"), min_value=0, value=800000, step=50000, key="budget_min")
        with c2:
            budget_max = st.number_input(t("budget_max"), min_value=0, value=1200000, step=50000, key="budget_max")
        with c3:
            topn = st.number_input(t("budget_topn"), min_value=10, max_value=5000, value=200, step=10, key="budget_topn")

        if budget_max < budget_min:
            st.warning(t("budget_invalid"))
        else:
            df_budget = build_budget_table(weekly, monthly, dwelling, int(budget_min), int(budget_max), int(topn))
            st.caption(t("budget_table_note"))
            if df_budget.empty:
                st.info(t("no_data"))
            else:
                st.dataframe(df_budget, use_container_width=True)
    else:
        st.info(t("need_level_budget"))


if __name__ == "__main__":
    main()