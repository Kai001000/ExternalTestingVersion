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
        max-width: 980px;
    }
    .public-home-status {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        background: rgba(13, 148, 136, 0.12);
        color: #0f766e;
        padding: 0.28rem 0.68rem;
        font-size: 11px;
        font-weight: 600;
        line-height: 1;
        margin-bottom: 0.85rem;
    }
    .public-home-title {
        color: #111827;
        font-size: 26px;
        font-weight: 600;
        line-height: 1.24;
        margin: 0 0 0.62rem 0;
    }
    .public-home-title span {
        color: #0f766e;
    }
    .public-home-subtitle {
        color: #5f6b7a;
        font-size: 13.5px;
        line-height: 1.72;
        max-width: 520px;
        margin: 0 0 1rem 0;
    }
    .public-home-subtitle strong {
        color: #1f2937;
        font-weight: 600;
    }
    .public-home-source-strip {
        max-width: 520px;
        display: grid;
        grid-template-columns: 24px 1fr;
        gap: 0.7rem;
        align-items: start;
        background: #ffffff;
        border: 1px solid rgba(15, 118, 110, 0.16);
        border-left: 3px solid #0f766e;
        border-radius: 8px;
        padding: 0.76rem 0.92rem;
        margin: 0 0 1.35rem 0;
    }
    .public-home-source-icon {
        color: #0f766e;
        font-size: 17px;
        line-height: 1.2;
        padding-top: 0.05rem;
    }
    .public-home-source-text {
        color: #667085;
        font-size: 12.5px;
        line-height: 1.58;
    }
    .public-home-source-text strong {
        color: #1f2937;
        font-weight: 600;
    }
    .public-home-section-label {
        color: #6b7280;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin: 0.15rem 0 0.5rem 0;
    }
    .public-home-nav-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 10px;
        margin-bottom: 1rem;
    }
    .public-home-card-link {
        display: block;
        height: 100%;
        text-decoration: none !important;
        color: inherit !important;
        background: #ffffff;
        border: 1px solid rgba(148, 163, 184, 0.28);
        border-radius: 8px;
        padding: 14px 16px;
        transition: border-color 140ms ease, box-shadow 140ms ease, transform 140ms ease;
    }
    .public-home-card-link:hover {
        border-color: #0f766e;
        box-shadow: 0 8px 22px rgba(15, 118, 110, 0.08);
        transform: translateY(-1px);
    }
    .public-home-card-icon {
        color: #0f766e;
        font-size: 18px;
        line-height: 1;
        margin-bottom: 0.58rem;
    }
    .public-home-card-title {
        color: #111827;
        font-size: 13px;
        font-weight: 600;
        margin: 0 0 0.34rem 0;
    }
    .public-home-card-body {
        color: #667085;
        font-size: 12px;
        line-height: 1.58;
        margin: 0;
    }
    .public-home-info-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
        margin-bottom: 1rem;
    }
    .public-home-info-card {
        background: #ffffff;
        border: 1px solid rgba(148, 163, 184, 0.24);
        border-radius: 8px;
        padding: 14px 16px;
    }
    .public-home-info-title {
        color: #1f2937;
        font-size: 12.5px;
        font-weight: 500;
        margin: 0 0 0.42rem 0;
    }
    .public-home-info-body {
        color: #667085;
        font-size: 12px;
        line-height: 1.6;
        margin: 0;
    }
    .public-home-builder-note {
        background: #f8faf9;
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 8px;
        padding: 14px 18px;
        color: #667085;
        font-size: 12px;
        line-height: 1.7;
    }
    .public-home-builder-note strong {
        color: #1f2937;
        font-weight: 500;
    }
    @media (max-width: 860px) {
        .public-home-nav-grid,
        .public-home-info-grid {
            grid-template-columns: 1fr;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def main() -> None:
    ensure_lang()
    inject_app_theme()

    with st.sidebar:
        sidebar_common(include_dwelling=False)

    st.markdown(
        """
        <div class="public-home-shell">
          <div class="public-home-status">Beta · 持续优化中</div>
          <h1 class="public-home-title">看懂 NSW 楼市，<span>从数据源头开始</span></h1>
          <p class="public-home-subtitle">
            大多数平台只展示挂牌数据。这里收录的是所有<strong>政府在册的正常成交记录</strong>，包含线下交易（off-market）——让你看到的是真实成交市场，而不是挂牌市场的切片。
          </p>
          <div class="public-home-source-strip">
            <div class="public-home-source-icon">▦</div>
            <div class="public-home-source-text">
              <strong>数据来源：NSW Valuation（政府产权记录）</strong>　涵盖所有正常成交产权，含 off-market 交易，每周更新
            </div>
          </div>
          <div class="public-home-section-label">从这里开始</div>
          <div class="public-home-nav-grid">
            <a class="public-home-card-link" href="/1_Market_View" target="_self">
              <div class="public-home-card-icon">↗</div>
              <div class="public-home-card-title">市场概览</div>
              <p class="public-home-card-body">区域价格趋势、成交量变化、各区对比</p>
            </a>
            <a class="public-home-card-link" href="/3_Buy_Budget" target="_self">
              <div class="public-home-card-icon">⌂</div>
              <div class="public-home-card-title">买房预算</div>
              <p class="public-home-card-body">设定预算，筛选目标区域和房型</p>
            </a>
            <a class="public-home-card-link" href="/4_Rent_Budget" target="_self">
              <div class="public-home-card-icon">⚿</div>
              <div class="public-home-card-title">租房预算</div>
              <p class="public-home-card-body">租金分布、区域租金走势对比</p>
            </a>
          </div>
          <div class="public-home-info-grid">
            <div class="public-home-info-card">
              <div class="public-home-info-title">这个工具能帮你做什么</div>
              <p class="public-home-info-body">快速建立对 NSW 市场的整体感——哪些区在涨、哪些区有性价比、你的预算对应什么现实选择。适合买家、租户和关注市场走向的人。</p>
            </div>
            <div class="public-home-info-card">
              <div class="public-home-info-title">它不能替代什么</div>
              <p class="public-home-info-body">个人财务规划、法律尽调、单盘评估。这里是市场视角的辅助判断工具，具体决策建议结合专业顾问一起用。</p>
            </div>
          </div>
          <div class="public-home-builder-note">
            <strong>一点说明：</strong>　做这个工具的起点很简单——市面上的数据太碎，挂牌平台只看得到卖家愿意公开的部分。我希望从政府完整的产权记录出发，把真实成交市场还原出来。现在还在打磨，有任何想法欢迎直接反馈。
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
