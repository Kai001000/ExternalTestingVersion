import json
import importlib.util
import math
import os
import re
import textwrap
from contextlib import nullcontext
from html import escape
from io import BytesIO
from pathlib import Path
from urllib.parse import quote_plus

import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from matplotlib import font_manager, rcParams
from matplotlib.backends.backend_pdf import PdfPages
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from utils.config import IS_EXTERNAL_DEPLOYMENT, IS_PUBLIC_MODE
from utils.data import (
    add_underlying_trend,
    apply_external_rent_listing_display_filter,
    apply_external_sale_listing_display_filter,
    build_suburb_centroid_lookup,
    compute_commute_listing_frame,
    compute_commute_suburb_frame,
    format_price,
    get_domain_listing_source_status,
    load_daily_rolling,
    load_domain_rent_listings,
    load_domain_sale_listings,
    load_filtered_fact_sales,
    order_external_sale_listing_display,
    resolve_commute_origin,
)
from utils.i18n import ensure_lang, get_lang, t, tr
from utils.map_view import NSW_MAP_BOUNDS, clamp_to_nsw_map_view, resolve_budget_map_view
from utils.perf import PagePerf, render_internal_timing_summary
from utils.tables import apply_right_edge_stability_rule, fmt_date, fmt_int, fmt_pct
from utils.ui import inject_app_theme, render_external_page_header, sidebar_common
from utils.ui_style import budget_hero_block, chip_row, hero_block, section_note, simple_card


SUBURB_JOIN_ALIASES = {
    "CESSNOCK WEST": "CESSNOCK",
    "PATONGA BEACH": "PATONGA",
}
IGNORABLE_SUBURB_KEYS = {"NORFOLK ISLAND"}
LOCALITY_VARIANT_KEYS = {"BALMORAL VILLAGE", "DARLING HARBOUR", "WALSH BAY", "YELLOW ROCK RIDGE"}
BUDGET_STEP = 50_000
EXTERNAL_MAP_PANEL_HEIGHT = 760
MAP_HEIGHT = 712
EXTERNAL_PANEL_BODY_HEIGHT = EXTERNAL_MAP_PANEL_HEIGHT
EXTERNAL_PAGE_SIZE = 4
EXTERNAL_MAX_PAGES = 5
EXTERNAL_MAX_LISTINGS = 150
EXTERNAL_MAX_SUBURBS = 60
EXTERNAL_MAX_MARKERS = 150
EXTERNAL_RANKING_PAGE_SIZE = 8
EXTERNAL_STREET_VIEW_SIZE = "640x360"
EXTERNAL_SAME_SUBURB_LIMIT = 6
EXTERNAL_SAME_SUBURB_PAGE_SIZE = 3
SALE_REPORT_STABLE_RATIO = 0.55
SALE_REPORT_MIN_MEDIAN_SALES = 5
SALE_REPORT_LONG_TREND_MIN_MEDIAN_SALES = 20
SALE_REPORT_COMPARABLE_LIMIT = 8
SALE_REPORT_PRICE_BANDS = [
    (0, 750_000, "<750k"),
    (750_000, 1_200_000, "750k-1.2M"),
    (1_200_000, 2_000_000, "1.2M-2M"),
    (2_000_000, 3_000_000, "2M-3M"),
    (3_000_000, float("inf"), ">3M"),
]
BUY_SORT_SPECS: dict[str, tuple[str, bool]] = {
    "price_asc": ("price_mid", True),
    "price_desc": ("price_mid", False),
    "newest": ("listing_date", False),
    "bedrooms_desc": ("bedrooms", False),
    "suburb_asc": ("suburb", True),
}

CORE_LISTING_BADGE = "Core listing"
EXTENDED_LISTING_BADGE = "Additional market record"
EXTENDED_LISTING_CAPTION = "Additional records are drawn from publicly available market records."
EXTENDED_LAYER_ROOT = Path(__file__).resolve().parents[2] / "BeautifulDataSource" / "data" / "extended" / "onthehouse_validated"
EXTENDED_SOURCE_FILTER_OPTIONS = ["Show all", "Show listing data only", "Show additional records only"]

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
        padding-top: 1.3rem;
    }
    .budget-kicker {
        color: #8c5e3c;
        font-size: 0.8rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 0.2rem;
    }
    .budget-title {
        font-size: 1.95rem;
        font-weight: 800;
        color: #111827;
        margin-bottom: 0.3rem;
    }
    .budget-note {
        color: #6b7280;
        font-size: 0.94rem;
        margin-bottom: 0.8rem;
    }
    .budget-budget-pill {
        display: inline-block;
        border-radius: 999px;
        background: #182230;
        color: #f8f5f1;
        padding: 0.42rem 0.9rem;
        font-size: 0.96rem;
        font-weight: 800;
        margin-bottom: 0.8rem;
    }
    .budget-chip {
        display: inline-block;
        border-radius: 999px;
        background: #efe6d8;
        color: #6f4e37;
        padding: 0.22rem 0.65rem;
        font-size: 0.78rem;
        font-weight: 700;
        margin-right: 0.35rem;
        margin-bottom: 0.35rem;
    }
    .budget-suburb-row {
        padding: 0.25rem 0 0.35rem 0;
        border-bottom: 1px solid rgba(148, 163, 184, 0.18);
    }
    .budget-suburb-meta {
        color: #6b7280;
        font-size: 0.82rem;
    }
    .budget-shortlist-status {
        color: #6b7280;
        font-size: 0.88rem;
    }
    .budget-list-row {
        border: 1px solid rgba(148, 163, 184, 0.22);
        border-radius: 16px;
        padding: 0.85rem 0.95rem;
        margin-bottom: 0.75rem;
        background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.92));
    }
    .budget-list-address {
        font-size: 1rem;
        font-weight: 700;
        color: #111827;
        line-height: 1.3;
        margin-bottom: 0.18rem;
    }
    .budget-list-meta {
        color: #6b7280;
        font-size: 0.82rem;
        line-height: 1.4;
    }
    .budget-list-price {
        font-size: 1.05rem;
        font-weight: 800;
        color: #0f172a;
        text-align: right;
        white-space: nowrap;
    }
    .budget-list-subprice {
        color: #6b7280;
        font-size: 0.78rem;
        text-align: right;
    }
    .budget-panel-summary {
        border: 1px solid rgba(148, 163, 184, 0.20);
        border-radius: 16px;
        background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.94));
        padding: 0.9rem 1rem;
        margin-bottom: 0.85rem;
    }
    .budget-panel-eyebrow {
        color: #8c5e3c;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 0.2rem;
    }
    .budget-panel-title {
        color: #111827;
        font-size: 1.02rem;
        font-weight: 800;
        margin-bottom: 0.22rem;
        line-height: 1.3;
    }
    .budget-panel-subtitle {
        color: #6b7280;
        font-size: 0.82rem;
        line-height: 1.4;
    }
    .budget-panel-badge {
        display: inline-block;
        border-radius: 999px;
        background: #182230;
        color: #f8fafc;
        padding: 0.16rem 0.52rem;
        font-size: 0.72rem;
        font-weight: 700;
        margin-left: 0.35rem;
    }
    .budget-card {
        border: 1px solid rgba(148, 163, 184, 0.22);
        border-radius: 18px;
        background: linear-gradient(180deg, rgba(255,255,255,0.99), rgba(248,250,252,0.95));
        padding: 0.9rem 0.95rem;
        margin-bottom: 0.8rem;
    }
    .budget-card-price {
        color: #0f172a;
        font-size: 1.08rem;
        font-weight: 800;
        margin-bottom: 0.2rem;
    }
    .budget-card-address {
        color: #111827;
        font-size: 0.96rem;
        font-weight: 700;
        line-height: 1.35;
        margin-bottom: 0.2rem;
    }
    .budget-card-meta {
        color: #6b7280;
        font-size: 0.81rem;
        line-height: 1.45;
    }
    .budget-fact-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.55rem;
        margin: 0.85rem 0 0.65rem 0;
    }
    .budget-fact {
        border-radius: 12px;
        background: rgba(248, 250, 252, 0.96);
        border: 1px solid rgba(148, 163, 184, 0.18);
        padding: 0.55rem 0.65rem;
    }
    .budget-fact-label {
        color: #6b7280;
        font-size: 0.72rem;
        margin-bottom: 0.14rem;
    }
    .budget-fact-value {
        color: #111827;
        font-size: 0.84rem;
        font-weight: 700;
        line-height: 1.35;
    }
    .budget-panel-footer {
        border-top: 1px solid rgba(148, 163, 184, 0.18);
        margin-top: 0.65rem;
        padding-top: 0.7rem;
    }
    .budget-mini-card {
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 14px;
        background: rgba(255,255,255,0.96);
        padding: 0.7rem 0.78rem;
        margin-bottom: 0.6rem;
    }
    .budget-mini-price {
        color: #0f172a;
        font-size: 0.92rem;
        font-weight: 800;
        margin-bottom: 0.12rem;
    }
    .budget-mini-address {
        color: #111827;
        font-size: 0.82rem;
        font-weight: 700;
        line-height: 1.35;
        margin-bottom: 0.12rem;
    }
    .budget-mini-meta {
        color: #6b7280;
        font-size: 0.76rem;
        line-height: 1.35;
    }
    .budget-table-head {
        font-size: 0.76rem;
        font-weight: 800;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #6b7280;
        padding-bottom: 0.35rem;
        border-bottom: 1px solid rgba(148, 163, 184, 0.24);
        margin-bottom: 0.3rem;
    }
    .budget-table-row {
        padding: 0.28rem 0;
        border-bottom: 1px solid rgba(148, 163, 184, 0.14);
        min-height: 2.45rem;
        display: flex;
        align-items: center;
    }
    .budget-table-cell {
        font-size: 0.88rem;
        color: #1f2937;
        line-height: 1.25;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .budget-table-price {
        font-size: 0.92rem;
        font-weight: 800;
        color: #0f172a;
        white-space: nowrap;
    }
    .budget-table-address a {
        color: #0f172a;
        text-decoration: none;
        font-weight: 700;
    }
    .budget-table-address a:hover {
        text-decoration: underline;
    }
    .budget-table-muted {
        color: #6b7280;
        font-size: 0.8rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    @media (max-width: 900px) {
        div[data-testid="column"] {
            min-width: 100% !important;
            flex: 1 1 100% !important;
        }
        .stButton > button,
        .stLinkButton > a {
            min-height: 2.75rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _money(value: float | int | None) -> str:
    return format_price(value)


def _count_label(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return _report_na()
    if float(value).is_integer():
        return str(int(value))
    return f"{float(value):.1f}"


def _feature_triplet(row: pd.Series) -> str:
    return f"{_count_label(row.get('bedrooms'))} / {_count_label(row.get('bathrooms'))} / {_count_label(row.get('parking'))}"


def _is_extended_listing(row: pd.Series | dict[str, object]) -> bool:
    value = row.get("listing_layer") if isinstance(row, dict) else row.get("listing_layer")
    return str(value or "").strip().lower() == "extended"


def _source_badge_for_row(row: pd.Series | dict[str, object]) -> str:
    value = row.get("source_badge") if isinstance(row, dict) else row.get("source_badge")
    text = str(value or "").strip()
    if text:
        return text
    return EXTENDED_LISTING_BADGE if _is_extended_listing(row) else CORE_LISTING_BADGE


def _with_core_listing_badge(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    result = df.copy()
    if "source_badge" not in result.columns:
        result["source_badge"] = CORE_LISTING_BADGE
    else:
        result["source_badge"] = result["source_badge"].fillna(CORE_LISTING_BADGE).replace("", CORE_LISTING_BADGE)
    if "listing_layer" not in result.columns:
        result["listing_layer"] = "core"
    else:
        result["listing_layer"] = result["listing_layer"].fillna("core").replace("", "core")
    if "source_name" not in result.columns:
        result["source_name"] = "domain"
    else:
        result["source_name"] = result["source_name"].fillna("domain").replace("", "domain")
    if "public_export_enabled" not in result.columns:
        result["public_export_enabled"] = True
    return result


def _latest_extended_listing_path() -> Path | None:
    if not EXTENDED_LAYER_ROOT.exists():
        return None
    candidates = sorted(
        EXTENDED_LAYER_ROOT.glob("*/onthehouse_validated_listings.parquet"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _parse_extended_price_bounds(price_raw: object) -> tuple[float | None, float | None, str, bool]:
    text = str(price_raw or "").strip()
    if not text:
        return None, None, "Price on request", False
    lowered = text.lower()
    if "auction" in lowered:
        return None, None, text, False
    amounts: list[float] = []
    for match in re.findall(r"\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)(\s*[kKmM])?", text):
        number_text, suffix = match
        try:
            amount = float(number_text.replace(",", ""))
        except ValueError:
            continue
        suffix = suffix.strip().lower()
        if suffix == "k":
            amount *= 1_000
        elif suffix == "m":
            amount *= 1_000_000
        if amount >= 10_000:
            amounts.append(amount)
    if not amounts:
        return None, None, text, False
    price_min = min(amounts)
    price_max = max(amounts)
    return price_min, price_max, text, True


def _load_validated_extended_listings_for_browser() -> pd.DataFrame:
    path = _latest_extended_listing_path()
    if path is None:
        print("[Buy Budget] Extended listings loaded: 0")
        return pd.DataFrame()
    try:
        raw = pd.read_parquet(path)
    except Exception as exc:
        print(f"[Buy Budget] Extended listings load failed: {exc}")
        return pd.DataFrame()
    if raw.empty:
        print("[Buy Budget] Extended listings loaded: 0")
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for _, item in raw.copy().iterrows():
        listing_type = str(item.get("listing_type") or "").strip().lower()
        if listing_type and listing_type != "sale":
            continue
        price_min, price_max, price_display, has_price = _parse_extended_price_bounds(item.get("price_raw"))
        price_mid = None if price_min is None or price_max is None else (price_min + price_max) / 2
        source_record_id = str(item.get("source_record_id") or item.get("listing_id") or "").strip()
        listing_id = str(item.get("listing_id") or f"oth_{source_record_id}").strip()
        rows.append(
            {
                "listing_id": listing_id,
                "address": item.get("address"),
                "suburb": item.get("suburb"),
                "postcode": str(item.get("postcode") or "").strip(),
                "listing_type": "sale",
                "price_raw": item.get("price_raw"),
                "price_display": price_display,
                "price_mid": price_mid,
                "price_filter_min": price_min,
                "price_filter_max": price_max,
                "has_price": bool(has_price),
                "bedrooms": pd.to_numeric(item.get("bedrooms"), errors="coerce"),
                "bathrooms": pd.to_numeric(item.get("bathrooms"), errors="coerce"),
                "parking": pd.to_numeric(item.get("parking"), errors="coerce"),
                "property_group": "extended",
                "property_group_label": "Extended",
                "property_subtype": "validated listing",
                "listing_date": pd.to_datetime(item.get("signal_last_seen_at"), errors="coerce"),
                "source_url": item.get("source_url"),
                "url": item.get("source_url"),
                "agency_name": pd.NA,
                "land_size": pd.NA,
                "main_image": pd.NA,
                "latitude": pd.NA,
                "longitude": pd.NA,
                "source_name": "onthehouse",
                "source_record_id": source_record_id,
                "source_badge": EXTENDED_LISTING_BADGE,
                "listing_layer": "extended",
                "public_export_enabled": False,
            }
        )
    result = pd.DataFrame(rows)
    print(f"[Buy Budget] Extended listings loaded: {len(result)}")
    return result


def _filter_extended_listings_for_browser(
    extended: pd.DataFrame,
    *,
    budget_min: int,
    budget_max: int,
    min_budget: int,
    max_budget: int,
    selected_suburbs: list[str] | None,
    selected_postcodes: list[str] | None,
    min_bedrooms: int,
    min_bathrooms: int,
    min_parking: int,
    exact_bedrooms: bool,
    exact_bathrooms: bool,
    exact_parking: bool,
    allowed_suburbs: list[str] | None,
) -> pd.DataFrame:
    if extended.empty:
        return extended.copy()
    filtered, _ = _apply_budget_filters(
        extended,
        budget_min=budget_min,
        budget_max=budget_max,
        min_budget=min_budget,
        max_budget=max_budget,
        selected_suburbs=selected_suburbs,
        selected_postcodes=selected_postcodes,
        min_bedrooms=min_bedrooms,
        min_bathrooms=min_bathrooms,
        min_parking=min_parking,
        exact_bedrooms=exact_bedrooms,
        exact_bathrooms=exact_bathrooms,
        exact_parking=exact_parking,
        allowed_listing_ids=None,
        allowed_suburbs=allowed_suburbs,
        skip_filters={"property_group", "property_subtype"},
    )
    return filtered


def _filter_browser_listing_source(display: pd.DataFrame, mode: str) -> pd.DataFrame:
    if display.empty or mode == "Show all":
        return display.copy()
    is_extended = display.get("listing_layer", pd.Series(index=display.index, dtype=object)).astype(str).str.lower() == "extended"
    if mode == "Show additional records only":
        return display.loc[is_extended].copy()
    if mode == "Show listing data only":
        return display.loc[~is_extended].copy()
    return display.copy()


def _land_size_label(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return _report_na()
    return f"{int(round(float(value))):,} {tr('平方米', 'sqm')}"


def _compact_price(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return _report_na()
    amount = float(value)
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.2f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.0f}K"
    return format_price(amount)


def _sale_report_now_label() -> str:
    return pd.Timestamp.now(tz="Australia/Sydney").strftime("%Y-%m-%d %H:%M")


def _report_na() -> str:
    return tr("暂无", "N/A")


def _report_text(value: object) -> str:
    if value is None or pd.isna(value):
        return _report_na()
    text = str(value).strip()
    return text if text else _report_na()


def _report_money(value: object) -> str:
    amount = pd.to_numeric(value, errors="coerce")
    if pd.isna(amount):
        return _report_na()
    return _money(float(amount))


def _report_pct(value: object) -> str:
    amount = pd.to_numeric(value, errors="coerce")
    if pd.isna(amount):
        return _report_na()
    return fmt_pct(float(amount))


def _report_date(value: object) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return _report_na()
    return fmt_date(ts)


def _report_numeric(value: object) -> float | None:
    amount = pd.to_numeric(value, errors="coerce")
    if pd.isna(amount):
        return None
    return float(amount)


def _listing_numeric_price(row: pd.Series) -> float | None:
    price_mid = _report_numeric(row.get("price_mid"))
    if price_mid is not None:
        return price_mid
    price_min = _report_numeric(row.get("price_filter_min"))
    price_max = _report_numeric(row.get("price_filter_max"))
    if price_min is not None and price_max is not None:
        return (price_min + price_max) / 2.0
    return None


def _sale_report_dwelling_group(row: pd.Series) -> str | None:
    group = str(row.get("property_group") or "").strip().lower()
    subtype = str(row.get("property_subtype") or "").strip().lower()
    if group == "house" or subtype in {"house", "semi-detached", "duplex", "villa", "terrace"}:
        return "HOUSE"
    if group in {"apartment"} or subtype in {"apartment", "unit", "flat", "studio", "penthouse", "block of units"}:
        return "UNIT"
    if group == "townhouse" or subtype == "townhouse":
        return "HOUSE"
    return None


def _sale_report_same_type_scope(listings: pd.DataFrame, row: pd.Series) -> tuple[pd.DataFrame, str]:
    if listings.empty:
        return listings.copy(), tr(
            "可比挂牌中位价（有精确 subtype 时优先，否则回退到更宽泛的大类）",
            "Comparable listing median (exact subtype when available, otherwise broader property group)",
        )

    suburb = str(row.get("suburb") or "").strip()
    suburb_scope = listings.loc[listings["suburb"].astype(str) == suburb].copy() if suburb else listings.copy()
    subtype = str(row.get("property_subtype") or "").strip().lower()
    group = str(row.get("property_group") or "").strip().lower()

    if subtype and subtype != "unknown":
        subtype_scope = suburb_scope.loc[suburb_scope["property_subtype"].astype(str).str.lower() == subtype].copy()
        if not subtype_scope.empty:
            return subtype_scope, tr(
                "可比挂牌中位价（精确 subtype）",
                "Comparable listing median (exact subtype)",
            )
    if group:
        group_scope = suburb_scope.loc[suburb_scope["property_group"].astype(str).str.lower() == group].copy()
        if not group_scope.empty:
            return group_scope, tr(
                "可比挂牌中位价（更宽泛大类）",
                "Comparable listing median (broader property group)",
            )
    return suburb_scope, tr(
        "可比挂牌中位价（suburb 范围）",
        "Comparable listing median (suburb scope)",
    )


def _report_property_type(row: pd.Series) -> str:
    group_label = _report_text(row.get("property_group_label"))
    subtype = str(row.get("property_subtype") or "").strip().lower()
    subtype_label = "N/A" if not subtype or subtype == "unknown" else _title_case_subtype(subtype)
    if group_label == "N/A" and subtype_label == "N/A":
        return "N/A"
    if subtype_label == "N/A":
        return group_label
    if group_label == "N/A":
        return subtype_label
    return f"{group_label} / {subtype_label}"


def _sale_report_verdict(delta: float | None, *, lower_label: str, middle_label: str, upper_label: str) -> str:
    if delta is None or pd.isna(delta):
        return "N/A"
    if float(delta) <= -0.05:
        return lower_label
    if float(delta) < 0.05:
        return middle_label
    return upper_label


def _sale_report_trend_verdict(stable_yoy: float | None) -> str:
    if stable_yoy is None or pd.isna(stable_yoy):
        return "N/A"
    if float(stable_yoy) > 0.03:
        return tr("上涨", "Rising")
    if float(stable_yoy) < -0.03:
        return tr("走弱", "Softening")
    return tr("平稳", "Flat")


def _sale_report_summary_sentence(verdicts: dict[str, str]) -> str:
    sold = verdicts.get("sold_market", "N/A")
    listings = verdicts.get("current_listings", "N/A")
    trend = verdicts.get("local_trend", "N/A")
    if sold != "N/A" and listings != "N/A" and trend != "N/A":
        return tr(
            f"该房源相对近期成交水平为“{sold}”，相对当前同类挂牌为“{listings}”，本地成交趋势为“{trend}”。",
            f"This property is {sold.lower()} and {listings.lower()}, while the local sold trend is {trend.lower()}.",
        )
    if sold != "N/A" and listings != "N/A":
        return tr(
            f"该房源相对近期成交水平为“{sold}”，相对当前同类挂牌为“{listings}”。",
            f"This property is {sold.lower()} and {listings.lower()}.",
        )
    if sold != "N/A":
        return tr(
            f"该房源相对近期成交水平为“{sold}”，其余市场对比暂时不足。",
            f"This property is {sold.lower()}, while the remaining market context is currently limited.",
        )
    return tr(
        "当前报告仅能提供部分市场背景信息，请结合原始挂牌详情继续判断。",
        "This report currently provides partial market context only; use it alongside the listing details.",
    )


def _sale_report_price_positioning_verdict(delta: float | None) -> str:
    return _sale_report_verdict(
        delta,
        lower_label=tr("低于 suburb 挂牌中位价", "Below suburb listing median"),
        middle_label=tr("接近 suburb 挂牌中位价", "Around suburb listing median"),
        upper_label=tr("高于 suburb 挂牌中位价", "Above suburb listing median"),
    )


def _sale_report_liquidity_verdict(sales_28d: float | None) -> str:
    sales = _report_numeric(sales_28d)
    if sales is None:
        return "N/A"
    if sales >= 20:
        return tr("流动性活跃", "Liquidity active")
    if sales >= 8:
        return tr("流动性中等", "Liquidity moderate")
    return tr("流动性偏薄", "Liquidity thin")


def _sale_report_rent_activity_verdict(active_count: int | None) -> str:
    if active_count is None:
        return "N/A"
    if int(active_count) >= 25:
        return tr("租赁活动活跃", "Rental activity active")
    if int(active_count) >= 10:
        return tr("租赁活动中等", "Rental activity moderate")
    return tr("租赁活动偏薄", "Rental activity thin")


def _sale_report_band_for_price(price: float | None) -> str | None:
    if price is None or pd.isna(price):
        return None
    value = float(price)
    for lower, upper, label in SALE_REPORT_PRICE_BANDS:
        if lower <= value < upper:
            return label
    return None


def _sale_report_percentile_label(percentile: float | None) -> str:
    if percentile is None or pd.isna(percentile):
        return tr("可比挂牌不足", "Insufficient comparable listings")
    if percentile <= 0.33:
        return tr("处于可比挂牌较低价位", "In the lower range of comparable listings")
    if percentile < 0.67:
        return tr("可比挂牌中段价位", "In the middle range of comparable listings")
    return tr("处于可比挂牌较高价位", "In the upper range of comparable listings")


def _sale_report_estimated_gross_yield(median_rent: float | None, price: float | None) -> float | None:
    rent_value = _report_numeric(median_rent)
    price_value = _report_numeric(price)
    if rent_value in {None, 0} or price_value in {None, 0}:
        return None
    return (float(rent_value) * 52.0) / float(price_value)


def _report_group_label(value: object) -> str:
    text = str(value or "").strip().lower()
    mapping = {
        "house": tr("独立屋", "House"),
        "apartment": tr("公寓", "Apartment"),
        "unit": tr("公寓", "Apartment"),
        "townhouse": tr("联排/城市屋", "Townhouse"),
        "land": tr("土地", "Land"),
        "other": tr("其他", "Other"),
        "unknown": _report_na(),
    }
    return mapping.get(text, _report_text(value))


def _report_subtype_label(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text or text == "unknown":
        return _report_na()
    mapping = {
        "house": tr("独立屋", "House"),
        "semi-detached": tr("半独立屋", "Semi-detached"),
        "duplex": tr("双拼", "Duplex"),
        "villa": tr("别墅", "Villa"),
        "terrace": tr("排屋", "Terrace"),
        "apartment": tr("公寓", "Apartment"),
        "unit": tr("公寓", "Apartment"),
        "flat": tr("公寓", "Flat"),
        "studio": tr("单间", "Studio"),
        "penthouse": tr("顶层公寓", "Penthouse"),
        "block of units": tr("整栋公寓", "Block of Units"),
        "townhouse": tr("联排/城市屋", "Townhouse"),
        "land": tr("土地", "Land"),
    }
    return mapping.get(text, text.title())


def _report_listing_price_display(row: pd.Series, numeric_price: float | None) -> str:
    raw = str(row.get("price_display") or "").strip()
    raw = re.sub(r"(?<=\d),\s+(?=\d)", ",", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    if raw:
        if numeric_price is not None:
            numeric_label = _report_money(numeric_price)
            raw_digits = re.sub(r"[^\d]", "", raw)
            numeric_digits = re.sub(r"[^\d]", "", numeric_label)
            if raw_digits and raw_digits == numeric_digits:
                return numeric_label
        return raw
    return _report_money(numeric_price)


def _report_listing_price_line(row: pd.Series, numeric_price: float | None) -> str:
    display_label = _report_listing_price_display(row, numeric_price)
    numeric_label = _report_money(numeric_price)
    if display_label == numeric_label:
        return numeric_label
    if numeric_label == _report_na():
        return display_label
    return f"{display_label} ({numeric_label})"


def _sale_report_same_type_scope(listings: pd.DataFrame, row: pd.Series) -> tuple[pd.DataFrame, str]:
    if listings.empty:
        return listings.copy(), tr(
            "可比挂牌中位价（优先精确细分类，否则回退到更宽泛的大类）",
            "Comparable listing median (exact subtype when available, otherwise broader property group)",
        )
    suburb = str(row.get("suburb") or "").strip()
    suburb_scope = listings.loc[listings["suburb"].astype(str) == suburb].copy() if suburb else listings.copy()
    subtype = str(row.get("property_subtype") or "").strip().lower()
    group = str(row.get("property_group") or "").strip().lower()
    if subtype and subtype != "unknown":
        subtype_scope = suburb_scope.loc[suburb_scope["property_subtype"].astype(str).str.lower() == subtype].copy()
        if not subtype_scope.empty:
            return subtype_scope, tr("可比挂牌中位价（精确细分类）", "Comparable listing median (exact subtype)")
    if group:
        group_scope = suburb_scope.loc[suburb_scope["property_group"].astype(str).str.lower() == group].copy()
        if not group_scope.empty:
            return group_scope, tr("可比挂牌中位价（更宽泛大类）", "Comparable listing median (broader property group)")
    return suburb_scope, tr("可比挂牌中位价（当前区域范围）", "Comparable listing median (suburb scope)")


def _report_property_type(row: pd.Series) -> str:
    group_label = _report_group_label(row.get("property_group") or row.get("property_group_label"))
    subtype_label = _report_subtype_label(row.get("property_subtype"))
    if group_label == _report_na() and subtype_label == _report_na():
        return _report_na()
    if subtype_label == _report_na():
        return group_label
    if group_label == _report_na():
        return subtype_label
    if group_label.strip().lower() == subtype_label.strip().lower():
        return group_label
    return f"{group_label} / {subtype_label}"


def _sale_report_verdict(delta: float | None, *, lower_label: str, middle_label: str, upper_label: str) -> str:
    if delta is None or pd.isna(delta):
        return _report_na()
    if float(delta) <= -0.05:
        return lower_label
    if float(delta) < 0.05:
        return middle_label
    return upper_label


def _sale_report_trend_verdict(stable_yoy: float | None) -> str:
    if stable_yoy is None or pd.isna(stable_yoy):
        return _report_na()
    if float(stable_yoy) > 0.03:
        return tr("上涨", "Rising")
    if float(stable_yoy) < -0.03:
        return tr("走弱", "Softening")
    return tr("平稳", "Flat")


def _sale_report_summary_sentence(verdicts: dict[str, str]) -> str:
    na_label = _report_na()
    sold = verdicts.get("sold_market", na_label)
    listings = verdicts.get("current_listings", na_label)
    trend = verdicts.get("local_trend", na_label)
    if sold != na_label and listings != na_label and trend != na_label:
        return tr(
            f"该房源相对近期成交水平为“{sold}”，相对当前同类挂牌为“{listings}”，本地成交趋势为“{trend}”。",
            f"This property is {sold.lower()} and {listings.lower()}, while the local sold trend is {trend.lower()}.",
        )
    if sold != na_label and listings != na_label:
        return tr(
            f"该房源相对近期成交水平为“{sold}”，相对当前同类挂牌为“{listings}”。",
            f"This property is {sold.lower()} and {listings.lower()}.",
        )
    if sold != na_label:
        return tr(
            f"该房源相对近期成交水平为“{sold}”，其余市场对比暂时不足。",
            f"This property is {sold.lower()}, while the remaining market context is currently limited.",
        )
    return tr(
        "当前报告仅能提供部分市场背景信息，请结合原始挂牌详情继续判断。",
        "This report currently provides partial market context only; use it alongside the listing details.",
    )


def _sale_report_price_positioning_verdict(delta: float | None) -> str:
    return _sale_report_verdict(
        delta,
        lower_label=tr("低于区域挂牌中位价", "Below suburb listing median"),
        middle_label=tr("接近区域挂牌中位价", "Around suburb listing median"),
        upper_label=tr("高于区域挂牌中位价", "Above suburb listing median"),
    )


def _sale_report_liquidity_verdict(sales_28d: float | None) -> str:
    sales = _report_numeric(sales_28d)
    if sales is None:
        return _report_na()
    if sales >= 20:
        return tr("流动性活跃", "Liquidity active")
    if sales >= 8:
        return tr("流动性中等", "Liquidity moderate")
    return tr("流动性偏薄", "Liquidity thin")


def _sale_report_rent_activity_verdict(active_count: int | None) -> str:
    if active_count is None:
        return _report_na()
    if int(active_count) >= 25:
        return tr("租赁活跃", "Rental activity active")
    if int(active_count) >= 10:
        return tr("租赁中等", "Rental activity moderate")
    return tr("租赁偏淡", "Rental activity thin")


def _sale_report_percentile_label(percentile: float | None) -> str:
    if percentile is None or pd.isna(percentile):
        return tr("可比挂牌不足", "Insufficient comparable listings")
    if percentile <= 0.33:
        return tr("处于可比挂牌较低价位", "In the lower range of comparable listings")
    if percentile < 0.67:
        return tr("处于可比挂牌中段价位", "In the middle range of comparable listings")
    return tr("处于可比挂牌较高价位", "In the upper range of comparable listings")


@st.cache_resource(show_spinner=False)
def _load_market_view_module_for_report():
    module_path = Path(__file__).with_name("1_Market_View.py")
    spec = importlib.util.spec_from_file_location("market_view_report_module", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load Market View module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@st.cache_data(ttl=3600, show_spinner=False)
def _build_sale_report_sold_market_context(suburb: str, dwelling_group: str | None, postcode: str | None = None) -> dict[str, object]:
    empty = {
        "metrics": {
            "latest_median": None,
            "latest_point": None,
            "stable_yoy": None,
            "sales": None,
        },
        "plot_df": pd.DataFrame(),
        "anchor_points": pd.DataFrame(),
        "dwelling_group": dwelling_group,
        "context_level": None,
        "context_region": None,
    }
    suburb_text = str(suburb or "").strip()
    postcode_text = str(postcode or "").strip()
    if (not suburb_text and not postcode_text) or not dwelling_group:
        return empty

    daily_pd = pd.DataFrame()
    context_level = None
    context_region = None
    for level, region_text in (("SUBURB", suburb_text), ("POSTCODE", postcode_text)):
        if not region_text:
            continue
        daily = load_daily_rolling(level)
        if daily.is_empty():
            continue
        frame = daily.to_pandas()
        frame["region"] = frame["region"].astype(str).str.strip()
        frame["dwelling_group"] = frame["dwelling_group"].astype(str).str.strip().str.upper()
        frame = frame.loc[
            (frame["region"] == region_text)
            & (frame["dwelling_group"] == str(dwelling_group).strip().upper())
        ].copy()
        if not frame.empty:
            daily_pd = frame
            context_level = level
            context_region = region_text
            break
    if daily_pd.empty:
        return empty

    daily_pd["date"] = pd.to_datetime(daily_pd["date"], errors="coerce").dt.normalize()
    daily_pd["rolling_median"] = pd.to_numeric(daily_pd["rolling_median"], errors="coerce")
    daily_pd["sales_28d"] = pd.to_numeric(daily_pd["sales_28d"], errors="coerce")
    daily_pd = daily_pd.loc[daily_pd["date"].notna() & daily_pd["rolling_median"].notna()].copy()
    if daily_pd.empty:
        return empty

    one_year_ago = daily_pd["date"].max() - pd.DateOffset(years=1)
    base_sales = (
        daily_pd.loc[daily_pd["date"] >= one_year_ago]
        .groupby("region")["sales_28d"]
        .median()
        .to_dict()
    )

    plot_df = daily_pd[["date", "region", "rolling_median", "sales_28d"]].rename(
        columns={"date": "event_time", "rolling_median": "value"}
    )
    plot_df["base_sales"] = plot_df["region"].map(base_sales).fillna(0)
    plot_df["raw_stable"] = plot_df["sales_28d"] >= plot_df["base_sales"] * SALE_REPORT_STABLE_RATIO
    plot_df["stable"] = False
    plot_df = apply_right_edge_stability_rule(
        plot_df,
        group_cols=["region"],
        date_col="event_time",
        raw_stable_col="raw_stable",
        out_col="stable",
    )

    plot_df["underlying_trend"] = pd.Series([float("nan")] * len(plot_df), index=plot_df.index, dtype="float64")
    plot_df["underlying_trend_tail"] = False
    median_sales = pd.to_numeric(plot_df["sales_28d"], errors="coerce").median()
    if pd.notna(median_sales) and float(median_sales) >= SALE_REPORT_MIN_MEDIAN_SALES:
        plot_df = add_underlying_trend(
            plot_df,
            group_cols=["region"],
            date_col="event_time",
            value_col="value",
            out_col="underlying_trend",
            tail_col="underlying_trend_tail",
            window_days=91,
        )

    stable_rows = plot_df.loc[plot_df["stable"].fillna(False)].copy()
    if stable_rows.empty:
        return {
            "metrics": {
                "latest_median": None,
                "latest_point": None,
                "stable_yoy": None,
                "sales": None,
            },
            "plot_df": plot_df.copy(),
            "anchor_points": pd.DataFrame(),
            "dwelling_group": dwelling_group,
        }

    visible_col = "underlying_trend" if plot_df["underlying_trend"].notna().any() else "value"
    anchor_rows = stable_rows.loc[stable_rows[visible_col].notna()].copy()
    if anchor_rows.empty:
        anchor_rows = stable_rows.loc[stable_rows["value"].notna()].copy()
        visible_col = "value"
    anchor_rows = anchor_rows.sort_values("event_time")
    latest_anchor = anchor_rows.iloc[-1]

    target_date = pd.to_datetime(latest_anchor["event_time"], errors="coerce").normalize() - pd.Timedelta(days=365)
    prior_rows = anchor_rows.copy()
    prior_rows["_abs_day_gap"] = (prior_rows["event_time"] - target_date).abs().dt.days
    prior_rows = prior_rows.sort_values(["_abs_day_gap", "event_time"])
    prior_anchor = prior_rows.iloc[0] if not prior_rows.empty else None
    prior_value = pd.to_numeric(prior_anchor[visible_col], errors="coerce") if prior_anchor is not None else float("nan")
    latest_value = pd.to_numeric(latest_anchor[visible_col], errors="coerce")
    stable_yoy = None
    if pd.notna(latest_value) and pd.notna(prior_value) and float(prior_value) != 0:
        stable_yoy = float(latest_value) / float(prior_value) - 1.0

    anchor_points = pd.DataFrame(
        [{"x": latest_anchor["event_time"], "y": latest_value, "label": context_region or suburb_text or postcode_text}]
    ) if pd.notna(latest_value) else pd.DataFrame()
    return {
        "metrics": {
            "latest_median": float(latest_value) if pd.notna(latest_value) else None,
            "latest_point": latest_anchor["event_time"],
            "stable_yoy": stable_yoy,
            "sales": _report_numeric(latest_anchor.get("sales_28d")),
        },
        "plot_df": plot_df.copy(),
        "anchor_points": anchor_points,
        "dwelling_group": dwelling_group,
        "context_level": context_level,
        "context_region": context_region,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def _build_sale_report_price_band_summary(
    dwelling_group: str | None,
    *,
    context_level: str | None,
    context_region: str | None,
) -> pd.DataFrame:
    empty = pd.DataFrame(columns=["price_band", "latest_value", "stable_yoy", "anchor_date", "sales_28d", "series_name"])
    if not dwelling_group or not context_level or not context_region:
        return empty
    market_view = _load_market_view_module_for_report()
    normalized_level = str(context_level).strip().upper()
    normalized_region = str(context_region).strip()
    if not normalized_region:
        return empty
    if normalized_level in {"SUBURB", "POSTCODE"}:
        band_level = "AREA"
    else:
        band_level = normalized_level
    band_data = market_view.load_price_band_data(
        band_level,
        (normalized_region,),
        str(dwelling_group).strip().upper(),
    )
    if band_data.is_empty():
        return empty

    rows: list[dict[str, object]] = []
    for _, _, band_label in SALE_REPORT_PRICE_BANDS:
        visible_filtered = band_data.filter(band_data["price_band"] == band_label)
        full_history = band_data.filter(band_data["price_band"] == band_label)
        _, band_summary = market_view._calc_band_summary(visible_filtered, full_history, market_view.STABLE_RATIO)
        if band_summary.empty:
            rows.append({"price_band": band_label, "latest_value": None, "stable_yoy": None, "anchor_date": None, "sales_28d": None, "series_name": None})
            continue
        band_row = band_summary.iloc[0]
        sales_28d = None
        if pd.notna(band_row.get("anchor_date")):
            anchor_rows = visible_filtered.filter(visible_filtered["date"] == pd.to_datetime(band_row["anchor_date"]))
            if not anchor_rows.is_empty():
                sales_28d = _report_numeric(anchor_rows.to_pandas()["sales_28d"].iloc[0])
        rows.append(
            {
                "price_band": band_label,
                "latest_value": _report_numeric(band_row.get("median")),
                "stable_yoy": _report_numeric(band_row.get("yoy")),
                "anchor_date": band_row.get("anchor_date"),
                "sales_28d": sales_28d,
                "series_name": "rolling_median",
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=900, show_spinner=False)
def _build_sale_report_rent_context(suburb: str) -> dict[str, object]:
    empty = {
        "median_weekly_rent": None,
        "active_rental_count": 0,
        "priced_rental_count": 0,
        "activity_label": "N/A",
    }
    suburb_text = str(suburb or "").strip()
    if not suburb_text:
        return empty

    rent_df = load_domain_rent_listings()
    if rent_df.empty:
        return empty
    rent_df = apply_external_rent_listing_display_filter(rent_df)
    scope = rent_df.loc[rent_df["suburb"].astype(str).str.strip() == suburb_text].copy()
    if scope.empty:
        return empty
    priced_scope = scope.loc[scope["has_rent"].fillna(False)].copy()
    active_rental_count = int(len(scope))
    priced_rental_count = int(len(priced_scope))
    return {
        "median_weekly_rent": _report_numeric(priced_scope["rent_mid"].median()) if not priced_scope.empty else None,
        "active_rental_count": active_rental_count,
        "priced_rental_count": priced_rental_count,
        "activity_label": _sale_report_rent_activity_verdict(active_rental_count),
    }


def _build_sale_report_comparables(row: pd.Series, market_listings: pd.DataFrame) -> dict[str, object]:
    empty = {
        "scope_label": tr("当前筛选下无可比挂牌", "No comparable listings in the active filtered sale universe"),
        "table": pd.DataFrame(),
        "percentile": None,
        "range_label": tr("可比挂牌不足", "Insufficient comparable listings"),
        "selected_rank_text": "N/A",
    }
    if market_listings is None or market_listings.empty:
        return empty

    suburb = str(row.get("suburb") or "").strip()
    scope = market_listings.copy()
    scope["suburb"] = scope["suburb"].astype(str).str.strip()
    scope = scope.loc[scope["suburb"] == suburb].copy()
    if scope.empty:
        return empty

    scope["price_mid"] = pd.to_numeric(scope["price_mid"], errors="coerce")
    scope = scope.loc[scope["price_mid"].notna()].copy()
    if scope.empty:
        return empty

    subtype = str(row.get("property_subtype") or "").strip().lower()
    group = str(row.get("property_group") or "").strip().lower()
    selected_beds = _report_numeric(row.get("bedrooms"))

    candidates: list[tuple[pd.DataFrame, str]] = []
    if subtype:
        exact_subtype = scope.loc[scope["property_subtype"].astype(str).str.lower() == subtype].copy()
        if not exact_subtype.empty:
            if selected_beds is not None:
                subtype_beds = exact_subtype.loc[pd.to_numeric(exact_subtype["bedrooms"], errors="coerce") == selected_beds].copy()
                if len(subtype_beds) >= 3:
                    candidates.append((subtype_beds, tr("同 suburb / 同 subtype / 同户型", "Same suburb / same subtype / same beds")))
            candidates.append((exact_subtype, tr("同 suburb / 同 subtype", "Same suburb / same subtype")))
    if group:
        same_group = scope.loc[scope["property_group"].astype(str).str.lower() == group].copy()
        if not same_group.empty:
            if selected_beds is not None:
                group_beds = same_group.loc[pd.to_numeric(same_group["bedrooms"], errors="coerce") == selected_beds].copy()
                if len(group_beds) >= 3:
                    candidates.append((group_beds, tr("同 suburb / 同大类 / 同户型", "Same suburb / same property group / same beds")))
            candidates.append((same_group, tr("同 suburb / 同大类", "Same suburb / same property group")))
    if selected_beds is not None:
        same_beds = scope.loc[pd.to_numeric(scope["bedrooms"], errors="coerce") == selected_beds].copy()
        if not same_beds.empty:
            candidates.append((same_beds, tr("同 suburb / 同户型", "Same suburb / same beds")))
    candidates.append((scope, tr("同 suburb 全部挂牌", "All active listings in the same suburb")))

    chosen_scope, scope_label = candidates[-1]
    for candidate_df, candidate_label in candidates:
        if len(candidate_df) >= 3:
            chosen_scope = candidate_df.copy()
            scope_label = candidate_label
            break

    chosen_scope = chosen_scope.copy()
    selected_id = str(row.get("listing_id") or "").strip()
    chosen_scope["listing_id"] = chosen_scope["listing_id"].astype(str)
    chosen_scope["is_selected"] = chosen_scope["listing_id"] == selected_id
    if not chosen_scope["is_selected"].any():
        selected_price = _listing_numeric_price(row)
        if selected_price is not None:
            selected_row = row.to_frame().T.copy()
            selected_row["price_mid"] = selected_price
            selected_row["listing_id"] = selected_id
            selected_row["is_selected"] = True
            chosen_scope = pd.concat([chosen_scope, selected_row], ignore_index=True, sort=False)

    chosen_scope = chosen_scope.drop_duplicates(subset=["listing_id"], keep="first")
    chosen_scope["price_mid"] = pd.to_numeric(chosen_scope["price_mid"], errors="coerce")
    chosen_scope = chosen_scope.loc[chosen_scope["price_mid"].notna()].sort_values(["price_mid", "address"], ascending=[True, True], na_position="last")
    if chosen_scope.empty:
        return empty

    selected_price = _listing_numeric_price(row)
    percentile = None
    selected_rank_text = "N/A"
    if selected_price is not None and len(chosen_scope) >= 2:
        rank = int((chosen_scope["price_mid"] <= float(selected_price)).sum())
        percentile = rank / float(len(chosen_scope))
        selected_rank_text = f"{rank}/{len(chosen_scope)}"

    table = chosen_scope.head(SALE_REPORT_COMPARABLE_LIMIT).copy()
    table["note"] = table["is_selected"].map(lambda value: tr("本房源", "Selected") if bool(value) else "")
    table["type_label"] = table.apply(_report_property_type, axis=1)
    table["beds_label"] = table["bedrooms"].map(_count_label)
    table["price_label"] = table["price_mid"].map(_report_money)
    return {
        "scope_label": scope_label,
        "table": table,
        "percentile": percentile,
        "range_label": _sale_report_percentile_label(percentile),
        "selected_rank_text": selected_rank_text,
    }


def _build_sale_report_context(row: pd.Series, market_listings: pd.DataFrame) -> dict[str, object]:
    suburb = str(row.get("suburb") or "").strip()
    numeric_price = _listing_numeric_price(row)
    dwelling_group = _sale_report_dwelling_group(row)
    numeric_scope = market_listings.copy() if market_listings is not None else pd.DataFrame()
    if not numeric_scope.empty:
        numeric_scope["price_mid"] = pd.to_numeric(numeric_scope["price_mid"], errors="coerce")
    suburb_scope = (
        numeric_scope.loc[numeric_scope["suburb"].astype(str) == suburb].copy()
        if suburb and not numeric_scope.empty and "suburb" in numeric_scope.columns
        else pd.DataFrame()
    )
    suburb_priced = suburb_scope.loc[suburb_scope["price_mid"].notna()].copy() if not suburb_scope.empty else pd.DataFrame()
    same_type_scope, same_type_label = _sale_report_same_type_scope(numeric_scope, row)
    same_type_priced = same_type_scope.loc[pd.to_numeric(same_type_scope["price_mid"], errors="coerce").notna()].copy() if not same_type_scope.empty else pd.DataFrame()

    suburb_listing_median = _report_numeric(suburb_priced["price_mid"].median()) if not suburb_priced.empty else None
    same_type_listing_median = _report_numeric(same_type_priced["price_mid"].median()) if not same_type_priced.empty else None
    delta_vs_suburb = (
        (numeric_price / suburb_listing_median) - 1.0
        if numeric_price is not None and suburb_listing_median not in {None, 0}
        else None
    )
    delta_vs_same_type = (
        (numeric_price / same_type_listing_median) - 1.0
        if numeric_price is not None and same_type_listing_median not in {None, 0}
        else None
    )

    sold_context = _build_sale_report_sold_market_context(suburb, dwelling_group, row.get("postcode"))
    sold_metrics = sold_context["metrics"]
    sold_median = sold_metrics.get("latest_median")
    delta_vs_sold = (
        (numeric_price / sold_median) - 1.0
        if numeric_price is not None and sold_median not in {None, 0}
        else None
    )

    verdicts = {
        "sold_market": _sale_report_verdict(
            delta_vs_sold,
            lower_label=tr("低于成交市场", "Below sold market"),
            middle_label=tr("接近成交市场", "Near sold market"),
            upper_label=tr("高于成交市场", "Above sold market"),
        ),
        "current_listings": _sale_report_verdict(
            delta_vs_same_type,
            lower_label=tr("低于当前挂牌", "Below current listings"),
            middle_label=tr("接近当前挂牌", "In line with current listings"),
            upper_label=tr("高于当前挂牌", "Above current listings"),
        ),
        "local_trend": _sale_report_trend_verdict(sold_metrics.get("stable_yoy")),
    }
    price_positioning = _sale_report_price_positioning_verdict(delta_vs_suburb)
    liquidity_label = _sale_report_liquidity_verdict(sold_metrics.get("sales"))
    price_band_label = _sale_report_band_for_price(numeric_price)
    price_band_summary = _build_sale_report_price_band_summary(
        dwelling_group,
        context_level=sold_context.get("context_level"),
        context_region=sold_context.get("context_region"),
    )
    price_band_row = (
        price_band_summary.loc[price_band_summary["price_band"] == price_band_label].iloc[0].to_dict()
        if price_band_label and not price_band_summary.empty and (price_band_summary["price_band"] == price_band_label).any()
        else {}
    )
    rent_context = _build_sale_report_rent_context(suburb)
    comparables = _build_sale_report_comparables(row, market_listings)
    estimated_gross_yield = _sale_report_estimated_gross_yield(rent_context.get("median_weekly_rent"), numeric_price)
    suburb_price_range_low = _report_numeric(suburb_priced["price_mid"].min()) if not suburb_priced.empty else None
    suburb_price_range_high = _report_numeric(suburb_priced["price_mid"].max()) if not suburb_priced.empty else None

    return {
        "generated_at": _sale_report_now_label(),
        "numeric_price": numeric_price,
        "suburb_listing_median": suburb_listing_median,
        "same_type_listing_median": same_type_listing_median,
        "same_type_label": same_type_label,
        "delta_vs_suburb": delta_vs_suburb,
        "delta_vs_same_type": delta_vs_same_type,
        "delta_vs_sold": delta_vs_sold,
        "sold_context": sold_context,
        "verdicts": verdicts,
        "summary_sentence": _sale_report_summary_sentence(verdicts),
        "price_positioning": price_positioning,
        "liquidity_label": liquidity_label,
        "price_band": {
            "label": price_band_label,
            "latest_value": _report_numeric(price_band_row.get("latest_value")),
            "stable_yoy": _report_numeric(price_band_row.get("stable_yoy")),
            "anchor_date": price_band_row.get("anchor_date"),
            "sales_28d": _report_numeric(price_band_row.get("sales_28d")),
            "trend_label": _sale_report_trend_verdict(_report_numeric(price_band_row.get("stable_yoy"))),
        },
        "rent_context": rent_context,
        "estimated_gross_yield": estimated_gross_yield,
        "comparables": comparables,
        "suburb_price_range_low": suburb_price_range_low,
        "suburb_price_range_high": suburb_price_range_high,
    }


@st.cache_data(ttl=900, show_spinner=False)
def _build_sale_report_rent_context(suburb: str) -> dict[str, object]:
    empty = {
        "median_weekly_rent": None,
        "active_rental_count": 0,
        "priced_rental_count": 0,
        "activity_label": _report_na(),
    }
    suburb_text = str(suburb or "").strip()
    if not suburb_text:
        return empty
    rent_df = load_domain_rent_listings()
    if rent_df.empty:
        return empty
    rent_df = apply_external_rent_listing_display_filter(rent_df)
    scope = rent_df.loc[rent_df["suburb"].astype(str).str.strip() == suburb_text].copy()
    if scope.empty:
        return empty
    priced_scope = scope.loc[scope["has_rent"].fillna(False)].copy()
    active_rental_count = int(len(scope))
    priced_rental_count = int(len(priced_scope))
    return {
        "median_weekly_rent": _report_numeric(priced_scope["rent_mid"].median()) if not priced_scope.empty else None,
        "active_rental_count": active_rental_count,
        "priced_rental_count": priced_rental_count,
        "activity_label": _sale_report_rent_activity_verdict(active_rental_count),
    }


def _build_sale_report_comparables(row: pd.Series, market_listings: pd.DataFrame) -> dict[str, object]:
    empty = {
        "scope_label": tr("当前筛选范围内无可比挂牌", "No comparable listings in the active filtered sale universe"),
        "table": pd.DataFrame(),
        "percentile": None,
        "range_label": tr("可比挂牌不足", "Insufficient comparable listings"),
        "selected_rank_text": _report_na(),
    }
    if market_listings is None or market_listings.empty:
        return empty
    suburb = str(row.get("suburb") or "").strip()
    scope = market_listings.copy()
    scope["suburb"] = scope["suburb"].astype(str).str.strip()
    scope = scope.loc[scope["suburb"] == suburb].copy()
    if scope.empty:
        return empty
    scope["price_mid"] = pd.to_numeric(scope["price_mid"], errors="coerce")
    scope = scope.loc[scope["price_mid"].notna()].copy()
    if scope.empty:
        return empty

    subtype = str(row.get("property_subtype") or "").strip().lower()
    group = str(row.get("property_group") or "").strip().lower()
    selected_beds = _report_numeric(row.get("bedrooms"))

    candidates: list[tuple[pd.DataFrame, str]] = []
    if subtype:
        exact_subtype = scope.loc[scope["property_subtype"].astype(str).str.lower() == subtype].copy()
        if not exact_subtype.empty:
            if selected_beds is not None:
                subtype_beds = exact_subtype.loc[pd.to_numeric(exact_subtype["bedrooms"], errors="coerce") == selected_beds].copy()
                if len(subtype_beds) >= 3:
                    candidates.append((subtype_beds, tr("同一区域 / 同细分类 / 同卧室数", "Same suburb / same subtype / same beds")))
            candidates.append((exact_subtype, tr("同一区域 / 同细分类", "Same suburb / same subtype")))
    if group:
        same_group = scope.loc[scope["property_group"].astype(str).str.lower() == group].copy()
        if not same_group.empty:
            if selected_beds is not None:
                group_beds = same_group.loc[pd.to_numeric(same_group["bedrooms"], errors="coerce") == selected_beds].copy()
                if len(group_beds) >= 3:
                    candidates.append((group_beds, tr("同一区域 / 同大类 / 同卧室数", "Same suburb / same property group / same beds")))
            candidates.append((same_group, tr("同一区域 / 同大类", "Same suburb / same property group")))
    if selected_beds is not None:
        same_beds = scope.loc[pd.to_numeric(scope["bedrooms"], errors="coerce") == selected_beds].copy()
        if not same_beds.empty:
            candidates.append((same_beds, tr("同一区域 / 同卧室数", "Same suburb / same beds")))
    candidates.append((scope, tr("同一区域全部在售挂牌", "All active listings in the same suburb")))

    chosen_scope, scope_label = candidates[-1]
    for candidate_df, candidate_label in candidates:
        if len(candidate_df) >= 3:
            chosen_scope = candidate_df.copy()
            scope_label = candidate_label
            break

    chosen_scope = chosen_scope.copy()
    selected_id = str(row.get("listing_id") or "").strip()
    chosen_scope["listing_id"] = chosen_scope["listing_id"].astype(str)
    chosen_scope["is_selected"] = chosen_scope["listing_id"] == selected_id
    if not chosen_scope["is_selected"].any():
        selected_price = _listing_numeric_price(row)
        if selected_price is not None:
            selected_row = row.to_frame().T.copy()
            selected_row["price_mid"] = selected_price
            selected_row["listing_id"] = selected_id
            selected_row["is_selected"] = True
            chosen_scope = pd.concat([chosen_scope, selected_row], ignore_index=True, sort=False)

    chosen_scope = chosen_scope.drop_duplicates(subset=["listing_id"], keep="first")
    chosen_scope["price_mid"] = pd.to_numeric(chosen_scope["price_mid"], errors="coerce")
    chosen_scope = chosen_scope.loc[chosen_scope["price_mid"].notna()].sort_values(["price_mid", "address"], ascending=[True, True], na_position="last")
    if chosen_scope.empty:
        return empty

    selected_price = _listing_numeric_price(row)
    percentile = None
    selected_rank_text = _report_na()
    if selected_price is not None and len(chosen_scope) >= 2:
        rank = int((chosen_scope["price_mid"] <= float(selected_price)).sum())
        percentile = rank / float(len(chosen_scope))
        selected_rank_text = f"{rank}/{len(chosen_scope)}"

    table = chosen_scope.head(SALE_REPORT_COMPARABLE_LIMIT).copy()
    table["note"] = table["is_selected"].map(lambda value: tr("本房源", "Selected") if bool(value) else "")
    table["type_label"] = table.apply(_report_property_type, axis=1)
    table["beds_label"] = table["bedrooms"].map(_count_label)
    table["price_label"] = table["price_mid"].map(_report_money)
    return {
        "scope_label": scope_label,
        "table": table,
        "percentile": percentile,
        "range_label": _sale_report_percentile_label(percentile),
        "selected_rank_text": selected_rank_text,
    }


def _preferred_pdf_font_path() -> str | None:
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def _pdf_font(size: float, *, bold: bool = False) -> font_manager.FontProperties | None:
    path = _preferred_pdf_font_path()
    if not path:
        return None
    chosen = path
    if bold and Path(r"C:\Windows\Fonts\msyhbd.ttc").exists():
        chosen = r"C:\Windows\Fonts\msyhbd.ttc"
    return font_manager.FontProperties(fname=chosen, size=size)


def _pdf_text(
    fig: plt.Figure,
    x: float,
    y: float,
    text: str,
    *,
    size: float = 10,
    bold: bool = False,
    color: str = "#111827",
    ha: str = "left",
    va: str = "top",
) -> None:
    fig.text(
        x,
        y,
        text,
        fontproperties=_pdf_font(size, bold=bold),
        color=color,
        ha=ha,
        va=va,
    )


def _pdf_wrapped_lines(text: str, *, width: int = 88) -> list[str]:
    content = str(text or "").strip()
    if not content:
        return ["N/A"]
    return textwrap.wrap(content, width=width) or [content]


def _safe_report_filename(row: pd.Series) -> str:
    suburb = str(row.get("suburb") or "").strip().lower()
    address = str(row.get("address") or "").strip().lower()
    base = suburb or address or "property_report"
    base = re.sub(r"[^a-z0-9]+", "_", base)
    base = re.sub(r"_+", "_", base).strip("_")
    if not base:
        base = "property_report"
    return f"property_report_{base}_{pd.Timestamp.now(tz='Australia/Sydney').strftime('%Y-%m-%d')}.pdf"


def _build_sale_report_chart_figure(context: dict[str, object]) -> plt.Figure:
    sold_context = context["sold_context"]
    plot_df = sold_context.get("plot_df", pd.DataFrame())
    fig, ax = plt.subplots(figsize=(8.27, 3.6))
    title = tr("Suburb 成交长期趋势", "Suburb Sold Long-Run Trend")
    if plot_df is None or plot_df.empty:
        ax.axis("off")
        ax.text(
            0.5,
            0.5,
            tr("暂无可用成交趋势图。", "No sold trend chart is available."),
            ha="center",
            va="center",
            fontproperties=_pdf_font(11),
            color="#475467",
        )
        ax.set_title(title, fontproperties=_pdf_font(12, bold=True), loc="left")
        return fig

    frame = plot_df.copy().sort_values("event_time")
    frame["event_time"] = pd.to_datetime(frame["event_time"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["underlying_trend"] = pd.to_numeric(frame.get("underlying_trend"), errors="coerce")
    stable_frame = frame.loc[frame["stable"].fillna(False) & frame["value"].notna()].copy()
    trend_frame = frame.loc[frame["underlying_trend"].notna()].copy()

    if not stable_frame.empty:
        ax.plot(
            stable_frame["event_time"],
            stable_frame["value"],
            color="#1d4ed8",
            linewidth=1.8,
            label=tr("稳定中位价", "Stable median"),
        )
    if not trend_frame.empty:
        ax.plot(
            trend_frame["event_time"],
            trend_frame["underlying_trend"],
            color="#b45309",
            linewidth=2.2,
            linestyle="-",
            label=tr("长期趋势", "Underlying trend"),
        )

    anchor_points = sold_context.get("anchor_points", pd.DataFrame())
    if anchor_points is not None and not anchor_points.empty:
        anchor = anchor_points.iloc[-1]
        ax.scatter([anchor["x"]], [anchor["y"]], color="#111827", s=28, zorder=5)

    ax.set_title(title, fontproperties=_pdf_font(12, bold=True), loc="left")
    ax.grid(True, axis="y", alpha=0.18)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="x", labelrotation=0, labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    if _preferred_pdf_font_path():
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_fontproperties(_pdf_font(8))
    legend = ax.legend(frameon=False, loc="upper left", fontsize=8)
    if legend and _preferred_pdf_font_path():
        for text in legend.get_texts():
            text.set_fontproperties(_pdf_font(8))
    fig.tight_layout()
    return fig


def _build_sale_report_position_figure(context: dict[str, object]) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8.27, 2.5))
    ax.axis("off")
    ax.set_title(tr("Price Positioning", "Price Positioning"), fontproperties=_pdf_font(12, bold=True), loc="left")

    listing_price = _report_numeric(context.get("numeric_price"))
    suburb_median = _report_numeric(context.get("suburb_listing_median"))
    range_low = _report_numeric(context.get("suburb_price_range_low"))
    range_high = _report_numeric(context.get("suburb_price_range_high"))
    valid_values = [value for value in [listing_price, suburb_median, range_low, range_high] if value is not None]
    if len(valid_values) < 2:
        ax.text(
            0.5,
            0.5,
            tr("暂无足够的 suburb 挂牌价格数据来定位本房源。", "Insufficient suburb listing-price data to position this property."),
            ha="center",
            va="center",
            fontproperties=_pdf_font(11),
            color="#475467",
        )
        fig.tight_layout()
        return fig

    plot_min = min(valid_values)
    plot_max = max(valid_values)
    if plot_min == plot_max:
        plot_min = plot_min * 0.95
        plot_max = plot_max * 1.05
    ax.set_xlim(plot_min, plot_max)
    ax.set_ylim(0, 1)
    ax.hlines(0.5, plot_min, plot_max, color="#d0d5dd", linewidth=6, zorder=1)
    ax.scatter([suburb_median], [0.5], color="#1d4ed8", s=110, zorder=3)
    ax.scatter([listing_price], [0.5], color="#111827", s=120, zorder=4)
    ax.text(suburb_median, 0.68, tr("Suburb 中位价", "Suburb median"), ha="center", va="bottom", fontproperties=_pdf_font(9), color="#1d4ed8")
    ax.text(listing_price, 0.28, tr("本房源", "Selected listing"), ha="center", va="top", fontproperties=_pdf_font(9), color="#111827")
    ax.text(plot_min, 0.08, _report_money(plot_min), ha="left", va="bottom", fontproperties=_pdf_font(8), color="#667085")
    ax.text(plot_max, 0.08, _report_money(plot_max), ha="right", va="bottom", fontproperties=_pdf_font(8), color="#667085")
    ax.text(
        0.01,
        0.93,
        f"{tr('结论', 'Conclusion')}: {context.get('price_positioning', 'N/A')}",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontproperties=_pdf_font(10, bold=True),
        color="#111827",
    )
    fig.tight_layout()
    return fig


def _build_sale_report_comparables_figure(context: dict[str, object]) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8.27, 4.4))
    ax.axis("off")
    comparables = context.get("comparables", {})
    table_df = comparables.get("table", pd.DataFrame())
    ax.set_title(tr("Comparable Active Listings", "Comparable Active Listings"), fontproperties=_pdf_font(12, bold=True), loc="left")
    ax.text(
        0.0,
        0.96,
        comparables.get("scope_label", "N/A"),
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontproperties=_pdf_font(9),
        color="#475467",
    )

    if table_df is None or table_df.empty:
        ax.text(
            0.5,
            0.5,
            tr("当前筛选下暂无足够的可比挂牌。", "There are not enough comparable active listings in the current filtered universe."),
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontproperties=_pdf_font(11),
            color="#475467",
        )
        fig.tight_layout()
        return fig

    display = table_df[["note", "address", "type_label", "beds_label", "price_label", "is_selected"]].copy()
    table = ax.table(
        cellText=display.drop(columns=["is_selected"]).values.tolist(),
        colLabels=[
            tr("标记", "Note"),
            tr("地址", "Address"),
            tr("类型", "Type"),
            tr("卧室", "Beds"),
            tr("价格", "Price"),
        ],
        loc="upper left",
        bbox=[0.0, 0.14, 1.0, 0.74],
        cellLoc="left",
        colLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    for (row_idx, _), cell in table.get_celld().items():
        cell.set_edgecolor("#d0d5dd")
        if row_idx == 0:
            cell.set_facecolor("#f3f4f6")
            cell.set_text_props(fontproperties=_pdf_font(8, bold=True), color="#111827")
        else:
            is_selected = bool(display.iloc[row_idx - 1]["is_selected"])
            cell.set_facecolor("#eef2ff" if is_selected else "white")
            cell.set_text_props(fontproperties=_pdf_font(8), color="#111827")

    ax.text(
        0.0,
        0.06,
        f"{tr('价位判断', 'Relative position')}: {comparables.get('range_label', 'N/A')} · {tr('价格排名', 'Price rank')}: {comparables.get('selected_rank_text', 'N/A')}",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontproperties=_pdf_font(9),
        color="#111827",
    )
    fig.tight_layout()
    return fig


def _pdf_section(fig: plt.Figure, y: float, title: str, lines: list[str], *, width: int = 88) -> float:
    _pdf_text(fig, 0.07, y, title, size=13, bold=True)
    y -= 0.026
    for line in lines:
        for wrapped in _pdf_wrapped_lines(line, width=width):
            _pdf_text(fig, 0.08, y, wrapped, size=9.5, color="#111827")
            y -= 0.018
    return y - 0.014


def _render_sale_report_pdf_bytes(row: pd.Series, market_listings: pd.DataFrame) -> bytes:
    context = _build_sale_report_context(row, market_listings)
    sold_metrics = context["sold_context"]["metrics"]
    verdicts = context["verdicts"]

    rcParams["pdf.fonttype"] = 42
    rcParams["ps.fonttype"] = 42

    buffer = BytesIO()
    with PdfPages(buffer) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.patch.set_facecolor("white")
        y = 0.965

        _pdf_text(fig, 0.07, y, tr("房产报告", "Property Report"), size=20, bold=True)
        y -= 0.032
        _pdf_text(fig, 0.07, y, tr("出售房源分析", "Sale Listing Review"), size=11, color="#6b7280")
        y -= 0.04
        _pdf_text(fig, 0.07, y, _report_text(row.get("address")), size=14, bold=True)
        y -= 0.024
        _pdf_text(
            fig,
            0.07,
            y,
            f"{tr('生成日期', 'Generated date')}: {context['generated_at']} · {tr('Suburb', 'Suburb')}: {_report_text(row.get('suburb'))} / {_report_text(row.get('postcode'))}",
            size=9,
            color="#475467",
        )
        y -= 0.05

        sections = [
            (
                tr("房源快照", "Property Snapshot"),
                [
                    f"{tr('地址', 'Address')}: {_report_text(row.get('address'))}",
                    f"{tr('Suburb', 'Suburb')}: {_report_text(row.get('suburb'))}",
                    f"{tr('邮编', 'Postcode')}: {_report_text(row.get('postcode'))}",
                    f"{tr('房产类型', 'Property type')}: {_report_property_type(row)}",
                    f"{tr('卧室', 'Bedrooms')}: {_count_label(row.get('bedrooms'))}",
                    f"{tr('卫生间', 'Bathrooms')}: {_count_label(row.get('bathrooms'))}",
                    f"{tr('车位', 'Parking')}: {_count_label(row.get('parking'))}",
                    f"{tr('挂牌价格', 'Listing price')}: {_report_text(row.get('price_display'))} ({_report_money(context['numeric_price'])})",
                ],
            ),
            (
                tr("Suburb 成交市场快照", "Suburb Sold Market Snapshot"),
                [
                    f"{tr('最新稳定中位价', 'Latest stable median')}: {_report_money(sold_metrics.get('latest_median'))}",
                    f"{tr('稳定同比', 'Stable YoY')}: {_report_pct(sold_metrics.get('stable_yoy'))}",
                    f"{tr('最新稳定日期', 'Latest stable date')}: {_report_date(sold_metrics.get('latest_point'))}",
                    f"{tr('28天成交量', '28-day sales volume')}: {_report_text(fmt_int(sold_metrics['sales']) if sold_metrics.get('sales') is not None else 'N/A')}",
                ],
            ),
            (
                tr("当前挂牌位置", "Current Listing Position"),
                [
                    f"{tr('本房源价格', 'This listing price')}: {_report_money(context['numeric_price'])}",
                    f"{tr('当前 suburb 挂牌中位价', 'Current suburb listing median')}: {_report_money(context['suburb_listing_median'])}",
                    f"{context['same_type_label']}: {_report_money(context['same_type_listing_median'])}",
                    f"{tr('相对 suburb 挂牌中位价', 'vs suburb listing median')}: {_report_pct(context['delta_vs_suburb'])}",
                    f"{tr('相对可比挂牌中位价', 'vs comparable listing median')}: {_report_pct(context['delta_vs_same_type'])}",
                ],
            ),
            (
                tr("结论摘要", "Summary Verdict"),
                [
                    f"{tr('价格 vs 成交市场', 'Price vs Sold Market')}: {verdicts['sold_market']}",
                    f"{tr('价格 vs 当前挂牌', 'Price vs Current Listings')}: {verdicts['current_listings']}",
                    f"{tr('本地趋势', 'Local Trend')}: {verdicts['local_trend']}",
                    context["summary_sentence"],
                ],
            ),
            (
                tr("说明", "Footer / Disclaimer"),
                [
                    tr(
                        "本报告基于近期成交与挂牌数据生成，仅作市场参考，不构成正式估值。",
                        "This report is a market context summary based on recent sold and listing data. It is not a formal valuation.",
                    ),
                    tr(
                        "成交数据：已记录成交；挂牌数据：当前出售房源。",
                        "Sold data: recorded transactions. Listing data: current sale listings.",
                    ),
                ],
            ),
        ]

        for title, lines in sections:
            _pdf_text(fig, 0.07, y, title, size=13, bold=True)
            y -= 0.026
            for line in lines:
                for wrapped in _pdf_wrapped_lines(line, width=88):
                    _pdf_text(fig, 0.08, y, wrapped, size=9.5, color="#111827")
                    y -= 0.018
            y -= 0.014

        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        chart_fig = _build_sale_report_chart_figure(context)
        pdf.savefig(chart_fig, bbox_inches="tight")
        plt.close(chart_fig)

    buffer.seek(0)
    return buffer.getvalue()


def _render_sale_report_pdf_bytes_v2(row: pd.Series, market_listings: pd.DataFrame) -> bytes:
    context = _build_sale_report_context(row, market_listings)
    sold_metrics = context["sold_context"]["metrics"]
    price_band = context["price_band"]
    rent_context = context["rent_context"]
    comparables = context["comparables"]

    rcParams["pdf.fonttype"] = 42
    rcParams["ps.fonttype"] = 42

    buffer = BytesIO()
    with PdfPages(buffer) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.patch.set_facecolor("white")
        y = 0.965

        _pdf_text(fig, 0.07, y, tr("出售 shortlist 决策报告", "Sale Shortlist Decision Report"), size=20, bold=True)
        y -= 0.035
        _pdf_text(fig, 0.07, y, _report_text(row.get("address")), size=14, bold=True)
        y -= 0.024
        _pdf_text(
            fig,
            0.07,
            y,
            f"{tr('Generated date', 'Generated date')}: {context['generated_at']} | {tr('Suburb', 'Suburb')}: {_report_text(row.get('suburb'))} / {_report_text(row.get('postcode'))}",
            size=9,
            color="#475467",
        )
        y -= 0.05

        y = _pdf_section(
            fig,
            y,
            tr("1. Property Snapshot", "1. Property Snapshot"),
            [
                f"{tr('Address', 'Address')}: {_report_text(row.get('address'))}",
                f"{tr('Suburb / Postcode', 'Suburb / Postcode')}: {_report_text(row.get('suburb'))} / {_report_text(row.get('postcode'))}",
                f"{tr('Property type', 'Property type')}: {_report_property_type(row)}",
                f"{tr('Bedrooms / Bathrooms / Parking', 'Bedrooms / Bathrooms / Parking')}: {_count_label(row.get('bedrooms'))} / {_count_label(row.get('bathrooms'))} / {_count_label(row.get('parking'))}",
                f"{tr('Listing price', 'Listing price')}: {_report_text(row.get('price_display'))} ({_report_money(context['numeric_price'])})",
                f"{tr('Price positioning', 'Price positioning')}: {context['price_positioning']}",
                f"{tr('Current suburb listing median', 'Current suburb listing median')}: {_report_money(context['suburb_listing_median'])}",
                f"{context['same_type_label']}: {_report_money(context['same_type_listing_median'])}",
            ],
        )
        y = _pdf_section(
            fig,
            y,
            tr("2. Suburb Market Context", "2. Suburb Market Context"),
            [
                f"{tr('Latest stable median', 'Latest stable median')}: {_report_money(sold_metrics.get('latest_median'))}",
                f"{tr('Stable YoY', 'Stable YoY')}: {_report_pct(sold_metrics.get('stable_yoy'))}",
                f"{tr('28-day sales volume', '28-day sales volume')}: {_report_text(fmt_int(sold_metrics['sales']) if sold_metrics.get('sales') is not None else 'N/A')}",
                f"{tr('Market read', 'Market read')}: {context['verdicts']['local_trend']}",
                f"{tr('Liquidity read', 'Liquidity read')}: {context['liquidity_label']}",
                f"{tr('Latest stable date', 'Latest stable date')}: {_report_date(sold_metrics.get('latest_point'))}",
            ],
        )
        y = _pdf_section(
            fig,
            y,
            tr("3. Price-Band Trend Context", "3. Price-Band Trend Context"),
            [
                f"{tr('Selected price band', 'Selected price band')}: {_report_text(price_band.get('label'))}",
                f"{tr('Band anchor value', 'Band anchor value')}: {_report_money(price_band.get('latest_value'))}",
                f"{tr('Band stable YoY', 'Band stable YoY')}: {_report_pct(price_band.get('stable_yoy'))}",
                f"{tr('Band trend', 'Band trend')}: {_report_text(price_band.get('trend_label'))}",
                f"{tr('Band anchor date', 'Band anchor date')}: {_report_date(price_band.get('anchor_date'))}",
            ],
        )
        y = _pdf_section(
            fig,
            y,
            tr("4. Decision Summary", "4. Decision Summary"),
            [
                context["summary_sentence"],
                tr(
                    "This positioning uses the active filtered Sale listings universe and is not redefined by local focused-suburb state.",
                    "This positioning uses the active filtered Sale listings universe and is not redefined by local focused-suburb state.",
                ),
            ],
        )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        position_fig = _build_sale_report_position_figure(context)
        pdf.savefig(position_fig, bbox_inches="tight")
        plt.close(position_fig)

        chart_fig = _build_sale_report_chart_figure(context)
        pdf.savefig(chart_fig, bbox_inches="tight")
        plt.close(chart_fig)

        fig = plt.figure(figsize=(8.27, 11.69))
        fig.patch.set_facecolor("white")
        y = 0.965
        y = _pdf_section(
            fig,
            y,
            tr("5. Investment View", "5. Investment View"),
            [
                f"{tr('Suburb median weekly rent', 'Suburb median weekly rent')}: {_report_money(rent_context.get('median_weekly_rent'))}",
                f"{tr('Current rental listings in suburb', 'Current rental listings in suburb')}: {_report_text(fmt_int(rent_context.get('active_rental_count')) if rent_context.get('active_rental_count') is not None else 'N/A')}",
                f"{tr('Priced rental listings', 'Priced rental listings')}: {_report_text(fmt_int(rent_context.get('priced_rental_count')) if rent_context.get('priced_rental_count') is not None else 'N/A')}",
                f"{tr('Rental activity', 'Rental activity')}: {_report_text(rent_context.get('activity_label'))}",
                f"{tr('Estimated gross yield', 'Estimated gross yield')}: {_report_pct(context.get('estimated_gross_yield'))}",
                tr("Formula: suburb median weekly rent x 52 / selected listing price.", "Formula: suburb median weekly rent x 52 / selected listing price."),
                tr(
                    "This gross yield is a suburb-level estimate, not a property-specific rental appraisal.",
                    "This gross yield is a suburb-level estimate, not a property-specific rental appraisal.",
                ),
            ],
        )
        y = _pdf_section(
            fig,
            y,
            tr("6. Comparable Listings Conclusion", "6. Comparable Listings Conclusion"),
            [
                comparables.get("scope_label", "N/A"),
                f"{tr('Relative position', 'Relative position')}: {comparables.get('range_label', 'N/A')}",
                f"{tr('Price rank', 'Price rank')}: {comparables.get('selected_rank_text', 'N/A')}",
            ],
        )
        y = _pdf_section(
            fig,
            y,
            tr("7. Notes", "7. Notes"),
            [
                tr(
                    "This report is generated from recent sold data and current active listings. It is decision support only, not a formal valuation.",
                    "This report is generated from recent sold data and current active listings. It is decision support only, not a formal valuation.",
                ),
                tr(
                    "Current-listing positioning and comparables use the Sale page active filtered dataset only, so browser, shortlist, and report figures stay aligned.",
                    "Current-listing positioning and comparables use the Sale page active filtered dataset only, so browser, shortlist, and report figures stay aligned.",
                ),
                tr(
                    "When suburb-level or rent-side data is insufficient, the report shows N/A instead of switching to an inconsistent fallback methodology.",
                    "When suburb-level or rent-side data is insufficient, the report shows N/A instead of switching to an inconsistent fallback methodology.",
                ),
            ],
        )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        comparables_fig = _build_sale_report_comparables_figure(context)
        pdf.savefig(comparables_fig, bbox_inches="tight")
        plt.close(comparables_fig)

    buffer.seek(0)
    return buffer.getvalue()


_REPORT_PDF_FONT_NAME = "STSong-Light"


def _register_report_pdf_font() -> str:
    if _REPORT_PDF_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(_REPORT_PDF_FONT_NAME))
    return _REPORT_PDF_FONT_NAME


def _report_pdf_styles() -> dict[str, ParagraphStyle]:
    font_name = _register_report_pdf_font()
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "SaleReportTitle",
            parent=base["Title"],
            fontName=font_name,
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#111827"),
            alignment=TA_LEFT,
            spaceAfter=6,
            wordWrap="CJK",
        ),
        "subtitle": ParagraphStyle(
            "SaleReportSubtitle",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#475467"),
            wordWrap="CJK",
        ),
        "section": ParagraphStyle(
            "SaleReportSection",
            parent=base["Heading2"],
            fontName=font_name,
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#111827"),
            spaceBefore=4,
            spaceAfter=6,
            wordWrap="CJK",
        ),
        "body": ParagraphStyle(
            "SaleReportBody",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=9.5,
            leading=12,
            textColor=colors.HexColor("#111827"),
            wordWrap="CJK",
        ),
        "small": ParagraphStyle(
            "SaleReportSmall",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#475467"),
            wordWrap="CJK",
        ),
    }


def _report_paragraph(text: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(_report_text(text)).replace("\n", "<br/>"), style)


def _report_section_table(title: str, rows: list[tuple[str, object]], styles: dict[str, ParagraphStyle]) -> list[object]:
    flowables: list[object] = [Paragraph(escape(title), styles["section"])]
    table_rows = []
    for label, value in rows:
        table_rows.append([
            _report_paragraph(label, styles["body"]),
            _report_paragraph(value, styles["body"]),
        ])
    table = Table(table_rows, colWidths=[52 * mm, 122 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _REPORT_PDF_FONT_NAME),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("LEADING", (0, 0), (-1, -1), 12),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d5dd")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#e4e7ec")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    flowables.extend([table, Spacer(1, 4 * mm)])
    return flowables


def _report_figure_image(fig: plt.Figure, *, width_mm: float, height_mm: float | None = None) -> Image:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    image = Image(buffer)
    image.drawWidth = width_mm * mm
    if height_mm is not None:
        image.drawHeight = height_mm * mm
    else:
        aspect = image.imageHeight / float(image.imageWidth) if image.imageWidth else 1.0
        image.drawHeight = image.drawWidth * aspect
    return image


def _build_sale_report_chart_figure(context: dict[str, object]) -> plt.Figure:
    sold_context = context["sold_context"]
    plot_df = sold_context.get("plot_df", pd.DataFrame())
    fig, ax = plt.subplots(figsize=(8.27, 3.6))
    title = tr("区域成交长期趋势", "Suburb Sold Long-Run Trend")
    if plot_df is None or plot_df.empty:
        ax.axis("off")
        ax.text(
            0.5,
            0.5,
            tr("暂无可用成交趋势图。", "No sold trend chart is available."),
            ha="center",
            va="center",
            fontproperties=_pdf_font(11),
            color="#475467",
        )
        ax.set_title(title, fontproperties=_pdf_font(12, bold=True), loc="left")
        fig.tight_layout()
        return fig

    df = plot_df.copy().sort_values("event_time")
    x = pd.to_datetime(df["event_time"], errors="coerce")
    value = pd.to_numeric(df["value"], errors="coerce")
    stable = (df["is_stable"].fillna(False).astype(bool) if "is_stable" in df.columns else pd.Series([False] * len(df), index=df.index))
    trend = pd.to_numeric(df.get("underlying_trend"), errors="coerce")

    ax.plot(x, value, color="#cbd5e1", linewidth=1.4, alpha=0.9)
    if stable.any():
        ax.plot(
            x[stable],
            value[stable],
            color="#2563eb",
            linewidth=2.2,
            label=tr("稳定中位价", "Stable median"),
        )
    if trend.notna().any():
        ax.plot(
            x[trend.notna()],
            trend[trend.notna()],
            color="#0f766e",
            linewidth=1.8,
            linestyle="--",
            label=tr("长期趋势", "Underlying trend"),
        )
    anchor_points = sold_context.get("anchor_points", pd.DataFrame())
    if anchor_points is not None and not anchor_points.empty:
        anchor_x = pd.to_datetime(anchor_points["x"], errors="coerce")
        anchor_y = pd.to_numeric(anchor_points["y"], errors="coerce")
        ax.scatter(anchor_x, anchor_y, color="#111827", s=26, zorder=4)

    ax.set_title(title, fontproperties=_pdf_font(12, bold=True), loc="left")
    ax.tick_params(axis="x", labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontproperties(_pdf_font(8))
    ax.grid(True, axis="y", alpha=0.2)
    if ax.get_legend_handles_labels()[0]:
        legend = ax.legend(frameon=False, fontsize=8, loc="upper left")
        for text in legend.get_texts():
            text.set_fontproperties(_pdf_font(8))
    fig.tight_layout()
    return fig


def _build_sale_report_position_figure(context: dict[str, object]) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8.27, 2.2))
    ax.axis("off")
    listing_price = _report_numeric(context.get("numeric_price"))
    suburb_median = _report_numeric(context.get("suburb_listing_median"))
    range_low = _report_numeric(context.get("suburb_price_range_low"))
    range_high = _report_numeric(context.get("suburb_price_range_high"))
    ax.set_title(tr("价格定位", "Price Positioning"), fontproperties=_pdf_font(12, bold=True), loc="left")

    if None in {listing_price, suburb_median, range_low, range_high}:
        ax.text(
            0.5,
            0.5,
            tr("当前区域挂牌价格数据不足，暂无法定位本房源。", "Insufficient suburb listing-price data to position this property."),
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontproperties=_pdf_font(11),
            color="#475467",
        )
        fig.tight_layout()
        return fig

    plot_min = min(range_low, suburb_median, listing_price)
    plot_max = max(range_high, suburb_median, listing_price)
    if plot_max <= plot_min:
        plot_max = plot_min + 1.0

    ax.hlines(0.5, plot_min, plot_max, color="#cbd5e1", linewidth=6, alpha=0.8)
    ax.scatter([suburb_median], [0.5], color="#2563eb", s=90, zorder=3)
    ax.scatter([listing_price], [0.5], color="#111827", s=90, zorder=4)
    ax.text(suburb_median, 0.68, tr("区域挂牌中位价", "Suburb median"), ha="center", va="bottom", fontproperties=_pdf_font(9), color="#1d4ed8")
    ax.text(listing_price, 0.28, tr("本房源", "Selected listing"), ha="center", va="top", fontproperties=_pdf_font(9), color="#111827")
    ax.text(plot_min, 0.08, _report_money(plot_min), ha="left", va="bottom", fontproperties=_pdf_font(8), color="#667085")
    ax.text(plot_max, 0.08, _report_money(plot_max), ha="right", va="bottom", fontproperties=_pdf_font(8), color="#667085")
    ax.text(
        0.0,
        0.93,
        f"{tr('结论', 'Conclusion')}: {context.get('price_positioning', _report_na())}",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontproperties=_pdf_font(10, bold=True),
        color="#111827",
    )
    fig.tight_layout()
    return fig


def _build_sale_report_comparables_figure(context: dict[str, object]) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8.27, 4.4))
    ax.axis("off")
    comparables = context.get("comparables", {})
    table_df = comparables.get("table", pd.DataFrame())
    ax.set_title(tr("当前可比在售挂牌", "Comparable Active Listings"), fontproperties=_pdf_font(12, bold=True), loc="left")
    ax.text(
        0.0,
        0.96,
        comparables.get("scope_label", _report_na()),
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontproperties=_pdf_font(9),
        color="#475467",
    )
    if table_df is None or table_df.empty:
        ax.text(
            0.5,
            0.5,
            tr("当前筛选范围内暂无足够可比挂牌。", "There are not enough comparable active listings in the current filtered universe."),
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontproperties=_pdf_font(11),
            color="#475467",
        )
        fig.tight_layout()
        return fig

    display = table_df[["note", "address", "type_label", "beds_label", "price_label", "is_selected"]].copy()
    table = ax.table(
        cellText=display.drop(columns=["is_selected"]).values.tolist(),
        colLabels=[
            tr("标记", "Note"),
            tr("地址", "Address"),
            tr("类型", "Type"),
            tr("卧室", "Beds"),
            tr("价格", "Price"),
        ],
        loc="upper left",
        bbox=[0.0, 0.14, 1.0, 0.74],
        cellLoc="left",
        colLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    for (row_idx, _), cell in table.get_celld().items():
        cell.set_edgecolor("#d0d5dd")
        if row_idx == 0:
            cell.set_facecolor("#f3f4f6")
            cell.set_text_props(fontproperties=_pdf_font(8, bold=True), color="#111827")
        else:
            is_selected = bool(display.iloc[row_idx - 1]["is_selected"])
            cell.set_facecolor("#eef2ff" if is_selected else "white")
            cell.set_text_props(fontproperties=_pdf_font(8), color="#111827")
    ax.text(
        0.0,
        0.06,
        f"{tr('相对位置', 'Relative position')}: {comparables.get('range_label', _report_na())} · {tr('价格排名', 'Price rank')}: {comparables.get('selected_rank_text', _report_na())}",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontproperties=_pdf_font(9),
        color="#111827",
    )
    fig.tight_layout()
    return fig


def _render_sale_report_pdf_bytes_v2(row: pd.Series, market_listings: pd.DataFrame) -> bytes:
    context = _build_sale_report_context(row, market_listings)
    sold_metrics = context["sold_context"]["metrics"]
    price_band = context["price_band"]
    rent_context = context["rent_context"]
    comparables = context["comparables"]
    numeric_price = context.get("numeric_price")
    styles = _report_pdf_styles()
    _register_report_pdf_font()

    rcParams["pdf.fonttype"] = 42
    rcParams["ps.fonttype"] = 42

    story: list[object] = []
    story.append(Paragraph(escape(tr("出售候选房源决策报告", "Sale Shortlist Decision Report")), styles["title"]))
    story.append(_report_paragraph(_report_text(row.get("address")), styles["body"]))
    story.append(Spacer(1, 1.5 * mm))
    story.append(_report_paragraph(
        f"{tr('生成日期', 'Generated date')}: {context['generated_at']} | {tr('区域 / 邮编', 'Suburb / Postcode')}: {_report_text(row.get('suburb'))} / {_report_text(row.get('postcode'))}",
        styles["subtitle"],
    ))
    story.append(Spacer(1, 4 * mm))

    story.extend(_report_section_table(
        tr("1. 房源快照", "1. Property Snapshot"),
        [
            (tr("地址", "Address"), _report_text(row.get("address"))),
            (tr("区域 / 邮编", "Suburb / Postcode"), f"{_report_text(row.get('suburb'))} / {_report_text(row.get('postcode'))}"),
            (tr("房产类型", "Property type"), _report_property_type(row)),
            (tr("卧室 / 浴室 / 车位", "Bedrooms / Bathrooms / Parking"), f"{_count_label(row.get('bedrooms'))} / {_count_label(row.get('bathrooms'))} / {_count_label(row.get('parking'))}"),
            (tr("挂牌价格", "Listing price"), _report_listing_price_line(row, numeric_price)),
            (tr("价格定位", "Price positioning"), context["price_positioning"]),
            (tr("当前区域挂牌中位价", "Current suburb listing median"), _report_money(context["suburb_listing_median"])),
            (_report_text(context["same_type_label"]), _report_money(context["same_type_listing_median"])),
        ],
        styles,
    ))
    story.append(_report_figure_image(_build_sale_report_position_figure(context), width_mm=180, height_mm=42))
    story.append(Spacer(1, 4 * mm))

    story.extend(_report_section_table(
        tr("2. 区域市场背景", "2. Suburb Market Context"),
        [
            (tr("稳定中位价", "Latest stable median"), _report_money(sold_metrics.get("latest_median"))),
            (tr("稳定同比", "Stable YoY"), _report_pct(sold_metrics.get("stable_yoy"))),
            (tr("28天成交量", "28-day sales volume"), _report_text(fmt_int(sold_metrics["sales"]) if sold_metrics.get("sales") is not None else _report_na())),
            (tr("市场判断", "Market read"), context["verdicts"]["local_trend"]),
            (tr("流动性判断", "Liquidity read"), context["liquidity_label"]),
            (tr("稳定锚点日期", "Latest stable date"), _report_date(sold_metrics.get("latest_point"))),
        ],
        styles,
    ))

    story.extend(_report_section_table(
        tr("3. 价格带趋势背景", "3. Price-Band Trend Context"),
        [
            (tr("所处价格带", "Selected price band"), _report_text(price_band.get("label"))),
            (tr("价格带锚点价", "Band anchor value"), _report_money(price_band.get("latest_value"))),
            (tr("价格带稳定同比", "Band stable YoY"), _report_pct(price_band.get("stable_yoy"))),
            (tr("价格带趋势", "Band trend"), _report_text(price_band.get("trend_label"))),
            (tr("价格带锚点日期", "Band anchor date"), _report_date(price_band.get("anchor_date"))),
        ],
        styles,
    ))

    story.extend(_report_section_table(
        tr("4. 决策摘要", "4. Decision Summary"),
        [
            (tr("综合判断", "Decision summary"), context["summary_sentence"]),
            (
                tr("口径说明", "Method note"),
                tr(
                    "该定位严格基于买房预算页面当前筛选后的挂牌宇宙，不会被局部聚焦区域状态重新定义。",
                    "This positioning uses the active filtered Sale listings universe and is not redefined by local focused-suburb state.",
                ),
            ),
        ],
        styles,
    ))

    story.append(_report_figure_image(_build_sale_report_chart_figure(context), width_mm=180, height_mm=72))
    story.append(Spacer(1, 4 * mm))

    story.extend(_report_section_table(
        tr("5. 投资视角", "5. Investment View"),
        [
            (tr("区域周租金中位数", "Suburb median weekly rent"), _report_money(rent_context.get("median_weekly_rent"))),
            (tr("当前区域租赁挂牌数", "Current rental listings in suburb"), _report_text(fmt_int(rent_context.get("active_rental_count")) if rent_context.get("active_rental_count") is not None else _report_na())),
            (tr("有租金价格的挂牌数", "Priced rental listings"), _report_text(fmt_int(rent_context.get("priced_rental_count")) if rent_context.get("priced_rental_count") is not None else _report_na())),
            (tr("租赁活跃度", "Rental activity"), _report_text(rent_context.get("activity_label"))),
            (tr("估算毛租金回报率", "Estimated gross yield"), _report_pct(context.get("estimated_gross_yield"))),
            (tr("计算公式", "Formula"), tr("区域周租金中位数 × 52 ÷ 本房源价格", "Suburb median weekly rent x 52 / selected listing price")),
            (
                tr("说明", "Note"),
                tr(
                    "该毛租金回报率为区域层级估算，并非针对该房源的独立租金评估。",
                    "This gross yield is a suburb-level estimate, not a property-specific rental appraisal.",
                ),
            ),
        ],
        styles,
    ))

    story.extend(_report_section_table(
        tr("6. 可比挂牌结论", "6. Comparable Listings Conclusion"),
        [
            (tr("可比范围", "Comparable scope"), comparables.get("scope_label", _report_na())),
            (tr("相对位置", "Relative position"), comparables.get("range_label", _report_na())),
            (tr("价格排名", "Price rank"), comparables.get("selected_rank_text", _report_na())),
        ],
        styles,
    ))

    story.extend(_report_section_table(
        tr("7. 说明", "7. Notes"),
        [
            (
                tr("用途", "Purpose"),
                tr(
                    "本报告基于近期成交数据与当前在售挂牌生成，仅用于辅助决策，不构成正式估值。",
                    "This report is generated from recent sold data and current active listings. It is decision support only, not a formal valuation.",
                ),
            ),
            (
                tr("一致性", "Consistency"),
                tr(
                    "当前挂牌定位与可比范围仅使用买房预算页面当前筛选后的数据集，因此浏览器、候选房源与报告数字保持一致。",
                    "Current-listing positioning and comparables use the Sale page active filtered dataset only, so browser, shortlist, and report figures stay aligned.",
                ),
            ),
            (
                tr("缺失值处理", "Missing-data handling"),
                tr(
                    "当区域或租赁侧数据不足时，报告显示“暂无”，不会切换到不一致的回退算法。",
                    "When suburb-level or rent-side data is insufficient, the report shows N/A instead of switching to an inconsistent fallback methodology.",
                ),
            ),
        ],
        styles,
    ))

    story.append(_report_figure_image(_build_sale_report_comparables_figure(context), width_mm=180, height_mm=96))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=_report_text(row.get("address")),
        author="NSW Property Data",
    )
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def _build_external_sale_budget_scale() -> list[int]:
    values: set[int] = {0, 10_000_000}
    values.update(range(50_000, 1_000_000, 50_000))
    values.update(range(1_000_000, 3_000_001, 100_000))
    values.update(range(3_000_000, 5_000_001, 250_000))
    values.update(range(5_000_000, 10_000_001, 500_000))
    return sorted(values)


def _format_external_sale_budget_label(value: int | str) -> str:
    if isinstance(value, str):
        text = value.strip().upper()
        if text in {"0"} or text.endswith(("K", "M")):
            return text
        amount = int(text.replace(",", ""))
    else:
        amount = int(value)
    if amount <= 0:
        return "0"
    if amount < 1_000_000:
        return f"{int(amount / 1_000)}K"
    return f"{amount / 1_000_000:.1f}M"


def _coerce_external_budget_range(
    saved_range: tuple[int, int] | list[int] | None,
    *,
    options: list[int],
    default_range: tuple[int, int],
) -> tuple[int, int]:
    if not options:
        return default_range

    if (
        isinstance(saved_range, (list, tuple))
        and len(saved_range) == 2
    ):
        raw_min, raw_max = int(saved_range[0]), int(saved_range[1])
    else:
        raw_min, raw_max = default_range

    nearest_min = min(options, key=lambda item: (abs(item - raw_min), item))
    nearest_max = min(options, key=lambda item: (abs(item - raw_max), item))
    if nearest_min > nearest_max:
        return default_range
    return nearest_min, nearest_max


def _availability_level(listing_count: int) -> tuple[str, str]:
    if listing_count >= 12:
        return tr("供应充足", "High availability"), "green"
    if listing_count >= 5:
        return tr("供应中等", "Medium availability"), "orange"
    return tr("供应偏紧", "Low availability"), "red"


def _affordability_signal(listing_count: int) -> tuple[str, str]:
    if listing_count >= 20:
        return tr("预算优势明显", "Budget looks strong"), "green"
    if listing_count >= 6:
        return tr("预算基本可行", "Budget is workable"), "orange"
    return tr("预算较紧", "Budget is tight"), "red"


def _mode_or_na(series: pd.Series) -> str:
    cleaned = series.dropna()
    if cleaned.empty:
        return "N/A"
    mode = cleaned.mode()
    if mode.empty:
        return "N/A"
    value = mode.iloc[0]
    if isinstance(value, float) and float(value).is_integer():
        return str(int(value))
    return str(value)


def _normalise_bounds(df: pd.DataFrame) -> tuple[int, int]:
    source_df = apply_external_sale_listing_display_filter(df)
    if source_df.empty:
        source_df = df
    return 0, 10_000_000


def _title_case_subtype(value: str) -> str:
    if not value or value == "unknown":
        return tr("Unknown", "Unknown")
    return value.title()


def _property_group_options(df: pd.DataFrame) -> list[tuple[str, str, int]]:
    counts = df["property_group"].fillna("other").value_counts().to_dict()
    return [
        (group, tr(label, label), int(counts.get(group, 0)))
        for group, label in [
            ("house", "House"),
            ("apartment", "Apartment"),
            ("townhouse", "Townhouse"),
            ("land", "Land"),
            ("other", "Other"),
        ]
        if counts.get(group, 0) > 0
    ]


def _subtype_counts(df: pd.DataFrame, group: str) -> pd.Series:
    subset = df.loc[df["property_group"] == group, "property_subtype"].fillna("unknown")
    return subset.value_counts().sort_values(ascending=False)


def _category_option_label(label: str, count: int) -> str:
    return label if IS_EXTERNAL_DEPLOYMENT or IS_PUBLIC_MODE else f"{label} ({count:,})"


def _init_state() -> None:
    if "budget_shortlist_ids" not in st.session_state:
        st.session_state["budget_shortlist_ids"] = []
    if "budget_shortlist_items" not in st.session_state:
        st.session_state["budget_shortlist_items"] = {}
    if "budget_selected_suburb" not in st.session_state:
        st.session_state["budget_selected_suburb"] = "__ALL__"
    if "budget_selected_listing_id" not in st.session_state:
        st.session_state["budget_selected_listing_id"] = None
    if "budget_map_focus_token" not in st.session_state:
        st.session_state["budget_map_focus_token"] = None
    if "budget_map_view" not in st.session_state:
        st.session_state["budget_map_view"] = {"center": None, "zoom": None}
    if "budget_focus_notice" not in st.session_state:
        st.session_state["budget_focus_notice"] = None
    if "budget_commute_notice" not in st.session_state:
        st.session_state["budget_commute_notice"] = None
    if "budget_group_notice" not in st.session_state:
        st.session_state["budget_group_notice"] = None
    if "buy_external_search_triggered" not in st.session_state:
        st.session_state["buy_external_search_triggered"] = False
    if "budget_listing_page" not in st.session_state:
        st.session_state["budget_listing_page"] = 0
    if "budget_ranking_page" not in st.session_state:
        st.session_state["budget_ranking_page"] = 0
    if "budget_same_suburb_page" not in st.session_state:
        st.session_state["budget_same_suburb_page"] = 0
    if "budget_browser_scope_mode" not in st.session_state:
        st.session_state["budget_browser_scope_mode"] = "filtered"


def _consume_focus_notice(key: str) -> str | None:
    notice = st.session_state.get(key)
    st.session_state[key] = None
    return notice


def _format_budget_input(value: int) -> str:
    return f"{int(value):,}"


def _parse_budget_input(value: str) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return None
    return int(digits)


def _normalise_budget_value(value: int, min_budget: int, max_budget: int) -> int:
    clamped = max(min_budget, min(max_budget, int(value)))
    return int(round(clamped / BUDGET_STEP) * BUDGET_STEP)


def _ensure_budget_input_state(min_budget: int, max_budget: int) -> None:
    if "budget_range_slider" not in st.session_state:
        st.session_state["budget_range_slider"] = (min_budget, max_budget)
    current_min, current_max = st.session_state["budget_range_slider"]
    current_min = _normalise_budget_value(current_min, min_budget, max_budget)
    current_max = _normalise_budget_value(current_max, min_budget, max_budget)
    if current_min > current_max:
        current_min, current_max = min_budget, max_budget
    st.session_state["budget_range_slider"] = (current_min, current_max)
    if "budget_min_input" not in st.session_state:
        st.session_state["budget_min_input"] = _format_budget_input(st.session_state["budget_range_slider"][0])
    if "budget_max_input" not in st.session_state:
        st.session_state["budget_max_input"] = _format_budget_input(st.session_state["budget_range_slider"][1])
    if "budget_input_error" not in st.session_state:
        st.session_state["budget_input_error"] = None


def _apply_pending_budget_widget_state(min_budget: int, max_budget: int) -> None:
    pending_range = st.session_state.pop("budget_pending_range", None)
    if pending_range is None:
        return
    budget_min = _normalise_budget_value(pending_range[0], min_budget, max_budget)
    budget_max = _normalise_budget_value(pending_range[1], min_budget, max_budget)
    if budget_min > budget_max:
        budget_min, budget_max = min_budget, max_budget
    st.session_state["budget_range_slider"] = (budget_min, budget_max)
    st.session_state["budget_min_input"] = _format_budget_input(budget_min)
    st.session_state["budget_max_input"] = _format_budget_input(budget_max)


def _resolve_budget_submit_form_safe(
    *,
    min_budget: int,
    max_budget: int,
    slider_range: tuple[int, int],
    text_min_raw: str | None,
    text_max_raw: str | None,
) -> bool:
    slider_min = _normalise_budget_value(slider_range[0], min_budget, max_budget)
    slider_max = _normalise_budget_value(slider_range[1], min_budget, max_budget)
    parsed_min = _parse_budget_input(text_min_raw)
    parsed_max = _parse_budget_input(text_max_raw)
    use_text_override = parsed_min is not None and parsed_max is not None

    if use_text_override:
        budget_min = _normalise_budget_value(parsed_min, min_budget, max_budget)
        budget_max = _normalise_budget_value(parsed_max, min_budget, max_budget)
        if budget_min > budget_max:
            st.session_state["budget_input_error"] = tr("最低预算不能高于最高预算。", "Minimum budget cannot be higher than maximum budget.")
            budget_min, budget_max = slider_min, slider_max
        else:
            st.session_state["budget_input_error"] = None
    else:
        budget_min, budget_max = slider_min, slider_max
        text_min_present = bool(str(text_min_raw or "").strip())
        text_max_present = bool(str(text_max_raw or "").strip())
        if text_min_present or text_max_present:
            st.session_state["budget_input_error"] = tr("预算输入无效，已使用滑块预算区间。", "Budget inputs were invalid, so the slider range was used.")
        else:
            st.session_state["budget_input_error"] = None

    formatted_min = _format_budget_input(budget_min)
    formatted_max = _format_budget_input(budget_max)
    needs_widget_sync = (
        st.session_state.get("budget_range_slider") != (budget_min, budget_max)
        or st.session_state.get("budget_min_input") != formatted_min
        or st.session_state.get("budget_max_input") != formatted_max
    )
    if needs_widget_sync:
        st.session_state["budget_pending_range"] = (budget_min, budget_max)
    st.session_state["budget_applied_range"] = (budget_min, budget_max)
    return needs_widget_sync


def _get_shortlist_ids() -> set[str]:
    _init_state()
    return set(st.session_state["budget_shortlist_ids"])


def _set_shortlist_ids(ids: set[str]) -> None:
    st.session_state["budget_shortlist_ids"] = sorted(ids)


def _snapshot_listing(row: pd.Series | dict[str, object]) -> dict[str, object]:
    if isinstance(row, dict):
        return dict(row)
    return row.to_dict()


def _toggle_shortlist(listing_id: str, row: pd.Series | None = None) -> None:
    shortlist_ids = _get_shortlist_ids()
    shortlist_items = st.session_state.setdefault("budget_shortlist_items", {})
    if listing_id in shortlist_ids:
        shortlist_ids.remove(listing_id)
        shortlist_items.pop(listing_id, None)
    else:
        shortlist_ids.add(listing_id)
        if row is not None:
            shortlist_items[listing_id] = _snapshot_listing(row)
    _set_shortlist_ids(shortlist_ids)


def _toggle_shortlist_callback(listing_id: str, snapshot: dict[str, object] | None = None) -> None:
    row = pd.Series(snapshot) if snapshot is not None else None
    _toggle_shortlist(listing_id, row)


def _selected_suburb() -> str:
    _init_state()
    return st.session_state["budget_selected_suburb"]


def _selected_listing_id() -> str | None:
    _init_state()
    value = st.session_state.get("budget_selected_listing_id")
    if value in (None, ""):
        return None
    return str(value)


def _browser_scope_mode() -> str:
    _init_state()
    mode = str(st.session_state.get("budget_browser_scope_mode", "filtered"))
    return mode if mode in {"filtered", "focused_filtered", "focused_all"} else "filtered"


def _clear_selected_listing() -> None:
    st.session_state["budget_selected_listing_id"] = None


def _reset_listing_page() -> None:
    st.session_state["budget_listing_page"] = 0


def _reset_ranking_page() -> None:
    st.session_state["budget_ranking_page"] = 0


def _reset_same_suburb_page() -> None:
    st.session_state["budget_same_suburb_page"] = 0


def _set_selected_listing_id(listing_id: str | None) -> None:
    if listing_id in (None, ""):
        _clear_selected_listing()
        _reset_same_suburb_page()
        return
    st.session_state["budget_selected_listing_id"] = str(listing_id)
    _reset_same_suburb_page()


def _set_selected_listing_callback(listing_id: str | None) -> None:
    _set_selected_listing_id(listing_id)


def _set_selected_suburb(suburb: str) -> None:
    if st.session_state.get("budget_selected_suburb", "__ALL__") != suburb:
        _clear_selected_listing()
        _reset_listing_page()
        _reset_same_suburb_page()
    st.session_state["budget_selected_suburb"] = suburb
    st.session_state["budget_browser_scope_mode"] = "filtered" if suburb == "__ALL__" else "focused_filtered"


def _set_browser_scope_mode(mode: str) -> None:
    normalized = mode if mode in {"filtered", "focused_filtered", "focused_all"} else "filtered"
    if st.session_state.get("budget_browser_scope_mode", "filtered") != normalized:
        _reset_listing_page()
    st.session_state["budget_browser_scope_mode"] = normalized


def _set_panel_listing_callback(listing_id: str, suburb: str) -> None:
    if suburb:
        _set_selected_suburb(suburb)
    _set_selected_listing_id(listing_id)


def _shift_budget_listing_page(delta: int, total_pages: int) -> None:
    current = int(st.session_state.get("budget_listing_page", 0))
    st.session_state["budget_listing_page"] = max(0, min(max(total_pages - 1, 0), current + delta))


def _shift_budget_ranking_page(delta: int, total_pages: int) -> None:
    current = int(st.session_state.get("budget_ranking_page", 0))
    st.session_state["budget_ranking_page"] = max(0, min(max(total_pages - 1, 0), current + delta))


def _shift_budget_same_suburb_page(delta: int, total_pages: int) -> None:
    current = int(st.session_state.get("budget_same_suburb_page", 0))
    st.session_state["budget_same_suburb_page"] = max(0, min(max(total_pages - 1, 0), current + delta))


def _listing_locate_help(selected_suburb: str, row_suburb: str, has_coordinates: bool) -> str:
    if not has_coordinates:
        return tr("该房源暂无可用坐标。", "This listing does not have usable coordinates yet.")
    if selected_suburb == "__ALL__":
        return tr("点击后将聚焦该 suburb 并在地图上定位房源。", "Click to focus that suburb and place this listing on the map.")
    if selected_suburb == row_suburb:
        return tr("点击后将地图定位到这套房源。", "Click to locate this listing on the map.")
    return tr("点击后将切换 suburb 聚焦并定位该房源。", "Click to switch suburb focus and locate this listing.")


def _clear_suburb_focus() -> None:
    _set_selected_suburb("__ALL__")
    _clear_selected_listing()
    _reset_listing_page()
    _reset_same_suburb_page()
    st.session_state["budget_focus_notice"] = None


def _handle_view_all_in_focused_suburb() -> None:
    _set_browser_scope_mode("focused_all")


def _handle_adjust_filters() -> None:
    _clear_suburb_focus()
    _set_browser_scope_mode("filtered")


def _reset_ranking_filters() -> None:
    st.session_state["budget_pending_ranking_reset"] = True


def _apply_pending_ranking_filter_reset() -> None:
    if not st.session_state.pop("budget_pending_ranking_reset", False):
        return
    st.session_state["budget_ranking_search"] = ""
    st.session_state["budget_ranking_min_listings"] = 1
    _reset_ranking_page()


def _set_map_view(center: dict[str, float] | None, zoom: float | None) -> None:
    st.session_state["budget_map_view"] = {"center": center, "zoom": zoom}


def _default_budget_filters(min_budget: int, max_budget: int) -> dict[str, object]:
    return {
        "budget_min": min_budget,
        "budget_max": max_budget,
        "selected_suburbs": [],
        "selected_postcodes": [],
        "selected_property_groups": [],
        "selected_property_subtypes": [],
        "commute_query": "",
        "commute_mode": "drive",
        "commute_minutes": 30,
        "min_bedrooms": 0,
        "min_bathrooms": 0,
        "min_parking": 0,
        "exact_bedrooms": False,
        "exact_bathrooms": False,
        "exact_parking": False,
        "selected_sort": tr("价格从低到高", "Price low to high"),
        "show_subtypes": False,
    }


def _merge_filter_defaults(saved: dict[str, object] | None, min_budget: int, max_budget: int) -> dict[str, object]:
    merged = _default_budget_filters(min_budget, max_budget)
    if saved:
        merged.update(saved)
    merged["budget_min"] = _normalise_budget_value(int(merged["budget_min"]), min_budget, max_budget)
    merged["budget_max"] = _normalise_budget_value(int(merged["budget_max"]), min_budget, max_budget)
    merged["selected_sort"] = _coerce_buy_sort_key(merged.get("selected_sort"))
    if merged["budget_min"] > merged["budget_max"]:
        merged["budget_min"], merged["budget_max"] = min_budget, max_budget
    return merged


def _buy_sort_labels() -> dict[str, str]:
    return {
        "price_asc": tr("价格从低到高", "Price low to high"),
        "price_desc": tr("价格从高到低", "Price high to low"),
        "newest": tr("最新房源", "Newest listing"),
        "bedrooms_desc": tr("卧室数", "Bedrooms"),
        "suburb_asc": tr("Suburb", "Suburb"),
    }


def _coerce_buy_sort_key(value: object) -> str:
    current = str(value or "").strip()
    if current in BUY_SORT_SPECS:
        return current
    reverse = {label: key for key, label in _buy_sort_labels().items()}
    legacy_map = {
        "Price low to high": "price_asc",
        "价格从低到高": "price_asc",
        "Price high to low": "price_desc",
        "价格从高到低": "price_desc",
        "Newest listing": "newest",
        "最新房源": "newest",
        "Bedrooms": "bedrooms_desc",
        "卧室数": "bedrooms_desc",
        "Suburb": "suburb_asc",
    }
    return reverse.get(current) or legacy_map.get(current, "price_asc")


def _buy_sort_label(sort_key: object) -> str:
    return _buy_sort_labels().get(_coerce_buy_sort_key(sort_key), _buy_sort_labels()["price_asc"])


def _set_budget_draft_from_filters(filters: dict[str, object], *, overwrite: bool = False) -> None:
    for key, value in filters.items():
        state_key = f"budget_draft_{key}"
        if overwrite or state_key not in st.session_state:
            st.session_state[state_key] = value
    if overwrite or "budget_draft_min_input" not in st.session_state:
        st.session_state["budget_draft_min_input"] = _format_budget_input(int(filters["budget_min"]))
    if overwrite or "budget_draft_max_input" not in st.session_state:
        st.session_state["budget_draft_max_input"] = _format_budget_input(int(filters["budget_max"]))
    if overwrite or "budget_draft_range_slider" not in st.session_state:
        st.session_state["budget_draft_range_slider"] = (int(filters["budget_min"]), int(filters["budget_max"]))


def _init_budget_filter_state(min_budget: int, max_budget: int) -> None:
    applied = _merge_filter_defaults(st.session_state.get("budget_applied_filters"), min_budget, max_budget)
    st.session_state["budget_applied_filters"] = applied
    _set_budget_draft_from_filters(_merge_filter_defaults(st.session_state.get("budget_applied_filters"), min_budget, max_budget))


def _sync_external_buy_widget_state_from_applied(applied: dict[str, object], external_budget_options: list[int]) -> None:
    st.session_state["budget_selected_suburbs"] = list(applied.get("selected_suburbs", []))
    st.session_state["budget_selected_postcodes"] = list(applied.get("selected_postcodes", []))
    st.session_state["budget_min_bedrooms"] = int(applied.get("min_bedrooms", 0))
    st.session_state["budget_min_bathrooms"] = int(applied.get("min_bathrooms", 0))
    st.session_state["budget_min_parking"] = int(applied.get("min_parking", 0))
    st.session_state["budget_exact_bedrooms"] = bool(applied.get("exact_bedrooms", False))
    st.session_state["budget_exact_bathrooms"] = bool(applied.get("exact_bathrooms", False))
    st.session_state["budget_exact_parking"] = bool(applied.get("exact_parking", False))
    st.session_state["budget_show_subtypes"] = bool(applied.get("show_subtypes", False))
    st.session_state["budget_selected_sort"] = _coerce_buy_sort_key(applied.get("selected_sort"))
    st.session_state["budget_commute_query"] = str(applied.get("commute_query", ""))
    st.session_state["budget_commute_mode"] = str(applied.get("commute_mode", "drive"))
    st.session_state["budget_commute_minutes"] = int(applied.get("commute_minutes", 30))
    st.session_state["budget_selected_property_groups"] = list(applied.get("selected_property_groups", []))
    st.session_state["budget_selected_sort"] = _coerce_buy_sort_key(st.session_state.get("budget_selected_sort"))
    st.session_state["budget_external_applied_range"] = _coerce_external_budget_range(
        (int(applied.get("budget_min", 0)), int(applied.get("budget_max", 10_000_000))),
        options=external_budget_options,
        default_range=(0, 10_000_000),
    )


def _initialise_external_buy_widget_state_from_applied(applied: dict[str, object], external_budget_options: list[int]) -> None:
    widget_defaults = {
        "budget_selected_suburbs": list(applied.get("selected_suburbs", [])),
        "budget_selected_postcodes": list(applied.get("selected_postcodes", [])),
        "budget_min_bedrooms": int(applied.get("min_bedrooms", 0)),
        "budget_min_bathrooms": int(applied.get("min_bathrooms", 0)),
        "budget_min_parking": int(applied.get("min_parking", 0)),
        "budget_exact_bedrooms": bool(applied.get("exact_bedrooms", False)),
        "budget_exact_bathrooms": bool(applied.get("exact_bathrooms", False)),
        "budget_exact_parking": bool(applied.get("exact_parking", False)),
        "budget_show_subtypes": bool(applied.get("show_subtypes", False)),
        "budget_selected_sort": str(applied.get("selected_sort", tr("价格从低到高", "Price low to high"))),
        "budget_commute_query": str(applied.get("commute_query", "")),
        "budget_commute_mode": str(applied.get("commute_mode", "drive")),
        "budget_commute_minutes": int(applied.get("commute_minutes", 30)),
        "budget_selected_property_groups": list(applied.get("selected_property_groups", [])),
    }
    for key, value in widget_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    st.session_state["budget_selected_sort"] = _coerce_buy_sort_key(st.session_state.get("budget_selected_sort"))
    st.session_state["budget_external_applied_range"] = _coerce_external_budget_range(
        (int(applied.get("budget_min", 0)), int(applied.get("budget_max", 10_000_000))),
        options=external_budget_options,
        default_range=(0, 10_000_000),
    )


def _reset_external_buy_filters(min_budget: int, max_budget: int, external_budget_options: list[int]) -> None:
    defaults = _merge_filter_defaults({}, min_budget, max_budget)
    st.session_state["budget_applied_filters"] = defaults
    st.session_state["budget_pending_reset"] = True
    st.session_state["buy_external_search_triggered"] = False


def _apply_pending_external_buy_reset(external_budget_options: list[int]) -> None:
    if not st.session_state.pop("budget_pending_reset", False):
        return
    defaults = _merge_filter_defaults(st.session_state.get("budget_applied_filters"), 0, 10_000_000)
    _sync_external_buy_widget_state_from_applied(defaults, external_budget_options)
    for key in list(st.session_state.keys()):
        if key.startswith("budget_subtypes_"):
            del st.session_state[key]
    st.session_state["budget_selected_group_labels"] = []
    st.session_state["budget_commute_notice"] = None
    st.session_state["budget_group_notice"] = None
    st.session_state["budget_focus_notice"] = None
    st.session_state["budget_selected_suburb"] = "__ALL__"


def _format_applied_threshold(label: str, value: int, *, exact: bool) -> str:
    suffix = f"{value}" if exact else f"{value}+"
    return f"{label}: {suffix}"


def _format_applied_commute_summary(filters: dict[str, object]) -> str | None:
    commute_label = str(filters.get("commute_label", "") or "").strip()
    if commute_label:
        return commute_label

    commute_query = str(filters.get("commute_query", "") or "").strip()
    if not commute_query:
        return None

    commute_mode = str(filters.get("commute_mode", "drive") or "drive")
    commute_minutes = int(filters.get("commute_minutes", 30) or 30)
    return _format_commute_chip(mode=commute_mode, max_minutes=commute_minutes, label=commute_query)


def _valid_selected(values: list[str] | None, valid_options: list[str]) -> list[str]:
    valid_set = set(valid_options)
    return [value for value in (values or []) if value in valid_set]


def _build_shortlist_df(df: pd.DataFrame) -> pd.DataFrame:
    shortlist_ids = _get_shortlist_ids()
    shortlist_df = df.loc[df["listing_id"].astype(str).isin(shortlist_ids)].copy()
    current_ids = set(shortlist_df["listing_id"].astype(str).tolist())
    stored_items = st.session_state.get("budget_shortlist_items", {})
    missing_rows = [stored_items[item_id] for item_id in shortlist_ids if item_id not in current_ids and item_id in stored_items]
    if missing_rows:
        shortlist_df = pd.concat([shortlist_df, pd.DataFrame(missing_rows)], ignore_index=True, sort=False)
    if shortlist_df.empty:
        return shortlist_df
    return shortlist_df.drop_duplicates(subset=["listing_id"], keep="first")


def _collect_budget_draft_filters(
    *,
    min_budget: int,
    max_budget: int,
    selected_sort: str,
    group_options: list[str],
    subtype_options: dict[str, list[str]],
) -> dict[str, object]:
    parsed_min = _parse_budget_input(st.session_state.get("budget_draft_min_input"))
    parsed_max = _parse_budget_input(st.session_state.get("budget_draft_max_input"))
    slider_min, slider_max = st.session_state.get("budget_draft_range_slider", (min_budget, max_budget))

    budget_min = slider_min if parsed_min is None else _normalise_budget_value(parsed_min, min_budget, max_budget)
    budget_max = slider_max if parsed_max is None else _normalise_budget_value(parsed_max, min_budget, max_budget)
    if budget_min > budget_max:
        budget_min, budget_max = slider_min, slider_max

    selected_groups = _valid_selected(st.session_state.get("budget_draft_selected_property_groups"), group_options)
    selected_subtypes: list[str] = []
    for group, options in subtype_options.items():
        selected_subtypes.extend(_valid_selected(st.session_state.get(f"budget_draft_subtypes_{group}"), options))

    return {
        "budget_min": budget_min,
        "budget_max": budget_max,
        "selected_suburbs": list(st.session_state.get("budget_draft_selected_suburbs", [])),
        "selected_postcodes": list(st.session_state.get("budget_draft_selected_postcodes", [])),
        "selected_property_groups": selected_groups,
        "selected_property_subtypes": sorted(set(selected_subtypes)),
        "min_bedrooms": int(st.session_state.get("budget_draft_min_bedrooms", 0)),
        "min_bathrooms": int(st.session_state.get("budget_draft_min_bathrooms", 0)),
        "min_parking": int(st.session_state.get("budget_draft_min_parking", 0)),
        "exact_bedrooms": bool(st.session_state.get("budget_draft_exact_bedrooms", False)),
        "exact_bathrooms": bool(st.session_state.get("budget_draft_exact_bathrooms", False)),
        "exact_parking": bool(st.session_state.get("budget_draft_exact_parking", False)),
        "selected_sort": selected_sort,
        "show_subtypes": bool(st.session_state.get("budget_draft_show_subtypes", False)),
    }


def _full_budget_selected(current_min: int, current_max: int, absolute_min: int, absolute_max: int) -> bool:
    return current_min == absolute_min and current_max == absolute_max


def _normalise_suburb_key(value: str | None) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).upper().strip()
    text = re.sub(r"\([^)]*\)", "", text)
    text = text.replace("-", " ")
    text = text.replace("&", " AND ")
    text = text.replace("'", "")
    text = re.sub(r"\bMT\b", "MOUNT", text)
    text = re.sub(r"\bNSW\b", "", text)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = " ".join(text.split())
    return SUBURB_JOIN_ALIASES.get(text, text)


def _flatten_coords(node) -> list[tuple[float, float]]:
    if not isinstance(node, list) or not node:
        return []
    first = node[0]
    if isinstance(first, (int, float)) and len(node) >= 2:
        return [(float(node[0]), float(node[1]))]
    points: list[tuple[float, float]] = []
    for item in node:
        points.extend(_flatten_coords(item))
    return points


def _geometry_centroid(geometry: dict | None) -> tuple[float | None, float | None]:
    if not geometry:
        return None, None
    coords = _flatten_coords(geometry.get("coordinates"))
    if not coords:
        return None, None
    lon = sum(point[0] for point in coords) / len(coords)
    lat = sum(point[1] for point in coords) / len(coords)
    return lat, lon


def _simplify_ring(coords: list, step: int) -> list:
    if len(coords) <= 8 or step <= 1:
        return coords
    body = coords[:-1]
    simplified = body[::step]
    if body and simplified[-1] != body[-1]:
        simplified.append(body[-1])
    if simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    return simplified if len(simplified) >= 4 else coords


def _simplify_geometry_coords(node):
    if not isinstance(node, list) or not node:
        return node
    first = node[0]
    if isinstance(first, (int, float)):
        return node
    if first and isinstance(first[0], (int, float)):
        ring_len = len(node)
        if ring_len > 1400:
            return _simplify_ring(node, 8)
        if ring_len > 700:
            return _simplify_ring(node, 5)
        if ring_len > 300:
            return _simplify_ring(node, 3)
        if ring_len > 120:
            return _simplify_ring(node, 2)
        return node
    return [_simplify_geometry_coords(item) for item in node]


@st.cache_data(show_spinner=False)
def _load_suburb_boundaries() -> dict[str, object]:
    base_dir = Path(__file__).resolve().parents[1]
    abs_dir = base_dir / "Reference" / "ABS"
    candidates = [abs_dir / "nsw_suburbs.geojson"]
    if abs_dir.exists():
        candidates.extend(sorted(abs_dir.glob("*suburb*.geojson")))
        candidates.extend(sorted(abs_dir.glob("*Suburb*.geojson")))

    field_candidates = [
        "join_key",
        "suburb_name",
        "suburb",
        "Suburb",
        "suburb_name",
        "suburbnam",
        "SSC_NAME21",
        "SSC_NAME16",
        "nsw_loca_2",
        "LOC_NAME",
        "name",
        "NAME",
    ]

    for path in candidates:
        if not path.exists():
            continue

        payload = json.loads(path.read_text(encoding="utf-8"))
        features = payload.get("features", [])
        if not isinstance(features, list) or not features:
            continue
        render_features = []

        sample_properties = features[0].get("properties", {})
        feature_name_field = next((field for field in field_candidates if field in sample_properties), None)
        if feature_name_field is None:
            feature_name_field = next(
                (
                    field
                    for field, value in sample_properties.items()
                    if isinstance(value, str) and "suburb" in field.lower()
                ),
                None,
            )
        if feature_name_field is None:
            continue

        polygon_rows = []
        for feature_idx, feature in enumerate(features):
            properties = feature.setdefault("properties", {})
            suburb_name = properties.get(feature_name_field)
            suburb_key = properties.get("join_key") or _normalise_suburb_key(suburb_name)
            if not suburb_key:
                continue
            # `join_key` is derived from ABS `SAL_NAME21` during GeoJSON export.
            properties["join_key"] = suburb_key
            properties["__budget_suburb_key"] = suburb_key
            properties["feature_id"] = str(properties.get("feature_id") or properties.get("suburb_code") or feature_idx)
            if feature.get("geometry"):
                render_features.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "feature_id": properties["feature_id"],
                            "__budget_suburb_key": suburb_key,
                            "join_key": suburb_key,
                            "suburb_name": str(properties.get("suburb_name") or suburb_name).strip(),
                        },
                        "geometry": {
                            "type": feature["geometry"]["type"],
                            "coordinates": _simplify_geometry_coords(feature["geometry"]["coordinates"]),
                        },
                    }
                )
            lat, lon = _geometry_centroid(feature.get("geometry"))
            polygon_rows.append(
                {
                    "feature_id": properties["feature_id"],
                    "geo_suburb_key": suburb_key,
                    "boundary_suburb_name": str(properties.get("suburb_name") or suburb_name).strip(),
                    "boundary_latitude": lat,
                    "boundary_longitude": lon,
                }
            )
        polygon_df = pd.DataFrame(polygon_rows)
        centroid_df = (
            polygon_df.groupby("geo_suburb_key", dropna=False)
            .agg(
                boundary_suburb_name=("boundary_suburb_name", "first"),
                boundary_latitude=("boundary_latitude", "mean"),
                boundary_longitude=("boundary_longitude", "mean"),
            )
            .reset_index()
        )
        return {
            "available": True,
            "path": str(path),
            "geojson": {"type": "FeatureCollection", "features": render_features},
            "centroids": centroid_df,
            "polygons": polygon_df,
        }

    return {
        "available": False,
        "path": str(abs_dir / "nsw_suburbs.geojson"),
        "geojson": None,
        "centroids": pd.DataFrame(
            columns=["geo_suburb_key", "boundary_suburb_name", "boundary_latitude", "boundary_longitude"]
        ),
        "polygons": pd.DataFrame(
            columns=["feature_id", "geo_suburb_key", "boundary_suburb_name", "boundary_latitude", "boundary_longitude"]
        ),
    }


@st.cache_data(show_spinner=False)
def _prepare_choropleth_payload(summary_records: tuple[tuple, ...], polygon_records: tuple[tuple, ...]) -> dict[str, object]:
    summary = pd.DataFrame(
        summary_records,
        columns=[
            "suburb",
            "geo_suburb_key",
            "listing_count",
            "within_budget_count",
            "total_priced_listings",
            "unknown_price_count",
            "median_asking_price",
            "coverage_ratio",
        ],
    )
    polygons = pd.DataFrame(polygon_records, columns=["feature_id", "geo_suburb_key"])
    if summary.empty or polygons.empty:
        return {"frame": pd.DataFrame(), "score_stats": {}}

    choropleth_df = summary.merge(polygons, on="geo_suburb_key", how="inner").copy()
    if choropleth_df.empty:
        return {"frame": choropleth_df, "score_stats": {}}

    choropleth_df["color_score"] = choropleth_df["coverage_ratio"].fillna(0.0).clip(0.0, 1.0)

    return {
        "frame": choropleth_df,
        "score_stats": {
            "min": float(choropleth_df["coverage_ratio"].min()),
            "max": float(choropleth_df["coverage_ratio"].max()),
        },
    }


def _render_filter_chips(selected_property_groups, selected_property_subtypes, selected_suburbs, selected_postcodes, min_bedrooms, min_bathrooms, min_parking, commute_label: str | None = None) -> None:
    chips = []
    if selected_property_groups:
        chips.append(f"{tr('大类', 'Group')}: {len(selected_property_groups)}")
    if selected_property_subtypes:
        chips.append(f"{tr('细分类', 'Subtypes')}: {len(set(selected_property_subtypes))}")
    if selected_suburbs:
        chips.append(f"{tr('Suburb', 'Suburb')}: {len(selected_suburbs)}")
    if selected_postcodes:
        chips.append(f"{tr('邮编', 'Postcode')}: {len(selected_postcodes)}")
    if min_bedrooms:
        bedroom_mode = tr("精确", "Exact") if st.session_state.get("budget_exact_bedrooms", False) else "+"
        chips.append(f"{tr('卧室', 'Beds')} {min_bedrooms}{'' if bedroom_mode != '+' else '+'}" if bedroom_mode == "+" else f"{tr('卧室', 'Beds')} = {min_bedrooms}")
    if min_bathrooms:
        bathroom_mode = tr("精确", "Exact") if st.session_state.get("budget_exact_bathrooms", False) else "+"
        chips.append(f"{tr('卫生间', 'Baths')} {min_bathrooms}{'' if bathroom_mode != '+' else '+'}" if bathroom_mode == "+" else f"{tr('卫生间', 'Baths')} = {min_bathrooms}")
    if min_parking:
        parking_mode = tr("精确", "Exact") if st.session_state.get("budget_exact_parking", False) else "+"
        chips.append(f"{tr('车位', 'Parking')} {min_parking}{'' if parking_mode != '+' else '+'}" if parking_mode == "+" else f"{tr('车位', 'Parking')} = {min_parking}")
    if commute_label:
        chips.append(commute_label)
    if not chips:
        chips.append(tr("当前为宽筛选模式", "Currently using a broad search"))
    st.markdown("".join(f"<span class='budget-chip'>{item}</span>" for item in chips), unsafe_allow_html=True)


def _apply_budget_filters(
    df: pd.DataFrame,
    *,
    budget_min: int,
    budget_max: int,
    min_budget: int,
    max_budget: int,
    selected_property_groups: list[str] | None = None,
    selected_property_subtypes: list[str] | None = None,
    selected_suburbs: list[str] | None = None,
    selected_postcodes: list[str] | None = None,
    min_bedrooms: int = 0,
    min_bathrooms: int = 0,
    min_parking: int = 0,
    exact_bedrooms: bool = False,
    exact_bathrooms: bool = False,
    exact_parking: bool = False,
    allowed_listing_ids: list[str] | set[str] | None = None,
    allowed_suburbs: list[str] | None = None,
    include_budget: bool = True,
    skip_filters: set[str] | None = None,
) -> tuple[pd.DataFrame, list[tuple[str, int]]]:
    skip_filters = skip_filters or set()
    frames: list[tuple[str, int]] = [("loaded", int(len(df)))]
    filtered = df.copy()

    if include_budget:
        full_budget_selected = _full_budget_selected(budget_min, budget_max, min_budget, max_budget)
        budget_contained = (
            filtered["has_price"]
            & (filtered["price_filter_min"] >= budget_min)
            & (filtered["price_filter_max"] <= budget_max)
        )
        filtered = filtered.loc[budget_contained | (full_budget_selected & ~filtered["has_price"])].copy()
    frames.append(("after_budget", int(len(filtered))))

    if selected_suburbs and "suburb" not in skip_filters:
        filtered = filtered.loc[filtered["suburb"].isin(selected_suburbs)].copy()
    frames.append(("after_suburb", int(len(filtered))))

    if selected_postcodes and "postcode" not in skip_filters:
        filtered = filtered.loc[filtered["postcode"].isin(selected_postcodes)].copy()
    frames.append(("after_postcode", int(len(filtered))))

    if allowed_listing_ids is not None and "commute" not in skip_filters:
        allowed_listing_ids = {str(value) for value in allowed_listing_ids}
        filtered = filtered.loc[filtered["listing_id"].astype(str).isin(allowed_listing_ids)].copy()
    elif allowed_suburbs is not None and "commute" not in skip_filters:
        filtered = filtered.loc[filtered["suburb"].isin(allowed_suburbs)].copy()
    frames.append(("after_commute", int(len(filtered))))

    if min_bedrooms and "bedrooms" not in skip_filters:
        comparator = filtered["bedrooms"].fillna(-1) == min_bedrooms if exact_bedrooms else filtered["bedrooms"].fillna(-1) >= min_bedrooms
        filtered = filtered.loc[comparator].copy()
    frames.append(("after_bedrooms", int(len(filtered))))

    if min_bathrooms and "bathrooms" not in skip_filters:
        comparator = filtered["bathrooms"].fillna(-1) == min_bathrooms if exact_bathrooms else filtered["bathrooms"].fillna(-1) >= min_bathrooms
        filtered = filtered.loc[comparator].copy()
    frames.append(("after_bathrooms", int(len(filtered))))

    if min_parking and "parking" not in skip_filters:
        comparator = filtered["parking"].fillna(-1) == min_parking if exact_parking else filtered["parking"].fillna(-1) >= min_parking
        filtered = filtered.loc[comparator].copy()
    frames.append(("after_parking", int(len(filtered))))

    if selected_property_groups and "property_group" not in skip_filters:
        filtered = filtered.loc[filtered["property_group"].isin(selected_property_groups)].copy()
    frames.append(("after_property_group", int(len(filtered))))

    if selected_property_subtypes and "property_subtype" not in skip_filters:
        filtered = filtered.loc[filtered["property_subtype"].isin(sorted(set(selected_property_subtypes)))].copy()
    frames.append(("after_property_subtype", int(len(filtered))))

    return filtered, frames


def _budget_signal_label(coverage_ratio: float, listing_count: int) -> str:
    if listing_count <= 3 or coverage_ratio < 0.20:
        return tr("预算偏紧", "Budget is tight")
    if listing_count <= 12 or coverage_ratio < 0.55:
        return tr("预算适中", "Budget is balanced")
    return tr("预算较宽裕", "Budget is comfortable")


def _budget_status_from_distribution(priced: pd.DataFrame, budget_max: int) -> tuple[str, float]:
    if priced.empty:
        return tr("预算适中", "Budget is balanced"), 0.0
    prices = pd.to_numeric(priced["price_mid"], errors="coerce").dropna()
    if prices.empty:
        return tr("预算适中", "Budget is balanced"), 0.0
    coverage_ratio = float((prices <= float(budget_max)).mean())
    p50 = float(prices.quantile(0.50))
    p80 = float(prices.quantile(0.80))
    p95 = float(prices.quantile(0.95))
    if coverage_ratio >= 0.85 or budget_max >= p95:
        return tr("预算较宽裕", "Budget is comfortable"), coverage_ratio
    if coverage_ratio >= 0.45 or budget_max >= p50 or budget_max >= p80 * 0.9:
        return tr("预算适中", "Budget is balanced"), coverage_ratio
    return tr("预算偏紧", "Budget is tight"), coverage_ratio


def _budget_insight(filtered: pd.DataFrame, context_df: pd.DataFrame, budget_max: int, *, focused_suburb: str) -> dict:
    priced = filtered.loc[filtered["has_price"]].copy()
    context_priced = context_df.loc[context_df["has_price"]].copy()
    typical = priced["price_mid"].median() if not priced.empty else pd.NA
    listing_count = int(len(filtered))
    suburb_count = int(filtered["suburb"].dropna().nunique())
    signal_label, coverage_ratio = _budget_status_from_distribution(context_priced, budget_max)

    suburb_prices = (
        priced.groupby("suburb", dropna=False)["price_mid"]
        .median()
        .dropna()
        .sort_values()
    ) if not priced.empty else pd.Series(dtype=float)
    most_affordable_suburb = str(suburb_prices.index[0]) if not suburb_prices.empty else "N/A"

    stretch_pool = context_df.loc[
        context_df["has_price"]
        & (context_df["price_filter_min"] > budget_max)
        & (context_df["price_filter_min"] <= budget_max * 1.10)
    ].copy()
    plus_5 = stretch_pool.loc[stretch_pool["price_filter_min"] <= budget_max * 1.05]
    current_suburbs = set(filtered["suburb"].dropna().astype(str))
    new_suburbs = sorted(set(stretch_pool["suburb"].dropna().astype(str)) - current_suburbs)[:6]
    uplift_note = None
    if len(stretch_pool) > 0:
        uplift_note = (
            tr(f"预算上调 5% 可新增 {len(plus_5)} 套，10% 可新增 {len(stretch_pool)} 套。", f"A 5% stretch unlocks {len(plus_5)} extra listings and a 10% stretch unlocks {len(stretch_pool)}.")
            if len(plus_5) > 0 or len(stretch_pool) > 0
            else tr("预算上调对新增房源影响有限。", "Stretching the budget is unlikely to unlock many more listings.")
        )

    if focused_suburb != "__ALL__":
        conclusion = tr(
            f"当前聚焦 suburb 内共有 {listing_count} 套匹配房源，主流为 {_title_case_subtype(_mode_or_na(filtered['property_subtype']))}，预算状态为{signal_label}。",
            f"The focused suburb has {listing_count} matching listings, led by { _title_case_subtype(_mode_or_na(filtered['property_subtype'])) }, with a budget position of {signal_label}.",
        )
    else:
        conclusion = tr(
            f"当前筛选下覆盖 {suburb_count} 个 suburb，共 {listing_count} 套匹配房源，主流为 {_title_case_subtype(_mode_or_na(filtered['property_subtype']))}，预算状态为{signal_label}。",
            f"The current scope covers {suburb_count} suburbs and {listing_count} matching listings, led by { _title_case_subtype(_mode_or_na(filtered['property_subtype'])) }, with an overall budget position of {signal_label}.",
        )

    return {
        "typical_price": typical,
        "signal_label": signal_label,
        "coverage_ratio": coverage_ratio,
        "suburb_count": suburb_count,
        "listing_count": listing_count,
        "common_type": _title_case_subtype(_mode_or_na(filtered["property_subtype"])),
        "common_bedrooms": _mode_or_na(filtered["bedrooms"]),
        "common_bathrooms": _mode_or_na(filtered["bathrooms"]),
        "most_affordable_suburb": most_affordable_suburb,
        "plus_5": int(len(plus_5)),
        "plus_10": int(len(stretch_pool)),
        "new_suburbs": new_suburbs,
        "uplift_note": uplift_note,
        "conclusion": conclusion,
    }


@st.cache_data(show_spinner=False)
def _coverage_universe_scope(
    df: pd.DataFrame,
    *,
    selected_property_groups: tuple[str, ...] = (),
    selected_property_subtypes: tuple[str, ...] = (),
) -> pd.DataFrame:
    universe = df.copy()
    if selected_property_groups:
        universe = universe.loc[universe["property_group"].isin(list(selected_property_groups))].copy()
    if selected_property_subtypes:
        universe = universe.loc[universe["property_subtype"].isin(list(selected_property_subtypes))].copy()
    return universe


@st.cache_data(show_spinner=False)
def _suburb_summary(
    universe_df: pd.DataFrame,
    matched_df: pd.DataFrame,
    *,
    budget_min: int,
    budget_max: int,
) -> pd.DataFrame:
    universe_scope = universe_df.loc[universe_df["suburb"].notna()].copy()
    if universe_scope.empty:
        return pd.DataFrame()

    matched_scope = matched_df.loc[matched_df["suburb"].notna()].copy()

    universe_scope["priced_listing"] = universe_scope["has_price"].fillna(False).astype(int)
    universe_scope["unknown_price"] = (~universe_scope["has_price"].fillna(False)).astype(int)
    universe_summary = (
        universe_scope.groupby("suburb", dropna=False)
        .agg(
            total_listings_count=("listing_id", "count"),
            total_priced_listings=("priced_listing", "sum"),
            unknown_price_count=("unknown_price", "sum"),
            latitude=("latitude", "median"),
            longitude=("longitude", "median"),
            coordinate_count=("has_coordinates", "sum"),
        )
        .reset_index()
    )

    if matched_scope.empty:
        matched_summary = universe_summary[["suburb"]].copy()
        matched_summary["listing_count"] = 0
        matched_summary["within_budget_count"] = 0
        matched_summary["priced_listings_count"] = 0
        matched_summary["median_asking_price"] = pd.NA
        matched_summary["common_property_type"] = pd.NA
        matched_summary["common_bedrooms"] = pd.NA
    else:
        matched_scope["within_budget"] = (
            matched_scope["has_price"].fillna(False)
            & (matched_scope["price_filter_min"] <= budget_max)
            & (matched_scope["price_filter_max"] >= budget_min)
        )
        matched_scope["priced_listing"] = matched_scope["has_price"].fillna(False).astype(int)
        matched_summary = (
            matched_scope.groupby("suburb", dropna=False)
            .agg(
                listing_count=("listing_id", "count"),
                median_asking_price=("price_mid", "median"),
                common_property_type=("property_subtype", _mode_or_na),
                common_bedrooms=("bedrooms", _mode_or_na),
                within_budget_count=("within_budget", "sum"),
                priced_listings_count=("priced_listing", "sum"),
            )
            .reset_index()
        )

    summary = universe_summary.merge(matched_summary, on="suburb", how="left")
    summary["geo_suburb_key"] = summary["suburb"].map(_normalise_suburb_key)
    summary["listing_count"] = pd.to_numeric(summary["listing_count"], errors="coerce").fillna(0).astype(int)
    summary["within_budget_count"] = pd.to_numeric(summary["within_budget_count"], errors="coerce").fillna(0).astype(int)
    summary["priced_listings_count"] = pd.to_numeric(summary["priced_listings_count"], errors="coerce").fillna(0).astype(int)
    summary["coordinate_ratio"] = (summary["coordinate_count"] / summary["total_listings_count"]).fillna(0.0).clip(0.0, 1.0)
    summary["coverage_ratio"] = (
        pd.to_numeric(summary["listing_count"], errors="coerce")
        / pd.to_numeric(summary["total_listings_count"], errors="coerce").replace({0: pd.NA})
    ).fillna(0.0).clip(0.0, 1.0)
    summary["unknown_price_ratio"] = (summary["unknown_price_count"] / summary["total_listings_count"]).fillna(0.0).clip(0.0, 1.0)
    summary["heatmap_score"] = summary["coverage_ratio"]
    summary["heatmap_value"] = summary["listing_count"].astype(float)
    summary["heatmap_label"] = tr("Budget coverage", "Budget coverage")
    summary["coverage_label"] = pd.cut(
        summary["coverage_ratio"],
        bins=[-0.01, 0.0, 0.25, 0.50, 0.75, 1.0],
        labels=[
            tr("No coverage", "No coverage"),
            tr("Low coverage", "Low coverage"),
            tr("Moderate coverage", "Moderate coverage"),
            tr("High coverage", "High coverage"),
            tr("Very high coverage", "Very high coverage"),
        ],
    ).astype(str)
    summary["availability_label"] = summary["listing_count"].map(lambda x: _availability_level(int(x))[0])
    summary["availability_colour"] = summary["listing_count"].map(lambda x: _availability_level(int(x))[1])
    return summary.sort_values(
        ["coverage_ratio", "within_budget_count", "total_priced_listings", "median_asking_price", "suburb"],
        ascending=[False, False, False, True, True],
        na_position="last",
    ).reset_index(drop=True)


def _render_suburb_ranking(summary: pd.DataFrame) -> None:
    if summary.empty:
        st.info(tr("当前筛选条件下没有可用 suburb。", "No suburbs are available under the current filters."))
        return

    focused_suburb = _selected_suburb()
    total_available = len(summary.loc[summary["listing_count"] > 0].copy())
    controls = st.columns([1.9, 1.0, 1.0])
    with controls[0]:
        search_value = st.text_input(
            tr("Search suburb", "Search suburb"),
            key="budget_ranking_search",
            placeholder=tr("Type part of a suburb name", "Type part of a suburb name"),
        ).strip()
    min_listings = int(st.session_state.get("budget_ranking_min_listings", 1))
    reset_col = controls[1]
    focus_col = controls[2]
    with reset_col:
        if st.button(tr("Reset ranking filters", "Reset ranking filters"), use_container_width=True):
            _reset_ranking_filters()
            st.rerun()
    with focus_col:
        if focused_suburb != "__ALL__" and st.button(tr("Reset suburb focus", "Reset suburb focus"), use_container_width=True):
            _clear_suburb_focus()
            st.rerun()

    ranking = summary.copy()
    ranking = ranking.loc[ranking["listing_count"] > 0].copy()
    if search_value:
        ranking = ranking.loc[ranking["suburb"].astype(str).str.contains(search_value, case=False, na=False)].copy()
    ranking = ranking.sort_values(
        ["coverage_ratio", "within_budget_count", "total_priced_listings", "median_asking_price", "suburb"],
        ascending=[False, False, False, True, True],
        na_position="last",
    ).reset_index(drop=True)

    shown_count = len(ranking)
    st.caption(tr(f"显示 {shown_count:,} / {total_available:,} 个 suburb", f"Showing {shown_count:,} of {total_available:,} suburbs"))
    st.caption(
        tr(
            f"当前聚焦 suburb: {focused_suburb if focused_suburb != '__ALL__' else '无'}",
            f"Focused suburb: {focused_suburb if focused_suburb != '__ALL__' else 'None'}",
        )
    )

    if ranking.empty:
        st.warning(tr(f"排名筛选后可显示 0 / {total_available:,} 个 suburb。", f"Showing 0 of {total_available:,} suburbs after ranking filters."))
        return

    total_pages = max(1, math.ceil(len(ranking) / EXTERNAL_RANKING_PAGE_SIZE))
    current_page = min(int(st.session_state.get("budget_ranking_page", 0)), total_pages - 1)
    st.session_state["budget_ranking_page"] = current_page
    start = current_page * EXTERNAL_RANKING_PAGE_SIZE
    end = start + EXTERNAL_RANKING_PAGE_SIZE
    view = ranking.iloc[start:end].copy()
    view[tr("聚焦", "Focus")] = view["suburb"].eq(focused_suburb).map({True: tr("已聚焦", "Focused"), False: ""})
    view[tr("覆盖率", "Coverage")] = (view["coverage_ratio"] * 100).round().astype(int).astype(str) + "%"
    view[tr("预算内", "Within Budget")] = view["within_budget_count"].astype(int)
    view[tr("有报价", "Priced Listings")] = view["priced_listings_count"].astype(int)
    view[tr("总挂牌", "Total Listings")] = view["total_listings_count"].astype(int)
    view[tr("中位标价", "Median Price")] = view["median_asking_price"].map(_compact_price)

    _render_external_suburb_ranking_table(
        view.assign(**{"suburb": view["suburb"]}),
        focused_suburb=focused_suburb,
        key_prefix="budget_ranking",
    )
    pager_cols = st.columns([1, 1.3, 1])
    pager_cols[0].button(
        tr("上一页", "Previous"),
        key="budget_ranking_prev",
        use_container_width=True,
        disabled=current_page <= 0,
        on_click=_shift_budget_ranking_page,
        args=(-1, total_pages),
    )
    with pager_cols[1]:
        st.caption(tr(f"第 {current_page + 1} / {total_pages} 页", f"Page {current_page + 1} of {total_pages}"))
    pager_cols[2].button(
        tr("下一页", "Next"),
        key="budget_ranking_next",
        use_container_width=True,
        disabled=current_page >= total_pages - 1,
        on_click=_shift_budget_ranking_page,
        args=(1, total_pages),
    )
    return


def _resolve_map_selection(event_state) -> dict[str, str] | None:
    if event_state is None:
        return None
    selection = getattr(event_state, "selection", None)
    if selection is None and isinstance(event_state, dict):
        selection = event_state.get("selection")
    if not selection:
        return None
    points = getattr(selection, "points", None)
    if points is None and isinstance(selection, dict):
        points = selection.get("points")
    if not points:
        return None
    point = points[0]
    customdata = point.get("customdata") if isinstance(point, dict) else getattr(point, "customdata", None)
    if not isinstance(customdata, (list, tuple)) or len(customdata) < 2:
        return None
    kind = str(customdata[1]).strip()
    suburb = str(customdata[0]).strip()
    if kind == "suburb" and suburb:
        return {"kind": "suburb", "suburb": suburb}
    if kind == "listing" and len(customdata) >= 5:
        listing_id = str(customdata[4]).strip()
        if suburb and listing_id:
            return {"kind": "listing", "suburb": suburb, "listing_id": listing_id}
    return None


def _resolve_map_view(map_summary: pd.DataFrame, map_df: pd.DataFrame, selected_suburb: str) -> tuple[dict[str, float] | None, float]:
    boundaries = _load_suburb_boundaries()
    center, zoom = resolve_budget_map_view(
        selected_suburb=selected_suburb,
        suburb_key=_normalise_suburb_key(selected_suburb) if selected_suburb != "__ALL__" else None,
        map_summary=map_summary,
        map_df=map_df,
        boundary_geojson=boundaries.get("geojson"),
    )
    center, zoom = clamp_to_nsw_map_view(center, zoom)
    st.session_state["budget_map_focus_token"] = selected_suburb
    _set_map_view(center, zoom)
    return center, zoom


def _build_map(filtered: pd.DataFrame, suburb_summary: pd.DataFrame, selected_suburb: str) -> str:
    map_slot = st.empty()
    map_df = filtered.loc[filtered["has_coordinates"]].copy()
    boundaries = _load_suburb_boundaries()
    map_summary = suburb_summary.copy()
    selected_listing_id = _selected_listing_id()

    if map_df.empty and map_summary.empty:
        st.info(tr("当前筛选结果没有可用坐标，地图暂时无法显示。", "No coordinates are available for the current filters."))
        return selected_suburb

    centroids = boundaries["centroids"]
    polygon_links = boundaries["polygons"]
    if not centroids.empty:
        map_summary = map_summary.merge(centroids, on="geo_suburb_key", how="left")
        map_summary["map_latitude"] = map_summary["boundary_latitude"].fillna(map_summary["latitude"])
        map_summary["map_longitude"] = map_summary["boundary_longitude"].fillna(map_summary["longitude"])
    else:
        map_summary["map_latitude"] = map_summary["latitude"]
        map_summary["map_longitude"] = map_summary["longitude"]

    map_summary = map_summary.loc[map_summary["map_latitude"].notna() & map_summary["map_longitude"].notna()].copy()
    focus_points = map_df.loc[map_df["suburb"] == selected_suburb].copy() if selected_suburb != "__ALL__" else pd.DataFrame()
    center, zoom = _resolve_map_view(map_summary, map_df, selected_suburb)

    if True:
        summary_hash = int(pd.util.hash_pandas_object(map_summary[["suburb", "listing_count", "coverage_ratio", "total_listings_count"]], index=False).sum()) if not map_summary.empty else 0
        point_hash = int(pd.util.hash_pandas_object(map_df[["listing_id", "suburb", "latitude", "longitude"]], index=False).sum()) if not map_df.empty else 0
        map_signature = ("buy_external", selected_suburb, selected_listing_id or "", summary_hash, point_hash)
        if st.session_state.get("budget_external_map_signature") == map_signature and st.session_state.get("budget_external_map_figure") is not None:
            fig = st.session_state["budget_external_map_figure"]
            sampled = bool(st.session_state.get("budget_external_map_sampled", False))
            event_state = map_slot.plotly_chart(
                fig,
                width="stretch",
                config={"displayModeBar": False, "responsive": True, "scrollZoom": True},
                key="budget_map_chart",
                on_select="rerun",
                selection_mode="points",
            )
            map_selection = _resolve_map_selection(event_state)
            if map_selection:
                if map_selection["kind"] == "suburb" and map_selection["suburb"] != selected_suburb:
                    _set_selected_suburb(map_selection["suburb"])
                    return map_selection["suburb"]
                if map_selection["kind"] == "listing" and map_selection["listing_id"] != (_selected_listing_id() or ""):
                    _set_selected_suburb(map_selection["suburb"])
                    _set_selected_listing_id(map_selection["listing_id"])
                    return map_selection["suburb"]
            if sampled:
                st.caption(tr(f"当前地图中的房源点位仅展示前 {EXTERNAL_MAX_MARKERS} 条，以保持 External 页面响应速度。", f"Listing markers are capped to the first {EXTERNAL_MAX_MARKERS} results in External mode to keep the page responsive."))
            return selected_suburb
    if True:
        fig = go.Figure()
        sampled = False

        if boundaries["available"] and boundaries["geojson"] is not None:
            background_feature_ids = [str(feature["properties"].get("feature_id")) for feature in boundaries["geojson"].get("features", [])]
            if background_feature_ids:
                fig.add_trace(
                    go.Choroplethmapbox(
                        geojson=boundaries["geojson"],
                        locations=background_feature_ids,
                        z=[0] * len(background_feature_ids),
                        featureidkey="properties.feature_id",
                        zmin=0,
                        zmax=1,
                        colorscale=[[0.0, "#ece8e1"], [1.0, "#ece8e1"]],
                        marker_opacity=0.10,
                        marker_line_width=0.6,
                        marker_line_color="rgba(120, 120, 120, 0.30)",
                        hoverinfo="skip",
                        showscale=False,
                        showlegend=False,
                        name=tr("NSW suburb context", "NSW suburb context"),
                        below="",
                    )
                )
            choropleth_df = map_summary.merge(polygon_links[["feature_id", "geo_suburb_key"]], on="geo_suburb_key", how="inner").copy()
            if not choropleth_df.empty:
                if selected_suburb != "__ALL__":
                    background_df = choropleth_df.loc[choropleth_df["suburb"] != selected_suburb].copy()
                    active_df = choropleth_df.loc[choropleth_df["suburb"] == selected_suburb].copy()
                else:
                    background_df = pd.DataFrame(columns=choropleth_df.columns)
                    active_df = choropleth_df

                if not background_df.empty:
                    background_ids = set(background_df["feature_id"].astype(str).tolist())
                    background_geojson = {
                        "type": "FeatureCollection",
                        "features": [feature for feature in boundaries["geojson"]["features"] if str(feature["properties"].get("feature_id")) in background_ids],
                    }
                    fig.add_trace(
                        go.Choroplethmapbox(
                            geojson=background_geojson,
                            locations=background_df["feature_id"],
                            z=background_df["coverage_ratio"].fillna(0.0).clip(0.0, 1.0),
                            featureidkey="properties.feature_id",
                            zmin=0,
                            zmax=1,
                            colorscale=[[0.0, "#e7e5e4"], [0.20, "#d6d3d1"], [0.50, "#cfe2b3"], [0.75, "#7fbf7b"], [1.0, "#1f7a4d"]],
                            marker_opacity=0.12,
                            marker_line_width=0.7,
                            marker_line_color="rgba(88, 76, 64, 0.22)",
                            hoverinfo="skip",
                            showscale=False,
                            showlegend=False,
                            name=tr("Other suburbs", "Other suburbs"),
                            below="",
                        )
                    )

                active_ids = set(active_df["feature_id"].astype(str).tolist())
                active_geojson = {
                    "type": "FeatureCollection",
                    "features": [feature for feature in boundaries["geojson"]["features"] if str(feature["properties"].get("feature_id")) in active_ids],
                }
                fig.add_trace(
                    go.Choroplethmapbox(
                        geojson=active_geojson,
                        locations=active_df["feature_id"],
                        z=active_df["coverage_ratio"].fillna(0.0).clip(0.0, 1.0),
                        featureidkey="properties.feature_id",
                        zmin=0,
                        zmax=1,
                        colorscale=[[0.0, "#e7e5e4"], [0.20, "#d6d3d1"], [0.50, "#cfe2b3"], [0.75, "#7fbf7b"], [1.0, "#1f7a4d"]],
                        marker_opacity=0.78 if selected_suburb == "__ALL__" else 0.24,
                        marker_line_width=2.4 if selected_suburb != "__ALL__" else 1.0,
                        marker_line_color="#182230" if selected_suburb != "__ALL__" else "rgba(83, 63, 46, 0.55)",
                        customdata=list(zip(active_df["suburb"], active_df["coverage_ratio"], active_df["listing_count"], active_df["total_listings_count"], active_df["median_asking_price"].map(_compact_price))),
                        hovertemplate=(
                            "<b>%{customdata[0]}</b><br>"
                            + tr("Coverage", "Coverage") + ": %{customdata[1]:.0%}<br>"
                            + tr("Matching listings", "Matching listings") + ": %{customdata[2]:,.0f}<br>"
                            + tr("Total listings", "Total listings") + ": %{customdata[3]:,.0f}<br>"
                            + tr("Median price", "Median price") + ": %{customdata[4]}<extra></extra>"
                        ),
                        colorbar=dict(title=tr("Coverage", "Coverage"), thickness=8, x=0.985, y=0.52, len=0.32, tickvals=[0.0, 0.5, 1.0], ticktext=["0%", "50%", "100%"], bgcolor="rgba(255,255,255,0.82)", outlinewidth=0),
                        showscale=True,
                        showlegend=False,
                        name=tr("Suburb coverage", "Suburb coverage"),
                        below="",
                    )
                )

        sampled = False
        if selected_suburb != "__ALL__" and not focus_points.empty:
            focus_points = focus_points.sort_values(by=["price_mid", "listing_date"], ascending=[True, False], na_position="last")
            selected_point = focus_points.loc[focus_points["listing_id"].astype(str) == selected_listing_id].head(1).copy()
            if not selected_point.empty:
                center = {
                    "lat": float(selected_point.iloc[0]["latitude"]),
                    "lon": float(selected_point.iloc[0]["longitude"]),
                }
                zoom = max(float(zoom), 14.2)
            if len(focus_points) > EXTERNAL_MAX_MARKERS:
                focus_points = focus_points.head(EXTERNAL_MAX_MARKERS)
                if not selected_point.empty and selected_point.iloc[0]["listing_id"] not in set(focus_points["listing_id"].tolist()):
                    focus_points = pd.concat([selected_point, focus_points.head(EXTERNAL_MAX_MARKERS - 1)], ignore_index=True, sort=False)
                    focus_points = focus_points.drop_duplicates(subset=["listing_id"], keep="first")
                sampled = True
            fig.add_trace(
                go.Scattermapbox(
                    lat=focus_points["latitude"],
                    lon=focus_points["longitude"],
                    mode="markers",
                    name=tr("Other listings", "Other listings"),
                    marker=dict(size=8, color="#0d5ea6", opacity=0.88),
                    customdata=list(zip(focus_points["suburb"], ["listing"] * len(focus_points), focus_points["price_display"], focus_points["bedrooms"], focus_points["bathrooms"], focus_points["listing_id"].astype(str))),
                    text=focus_points["address"].fillna(""),
                    hovertemplate=(
                        "<b>%{text}</b><br>"
                        + tr("Suburb", "Suburb") + ": %{customdata[0]}<br>"
                        + tr("Price", "Price") + ": %{customdata[2]}<br>"
                        + tr("Beds/Baths", "Beds/Baths") + ": %{customdata[3]} / %{customdata[4]}<extra></extra>"
                    ),
                )
            )
            if not selected_point.empty:
                fig.add_trace(
                    go.Scattermapbox(
                        lat=selected_point["latitude"],
                        lon=selected_point["longitude"],
                        mode="markers",
                        name=tr("Selected listing", "Selected listing"),
                        marker=dict(size=12, color="#d97706", opacity=0.96),
                        customdata=list(zip(selected_point["suburb"], ["listing"] * len(selected_point), selected_point["price_display"], selected_point["bedrooms"], selected_point["bathrooms"], selected_point["listing_id"].astype(str))),
                        text=selected_point["address"].fillna(""),
                        hovertemplate=(
                            "<b>%{text}</b><br>"
                            + tr("Suburb", "Suburb") + ": %{customdata[0]}<br>"
                            + tr("Price", "Price") + ": %{customdata[2]}<br>"
                            + tr("Beds/Baths", "Beds/Baths") + ": %{customdata[3]} / %{customdata[4]}<extra></extra>"
                        ),
                    )
                )
        fig.update_layout(
            height=MAP_HEIGHT,
            margin={"l": 0, "r": 0, "t": 0, "b": 0},
            mapbox=dict(style="carto-positron", center=center, zoom=zoom, bounds=NSW_MAP_BOUNDS),
            legend=dict(orientation="h", yanchor="top", y=0.985, xanchor="left", x=0.02, bgcolor="rgba(255,255,255,0.82)"),
            showlegend=selected_suburb != "__ALL__" and not focus_points.empty,
            uirevision=f"budget-map-{selected_suburb}",
        )
        if st.session_state.get("budget_external_map_signature") != map_signature:
            st.session_state["budget_external_map_signature"] = map_signature
            st.session_state["budget_external_map_figure"] = fig
            st.session_state["budget_external_map_sampled"] = sampled
        event_state = map_slot.plotly_chart(
            fig,
            width="stretch",
            config={"displayModeBar": False, "responsive": True, "scrollZoom": True},
            key="budget_map_chart",
            on_select="rerun",
            selection_mode="points",
        )
        map_selection = _resolve_map_selection(event_state)
        if map_selection:
            if map_selection["kind"] == "suburb" and map_selection["suburb"] != selected_suburb:
                _set_selected_suburb(map_selection["suburb"])
                return map_selection["suburb"]
            if map_selection["kind"] == "listing" and map_selection["listing_id"] != (_selected_listing_id() or ""):
                _set_selected_suburb(map_selection["suburb"])
                _set_selected_listing_id(map_selection["listing_id"])
                return map_selection["suburb"]
        if sampled:
            st.caption(tr(f"当前地图中的房源点位仅展示前 {EXTERNAL_MAX_MARKERS} 条，以保持 External 页面响应速度。", f"Listing markers are capped to the first {EXTERNAL_MAX_MARKERS} results in External mode to keep the page responsive."))
        return selected_suburb

    polygon_count = 0
    joined_suburbs = 0
    unmatched_examples: list[str] = []
    join_rate = 0.0
    choropleth_ready = False
    score_stats = {}
    unresolved_unmatched: list[str] = []
    ignorable_unmatched: list[str] = []
    locality_unmatched: list[str] = []

    if boundaries["available"] and boundaries["geojson"] is not None:
        polygon_count = len(boundaries["geojson"].get("features", []))
        if not map_summary.empty and "boundary_suburb_name" in map_summary.columns:
            joined_suburbs = int(map_summary["boundary_suburb_name"].notna().sum())
            join_rate = joined_suburbs / max(len(map_summary), 1)
            unmatched_examples = (
                map_summary.loc[map_summary["boundary_suburb_name"].isna(), "suburb"]
                .astype(str)
                .drop_duplicates()
                .head(6)
                .tolist()
            )
            unresolved_unmatched = [name for name in unmatched_examples if _normalise_suburb_key(name) not in IGNORABLE_SUBURB_KEYS and _normalise_suburb_key(name) not in LOCALITY_VARIANT_KEYS]
            ignorable_unmatched = [name for name in unmatched_examples if _normalise_suburb_key(name) in IGNORABLE_SUBURB_KEYS]
            locality_unmatched = [name for name in unmatched_examples if _normalise_suburb_key(name) in LOCALITY_VARIANT_KEYS]
            choropleth_ready = join_rate >= 0.95 and joined_suburbs > 0

    if boundaries["available"] and boundaries["geojson"] is not None:
        background_feature_ids = [str(feature["properties"].get("feature_id")) for feature in boundaries["geojson"].get("features", [])]
        if background_feature_ids:
            fig.add_trace(
                go.Choroplethmapbox(
                    geojson=boundaries["geojson"],
                    locations=background_feature_ids,
                    z=[0] * len(background_feature_ids),
                    featureidkey="properties.feature_id",
                    zmin=0,
                    zmax=1,
                    colorscale=[[0.0, "#d9d9d9"], [1.0, "#d9d9d9"]],
                    marker_opacity=0.10,
                    marker_line_width=0.6,
                    marker_line_color="rgba(120, 120, 120, 0.35)",
                    hoverinfo="skip",
                    showscale=False,
                    name=tr("NSW suburb context", "NSW suburb context"),
                    below="",
                )
            )

    if choropleth_ready and not map_summary.empty:
        prep = _prepare_choropleth_payload(
            tuple(
                map_summary[
                    [
                        "suburb",
                        "geo_suburb_key",
                        "listing_count",
                        "within_budget_count",
                        "total_priced_listings",
                        "unknown_price_count",
                        "median_asking_price",
                        "coverage_ratio",
                    ]
                ].itertuples(index=False, name=None)
            ),
            tuple(polygon_links[["feature_id", "geo_suburb_key"]].itertuples(index=False, name=None)),
        )
        choropleth_df = prep["frame"]
        score_stats = prep["score_stats"]
        active_feature_ids = set(choropleth_df["feature_id"].astype(str).tolist())
        active_geojson = {
            "type": "FeatureCollection",
            "features": [feature for feature in boundaries["geojson"]["features"] if str(feature["properties"].get("feature_id")) in active_feature_ids],
        }
        fig.add_trace(
            go.Choroplethmapbox(
                geojson=active_geojson,
                locations=choropleth_df["feature_id"],
                z=choropleth_df["color_score"],
                featureidkey="properties.feature_id",
                zmin=0,
                zmax=1,
                colorscale=[[0.0, "#eeeeee"], [0.25, "#ffe08a"], [0.50, "#a6d96a"], [0.75, "#4daf4a"], [1.0, "#1a9850"]],
                marker_opacity=0.72,
                marker_line_width=1.0,
                marker_line_color="rgba(83, 63, 46, 0.55)",
                customdata=list(
                    zip(
                        choropleth_df["suburb"],
                        choropleth_df["coverage_ratio"],
                        choropleth_df["within_budget_count"],
                        choropleth_df["total_priced_listings"],
                    )
                ),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    + tr("Coverage", "Coverage") + ": %{customdata[1]:.0%}<br>"
                    + tr("Within budget", "Within budget") + ": %{customdata[2]:,.0f}<br>"
                    + tr("Total listings", "Total listings") + ": %{customdata[3]:,.0f}<extra></extra>"
                ),
                colorbar=dict(
                    title=tr("Coverage", "Coverage"),
                    tickvals=[0.0, 0.25, 0.5, 0.75, 1.0],
                    ticktext=["0%", "25%", "50%", "75%", "100%"],
                    len=0.55,
                ),
                name=tr("Suburb coverage", "Suburb coverage"),
                below="",
            )
        )
        if selected_suburb != "__ALL__":
            highlight_df = choropleth_df.loc[choropleth_df["suburb"] == selected_suburb]
            if not highlight_df.empty:
                fig.add_trace(
                    go.Choroplethmapbox(
                        geojson=active_geojson,
                        locations=highlight_df["feature_id"],
                        z=[1] * len(highlight_df),
                        featureidkey="properties.feature_id",
                        zmin=0,
                        zmax=1,
                        colorscale=[[0.0, "rgba(0,0,0,0)"], [1.0, "rgba(0,0,0,0)"]],
                        marker_opacity=0.0,
                        marker_line_width=2.6,
                        marker_line_color="#182230",
                        hoverinfo="skip",
                        showscale=False,
                        name=tr("当前聚焦 suburb", "Focused suburb"),
                    )
                )

    if not map_summary.empty:
        size_scale = 8 + 16 * (map_summary["listing_count"] / max(float(map_summary["listing_count"].max()), 1.0))
        fig.add_trace(
            go.Scattermapbox(
                lat=map_summary["map_latitude"],
                lon=map_summary["map_longitude"],
                mode="markers",
                name=tr("Suburb 选择点", "Suburb selector"),
                marker=dict(
                    size=size_scale.tolist(),
                    color=map_summary["suburb"].eq(selected_suburb).map({True: "#0f4c81", False: "#1d6f8c"}).tolist(),
                    opacity=0.72,
                ),
                customdata=list(zip(map_summary["suburb"], ["suburb"] * len(map_summary), map_summary["listing_count"])),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    + tr("匹配房源", "Matching listings") + ": %{customdata[2]:,.0f}<br>"
                    + tr("点击以聚焦 suburb", "Click to focus suburb")
                    + "<extra></extra>"
                ),
            )
        )

    sampled = False
    if selected_suburb != "__ALL__" and not focus_points.empty:
        focus_points = focus_points.sort_values(by=["price_mid", "listing_date"], ascending=[True, False], na_position="last")
        if len(focus_points) > 350:
            focus_points = focus_points.head(350)
            sampled = True
        fig.add_trace(
            go.Scattermapbox(
                lat=focus_points["latitude"],
                lon=focus_points["longitude"],
                mode="markers",
                name=tr("房源点位", "Listings"),
                marker=dict(size=9, color="#0d5ea6", opacity=0.88),
                customdata=list(zip(focus_points["suburb"], ["listing"] * len(focus_points), focus_points["price_display"])),
                text=focus_points["address"].fillna(""),
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    + tr("Suburb", "Suburb") + ": %{customdata[0]}<br>"
                    + tr("价格", "Price") + ": %{customdata[2]}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        height=MAP_HEIGHT,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        mapbox=dict(
            style="carto-positron",
            center=center,
            zoom=zoom,
            bounds=NSW_MAP_BOUNDS if True else None,
        ),
        legend=dict(orientation="h", yanchor="bottom", y=0.01, xanchor="left", x=0.01),
        uirevision=f"budget-map-{selected_suburb}",
    )

    event_state = map_slot.plotly_chart(
        fig,
        width="stretch",
        config={"displayModeBar": False, "responsive": True, "scrollZoom": True},
        key="budget_map_chart",
        on_select="rerun",
        selection_mode="points",
    )
    map_selection = _resolve_map_selection(event_state)
    if map_selection and map_selection["kind"] == "suburb" and map_selection["suburb"] != selected_suburb:
        _set_selected_suburb(map_selection["suburb"])
        st.rerun()

    if False:
        if not boundaries["available"]:
            st.caption(
                tr(
                    f"æœªæ‰¾åˆ°å®˜æ–¹ suburb è¾¹ç•Œæ–‡ä»¶ï¼Œå½“å‰ä½¿ç”¨ suburb ä¸­å¿ƒç‚¹æ›¿ä»£çƒ­åŠ›é¢ã€‚å¯å°† GeoJSON æ”¾å…¥ {boundaries['path']} ä»¥å¯ç”¨å®Œæ•´ choroplethã€‚",
                    f"Official suburb boundaries were not found, so the map is using suburb centroids instead of filled polygons. Add a GeoJSON at {boundaries['path']} to enable the full choropleth.",
                )
            )
        elif not choropleth_ready:
            st.warning(
                tr(
                    f"Suburb è¾¹ç•Œæ–‡ä»¶å·²åŠ è½½ï¼Œä½†å½“å‰ join è¦†ç›–ä¸è¶³ä»¥å®‰å…¨å¯ç”¨ choroplethã€‚NSW polygon: {polygon_count}ï¼Œlisting suburb: {len(map_summary)}ï¼ŒæˆåŠŸ join: {joined_suburbs}ã€‚æœªåŒ¹é…ç¤ºä¾‹ï¼š{', '.join(unmatched_examples) if unmatched_examples else 'N/A'}ã€‚",
                    f"The suburb boundary file loaded, but join coverage is too weak to safely enable the choropleth. NSW polygons: {polygon_count}, listing suburbs: {len(map_summary)}, successful joins: {joined_suburbs}. Unmatched examples: {', '.join(unmatched_examples) if unmatched_examples else 'N/A'}.",
                )
            )
        elif not map_summary.empty and "boundary_latitude" in map_summary.columns:
            st.caption(
                tr(
                    f"é¢œè‰²è¡¨ç¤ºå½“å‰ suburb é‡Œé¢„ç®—å†…æ ‡ä»·æˆ¿æºçš„å¤šå°‘ï¼šè¶Šç»¿ä»£è¡¨é¢„ç®—å†…é€‰æ‹©è¶Šå¤šï¼›è¶Šæµ…ä»£è¡¨é¢„ç®—å†…æ ‡ä»·æˆ¿æºæ›´å°‘ã€‚è‹¥ä¸€ä¸ª suburb æœ‰è¾ƒå¤šæœªå®šä»·æˆ¿æºï¼Œé¢œè‰²ä¼šæ›´ä¿å®ˆã€‚å½“å‰ join: {joined_suburbs}/{len(map_summary)}ï¼ˆ{join_rate:.0%}ï¼‰ï¼ŒæœªåŒ¹é…ç¤ºä¾‹ï¼š{', '.join(unmatched_examples) if unmatched_examples else 'æ— '}ã€‚",
                    f"Color shows how many priced in-budget options are available in each suburb: greener means more in-budget choice, lighter means fewer priced matches. If a suburb has many unknown-price listings, the color stays more conservative. Current join: {joined_suburbs}/{len(map_summary)} ({join_rate:.0%}), unmatched examples: {', '.join(unmatched_examples) if unmatched_examples else 'none'}.",
                )
            )
            if locality_unmatched or ignorable_unmatched or unresolved_unmatched:
                st.caption(
                    tr(
                        f"æœªåŒ¹é…åˆ†ç±»ï¼šåœ°åå˜ä½“ {', '.join(locality_unmatched) if locality_unmatched else 'æ— '}ï¼›å¯å¿½ç•¥ {', '.join(ignorable_unmatched) if ignorable_unmatched else 'æ— '}ï¼›ä»å¾…å¤„ç† {', '.join(unresolved_unmatched) if unresolved_unmatched else 'æ— '}ã€‚",
                        f"Unmatched classification: locality variants {', '.join(locality_unmatched) if locality_unmatched else 'none'}; ignorable {', '.join(ignorable_unmatched) if ignorable_unmatched else 'none'}; still unresolved {', '.join(unresolved_unmatched) if unresolved_unmatched else 'none'}.",
                    )
                )
        if sampled:
            st.caption(tr("当前 suburb 的房源点位最多展示 350 个更适合浏览的结果，以保持地图响应速度。", "Listing markers are capped to the first 350 browse-worthy results in the focused suburb to keep the map responsive."))

    return selected_suburb


def _listing_card(row: pd.Series, *, key_prefix: str) -> None:
    with st.container(border=True):
        if True:
            content_col = st.container()
            image_col = None
        else:
            content_col, image_col = st.columns([2.2, 1])
        with content_col:
            st.markdown(f"### {row['price_display']}")
            st.markdown(f"**{row['address']}**")
            st.caption(f"{row['suburb']} / {row['postcode']}")
            st.write(f"{tr('Type', 'Type')}: {row['property_group_label']} / {_title_case_subtype(row['property_subtype'])}")
            st.write(f"{tr('Beds/Baths/Parking', 'Beds/Baths/Parking')}: {_feature_triplet(row)}")
            st.write(f"{tr('Land size', 'Land size')}: {_land_size_label(row['land_size'])}")
            st.write(f"{tr('Agency', 'Agency')}: {row['agency_name'] if pd.notna(row['agency_name']) else 'N/A'}")
            action_cols = st.columns(1 if True else 2)
            with action_cols[0]:
                label = tr("移出 shortlist", "Remove") if str(row["listing_id"]) in _get_shortlist_ids() else tr("加入 shortlist", "Shortlist")
                if st.button(label, key=f"{key_prefix}_toggle_{row['listing_id']}", use_container_width=True):
                    _toggle_shortlist(str(row["listing_id"]), row)
                    st.rerun()
            if False:
                with action_cols[1]:
                    st.link_button(tr("打开房源", "Open listing"), row["url"], use_container_width=True)
        if image_col is not None and pd.notna(row["main_image"]):
            with image_col:
                st.image(row["main_image"], use_container_width=True)


def _external_listing_price_label(row: pd.Series) -> str:
    if bool(row.get("has_price")) and pd.notna(row.get("price_mid")):
        return _compact_price(row.get("price_mid"))
    display = str(row.get("price_display") or "").strip()
    return display if display else tr("Price on request", "Price on request")


def _compact_count_cell(value: object) -> str:
    text = _count_label(value)
    return "—" if text == "N/A" else text


def _external_sale_table_headers() -> list[str]:
    return [
        tr("价格", "Price"),
        tr("地址", "Address"),
        tr("区域 / 邮编", "Suburb / Postcode"),
        tr("类型", "Type"),
        tr("卧室", "Beds"),
        tr("卫浴", "Baths"),
        tr("车位", "Parking"),
        tr("土地", "Land"),
        tr("中介", "Agency"),
        tr("操作", "Action"),
    ]


def _render_external_sale_table(listings: pd.DataFrame, *, key_prefix: str, selected_suburb: str) -> None:
    widths = [1.0, 2.8, 1.5, 1.15, 0.55, 0.55, 0.65, 0.85, 1.2, 0.95]
    header_cols = st.columns(widths, gap="small")
    for col, label in zip(header_cols, _external_sale_table_headers()):
        col.markdown(f"<div class='budget-table-head'>{label}</div>", unsafe_allow_html=True)

    for _, row in listings.iterrows():
        cols = st.columns(widths, gap="small")
        price_text = _external_listing_price_label(row)
        address_text = row["address"] if pd.notna(row.get("address")) else "N/A"
        suburb_postcode = f"{row['suburb'] if pd.notna(row.get('suburb')) else '—'} / {row['postcode'] if pd.notna(row.get('postcode')) else '—'}"
        property_type = f"{row['property_group_label']} / {_title_case_subtype(row['property_subtype'])}"
        land_label = _land_size_label(row["land_size"])
        agency_label = row["agency_name"] if pd.notna(row.get("agency_name")) else tr("Contact agent", "Contact agent")
        row_suburb = str(row.get("suburb") or "").strip()
        locate_enabled = bool(row.get("has_coordinates", False)) and bool(row_suburb)
        locate_selected = str(row["listing_id"]) == _selected_listing_id()

        cols[0].markdown(f"<div class='budget-table-row'><div class='budget-table-cell budget-table-price'>{price_text}</div></div>", unsafe_allow_html=True)
        cols[1].button(address_text, key=f"{key_prefix}_locate_{row['listing_id']}", use_container_width=True, disabled=not locate_enabled, type="secondary" if locate_selected else "tertiary", help=_listing_locate_help(selected_suburb, row_suburb, bool(row.get("has_coordinates", False))), on_click=_set_panel_listing_callback if locate_enabled else None, args=(str(row["listing_id"]), row_suburb) if locate_enabled else None)
        cols[2].markdown(f"<div class='budget-table-row'><div class='budget-table-cell budget-table-muted'>{suburb_postcode}</div></div>", unsafe_allow_html=True)
        cols[3].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{property_type}</div></div>", unsafe_allow_html=True)
        cols[4].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{_compact_count_cell(row['bedrooms'])}</div></div>", unsafe_allow_html=True)
        cols[5].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{_compact_count_cell(row['bathrooms'])}</div></div>", unsafe_allow_html=True)
        cols[6].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{_compact_count_cell(row['parking'])}</div></div>", unsafe_allow_html=True)
        cols[7].markdown(f"<div class='budget-table-row'><div class='budget-table-cell budget-table-muted'>{'—' if land_label == 'N/A' else land_label}</div></div>", unsafe_allow_html=True)
        cols[8].markdown(f"<div class='budget-table-row'><div class='budget-table-cell budget-table-muted'>{agency_label}</div></div>", unsafe_allow_html=True)
        shortlisted = str(row["listing_id"]) in _get_shortlist_ids()
        action_label = tr("已选", "Saved") if shortlisted else tr("收藏", "Shortlist")
        cols[9].button(action_label, key=f"{key_prefix}_toggle_{row['listing_id']}", use_container_width=True, on_click=_toggle_shortlist_callback, args=(str(row["listing_id"]), _snapshot_listing(row)))

def _render_external_suburb_ranking_table(view: pd.DataFrame, *, focused_suburb: str, key_prefix: str) -> None:
    widths = [0.9, 1.6, 0.9, 1.0, 1.0, 1.0, 1.0]
    headers = [
        tr("操作", "Action"),
        tr("Suburb", "Suburb"),
        tr("覆盖率", "Coverage"),
        tr("预算内", "Within Budget"),
        tr("有报价", "Priced Listings"),
        tr("总挂牌", "Total Listings"),
        tr("中位标价", "Median Price"),
    ]
    header_cols = st.columns(widths, gap="small")
    for col, label in zip(header_cols, headers):
        col.markdown(f"<div class='budget-table-head'>{label}</div>", unsafe_allow_html=True)

    for _, row in view.iterrows():
        cols = st.columns(widths, gap="small")
        is_focused = str(row["suburb"]) == focused_suburb
        action_label = tr("已聚焦", "Focused") if is_focused else tr("聚焦", "Focus")
        cols[0].button(
            action_label,
            key=f"{key_prefix}_focus_{row['suburb']}",
            use_container_width=True,
            disabled=is_focused,
            on_click=_set_selected_suburb,
            args=(str(row["suburb"]),),
        )
        cols[1].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{row['suburb']}</div></div>", unsafe_allow_html=True)
        cols[2].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{row[tr('覆盖率', 'Coverage')]}</div></div>", unsafe_allow_html=True)
        cols[3].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{int(row[tr('预算内', 'Within Budget')]):,}</div></div>", unsafe_allow_html=True)
        cols[4].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{int(row[tr('有报价', 'Priced Listings')]):,}</div></div>", unsafe_allow_html=True)
        cols[5].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{int(row[tr('总挂牌', 'Total Listings')]):,}</div></div>", unsafe_allow_html=True)
        cols[6].markdown(f"<div class='budget-table-row'><div class='budget-table-cell budget-table-price'>{row[tr('中位标价', 'Median Price')]}</div></div>", unsafe_allow_html=True)


def _render_external_listing_row(row: pd.Series, *, key_prefix: str) -> None:
    with st.container():
        info_col, price_col, action_col = st.columns([4.6, 1.35, 1.55], gap="small")
        with info_col:
            st.markdown(
                f"""
                <div class="budget-list-row">
                  <div class="budget-list-address">{row['address'] if pd.notna(row.get('address')) else 'N/A'}</div>
                  <div class="budget-list-meta">
                    {row['suburb'] if pd.notna(row.get('suburb')) else 'N/A'} / {row['postcode'] if pd.notna(row.get('postcode')) else 'N/A'}<br>
                    {row['property_group_label']} / {_title_case_subtype(row['property_subtype'])} | {tr('Beds/Baths/Parking', 'Beds/Baths/Parking')}: {_feature_triplet(row)} | {tr('Land size', 'Land size')}: {_land_size_label(row['land_size'])}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with price_col:
            st.markdown(f"<div class='budget-list-price'>{_external_listing_price_label(row)}</div>", unsafe_allow_html=True)
            agency_label = row["agency_name"] if pd.notna(row.get("agency_name")) else tr("Contact agent", "Contact agent")
            st.markdown(f"<div class='budget-list-subprice'>{agency_label}</div>", unsafe_allow_html=True)
        with action_col:
            shortlisted = str(row["listing_id"]) in _get_shortlist_ids()
            label = tr("移出 shortlist", "Remove") if shortlisted else tr("加入 shortlist", "Shortlist")
            if st.button(label, key=f"{key_prefix}_toggle_{row['listing_id']}", use_container_width=True):
                _toggle_shortlist(str(row["listing_id"]), row)
                st.rerun()
            if False and pd.notna(row.get("url")):
                st.link_button(tr("打开房源", "Open listing"), row["url"], use_container_width=True)


def _prepare_external_display_listings(listings: pd.DataFrame, *, sort_column: str, sort_ascending: bool) -> pd.DataFrame:
    return order_external_sale_listing_display(
        listings,
        primary_sort_col=sort_column,
        primary_sort_ascending=sort_ascending,
    )


@st.cache_data(show_spinner=False)
def _protect_external_scope(
    sorted_listings: pd.DataFrame,
    suburb_summary: pd.DataFrame,
    *,
    focused_suburb: str,
    selected_listing_id: str | None,
) -> tuple[pd.DataFrame, dict[str, int | bool]]:
    protected = sorted_listings.copy()
    original_listing_count = int(len(protected))
    original_suburb_count = int(suburb_summary["suburb"].nunique()) if not suburb_summary.empty and "suburb" in suburb_summary.columns else 0
    top_suburbs = suburb_summary["suburb"].astype(str).dropna().tolist() if "suburb" in suburb_summary.columns else []
    if focused_suburb != "__ALL__" and focused_suburb in protected["suburb"].astype(str).tolist():
        top_suburbs = [focused_suburb] + [suburb for suburb in top_suburbs if suburb != focused_suburb]
    top_suburbs = top_suburbs[:EXTERNAL_MAX_SUBURBS]
    if top_suburbs:
        protected = protected.loc[protected["suburb"].astype(str).isin(top_suburbs)].copy()
    if len(protected) > EXTERNAL_MAX_LISTINGS:
        limited = protected.head(EXTERNAL_MAX_LISTINGS).copy()
        if selected_listing_id:
            selected_match = protected.loc[protected["listing_id"].astype(str) == str(selected_listing_id)].head(1).copy()
            if not selected_match.empty and str(selected_match.iloc[0]["listing_id"]) not in limited["listing_id"].astype(str).tolist():
                limited = pd.concat([selected_match, limited.head(EXTERNAL_MAX_LISTINGS - 1)], ignore_index=True, sort=False)
                limited = limited.drop_duplicates(subset=["listing_id"], keep="first").head(EXTERNAL_MAX_LISTINGS).copy()
        protected = limited
    metadata = {
        "original_listing_count": original_listing_count,
        "original_suburb_count": original_suburb_count,
        "limited_listing_count": int(len(protected)),
        "limited_suburb_count": int(protected["suburb"].dropna().nunique()) if "suburb" in protected.columns else 0,
        "is_limited": bool(original_listing_count > EXTERNAL_MAX_LISTINGS or original_suburb_count > EXTERNAL_MAX_SUBURBS),
    }
    return protected, metadata


def _selected_listing_row(listings: pd.DataFrame) -> pd.Series | None:
    selected_listing_id = _selected_listing_id()
    if not selected_listing_id or listings.empty:
        return None
    match = listings.loc[listings["listing_id"].astype(str) == selected_listing_id].head(1)
    if match.empty:
        return None
    return match.iloc[0]


def _street_view_api_key() -> str | None:
    secret_value = None
    try:
        secret_value = st.secrets.get("GOOGLE_MAPS_API_KEY")
    except Exception:
        secret_value = None
    key = secret_value or os.environ.get("GOOGLE_MAPS_API_KEY")
    return str(key).strip() if key else None


def _street_view_url(row: pd.Series) -> str | None:
    api_key = _street_view_api_key()
    latitude = pd.to_numeric(row.get("latitude"), errors="coerce")
    longitude = pd.to_numeric(row.get("longitude"), errors="coerce")
    if not api_key or pd.isna(latitude) or pd.isna(longitude):
        return None
    location = quote_plus(f"{float(latitude):.6f},{float(longitude):.6f}")
    return (
        "https://maps.googleapis.com/maps/api/streetview"
        f"?size={EXTERNAL_STREET_VIEW_SIZE}&location={location}&fov=80&pitch=0&key={api_key}"
    )


def _external_page_count(total_listings: int) -> int:
    if total_listings <= 0:
        return 1
    return min(EXTERNAL_MAX_PAGES, max(1, math.ceil(total_listings / EXTERNAL_PAGE_SIZE)))


def _set_panel_listing(row: pd.Series) -> None:
    suburb = str(row.get("suburb") or "").strip()
    if suburb:
        _set_selected_suburb(suburb)
    _set_selected_listing_id(str(row["listing_id"]))


@st.cache_data(show_spinner=False)
def _build_same_suburb_panel_rows(
    listings: pd.DataFrame,
    selected_suburb: str,
    selected_listing_id: str | None,
    ) -> tuple[pd.DataFrame, int]:
    if selected_suburb == "__ALL__" or listings.empty:
        return listings.head(0).copy(), 0
    same_suburb = listings.loc[listings["suburb"].astype(str) == str(selected_suburb)].copy()
    total_count = int(len(same_suburb))
    if selected_listing_id:
        same_suburb = same_suburb.loc[same_suburb["listing_id"].astype(str) != str(selected_listing_id)].copy()
    return same_suburb.copy(), total_count


def _render_external_same_suburb_section(
    listings: pd.DataFrame,
    selected_suburb: str,
    selected_listing_id: str | None,
    *,
    page_prefix: str,
) -> None:
    same_suburb_rows, total_count = _build_same_suburb_panel_rows(
        listings,
        selected_suburb=selected_suburb,
        selected_listing_id=selected_listing_id,
    )
    if selected_suburb == "__ALL__" or total_count <= 0:
        return
    heading = tr("当前筛选下该 suburb 的全部房源", "All listings in this suburb within current filters")
    st.markdown(
        f"<div class='budget-panel-eyebrow'>{heading}<span class='budget-panel-badge'>{total_count}</span></div>",
        unsafe_allow_html=True,
    )
    if same_suburb_rows.empty:
        st.caption(tr("当前已选房源是该 suburb 下本页唯一可切换房源。", "The selected listing is currently the only switchable listing for this suburb in scope."))
        return
    total_pages = max(1, math.ceil(len(same_suburb_rows) / EXTERNAL_SAME_SUBURB_PAGE_SIZE)) if not same_suburb_rows.empty else 1
    current_page = min(int(st.session_state.get("budget_same_suburb_page", 0)), total_pages - 1)
    st.session_state["budget_same_suburb_page"] = current_page
    start = current_page * EXTERNAL_SAME_SUBURB_PAGE_SIZE
    end = start + EXTERNAL_SAME_SUBURB_PAGE_SIZE
    page_rows = same_suburb_rows.iloc[start:end].copy()

    for _, row in page_rows.iterrows():
        st.markdown(
            f"""
            <div class="budget-mini-card">
              <div class="budget-mini-price">{_external_listing_price_label(row)}</div>
              <div class="budget-mini-address">{row['address'] if pd.notna(row.get('address')) else 'N/A'}</div>
              <div class="budget-mini-meta">
                {row['suburb'] if pd.notna(row.get('suburb')) else 'N/A'} / {row['postcode'] if pd.notna(row.get('postcode')) else 'N/A'}<br>
                {row['property_group_label']} / {_title_case_subtype(row['property_subtype'])} • {tr('Beds/Baths/Parking', 'Beds/Baths/Parking')}: {_feature_triplet(row)}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        action_cols = st.columns([1.15, 0.85])
        action_cols[0].button(
            tr("切换到这套并定位", "Switch to this one"),
            key=f"{page_prefix}_same_suburb_switch_{row['listing_id']}",
            use_container_width=True,
            on_click=_set_selected_listing_callback,
            args=(str(row["listing_id"]),),
        )
        shortlisted = str(row["listing_id"]) in _get_shortlist_ids()
        action_cols[1].button(
            tr("已选", "Saved") if shortlisted else tr("收藏", "Shortlist"),
            key=f"{page_prefix}_same_suburb_shortlist_{row['listing_id']}",
            use_container_width=True,
            on_click=_toggle_shortlist_callback,
            args=(str(row["listing_id"]), _snapshot_listing(row)),
        )
    if total_pages > 1:
        pager_cols = st.columns([1, 1.3, 1])
        pager_cols[0].button(
            tr("上一页", "Previous"),
            key=f"{page_prefix}_same_suburb_prev",
            use_container_width=True,
            disabled=current_page <= 0,
            on_click=_shift_budget_same_suburb_page,
            args=(-1, total_pages),
        )
        with pager_cols[1]:
            st.caption(tr(f"第 {current_page + 1} / {total_pages} 页", f"Page {current_page + 1} of {total_pages}"))
        pager_cols[2].button(
            tr("下一页", "Next"),
            key=f"{page_prefix}_same_suburb_next",
            use_container_width=True,
            disabled=current_page >= total_pages - 1,
            on_click=_shift_budget_same_suburb_page,
            args=(1, total_pages),
        )
    remaining = total_count - 1 - end
    if remaining > 0:
        st.caption(tr(f"当前筛选下该 suburb 还有 {remaining} 套房源未在此处展开。", f"{remaining} more in-scope listings from this suburb are not expanded here."))


def _render_external_listing_detail(
    row: pd.Series,
    listings: pd.DataFrame,
    selected_suburb: str,
) -> None:
    header_cols = st.columns([1, 1])
    with header_cols[0]:
        st.button(
            tr("返回列表", "Back to list"),
            key=f"buy_detail_back_{row['listing_id']}",
            use_container_width=True,
            on_click=_clear_selected_listing,
        )
    with header_cols[1]:
        is_extended = _is_extended_listing(row)
        shortlisted = str(row["listing_id"]) in _get_shortlist_ids()
        action_label = tr("Remove", "Remove") if shortlisted else tr("Shortlist", "Shortlist")
        if is_extended:
            st.button(
                tr("View only", "View only"),
                key=f"buy_detail_shortlist_{row['listing_id']}",
                use_container_width=True,
                disabled=True,
            )
        else:
            st.button(
                action_label,
                key=f"buy_detail_shortlist_{row['listing_id']}",
                use_container_width=True,
                on_click=_toggle_shortlist_callback,
                args=(str(row["listing_id"]), _snapshot_listing(row)),
            )
    st.markdown(f"<div class='budget-panel-eyebrow'>{tr('Focused suburb', 'Focused suburb')} / {_source_badge_for_row(row)}</div>", unsafe_allow_html=True)
    if _is_extended_listing(row):
        st.caption(EXTENDED_LISTING_CAPTION)
    st.markdown(f"<div class='budget-card-price'>{_external_listing_price_label(row)}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='budget-card-address'>{row['address'] if pd.notna(row.get('address')) else 'N/A'}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='budget-card-meta'>{row['suburb'] if pd.notna(row.get('suburb')) else 'N/A'} / {row['postcode'] if pd.notna(row.get('postcode')) else 'N/A'}</div>", unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="budget-fact-grid">
          <div class="budget-fact"><div class="budget-fact-label">{tr('Beds / Baths / Parking', 'Beds / Baths / Parking')}</div><div class="budget-fact-value">{_feature_triplet(row)}</div></div>
          <div class="budget-fact"><div class="budget-fact-label">{tr('Type', 'Type')}</div><div class="budget-fact-value">{row['property_group_label']} / {_title_case_subtype(row['property_subtype'])}</div></div>
          <div class="budget-fact"><div class="budget-fact-label">{tr('Agency', 'Agency')}</div><div class="budget-fact-value">{row['agency_name'] if pd.notna(row.get('agency_name')) else 'N/A'}</div></div>
          <div class="budget-fact"><div class="budget-fact-label">{tr('Land size', 'Land size')}</div><div class="budget-fact-value">{_land_size_label(row['land_size'])}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if pd.notna(row.get("main_image")):
        st.image(row["main_image"], use_container_width=True)
    street_view_url = _street_view_url(row)
    if street_view_url:
        st.image(street_view_url, use_container_width=True)
    else:
        st.caption(tr("街景仅在已配置 Google Static API 时显示。", "Street view appears only when a Google Static API key is configured."))
    st.markdown("<div class='budget-panel-footer'>", unsafe_allow_html=True)
    _render_external_same_suburb_section(listings, selected_suburb=selected_suburb, selected_listing_id=str(row["listing_id"]), page_prefix="buy")
    st.markdown("</div>", unsafe_allow_html=True)


def _render_external_listing_panel(listings: pd.DataFrame, selected_suburb: str, metadata: dict[str, int | bool]) -> None:
    if listings.empty:
        st.info(tr("当前 suburb / 筛选条件下没有房源。", "No listings match the current suburb or filters."))
        return
    selected_row = _selected_listing_row(listings)
    scope_label = selected_suburb if selected_suburb != "__ALL__" else tr("全部匹配房源", "All matching listings")
    scope_eyebrow = tr("当前聚焦 suburb", "Focused suburb") if selected_suburb != "__ALL__" else tr("当前列表范围", "Current listing scope")
    st.markdown(
        f"""
        <div class="budget-panel-summary">
          <div class="budget-panel-eyebrow">{scope_eyebrow}</div>
          <div class="budget-panel-title">{scope_label}<span class="budget-panel-badge">{len(listings):,}</span></div>
          <div class="budget-panel-subtitle">{tr('右侧列表与详情均基于当前筛选范围。', 'The list and detail panel use the current filtered scope.')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if bool(metadata.get("is_limited")):
        st.warning(tr("请收窄筛选条件。当前仅展示受保护的顶部结果。", "Please refine your filters. Only protected top results are shown right now."))
        st.caption(tr("显示顶部结果 — 请细化筛选条件", "Showing top results — refine filters"))
    if selected_row is not None:
        with st.container(height=EXTERNAL_PANEL_BODY_HEIGHT):
            _render_external_listing_detail(selected_row, listings, selected_suburb)
        return

    total_pages = _external_page_count(len(listings))
    current_page = min(int(st.session_state.get("budget_listing_page", 0)), total_pages - 1)
    st.session_state["budget_listing_page"] = current_page
    start = current_page * EXTERNAL_PAGE_SIZE
    end = min(start + EXTERNAL_PAGE_SIZE, len(listings))
    with st.container(height=EXTERNAL_PANEL_BODY_HEIGHT):
        for _, row in listings.iloc[start:end].copy().iterrows():
            st.markdown(
                f"""
                <div class="budget-card">
                  <div class="budget-card-price">{_external_listing_price_label(row)}</div>
                  <div class="budget-card-address">{row['address'] if pd.notna(row.get('address')) else 'N/A'}</div>
                  <div class="budget-card-meta">
                    {row['suburb'] if pd.notna(row.get('suburb')) else 'N/A'} / {row['postcode'] if pd.notna(row.get('postcode')) else 'N/A'}<br>
                    {row['property_group_label']} / {_title_case_subtype(row['property_subtype'])} • {tr('Beds/Baths/Parking', 'Beds/Baths/Parking')}: {_feature_triplet(row)}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            row_cols = st.columns([1.18, 0.82])
            row_cols[0].button(
                tr("查看详情并定位", "View details and locate"),
                key=f"budget_panel_view_{row['listing_id']}",
                use_container_width=True,
                on_click=_set_panel_listing_callback,
                args=(str(row["listing_id"]), str(row.get("suburb") or "")),
            )
            shortlisted = str(row["listing_id"]) in _get_shortlist_ids()
            row_cols[1].button(
                tr("已选", "Saved") if shortlisted else tr("收藏", "Shortlist"),
                key=f"budget_panel_shortlist_{row['listing_id']}",
                use_container_width=True,
                on_click=_toggle_shortlist_callback,
                args=(str(row["listing_id"]), _snapshot_listing(row)),
            )
    st.markdown("<div class='budget-panel-footer'>", unsafe_allow_html=True)
    pager_cols = st.columns([1, 1.3, 1])
    pager_cols[0].button(
        tr("上一页", "Previous"),
        key="budget_panel_prev",
        use_container_width=True,
        disabled=current_page <= 0,
        on_click=_shift_budget_listing_page,
        args=(-1, total_pages),
    )
    with pager_cols[1]:
        st.caption(tr(f"第 {current_page + 1} / {total_pages} 页", f"Page {current_page + 1} of {total_pages}"))
    pager_cols[2].button(
        tr("下一页", "Next"),
        key="budget_panel_next",
        use_container_width=True,
        disabled=current_page >= total_pages - 1,
        on_click=_shift_budget_listing_page,
        args=(1, total_pages),
    )
    st.markdown("</div>", unsafe_allow_html=True)


def _browser_filter_summary(
    *,
    budget_min: int,
    budget_max: int,
    min_budget: int,
    max_budget: int,
    min_bedrooms: int,
    exact_bedrooms: bool,
) -> str:
    if budget_min <= min_budget and budget_max >= max_budget:
        price_part = tr("不限价格", "Any price")
    else:
        price_part = f"{_money(budget_min)}-{_money(budget_max)}"
    if min_bedrooms <= 0:
        beds_part = tr("不限卧室", "Any beds")
    elif exact_bedrooms:
        beds_part = tr(f"{min_bedrooms}房", f"{min_bedrooms} beds")
    else:
        beds_part = tr(f"{min_bedrooms}房+", f"{min_bedrooms}+ beds")
    return f"{price_part} / {beds_part}"


def _render_browser_empty_state_card(
    *,
    focused_suburb: str,
    filter_summary: str,
    active_listing_count: int,
    browser_mode: str,
) -> None:
    st.markdown(
        f"""
        <div class="budget-panel-summary">
          <div class="budget-panel-eyebrow">{tr("匹配房源", "Matching Listings")}</div>
          <div class="budget-panel-title">{tr("当前没有符合筛选条件的房源", "No matching listings right now")}</div>
          <div class="budget-panel-subtitle">{tr(f"{focused_suburb} 目前没有符合你筛选条件的房源", f"No listings currently match your filters in {focused_suburb}")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"{tr('当前条件', 'Current filters')}: {filter_summary}")
    st.caption(
        tr(
            f"该区域当前共有 {active_listing_count:,} 个在售房源。",
            f"There are {active_listing_count:,} active listings in this suburb.",
        )
    )
    if active_listing_count <= 0:
        st.info(
            tr(
                "该 suburb 当前没有可用在售房源，请清除聚焦或调整筛选条件后继续。",
                "This suburb currently has no active listings. Clear the focus or adjust filters to continue.",
            )
        )
    else:
        st.info(
            tr(
                "你可以查看该区域全部房源，或清除当前 suburb 聚焦后回到全局匹配结果。",
                "You can view all listings in this suburb, or clear the current suburb focus and return to the global matches.",
            )
        )
    action_cols = st.columns(2)
    action_cols[0].button(
        tr("查看该区域全部房源", "View all in this suburb"),
        key=f"budget_browser_view_all_{focused_suburb}",
        use_container_width=True,
        disabled=active_listing_count <= 0 or browser_mode == "focused_all",
        on_click=_handle_view_all_in_focused_suburb,
    )
    action_cols[1].button(
        tr("调整筛选条件", "Adjust filters"),
        key=f"budget_browser_adjust_{focused_suburb}",
        use_container_width=True,
        on_click=_handle_adjust_filters,
    )


def _resolve_focused_suburb_browser_rows(
    filtered_display_listings: pd.DataFrame,
    all_display_listings: pd.DataFrame,
    *,
    selected_suburb: str,
    browser_scope_mode: str,
) -> tuple[pd.DataFrame, int]:
    if selected_suburb == "__ALL__":
        return filtered_display_listings.copy(), int(len(filtered_display_listings))
    filtered_rows = filtered_display_listings.loc[
        filtered_display_listings["suburb"].astype(str) == str(selected_suburb)
    ].copy()
    if browser_scope_mode == "focused_all":
        all_rows = all_display_listings.loc[
            all_display_listings["suburb"].astype(str) == str(selected_suburb)
        ].copy()
        return all_rows, int(len(filtered_rows))
    return filtered_rows, int(len(filtered_rows))


def _render_external_listing_panel(
    listings: pd.DataFrame,
    selected_suburb: str,
    metadata: dict[str, int | bool],
    *,
    browser_scope_mode: str = "filtered",
    empty_state: dict[str, object] | None = None,
) -> None:
    title = (
        tr(f"{selected_suburb} 的匹配房源", f"Matching Listings in {selected_suburb}")
        if selected_suburb != "__ALL__"
        else tr("匹配房源", "Matching Listings")
    )
    eyebrow = (
        tr("地图聚焦 suburb", "Focused suburb browser")
        if selected_suburb != "__ALL__"
        else tr("当前列表范围", "Current listing scope")
    )
    subtitle = (
        tr(
            "右侧房源浏览仅切换为当前聚焦 suburb，顶部筛选、指标和 suburb 排序保持全局不变。",
            "The browser is scoped to the focused suburb only. Top filters, metrics, and suburb ranking remain global.",
        )
        if selected_suburb != "__ALL__"
        else tr(
            "右侧房源浏览显示当前顶部筛选条件下的全部匹配房源。",
            "The browser shows all listings that match the current top filters.",
        )
    )
    if browser_scope_mode == "focused_all" and selected_suburb != "__ALL__":
        subtitle = tr(
            "当前显示该 suburb 的全部在售房源，仅影响右侧浏览区，不会改写顶部筛选条件。",
            "Currently showing all active listings in this suburb. This only affects the browser panel and does not change the top filters.",
        )
    st.markdown(
        f"""
        <div class="budget-panel-summary">
          <div class="budget-panel-eyebrow">{eyebrow}</div>
          <div class="budget-panel-title">{title}<span class="budget-panel-badge">{len(listings):,}</span></div>
          <div class="budget-panel-subtitle">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if listings.empty:
        if empty_state and selected_suburb != "__ALL__":
            _render_browser_empty_state_card(
                focused_suburb=str(empty_state.get("focused_suburb") or selected_suburb),
                filter_summary=str(empty_state.get("filter_summary") or "N/A"),
                active_listing_count=int(empty_state.get("active_listing_count") or 0),
                browser_mode=browser_scope_mode,
            )
        else:
            st.info(tr("当前 suburb / 筛选条件下没有房源。", "No listings match the current suburb or filters."))
        return

    selected_row = _selected_listing_row(listings)
    if bool(metadata.get("is_limited")) and selected_suburb == "__ALL__":
        st.warning(tr("请收窄筛选条件。当前仅展示受保护的顶部结果。", "Please refine your filters. Only protected top results are shown right now."))
        st.caption(tr("显示顶部结果 — 请细化筛选条件", "Showing top results — refine filters"))

    if selected_row is not None:
        st.markdown(
            chip_row(
                [
                    (f"{t('focused_label')}: {selected_suburb}", "caution")
                    if selected_suburb != "__ALL__"
                    else (t("global_view_label"), "neutral"),
                    (t("selected_property_indicator"), "positive"),
                ]
            ),
            unsafe_allow_html=True,
        )
        _render_external_listing_detail(selected_row, listings, selected_suburb)
        return

    total_pages = _external_page_count(len(listings))
    current_page = min(int(st.session_state.get("budget_listing_page", 0)), total_pages - 1)
    st.session_state["budget_listing_page"] = current_page
    start = current_page * EXTERNAL_PAGE_SIZE
    end = min(start + EXTERNAL_PAGE_SIZE, len(listings))

    for _, row in listings.iloc[start:end].copy().iterrows():
        st.markdown(
            f"""
            <div class="budget-card">
              <div class="budget-card-price">{_external_listing_price_label(row)}</div>
              <div class="budget-card-address">{row['address'] if pd.notna(row.get('address')) else 'N/A'}</div>
              <div class="budget-card-meta">
                {row['suburb'] if pd.notna(row.get('suburb')) else 'N/A'} / {row['postcode'] if pd.notna(row.get('postcode')) else 'N/A'}<br>
                {row['property_group_label']} / {_title_case_subtype(row['property_subtype'])} / {tr('Beds/Baths/Parking', 'Beds/Baths/Parking')}: {_feature_triplet(row)}<br>
                {_source_badge_for_row(row)}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        row_cols = st.columns([1.18, 0.82])
        row_cols[0].button(
            tr("查看详情并定位", "View details and locate"),
            key=f"budget_panel_view_{row['listing_id']}",
            use_container_width=True,
            on_click=_set_panel_listing_callback,
            args=(str(row["listing_id"]), str(row.get("suburb") or "")),
        )
        if _is_extended_listing(row):
            row_cols[1].button(
                tr("View only", "View only"),
                key=f"budget_panel_shortlist_{row['listing_id']}",
                use_container_width=True,
                disabled=True,
            )
        else:
            shortlisted = str(row["listing_id"]) in _get_shortlist_ids()
            row_cols[1].button(
                tr("Saved", "Saved") if shortlisted else tr("Shortlist", "Shortlist"),
                key=f"budget_panel_shortlist_{row['listing_id']}",
                use_container_width=True,
                on_click=_toggle_shortlist_callback,
                args=(str(row["listing_id"]), _snapshot_listing(row)),
            )
    st.markdown("<div class='budget-panel-footer'>", unsafe_allow_html=True)
    pager_cols = st.columns([1, 1.3, 1])
    pager_cols[0].button(
        tr("上一页", "Previous"),
        key="budget_panel_prev",
        use_container_width=True,
        disabled=current_page <= 0,
        on_click=_shift_budget_listing_page,
        args=(-1, total_pages),
    )
    with pager_cols[1]:
        st.caption(tr(f"第 {current_page + 1} / {total_pages} 页", f"Page {current_page + 1} of {total_pages}"))
    pager_cols[2].button(
        tr("下一页", "Next"),
        key="budget_panel_next",
        use_container_width=True,
        disabled=current_page >= total_pages - 1,
        on_click=_shift_budget_listing_page,
        args=(1, total_pages),
    )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_listing_results(listings: pd.DataFrame, selected_suburb: str) -> None:
    if listings.empty:
        st.info(tr("当前 suburb / 筛选条件下没有房源。", "No listings match the current suburb or filters."))
        return
    label = (
        tr(f"{selected_suburb} 的匹配房源", f"Matching Listings in {selected_suburb}")
        if selected_suburb != "__ALL__"
        else tr("匹配房源", "Matching Listings")
    )
    st.caption(f"{label} • {len(listings):,} {tr('套房源', 'listings')}")
    if selected_suburb != "__ALL__":
        st.caption(tr("点击地址即可在地图上定位该房源。", "Click an address to locate that listing on the map."))
    else:
        st.caption(tr("先聚焦一个 suburb，再点击地址查看房源在地图上的位置。", "Focus a suburb first, then click an address to locate a listing on the map."))
    browse_limit = 24 if True else 14
    if True:
        _render_external_sale_table(listings.head(browse_limit), key_prefix="browse", selected_suburb=selected_suburb)
    else:
        for _, row in listings.head(browse_limit).iterrows():
            _listing_card(row, key_prefix="browse")
    if len(listings) > browse_limit:
        st.caption(tr(f"当前先展示前 {browse_limit} 条更适合浏览的结果。", f"Showing the first {browse_limit} results for easier browsing."))


def _render_shortlist_summary(shortlist_df: pd.DataFrame) -> None:
    if shortlist_df.empty:
        st.info(tr("shortlist 为空。", "The shortlist is empty."))
        return
    suburbs = sorted(x for x in shortlist_df["suburb"].dropna().unique().tolist() if str(x).strip())
    priced = shortlist_df.loc[shortlist_df["has_price"]]
    price_range = "N/A"
    if not priced.empty:
        price_range = f"{_money(priced['price_filter_min'].min())} – {_money(priced['price_filter_max'].max())}"
    st.code(
        "\n".join([
            f"{tr('Shortlisted listings', 'Shortlisted listings')}: {len(shortlist_df)}",
            f"{tr('Suburbs covered', 'Suburbs covered')}: {', '.join(suburbs) if suburbs else 'N/A'}",
            f"{tr('Price range', 'Price range')}: {price_range}",
            f"{tr('Dominant property type', 'Dominant property type')}: {_title_case_subtype(_mode_or_na(shortlist_df['property_subtype']))}",
            f"{tr('Dominant bedroom count', 'Dominant bedroom count')}: {_mode_or_na(shortlist_df['bedrooms'])}",
        ])
    )


def _render_shortlist_report_item(row: pd.Series, market_listings: pd.DataFrame) -> None:
    with st.container(border=True):
        info_col, action_col = st.columns([4.6, 2.0], gap="small")
        with info_col:
            st.markdown(f"**{_report_text(row.get('address'))}**")
            st.caption(f"{_report_text(row.get('suburb'))} / {_report_text(row.get('postcode'))}")
            st.write(f"{tr('Price', 'Price')}: {_report_text(row.get('price_display'))}")
            st.write(f"{tr('Type', 'Type')}: {_report_property_type(row)}")
            st.write(f"{tr('Beds/Baths/Parking', 'Beds/Baths/Parking')}: {_feature_triplet(row)}")
        with action_col:
            st.button(
                tr("移出 shortlist", "Remove"),
                key=f"shortlist_remove_{row['listing_id']}",
                use_container_width=True,
                on_click=_toggle_shortlist_callback,
                args=(str(row["listing_id"]), _snapshot_listing(row)),
            )
            try:
                if IS_EXTERNAL_DEPLOYMENT:
                    st.caption(tr("报告下载尚未对公开部署开放。", "Report download is not available in the public deployment."))
                else:
                    pdf_bytes = _render_sale_report_pdf_bytes_v2(row, market_listings)
                    st.download_button(
                        tr("下载报告", "Download Report"),
                        data=pdf_bytes,
                        file_name=_safe_report_filename(row),
                        mime="application/pdf",
                        key=f"shortlist_report_{row['listing_id']}",
                        use_container_width=True,
                    )
            except Exception:
                st.caption(tr("该房源报告暂时无法生成。", "This report is currently unavailable for this listing."))


def _render_shortlist_panel(shortlist_df: pd.DataFrame, market_listings: pd.DataFrame) -> None:
    if shortlist_df.empty:
        st.info(tr("还没有加入 shortlist 的房源。", "No listings have been shortlisted yet."))
        return
    for _, row in shortlist_df.iterrows():
        _render_shortlist_report_item_public_aligned(row, market_listings)


def _render_shortlist_report_item_public_aligned(row: pd.Series, market_listings: pd.DataFrame) -> None:
    with st.container(border=True):
        info_col, action_col = st.columns([4.6, 2.0], gap="small")
        with info_col:
            st.markdown(f"**{_report_text(row.get('address'))}**")
            st.caption(f"{_report_text(row.get('suburb'))} / {_report_text(row.get('postcode'))}")
            st.write(f"{tr('Price', 'Price')}: {_report_text(row.get('price_display'))}")
            st.write(f"{tr('Type', 'Type')}: {_report_property_type(row)}")
            st.write(f"{tr('Beds/Baths/Parking', 'Beds/Baths/Parking')}: {_feature_triplet(row)}")
        with action_col:
            st.button(
                tr("移出 shortlist", "Remove"),
                key=f"shortlist_remove_public_aligned_{row['listing_id']}",
                use_container_width=True,
                on_click=_toggle_shortlist_callback,
                args=(str(row["listing_id"]), _snapshot_listing(row)),
            )
            if IS_EXTERNAL_DEPLOYMENT or IS_PUBLIC_MODE:
                st.caption(tr("报告下载尚未对公开部署开放。", "Report download is not available in the public deployment."))
            else:
                try:
                    pdf_bytes = _render_sale_report_pdf_bytes_v2(row, market_listings)
                    st.download_button(
                        tr("下载报告", "Download Report"),
                        data=pdf_bytes,
                        file_name=_safe_report_filename(row),
                        mime="application/pdf",
                        key=f"shortlist_report_public_aligned_{row['listing_id']}",
                        use_container_width=True,
                    )
                except Exception:
                    st.caption(tr("该房源报告暂时无法生成。", "This report is currently unavailable for this listing."))


def _render_comparison_table(shortlist_df: pd.DataFrame) -> None:
    if shortlist_df.empty:
        st.info(tr("先将房源加入 shortlist，再在这里进行对比。", "Add listings to the shortlist first to compare them here."))
        return
    comparison = shortlist_df.copy()
    comparison["bedrooms"] = comparison["bedrooms"].map(_count_label)
    comparison["bathrooms"] = comparison["bathrooms"].map(_count_label)
    comparison["parking"] = comparison["parking"].map(_count_label)
    comparison["land_size"] = comparison["land_size"].map(_land_size_label)
    comparison["property_type_label"] = comparison["property_group_label"] + " / " + comparison["property_subtype"].map(_title_case_subtype)
    if True:
        widths = [2.2, 1.0, 1.4, 0.7, 0.7, 0.8, 0.9, 1.1, 1.1]
        headers = [
            tr("地址", "Address"),
            tr("标价", "Price"),
            tr("类型", "Type"),
            tr("卧室", "Bedrooms"),
            tr("卫生间", "Bathrooms"),
            tr("车位", "Parking"),
            tr("土地面积", "Land size"),
            tr("Suburb", "Suburb"),
            tr("中介", "Agency"),
        ]
        header_cols = st.columns(widths, gap="small")
        for col, label in zip(header_cols, headers):
            col.markdown(f"<div class='budget-table-head'>{label}</div>", unsafe_allow_html=True)
        for _, row in comparison.iterrows():
            cols = st.columns(widths, gap="small")
            cols[0].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{row['address'] if pd.notna(row.get('address')) else 'N/A'}</div></div>", unsafe_allow_html=True)
            cols[1].markdown(f"<div class='budget-table-row'><div class='budget-table-cell budget-table-price'>{row['price_display']}</div></div>", unsafe_allow_html=True)
            cols[2].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{row['property_type_label']}</div></div>", unsafe_allow_html=True)
            cols[3].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{row['bedrooms']}</div></div>", unsafe_allow_html=True)
            cols[4].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{row['bathrooms']}</div></div>", unsafe_allow_html=True)
            cols[5].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{row['parking']}</div></div>", unsafe_allow_html=True)
            cols[6].markdown(f"<div class='budget-table-row'><div class='budget-table-cell budget-table-muted'>{row['land_size']}</div></div>", unsafe_allow_html=True)
            cols[7].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{row['suburb'] if pd.notna(row.get('suburb')) else 'N/A'}</div></div>", unsafe_allow_html=True)
            cols[8].markdown(f"<div class='budget-table-row'><div class='budget-table-cell budget-table-muted'>{row['agency_name'] if pd.notna(row.get('agency_name')) else 'N/A'}</div></div>", unsafe_allow_html=True)
        return
    st.dataframe(
        comparison[[
            "address",
            "price_display",
            "property_type_label",
            "bedrooms",
            "bathrooms",
            "parking",
            "land_size",
            "suburb",
            "agency_name",
        ]].rename(columns={
            "address": tr("地址", "Address"),
            "price_display": tr("标价", "Price"),
            "property_type_label": tr("类型", "Type"),
            "bedrooms": tr("卧室", "Bedrooms"),
            "bathrooms": tr("卫生间", "Bathrooms"),
            "parking": tr("车位", "Parking"),
            "land_size": tr("土地面积", "Land size"),
            "suburb": tr("Suburb", "Suburb"),
            "agency_name": tr("中介", "Agency"),
        }),
        use_container_width=True,
        hide_index=True,
    )


def _resolve_commute_filter(df: pd.DataFrame, suburb_lookup: pd.DataFrame, *, query: str, mode: str, max_minutes: int) -> tuple[list[str], set[str], pd.DataFrame, dict[str, object], str | None]:
    origin = resolve_commute_origin(query, suburb_lookup, df)
    fallback_label = _format_commute_chip(mode=mode, max_minutes=int(max_minutes), label=str(query).strip())
    if not origin.get("matched"):
        return [], set(), pd.DataFrame(), origin, fallback_label

    commute_df = compute_commute_listing_frame(
        origin_lat=float(origin["latitude"]),
        origin_lon=float(origin["longitude"]),
        listing_df=df,
        mode=mode,
    )
    if commute_df.empty:
        suburb_commute_df = compute_commute_suburb_frame(
            origin_lat=float(origin["latitude"]),
            origin_lon=float(origin["longitude"]),
            suburb_lookup=suburb_lookup,
            mode=mode,
        )
        matched_suburbs = suburb_commute_df.loc[suburb_commute_df["commute_minutes"] <= float(max_minutes)].copy()
        allowed_suburbs = matched_suburbs["suburb"].astype(str).dropna().drop_duplicates().tolist()
        return allowed_suburbs, set(), matched_suburbs, origin, _format_commute_chip(mode=mode, max_minutes=int(max_minutes), label=str(origin["label"]))
    matched = commute_df.loc[commute_df["commute_minutes"] <= float(max_minutes)].copy()
    allowed_suburbs = matched["suburb"].astype(str).dropna().drop_duplicates().tolist()
    allowed_listing_ids = set(matched["listing_id"].astype(str).dropna().tolist())

    mode_label = {
        "drive": tr("开车", "Drive"),
        "transit": tr("公共交通", "Public transport"),
        "walk": tr("步行", "Walking"),
    }.get(mode, tr("开车", "Drive"))
    chip = tr("通勤", "Commute") + f": {int(max_minutes)} min {mode_label} to {origin['label']}"
    return allowed_suburbs, allowed_listing_ids, matched, origin, chip


def _format_commute_chip(*, mode: str, max_minutes: int, label: str) -> str:
    mode_label = {
        "drive": tr("\u8f66\u7a0b", "drive"),
        "transit": tr("\u516c\u5171\u4ea4\u901a", "public transport"),
        "walk": tr("\u6b65\u884c", "walk"),
    }.get(mode, tr("\u8f66\u7a0b", "drive"))
    return (
        tr("\u901a\u52e4\uff1a", "Commute:")
        + f" {int(max_minutes)} "
        + tr(f"\u5206\u949f{mode_label}\u5230", f"min {mode_label} to")
        + f" {label}"
    )


def _format_summary_budget_range(min_value: int, max_value: int) -> str:
    return f"{_money(min_value)} - {_money(max_value)}"


def _render_external_buy_applied_filter_summary(filters: dict[str, object]) -> None:
    filters = dict(filters)
    filters["selected_sort"] = _buy_sort_label(filters.get("selected_sort"))
    lines = [
        tr("当前筛选：", "Active filters:"),
        f"{tr('预算', 'Budget')}: {_format_summary_budget_range(int(filters['budget_min']), int(filters['budget_max']))}",
    ]
    commute_summary = _format_applied_commute_summary(filters)
    if commute_summary:
        lines.append(commute_summary)
    if filters.get("selected_property_groups"):
        lines.append(
            f"{tr('房产大类', 'Property type')}: "
            + ", ".join(_title_case_subtype(group) for group in filters["selected_property_groups"])
        )
    if filters.get("selected_property_subtypes"):
        lines.append(
            f"{tr('细分类', 'Subtypes')}: "
            + ", ".join(_title_case_subtype(subtype) for subtype in filters["selected_property_subtypes"])
        )
    if filters.get("min_bedrooms"):
        lines.append(
            _format_applied_threshold(
                tr("卧室", "Bedrooms"),
                int(filters["min_bedrooms"]),
                exact=bool(filters.get("exact_bedrooms", False)),
            )
        )
    if filters.get("min_bathrooms"):
        lines.append(
            _format_applied_threshold(
                tr("卫生间", "Bathrooms"),
                int(filters["min_bathrooms"]),
                exact=bool(filters.get("exact_bathrooms", False)),
            )
        )
    if filters.get("min_parking"):
        lines.append(
            _format_applied_threshold(
                tr("车位", "Parking"),
                int(filters["min_parking"]),
                exact=bool(filters.get("exact_parking", False)),
            )
        )
    if filters.get("selected_suburbs"):
        lines.append(f"{tr('重点 suburb', 'Priority suburb')}: {', '.join(filters['selected_suburbs'])}")
    if filters.get("selected_postcodes"):
        lines.append(f"{tr('邮编', 'Postcode')}: {', '.join(filters['selected_postcodes'])}")
    lines.append(f"{tr('排序', 'Sort')}: {filters['selected_sort']}")
    chips = "".join(
        f"<span class='internal-chip' style='margin:0 0.45rem 0.45rem 0;'>{escape(line)}</span>"
        for line in lines[1:]
        if line
    )
    st.markdown(
        f"""
        <div class="internal-insight-card">
          <div class="internal-card-title">{escape(lines[0])}</div>
          <div class="internal-help-text" style="margin-bottom:0.3rem;">{escape(t('buy_budget_applied_filters_note'))}</div>
          <div>{chips}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_buy_page_header() -> None:
    badge = t("buy_budget_mode_public") if IS_PUBLIC_MODE else t("buy_budget_mode_internal")
    note = t("buy_budget_note_public") if IS_PUBLIC_MODE else t("buy_budget_note_internal")
    st.markdown(
        hero_block(
            title=t("buy_budget_title"),
            subtitle=note,
            badge=badge,
        ),
        unsafe_allow_html=True,
    )


def _render_buy_budget_summary(*, budget_min: int, budget_max: int) -> None:
    with st.container(border=True):
        st.markdown(f"**{t('buy_budget_summary_title')}**")
        st.caption(t("buy_budget_summary_note"))
        st.markdown(
            budget_hero_block(
                label=t("buy_budget_limit_label"),
                value=_money(budget_max),
                note=f"{t('buy_budget_applied_range')} {_money(budget_min)} - {_money(budget_max)}",
            ),
            unsafe_allow_html=True,
        )


def _render_buy_dashboard_cards(insight: dict[str, object], *, budget_min: int, budget_max: int) -> None:
    cards = [
        (tr("当前挂牌中位价", "Current median asking price"), _money(insight["typical_price"]), tr("当前筛选结果中的典型标价", "Typical asking price within the active result set"), ""),
        (tr("预算信号", "Budget signal"), insight["signal_label"], tr("帮助判断当前预算位于市场中的相对位置", "Helps position the current budget within the market"), ""),
        (tr("可选 suburb", "Available suburbs"), f"{insight['suburb_count']:,}", tr("当前顶层筛选仍然覆盖的 suburb 数量", "Suburbs still covered by the active top filters"), ""),
        (tr("匹配房源", "Matching listings"), f"{insight['listing_count']:,}", tr("当前页面筛选后的房源数量", "Listings remaining after the active page filters"), ""),
    ]
    cols = st.columns(4)
    for col, (label, value, caption, tone) in zip(cols, cards):
        with col:
            tone_html = f"<div class='{tone}'></div>" if tone else ""
            st.markdown(
                f"""
                <div class="internal-card">
                  <div class="internal-card-title">{escape(label)}</div>
                  <div class="internal-metric-value">{escape(value)}</div>
                  {tone_html}
                  <div class="internal-help-text" style="margin-top:0.55rem;">{escape(caption)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_buy_overview_row(insight: dict[str, object], *, budget_min: int, budget_max: int) -> None:
    cards = [
        (
            t("buy_overview_budget"),
            _money(budget_max),
            f"{t('buy_budget_applied_range')} {_money(budget_min)} - {_money(budget_max)}",
        ),
        (
            t("buy_overview_signal"),
            str(insight["signal_label"]),
            tr("帮助判断当前预算位于市场中的相对位置", "Helps position the active budget within the market."),
        ),
        (
            t("buy_overview_bedrooms"),
            str(insight.get("common_bedrooms") or "N/A"),
            tr("当前匹配房源中最常见的卧室数量", "Most common bedroom count in the current matches."),
        ),
        (
            t("buy_overview_bathrooms"),
            str(insight.get("common_bathrooms") or "N/A"),
            tr("当前匹配房源中最常见的浴室数量", "Most common bathroom count in the current matches."),
        ),
    ]
    cols = st.columns(4)
    for col, (label, value, caption) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="internal-card">
                  <div class="internal-card-title">{escape(label)}</div>
                  <div class="internal-metric-value">{escape(value)}</div>
                  <div class="internal-help-text" style="margin-top:0.55rem;">{escape(caption)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_scope_and_selection_status(*, selected_suburb: str, selected_listing_id: str | None) -> None:
    items: list[tuple[str, str | None]] = []
    if selected_suburb == "__ALL__":
        items.append((t("global_view_label"), "neutral"))
    else:
        items.append((f"{t('focused_label')}: {selected_suburb}", "caution"))
    if selected_listing_id:
        items.append((t("selected_property_indicator"), "positive"))
    st.markdown(chip_row(items), unsafe_allow_html=True)


def _render_public_access_restricted_state() -> None:
    st.markdown(
        simple_card(
            title=t("public_page_restricted_title"),
            body=t("public_page_restricted_body"),
            variant="warning",
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        chip_row(
            [
                (t("public_page_restricted_home"), "neutral"),
                (t("public_page_restricted_market"), "positive"),
            ]
        ),
        unsafe_allow_html=True,
    )
    st.caption(t("public_page_restricted_internal"))


def main() -> None:
    perf = PagePerf("buy_budget")
    ensure_lang()
    inject_app_theme()
    _init_state()

    with st.sidebar:
        sidebar_common(include_dwelling=False)
    _render_buy_page_header()
    if IS_PUBLIC_MODE:
        _render_public_access_restricted_state()
        return
    if False:
        render_external_page_header(
        badge=tr("Public Beta", "Public Beta"),
        title=tr("买房预算", "Buy Budget"),
        note=tr(
            "公开测试版：帮助你更快锁定符合预算、通勤与房型偏好的房源和 suburb。",
            "Public beta to quickly narrow homes and suburbs that fit your budget, commute, and property preferences.",
        ),
    )

    with perf.track("source_data_load"):
        source_status = get_domain_listing_source_status()
        df = load_domain_sale_listings()
    if df.empty:
        st.error(tr("未找到可用的市场挂牌数据。", "No market listing data file was found."))
        if not IS_EXTERNAL_DEPLOYMENT:
            st.code(source_status["path"])
        return
    df = apply_external_sale_listing_display_filter(df)
    suburb_centroid_lookup = build_suburb_centroid_lookup(df)

    min_budget, max_budget = _normalise_bounds(df)
    external_budget_options = _build_external_sale_budget_scale()
    _init_budget_filter_state(min_budget, max_budget)
    _apply_pending_ranking_filter_reset()
    applied_filters = _merge_filter_defaults(st.session_state.get("budget_applied_filters"), min_budget, max_budget)
    st.session_state["budget_applied_filters"] = applied_filters
    _apply_pending_external_buy_reset(external_budget_options)
    applied_filters = _merge_filter_defaults(st.session_state.get("budget_applied_filters"), min_budget, max_budget)
    st.session_state["budget_applied_filters"] = applied_filters
    _initialise_external_buy_widget_state_from_applied(applied_filters, external_budget_options)
    external_budget_range = _coerce_external_budget_range(
        st.session_state.get("budget_external_applied_range"),
        options=external_budget_options,
        default_range=(int(applied_filters.get("budget_min", min_budget)), int(applied_filters.get("budget_max", max_budget))),
    )
    shortlist_ids = set(_get_shortlist_ids())
    shortlist_count = len(shortlist_ids)
    search_submitted = False
    reset_submitted = False

    _render_buy_budget_summary(
        budget_min=external_budget_range[0],
        budget_max=external_budget_range[1],
    )

    with st.container(border=True):
        st.markdown(
            f"""
            <div class="internal-filter-panel">
              <div class="internal-filter-shell-head">
                <div class="internal-card-title">{escape(t("buy_budget_controls_title"))}</div>
                <div class="internal-help-text">{escape(t("buy_budget_controls_note"))}</div>
              </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("budget_search_form", border=False):
            budget_col = st.container()
            filter_col = st.container()
            with budget_col:
                st.markdown(f"**{t('buy_budget_limit_label')}**")
                budget_min, budget_max = st.select_slider(
                    tr("预算区间", "Budget range"),
                    options=external_budget_options,
                    value=external_budget_range,
                    format_func=_format_external_sale_budget_label,
                )
                st.markdown(f"<div class='internal-inline-note'>{escape(t('buy_budget_limit_note'))}</div>", unsafe_allow_html=True)
                st.caption(
                    tr(
                        "低价区间使用更细分的步长，高价区间使用更宽的步长，以便更快浏览。",
                        "Lower price bands use finer steps and higher price bands use broader steps for faster browsing.",
                    )
                )
                st.caption(tr("预算是本页的核心驱动条件，其他筛选都叠加在预算之上。", "Budget is the main driver of this page; the other filters sit on top of it."))
            with filter_col:
                row1, row2, row3 = st.columns([1.15, 1.0, 1.0])
                suburb_options = sorted(x for x in df["suburb"].dropna().unique().tolist() if str(x).strip())
                postcode_options = sorted(x for x in df["postcode"].dropna().unique().tolist() if str(x).strip())
                with row1:
                    selected_suburbs = st.multiselect(tr("优先 suburb", "Priority suburbs"), options=suburb_options, placeholder=tr("不限 suburb", "Any suburb"), key="budget_selected_suburbs")
                with row2:
                    selected_postcodes = st.multiselect(tr("邮编", "Postcode"), options=postcode_options, placeholder=tr("不限邮编", "Any postcode"), key="budget_selected_postcodes")
                with row3:
                    current_min_bedrooms = int(st.session_state.get("budget_min_bedrooms", 0))
                commute_query = ""
                commute_mode = "drive"
                commute_minutes = 30
                commute_col1, commute_col2, commute_col3 = st.columns([1.7, 1.0, 0.9])
                with commute_col1:
                    commute_query = st.text_input(
                        tr("\u8ddd\u79bb\u7b5b\u9009", "Commute filter"),
                        key="budget_commute_query",
                        placeholder=tr("\u8f93\u5165 suburb \u6216 postcode", "Enter a suburb or postcode"),
                    )
                with commute_col2:
                    commute_mode = st.selectbox(
                        tr("\u51fa\u884c\u65b9\u5f0f", "Travel mode"),
                        options=["drive", "transit", "walk"],
                        format_func=lambda value: {
                            "drive": tr("\u5f00\u8f66", "Drive"),
                            "transit": tr("\u516c\u5171\u4ea4\u901a", "Public transport"),
                            "walk": tr("\u6b65\u884c", "Walking"),
                        }[value],
                        key="budget_commute_mode",
                    )
                with commute_col3:
                    commute_minutes = st.selectbox(
                        tr("\u901a\u52e4\u65f6\u95f4", "Travel time"),
                        options=[10, 20, 30, 45, 60],
                        key="budget_commute_minutes",
                    )
                st.caption(
                    tr(
                        "\u6d4b\u8bd5\u7248\u901a\u52e4\u7b5b\u9009\u5f53\u524d\u652f\u6301 suburb \u548c postcode\uff0c\u6682\u4e0d\u7a33\u5b9a\u652f\u6301\u5b8c\u6574\u8857\u9053\u5730\u5740\u3002",
                        "In beta, the commute filter currently supports suburbs and postcodes. Full street addresses are not yet supported reliably.",
                    )
                )

                commute_allowed_suburbs: list[str] | None = None
                commute_allowed_listing_ids: set[str] | None = None
                commute_label: str | None = None
                if str(commute_query).strip():
                    commute_allowed_suburbs, commute_allowed_listing_ids, _, commute_origin, commute_label = _resolve_commute_filter(
                        df,
                        suburb_centroid_lookup,
                        query=commute_query,
                        mode=commute_mode,
                        max_minutes=int(commute_minutes),
                    )
                    if commute_origin.get("matched"):
                        commute_label = _format_commute_chip(
                            mode=commute_mode,
                            max_minutes=int(commute_minutes),
                            label=str(commute_origin["label"]),
                        )
                    st.session_state["budget_commute_notice"] = None if commute_origin.get("matched") else tr(
                        "无法识别该地点，请优先使用 NSW suburb、postcode 或当前房源地址。",
                        "That location could not be resolved. Try an NSW suburb or postcode.",
                    )
                    if not commute_origin.get("matched"):
                        st.session_state["budget_commute_notice"] = tr(
                            "\u65e0\u6cd5\u8bc6\u522b\u8be5\u5730\u70b9\uff0c\u8bf7\u4f18\u5148\u4f7f\u7528 NSW suburb\u3001postcode \u6216\u5f53\u524d\u623f\u6e90\u5730\u5740\u3002",
                            "That location could not be resolved. Try an NSW suburb or postcode.",
                        )
                else:
                    st.session_state["budget_commute_notice"] = None
                current_min_bathrooms = int(st.session_state.get("budget_min_bathrooms", 0))
                current_min_parking = int(st.session_state.get("budget_min_parking", 0))
                property_group_context, _ = _apply_budget_filters(
                    df,
                    budget_min=budget_min,
                    budget_max=budget_max,
                    min_budget=min_budget,
                    max_budget=max_budget,
                    selected_suburbs=selected_suburbs,
                    selected_postcodes=selected_postcodes,
                    min_bedrooms=current_min_bedrooms,
                    min_bathrooms=current_min_bathrooms,
                    min_parking=current_min_parking,
                    exact_bedrooms=bool(st.session_state.get("budget_exact_bedrooms", False)),
                    exact_bathrooms=bool(st.session_state.get("budget_exact_bathrooms", False)),
                    exact_parking=bool(st.session_state.get("budget_exact_parking", False)),
                    allowed_listing_ids=commute_allowed_listing_ids,
                    allowed_suburbs=commute_allowed_suburbs,
                    include_budget=True,
                    skip_filters={"property_group", "property_subtype"},
                )
                property_group_options = _property_group_options(property_group_context)
                group_values = [group for group, _, _ in property_group_options]
                group_label_map = {group: label for group, label, _ in property_group_options}
                group_count_map = {group: count for group, _, count in property_group_options}
                applied_group_values = _valid_selected(
                    st.session_state.get("budget_applied_filters", {}).get("selected_property_groups", []),
                    group_values,
                )
                current_group_values = st.session_state.get("budget_selected_group_labels")
                if current_group_values is None or any(group not in group_values for group in current_group_values):
                    st.session_state["budget_selected_group_labels"] = applied_group_values
                selected_group_values = st.multiselect(
                    tr("房产大类", "Property type"),
                    options=group_values,
                    placeholder=tr("不限类型", "Any group"),
                    format_func=lambda group: _category_option_label(group_label_map[group], int(group_count_map[group])),
                    key="budget_selected_group_labels",
                )
                previous_group_selection = list(st.session_state.get("budget_applied_filters", {}).get("selected_property_groups", []))
                valid_group_selection = _valid_selected(previous_group_selection, group_values)
                invalid_group_selection = [value for value in previous_group_selection if value not in set(group_values)]
                st.session_state["budget_group_notice"] = (
                    tr("当前筛选条件下已无该房产大类，系统已自动清除该选择。", "The selected property group is no longer available under the current filters, so it was cleared.")
                    if invalid_group_selection and not property_group_context.empty else None
                )
                selected_property_groups = list(selected_group_values)

            row4, row5, row6, row7 = st.columns([1.0, 1.0, 1.0, 1.1])
            with row4:
                min_bedrooms = st.selectbox(tr("最少卧室", "Min bedrooms"), options=[0, 1, 2, 3, 4, 5], format_func=lambda x: tr("不限", "Any") if x == 0 else f"{x}+", key="budget_min_bedrooms")
                st.toggle(tr("卧室精确匹配", "Exact beds"), key="budget_exact_bedrooms")
            with row5:
                min_bathrooms = st.selectbox(tr("最少浴室", "Min bathrooms"), options=[0, 1, 2, 3, 4], format_func=lambda x: tr("不限", "Any") if x == 0 else f"{x}+", key="budget_min_bathrooms")
                st.toggle(tr("浴室精确匹配", "Exact baths"), key="budget_exact_bathrooms")
            with row6:
                min_parking = st.selectbox(tr("最少车位", "Min parking"), options=[0, 1, 2, 3, 4], format_func=lambda x: tr("不限", "Any") if x == 0 else f"{x}+", key="budget_min_parking")
                st.toggle(tr("车位精确匹配", "Exact parking"), key="budget_exact_parking")
            with row7:
                sort_options = {
                    tr("价格从低到高", "Price low to high"): ("price_mid", True),
                    tr("价格从高到低", "Price high to low"): ("price_mid", False),
                    tr("最新挂牌", "Newest listing"): ("listing_date", False),
                    tr("卧室数量", "Bedrooms"): ("bedrooms", False),
                    tr("Suburb", "Suburb"): ("suburb", True),
                }
                selected_sort = st.selectbox(
                    tr("房源排序", "Listing sort"),
                    options=list(BUY_SORT_SPECS.keys()),
                    format_func=_buy_sort_label,
                    key="budget_selected_sort",
                )

            selected_property_subtypes: list[str] = []
            if st.toggle(tr("显示细分类", "Show subtype filter"), key="budget_show_subtypes"):
                subtype_cols = st.columns(min(max(len(property_group_options), 1), 3))
                for idx, (group, label, count) in enumerate(property_group_options):
                    with subtype_cols[idx % len(subtype_cols)]:
                        with st.expander(_category_option_label(label, int(count)), expanded=group in selected_property_groups):
                            subtype_count_series = _subtype_counts(property_group_context, group)
                            subtype_values = list(subtype_count_series.index)
                            state_key = f"budget_subtypes_{group}"
                            applied_subtypes = set(st.session_state.get("budget_applied_filters", {}).get("selected_property_subtypes", []))
                            applied_group_subtypes = _valid_selected(
                                [subtype for subtype in subtype_values if subtype in applied_subtypes],
                                subtype_values,
                            )
                            current_group_subtypes = st.session_state.get(state_key)
                            if current_group_subtypes is None or any(subtype not in subtype_values for subtype in current_group_subtypes):
                                st.session_state[state_key] = applied_group_subtypes
                            picked_values = st.multiselect(
                                tr("选择细分类", "Select subtypes"),
                                options=subtype_values,
                                format_func=lambda subtype, counts=subtype_count_series: _category_option_label(_title_case_subtype(subtype), int(counts.get(subtype, 0))),
                                key=state_key,
                            )
                            selected_property_subtypes.extend(picked_values)

            _render_filter_chips(selected_property_groups, selected_property_subtypes, selected_suburbs, selected_postcodes, min_bedrooms, min_bathrooms, min_parking, commute_label=commute_label)
            action_cols = st.columns(2)
            with action_cols[0]:
                search_submitted = st.form_submit_button(tr("搜索", "Search"), type="primary", use_container_width=True)
            with action_cols[1]:
                reset_submitted = st.form_submit_button(tr("重置筛选", "Reset filters"), use_container_width=True)
            st.caption(tr("房产大类计数基于当前预算、suburb、邮编和卧室/浴室/车位条件计算，不包含房产大类筛选本身。", "Property-group counts are computed from the current budget, suburb, postcode, and bed/bath/parking context, excluding the property-group filter itself."))
        st.markdown("</div>", unsafe_allow_html=True)
    if True and reset_submitted:
        _reset_external_buy_filters(min_budget, max_budget, external_budget_options)
        st.rerun()
    if search_submitted:
        st.session_state["budget_external_applied_range"] = (budget_min, budget_max)
        st.session_state["budget_applied_filters"] = _merge_filter_defaults(
            {
                "budget_min": budget_min,
                "budget_max": budget_max,
                "selected_suburbs": list(selected_suburbs),
                "selected_postcodes": list(selected_postcodes),
                "selected_property_groups": list(selected_property_groups),
                "selected_property_subtypes": sorted(set(selected_property_subtypes)),
                "commute_query": str(commute_query),
                "commute_mode": str(commute_mode),
                "commute_minutes": int(commute_minutes),
                "min_bedrooms": int(min_bedrooms),
                "min_bathrooms": int(min_bathrooms),
                "min_parking": int(min_parking),
                "exact_bedrooms": bool(st.session_state.get("budget_exact_bedrooms", False)),
                "exact_bathrooms": bool(st.session_state.get("budget_exact_bathrooms", False)),
                "exact_parking": bool(st.session_state.get("budget_exact_parking", False)),
                "selected_sort": _coerce_buy_sort_key(selected_sort),
                "show_subtypes": bool(st.session_state.get("budget_show_subtypes", False)),
                "commute_label": commute_label,
            },
            min_budget,
            max_budget,
        )
        _set_browser_scope_mode("focused_filtered" if _selected_suburb() != "__ALL__" else "filtered")
        st.session_state["buy_external_search_triggered"] = True
        _reset_listing_page()
        _reset_ranking_page()
    external_search_triggered = bool(st.session_state.get("buy_external_search_triggered", False))

    if not external_search_triggered:
        with st.container(border=True):
            st.markdown(f"**{tr('排序 suburb', 'Ranked Suburbs')}**")
            st.info(tr("应用筛选条件后点击搜索，即可查看结果。", "Apply filters and click Search to view results"))
        with st.container(border=True):
            st.markdown(f"**{tr('房源', 'Listings')}**")
            st.info(tr("应用筛选条件后点击搜索，即可查看结果。", "Apply filters and click Search to view results"))
        with st.container(border=True):
            status_cols = st.columns([2.5, 1])
            with status_cols[0]:
                st.markdown(f"**{tr('Shortlist', 'Shortlist')}**")
                st.markdown(f"<div class='budget-shortlist-status'>{tr('当前已收藏', 'Currently shortlisted')}: {shortlist_count} {tr('套房源', 'listings')}</div>", unsafe_allow_html=True)
            with status_cols[1]:
                if shortlist_count > 0 and st.button(tr("清空 shortlist", "Clear shortlist"), use_container_width=True):
                    _set_shortlist_ids(set())
                    st.session_state["budget_shortlist_items"] = {}
                    st.rerun()
        timing_payload = perf.log(shortlisted=len(_get_shortlist_ids()), filtered_rows=0)
        render_internal_timing_summary(timing_payload, enabled=False)
        return
    exact_bedrooms = bool(st.session_state.get("budget_exact_bedrooms", False))
    exact_bathrooms = bool(st.session_state.get("budget_exact_bathrooms", False))
    exact_parking = bool(st.session_state.get("budget_exact_parking", False))
    effective_filters = _merge_filter_defaults(st.session_state.get("budget_applied_filters"), min_budget, max_budget)
    budget_min = int(effective_filters["budget_min"])
    budget_max = int(effective_filters["budget_max"])
    selected_property_groups = list(effective_filters.get("selected_property_groups", []))
    selected_property_subtypes = list(effective_filters.get("selected_property_subtypes", []))
    selected_suburbs = list(effective_filters.get("selected_suburbs", []))
    selected_postcodes = list(effective_filters.get("selected_postcodes", []))
    min_bedrooms = int(effective_filters.get("min_bedrooms", 0))
    min_bathrooms = int(effective_filters.get("min_bathrooms", 0))
    min_parking = int(effective_filters.get("min_parking", 0))
    selected_sort = _coerce_buy_sort_key(effective_filters.get("selected_sort", selected_sort))
    commute_query = str(effective_filters.get("commute_query", ""))
    commute_mode = str(effective_filters.get("commute_mode", "drive"))
    commute_minutes = int(effective_filters.get("commute_minutes", 30))
    exact_bedrooms = bool(effective_filters.get("exact_bedrooms", False))
    exact_bathrooms = bool(effective_filters.get("exact_bathrooms", False))
    exact_parking = bool(effective_filters.get("exact_parking", False))
    commute_allowed_listing_ids: set[str] | None = None
    if commute_query.strip():
            commute_allowed_suburbs, commute_allowed_listing_ids, _, commute_origin, commute_label = _resolve_commute_filter(
                df,
                suburb_centroid_lookup,
                query=commute_query,
                mode=commute_mode,
                max_minutes=int(commute_minutes),
            )
            st.session_state["budget_commute_notice"] = None if commute_origin.get("matched") else tr(
                "无法识别该地点，请优先使用 NSW suburb、postcode 或当前房源地址。",
                "That location could not be resolved. Try an NSW suburb or postcode.",
            )
            if commute_origin.get("matched"):
                commute_label = _format_commute_chip(
                    mode=commute_mode,
                    max_minutes=int(commute_minutes),
                    label=commute_origin["label"],
                )
    else:
        commute_allowed_suburbs = None
        commute_allowed_listing_ids = None
        commute_origin = {"matched": False, "label": ""}
        commute_label = None
        st.session_state["budget_commute_notice"] = None
    commute_notice = st.session_state.get("budget_commute_notice")
    group_notice = st.session_state.get("budget_group_notice")
    full_budget_selected = _full_budget_selected(budget_min, budget_max, min_budget, max_budget)
    with (st.spinner("Searching...") if search_submitted else nullcontext()):
        with perf.track("filter_application"):
            filtered_listings, filter_debug_steps = _apply_budget_filters(
                df,
                budget_min=budget_min,
                budget_max=budget_max,
                min_budget=min_budget,
                max_budget=max_budget,
                selected_property_groups=selected_property_groups,
                selected_property_subtypes=selected_property_subtypes,
                selected_suburbs=selected_suburbs,
                selected_postcodes=selected_postcodes,
                min_bedrooms=min_bedrooms,
                min_bathrooms=min_bathrooms,
                min_parking=min_parking,
                exact_bedrooms=exact_bedrooms,
                exact_bathrooms=exact_bathrooms,
                exact_parking=exact_parking,
                allowed_listing_ids=commute_allowed_listing_ids,
                allowed_suburbs=commute_allowed_suburbs,
            )
            context_listings = filtered_listings.copy()

    sort_column, sort_ascending = BUY_SORT_SPECS[_coerce_buy_sort_key(selected_sort)]
    filtered_listings = filtered_listings.sort_values(by=[sort_column, "suburb", "address"], ascending=[sort_ascending, True, True], na_position="last")
    matched_filtered_listings = filtered_listings.copy()
    selected_suburb = _selected_suburb()
    selected_listing_id = _selected_listing_id()
    protection_meta = {"is_limited": False}
    coverage_universe = _coverage_universe_scope(
        df,
        selected_property_groups=tuple(sorted(set(selected_property_groups))),
        selected_property_subtypes=tuple(sorted(set(selected_property_subtypes))),
    )
    coverage_summary = _suburb_summary(coverage_universe, matched_filtered_listings, budget_min=budget_min, budget_max=budget_max)
    ranked_suburb_summary = coverage_summary.loc[coverage_summary["listing_count"] > 0].copy()
    filtered_listings, protection_meta = _protect_external_scope(
            matched_filtered_listings,
            suburb_summary=ranked_suburb_summary,
            focused_suburb=selected_suburb,
            selected_listing_id=selected_listing_id,
        )
    display_listings = _with_core_listing_badge(_prepare_external_display_listings(filtered_listings, sort_column=sort_column, sort_ascending=sort_ascending))
    all_display_listings = _with_core_listing_badge(_prepare_external_display_listings(df, sort_column=sort_column, sort_ascending=sort_ascending))
    browser_display_listings = display_listings.copy()
    browser_all_display_listings = all_display_listings.copy()
    include_extended_listings = False
    extended_source_filter = "Show all"
    if not IS_PUBLIC_MODE:
        with st.container(border=True):
            include_extended_listings = st.toggle(
                "Include additional market listing records",
                value=False,
                key="budget_include_validated_extended_listings",
            )
            if include_extended_listings:
                st.caption(EXTENDED_LISTING_CAPTION)
                extended_source_filter = st.selectbox(
                    "Listing data view",
                    EXTENDED_SOURCE_FILTER_OPTIONS,
                    index=0,
                    key="budget_extended_listing_source_filter",
                )
                extended_all_listings = _load_validated_extended_listings_for_browser()
                extended_filtered_listings = _filter_extended_listings_for_browser(
                    extended_all_listings,
                    budget_min=budget_min,
                    budget_max=budget_max,
                    min_budget=min_budget,
                    max_budget=max_budget,
                    selected_suburbs=selected_suburbs,
                    selected_postcodes=selected_postcodes,
                    min_bedrooms=min_bedrooms,
                    min_bathrooms=min_bathrooms,
                    min_parking=min_parking,
                    exact_bedrooms=exact_bedrooms,
                    exact_bathrooms=exact_bathrooms,
                    exact_parking=exact_parking,
                    allowed_suburbs=commute_allowed_suburbs,
                )
                if extended_all_listings.empty:
                    extended_display_listings = pd.DataFrame(columns=display_listings.columns)
                    extended_all_display_listings = pd.DataFrame(columns=all_display_listings.columns)
                else:
                    extended_display_listings = _prepare_external_display_listings(
                        extended_filtered_listings,
                        sort_column=sort_column,
                        sort_ascending=sort_ascending,
                    )
                    extended_all_display_listings = _prepare_external_display_listings(
                        extended_all_listings,
                        sort_column=sort_column,
                        sort_ascending=sort_ascending,
                    )
                browser_display_listings = pd.concat([display_listings, extended_display_listings], ignore_index=True, sort=False)
                browser_all_display_listings = pd.concat([all_display_listings, extended_all_display_listings], ignore_index=True, sort=False)
                browser_display_listings = _filter_browser_listing_source(browser_display_listings, extended_source_filter)
                browser_all_display_listings = _filter_browser_listing_source(browser_all_display_listings, extended_source_filter)
                print(f"[Buy Budget] Combined listing count: {len(browser_display_listings)}")
    with perf.track("ranking_table_prep"):
        suburb_summary = ranked_suburb_summary

    available_suburbs = set(df["suburb"].dropna().astype(str))
    if selected_suburb != "__ALL__" and selected_suburb not in available_suburbs:
        st.session_state["budget_focus_notice"] = tr(
            "当前聚焦 suburb 在新筛选条件下已无匹配房源，已返回全局视图。",
            "The focused suburb no longer has matching listings under the new filters, so the page has returned to the global view.",
        )
        _set_selected_suburb("__ALL__")
        selected_suburb = "__ALL__"

    focused_listings = matched_filtered_listings.loc[matched_filtered_listings["suburb"] == selected_suburb].copy() if selected_suburb != "__ALL__" else matched_filtered_listings.copy()
    focused_display_listings = browser_display_listings.loc[browser_display_listings["suburb"] == selected_suburb].copy() if selected_suburb != "__ALL__" else browser_display_listings.copy()
    browser_scope_mode = _browser_scope_mode()
    browser_listings, focused_match_count = _resolve_focused_suburb_browser_rows(
        browser_display_listings,
        browser_all_display_listings,
        selected_suburb=selected_suburb,
        browser_scope_mode=browser_scope_mode,
    )
    selected_listing_id = _selected_listing_id()
    visible_listing_ids = set(browser_listings["listing_id"].astype(str).tolist()) if selected_suburb != "__ALL__" else (
        set(focused_display_listings["listing_id"].astype(str).tolist()) if selected_suburb != "__ALL__" else set()
    )
    if selected_suburb == "__ALL__" or (selected_listing_id is not None and selected_listing_id not in visible_listing_ids):
        _clear_selected_listing()
    browser_empty_state = None
    if selected_suburb != "__ALL__" and focused_match_count <= 0:
        browser_empty_state = {
            "focused_suburb": selected_suburb,
            "filter_summary": _browser_filter_summary(
                budget_min=budget_min,
                budget_max=budget_max,
                min_budget=min_budget,
                max_budget=max_budget,
                min_bedrooms=min_bedrooms,
                exact_bedrooms=exact_bedrooms,
            ),
            "active_listing_count": int(len(df.loc[df["suburb"].astype(str) == str(selected_suburb)])),
        }
    insight_scope = matched_filtered_listings
    context_scope = context_listings
    focused_summary = suburb_summary.loc[suburb_summary["suburb"] == selected_suburb].copy() if selected_suburb != "__ALL__" else suburb_summary
    insight = _budget_insight(insight_scope, context_scope, budget_max, focused_suburb="__ALL__")
    shortlist_df = display_listings.loc[display_listings["listing_id"].astype(str).isin(shortlist_ids)].copy()
    shortlist_count = int(len(shortlist_df))
    if {"sort_has_numeric", "sort_primary", "suburb", "address"}.issubset(shortlist_df.columns):
        shortlist_df = shortlist_df.sort_values(by=["sort_has_numeric", "sort_primary", "suburb", "address"], ascending=[False, sort_ascending, True, True], na_position="last")
    show_debug = False
    focus_notice = _consume_focus_notice("budget_focus_notice")

    if show_debug:
        with st.expander("Budget Debug", expanded=False):
            debug_df = pd.DataFrame(filter_debug_steps, columns=["step", "rows"])
            st.dataframe(debug_df, use_container_width=True, hide_index=True)
            cleaning_counts = (
                df["price_cleaning_flag"]
                .fillna("missing")
                .value_counts()
                .rename_axis("price_cleaning_flag")
                .reset_index(name="rows")
            )
            st.dataframe(cleaning_counts, use_container_width=True, hide_index=True)
            st.caption(
                f"Budget rule = interval overlap on priced listings: "
                f"`has_price and price_filter_min <= budget_max and price_filter_max >= budget_min`; "
                f"unpriced listings are only included when the full market budget range is selected ({full_budget_selected})."
            )

    if commute_notice:
        st.warning(commute_notice)
    if group_notice:
        st.warning(group_notice)
    filters_for_summary = dict(effective_filters)
    if commute_label:
        filters_for_summary["commute_label"] = commute_label
    with st.container(border=True):
        st.markdown(f"**{tr('当前筛选', 'Active filters')}**")
        _render_external_buy_applied_filter_summary(filters_for_summary)
    if filtered_listings.empty:
        st.warning(tr("当前筛选条件下没有匹配房源。", "No listings match the current filters."))
    else:
        if focus_notice:
            st.warning(focus_notice)
        with st.container(border=True):
            st.markdown(f"**{t('buy_budget_dashboard_title')}**")
            st.caption(t("buy_budget_dashboard_note"))
            st.markdown(section_note(t("buy_budget_overview_intent")), unsafe_allow_html=True)
            _render_scope_and_selection_status(
                selected_suburb=selected_suburb,
                selected_listing_id=_selected_listing_id(),
            )
            _render_buy_overview_row(insight, budget_min=budget_min, budget_max=budget_max)
            if commute_label and not commute_notice:
                st.markdown(f"<span class='internal-chip internal-chip-caution'>{escape(commute_label)}</span>", unsafe_allow_html=True)
            st.markdown(f"**{tr('预算结论', 'Budget conclusion')}**")
            st.write(insight["conclusion"])
            if insight["new_suburbs"] and selected_suburb == "__ALL__":
                st.caption(f"{tr('潜在可拓展 suburb', 'Potential suburb expansion')}: {', '.join(insight['new_suburbs'])}")
            if insight.get("uplift_note"):
                st.caption(insight["uplift_note"])
        with st.container(border=True):
            focus_cols = st.columns([2.4, 1])
            with focus_cols[0]:
                st.markdown(f"**{tr('排序 suburb', 'Ranked Suburbs')}**")
                st.caption(t("buy_budget_ranking_intent"))
            with focus_cols[1]:
                _render_scope_and_selection_status(
                    selected_suburb=selected_suburb,
                    selected_listing_id=_selected_listing_id(),
                )
            _render_suburb_ranking(suburb_summary)

        if False:
            with st.container(border=True):
                st.markdown(f"**{tr('Map', 'Map')}**")
                st.caption(tr("地图现在是主要决策层：先看 suburb 覆盖率，再查看所选 suburb 内的房源点位。", "The map is now the main decision layer: read suburb coverage first, then inspect listing markers inside the selected suburb."))
                with perf.track("map_prep"):
                    selected_suburb = _build_map(matched_filtered_listings, suburb_summary, selected_suburb)
            focus_listings = (
                matched_filtered_listings.loc[matched_filtered_listings["suburb"] == selected_suburb].copy()
                if selected_suburb != "__ALL__"
                else matched_filtered_listings.copy()
            )
        else:
            focus_listings = browser_listings
        if True:
            with st.container(border=True):
                st.markdown(f"**{t('buy_budget_map_title')} + {t('buy_budget_browser_title')}**")
                st.caption(t("buy_budget_map_note"))
                st.markdown(section_note(t("buy_budget_browser_intent")), unsafe_allow_html=True)
                _render_scope_and_selection_status(
                    selected_suburb=selected_suburb,
                    selected_listing_id=_selected_listing_id(),
                )
                map_col, panel_col = st.columns([7, 3], gap="large")
                with map_col:
                    with st.container(border=True, height=EXTERNAL_MAP_PANEL_HEIGHT):
                        st.markdown(f"**{t('buy_budget_map_title')}**")
                        st.caption(tr("先看覆盖率，再看点位。首次加载需几秒。", "Read coverage first, then markers. First load can take a few seconds."))
                        with perf.track("map_prep_external_panel"):
                            selected_suburb = _build_map(matched_filtered_listings, suburb_summary, selected_suburb)
                browser_scope_mode = _browser_scope_mode()
                focus_listings, focused_match_count = _resolve_focused_suburb_browser_rows(
                    browser_display_listings,
                    browser_all_display_listings,
                    selected_suburb=selected_suburb,
                    browser_scope_mode=browser_scope_mode,
                )
                browser_empty_state = None
                if selected_suburb != "__ALL__" and focused_match_count <= 0:
                    browser_empty_state = {
                        "focused_suburb": selected_suburb,
                        "filter_summary": _browser_filter_summary(
                            budget_min=budget_min,
                            budget_max=budget_max,
                            min_budget=min_budget,
                            max_budget=max_budget,
                            min_bedrooms=min_bedrooms,
                            exact_bedrooms=exact_bedrooms,
                        ),
                        "active_listing_count": int(len(df.loc[df["suburb"].astype(str) == str(selected_suburb)])),
                    }
                with panel_col:
                    with st.container(border=True, height=EXTERNAL_MAP_PANEL_HEIGHT):
                        st.markdown(f"**{t('buy_budget_browser_title')}**")
                        if selected_suburb != "__ALL__":
                            st.caption(f"{tr('当前聚焦 suburb', 'Focused suburb')}: {selected_suburb}")
                        _render_external_listing_panel(
                            focus_listings,
                            selected_suburb,
                            protection_meta,
                            browser_scope_mode=browser_scope_mode,
                            empty_state=browser_empty_state,
                        )
    with st.container(border=True):
        status_cols = st.columns([2.5, 1])
        with status_cols[0]:
            st.markdown(f"**{tr('Shortlist', 'Shortlist')}**")
            st.markdown(f"<div class='budget-shortlist-status'>{tr('当前已收藏', 'Currently shortlisted')}: {shortlist_count} {tr('套房源', 'listings')}</div>", unsafe_allow_html=True)
        with status_cols[1]:
            if shortlist_count > 0 and st.button(tr("清空 shortlist", "Clear shortlist"), use_container_width=True):
                _set_shortlist_ids(set())
                st.session_state["budget_shortlist_items"] = {}
                st.rerun()

        with st.expander(tr("打开 shortlist 工作区", "Open shortlist workspace"), expanded=shortlist_count > 0):
            review_tab, compare_tab = st.tabs([
                tr("查看", "Review"),
                tr("对比", "Compare"),
            ])
            with review_tab:
                _render_shortlist_panel(shortlist_df, matched_filtered_listings)
            with compare_tab:
                _render_comparison_table(shortlist_df)

    timing_payload = perf.log(shortlisted=len(_get_shortlist_ids()), filtered_rows=int(len(filtered_listings)))
    render_internal_timing_summary(timing_payload, enabled=False)


if __name__ == "__main__":
    main()

