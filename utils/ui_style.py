from html import escape

import streamlit as st


def internal_ui_css() -> str:
    return """
    <style>
    :root {
        --ui-color-primary: #0f6e56;
        --ui-color-primary-soft: #e4f1ed;
        --ui-color-secondary: #1d9e75;
        --ui-color-secondary-soft: #e2f4ee;
        --ui-color-accent-caution: #ba7517;
        --ui-color-accent-caution-soft: #f6ecdb;
        --ui-color-accent-danger: #d85a30;
        --ui-color-accent-danger-soft: #f9ebe6;
        --ui-color-neutral-950: #1a1f2e;
        --ui-color-neutral-900: #22283a;
        --ui-color-neutral-700: #54545f;
        --ui-color-neutral-600: #70707b;
        --ui-color-neutral-500: #888780;
        --ui-color-neutral-400: #b5b3ac;
        --ui-color-border: rgba(26, 31, 46, 0.08);
        --ui-color-border-strong: rgba(26, 31, 46, 0.14);
        --ui-color-surface: #ffffff;
        --ui-color-surface-soft: #ffffff;
        --ui-color-surface-muted: #f1efe8;
        --ui-color-bg: #f7f8fa;
        --ui-color-text: #1a1f2e;
        --ui-color-text-muted: #888780;
        --ui-radius-sm: 12px;
        --ui-radius-md: 18px;
        --ui-radius-lg: 24px;
        --ui-shadow-sm: 0 10px 28px rgba(26, 31, 46, 0.05);
        --ui-shadow-md: 0 18px 40px rgba(26, 31, 46, 0.07);
        --ui-space-xs: 0.35rem;
        --ui-space-sm: 0.65rem;
        --ui-space-md: 1rem;
        --ui-space-lg: 1.4rem;
        --ui-space-xl: 2rem;
    }

    div[data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at top left, rgba(228, 241, 237, 0.85), transparent 26%),
            linear-gradient(180deg, #fbfbfc 0%, var(--ui-color-bg) 38%, #f2f4f6 100%);
    }
    .block-container {
        max-width: 1280px;
        padding-top: 1.6rem;
        padding-bottom: 2.8rem;
    }

    .internal-hero,
    .internal-section,
    .internal-card,
    .internal-panel,
    .internal-filter-panel,
    .internal-insight-card,
    .internal-warning-card,
    .internal-map-panel {
        background: var(--ui-color-surface);
        border: 1px solid var(--ui-color-border);
        border-radius: var(--ui-radius-lg);
        box-shadow: var(--ui-shadow-sm);
    }

    .internal-hero {
        padding: 1.35rem 1.45rem;
        margin-bottom: 1rem;
    }
    .internal-page-title {
        color: var(--ui-color-text);
        font-size: 2.05rem;
        line-height: 1.1;
        font-weight: 800;
        margin: 0;
    }
    .internal-page-subtitle {
        color: var(--ui-color-text-muted);
        font-size: 0.96rem;
        line-height: 1.55;
        margin-top: 0.45rem;
    }
    .internal-section {
        padding: 1.1rem 1.2rem;
        margin-bottom: 1rem;
    }
    .internal-section-title {
        color: var(--ui-color-neutral-900);
        font-size: 1.18rem;
        font-weight: 800;
        margin: 0;
    }
    .internal-section-subtitle {
        color: var(--ui-color-text-muted);
        font-size: 0.9rem;
        line-height: 1.5;
        margin-top: 0.28rem;
    }
    .internal-card {
        padding: 0.95rem 1rem;
    }
    .internal-card-title {
        color: var(--ui-color-text-muted);
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin-bottom: 0.45rem;
    }
    .internal-metric-value {
        color: var(--ui-color-neutral-950);
        font-size: 1.8rem;
        line-height: 1.05;
        font-weight: 800;
        font-variant-numeric: tabular-nums;
    }
    .internal-help-text {
        color: var(--ui-color-text-muted);
        font-size: 0.88rem;
        line-height: 1.5;
    }
    .internal-caption {
        color: var(--ui-color-neutral-500);
        font-size: 0.76rem;
        line-height: 1.45;
    }
    .internal-insight-card {
        padding: 0.95rem 1rem;
        border-color: rgba(15, 110, 86, 0.12);
        background: linear-gradient(180deg, rgba(228, 241, 237, 0.72), rgba(255, 255, 255, 0.96));
    }
    .internal-warning-card {
        padding: 0.95rem 1rem;
        border-color: rgba(186, 117, 23, 0.18);
        border-left: 4px solid var(--ui-color-accent-caution);
        background: linear-gradient(180deg, rgba(246, 236, 219, 0.65), rgba(255, 255, 255, 0.98));
    }
    .internal-filter-panel {
        padding: 1.2rem 1.25rem;
        margin-bottom: 1rem;
    }
    .internal-map-panel {
        padding: 0.9rem 1rem;
    }
    .internal-filter-shell-head {
        margin-bottom: 1rem;
    }
    .internal-budget-hero {
        padding: 1rem 1.05rem;
        border-radius: 20px;
        background: linear-gradient(180deg, rgba(241, 239, 232, 0.7), rgba(255, 255, 255, 0.92));
        border: 1px solid rgba(26, 31, 46, 0.06);
        margin-bottom: 0.9rem;
    }
    .internal-budget-hero-label {
        color: var(--ui-color-text-muted);
        font-size: 0.76rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin-bottom: 0.38rem;
    }
    .internal-budget-hero-value {
        color: var(--ui-color-neutral-950);
        font-size: clamp(2rem, 3vw, 2.75rem);
        line-height: 1.02;
        font-weight: 800;
        letter-spacing: -0.03em;
        font-variant-numeric: tabular-nums;
    }
    .internal-budget-hero-note {
        color: var(--ui-color-text-muted);
        font-size: 0.84rem;
        line-height: 1.45;
        margin-top: 0.4rem;
    }
    .internal-inline-note {
        color: var(--ui-color-text-muted);
        font-size: 0.82rem;
        line-height: 1.45;
        margin: 0.35rem 0 0.2rem 0;
    }
    .internal-badge,
    .internal-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.32rem;
        border-radius: 999px;
        border: 1px solid transparent;
        padding: 0.28rem 0.68rem;
        font-size: 0.78rem;
        font-weight: 700;
        line-height: 1.2;
        white-space: nowrap;
    }
    .internal-badge {
        background: var(--ui-color-primary-soft);
        color: var(--ui-color-primary);
        border-color: rgba(15, 110, 86, 0.12);
    }
    .internal-chip {
        background: rgba(255, 255, 255, 0.98);
        color: var(--ui-color-neutral-700);
        border-color: rgba(26, 31, 46, 0.08);
    }
    .internal-chip-positive {
        background: var(--ui-color-secondary-soft);
        color: var(--ui-color-secondary);
        border-color: rgba(21, 128, 61, 0.10);
    }
    .internal-chip-caution {
        background: var(--ui-color-accent-caution-soft);
        color: var(--ui-color-accent-caution);
        border-color: rgba(217, 119, 6, 0.12);
    }
    .internal-chip-danger {
        background: var(--ui-color-accent-danger-soft);
        color: var(--ui-color-accent-danger);
        border-color: rgba(180, 35, 24, 0.12);
    }
    .internal-divider {
        height: 1px;
        background: linear-gradient(90deg, rgba(15, 23, 42, 0), rgba(15, 23, 42, 0.14), rgba(15, 23, 42, 0));
        margin: 1rem 0;
        border: 0;
    }
    .internal-spacer-sm { margin-top: 0.5rem; }
    .internal-spacer-md { margin-top: 0.9rem; }
    .internal-spacer-lg { margin-top: 1.35rem; }

    div[data-testid="stMetric"],
    div[data-testid="stDataFrame"],
    div[data-testid="stPlotlyChart"],
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 22px;
    }

    div[data-testid="stMetric"] {
        background: var(--ui-color-surface);
        border: 1px solid var(--ui-color-border);
        box-shadow: var(--ui-shadow-sm);
        padding: 0.85rem 0.95rem;
    }
    div[data-testid="stMetricValue"] {
        font-variant-numeric: tabular-nums;
    }

    [data-testid="stForm"] {
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(247, 248, 250, 0.94));
        border: 1px solid var(--ui-color-border);
        border-radius: var(--ui-radius-lg);
        padding: 1rem 1.05rem 0.55rem 1.05rem;
    }

    .stButton > button,
    .stDownloadButton > button,
    .stLinkButton > a {
        border-radius: 999px;
        border: 1px solid rgba(15, 110, 86, 0.14);
        font-weight: 700;
    }

    [data-baseweb="select"] > div,
    [data-baseweb="base-input"] > div,
    .stNumberInput input {
        border-radius: 14px;
        border-color: rgba(15, 23, 42, 0.12);
        background: rgba(255, 255, 255, 0.95);
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #162033 100%);
        border-right: 1px solid rgba(255,255,255,0.08);
    }
    [data-testid="stSidebar"] * {
        color: #f8fafc;
    }
    div[data-testid="stSidebarNav"] ul li a {
        color: rgba(248, 250, 252, 0.92) !important;
        border-radius: 12px;
    }
    div[data-testid="stSidebarNav"] ul li a:hover,
    div[data-testid="stSidebarNav"] ul li a[aria-current="page"] {
        background: rgba(96, 165, 250, 0.16);
        color: #ffffff !important;
        font-weight: 700;
    }
    div[data-testid="stSidebarNav"] ul li a[aria-current="page"] {
        border-left: 3px solid #60a5fa;
    }
    </style>
    """


def inject_internal_ui_style() -> None:
    st.markdown(internal_ui_css(), unsafe_allow_html=True)


def hero_block(*, title: str, subtitle: str = "", badge: str | None = None) -> str:
    badge_html = f"<div class='internal-badge'>{escape(badge)}</div>" if badge else ""
    subtitle_html = f"<div class='internal-page-subtitle'>{escape(subtitle)}</div>" if subtitle else ""
    return (
        "<div class='internal-hero'>"
        f"{badge_html}"
        f"<h1 class='internal-page-title'>{escape(title)}</h1>"
        f"{subtitle_html}"
        "</div>"
    )


def budget_hero_block(*, label: str, value: str, note: str = "") -> str:
    note_html = f"<div class='internal-budget-hero-note'>{escape(note)}</div>" if note else ""
    return (
        "<div class='internal-budget-hero'>"
        f"<div class='internal-budget-hero-label'>{escape(label)}</div>"
        f"<div class='internal-budget-hero-value'>{escape(value)}</div>"
        f"{note_html}"
        "</div>"
    )


def section_header(*, title: str, subtitle: str = "") -> str:
    subtitle_html = f"<div class='internal-section-subtitle'>{escape(subtitle)}</div>" if subtitle else ""
    return (
        "<div class='internal-section'>"
        f"<div class='internal-section-title'>{escape(title)}</div>"
        f"{subtitle_html}"
        "</div>"
    )


def metric_card(*, title: str, value: str, help_text: str = "", tone: str = "neutral") -> str:
    tone_class = {
        "positive": "internal-chip internal-chip-positive",
        "caution": "internal-chip internal-chip-caution",
        "danger": "internal-chip internal-chip-danger",
    }.get(tone, "internal-chip")
    help_html = f"<div class='internal-help-text'>{escape(help_text)}</div>" if help_text else ""
    return (
        "<div class='internal-card'>"
        f"<div class='internal-card-title'>{escape(title)}</div>"
        f"<div class='internal-metric-value'>{escape(value)}</div>"
        f"<div class='{tone_class}' style='margin-top:0.55rem;width:fit-content'>{escape(title)}</div>"
        f"{help_html}"
        "</div>"
    )


def simple_card(*, title: str, body: str, variant: str = "default") -> str:
    class_name = {
        "insight": "internal-insight-card",
        "warning": "internal-warning-card",
        "panel": "internal-panel",
        "filter": "internal-filter-panel",
        "map": "internal-map-panel",
    }.get(variant, "internal-card")
    return (
        f"<div class='{class_name}'>"
        f"<div class='internal-card-title'>{escape(title)}</div>"
        f"<div class='internal-help-text'>{escape(body)}</div>"
        "</div>"
    )


def divider() -> str:
    return "<div class='internal-divider'></div>"
