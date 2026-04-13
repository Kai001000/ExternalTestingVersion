import json
import math
import re
from contextlib import nullcontext
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.config import IS_EXTERNAL_MODE
from utils.data import (
    apply_external_rent_listing_display_filter,
    build_suburb_centroid_lookup,
    compute_commute_listing_frame,
    compute_commute_suburb_frame,
    format_price,
    get_domain_rent_source_status,
    load_domain_rent_listings,
    order_external_rent_listing_display,
    resolve_commute_origin,
)
from utils.i18n import ensure_lang, tr
from utils.map_view import NSW_MAP_BOUNDS, clamp_to_nsw_map_view, resolve_budget_map_view
from utils.perf import PagePerf, render_internal_timing_summary
from utils.ui import inject_app_theme, render_external_page_header, sidebar_common


SUBURB_JOIN_ALIASES = {"CESSNOCK WEST": "CESSNOCK", "PATONGA BEACH": "PATONGA"}
RENT_BUDGET_STEP = 25
MAP_HEIGHT = 640
EXTERNAL_MAX_WEEKLY_RENT = 100_000
RENT_SORT_SPECS = {
    "rent_asc": ("rent_mid", True),
    "rent_desc": ("rent_mid", False),
    "available_asc": ("available_date", True),
    "bedrooms_desc": ("bedrooms", False),
    "suburb_asc": ("suburb", True),
}

st.markdown(
    """
    <style>
    [data-testid="stHeader"] { height: 0rem; min-height: 0rem; padding: 0; }
    [data-testid="stToolbar"] { display: none; }
    section[data-testid="stMain"] > div:first-child { padding-top: 1.3rem; }
    .budget-kicker { color: #8c5e3c; font-size: 0.8rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 0.2rem; }
    .budget-title { font-size: 1.95rem; font-weight: 800; color: #111827; margin-bottom: 0.3rem; }
    .budget-note { color: #6b7280; font-size: 0.94rem; margin-bottom: 0.8rem; }
    .budget-budget-pill { display: inline-block; border-radius: 999px; background: #182230; color: #f8f5f1; padding: 0.42rem 0.9rem; font-size: 0.96rem; font-weight: 800; margin-bottom: 0.8rem; }
    .budget-chip { display: inline-block; border-radius: 999px; background: #efe6d8; color: #6f4e37; padding: 0.22rem 0.65rem; font-size: 0.78rem; font-weight: 700; margin-right: 0.35rem; margin-bottom: 0.35rem; }
    .budget-shortlist-status { color: #6b7280; font-size: 0.88rem; }
    .budget-list-row { border: 1px solid rgba(148, 163, 184, 0.22); border-radius: 16px; padding: 0.85rem 0.95rem; margin-bottom: 0.75rem; background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.92)); }
    .budget-list-address { font-size: 1rem; font-weight: 700; color: #111827; line-height: 1.3; margin-bottom: 0.18rem; }
    .budget-list-meta { color: #6b7280; font-size: 0.82rem; line-height: 1.4; }
    .budget-list-price { font-size: 1.05rem; font-weight: 800; color: #0f172a; text-align: right; white-space: nowrap; }
    .budget-list-subprice { color: #6b7280; font-size: 0.78rem; text-align: right; }
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


def _money(value):
    return format_price(value)


def _weekly_money(value):
    if value is None or pd.isna(value):
        return "N/A"
    return f"{format_price(value)} pw"


def _count_label(value):
    if value is None or pd.isna(value):
        return "N/A"
    if float(value).is_integer():
        return str(int(value))
    return f"{float(value):.1f}"


def _feature_triplet(row):
    return f"{_count_label(row['bedrooms'])} / {_count_label(row['bathrooms'])} / {_count_label(row['parking'])}"


def _compact_weekly_rent(value):
    if value is None or pd.isna(value):
        return "N/A"
    return f"${float(value):,.0f} pw"


def _build_external_rent_budget_scale() -> list[int]:
    values: set[int] = {75, 5_000}
    values.update(range(100, 1_001, 25))
    values.update(range(1_000, 2_001, 100))
    values.update(range(2_000, 5_001, 250))
    return sorted(values)


def _format_external_rent_budget_label(value) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("$") and text.endswith("/w"):
            return text
    return f"${int(value):,}/w"


def _coerce_external_rent_budget_range(saved_range, *, options, default_range):
    if not options:
        return default_range
    if isinstance(saved_range, (list, tuple)) and len(saved_range) == 2:
        raw_min, raw_max = int(saved_range[0]), int(saved_range[1])
    else:
        raw_min, raw_max = default_range
    nearest_min = min(options, key=lambda item: (abs(item - raw_min), item))
    nearest_max = min(options, key=lambda item: (abs(item - raw_max), item))
    if nearest_min > nearest_max:
        return default_range
    return nearest_min, nearest_max


def _mode_or_na(series):
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


def _title_case_subtype(value):
    if not value or value == "unknown":
        return tr("Unknown", "Unknown")
    return str(value).title()


def _normalise_weekly_bounds(df):
    source_df = apply_external_rent_listing_display_filter(df) if IS_EXTERNAL_MODE else df
    if source_df.empty:
        source_df = df
    rent_min = pd.to_numeric(source_df["rent_filter_min"], errors="coerce")
    rent_max = pd.to_numeric(source_df["rent_filter_max"], errors="coerce")
    if IS_EXTERNAL_MODE:
        return 75, 5_000
    if rent_min.notna().any() and rent_max.notna().any():
        lower = max(0, int(math.floor(rent_min.min() / RENT_BUDGET_STEP) * RENT_BUDGET_STEP))
        upper = int(math.ceil(rent_max.max() / RENT_BUDGET_STEP) * RENT_BUDGET_STEP)
        return lower, max(upper, lower + RENT_BUDGET_STEP)
    return 0, 3000


def _property_group_options(df):
    counts = df["property_group"].fillna("other").value_counts().to_dict()
    labels = [("house", "House"), ("apartment", "Apartment"), ("townhouse", "Townhouse"), ("land", "Land"), ("other", "Other")]
    return [(group, tr(label, label), int(counts.get(group, 0))) for group, label in labels if counts.get(group, 0) > 0]


def _subtype_counts(df, group):
    subset = df.loc[df["property_group"] == group, "property_subtype"].fillna("unknown")
    return subset.value_counts().sort_values(ascending=False)


def _filter_external_extreme_rents(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    filtered = df.copy()
    rent_mid = pd.to_numeric(filtered.get("rent_mid"), errors="coerce")
    rent_min = pd.to_numeric(filtered.get("rent_filter_min"), errors="coerce")
    rent_max = pd.to_numeric(filtered.get("rent_filter_max"), errors="coerce")

    clear_extreme = rent_mid.gt(EXTERNAL_MAX_WEEKLY_RENT)
    clear_extreme = clear_extreme.fillna(False)

    no_mid_but_extreme_range = rent_mid.isna() & rent_min.gt(EXTERNAL_MAX_WEEKLY_RENT) & rent_max.gt(EXTERNAL_MAX_WEEKLY_RENT)
    no_mid_but_extreme_range = no_mid_but_extreme_range.fillna(False)

    return filtered.loc[~(clear_extreme | no_mid_but_extreme_range)].copy()


def _format_budget_input(value):
    return f"{int(value):,}"


def _parse_budget_input(value):
    if value is None:
        return None
    digits = re.sub(r"[^\d]", "", str(value).strip())
    return int(digits) if digits else None


def _normalise_budget_value(value, min_budget, max_budget):
    clamped = max(min_budget, min(max_budget, int(value)))
    return int(round(clamped / RENT_BUDGET_STEP) * RENT_BUDGET_STEP)


def _init_state():
    st.session_state.setdefault("rent_shortlist_ids", [])
    st.session_state.setdefault("rent_shortlist_items", {})
    st.session_state.setdefault("rent_selected_suburb", "__ALL__")
    st.session_state.setdefault("rent_map_focus_token", None)
    st.session_state.setdefault("rent_map_view", {"center": None, "zoom": None})
    st.session_state.setdefault("rent_focus_notice", None)
    st.session_state.setdefault("rent_commute_notice", None)
    st.session_state.setdefault("rent_group_notice", None)
    st.session_state.setdefault("rent_external_search_triggered", False)


def _consume_focus_notice(key):
    notice = st.session_state.get(key)
    st.session_state[key] = None
    return notice


def _ensure_budget_input_state(min_budget, max_budget):
    st.session_state.setdefault("rent_budget_range_slider", (min_budget, max_budget))
    current_min, current_max = st.session_state["rent_budget_range_slider"]
    current_min = _normalise_budget_value(current_min, min_budget, max_budget)
    current_max = _normalise_budget_value(current_max, min_budget, max_budget)
    if current_min > current_max:
        current_min, current_max = min_budget, max_budget
    st.session_state["rent_budget_range_slider"] = (current_min, current_max)
    st.session_state.setdefault("rent_budget_min_input", _format_budget_input(current_min))
    st.session_state.setdefault("rent_budget_max_input", _format_budget_input(current_max))
    st.session_state.setdefault("rent_budget_input_error", None)


def _apply_pending_budget_widget_state(min_budget, max_budget):
    pending_range = st.session_state.pop("rent_budget_pending_range", None)
    if pending_range is None:
        return
    budget_min = _normalise_budget_value(pending_range[0], min_budget, max_budget)
    budget_max = _normalise_budget_value(pending_range[1], min_budget, max_budget)
    if budget_min > budget_max:
        budget_min, budget_max = min_budget, max_budget
    st.session_state["rent_budget_range_slider"] = (budget_min, budget_max)
    st.session_state["rent_budget_min_input"] = _format_budget_input(budget_min)
    st.session_state["rent_budget_max_input"] = _format_budget_input(budget_max)


def _resolve_budget_submit_form_safe(*, min_budget, max_budget, slider_range, text_min_raw, text_max_raw):
    slider_min = _normalise_budget_value(slider_range[0], min_budget, max_budget)
    slider_max = _normalise_budget_value(slider_range[1], min_budget, max_budget)
    parsed_min = _parse_budget_input(text_min_raw)
    parsed_max = _parse_budget_input(text_max_raw)
    use_text_override = parsed_min is not None and parsed_max is not None

    if use_text_override:
        budget_min = _normalise_budget_value(parsed_min, min_budget, max_budget)
        budget_max = _normalise_budget_value(parsed_max, min_budget, max_budget)
        if budget_min > budget_max:
            st.session_state["rent_budget_input_error"] = tr("最低租金预算不能高于最高租金预算。", "Minimum rent budget cannot be higher than maximum rent budget.")
            budget_min, budget_max = slider_min, slider_max
        else:
            st.session_state["rent_budget_input_error"] = None
    else:
        budget_min, budget_max = slider_min, slider_max
        text_min_present = bool(str(text_min_raw or "").strip())
        text_max_present = bool(str(text_max_raw or "").strip())
        if text_min_present or text_max_present:
            st.session_state["rent_budget_input_error"] = tr("租金预算输入无效，已使用滑块预算区间。", "Rent budget inputs were invalid, so the slider range was used.")
        else:
            st.session_state["rent_budget_input_error"] = None

    formatted_min = _format_budget_input(budget_min)
    formatted_max = _format_budget_input(budget_max)
    needs_widget_sync = (
        st.session_state.get("rent_budget_range_slider") != (budget_min, budget_max)
        or st.session_state.get("rent_budget_min_input") != formatted_min
        or st.session_state.get("rent_budget_max_input") != formatted_max
    )
    if needs_widget_sync:
        st.session_state["rent_budget_pending_range"] = (budget_min, budget_max)
    st.session_state["rent_budget_applied_range"] = (budget_min, budget_max)
    return needs_widget_sync


def _get_shortlist_ids():
    _init_state()
    return set(st.session_state["rent_shortlist_ids"])


def _set_shortlist_ids(ids):
    st.session_state["rent_shortlist_ids"] = sorted(ids)


def _snapshot_listing(row):
    return row.to_dict()


def _toggle_shortlist(listing_id, row=None):
    shortlist_ids = _get_shortlist_ids()
    shortlist_items = st.session_state.setdefault("rent_shortlist_items", {})
    if listing_id in shortlist_ids:
        shortlist_ids.remove(listing_id)
        shortlist_items.pop(listing_id, None)
    else:
        shortlist_ids.add(listing_id)
        if row is not None:
            shortlist_items[listing_id] = _snapshot_listing(row)
    _set_shortlist_ids(shortlist_ids)


def _selected_suburb():
    return st.session_state["rent_selected_suburb"]


def _set_selected_suburb(suburb):
    st.session_state["rent_selected_suburb"] = suburb


def _clear_suburb_focus():
    _set_selected_suburb("__ALL__")
    st.session_state["rent_focus_notice"] = None


def _reset_ranking_filters():
    st.session_state["rent_ranking_search"] = ""
    st.session_state["rent_ranking_min_listings"] = 1 if IS_EXTERNAL_MODE else 3


def _set_map_view(center, zoom):
    st.session_state["rent_map_view"] = {"center": center, "zoom": zoom}


def _default_rent_filters(min_budget, max_budget):
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
        "selected_sort": tr("周租从低到高", "Weekly rent low to high"),
        "show_subtypes": False,
    }


def _merge_rent_filter_defaults(saved, min_budget, max_budget):
    merged = _default_rent_filters(min_budget, max_budget)
    if saved:
        merged.update(saved)
    merged["budget_min"] = _normalise_budget_value(int(merged["budget_min"]), min_budget, max_budget)
    merged["budget_max"] = _normalise_budget_value(int(merged["budget_max"]), min_budget, max_budget)
    merged["selected_sort"] = _coerce_rent_sort_key(merged.get("selected_sort"))
    if merged["budget_min"] > merged["budget_max"]:
        merged["budget_min"], merged["budget_max"] = min_budget, max_budget
    return merged


def _rent_sort_labels():
    return {
        "rent_asc": tr("周租从低到高", "Weekly rent low to high"),
        "rent_desc": tr("周租从高到低", "Weekly rent high to low"),
        "available_asc": tr("最早可入住", "Earliest available"),
        "bedrooms_desc": tr("卧室数", "Bedrooms"),
        "suburb_asc": tr("Suburb", "Suburb"),
    }


def _coerce_rent_sort_key(value):
    current = str(value or "").strip()
    if current in RENT_SORT_SPECS:
        return current
    reverse = {label: key for key, label in _rent_sort_labels().items()}
    legacy_map = {
        "Weekly rent low to high": "rent_asc",
        "周租从低到高": "rent_asc",
        "Weekly rent high to low": "rent_desc",
        "周租从高到低": "rent_desc",
        "Earliest available": "available_asc",
        "最早可入住": "available_asc",
        "Bedrooms": "bedrooms_desc",
        "卧室数": "bedrooms_desc",
        "Suburb": "suburb_asc",
    }
    return reverse.get(current) or legacy_map.get(current, "rent_asc")


def _rent_sort_label(sort_key):
    return _rent_sort_labels().get(_coerce_rent_sort_key(sort_key), _rent_sort_labels()["rent_asc"])


def _sync_external_rent_widget_state_from_applied(applied, external_budget_options):
    st.session_state["rent_selected_suburbs"] = list(applied.get("selected_suburbs", []))
    st.session_state["rent_selected_postcodes"] = list(applied.get("selected_postcodes", []))
    st.session_state["rent_selected_property_groups"] = list(applied.get("selected_property_groups", []))
    st.session_state["rent_min_bedrooms"] = int(applied.get("min_bedrooms", 0))
    st.session_state["rent_min_bathrooms"] = int(applied.get("min_bathrooms", 0))
    st.session_state["rent_min_parking"] = int(applied.get("min_parking", 0))
    st.session_state["rent_exact_bedrooms"] = bool(applied.get("exact_bedrooms", False))
    st.session_state["rent_exact_bathrooms"] = bool(applied.get("exact_bathrooms", False))
    st.session_state["rent_exact_parking"] = bool(applied.get("exact_parking", False))
    st.session_state["rent_selected_sort"] = str(applied.get("selected_sort", tr("周租从低到高", "Weekly rent low to high")))
    st.session_state["rent_show_subtypes"] = bool(applied.get("show_subtypes", False))
    st.session_state["rent_commute_query"] = str(applied.get("commute_query", ""))
    st.session_state["rent_commute_mode"] = str(applied.get("commute_mode", "drive"))
    st.session_state["rent_commute_minutes"] = int(applied.get("commute_minutes", 30))
    st.session_state["rent_selected_sort"] = _coerce_rent_sort_key(st.session_state.get("rent_selected_sort"))
    st.session_state["rent_budget_external_applied_range"] = _coerce_external_rent_budget_range(
        (int(applied.get("budget_min", 75)), int(applied.get("budget_max", 5000))),
        options=external_budget_options,
        default_range=(75, 5000),
    )


def _initialise_external_rent_widget_state_from_applied(applied, external_budget_options):
    widget_defaults = {
        "rent_selected_suburbs": list(applied.get("selected_suburbs", [])),
        "rent_selected_postcodes": list(applied.get("selected_postcodes", [])),
        "rent_selected_property_groups": list(applied.get("selected_property_groups", [])),
        "rent_min_bedrooms": int(applied.get("min_bedrooms", 0)),
        "rent_min_bathrooms": int(applied.get("min_bathrooms", 0)),
        "rent_min_parking": int(applied.get("min_parking", 0)),
        "rent_exact_bedrooms": bool(applied.get("exact_bedrooms", False)),
        "rent_exact_bathrooms": bool(applied.get("exact_bathrooms", False)),
        "rent_exact_parking": bool(applied.get("exact_parking", False)),
        "rent_selected_sort": str(applied.get("selected_sort", tr("周租从低到高", "Weekly rent low to high"))),
        "rent_show_subtypes": bool(applied.get("show_subtypes", False)),
        "rent_commute_query": str(applied.get("commute_query", "")),
        "rent_commute_mode": str(applied.get("commute_mode", "drive")),
        "rent_commute_minutes": int(applied.get("commute_minutes", 30)),
    }
    for key, value in widget_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    st.session_state["rent_selected_sort"] = _coerce_rent_sort_key(st.session_state.get("rent_selected_sort"))
    st.session_state["rent_budget_external_applied_range"] = _coerce_external_rent_budget_range(
        (int(applied.get("budget_min", 75)), int(applied.get("budget_max", 5000))),
        options=external_budget_options,
        default_range=(75, 5000),
    )


def _reset_external_rent_filters(min_budget, max_budget, external_budget_options):
    defaults = _merge_rent_filter_defaults({}, min_budget, max_budget)
    st.session_state["rent_budget_applied_filters"] = defaults
    st.session_state["rent_pending_reset"] = True
    st.session_state["rent_external_search_triggered"] = False


def _apply_pending_external_rent_reset(external_budget_options):
    if not st.session_state.pop("rent_pending_reset", False):
        return
    defaults = _merge_rent_filter_defaults(st.session_state.get("rent_budget_applied_filters"), 75, 5000)
    _sync_external_rent_widget_state_from_applied(defaults, external_budget_options)
    for key in list(st.session_state.keys()):
        if key.startswith("rent_subtypes_"):
            del st.session_state[key]
    st.session_state["rent_selected_group_labels"] = []
    st.session_state["rent_commute_notice"] = None
    st.session_state["rent_group_notice"] = None
    st.session_state["rent_focus_notice"] = None
    st.session_state["rent_selected_suburb"] = "__ALL__"


def _format_applied_threshold(label, value, *, exact):
    suffix = f"{value}" if exact else f"{value}+"
    return f"{label}: {suffix}"


def _format_applied_commute_summary(filters):
    commute_label = str(filters.get("commute_label", "") or "").strip()
    if commute_label:
        return commute_label

    commute_query = str(filters.get("commute_query", "") or "").strip()
    if not commute_query:
        return None

    commute_mode = str(filters.get("commute_mode", "drive") or "drive")
    commute_minutes = int(filters.get("commute_minutes", 30) or 30)
    mode_label = {
        "drive": tr("开车", "Drive"),
        "transit": tr("公共交通", "Public transport"),
        "walk": tr("步行", "Walking"),
    }.get(commute_mode, tr("开车", "Drive"))
    return tr("通勤：", "Commute:") + f" {commute_minutes} " + tr(
        f"分钟{mode_label}到",
        f"min {mode_label.lower()} to" if isinstance(mode_label, str) else "min commute to",
    ) + f" {commute_query}"


def _valid_selected(values, valid_options):
    valid_set = set(valid_options)
    return [value for value in (values or []) if value in valid_set]


def _build_shortlist_df(df):
    shortlist_ids = _get_shortlist_ids()
    shortlist_df = df.loc[df["listing_id"].astype(str).isin(shortlist_ids)].copy()
    current_ids = set(shortlist_df["listing_id"].astype(str).tolist())
    stored_items = st.session_state.get("rent_shortlist_items", {})
    missing_rows = [stored_items[item_id] for item_id in shortlist_ids if item_id not in current_ids and item_id in stored_items]
    if missing_rows:
        shortlist_df = pd.concat([shortlist_df, pd.DataFrame(missing_rows)], ignore_index=True, sort=False)
    if shortlist_df.empty:
        return shortlist_df
    return shortlist_df.drop_duplicates(subset=["listing_id"], keep="first")


def _full_budget_selected(current_min, current_max, absolute_min, absolute_max):
    return current_min == absolute_min and current_max == absolute_max


def _normalise_suburb_key(value):
    if value is None or pd.isna(value):
        return ""
    text = str(value).upper().strip()
    text = re.sub(r"\([^)]*\)", "", text)
    text = text.replace("-", " ").replace("&", " AND ").replace("'", "")
    text = re.sub(r"\bMT\b", "MOUNT", text)
    text = re.sub(r"\bNSW\b", "", text)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = " ".join(text.split())
    return SUBURB_JOIN_ALIASES.get(text, text)


def _flatten_coords(node):
    if not isinstance(node, list) or not node:
        return []
    if isinstance(node[0], (int, float)) and len(node) >= 2:
        return [(float(node[0]), float(node[1]))]
    points = []
    for item in node:
        points.extend(_flatten_coords(item))
    return points


def _geometry_centroid(geometry):
    coords = _flatten_coords((geometry or {}).get("coordinates"))
    if not coords:
        return None, None
    lon = sum(point[0] for point in coords) / len(coords)
    lat = sum(point[1] for point in coords) / len(coords)
    return lat, lon


def _simplify_geometry_coords(node):
    if not isinstance(node, list) or not node:
        return node
    first = node[0]
    if isinstance(first, (int, float)):
        return node
    if first and isinstance(first[0], (int, float)):
        body = node[:-1]
        step = 1 if len(node) <= 120 else 2 if len(node) <= 300 else 3 if len(node) <= 700 else 5
        if step == 1:
            return node
        simplified = body[::step]
        if body and simplified[-1] != body[-1]:
            simplified.append(body[-1])
        if simplified[0] != simplified[-1]:
            simplified.append(simplified[0])
        return simplified if len(simplified) >= 4 else node
    return [_simplify_geometry_coords(item) for item in node]


@st.cache_data(show_spinner=False)
def _load_suburb_boundaries():
    base_dir = Path(__file__).resolve().parents[1]
    abs_dir = base_dir / "Reference" / "ABS"
    path = abs_dir / "nsw_suburbs.geojson"
    if not path.exists():
        return {"available": False, "path": str(path), "geojson": None, "centroids": pd.DataFrame(), "polygons": pd.DataFrame()}
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features", [])
    render_features, polygon_rows = [], []
    for idx, feature in enumerate(features):
        properties = feature.get("properties", {})
        suburb_name = properties.get("suburb_name") or properties.get("SSC_NAME21") or properties.get("name")
        suburb_key = properties.get("join_key") or _normalise_suburb_key(suburb_name)
        if not suburb_key or not feature.get("geometry"):
            continue
        feature_id = str(properties.get("feature_id") or properties.get("suburb_code") or idx)
        render_features.append({"type": "Feature", "properties": {"feature_id": feature_id, "join_key": suburb_key, "suburb_name": suburb_name}, "geometry": {"type": feature["geometry"]["type"], "coordinates": _simplify_geometry_coords(feature["geometry"]["coordinates"])}})
        lat, lon = _geometry_centroid(feature.get("geometry"))
        polygon_rows.append({"feature_id": feature_id, "geo_suburb_key": suburb_key, "boundary_suburb_name": suburb_name, "boundary_latitude": lat, "boundary_longitude": lon})
    polygon_df = pd.DataFrame(polygon_rows)
    centroids = polygon_df.groupby("geo_suburb_key", dropna=False).agg(boundary_suburb_name=("boundary_suburb_name", "first"), boundary_latitude=("boundary_latitude", "mean"), boundary_longitude=("boundary_longitude", "mean")).reset_index()
    return {"available": True, "path": str(path), "geojson": {"type": "FeatureCollection", "features": render_features}, "centroids": centroids, "polygons": polygon_df}


def _render_filter_chips(selected_property_groups, selected_property_subtypes, selected_suburbs, selected_postcodes, min_bedrooms, min_bathrooms, min_parking, commute_label=None):
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
        chips.append(f"{tr('卧室', 'Beds')} = {min_bedrooms}" if st.session_state.get("rent_exact_bedrooms", False) else f"{tr('卧室', 'Beds')} {min_bedrooms}+")
    if min_bathrooms:
        chips.append(f"{tr('卫生间', 'Baths')} = {min_bathrooms}" if st.session_state.get("rent_exact_bathrooms", False) else f"{tr('卫生间', 'Baths')} {min_bathrooms}+")
    if min_parking:
        chips.append(f"{tr('车位', 'Parking')} = {min_parking}" if st.session_state.get("rent_exact_parking", False) else f"{tr('车位', 'Parking')} {min_parking}+")
    if commute_label:
        chips.append(commute_label)
    if not chips:
        chips.append(tr("当前为宽筛选模式", "Currently using a broad search"))
    st.markdown("".join(f"<span class='budget-chip'>{item}</span>" for item in chips), unsafe_allow_html=True)


def _apply_rent_filters(df, *, budget_min, budget_max, min_budget, max_budget, selected_property_groups=None, selected_property_subtypes=None, selected_suburbs=None, selected_postcodes=None, min_bedrooms=0, min_bathrooms=0, min_parking=0, exact_bedrooms=False, exact_bathrooms=False, exact_parking=False, allowed_listing_ids=None, allowed_suburbs=None, include_budget=True, skip_filters=None):
    skip_filters = skip_filters or set()
    frames = [("loaded", int(len(df)))]
    filtered = df.copy()
    if include_budget:
        full_budget_selected = _full_budget_selected(budget_min, budget_max, min_budget, max_budget)
        budget_contained = filtered["has_rent"] & (filtered["rent_filter_min"] >= budget_min) & (filtered["rent_filter_max"] <= budget_max)
        filtered = filtered.loc[budget_contained | (full_budget_selected & ~filtered["has_rent"])].copy()
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


def _suburb_summary(context_df, *, budget_min, budget_max):
    suburb_df = context_df.loc[context_df["suburb"].notna()].copy()
    if suburb_df.empty:
        return pd.DataFrame()
    suburb_df["within_budget"] = suburb_df["has_rent"].fillna(False) & (suburb_df["rent_filter_min"] <= budget_max) & (suburb_df["rent_filter_max"] >= budget_min)
    suburb_df["priced_listing"] = suburb_df["has_rent"].fillna(False).astype(int)
    suburb_df["unknown_price"] = (~suburb_df["has_rent"].fillna(False)).astype(int)
    summary = suburb_df.groupby("suburb", dropna=False).agg(listing_count=("listing_id", "count"), median_weekly_rent=("rent_mid", "median"), latitude=("latitude", "median"), longitude=("longitude", "median"), within_budget_count=("within_budget", "sum"), priced_listings_count=("priced_listing", "sum"), unknown_price_count=("unknown_price", "sum"), coordinate_count=("has_coordinates", "sum")).reset_index()
    summary["geo_suburb_key"] = summary["suburb"].map(_normalise_suburb_key)
    priced_denominator = pd.to_numeric(summary["priced_listings_count"], errors="coerce").replace({0: pd.NA}).astype("Float64")
    summary["coverage_ratio"] = (pd.to_numeric(summary["within_budget_count"], errors="coerce") / priced_denominator).astype("Float64").fillna(0.0).clip(0.0, 1.0)
    summary["total_listings_count"] = summary["listing_count"].astype(int)
    summary["total_priced_listings"] = summary["priced_listings_count"]
    return summary.sort_values(["coverage_ratio", "within_budget_count", "total_priced_listings", "median_weekly_rent", "suburb"], ascending=[False, False, False, True, True], na_position="last").reset_index(drop=True)


def _rent_signal_label(coverage_ratio, listing_count):
    if listing_count <= 3 or coverage_ratio < 0.20:
        return tr("预算偏紧", "Budget is tight")
    if listing_count <= 12 or coverage_ratio < 0.55:
        return tr("预算适中", "Budget is balanced")
    return tr("预算较宽裕", "Budget is comfortable")


def _rent_status_from_distribution(priced, budget_max):
    if priced.empty:
        return tr("预算适中", "Budget is balanced"), 0.0
    prices = pd.to_numeric(priced["rent_mid"], errors="coerce").dropna()
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


def _rent_insight(scope_df, context_df, summary, *, focused_suburb, budget_max):
    priced = scope_df.loc[scope_df["has_rent"]]
    context_priced = context_df.loc[context_df["has_rent"]]
    typical_weekly_rent = priced["rent_mid"].median() if not priced.empty else pd.NA
    signal_label, coverage_ratio = _rent_status_from_distribution(context_priced, budget_max)
    listing_count = int(len(scope_df))
    suburb_count = int(scope_df["suburb"].dropna().nunique())
    conclusion = (
        tr(
            f"当前聚焦 suburb 内共有 {listing_count} 套匹配租盘，主流为 {_title_case_subtype(_mode_or_na(scope_df['property_subtype']))}，预算状态为{signal_label}。",
            f"The focused suburb has {listing_count} matching rentals, led by {_title_case_subtype(_mode_or_na(scope_df['property_subtype']))}, with a rental budget position of {signal_label}.",
        )
        if focused_suburb != "__ALL__"
        else tr(
            f"当前筛选下覆盖 {suburb_count} 个 suburb，共 {listing_count} 套匹配租盘，主流为 {_title_case_subtype(_mode_or_na(scope_df['property_subtype']))}，预算状态为{signal_label}。",
            f"The current scope covers {suburb_count} suburbs and {listing_count} matching rentals, led by {_title_case_subtype(_mode_or_na(scope_df['property_subtype']))}, with an overall rental budget position of {signal_label}.",
        )
    )
    return {"typical_weekly_rent": typical_weekly_rent, "coverage_ratio": float(coverage_ratio), "suburb_count": suburb_count, "listing_count": listing_count, "common_type": _title_case_subtype(_mode_or_na(scope_df["property_subtype"])), "common_bedrooms": _mode_or_na(scope_df["bedrooms"]), "signal_label": signal_label, "conclusion": conclusion}


def _render_suburb_ranking(summary):
    if summary.empty:
        st.info(tr("当前筛选条件下没有可选 suburb。", "No suburbs are available under the current filters."))
        return
    focused_suburb = _selected_suburb()
    total_available = len(summary)
    controls = st.columns([1.7, 1.0, 1.0] if IS_EXTERNAL_MODE else [1.35, 0.85, 0.9, 0.9])
    with controls[0]:
        search_value = st.text_input(tr("Search suburb", "Search suburb"), key="rent_ranking_search", placeholder=tr("Type part of a suburb name", "Type part of a suburb name")).strip()
    if not IS_EXTERNAL_MODE:
        with controls[1]:
            min_listings = int(st.number_input(tr("Min listings", "Min listings"), min_value=1, max_value=500, value=int(st.session_state.get("rent_ranking_min_listings", 3)), step=1, key="rent_ranking_min_listings"))
        reset_col = controls[2]
        focus_col = controls[3]
    else:
        min_listings = int(st.session_state.get("rent_ranking_min_listings", 1))
        reset_col = controls[1]
        focus_col = controls[2]
    with reset_col:
        if st.button(tr("Reset ranking filters", "Reset ranking filters"), use_container_width=True):
            _reset_ranking_filters()
            st.rerun()
    with focus_col:
        if st.button(tr("Reset suburb focus", "Reset suburb focus"), use_container_width=True, disabled=focused_suburb == "__ALL__"):
            _clear_suburb_focus()
            st.rerun()
    ranking = summary.copy()
    if search_value:
        ranking = ranking.loc[ranking["suburb"].astype(str).str.contains(search_value, case=False, na=False)].copy()
    if focused_suburb != "__ALL__":
        ranking = ranking.loc[ranking["suburb"] == focused_suburb].copy()
    if focused_suburb == "__ALL__" and not IS_EXTERNAL_MODE:
        ranking = ranking.loc[ranking["priced_listings_count"] >= min_listings].copy()
    ranking = ranking.reset_index(drop=True)
    shown_count = len(ranking) if IS_EXTERNAL_MODE else min(len(ranking), 50)
    st.caption(tr(f"显示 {shown_count:,} / {total_available:,} 个 suburb", f"Showing {shown_count:,} of {total_available:,} suburbs"))
    if ranking.empty:
        st.warning(tr(f"排名筛选后 0 / {total_available:,} 个 suburb 可显示。", f"Showing 0 of {total_available:,} suburbs after ranking filters."))
        return
    view = ranking.copy() if IS_EXTERNAL_MODE else ranking.head(50).copy()
    view[tr("聚焦", "Focus")] = view["suburb"].eq(focused_suburb).map({True: tr("已聚焦", "Focused"), False: ""})
    view[tr("覆盖率 %", "Coverage %")] = (view["coverage_ratio"] * 100).round().astype(int)
    view[tr("预算内", "Within Budget")] = view["within_budget_count"].astype(int)
    view[tr("有报价", "Priced Listings")] = view["priced_listings_count"].astype(int)
    view[tr("总挂牌", "Total Listings")] = view["total_listings_count"].astype(int)
    view[tr("典型周租", "Typical Weekly Rent")] = view["median_weekly_rent"].map(_compact_weekly_rent)
    if IS_EXTERNAL_MODE:
        _render_external_rent_ranking_table(view, focused_suburb=focused_suburb, key_prefix="rent_ranking")
        return
    selection = st.dataframe(view[[tr("聚焦", "Focus"), "suburb", tr("覆盖率 %", "Coverage %"), tr("预算内", "Within Budget"), tr("有报价", "Priced Listings"), tr("总挂牌", "Total Listings"), tr("典型周租", "Typical Weekly Rent")]].rename(columns={"suburb": tr("Suburb", "Suburb")}), use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key="rent_ranking_table")
    picked_rows = selection.get("selection", {}).get("rows", []) if isinstance(selection, dict) else (getattr(getattr(selection, "selection", None), "rows", []) or [])
    if picked_rows:
        picked_suburb = str(view.iloc[picked_rows[0]]["suburb"])
        if picked_suburb != focused_suburb:
            _set_selected_suburb(picked_suburb)
            st.rerun()


def _resolve_map_selection(event_state):
    selection = getattr(event_state, "selection", None) if event_state is not None else None
    if selection is None and isinstance(event_state, dict):
        selection = event_state.get("selection")
    if not selection:
        return None
    points = getattr(selection, "points", None) if not isinstance(selection, dict) else selection.get("points")
    if not points:
        return None
    point = points[0]
    customdata = point.get("customdata") if isinstance(point, dict) else getattr(point, "customdata", None)
    if isinstance(customdata, (list, tuple)) and len(customdata) >= 2 and customdata[1] == "suburb":
        suburb = str(customdata[0]).strip()
        return suburb or None
    return None


def _resolve_map_view(map_summary, map_df, selected_suburb):
    boundaries = _load_suburb_boundaries() if not IS_EXTERNAL_MODE else {"geojson": None}
    center, zoom = resolve_budget_map_view(
        selected_suburb=selected_suburb,
        suburb_key=_normalise_suburb_key(selected_suburb) if selected_suburb != "__ALL__" else None,
        map_summary=map_summary,
        map_df=map_df,
        boundary_geojson=boundaries.get("geojson"),
    )
    if IS_EXTERNAL_MODE:
        center, zoom = clamp_to_nsw_map_view(center, zoom)
    st.session_state["rent_map_focus_token"] = selected_suburb
    _set_map_view(center, zoom)
    return center, zoom


def _build_map(context_df, suburb_summary, selected_suburb):
    map_df = context_df.loc[context_df["has_coordinates"]].copy()
    boundaries = _load_suburb_boundaries() if not IS_EXTERNAL_MODE else {
        "available": False,
        "path": "",
        "geojson": None,
        "centroids": pd.DataFrame(),
        "polygons": pd.DataFrame(),
    }
    map_summary = suburb_summary.copy()
    if map_df.empty and map_summary.empty:
        st.info(tr("当前筛选结果没有可用坐标，地图暂时无法展示。", "No coordinates are available for the current filters."))
        return selected_suburb
    centroids = boundaries["centroids"]
    polygons = boundaries["polygons"]
    if not centroids.empty:
        map_summary = map_summary.merge(centroids, on="geo_suburb_key", how="left")
        map_summary["map_latitude"] = map_summary["boundary_latitude"].fillna(map_summary["latitude"])
        map_summary["map_longitude"] = map_summary["boundary_longitude"].fillna(map_summary["longitude"])
    else:
        map_summary["map_latitude"] = map_summary["latitude"]
        map_summary["map_longitude"] = map_summary["longitude"]
    map_summary = map_summary.loc[map_summary["map_latitude"].notna() & map_summary["map_longitude"].notna()].copy()
    center, zoom = _resolve_map_view(map_summary, map_df, selected_suburb)
    if IS_EXTERNAL_MODE:
        fig = go.Figure()
        if not map_summary.empty:
            fig.add_trace(go.Scattermapbox(lat=map_summary["map_latitude"], lon=map_summary["map_longitude"], mode="markers", marker=dict(size=(9 + 14 * (map_summary["listing_count"] / max(float(map_summary["listing_count"].max()), 1.0))).tolist(), color=map_summary["suburb"].eq(selected_suburb).map({True: "#0f4c81", False: "#1d6f8c"}).tolist(), opacity=0.76), customdata=list(zip(map_summary["suburb"], ["suburb"] * len(map_summary), map_summary["listing_count"])), hovertemplate="<b>%{customdata[0]}</b><br>Matching listings: %{customdata[2]:,.0f}<br>Click to focus suburb<extra></extra>", name="Suburb selector"))
        focus_points = map_df.loc[map_df["suburb"] == selected_suburb].copy() if selected_suburb != "__ALL__" else pd.DataFrame()
        sampled = False
        if not focus_points.empty:
            focus_points = focus_points.sort_values(by=["rent_mid", "available_date"], ascending=[True, True], na_position="last")
            if len(focus_points) > 180:
                focus_points = focus_points.head(180)
                sampled = True
            fig.add_trace(go.Scattermapbox(lat=focus_points["latitude"], lon=focus_points["longitude"], mode="markers", marker=dict(size=8, color="#0d5ea6", opacity=0.86), customdata=list(zip(focus_points["suburb"], ["listing"] * len(focus_points), focus_points["rent_display"].fillna("N/A"))), text=focus_points["address"].fillna(""), hovertemplate="<b>%{text}</b><br>Suburb: %{customdata[0]}<br>Rent: %{customdata[2]}<extra></extra>", name="Rental listings"))
        fig.update_layout(height=MAP_HEIGHT, margin={"l": 0, "r": 0, "t": 0, "b": 0}, mapbox=dict(style="carto-positron", center=center, zoom=zoom, bounds=NSW_MAP_BOUNDS if IS_EXTERNAL_MODE else None), legend=dict(orientation="h", yanchor="bottom", y=0.01, xanchor="left", x=0.01), uirevision=f"rent-map-{selected_suburb}")
        event_state = st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True, "scrollZoom": True}, key="rent_map_chart", on_select="rerun", selection_mode="points")
        picked_suburb = _resolve_map_selection(event_state)
        if picked_suburb and picked_suburb != selected_suburb:
            _set_selected_suburb(picked_suburb)
            st.rerun()
        if sampled:
            st.caption(tr("当前地图中的租盘点位仅展示前 180 条，以保持 External 页面响应速度。", "Rental markers are capped to the first 180 results in External mode to keep the page responsive."))
        return selected_suburb
    fig = go.Figure()
    if boundaries["available"] and boundaries["geojson"] is not None:
        feature_ids = [str(feature["properties"].get("feature_id")) for feature in boundaries["geojson"].get("features", [])]
        if feature_ids:
            fig.add_trace(go.Choroplethmapbox(geojson=boundaries["geojson"], locations=feature_ids, z=[0] * len(feature_ids), featureidkey="properties.feature_id", zmin=0, zmax=1, colorscale=[[0.0, "#d9d9d9"], [1.0, "#d9d9d9"]], marker_opacity=0.10, marker_line_width=0.6, hoverinfo="skip", showscale=False))
        choropleth_df = map_summary.merge(polygons[["feature_id", "geo_suburb_key"]], on="geo_suburb_key", how="inner").copy()
        if not choropleth_df.empty:
            active_ids = set(choropleth_df["feature_id"].astype(str).tolist())
            active_geojson = {"type": "FeatureCollection", "features": [feature for feature in boundaries["geojson"]["features"] if str(feature["properties"].get("feature_id")) in active_ids]}
            fig.add_trace(go.Choroplethmapbox(geojson=active_geojson, locations=choropleth_df["feature_id"], z=choropleth_df["coverage_ratio"].fillna(0.0).clip(0.0, 1.0), featureidkey="properties.feature_id", zmin=0, zmax=1, colorscale=[[0.0, "#eeeeee"], [0.25, "#ffe08a"], [0.50, "#a6d96a"], [0.75, "#4daf4a"], [1.0, "#1a9850"]], marker_opacity=0.72, marker_line_width=0.9, customdata=list(zip(choropleth_df["suburb"], (choropleth_df["coverage_ratio"] * 100).round(0), choropleth_df["within_budget_count"], choropleth_df["total_priced_listings"], choropleth_df["median_weekly_rent"].map(_compact_weekly_rent))), hovertemplate="<b>%{customdata[0]}</b><br>Coverage: %{customdata[1]:.0f}%<br>Within budget: %{customdata[2]:,.0f}<br>Total priced listings: %{customdata[3]:,.0f}<br>Typical weekly rent: %{customdata[4]}<extra></extra>", colorbar=dict(title="Coverage", thickness=14, x=0.99, len=0.45)))
    if not map_summary.empty:
        fig.add_trace(go.Scattermapbox(lat=map_summary["map_latitude"], lon=map_summary["map_longitude"], mode="markers", marker=dict(size=(8 + 16 * (map_summary["listing_count"] / max(float(map_summary["listing_count"].max()), 1.0))).tolist(), color=map_summary["suburb"].eq(selected_suburb).map({True: "#0f4c81", False: "#1d6f8c"}).tolist(), opacity=0.72), customdata=list(zip(map_summary["suburb"], ["suburb"] * len(map_summary), map_summary["listing_count"])), hovertemplate="<b>%{customdata[0]}</b><br>Matching listings: %{customdata[2]:,.0f}<br>Click to focus suburb<extra></extra>", name="Suburb selector"))
    focus_points = map_df.loc[map_df["suburb"] == selected_suburb].copy() if selected_suburb != "__ALL__" else pd.DataFrame()
    if not focus_points.empty:
        focus_points = focus_points.sort_values(by=["rent_mid", "available_date"], ascending=[True, True], na_position="last").head(350)
        fig.add_trace(go.Scattermapbox(lat=focus_points["latitude"], lon=focus_points["longitude"], mode="markers", marker=dict(size=9, color="#0d5ea6", opacity=0.88), customdata=list(zip(focus_points["suburb"], ["listing"] * len(focus_points), focus_points["rent_display"].fillna("N/A"))), text=focus_points["address"].fillna(""), hovertemplate="<b>%{text}</b><br>Suburb: %{customdata[0]}<br>Rent: %{customdata[2]}<extra></extra>", name="Rental listings"))
    fig.update_layout(height=MAP_HEIGHT, margin={"l": 0, "r": 0, "t": 0, "b": 0}, mapbox=dict(style="carto-positron", center=center, zoom=zoom, bounds=NSW_MAP_BOUNDS if IS_EXTERNAL_MODE else None), legend=dict(orientation="h", yanchor="bottom", y=0.01, xanchor="left", x=0.01), uirevision=f"rent-map-{selected_suburb}")
    event_state = st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": not IS_EXTERNAL_MODE, "responsive": True, "scrollZoom": True}, key="rent_map_chart", on_select="rerun", selection_mode="points")
    picked_suburb = _resolve_map_selection(event_state)
    if picked_suburb and picked_suburb != selected_suburb:
        _set_selected_suburb(picked_suburb)
        st.rerun()
    return selected_suburb


def _rent_display_label(row):
    if pd.notna(row.get("rent_display")) and str(row["rent_display"]).strip():
        return str(row["rent_display"]).strip()
    low, high = row.get("rent_filter_min"), row.get("rent_filter_max")
    if pd.notna(low) and pd.notna(high):
        return _weekly_money(low) if int(round(float(low))) == int(round(float(high))) else f"{_money(low)} - {_money(high)} pw"
    return tr("Rent on request", "Rent on request")


def _available_date_label(value):
    if value is None or pd.isna(value):
        return "N/A"
    return value.strftime("%Y-%m-%d") if isinstance(value, pd.Timestamp) else str(value)


def _listing_card(row, *, key_prefix):
    with st.container(border=True):
        if IS_EXTERNAL_MODE:
            content_col = st.container()
            image_col = None
        else:
            content_col, image_col = st.columns([2.2, 1])
        with content_col:
            st.markdown(f"### {_rent_display_label(row)}")
            st.markdown(f"**{row['address']}**")
            st.caption(f"{row['suburb']} / {row['postcode']}")
            st.write(f"{tr('Type', 'Type')}: {row['property_group_label']} / {_title_case_subtype(row['property_subtype'])}")
            st.write(f"{tr('Beds/Baths/Parking', 'Beds/Baths/Parking')}: {_feature_triplet(row)}")
            st.write(f"{tr('Available date', 'Available date')}: {_available_date_label(row['available_date'])}")
            st.write(f"{tr('Agency', 'Agency')}: {row['agency_name'] if pd.notna(row['agency_name']) else 'N/A'}")
            action_cols = st.columns(1 if IS_EXTERNAL_MODE else 2)
            with action_cols[0]:
                label = tr("移出 shortlist", "Remove") if str(row["listing_id"]) in _get_shortlist_ids() else tr("加入 shortlist", "Shortlist")
                if st.button(label, key=f"{key_prefix}_toggle_{row['listing_id']}", use_container_width=True):
                    _toggle_shortlist(str(row["listing_id"]), row)
                    st.rerun()
            if not IS_EXTERNAL_MODE:
                with action_cols[1]:
                    st.link_button(tr("打开租盘", "Open listing"), row["url"], use_container_width=True)
        if image_col is not None and pd.notna(row["main_image"]):
            with image_col:
                st.image(row["main_image"], use_container_width=True)


def _render_external_listing_row(row, *, key_prefix):
    with st.container():
        info_col, price_col, action_col = st.columns([4.6, 1.35, 1.55], gap="small")
        with info_col:
            st.markdown(
                f"""
                <div class="budget-list-row">
                  <div class="budget-list-address">{row['address'] if pd.notna(row.get('address')) else 'N/A'}</div>
                  <div class="budget-list-meta">
                    {row['suburb'] if pd.notna(row.get('suburb')) else 'N/A'} / {row['postcode'] if pd.notna(row.get('postcode')) else 'N/A'}<br>
                    {row['property_group_label']} / {_title_case_subtype(row['property_subtype'])} | {tr('Beds/Baths/Parking', 'Beds/Baths/Parking')}: {_feature_triplet(row)} | {tr('Available date', 'Available date')}: {_available_date_label(row['available_date'])}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with price_col:
            st.markdown(f"<div class='budget-list-price'>{_rent_display_label(row)}</div>", unsafe_allow_html=True)
            agency_label = row["agency_name"] if pd.notna(row.get("agency_name")) else tr("Contact agent", "Contact agent")
            st.markdown(f"<div class='budget-list-subprice'>{agency_label}</div>", unsafe_allow_html=True)
        with action_col:
            shortlisted = str(row["listing_id"]) in _get_shortlist_ids()
            label = tr("移出 shortlist", "Remove") if shortlisted else tr("加入 shortlist", "Shortlist")
            if st.button(label, key=f"{key_prefix}_toggle_{row['listing_id']}", use_container_width=True):
                _toggle_shortlist(str(row["listing_id"]), row)
                st.rerun()
            if False and pd.notna(row.get("url")):
                st.link_button(tr("打开租盘", "Open listing"), row["url"], use_container_width=True)


def _compact_count_cell(value):
    text = _count_label(value)
    return "—" if text == "N/A" else text


def _external_rent_table_headers():
    return [
        tr("周租", "Weekly Rent"),
        tr("地址", "Address"),
        tr("区域 / 邮编", "Suburb / Postcode"),
        tr("类型", "Type"),
        tr("卧室", "Beds"),
        tr("卫浴", "Baths"),
        tr("车位", "Parking"),
        tr("中介", "Agency"),
        tr("操作", "Action"),
    ]


def _render_external_rent_table(listings, *, key_prefix):
    widths = [1.0, 2.9, 1.6, 1.15, 0.55, 0.55, 0.65, 1.25, 0.95]
    header_cols = st.columns(widths, gap="small")
    for col, label in zip(header_cols, _external_rent_table_headers()):
        col.markdown(f"<div class='budget-table-head'>{label}</div>", unsafe_allow_html=True)

    for _, row in listings.iterrows():
        cols = st.columns(widths, gap="small")
        price_text = _rent_display_label(row)
        address_text = row["address"] if pd.notna(row.get("address")) else "N/A"
        url = ""
        address_html = address_text
        suburb_postcode = f"{row['suburb'] if pd.notna(row.get('suburb')) else '—'} / {row['postcode'] if pd.notna(row.get('postcode')) else '—'}"
        property_type = f"{row['property_group_label']} / {_title_case_subtype(row['property_subtype'])}"
        agency_label = row["agency_name"] if pd.notna(row.get("agency_name")) else tr("Contact agent", "Contact agent")

        cols[0].markdown(f"<div class='budget-table-row'><div class='budget-table-cell budget-table-price'>{price_text}</div></div>", unsafe_allow_html=True)
        cols[1].markdown(f"<div class='budget-table-row'><div class='budget-table-cell budget-table-address'>{address_html}</div></div>", unsafe_allow_html=True)
        cols[2].markdown(f"<div class='budget-table-row'><div class='budget-table-cell budget-table-muted'>{suburb_postcode}</div></div>", unsafe_allow_html=True)
        cols[3].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{property_type}</div></div>", unsafe_allow_html=True)
        cols[4].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{_compact_count_cell(row['bedrooms'])}</div></div>", unsafe_allow_html=True)
        cols[5].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{_compact_count_cell(row['bathrooms'])}</div></div>", unsafe_allow_html=True)
        cols[6].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{_compact_count_cell(row['parking'])}</div></div>", unsafe_allow_html=True)
        cols[7].markdown(f"<div class='budget-table-row'><div class='budget-table-cell budget-table-muted'>{agency_label}</div></div>", unsafe_allow_html=True)
        shortlisted = str(row["listing_id"]) in _get_shortlist_ids()
        action_label = tr("已选", "Saved") if shortlisted else tr("收藏", "Shortlist")
        if cols[8].button(action_label, key=f"{key_prefix}_toggle_{row['listing_id']}", use_container_width=True):
            _toggle_shortlist(str(row["listing_id"]), row)
            st.rerun()


def _render_external_rent_ranking_table(view, *, focused_suburb, key_prefix):
    widths = [0.9, 1.6, 0.9, 1.0, 1.0, 1.0, 1.0]
    headers = [
        tr("操作", "Action"),
        tr("Suburb", "Suburb"),
        tr("覆盖率 %", "Coverage %"),
        tr("预算内", "Within Budget"),
        tr("有报价", "Priced Listings"),
        tr("总挂牌", "Total Listings"),
        tr("典型周租", "Typical Weekly Rent"),
    ]
    header_cols = st.columns(widths, gap="small")
    for col, label in zip(header_cols, headers):
        col.markdown(f"<div class='budget-table-head'>{label}</div>", unsafe_allow_html=True)

    for _, row in view.iterrows():
        cols = st.columns(widths, gap="small")
        is_focused = str(row["suburb"]) == focused_suburb
        action_label = tr("已聚焦", "Focused") if is_focused else tr("聚焦", "Focus")
        if cols[0].button(action_label, key=f"{key_prefix}_focus_{row['suburb']}", use_container_width=True, disabled=is_focused):
            _set_selected_suburb(str(row["suburb"]))
            st.rerun()
        cols[1].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{row['suburb']}</div></div>", unsafe_allow_html=True)
        cols[2].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{int(row[tr('覆盖率 %', 'Coverage %')])}%</div></div>", unsafe_allow_html=True)
        cols[3].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{int(row[tr('预算内', 'Within Budget')]):,}</div></div>", unsafe_allow_html=True)
        cols[4].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{int(row[tr('有报价', 'Priced Listings')]):,}</div></div>", unsafe_allow_html=True)
        cols[5].markdown(f"<div class='budget-table-row'><div class='budget-table-cell'>{int(row[tr('总挂牌', 'Total Listings')]):,}</div></div>", unsafe_allow_html=True)
        cols[6].markdown(f"<div class='budget-table-row'><div class='budget-table-cell budget-table-price'>{row[tr('典型周租', 'Typical Weekly Rent')]}</div></div>", unsafe_allow_html=True)


def _format_summary_rent_range(min_value: int, max_value: int) -> str:
    return f"{_weekly_money(min_value)} – {_weekly_money(max_value)}"


def _prepare_external_display_listings(listings, *, sort_column, sort_ascending):
    return order_external_rent_listing_display(
        listings,
        primary_sort_col=sort_column,
        primary_sort_ascending=sort_ascending,
    )


def _render_listing_results(listings, selected_suburb):
    if listings.empty:
        st.info(tr("当前 suburb / 筛选条件下没有租盘。", "No rental listings match the current suburb or filters."))
        return
    label = selected_suburb if selected_suburb != "__ALL__" else tr("全部匹配 suburb", "All matching suburbs")
    st.caption(f"{tr('当前查看', 'Showing')}: {label} | {len(listings):,} {tr('套租盘', 'rentals')}")
    browse_limit = 24 if IS_EXTERNAL_MODE else 14
    if IS_EXTERNAL_MODE:
        _render_external_rent_table(listings.head(browse_limit), key_prefix="rent_browse")
    else:
        for _, row in listings.head(browse_limit).iterrows():
            _listing_card(row, key_prefix="rent_browse")
    if len(listings) > browse_limit:
        st.caption(tr(f"当前先展示前 {browse_limit} 条更适合浏览的结果。", f"Showing the first {browse_limit} results for easier browsing."))


def _render_shortlist_panel(shortlist_df):
    if shortlist_df.empty:
        st.info(tr("还没有加入 shortlist 的租盘。", "No rental listings have been shortlisted yet."))
        return
    if IS_EXTERNAL_MODE:
        _render_external_rent_table(shortlist_df, key_prefix="rent_shortlist")
    else:
        for _, row in shortlist_df.iterrows():
            _listing_card(row, key_prefix="rent_shortlist")


def _resolve_commute_filter(df, suburb_lookup, *, query, mode, max_minutes):
    origin = resolve_commute_origin(query, suburb_lookup, df)
    fallback_label = tr("通勤：", "Commute:") + f" {int(max_minutes)} " + tr(
        f"分钟{ {'drive': tr('开车', 'Drive'), 'transit': tr('公共交通', 'Public transport'), 'walk': tr('步行', 'Walking')}.get(mode, tr('开车', 'Drive')) }到",
        f"min { {'drive': 'drive', 'transit': 'public transport', 'walk': 'walking'}.get(mode, 'drive') } to",
    ) + f" {str(query).strip()}"
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
        mode_label = {
            "drive": tr("开车", "Drive"),
            "transit": tr("公共交通", "Public transport"),
            "walk": tr("步行", "Walking"),
        }.get(mode, tr("开车", "Drive"))
        chip = tr("通勤：", "Commute:") + f" {int(max_minutes)} " + tr(
            f"分钟{mode_label}到",
            f"min {mode_label.lower()} to" if isinstance(mode_label, str) else "min commute to",
        ) + f" {origin['label']}"
        return allowed_suburbs, set(), matched_suburbs, origin, chip
    matched = commute_df.loc[commute_df["commute_minutes"] <= float(max_minutes)].copy()
    allowed_suburbs = matched["suburb"].astype(str).dropna().drop_duplicates().tolist()
    allowed_listing_ids = set(matched["listing_id"].astype(str).dropna().tolist())
    mode_label = {
        "drive": tr("开车", "Drive"),
        "transit": tr("公共交通", "Public transport"),
        "walk": tr("步行", "Walking"),
    }.get(mode, tr("开车", "Drive"))
    chip = tr("通勤：", "Commute:") + f" {int(max_minutes)} " + tr(
        f"分钟{mode_label}到",
        f"min {mode_label.lower()} to" if isinstance(mode_label, str) else "min commute to",
    ) + f" {origin['label']}"
    return allowed_suburbs, allowed_listing_ids, matched, origin, chip


def _render_external_applied_filter_summary(filters, *, rent_mode):
    filters = dict(filters)
    filters["selected_sort"] = _rent_sort_label(filters.get("selected_sort"))
    lines = [
        tr("当前筛选：", "Active filters:"),
        f"{tr('周租预算', 'Weekly rent')}: {_format_summary_rent_range(int(filters['budget_min']), int(filters['budget_max']))}" if rent_mode else "",
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
    st.markdown("  \n".join([line for line in lines if line]))


def main():
    perf = PagePerf("rent_budget")
    ensure_lang()
    inject_app_theme()
    _init_state()
    if IS_EXTERNAL_MODE:
        with st.sidebar:
            sidebar_common(include_dwelling=False)
        render_external_page_header(
            badge=tr("Public Beta", "Public Beta"),
            title=tr("租房预算地图", "Rent Budget"),
            note=tr(
                "测试版可帮助你更快筛选符合预算、通勤和房型偏好的租盘与 suburb。",
                "Public beta to quickly narrow rentals and suburbs that fit your budget, commute, and property preferences.",
            ),
        )
    if not IS_EXTERNAL_MODE:
        st.markdown(f"<div class='budget-kicker'>{tr('租房工作流', 'Rental Workflow')}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='budget-title'>{tr('租金预算地图', 'Rent Budget Map')}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='budget-note'>{tr('核心问题：在我当前租金预算和条件下，哪些 suburb 可选、覆盖度如何、具体有哪些租盘？', 'Core question: under the current rental budget and filters, which suburbs are available, how strong is the budget coverage, and which specific rentals are there?')}</div>", unsafe_allow_html=True)
    with perf.track("source_data_load"):
        source_status = get_domain_rent_source_status()
        df = load_domain_rent_listings()
    if df.empty:
        st.error(tr("未找到可用的 Domain 租盘 parquet 文件。", "No Domain rent parquet file was found."))
        st.code(source_status["path"])
        return
    if IS_EXTERNAL_MODE:
        df = apply_external_rent_listing_display_filter(df)
    suburb_centroid_lookup = build_suburb_centroid_lookup(df)
    min_budget, max_budget = _normalise_weekly_bounds(df)
    external_budget_options = _build_external_rent_budget_scale() if IS_EXTERNAL_MODE else []
    if IS_EXTERNAL_MODE:
        rent_applied_filters = _merge_rent_filter_defaults(st.session_state.get("rent_budget_applied_filters"), min_budget, max_budget)
        st.session_state["rent_budget_applied_filters"] = rent_applied_filters
        _apply_pending_external_rent_reset(external_budget_options)
        rent_applied_filters = _merge_rent_filter_defaults(st.session_state.get("rent_budget_applied_filters"), min_budget, max_budget)
        st.session_state["rent_budget_applied_filters"] = rent_applied_filters
        _initialise_external_rent_widget_state_from_applied(rent_applied_filters, external_budget_options)
    else:
        rent_applied_filters = _default_rent_filters(min_budget, max_budget)
    external_budget_range = _coerce_external_rent_budget_range(
        st.session_state.get("rent_budget_external_applied_range"),
        options=external_budget_options,
        default_range=(int(rent_applied_filters.get("budget_min", min_budget)), int(rent_applied_filters.get("budget_max", max_budget))),
    ) if IS_EXTERNAL_MODE else (min_budget, max_budget)
    if not IS_EXTERNAL_MODE:
        _ensure_budget_input_state(min_budget, max_budget)
        _apply_pending_budget_widget_state(min_budget, max_budget)
    shortlist_ids = set(_get_shortlist_ids())
    shortlist_count = len(shortlist_ids)
    search_submitted = False
    reset_submitted = False

    with st.container(border=True):
        with st.form("rent_search_form", border=False):
            budget_col, filter_col = st.columns([1.25, 2.0])
            with budget_col:
                st.markdown(f"<div class='budget-budget-pill'>{tr('当前周租预算', 'Current weekly rent budget')}: {_weekly_money(min_budget)} - {_weekly_money(max_budget)}</div>", unsafe_allow_html=True)
                if IS_EXTERNAL_MODE:
                    budget_min, budget_max = st.select_slider(
                        tr("周租预算区间", "Weekly rent budget range"),
                        options=external_budget_options,
                        value=external_budget_range,
                        format_func=_format_external_rent_budget_label,
                    )
                    st.caption(
                        tr(
                            "低租金段使用更细的预算档位，高租金段使用更宽的档位，以便更快浏览租盘。",
                            "Lower weekly rents use finer steps and higher weekly rents use broader steps for faster browsing.",
                        )
                    )
                budget_min, budget_max = (budget_min, budget_max) if IS_EXTERNAL_MODE else st.slider(tr("周租预算区间", "Weekly rent budget range"), min_value=min_budget, max_value=max_budget, step=RENT_BUDGET_STEP, format="$%d", key="rent_budget_range_slider")
                if not IS_EXTERNAL_MODE:
                    input_cols = st.columns(2)
                    with input_cols[0]:
                        st.text_input(tr("最低周租", "Min weekly rent"), key="rent_budget_min_input")
                    with input_cols[1]:
                        st.text_input(tr("最高周租", "Max weekly rent"), key="rent_budget_max_input")
                if not IS_EXTERNAL_MODE and st.session_state.get("rent_budget_input_error"):
                    st.warning(st.session_state["rent_budget_input_error"])
            with filter_col:
                pass
            row1, row2, row3 = st.columns([1.15, 1.0, 1.0])
            with row1:
                suburb_options = sorted(x for x in df["suburb"].dropna().unique().tolist() if str(x).strip())
                selected_suburbs = st.multiselect(tr("重点 suburb", "Priority suburbs"), options=suburb_options, placeholder=tr("不限 suburb", "Any suburb"), key="rent_selected_suburbs")
            with row2:
                postcode_options = sorted(x for x in df["postcode"].dropna().unique().tolist() if str(x).strip())
                selected_postcodes = st.multiselect(tr("邮编", "Postcode"), options=postcode_options, placeholder=tr("不限邮编", "Any postcode"), key="rent_selected_postcodes")
            with row3:
                current_min_bedrooms = int(st.session_state.get("rent_min_bedrooms", 0))
                current_min_bathrooms = int(st.session_state.get("rent_min_bathrooms", 0))
                current_min_parking = int(st.session_state.get("rent_min_parking", 0))
            commute_query = ""
            commute_mode = "drive"
            commute_minutes = 30
            if IS_EXTERNAL_MODE:
                commute_col1, commute_col2, commute_col3 = st.columns([1.7, 1.0, 0.9])
                with commute_col1:
                    commute_query = st.text_input(
                        tr("距离筛选", "Commute filter"),
                        key="rent_commute_query",
                        placeholder=tr("输入 suburb 或 postcode", "Enter a suburb or postcode"),
                    )
                with commute_col2:
                    commute_mode = st.selectbox(
                        tr("出行方式", "Travel mode"),
                        options=["drive", "transit", "walk"],
                        format_func=lambda value: {
                            "drive": tr("开车", "Drive"),
                            "transit": tr("公共交通", "Public transport"),
                            "walk": tr("步行", "Walking"),
                        }[value],
                        key="rent_commute_mode",
                    )
                with commute_col3:
                    commute_minutes = st.selectbox(
                        tr("通勤时间", "Travel time"),
                        options=[10, 20, 30, 45, 60],
                        key="rent_commute_minutes",
                    )
                st.caption(
                    tr(
                        "测试版通勤筛选当前支持 suburb 和 postcode，暂不稳定支持完整街道地址。",
                        "In beta, the commute filter currently supports suburbs and postcodes. Full street addresses are not yet supported reliably.",
                    )
                )
            commute_allowed_suburbs = None
            commute_allowed_listing_ids = None
            commute_label = None
            if IS_EXTERNAL_MODE and str(commute_query).strip():
                commute_allowed_suburbs, commute_allowed_listing_ids, _, commute_origin, commute_label = _resolve_commute_filter(
                    df,
                    suburb_centroid_lookup,
                    query=commute_query,
                    mode=commute_mode,
                    max_minutes=int(commute_minutes),
                )
                st.session_state["rent_commute_notice"] = None if commute_origin.get("matched") else tr(
                    "无法识别该地点，请优先使用 NSW suburb、postcode 或当前房源地址。",
                    "That location could not be resolved. Try an NSW suburb or postcode.",
                )
            else:
                st.session_state["rent_commute_notice"] = None
            property_group_context, _ = _apply_rent_filters(df, budget_min=budget_min, budget_max=budget_max, min_budget=min_budget, max_budget=max_budget, selected_suburbs=selected_suburbs, selected_postcodes=selected_postcodes, min_bedrooms=current_min_bedrooms, min_bathrooms=current_min_bathrooms, min_parking=current_min_parking, exact_bedrooms=bool(st.session_state.get("rent_exact_bedrooms", False)), exact_bathrooms=bool(st.session_state.get("rent_exact_bathrooms", False)), exact_parking=bool(st.session_state.get("rent_exact_parking", False)), allowed_listing_ids=commute_allowed_listing_ids, allowed_suburbs=commute_allowed_suburbs, include_budget=True, skip_filters={"property_group", "property_subtype"})
            with perf.track("filter_option_prep"):
                property_group_options = _property_group_options(property_group_context)
            group_values = [group for group, _, _ in property_group_options]
            group_label_map = {group: label for group, label, _ in property_group_options}
            group_count_map = {group: count for group, _, count in property_group_options}
            previous_group_selection = list(st.session_state.get("rent_budget_applied_filters", {}).get("selected_property_groups", []))
            invalid_group_selection = [value for value in previous_group_selection if value not in set(group_values)]
            st.session_state["rent_group_notice"] = (
                tr("所选房产大类在当前筛选条件下已无可用结果，系统已清除该选择。", "The selected property group is no longer available under the current filters, so it was cleared.")
                if invalid_group_selection and not property_group_context.empty else None
            )
            applied_group_values = _valid_selected(
                st.session_state.get("rent_budget_applied_filters", {}).get("selected_property_groups", []),
                group_values,
            )
            current_group_values = st.session_state.get("rent_selected_group_labels")
            if current_group_values is None or any(group not in group_values for group in current_group_values):
                st.session_state["rent_selected_group_labels"] = applied_group_values
            selected_group_values = st.multiselect(
                tr("房产大类", "Property type"),
                options=group_values,
                placeholder=tr("不限大类", "Any group"),
                format_func=lambda group: f"{group_label_map[group]} ({group_count_map[group]:,})",
                key="rent_selected_group_labels",
            )
            selected_property_groups = list(selected_group_values)
            row4, row5, row6, row7 = st.columns([1.0, 1.0, 1.0, 1.1])
            with row4:
                min_bedrooms = st.selectbox(tr("最少卧室", "Min bedrooms"), options=[0, 1, 2, 3, 4, 5], format_func=lambda x: tr("不限", "Any") if x == 0 else f"{x}+", key="rent_min_bedrooms")
                st.toggle(tr("精确卧室", "Exact beds"), value=bool(st.session_state.get("rent_exact_bedrooms", False)), key="rent_exact_bedrooms")
            with row5:
                min_bathrooms = st.selectbox(tr("最少卫生间", "Min bathrooms"), options=[0, 1, 2, 3, 4], format_func=lambda x: tr("不限", "Any") if x == 0 else f"{x}+", key="rent_min_bathrooms")
                st.toggle(tr("精确卫生间", "Exact baths"), value=bool(st.session_state.get("rent_exact_bathrooms", False)), key="rent_exact_bathrooms")
            with row6:
                min_parking = st.selectbox(tr("最少车位", "Min parking"), options=[0, 1, 2, 3, 4], format_func=lambda x: tr("不限", "Any") if x == 0 else f"{x}+", key="rent_min_parking")
                st.toggle(tr("精确车位", "Exact parking"), value=bool(st.session_state.get("rent_exact_parking", False)), key="rent_exact_parking")
            with row7:
                selected_sort = st.selectbox(
                    tr("列表排序", "Listing sort"),
                    options=list(RENT_SORT_SPECS.keys()),
                    format_func=_rent_sort_label,
                    key="rent_selected_sort",
                )
            selected_property_subtypes = []
            if st.toggle(tr("显示细分类", "Show subtype filter"), value=False, key="rent_show_subtypes"):
                subtype_cols = st.columns(min(max(len(property_group_options), 1), 3))
                for idx, (group, label, count) in enumerate(property_group_options):
                    with subtype_cols[idx % len(subtype_cols)]:
                        with st.expander(f"{label} ({count:,})", expanded=group in selected_property_groups):
                            subtype_count_series = _subtype_counts(property_group_context, group)
                            subtype_values = list(subtype_count_series.index)
                            state_key = f"rent_subtypes_{group}"
                            applied_subtypes = set(st.session_state.get("rent_budget_applied_filters", {}).get("selected_property_subtypes", []))
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
                                format_func=lambda subtype, counts=subtype_count_series: f"{_title_case_subtype(subtype)} ({int(counts.get(subtype, 0)):,})",
                                key=state_key,
                            )
                            selected_property_subtypes.extend(picked_values)
            _render_filter_chips(selected_property_groups, selected_property_subtypes, selected_suburbs, selected_postcodes, min_bedrooms, min_bathrooms, min_parking, commute_label=commute_label)
            action_cols = st.columns(2)
            with action_cols[0]:
                search_submitted = st.form_submit_button(tr("搜索", "Search"), type="primary", use_container_width=True)
            with action_cols[1]:
                reset_submitted = st.form_submit_button(tr("重置筛选", "Reset filters"), use_container_width=True)

    if IS_EXTERNAL_MODE and reset_submitted:
        _reset_external_rent_filters(min_budget, max_budget, external_budget_options)
        st.rerun()
    if search_submitted:
        if IS_EXTERNAL_MODE:
            st.session_state["rent_budget_external_applied_range"] = (budget_min, budget_max)
            st.session_state["rent_budget_applied_filters"] = _merge_rent_filter_defaults(
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
                    "exact_bedrooms": bool(st.session_state.get("rent_exact_bedrooms", False)),
                    "exact_bathrooms": bool(st.session_state.get("rent_exact_bathrooms", False)),
                    "exact_parking": bool(st.session_state.get("rent_exact_parking", False)),
                    "selected_sort": _coerce_rent_sort_key(selected_sort),
                    "show_subtypes": bool(st.session_state.get("rent_show_subtypes", False)),
                    "commute_label": commute_label,
                },
                min_budget,
                max_budget,
            )
            st.session_state["rent_external_search_triggered"] = True
        else:
            if _resolve_budget_submit_form_safe(
                min_budget=min_budget,
                max_budget=max_budget,
                slider_range=(budget_min, budget_max),
                text_min_raw=st.session_state.get("rent_budget_min_input"),
                text_max_raw=st.session_state.get("rent_budget_max_input"),
            ):
                st.rerun()
            budget_min, budget_max = st.session_state["rent_budget_range_slider"]
    external_search_triggered = True if not IS_EXTERNAL_MODE else bool(st.session_state.get("rent_external_search_triggered", False))

    if IS_EXTERNAL_MODE and not external_search_triggered:
        with st.container(border=True):
            st.markdown(f"**{tr('排序 suburb', 'Ranked Suburbs')}**")
            st.info(tr("请设置筛选条件并点击搜索以查看结果", "Apply filters and click Search to view results"))
        with st.container(border=True):
            st.markdown(f"**{tr('租盘浏览', 'Rental Listings')}**")
            st.info(tr("请设置筛选条件并点击搜索以查看结果", "Apply filters and click Search to view results"))
        with st.container(border=True):
            status_cols = st.columns([2.5, 1])
            with status_cols[0]:
                st.markdown(f"**{tr('Shortlist', 'Shortlist')}**")
                st.markdown(f"<div class='budget-shortlist-status'>{tr('当前已加入', 'Currently shortlisted')}: {shortlist_count} {tr('套租盘', 'rentals')}</div>", unsafe_allow_html=True)
            with status_cols[1]:
                if shortlist_count > 0 and st.button(tr("清空 shortlist", "Clear shortlist"), use_container_width=True):
                    _set_shortlist_ids(set())
                    st.session_state["rent_shortlist_items"] = {}
                    st.rerun()
        timing_payload = perf.log(shortlisted=len(_get_shortlist_ids()), filtered_rows=0)
        render_internal_timing_summary(timing_payload, enabled=not IS_EXTERNAL_MODE)
        return
    exact_bedrooms = bool(st.session_state.get("rent_exact_bedrooms", False))
    exact_bathrooms = bool(st.session_state.get("rent_exact_bathrooms", False))
    exact_parking = bool(st.session_state.get("rent_exact_parking", False))
    if IS_EXTERNAL_MODE:
        effective_filters = _merge_rent_filter_defaults(st.session_state.get("rent_budget_applied_filters"), min_budget, max_budget)
        budget_min = int(effective_filters["budget_min"])
        budget_max = int(effective_filters["budget_max"])
        selected_property_groups = list(effective_filters.get("selected_property_groups", []))
        selected_property_subtypes = list(effective_filters.get("selected_property_subtypes", []))
        selected_suburbs = list(effective_filters.get("selected_suburbs", []))
        selected_postcodes = list(effective_filters.get("selected_postcodes", []))
        min_bedrooms = int(effective_filters.get("min_bedrooms", 0))
        min_bathrooms = int(effective_filters.get("min_bathrooms", 0))
        min_parking = int(effective_filters.get("min_parking", 0))
        selected_sort = _coerce_rent_sort_key(effective_filters.get("selected_sort", selected_sort))
        commute_query = str(effective_filters.get("commute_query", ""))
        commute_mode = str(effective_filters.get("commute_mode", "drive"))
        commute_minutes = int(effective_filters.get("commute_minutes", 30))
        exact_bedrooms = bool(effective_filters.get("exact_bedrooms", False))
        exact_bathrooms = bool(effective_filters.get("exact_bathrooms", False))
        exact_parking = bool(effective_filters.get("exact_parking", False))
        if commute_query.strip():
            commute_allowed_listing_ids = None
            commute_allowed_suburbs, commute_allowed_listing_ids, _, commute_origin, commute_label = _resolve_commute_filter(
                df,
                suburb_centroid_lookup,
                query=commute_query,
                mode=commute_mode,
                max_minutes=int(commute_minutes),
            )
            st.session_state["rent_commute_notice"] = None if commute_origin.get("matched") else tr(
                "无法识别该地点，请优先使用 NSW suburb、postcode 或当前房源地址。",
                "That location could not be resolved. Try an NSW suburb or postcode.",
            )
        else:
            commute_allowed_suburbs = None
            commute_allowed_listing_ids = None
            commute_origin = {"matched": False, "label": ""}
            commute_label = None
            st.session_state["rent_commute_notice"] = None
    commute_notice = st.session_state.get("rent_commute_notice")
    group_notice = st.session_state.get("rent_group_notice")
    with (st.spinner("Searching...") if search_submitted else nullcontext()):
        with perf.track("filter_application"):
            filtered_rent_listings, filter_debug_steps = _apply_rent_filters(df, budget_min=budget_min, budget_max=budget_max, min_budget=min_budget, max_budget=max_budget, selected_property_groups=selected_property_groups, selected_property_subtypes=selected_property_subtypes, selected_suburbs=selected_suburbs, selected_postcodes=selected_postcodes, min_bedrooms=min_bedrooms, min_bathrooms=min_bathrooms, min_parking=min_parking, exact_bedrooms=exact_bedrooms, exact_bathrooms=exact_bathrooms, exact_parking=exact_parking, allowed_listing_ids=commute_allowed_listing_ids, allowed_suburbs=commute_allowed_suburbs, include_budget=True)
            context_rent_listings = filtered_rent_listings.copy() if IS_EXTERNAL_MODE else _apply_rent_filters(df, budget_min=budget_min, budget_max=budget_max, min_budget=min_budget, max_budget=max_budget, selected_property_groups=selected_property_groups, selected_property_subtypes=selected_property_subtypes, selected_suburbs=selected_suburbs, selected_postcodes=selected_postcodes, min_bedrooms=min_bedrooms, min_bathrooms=min_bathrooms, min_parking=min_parking, exact_bedrooms=exact_bedrooms, exact_bathrooms=exact_bathrooms, exact_parking=exact_parking, allowed_listing_ids=commute_allowed_listing_ids, allowed_suburbs=commute_allowed_suburbs, include_budget=False)[0]
    sort_column, sort_ascending = RENT_SORT_SPECS[_coerce_rent_sort_key(selected_sort)]
    filtered_rent_listings = filtered_rent_listings.sort_values(by=[sort_column, "suburb", "address"], ascending=[sort_ascending, True, True], na_position="last")
    display_rent_listings = _prepare_external_display_listings(filtered_rent_listings, sort_column=sort_column, sort_ascending=sort_ascending) if IS_EXTERNAL_MODE else filtered_rent_listings
    with perf.track("ranking_table_prep"):
        suburb_summary = _suburb_summary(context_rent_listings, budget_min=budget_min, budget_max=budget_max)
    selected_suburb = _selected_suburb()
    available_suburbs = set(suburb_summary["suburb"].astype(str)) if not suburb_summary.empty else set()
    if selected_suburb != "__ALL__" and selected_suburb not in available_suburbs:
        st.session_state["rent_focus_notice"] = tr(
            "当前聚焦 suburb 在新筛选条件下已无匹配房源，已返回全局视图。",
            "The focused suburb no longer has matching rentals under the new filters, so the page has returned to the global view.",
        )
        _set_selected_suburb("__ALL__")
        selected_suburb = "__ALL__"
    focused_rent_listings = filtered_rent_listings.loc[filtered_rent_listings["suburb"] == selected_suburb].copy() if selected_suburb != "__ALL__" else filtered_rent_listings.copy()
    focused_display_listings = display_rent_listings.loc[display_rent_listings["suburb"] == selected_suburb].copy() if selected_suburb != "__ALL__" else display_rent_listings.copy()
    focused_summary = suburb_summary.loc[suburb_summary["suburb"] == selected_suburb].copy() if selected_suburb != "__ALL__" else suburb_summary
    context_scope = context_rent_listings.loc[context_rent_listings["suburb"] == selected_suburb].copy() if selected_suburb != "__ALL__" else context_rent_listings
    insight = _rent_insight(focused_rent_listings if selected_suburb != "__ALL__" else filtered_rent_listings, context_scope, focused_summary if selected_suburb != "__ALL__" else suburb_summary, focused_suburb=selected_suburb, budget_max=budget_max)
    if IS_EXTERNAL_MODE:
        shortlist_df = display_rent_listings.loc[display_rent_listings["listing_id"].astype(str).isin(shortlist_ids)].copy()
        shortlist_count = int(len(shortlist_df))
        if {"sort_has_numeric", "sort_primary", "suburb", "address"}.issubset(shortlist_df.columns):
            shortlist_df = shortlist_df.sort_values(by=["sort_has_numeric", "sort_primary", "suburb", "address"], ascending=[False, sort_ascending, True, True], na_position="last")
    else:
        shortlist_df = _build_shortlist_df(df).sort_values(by=["rent_mid", "suburb", "address"], ascending=[True, True, True], na_position="last")
    show_debug = (not IS_EXTERNAL_MODE) and str(st.query_params.get("rent_debug", "0")) == "1"
    focus_notice = _consume_focus_notice("rent_focus_notice")
    if show_debug:
        with st.expander("Rent Debug", expanded=False):
            st.dataframe(pd.DataFrame(filter_debug_steps, columns=["step", "rows"]), use_container_width=True, hide_index=True)
    if commute_notice:
        st.warning(commute_notice)
    if group_notice:
        st.warning(group_notice)
    if IS_EXTERNAL_MODE:
        filters_for_summary = dict(effective_filters)
        if commute_label:
            filters_for_summary["commute_label"] = commute_label
        with st.container(border=True):
            _render_external_applied_filter_summary(filters_for_summary, rent_mode=True)
    if filtered_rent_listings.empty:
        st.warning(tr("当前筛选条件下没有匹配租盘。", "No rental listings match the current filters."))
    else:
        if focus_notice:
            st.warning(focus_notice)
        metrics_cols = st.columns(4)
        metrics_cols[0].metric(tr("典型周租", "Typical weekly rent"), _weekly_money(insight["typical_weekly_rent"]))
        metrics_cols[1].metric(tr("租金预算覆盖率", "Rent budget coverage"), f"{insight['coverage_ratio']:.0%}")
        metrics_cols[2].metric(tr("可选 suburb", "Available suburbs"), f"{insight['suburb_count']:,}")
        metrics_cols[3].metric(tr("匹配租盘", "Matching rentals"), f"{insight['listing_count']:,}")
        if commute_label and not commute_notice:
            st.caption(commute_label)
        with st.container(border=True):
            st.markdown(f"**{tr('租金结论', 'Rent conclusion')}**")
            st.write(insight["conclusion"])
            if selected_suburb != "__ALL__":
                st.caption(f"{tr('当前聚焦 suburb', 'Currently focused suburb')}: {selected_suburb}")
        with st.container(border=True):
            st.markdown(f"**{tr('排序 suburb', 'Ranked Suburbs')}**")
            _render_suburb_ranking(focused_summary if selected_suburb != "__ALL__" else suburb_summary)
        with st.container(border=True):
            st.markdown(f"**{tr('Map', 'Map')}**")
            with perf.track("map_prep"):
                selected_suburb = _build_map(context_rent_listings, suburb_summary, selected_suburb)
        with st.container(border=True):
            st.markdown(f"**{tr('租盘浏览', 'Rental Listings')}**")
            _render_listing_results(focused_display_listings if IS_EXTERNAL_MODE else focused_rent_listings, selected_suburb)
    with st.container(border=True):
        status_cols = st.columns([2.5, 1])
        with status_cols[0]:
            st.markdown(f"**{tr('Shortlist', 'Shortlist')}**")
            st.markdown(f"<div class='budget-shortlist-status'>{tr('当前已加入', 'Currently shortlisted')}: {shortlist_count} {tr('套租盘', 'rentals')}</div>", unsafe_allow_html=True)
        with status_cols[1]:
            if shortlist_count > 0 and st.button(tr("清空 shortlist", "Clear shortlist"), use_container_width=True):
                _set_shortlist_ids(set())
                st.session_state["rent_shortlist_items"] = {}
                st.rerun()
        with st.expander(tr("打开 shortlist 工作区", "Open shortlist workspace"), expanded=shortlist_count > 0):
            _render_shortlist_panel(shortlist_df)

    timing_payload = perf.log(shortlisted=len(_get_shortlist_ids()), filtered_rows=int(len(filtered_rent_listings)))
    render_internal_timing_summary(timing_payload, enabled=not IS_EXTERNAL_MODE)


if __name__ == "__main__":
    main()

