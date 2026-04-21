from html import escape

import streamlit as st

from utils.i18n import ensure_lang
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
    .public-home-shell {
        max-width: 1120px;
    }
    .public-home-status {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        border-radius: 999px;
        background: rgba(24, 34, 48, 0.92);
        color: #f8fafc;
        padding: 0.4rem 0.78rem;
        font-size: 0.8rem;
        font-weight: 800;
        letter-spacing: 0.02em;
        margin-bottom: 0.95rem;
    }
    .public-home-status-dot {
        width: 0.48rem;
        height: 0.48rem;
        border-radius: 999px;
        background: #e9c46a;
        box-shadow: 0 0 0 0.18rem rgba(233, 196, 106, 0.18);
        flex: 0 0 auto;
    }
    .public-home-hero {
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 28px;
        background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.94));
        padding: 1.42rem 1.45rem 1.28rem 1.45rem;
        margin-bottom: 1rem;
    }
    .public-home-title {
        color: #111827;
        font-size: 2.45rem;
        font-weight: 800;
        line-height: 1.08;
        margin-bottom: 0.62rem;
        max-width: 760px;
    }
    .public-home-note {
        color: #4b5563;
        font-size: 1rem;
        line-height: 1.72;
        max-width: 860px;
        margin: 0;
    }
    .public-home-facts {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.88rem;
        margin: 0 0 1rem 0;
    }
    .public-home-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.88rem;
        margin-top: 0;
    }
    .public-home-card {
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 22px;
        background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.95));
        padding: 0.92rem 1rem 0.88rem 1rem;
        min-height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
    }
    .public-home-card-compact {
        padding-top: 0.82rem;
        padding-bottom: 0.8rem;
    }
    .public-home-card h3 {
        color: #111827;
        font-size: 1rem;
        margin: 0 0 0.28rem 0;
        line-height: 1.3;
    }
    .public-home-card p {
        color: #4b5563;
        font-size: 0.91rem;
        line-height: 1.58;
        margin: 0;
    }
    .public-home-card-eyebrow {
        color: #8c5e3c;
        font-size: 0.74rem;
        font-weight: 800;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        margin-bottom: 0.2rem;
    }
    .public-home-card-value {
        color: #111827;
        font-size: 1.16rem;
        font-weight: 800;
        line-height: 1.2;
        margin-bottom: 0.16rem;
    }
    .public-home-closing {
        margin-top: 1rem;
        border-radius: 20px;
        background: rgba(239, 230, 216, 0.56);
        padding: 0.9rem 0.98rem;
        color: #5b6472;
        font-size: 0.9rem;
        line-height: 1.66;
    }
    @media (max-width: 980px) {
        .public-home-facts,
        .public-home-grid {
            grid-template-columns: 1fr;
        }
        .public-home-title {
            font-size: 2rem;
        }
        .public-home-hero {
            padding: 1.18rem 1.02rem 1.08rem 1.02rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _fact_card(label: str, value: str, note: str) -> str:
    return f"""
    <div class="public-home-card public-home-card-compact">
      <div class="public-home-card-eyebrow">{escape(label)}</div>
      <div class="public-home-card-value">{escape(value)}</div>
      <p>{escape(note)}</p>
    </div>
    """


def _content_card(title: str, body: str) -> str:
    return f"""
    <div class="public-home-card">
      <h3>{escape(title)}</h3>
      <p>{escape(body)}</p>
    </div>
    """


def main() -> None:
    ensure_lang()
    inject_app_theme()

    with st.sidebar:
        sidebar_common(include_dwelling=False)

    status_line = "测试版 · 持续优化中"
    hero_title = "让更多人真正看懂 NSW 楼市"
    hero_note = (
        "很多人并不缺房产信息，真正困难的是把分散的数据、价格变化和区域差异，"
        "转化成可以帮助判断的市场理解。这个产品希望把 NSW 的区域、价格和市场节奏"
        "整理得更直观，让你更容易形成自己的判断。当前版本仍在持续打磨中，"
        "但已经可以帮助你更快看市场；如果你在使用中有任何想法、建议或发现问题，也欢迎联系作者反馈。"
    )

    fact_cards = [
        ("数据更新频率", "每周更新", "保持对当前市场节奏的持续观察。"),
        ("当前阶段", "Beta", "已可使用，也仍在持续优化细节与体验。"),
        ("覆盖范围", "NSW", "聚焦 NSW 市场理解，不在首页展开更细的范围说明。"),
    ]
    secondary_cards = [
        ("你可以用它做什么", "快速查看市场趋势、区域差异、价格带变化，以及买房和租房两个预算视角下的浏览结果。"),
        ("怎么开始最合适", "建议先看 Market View 建立整体感觉，再进入 Buy Budget 或 Rent Budget 做更具体的区域和价格筛选。"),
        ("当前版本的边界", "它更适合帮助你建立对市场的理解和方向感，部分细节能力仍会继续补足和优化。"),
        ("欢迎提出反馈", "如果你觉得哪里不够清楚、功能还不完整，或希望加入新的视角与能力，都欢迎联系作者反馈；这些意见会直接影响下一版的改进方向。"),
    ]
    closing_note = (
        "这是一个仍在演进中的版本。当前结果更适合帮助你建立对 NSW 楼市的理解、比较不同区域和价格带，"
        "而不是替代完整的专业决策流程。如果你有任何建议、想法或使用中的发现，欢迎联系作者交流反馈。"
    )

    homepage_html = f"""
    <div class="public-home-shell">
      <div class="public-home-status"><span class="public-home-status-dot"></span>{escape(status_line)}</div>
      <div class="public-home-hero">
        <div class="public-home-title">{escape(hero_title)}</div>
        <p class="public-home-note">{escape(hero_note)}</p>
      </div>
      <div class="public-home-facts">
        {''.join(_fact_card(*card) for card in fact_cards)}
      </div>
      <div class="public-home-grid">
        {''.join(_content_card(*card) for card in secondary_cards)}
      </div>
      <div class="public-home-closing">{escape(closing_note)}</div>
    </div>
    """
    st.markdown(homepage_html, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
