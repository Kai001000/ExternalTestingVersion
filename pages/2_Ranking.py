from html import escape

import streamlit as st

from utils.i18n import ensure_lang, tr
from utils.ui import inject_app_theme, sidebar_common


st.markdown(
    """
    <style>
    [data-testid="stHeader"] {
        height: 0rem;
        min-height: 0rem;
        padding: 0;
    }
    [data-testid="stToolbar"] {
        display: none;
    }
    section[data-testid="stMain"] > div:first-child {
        padding-top: 1.4rem;
    }
    .ranking-retired {
        max-width: 920px;
    }
    .ranking-retired h1 {
        color: #111827;
        font-size: 2rem;
        margin-bottom: 0.45rem;
    }
    .ranking-retired p {
        color: #4b5563;
        font-size: 0.98rem;
        line-height: 1.65;
        margin-bottom: 0.9rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def main() -> None:
    ensure_lang()
    inject_app_theme()

    with st.sidebar:
        sidebar_common()

    st.markdown("<div class='ranking-retired'>", unsafe_allow_html=True)
    st.markdown(
        f"<h1>{escape(tr('Ranking 已退出当前产品主路径', 'Ranking Has Been Retired From The Active Product Flow'))}</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<p>{escape(tr('旧的内部 Ranking 行为不再作为默认产品路径或当前真相来源。当前版本以 Market View、Buy Budget 和 Rent Budget 为主线。', 'The legacy internal Ranking workflow is no longer part of the default product path or the current source of truth. The active product flow now centers on Market View, Buy Budget, and Rent Budget.'))}</p>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<p>{escape(tr('如果后续需要重新引入排名能力，应基于当前基线产品重新定义，而不是恢复旧的内部专用逻辑。', 'If ranking is reintroduced later, it should be redefined on top of the current baseline product rather than restoring the old internal-only logic.'))}</p>",
        unsafe_allow_html=True,
    )
    st.info(tr("请使用左侧导航进入当前产品页面。", "Use the left navigation to continue through the active product pages."))
    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
