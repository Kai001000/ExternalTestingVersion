import streamlit as st
from .i18n import t, I18N


def sidebar_common() -> dict:
    st.title(t("sidebar_title"))

    st.radio(
        t("lang"),
        options=["zh", "en"],
        format_func=lambda x: I18N[x]["lang_zh"] if x == "zh" else I18N[x]["lang_en"],
        horizontal=True,
        key="lang",
    )

    st.markdown("---")

    level = st.selectbox(
        t("data_level"),
        options=["NSW", "REGION", "AREA"],
        format_func=lambda x: (
            t("level_nsw") if x == "NSW"
            else (t("level_region") if x == "REGION" else t("level_area"))
        ),
        key="data_level"
    )

    dwelling = st.radio(
        t("dwelling_group"),
        options=["HOUSE", "UNIT"],
        horizontal=True,
        key="dwelling_group"
    )

    return {
        "level": level,
        "dwelling": dwelling,
    }