import pandas as pd
import streamlit as st

from utils.i18n import t, ensure_lang
from utils.config import PRICE_MAX, PRICE_MIN_EXCLUSIVE
from utils.data import list_dataset_labels, load_weekly, load_monthly, normalize_region_values
from utils.metrics import coerce_numeric_cols, filter_price_range
from utils.tables import build_budget_table
from utils.ui import sidebar_common


def _validate_schema(weekly: pd.DataFrame, monthly: pd.DataFrame) -> tuple[bool, str]:
    required_weekly = {
        "event_week_start", "region", "dwelling_group",
        "weekly_sales_count", "weekly_median_price", "weekly_max_price", "weekly_min_price",
        "signal_price", "signal_confidence", "signal_n_sales", "signal_span_days"
    }
    missing_weekly = required_weekly - set(weekly.columns)
    if missing_weekly:
        return False, f"{t('bad_schema_weekly')}\nMissing: {sorted(list(missing_weekly))}"

    required_monthly = {
        "event_month_start", "region", "dwelling_group",
        "monthly_sales_count", "monthly_median_price", "monthly_max_price", "monthly_min_price",
    }
    missing_monthly = required_monthly - set(monthly.columns)
    if missing_monthly:
        return False, f"{t('bad_schema_monthly')}\nMissing: {sorted(list(missing_monthly))}"

    return True, ""


def main():
    st.set_page_config(page_title="Budget", layout="wide")
    ensure_lang()

    labels = list_dataset_labels()
    if not labels:
        st.error(t("no_data"))
        return

    with st.sidebar:
        opts = sidebar_common(labels)

    label = opts["label"]
    level = opts["level"]
    dwelling = opts["dwelling"]

    st.title(t("budget_title"))
    st.caption(t("budget_hint"))

    if level not in ["REGION", "SUBURB", "POSTCODE"]:
        st.info(t("need_level_budget"))
        return

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

    ok, msg = _validate_schema(weekly, monthly)
    if not ok:
        st.error(msg)
        return

    # numeric guards
    weekly = coerce_numeric_cols(
        weekly,
        ["weekly_median_price", "weekly_max_price", "weekly_min_price", "weekly_sales_count",
         "signal_price", "signal_n_sales", "signal_span_days"]
    )
    weekly = filter_price_range(
        weekly,
        ["weekly_median_price", "weekly_max_price", "weekly_min_price", "signal_price"],
        price_min_exclusive=PRICE_MIN_EXCLUSIVE,
        price_max=PRICE_MAX
    )

    monthly = coerce_numeric_cols(
        monthly,
        ["monthly_median_price", "monthly_max_price", "monthly_min_price", "monthly_sales_count"]
    )
    monthly = filter_price_range(
        monthly,
        ["monthly_median_price", "monthly_max_price", "monthly_min_price"],
        price_min_exclusive=PRICE_MIN_EXCLUSIVE,
        price_max=PRICE_MAX
    )

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        budget_min = st.number_input(t("budget_min"), min_value=0, value=1400000, step=50000, key="budget_min")
    with c2:
        budget_max = st.number_input(t("budget_max"), min_value=0, value=2500000, step=50000, key="budget_max")
    with c3:
        topn = st.number_input(t("budget_topn"), min_value=10, max_value=5000, value=200, step=10, key="budget_topn")

    if budget_max < budget_min:
        st.warning(t("budget_invalid"))
        return

    df_budget = build_budget_table(weekly, monthly, dwelling, int(budget_min), int(budget_max), int(topn))
    st.caption(t("budget_table_note"))
    if df_budget.empty:
        st.info(t("no_data"))
    else:
        st.dataframe(df_budget, use_container_width=True, hide_index=True, height=720)


if __name__ == "__main__":
    main()