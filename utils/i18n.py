import streamlit as st


I18N = {
    "zh": {
        "app_title": "NSW 房产决策平台",
        "nav_market_view": "市场概览",
        "nav_ranking": "区域排名",
        "nav_buy_budget": "买房预算",
        "nav_rent_budget": "租房预算",
        "lang": "语言",
        "lang_zh": "中文",
        "lang_en": "English",
        "sidebar_dwelling_title": "房产类型",
        "dwelling_group": "房产类型",
        "dwelling_house": "House",
        "dwelling_unit": "Unit",
        "no_data": "没有数据，请检查当前筛选条件或数据文件。",
        "market_view_title": "市场概览",
        "market_view_note": "基于当前滚动 mart 口径展示稳定与非稳定尾段，不改动现有 rolling 定义。",
        "data_as_of": "数据截至",
        "time_range": "时间范围",
        "data_level": "数据层级",
        "stable_ratio": "稳定阈值",
        "region": "区域",
        "display_mode": "显示模式",
        "display_mode_dual": "双线",
        "display_mode_short": "仅短期",
        "display_mode_long": "仅长期",
        "rolling_median_trend": "滚动中位价走势",
        "rolling_median_trend_note": "28 天滚动中位价展示短期变化，底层趋势线展示平滑后的长期方向，右侧尾段按既有规则弱化显示。",
        "sales_28d": "28 天成交量",
        "axis_price": "价格（AUD）",
        "axis_week": "周",
        "col_region": "区域",
        "col_sales": "成交量",
        "core_metrics": "核心指标",
        "price_band_trend": "价格区间走势",
        "price_band_trend_note": "同图展示短期线与长期线，可通过显示模式切换更专注地观察短期或长期变化。",
        "price_band": "价格区间",
        "all_price_bands_yoy": "各价格区间稳定中位价 · YoY（最新稳定点 vs 去年同日稳定点）",
        "vs_same_date_last_year": "对比去年同日",
        "stable_movers": "稳定涨跌榜",
        "stable_movers_note": "基于最新稳定中位价与上年同日稳定中位价的同比变化排序。",
        "stable_gainers": "稳定涨幅榜",
        "stable_losers": "稳定跌幅榜",
        "select_region": "请选择区域。",
        "loading_market_view": "加载市场概览中...",
        "market_view_no_band_data": "暂无价格区间数据。",
        "market_view_no_band_filtered_data": "当前时间范围或价格区间下暂无数据。",
        "market_view_no_stable_ranking": "当前没有可展示的稳定排名数据。",
        "market_view_missing_daily": "无每日滚动数据，请先运行 build_mart_daily_rolling.py",
        "search_suburb_or_postcode": "搜索 suburb 或 postcode",
        "ranking_title": "区域排名",
        "ranking_subtitle": "完整展示当前筛选下的所有 suburb，按稳定同比排序。",
        "ranking_all_regions": "全部区域",
        "calibre": "口径",
        "stable": "稳定",
        "standard": "普通",
        "sort": "排序",
        "descending": "降序",
        "ascending": "升序",
        "median_range": "中位价范围",
        "sales_volume": "成交量",
        "stable_yoy_range": "稳定同比范围",
        "min_value": "最小值",
        "max_value": "最大值",
        "ranking_empty": "当前筛选下无数据。",
        "rank": "排名",
        "postcode": "邮编",
        "median_price": "中位价",
        "stable_median_price": "稳定中位价",
        "as_of": "截止日",
        "stable_as_of": "稳定截止日",
        "stable_yoy": "稳定同比",
    },
    "en": {
        "app_title": "NSW Property Decision Platform",
        "nav_market_view": "Market View",
        "nav_ranking": "Ranking",
        "nav_buy_budget": "Buy Budget",
        "nav_rent_budget": "Rent Budget",
        "lang": "Language",
        "lang_zh": "中文",
        "lang_en": "English",
        "sidebar_dwelling_title": "Dwelling Type",
        "dwelling_group": "Dwelling type",
        "dwelling_house": "House",
        "dwelling_unit": "Unit",
        "no_data": "No data. Check the current filters or data files.",
        "market_view_title": "Market View",
        "market_view_note": "Shows the stable and unstable tail under the current rolling mart definition without changing the existing rolling logic.",
        "data_as_of": "Data as of",
        "time_range": "Time range",
        "data_level": "Data level",
        "stable_ratio": "Stability threshold",
        "region": "Region",
        "display_mode": "Display mode",
        "display_mode_dual": "Dual",
        "display_mode_short": "Short-term only",
        "display_mode_long": "Long-term only",
        "rolling_median_trend": "Rolling Median Trend",
        "rolling_median_trend_note": "The 28-day rolling median shows short-term movement, while the underlying trend line shows the smoothed long-term direction and the right-edge tail is visually weakened under the existing rule.",
        "sales_28d": "28-day sales",
        "axis_price": "Price (AUD)",
        "axis_week": "Week",
        "col_region": "Region",
        "col_sales": "Sales",
        "core_metrics": "Core Metrics",
        "price_band_trend": "Price Band Trend",
        "price_band_trend_note": "Shows short-term and long-term lines together, with display modes to focus on either horizon.",
        "price_band": "Price band",
        "all_price_bands_yoy": "Stable median by price band · YoY (latest stable point vs same day last year)",
        "vs_same_date_last_year": "vs same date last year",
        "stable_movers": "Stable Movers",
        "stable_movers_note": "Sorted by YoY change between the latest stable median and the stable median on the same day last year.",
        "stable_gainers": "Stable Gainers",
        "stable_losers": "Stable Losers",
        "select_region": "Please select a region.",
        "loading_market_view": "Loading market view...",
        "market_view_no_band_data": "No price-band data is available.",
        "market_view_no_band_filtered_data": "No data is available for the current time range or price-band selection.",
        "market_view_no_stable_ranking": "No stable ranking data is available for display.",
        "market_view_missing_daily": "No daily rolling data was found. Run build_mart_daily_rolling.py first.",
        "search_suburb_or_postcode": "Search suburb or postcode",
        "ranking_title": "Ranking",
        "ranking_subtitle": "Shows all suburbs under the current filters, sorted by stable YoY.",
        "ranking_all_regions": "All regions",
        "calibre": "Calibre",
        "stable": "Stable",
        "standard": "Standard",
        "sort": "Sort",
        "descending": "Descending",
        "ascending": "Ascending",
        "median_range": "Median range",
        "sales_volume": "Sales volume",
        "stable_yoy_range": "Stable YoY range",
        "min_value": "Min",
        "max_value": "Max",
        "ranking_empty": "No data is available under the current filters.",
        "rank": "Rank",
        "postcode": "Postcode",
        "median_price": "Median price",
        "stable_median_price": "Stable median price",
        "as_of": "As of",
        "stable_as_of": "Stable as of",
        "stable_yoy": "Stable YoY",
    },
}


def ensure_lang() -> None:
    if "lang" not in st.session_state:
        st.session_state["lang"] = "zh"


def get_lang() -> str:
    ensure_lang()
    return st.session_state.get("lang", "zh")


def set_lang(lang: str) -> None:
    st.session_state["lang"] = "en" if str(lang) == "en" else "zh"


def t(key: str) -> str:
    ensure_lang()
    lang = get_lang()
    return I18N.get(lang, I18N["zh"]).get(key, key)


def tr(zh: str, en: str) -> str:
    return zh if get_lang() == "zh" else en


def language_options() -> list[str]:
    return ["zh", "en"]


def language_label(lang: str) -> str:
    return t("lang_zh") if lang == "zh" else t("lang_en")
