import streamlit as st

st.set_page_config(
    page_title="NSW 房产数据仪表盘",
    page_icon="🏡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .main-title {
        font-size: 3rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 1rem;
        text-align: center;
    }
    .sub-title {
        font-size: 1.5rem;
        color: #4B5563;
        margin-bottom: 2rem;
        text-align: center;
    }
    .feature-card {
        background-color: #F3F4F6;
        border-radius: 10px;
        padding: 1.5rem;
        margin: 1rem 0;
        border-left: 5px solid #3B82F6;
    }
    .feature-title {
        font-size: 1.3rem;
        font-weight: 600;
        color: #1E40AF;
    }
    .feature-desc {
        font-size: 1rem;
        color: #374151;
    }
    .nav-hint {
        background-color: #EFF6FF;
        border-radius: 8px;
        padding: 1rem;
        margin-top: 2rem;
        font-size: 1.1rem;
        border: 1px solid #BFDBFE;
    }
    .emoji-icon {
        font-size: 1.5rem;
        vertical-align: middle;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🏡 NSW 房产数据仪表盘</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">探索悉尼及新南威尔士州房产价格趋势</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-title">📈 价格趋势分析</div>
        <div class="feature-desc">查看 NSW、大悉尼地区、城区、邮编级别的房产价格走势，支持 House/Unit 切换，季度概览一目了然。</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="feature-card">
        <div class="feature-title">🏆 稳定排名</div>
        <div class="feature-desc">基于滚动13周中位价，展示 Greater Sydney 内城区 MoM/QoQ 涨幅榜和跌幅榜，数据独立缓存，切换筛选不影响排名。</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-title">📊 季度概览表</div>
        <div class="feature-desc">提供最新季度中位价、成交量、环比变化（QoQ/MoM）以及稳定口径的滞后变化，帮助判断市场趋势。</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="feature-card">
        <div class="feature-title">⚡ 高性能优化</div>
        <div class="feature-desc">排名表计算结果缓存，切换时间范围或区域选择时不会重新计算，页面响应更快。</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("""
<div class="nav-hint">
    <span class="emoji-icon">👉</span> 
    <strong>开始使用：</strong> 点击左侧边栏的 <code>Market View</code> 进入分析页面。
    <br>
    <small>（如果侧边栏没有出现，请点击左上角 <code>≡</code> 展开）</small>
</div>
""", unsafe_allow_html=True)

st.markdown("---")
st.markdown(
    "<p style='text-align: center; color: #6B7280;'>© 2025 NSW Property Dashboard · 数据仅供参考</p>",
    unsafe_allow_html=True
)