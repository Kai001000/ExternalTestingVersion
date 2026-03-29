import threading

import streamlit as st

from pages._ranking_cache import warm_ranking_cache
from utils.i18n import ensure_lang, t


threading.Thread(target=warm_ranking_cache, daemon=True).start()

ensure_lang()

st.set_page_config(
    page_title=t("app_title"),
    layout="wide",
    initial_sidebar_state="expanded",
)

pages = [
    st.Page("pages/1_Market_View.py", title=t("nav_market_view"), default=True),
    st.Page("pages/2_Ranking.py", title=t("nav_ranking")),
    st.Page("pages/3_Buy_Budget.py", title=t("nav_buy_budget")),
    st.Page("pages/4_Rent_Budget.py", title=t("nav_rent_budget")),
]

pg = st.navigation(pages, position="sidebar")
pg.run()
