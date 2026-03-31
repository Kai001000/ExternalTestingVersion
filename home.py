import threading

import streamlit as st

from pages._ranking_cache import warm_ranking_cache
from utils.config import IS_EXTERNAL_MODE
from utils.i18n import ensure_lang, t


def _nav_page_defs() -> list[tuple[str, str, bool]]:
    pages = [
        ("pages/1_Market_View.py", t("nav_market_view"), True),
        ("pages/3_Buy_Budget.py", t("nav_buy_budget"), False),
        ("pages/4_Rent_Budget.py", t("nav_rent_budget"), False),
    ]
    if not IS_EXTERNAL_MODE:
        pages.insert(1, ("pages/2_Ranking.py", t("nav_ranking"), False))
    return pages


def _build_navigation_pages() -> list[st.Page]:
    return [st.Page(path, title=title, default=default) for path, title, default in _nav_page_defs()]


def main() -> None:
    if not IS_EXTERNAL_MODE:
        threading.Thread(target=warm_ranking_cache, daemon=True).start()

    ensure_lang()

    st.set_page_config(
        page_title=t("app_title"),
        layout="wide",
        initial_sidebar_state="expanded",
    )

    pg = st.navigation(_build_navigation_pages(), position="sidebar")
    pg.run()


if __name__ == "__main__":
    main()
