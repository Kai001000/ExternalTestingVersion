# utils/ui.py
import streamlit as st

from .i18n import get_lang, language_label, language_options, set_lang, t


def inject_app_theme():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"] {
            font-family: "Manrope", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        div[data-testid="stAppViewContainer"] {
            background: #f8f5f1;
        }
        .block-container {
            padding-top: 1.6rem;
            padding-bottom: 2.8rem;
        }
        section[data-testid="stSidebar"] {
            background: #1a1a2e;
            border-right: 1px solid rgba(255,255,255,0.08);
        }
        section[data-testid="stSidebar"] * {
            color: #f7f5f2;
        }
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] .stRadio label,
        section[data-testid="stSidebar"] .stSelectbox label {
            color: #f7f5f2 !important;
        }
        section[data-testid="stSidebar"] [data-baseweb="select"] > div,
        section[data-testid="stSidebar"] [data-baseweb="base-input"] > div,
        section[data-testid="stSidebar"] .stRadio [role="radiogroup"] label,
        section[data-testid="stSidebar"] .stNumberInput input {
            background: rgba(255,255,255,0.08);
            border-color: rgba(255,255,255,0.12);
            color: #f7f5f2;
        }
        section[data-testid="stSidebar"] .stRadio [role="radiogroup"] label[data-checked="true"] {
            background: rgba(233, 196, 106, 0.22);
            border-radius: 999px;
        }
        div[data-testid="stSidebarNav"] ul li a {
            color: #ece8e1 !important;
            border-radius: 12px;
        }
        div[data-testid="stSidebarNav"] ul li a:hover,
        div[data-testid="stSidebarNav"] ul li a[aria-current="page"] {
            background: rgba(233, 196, 106, 0.20);
            color: #ffffff !important;
            font-weight: 700;
        }
        div[data-testid="stSidebarNav"] ul li a[aria-current="page"] {
            border-left: 3px solid #e9c46a;
        }
        div[data-testid="stMetric"],
        div[data-testid="stDataFrame"],
        div[data-testid="stPlotlyChart"],
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 22px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def external_language_switch(*, key: str = "global_lang_switch", label_visibility: str = "collapsed") -> str:
    lang_options = language_options()
    current_lang = get_lang()
    selected_lang = st.radio(
        t("lang"),
        options=lang_options,
        index=lang_options.index(current_lang),
        format_func=language_label,
        horizontal=True,
        key=key,
        label_visibility=label_visibility,
    )
    if selected_lang != current_lang:
        set_lang(selected_lang)
        st.rerun()
    return selected_lang


def render_external_page_header(*, badge: str, title: str, note: str) -> None:
    st.markdown(
        f"<div class='budget-kicker'>{badge}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(f"<div class='budget-title'>{title}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='budget-note'>{note}</div>", unsafe_allow_html=True)


def render_external_map_legend(
    *,
    coverage_label: str,
    low_label: str,
    high_label: str,
    selected_label: str,
    other_label: str,
) -> None:
    st.markdown(
        f"""
        <div style="margin-top:0.7rem;border:1px solid rgba(148,163,184,0.18);border-radius:16px;background:linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,250,252,0.95));padding:0.8rem 0.9rem;">
          <div style="font-size:0.74rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#8c5e3c;margin-bottom:0.45rem;">{coverage_label}</div>
          <div style="display:flex;align-items:center;gap:0.55rem;margin-bottom:0.75rem;">
            <span style="font-size:0.74rem;color:#6b7280;">{low_label}</span>
            <div style="flex:1;height:10px;border-radius:999px;background:linear-gradient(90deg,#f2efe8 0%,#e5ddb7 25%,#c6d68c 55%,#7fbf7b 78%,#2c7f62 100%);"></div>
            <span style="font-size:0.74rem;color:#6b7280;">{high_label}</span>
          </div>
          <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0.5rem;">
            <div style="display:flex;align-items:center;gap:0.45rem;font-size:0.8rem;color:#374151;">
              <span style="display:inline-block;width:12px;height:12px;border-radius:999px;background:#d97706;border:2px solid rgba(255,255,255,0.92);box-shadow:0 0 0 1px rgba(15,23,42,0.08);"></span>
              <span>{selected_label}</span>
            </div>
            <div style="display:flex;align-items:center;gap:0.45rem;font-size:0.8rem;color:#374151;">
              <span style="display:inline-block;width:10px;height:10px;border-radius:999px;background:#0d5ea6;opacity:0.9;"></span>
              <span>{other_label}</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_common(*, include_dwelling: bool = True) -> dict:
    st.markdown(f"**{t('lang')}**")
    external_language_switch(key="global_lang_switch")

    if "dwelling_group" not in st.session_state:
        st.session_state["dwelling_group"] = "HOUSE"

    dwelling = st.session_state["dwelling_group"]
    if include_dwelling:
        st.markdown("---")
        st.markdown(f"**{t('sidebar_dwelling_title')}**")
        dwelling = st.radio(
            t("dwelling_group"),
            options=["HOUSE", "UNIT"],
            format_func=lambda value: t("dwelling_house") if value == "HOUSE" else t("dwelling_unit"),
            horizontal=True,
            key="dwelling_group",
        )
    return {"dwelling": dwelling}
