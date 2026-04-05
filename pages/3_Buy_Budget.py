import json
import math
import re
from contextlib import nullcontext
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.config import IS_EXTERNAL_MODE
from utils.data import format_price, get_domain_listing_source_status, load_domain_sale_listings
from utils.i18n import ensure_lang, tr
from utils.map_view import resolve_budget_map_view
from utils.perf import PagePerf, render_internal_timing_summary
from utils.ui import inject_app_theme


SUBURB_JOIN_ALIASES = {
    "CESSNOCK WEST": "CESSNOCK",
    "PATONGA BEACH": "PATONGA",
}
IGNORABLE_SUBURB_KEYS = {"NORFOLK ISLAND"}
LOCALITY_VARIANT_KEYS = {"BALMORAL VILLAGE", "DARLING HARBOUR", "WALSH BAY", "YELLOW ROCK RIDGE"}
BUDGET_STEP = 50_000
MAP_HEIGHT = 640

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
        return "N/A"
    if float(value).is_integer():
        return str(int(value))
    return f"{float(value):.1f}"


def _feature_triplet(row: pd.Series) -> str:
    return f"{_count_label(row['bedrooms'])} / {_count_label(row['bathrooms'])} / {_count_label(row['parking'])}"


def _land_size_label(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{int(round(float(value))):,} sqm"


def _compact_price(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    amount = float(value)
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.2f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.0f}K"
    return format_price(amount)


def _availability_level(listing_count: int) -> tuple[str, str]:
    if listing_count >= 12:
        return tr("高可选", "High availability"), "green"
    if listing_count >= 5:
        return tr("中等可选", "Medium availability"), "orange"
    return tr("低可选", "Low availability"), "red"


def _affordability_signal(listing_count: int) -> tuple[str, str]:
    if listing_count >= 20:
        return tr("预算比较宽松", "Budget looks strong"), "green"
    if listing_count >= 6:
        return tr("预算偏紧但可选", "Budget is workable"), "orange"
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
    price_min = pd.to_numeric(df["price_filter_min"], errors="coerce")
    price_max = pd.to_numeric(df["price_filter_max"], errors="coerce")
    if price_min.notna().any() and price_max.notna().any():
        lower = max(0, int(math.floor(price_min.min() / 50_000.0) * 50_000))
        upper = int(math.ceil(price_max.max() / 50_000.0) * 50_000)
        if upper <= lower:
            upper = lower + 50_000
        return lower, upper
    return 0, 5_000_000


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


def _init_state() -> None:
    if "budget_shortlist_ids" not in st.session_state:
        st.session_state["budget_shortlist_ids"] = []
    if "budget_shortlist_items" not in st.session_state:
        st.session_state["budget_shortlist_items"] = {}
    if "budget_selected_suburb" not in st.session_state:
        st.session_state["budget_selected_suburb"] = "__ALL__"
    if "budget_map_focus_token" not in st.session_state:
        st.session_state["budget_map_focus_token"] = None
    if "budget_map_view" not in st.session_state:
        st.session_state["budget_map_view"] = {"center": None, "zoom": None}
    if "budget_focus_notice" not in st.session_state:
        st.session_state["budget_focus_notice"] = None


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


def _snapshot_listing(row: pd.Series) -> dict[str, object]:
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


def _selected_suburb() -> str:
    _init_state()
    return st.session_state["budget_selected_suburb"]


def _set_selected_suburb(suburb: str) -> None:
    st.session_state["budget_selected_suburb"] = suburb


def _clear_suburb_focus() -> None:
    _set_selected_suburb("__ALL__")
    st.session_state["budget_focus_notice"] = None


def _reset_ranking_filters() -> None:
    st.session_state["budget_ranking_search"] = ""
    st.session_state["budget_ranking_min_listings"] = 5


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
    if merged["budget_min"] > merged["budget_max"]:
        merged["budget_min"], merged["budget_max"] = min_budget, max_budget
    return merged


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


def _render_filter_chips(selected_property_groups, selected_property_subtypes, selected_suburbs, selected_postcodes, min_bedrooms, min_bathrooms, min_parking) -> None:
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
    include_budget: bool = True,
    skip_filters: set[str] | None = None,
) -> tuple[pd.DataFrame, list[tuple[str, int]]]:
    skip_filters = skip_filters or set()
    frames: list[tuple[str, int]] = [("loaded", int(len(df)))]
    filtered = df.copy()

    if include_budget:
        full_budget_selected = _full_budget_selected(budget_min, budget_max, min_budget, max_budget)
        budget_overlap = (
            filtered["has_price"]
            & (filtered["price_filter_min"] <= budget_max)
            & (filtered["price_filter_max"] >= budget_min)
        )
        filtered = filtered.loc[budget_overlap | (full_budget_selected & ~filtered["has_price"])].copy()
    frames.append(("after_budget", int(len(filtered))))

    if selected_suburbs and "suburb" not in skip_filters:
        filtered = filtered.loc[filtered["suburb"].isin(selected_suburbs)].copy()
    frames.append(("after_suburb", int(len(filtered))))

    if selected_postcodes and "postcode" not in skip_filters:
        filtered = filtered.loc[filtered["postcode"].isin(selected_postcodes)].copy()
    frames.append(("after_postcode", int(len(filtered))))

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
            f"当前聚焦 suburb 内共有 {listing_count} 套匹配房源，主流为 { _title_case_subtype(_mode_or_na(filtered['property_subtype'])) }，预算状态为{signal_label}。",
            f"The focused suburb has {listing_count} matching listings, led by { _title_case_subtype(_mode_or_na(filtered['property_subtype'])) }, with a budget position of {signal_label}.",
        )
    else:
        conclusion = tr(
            f"当前筛选下覆盖 {suburb_count} 个 suburb，共 {listing_count} 套匹配房源，主流为 { _title_case_subtype(_mode_or_na(filtered['property_subtype'])) }，预算状态为{signal_label}。",
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
        "most_affordable_suburb": most_affordable_suburb,
        "plus_5": int(len(plus_5)),
        "plus_10": int(len(stretch_pool)),
        "new_suburbs": new_suburbs,
        "uplift_note": uplift_note,
        "conclusion": conclusion,
    }


def _suburb_summary(filtered: pd.DataFrame, *, budget_min: int, budget_max: int) -> pd.DataFrame:
    suburb_df = filtered.loc[filtered["suburb"].notna()].copy()
    if suburb_df.empty:
        return pd.DataFrame()

    suburb_df["within_budget"] = (
        suburb_df["has_price"].fillna(False)
        & (suburb_df["price_filter_min"] <= budget_max)
        & (suburb_df["price_filter_max"] >= budget_min)
    )
    suburb_df["priced_listing"] = suburb_df["has_price"].fillna(False).astype(int)
    suburb_df["unknown_price"] = (~suburb_df["has_price"].fillna(False)).astype(int)
    summary = (
        suburb_df.groupby("suburb", dropna=False)
        .agg(
            listing_count=("listing_id", "count"),
            median_asking_price=("price_mid", "median"),
            common_property_type=("property_subtype", _mode_or_na),
            common_bedrooms=("bedrooms", _mode_or_na),
            latitude=("latitude", "median"),
            longitude=("longitude", "median"),
            coordinate_count=("has_coordinates", "sum"),
            within_budget_count=("within_budget", "sum"),
            priced_listings_count=("priced_listing", "sum"),
            unknown_price_count=("unknown_price", "sum"),
        )
        .reset_index()
    )
    summary["geo_suburb_key"] = summary["suburb"].map(_normalise_suburb_key)
    summary["coordinate_ratio"] = (summary["coordinate_count"] / summary["listing_count"]).fillna(0.0).clip(0.0, 1.0)
    summary["coverage_ratio"] = (
        summary["within_budget_count"] / summary["priced_listings_count"].replace({0: pd.NA})
    ).fillna(0.0).clip(0.0, 1.0)
    summary["total_listings_count"] = summary["listing_count"].astype(int)
    summary["total_priced_listings"] = summary["priced_listings_count"]
    summary["unknown_price_ratio"] = (summary["unknown_price_count"] / summary["listing_count"]).fillna(0.0).clip(0.0, 1.0)
    summary["heatmap_score"] = summary["coverage_ratio"]
    summary["heatmap_value"] = summary["within_budget_count"].astype(float)
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
        st.info(tr("当前筛选条件下没有可选 suburb。", "No suburbs are available under the current filters."))
        return

    focused_suburb = _selected_suburb()
    total_available = len(summary)
    controls = st.columns([1.55, 0.9, 0.95, 0.95])
    with controls[0]:
        search_value = st.text_input(
            tr("Search suburb", "Search suburb"),
            key="budget_ranking_search",
            placeholder=tr("Type part of a suburb name", "Type part of a suburb name"),
        ).strip()
    with controls[1]:
        min_listings = int(
            st.number_input(
                tr("Min listings", "Min listings"),
                min_value=1,
                max_value=500,
                value=int(st.session_state.get("budget_ranking_min_listings", 5)),
                step=1,
                key="budget_ranking_min_listings",
            )
        )
    with controls[2]:
        if st.button(tr("Reset ranking filters", "Reset ranking filters"), use_container_width=True):
            _reset_ranking_filters()
            st.rerun()
    with controls[3]:
        if st.button(tr("Reset suburb focus", "Reset suburb focus"), use_container_width=True, disabled=focused_suburb == "__ALL__"):
            _clear_suburb_focus()
            st.rerun()

    ranking = summary.copy()
    if search_value:
        ranking = ranking.loc[ranking["suburb"].astype(str).str.contains(search_value, case=False, na=False)].copy()
    if focused_suburb != "__ALL__":
        ranking = ranking.loc[ranking["suburb"] == focused_suburb].copy()
    if focused_suburb == "__ALL__":
        ranking = ranking.loc[ranking["priced_listings_count"] >= min_listings].copy()
    ranking = ranking.sort_values(
        ["coverage_ratio", "within_budget_count", "total_priced_listings", "median_asking_price", "suburb"],
        ascending=[False, False, False, True, True],
        na_position="last",
    ).reset_index(drop=True)

    st.caption(tr(f"显示 {min(len(ranking), 50):,} / {total_available:,} 个 suburb", f"Showing {min(len(ranking), 50):,} of {total_available:,} suburbs"))
    st.caption(tr(f"最小挂牌数阈值后: {min_listings}", f"After ranking min listings threshold: {min_listings}"))
    st.caption(tr(f"当前聚焦 suburb: {focused_suburb if focused_suburb != '__ALL__' else '无'}", f"Focused suburb: {focused_suburb if focused_suburb != '__ALL__' else 'None'}"))

    if ranking.empty:
        st.warning(tr(f"排名筛选后 0 / {total_available:,} 个 suburb 可显示。", f"Showing 0 of {total_available:,} suburbs after ranking filters."))
        return

    view = ranking.head(50).copy()
    view[tr("聚焦", "Focus")] = view["suburb"].eq(focused_suburb).map({True: tr("已聚焦", "Focused"), False: ""})
    view[tr("覆盖率", "Coverage")] = (view["coverage_ratio"] * 100).round().astype(int).astype(str) + "%"
    view[tr("预算内", "Within Budget")] = view["within_budget_count"].astype(int)
    view[tr("有报价", "Priced Listings")] = view["priced_listings_count"].astype(int)
    view[tr("总挂牌", "Total Listings")] = view["total_listings_count"].astype(int)
    view[tr("中位标价", "Median Price")] = view["median_asking_price"].map(_compact_price)

    selection = st.dataframe(
        view[[tr("聚焦", "Focus"), "suburb", tr("覆盖率", "Coverage"), tr("预算内", "Within Budget"), tr("有报价", "Priced Listings"), tr("总挂牌", "Total Listings"), tr("中位标价", "Median Price")]].rename(
            columns={"suburb": tr("Suburb", "Suburb")}
        ),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="budget_ranking_table",
    )

    picked_rows = []
    if isinstance(selection, dict):
        picked_rows = selection.get("selection", {}).get("rows", [])
    else:
        picked_rows = getattr(getattr(selection, "selection", None), "rows", []) or []
    if picked_rows:
        picked_suburb = str(view.iloc[picked_rows[0]]["suburb"])
        if picked_suburb != focused_suburb:
            _set_selected_suburb(picked_suburb)
            st.rerun()


def _resolve_map_selection(event_state) -> str | None:
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
    if isinstance(customdata, (list, tuple)) and len(customdata) >= 2 and customdata[1] == "suburb":
        suburb = str(customdata[0]).strip()
        return suburb or None
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
    st.session_state["budget_map_focus_token"] = selected_suburb
    _set_map_view(center, zoom)
    return center, zoom


def _build_map(filtered: pd.DataFrame, suburb_summary: pd.DataFrame, selected_suburb: str) -> str:
    map_df = filtered.loc[filtered["has_coordinates"]].copy()
    boundaries = _load_suburb_boundaries()
    map_summary = suburb_summary.copy()

    if map_df.empty and map_summary.empty:
        st.info(tr("当前筛选结果没有可用坐标，地图暂时无法展示。", "No coordinates are available for the current filters."))
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

    fig = go.Figure()
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
                        name=tr("Focused suburb", "Focused suburb"),
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
        mapbox=dict(style="carto-positron", center=center, zoom=zoom),
        legend=dict(orientation="h", yanchor="bottom", y=0.01, xanchor="left", x=0.01),
        uirevision=f"budget-map-{selected_suburb}",
    )

    event_state = st.plotly_chart(
        fig,
        use_container_width=True,
        config={"displayModeBar": True, "responsive": True, "scrollZoom": True},
        key="budget_map_chart",
        on_select="rerun",
        selection_mode="points",
    )
    picked_suburb = _resolve_map_selection(event_state)
    if picked_suburb and picked_suburb != selected_suburb:
        _set_selected_suburb(picked_suburb)
        st.rerun()

    if not IS_EXTERNAL_MODE:
        if not boundaries["available"]:
            st.caption(
                tr(
                    f"未找到官方 suburb 边界文件，当前使用 suburb 中心点替代热力面。可将 GeoJSON 放入 {boundaries['path']} 以启用完整 choropleth。",
                    f"Official suburb boundaries were not found, so the map is using suburb centroids instead of filled polygons. Add a GeoJSON at {boundaries['path']} to enable the full choropleth.",
                )
            )
        elif not choropleth_ready:
            st.warning(
                tr(
                    f"Suburb 边界文件已加载，但当前 join 覆盖不足以安全启用 choropleth。NSW polygon: {polygon_count}，listing suburb: {len(map_summary)}，成功 join: {joined_suburbs}。未匹配示例：{', '.join(unmatched_examples) if unmatched_examples else 'N/A'}。",
                    f"The suburb boundary file loaded, but join coverage is too weak to safely enable the choropleth. NSW polygons: {polygon_count}, listing suburbs: {len(map_summary)}, successful joins: {joined_suburbs}. Unmatched examples: {', '.join(unmatched_examples) if unmatched_examples else 'N/A'}.",
                )
            )
        elif not map_summary.empty and "boundary_latitude" in map_summary.columns:
            st.caption(
                tr(
                    f"颜色表示当前 suburb 里预算内标价房源的多少：越绿代表预算内选择越多；越浅代表预算内标价房源更少。若一个 suburb 有较多未定价房源，颜色会更保守。当前 join: {joined_suburbs}/{len(map_summary)}（{join_rate:.0%}），未匹配示例：{', '.join(unmatched_examples) if unmatched_examples else '无'}。",
                    f"Color shows how many priced in-budget options are available in each suburb: greener means more in-budget choice, lighter means fewer priced matches. If a suburb has many unknown-price listings, the color stays more conservative. Current join: {joined_suburbs}/{len(map_summary)} ({join_rate:.0%}), unmatched examples: {', '.join(unmatched_examples) if unmatched_examples else 'none'}.",
                )
            )
            if locality_unmatched or ignorable_unmatched or unresolved_unmatched:
                st.caption(
                    tr(
                        f"未匹配分类：地名变体 {', '.join(locality_unmatched) if locality_unmatched else '无'}；可忽略 {', '.join(ignorable_unmatched) if ignorable_unmatched else '无'}；仍待处理 {', '.join(unresolved_unmatched) if unresolved_unmatched else '无'}。",
                        f"Unmatched classification: locality variants {', '.join(locality_unmatched) if locality_unmatched else 'none'}; ignorable {', '.join(ignorable_unmatched) if ignorable_unmatched else 'none'}; still unresolved {', '.join(unresolved_unmatched) if unresolved_unmatched else 'none'}.",
                    )
                )
        if sampled:
            st.caption(tr("当前 suburb 的房源点位优先展示最多 350 个更适合浏览的结果，以保持地图响应速度。", "Listing markers are capped to the first 350 browse-worthy results in the focused suburb to keep the map responsive."))

    return selected_suburb


def _listing_card(row: pd.Series, *, key_prefix: str) -> None:
    with st.container(border=True):
        if IS_EXTERNAL_MODE:
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
            action_cols = st.columns(1 if IS_EXTERNAL_MODE else 2)
            with action_cols[0]:
                label = tr("移出 shortlist", "Remove") if str(row["listing_id"]) in _get_shortlist_ids() else tr("加入 shortlist", "Shortlist")
                if st.button(label, key=f"{key_prefix}_toggle_{row['listing_id']}", use_container_width=True):
                    _toggle_shortlist(str(row["listing_id"]), row)
                    st.rerun()
            if not IS_EXTERNAL_MODE:
                with action_cols[1]:
                    st.link_button(tr("打开房源", "Open listing"), row["url"], use_container_width=True)
        if image_col is not None and pd.notna(row["main_image"]):
            with image_col:
                st.image(row["main_image"], use_container_width=True)


def _render_listing_results(listings: pd.DataFrame, selected_suburb: str) -> None:
    if listings.empty:
        st.info(tr("当前 suburb / 筛选条件下没有房源。", "No listings match the current suburb or filters."))
        return
    st.caption(
        tr("当前查看", "Showing")
        + ": "
        + (selected_suburb if selected_suburb != "__ALL__" else tr("全部匹配 suburb", "All matching suburbs"))
        + f" • {len(listings):,} {tr('套房源', 'listings')}"
    )
    for _, row in listings.head(14).iterrows():
        _listing_card(row, key_prefix="browse")
    if len(listings) > 14:
        st.caption(tr("当前先展示前 14 条更适合浏览的结果。", "Showing the first 14 results for easier browsing."))


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


def _render_shortlist_panel(shortlist_df: pd.DataFrame) -> None:
    if shortlist_df.empty:
        st.info(tr("还没有加入 shortlist 的房源。", "No listings have been shortlisted yet."))
        return
    for _, row in shortlist_df.iterrows():
        _listing_card(row, key_prefix="shortlist")


def _render_comparison_table(shortlist_df: pd.DataFrame) -> None:
    if shortlist_df.empty:
        st.info(tr("先把房源加入 shortlist，再进行对比。", "Add listings to the shortlist first to compare them here."))
        return
    comparison = shortlist_df.copy()
    comparison["bedrooms"] = comparison["bedrooms"].map(_count_label)
    comparison["bathrooms"] = comparison["bathrooms"].map(_count_label)
    comparison["parking"] = comparison["parking"].map(_count_label)
    comparison["land_size"] = comparison["land_size"].map(_land_size_label)
    comparison["property_type_label"] = comparison["property_group_label"] + " / " + comparison["property_subtype"].map(_title_case_subtype)
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


def main() -> None:
    perf = PagePerf("buy_budget")
    ensure_lang()
    inject_app_theme()
    _init_state()

    st.markdown(f"<div class='budget-kicker'>{tr('买家工作流', 'Buyer Workflow')}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='budget-title'>{tr('预算地图', 'Budget Map')}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='budget-note'>{tr('核心问题：这笔预算在什么地方最有机会买到合适房源？', 'Core question: where does this budget give the buyer the best chance of finding a suitable home?')}</div>",
        unsafe_allow_html=True,
    )

    with perf.track("source_data_load"):
        source_status = get_domain_listing_source_status()
        df = load_domain_sale_listings()
    if df.empty:
        st.error(tr("未找到可用的 Domain 房源 parquet 文件。", "No Domain listing parquet file was found."))
        st.code(source_status["path"])
        return

    min_budget, max_budget = _normalise_bounds(df)
    _ensure_budget_input_state(min_budget, max_budget)
    _apply_pending_budget_widget_state(min_budget, max_budget)
    shortlist_count = len(_get_shortlist_ids())
    search_submitted = False

    with st.container(border=True):
        with st.form("budget_search_form", border=False):
            budget_col, filter_col = st.columns([1.25, 2.0])
            with budget_col:
                st.markdown(f"<div class='budget-budget-pill'>{tr('当前预算', 'Current budget')}: {_money(min_budget)} - {_money(max_budget)}</div>", unsafe_allow_html=True)
                input_cols = st.columns(2)
                with input_cols[0]:
                    st.text_input(
                        tr("最低预算", "Min budget"),
                        key="budget_min_input",
                    )
                with input_cols[1]:
                    st.text_input(
                        tr("最高预算", "Max budget"),
                        key="budget_max_input",
                    )
                budget_min, budget_max = st.slider(
                    tr("预算区间", "Budget range"),
                    min_value=min_budget,
                    max_value=max_budget,
                    step=BUDGET_STEP,
                    format="$%d",
                    key="budget_range_slider",
                )
                if st.session_state.get("budget_input_error"):
                    st.warning(st.session_state["budget_input_error"])
                st.caption(tr("预算是整个页面的主驱动，其他条件都建立在它之上。", "Budget is the main driver of this page; the other filters sit on top of it."))
            with filter_col:
                row1, row2, row3 = st.columns([1.15, 1.0, 1.0])
                with row1:
                    pass
                    suburb_options = sorted(x for x in df["suburb"].dropna().unique().tolist() if str(x).strip())
                selected_suburbs = st.multiselect(tr("重点 suburb", "Priority suburbs"), options=suburb_options, placeholder=tr("不限 suburb", "Any suburb"), key="budget_selected_suburbs")
                with row2:
                    pass
                    postcode_options = sorted(x for x in df["postcode"].dropna().unique().tolist() if str(x).strip())
                selected_postcodes = st.multiselect(tr("邮编", "Postcode"), options=postcode_options, placeholder=tr("不限邮编", "Any postcode"), key="budget_selected_postcodes")
                with row3:
                    pass
                    current_min_bedrooms = int(st.session_state.get("budget_min_bedrooms", 0))
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
                    include_budget=False,
                    skip_filters={"property_group", "property_subtype"},
                )
                property_group_options = _property_group_options(property_group_context)
                group_labels = [f"{label} ({count:,})" for _, label, count in property_group_options]
                label_to_group = {f"{label} ({count:,})": group for group, label, count in property_group_options}
                selected_group_labels = st.multiselect(tr("房产大类", "Property group"), options=group_labels, placeholder=tr("不限大类", "Any group"), key="budget_selected_group_labels")
                selected_property_groups = [label_to_group[label] for label in selected_group_labels]

            row4, row5, row6, row7 = st.columns([1.0, 1.0, 1.0, 1.1])
            with row4:
                min_bedrooms = st.selectbox(tr("最少卧室", "Min bedrooms"), options=[0, 1, 2, 3, 4, 5], format_func=lambda x: tr("不限", "Any") if x == 0 else f"{x}+", key="budget_min_bedrooms")
                st.toggle(tr("精确卧室", "Exact beds"), value=bool(st.session_state.get("budget_exact_bedrooms", False)), key="budget_exact_bedrooms")
            with row5:
                min_bathrooms = st.selectbox(tr("最少卫生间", "Min bathrooms"), options=[0, 1, 2, 3, 4], format_func=lambda x: tr("不限", "Any") if x == 0 else f"{x}+", key="budget_min_bathrooms")
                st.toggle(tr("精确卫生间", "Exact baths"), value=bool(st.session_state.get("budget_exact_bathrooms", False)), key="budget_exact_bathrooms")
            with row6:
                min_parking = st.selectbox(tr("最少车位", "Min parking"), options=[0, 1, 2, 3, 4], format_func=lambda x: tr("不限", "Any") if x == 0 else f"{x}+", key="budget_min_parking")
                st.toggle(tr("精确车位", "Exact parking"), value=bool(st.session_state.get("budget_exact_parking", False)), key="budget_exact_parking")
            with row7:
                sort_options = {
                    tr("价格从低到高", "Price low to high"): ("price_mid", True),
                    tr("价格从高到低", "Price high to low"): ("price_mid", False),
                    tr("最新房源", "Newest listing"): ("listing_date", False),
                    tr("卧室数", "Bedrooms"): ("bedrooms", False),
                    tr("Suburb", "Suburb"): ("suburb", True),
                }
                selected_sort = st.selectbox(tr("列表排序", "Listing sort"), options=list(sort_options.keys()), key="budget_selected_sort")

            selected_property_subtypes: list[str] = []
            if st.toggle(tr("显示细分类", "Show subtype filter"), value=False):
                subtype_cols = st.columns(min(max(len(property_group_options), 1), 3))
                for idx, (group, label, count) in enumerate(property_group_options):
                    with subtype_cols[idx % len(subtype_cols)]:
                        with st.expander(f"{label} ({count:,})", expanded=group in selected_property_groups):
                            subtype_count_series = _subtype_counts(property_group_context, group)
                            subtype_labels = [f"{_title_case_subtype(subtype)} ({int(sub_count):,})" for subtype, sub_count in subtype_count_series.items()]
                            subtype_label_to_value = {f"{_title_case_subtype(subtype)} ({int(sub_count):,})": subtype for subtype, sub_count in subtype_count_series.items()}
                            default_labels = subtype_labels if group in selected_property_groups else []
                            picked_labels = st.multiselect(
                                tr("选择细分类", "Select subtypes"),
                                options=subtype_labels,
                                default=default_labels,
                                key=f"subtypes_{group}",
                            )
                            selected_property_subtypes.extend([subtype_label_to_value[item] for item in picked_labels])

            _render_filter_chips(selected_property_groups, selected_property_subtypes, selected_suburbs, selected_postcodes, min_bedrooms, min_bathrooms, min_parking)
            search_submitted = st.form_submit_button("Search", type="primary", use_container_width=True)
            st.caption(tr("房产大类后的数量按当前预算、suburb、postcode 与房型要求实时计算，不包含大类筛选本身。", "Property-group counts are computed from the current budget, suburb, postcode, and bed/bath/parking context, excluding the property-group filter itself."))
    if search_submitted:
        if _resolve_budget_submit_form_safe(
            min_budget=min_budget,
            max_budget=max_budget,
            slider_range=(budget_min, budget_max),
            text_min_raw=st.session_state.get("budget_min_input"),
            text_max_raw=st.session_state.get("budget_max_input"),
        ):
            st.rerun()
        budget_min, budget_max = st.session_state["budget_range_slider"]
    full_budget_selected = _full_budget_selected(budget_min, budget_max, min_budget, max_budget)
    with (st.spinner("Searching...") if search_submitted else nullcontext()):
        with perf.track("filter_application"):
            context_listings, _ = _apply_budget_filters(
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
                exact_bedrooms=bool(st.session_state.get("budget_exact_bedrooms", False)),
                exact_bathrooms=bool(st.session_state.get("budget_exact_bathrooms", False)),
                exact_parking=bool(st.session_state.get("budget_exact_parking", False)),
                include_budget=False,
            )
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
                exact_bedrooms=bool(st.session_state.get("budget_exact_bedrooms", False)),
                exact_bathrooms=bool(st.session_state.get("budget_exact_bathrooms", False)),
                exact_parking=bool(st.session_state.get("budget_exact_parking", False)),
            )

    sort_column, sort_ascending = sort_options[selected_sort]
    filtered_listings = filtered_listings.sort_values(by=[sort_column, "suburb", "address"], ascending=[sort_ascending, True, True], na_position="last")
    with perf.track("ranking_table_prep"):
        suburb_summary = _suburb_summary(context_listings, budget_min=budget_min, budget_max=budget_max)

    selected_suburb = _selected_suburb()
    available_suburbs = set(suburb_summary["suburb"].astype(str)) if not suburb_summary.empty else set()
    if selected_suburb != "__ALL__" and selected_suburb not in available_suburbs:
        st.session_state["budget_focus_notice"] = tr(
            "当前聚焦 suburb 在新筛选条件下已无匹配房源，已返回全局视图。",
            "The focused suburb no longer has matching listings under the new filters, so the page has returned to the global view.",
        )
        _set_selected_suburb("__ALL__")
        selected_suburb = "__ALL__"

    focused_listings = filtered_listings.loc[filtered_listings["suburb"] == selected_suburb].copy() if selected_suburb != "__ALL__" else filtered_listings.copy()
    insight_scope = focused_listings if selected_suburb != "__ALL__" else filtered_listings
    context_scope = context_listings.loc[context_listings["suburb"] == selected_suburb].copy() if selected_suburb != "__ALL__" else context_listings
    focused_summary = suburb_summary.loc[suburb_summary["suburb"] == selected_suburb].copy() if selected_suburb != "__ALL__" else suburb_summary
    insight = _budget_insight(insight_scope, context_scope, budget_max, focused_suburb=selected_suburb)
    shortlist_df = _build_shortlist_df(df)
    shortlist_df = shortlist_df.sort_values(by=["price_mid", "suburb", "address"], ascending=[True, True, True], na_position="last")
    show_debug = (not IS_EXTERNAL_MODE) and str(st.query_params.get("budget_debug", "0")) == "1"
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

    if filtered_listings.empty:
        st.warning(tr("当前筛选条件下没有匹配房源。", "No listings match the current filters."))
    else:
        if focus_notice:
            st.warning(focus_notice)
        metrics_cols = st.columns(4)
        with metrics_cols[0]:
            st.metric(tr("当前中位标价", "Current median asking price"), _money(insight["typical_price"]))
        with metrics_cols[1]:
            st.metric(tr("预算状态", "Budget signal"), insight["signal_label"])
        with metrics_cols[2]:
            st.metric(tr("可选 suburb", "Available suburbs"), f"{insight['suburb_count']:,}")
        with metrics_cols[3]:
            st.metric(tr("匹配房源", "Matching listings"), f"{insight['listing_count']:,}")

        with st.container(border=True):
            st.markdown(f"**{tr('预算结论', 'Budget conclusion')}**")
            st.write(insight["conclusion"])
            if insight["new_suburbs"] and selected_suburb == "__ALL__":
                st.caption(f"{tr('预算上调后可能新增的 suburb', 'Potential suburb expansion')}: {', '.join(insight['new_suburbs'])}")
            if insight.get("uplift_note"):
                st.caption(insight["uplift_note"])

        with st.container(border=True):
            focus_cols = st.columns([2.4, 1])
            with focus_cols[0]:
                st.markdown(f"**{tr('排序 suburb', 'Ranked Suburbs')}**")
                st.caption(tr("先按 suburb 搜索并设置最小挂牌阈值，再通过表格聚焦地图。", "Search by suburb, apply a minimum priced-listings threshold, then use the table to focus the map."))
            with focus_cols[1]:
                if selected_suburb != "__ALL__":
                    st.caption(f"{tr('当前聚焦 suburb', 'Focused suburb')}: {selected_suburb}")
                    if st.button(tr("Reset suburb focus", "Reset suburb focus"), key="budget_reset_focus_header", use_container_width=True):
                        _clear_suburb_focus()
                        st.rerun()
            _render_suburb_ranking(focused_summary if selected_suburb != "__ALL__" else suburb_summary)

        with st.container(border=True):
            st.markdown(f"**{tr('Map', 'Map')}**")
            st.caption(tr("地图现在是主要决策层：先看 suburb 覆盖率，再查看所选 suburb 内的房源点位。", "The map is now the main decision layer: read suburb coverage first, then inspect listing markers inside the selected suburb."))
            with perf.track("map_prep"):
                selected_suburb = _build_map(filtered_listings, suburb_summary, selected_suburb)
        focus_listings = focused_listings
        with st.container(border=True):
            st.markdown(f"**{tr('房源浏览', 'Listings')}**")
            st.caption(tr("价格和地址优先，其次才是图片与其他细节。", "Price and address come first, with image and details supporting the decision."))
            _render_listing_results(focus_listings, selected_suburb)

    with st.container(border=True):
        status_cols = st.columns([2.5, 1])
        with status_cols[0]:
            st.markdown(f"**{tr('Shortlist', 'Shortlist')}**")
            st.markdown(f"<div class='budget-shortlist-status'>{tr('当前已加入', 'Currently shortlisted')}: {shortlist_count} {tr('套房源', 'listings')}</div>", unsafe_allow_html=True)
        with status_cols[1]:
            if shortlist_count > 0 and st.button(tr("清空 shortlist", "Clear shortlist"), use_container_width=True):
                _set_shortlist_ids(set())
                st.session_state["budget_shortlist_items"] = {}
                st.rerun()

        with st.expander(tr("打开 shortlist 工作区", "Open shortlist workspace"), expanded=shortlist_count > 0):
            if IS_EXTERNAL_MODE:
                review_tab, compare_tab = st.tabs([
                    tr("已选房源", "Review"),
                    tr("对比", "Compare"),
                ])
                with review_tab:
                    _render_shortlist_panel(shortlist_df)
                with compare_tab:
                    _render_comparison_table(shortlist_df)
            else:
                review_tab, compare_tab, export_tab = st.tabs([
                    tr("已选房源", "Review"),
                    tr("对比", "Compare"),
                    tr("摘要", "Export Summary"),
                ])
                with review_tab:
                    _render_shortlist_panel(shortlist_df)
                with compare_tab:
                    _render_comparison_table(shortlist_df)
                with export_tab:
                    _render_shortlist_summary(shortlist_df)

    timing_payload = perf.log(shortlisted=len(_get_shortlist_ids()), filtered_rows=int(len(filtered_listings)))
    render_internal_timing_summary(timing_payload, enabled=not IS_EXTERNAL_MODE)


if __name__ == "__main__":
    main()
