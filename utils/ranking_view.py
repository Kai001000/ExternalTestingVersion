import pandas as pd
import streamlit as st

from utils.i18n import t
from utils.tables import fmt_date, fmt_float0, fmt_int, fmt_pct

UP_ARROW = chr(9650)
DOWN_ARROW = chr(9660)
FLAT_DOT = chr(8226)
POSITIVE_COLOR = "#027a48"
NEGATIVE_COLOR = "#b42318"
NEUTRAL_COLOR = "#475467"


def _format_currency(value) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    text = fmt_float0(value)
    return f"${text}" if text else "N/A"


def _format_change(value) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    value = float(value)
    if value > 0:
        return f"{UP_ARROW} {fmt_pct(value)}"
    if value < 0:
        return f"{DOWN_ARROW} {fmt_pct(abs(value))}"
    return f"{FLAT_DOT} 0.0%"


def _change_style(value) -> str:
    if value is None or pd.isna(value):
        return ""
    value = float(value)
    if value > 0:
        return f"color: {POSITIVE_COLOR}; font-weight: 700;"
    if value < 0:
        return f"color: {NEGATIVE_COLOR}; font-weight: 700;"
    return f"color: {NEUTRAL_COLOR};"


def build_rank_display_table(
    df: pd.DataFrame,
    metric: str,
    *,
    include_asof: bool,
    stable_mode: bool,
    limit: int | None = None,
) -> tuple[pd.DataFrame, pd.Series]:
    if df is None or df.empty:
        return pd.DataFrame(), pd.Series(dtype=float)

    metric = "Stable YoY"
    frame = df.copy()
    if limit is not None:
        frame = frame.head(int(limit)).copy()

    median_label = t("stable_median_price") if stable_mode and include_asof else t("median_price")
    asof_label = t("stable_as_of") if stable_mode else t("as_of")
    metric_label = t("stable_yoy")

    metric_values = pd.to_numeric(frame[metric], errors="coerce")
    display = pd.DataFrame(
        {
            t("rank"): range(1, len(frame) + 1),
            "Suburb": frame["Suburb"].fillna("").astype(str),
            t("postcode"): frame["Postcode"].fillna("").astype(str),
            median_label: frame["28d median"].apply(_format_currency),
            t("sales_volume"): frame["28d sales"].apply(fmt_int).replace("", "N/A"),
            metric_label: metric_values.apply(_format_change),
        }
    )

    if include_asof:
        display.insert(4, asof_label, frame["As of"].apply(fmt_date).replace("", "N/A"))

    metric_values.index = display.index
    return display, metric_values


def render_rank_table(
    df: pd.DataFrame,
    metric: str,
    *,
    include_asof: bool,
    stable_mode: bool,
    limit: int | None = None,
    height: int | None = None,
    empty_message: str | None = None,
):
    display, metric_values = build_rank_display_table(
        df,
        metric,
        include_asof=include_asof,
        stable_mode=stable_mode,
        limit=limit,
    )
    if display.empty:
        st.info(empty_message or t("ranking_empty"))
        return

    metric_label = t("stable_yoy")

    def _style_metric_column(col: pd.Series):
        if col.name != metric_label:
            return [""] * len(col)
        return [_change_style(metric_values.get(idx)) for idx in col.index]

    styler = display.style.apply(_style_metric_column, axis=0)
    st.dataframe(styler, hide_index=True, use_container_width=True, height=height)
