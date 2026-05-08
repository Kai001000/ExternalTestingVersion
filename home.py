import streamlit as st

from utils.i18n import ensure_lang, t, tr


def _nav_page_defs() -> list[tuple[str, str, bool]]:
    return [
        ("pages/0_External_Home.py", tr("产品首页", "Home"), True),
        ("pages/1_Market_View.py", t("nav_market_view"), False),
        ("pages/3_Buy_Budget.py", t("nav_buy_budget"), False),
        ("pages/4_Rent_Budget.py", t("nav_rent_budget"), False),
    ]


def _build_navigation_pages() -> list[st.Page]:
    return [st.Page(path, title=title, default=default) for path, title, default in _nav_page_defs()]


def main() -> None:
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

