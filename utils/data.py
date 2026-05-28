import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import streamlit as st

from .config import (
    BASE_DIR,
    DEFAULT_DOMAIN_RENT_LISTINGS_PARQUET,
    DEFAULT_DOMAIN_SALE_LISTINGS_PARQUET,
    CURRENT_RENT_CLASSIFICATION_JSONL,
    DOMAIN_RENT_LISTINGS_ENV_VAR,
    DOMAIN_SALE_LISTINGS_ENV_VAR,
    IS_PUBLIC_MODE,
    LEGACY_DOMAIN_RENT_LISTINGS_PARQUET,
    LEGACY_DOMAIN_SALE_LISTINGS_PARQUET,
    MART_DAILY_ROLLING_DIR,
    MART_MONTHLY_DIR,
    MART_WEEKLY_DIR,
    PUBLIC_MARKET_VIEW_DAILY_DIR,
    PUBLIC_MARKET_VIEW_PRICE_BAND_DIR,
    STANDARD_RESIDENTIAL_LISTING_CLASSIFICATION,
)
from .region16_segments import REGION16_SEGMENT_DEFINITIONS

ANALYTICS_PRICE_MIN = 80_000
ANALYTICS_PRICE_MAX = 20_000_000
ADAPTIVE_PRICE_P5 = 0.05
ADAPTIVE_PRICE_P95 = 0.95
ADAPTIVE_LOWER_MULTIPLIER = 0.7
ADAPTIVE_UPPER_MULTIPLIER = 1.5
ADAPTIVE_MIN_HISTORY_ROWS = 50
ALLOWED_REGION_GROUPS = {"Greater Sydney", "Rest of NSW"}
EXTERNAL_MARKET_VIEW_FACT_BYTES_THRESHOLD = 40_000_000
EXTERNAL_SALE_DISPLAY_MIN_PRICE = 50_000
EXTERNAL_SALE_DISPLAY_MAX_PRICE = 10_000_000
EXTERNAL_RENT_DISPLAY_MIN_WEEKLY = 80
EXTERNAL_RENT_DISPLAY_MAX_WEEKLY = 5_000
DOMAIN_LISTING_COLUMNS = [
    "listing_id",
    "url",
    "address",
    "suburb",
    "postcode",
    "state",
    "latitude",
    "longitude",
    "price_display",
    "price_min",
    "price_max",
    "property_type",
    "bedrooms",
    "bathrooms",
    "parking",
    "land_size",
    "listing_date",
    "agent_name",
    "agency_name",
    "main_image",
]
PROPERTY_TYPE_GROUP_LABELS = {
    "house": "House",
    "apartment": "Apartment",
    "townhouse": "Townhouse",
    "land": "Land",
    "other": "Other",
}
DOMAIN_LISTING_STRING_COLUMNS = [
    "listing_id",
    "url",
    "address",
    "suburb",
    "postcode",
    "state",
    "price_display",
    "property_type",
    "listing_date",
    "agent_name",
    "agency_name",
    "main_image",
]
DOMAIN_LISTING_NUMERIC_COLUMNS = [
    "latitude",
    "longitude",
    "price_min",
    "price_max",
    "bedrooms",
    "bathrooms",
    "parking",
    "land_size",
]
DOMAIN_RENT_LISTING_COLUMNS = [
    "listing_id",
    "url",
    "address",
    "suburb",
    "postcode",
    "state",
    "latitude",
    "longitude",
    "rent_display",
    "rent_min",
    "rent_max",
    "rent_frequency",
    "property_type",
    "bedrooms",
    "bathrooms",
    "parking",
    "furnished",
    "available_date",
    "bond",
    "lease_term",
    "agent_name",
    "agency_name",
    "main_image",
    "features",
    "description",
]
DOMAIN_RENT_LISTING_STRING_COLUMNS = [
    "listing_id",
    "url",
    "address",
    "suburb",
    "postcode",
    "state",
    "rent_display",
    "rent_frequency",
    "property_type",
    "furnished",
    "available_date",
    "lease_term",
    "agent_name",
    "agency_name",
    "main_image",
    "features",
    "description",
]
DOMAIN_RENT_LISTING_NUMERIC_COLUMNS = [
    "latitude",
    "longitude",
    "rent_min",
    "rent_max",
    "bedrooms",
    "bathrooms",
    "parking",
    "bond",
]
PRICE_SANITY_MULTIPLIER = 5.0
PRICE_SANITY_MAX_ZERO_TRIMS = 4


def format_price(value, *, prefix: str = "$", na_label: str = "N/A") -> str:
    if value is None or pd.isna(value):
        return na_label
    return f"{prefix}{int(round(float(value))):,}"


COMMUTE_MODE_CONFIG: dict[str, dict[str, float]] = {
    "drive": {"speed_kmh": 32.0, "fixed_minutes": 7.0, "distance_multiplier": 1.28},
    "transit": {"speed_kmh": 18.0, "fixed_minutes": 12.0, "distance_multiplier": 1.55},
    "walk": {"speed_kmh": 4.6, "fixed_minutes": 0.0, "distance_multiplier": 1.10},
}


def normalize_suburb_key(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).upper().strip()
    text = re.sub(r"\([^)]*\)", "", text)
    text = text.replace("-", " ").replace("&", " AND ").replace("'", "")
    text = re.sub(r"\bMT\b", "MOUNT", text)
    text = re.sub(r"\bNSW\b", "", text)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return " ".join(text.split())


def _flatten_coords(node: object) -> list[tuple[float, float]]:
    if not isinstance(node, list) or not node:
        return []
    if isinstance(node[0], (int, float)) and len(node) >= 2:
        return [(float(node[0]), float(node[1]))]
    points: list[tuple[float, float]] = []
    for item in node:
        points.extend(_flatten_coords(item))
    return points


def _geometry_centroid(geometry: dict[str, object] | None) -> tuple[float | None, float | None]:
    coords = _flatten_coords((geometry or {}).get("coordinates"))
    if not coords:
        return None, None
    lon = sum(point[0] for point in coords) / len(coords)
    lat = sum(point[1] for point in coords) / len(coords)
    return lat, lon


@st.cache_data(ttl=3600, show_spinner=False)
def load_nsw_suburb_centroids() -> pd.DataFrame:
    path = BASE_DIR / "Reference" / "ABS" / "nsw_suburbs.geojson"
    columns = ["geo_suburb_key", "boundary_suburb_name", "boundary_latitude", "boundary_longitude"]
    if not path.exists():
        return pd.DataFrame(columns=columns)

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for idx, feature in enumerate(payload.get("features", [])):
        properties = feature.get("properties", {}) if isinstance(feature, dict) else {}
        suburb_name = properties.get("suburb_name") or properties.get("SSC_NAME21") or properties.get("name")
        suburb_key = properties.get("join_key") or normalize_suburb_key(suburb_name)
        if not suburb_key:
            continue
        lat, lon = _geometry_centroid(feature.get("geometry"))
        rows.append(
            {
                "feature_id": str(properties.get("feature_id") or properties.get("suburb_code") or idx),
                "geo_suburb_key": suburb_key,
                "boundary_suburb_name": suburb_name,
                "boundary_latitude": lat,
                "boundary_longitude": lon,
            }
        )

    if not rows:
        return pd.DataFrame(columns=columns)

    polygon_df = pd.DataFrame(rows)
    return (
        polygon_df.groupby("geo_suburb_key", dropna=False)
        .agg(
            boundary_suburb_name=("boundary_suburb_name", "first"),
            boundary_latitude=("boundary_latitude", "mean"),
            boundary_longitude=("boundary_longitude", "mean"),
        )
        .reset_index()
    )


def build_listing_location_lookup(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["geo_suburb_key", "suburb", "postcode", "latitude", "longitude"])

    working = df.copy()
    working["suburb"] = _clean_string_series(working.get("suburb", pd.Series(dtype="string")))
    working["postcode"] = _clean_string_series(working.get("postcode", pd.Series(dtype="string")))
    working["latitude"] = pd.to_numeric(working.get("latitude"), errors="coerce")
    working["longitude"] = pd.to_numeric(working.get("longitude"), errors="coerce")
    working = working.loc[
        working["suburb"].notna()
        & working["latitude"].notna()
        & working["longitude"].notna()
    ].copy()
    if working.empty:
        return pd.DataFrame(columns=["geo_suburb_key", "suburb", "postcode", "latitude", "longitude"])

    working["geo_suburb_key"] = working["suburb"].map(normalize_suburb_key)
    return (
        working.groupby("geo_suburb_key", dropna=False)
        .agg(
            suburb=("suburb", "first"),
            postcode=("postcode", "first"),
            latitude=("latitude", "median"),
            longitude=("longitude", "median"),
        )
        .reset_index()
    )


def build_suburb_centroid_lookup(df: pd.DataFrame) -> pd.DataFrame:
    listing_centroids = build_listing_location_lookup(df)
    boundary_centroids = load_nsw_suburb_centroids()

    if boundary_centroids.empty and listing_centroids.empty:
        return pd.DataFrame(columns=["geo_suburb_key", "suburb", "postcode", "centroid_latitude", "centroid_longitude"])

    merged = listing_centroids.merge(boundary_centroids, on="geo_suburb_key", how="outer")
    merged["suburb"] = merged["suburb"].fillna(merged["boundary_suburb_name"])
    merged["centroid_latitude"] = merged["boundary_latitude"].fillna(merged["latitude"])
    merged["centroid_longitude"] = merged["boundary_longitude"].fillna(merged["longitude"])
    return merged.loc[
        merged["suburb"].notna()
        & merged["centroid_latitude"].notna()
        & merged["centroid_longitude"].notna()
    , ["geo_suburb_key", "suburb", "postcode", "centroid_latitude", "centroid_longitude"]].copy()


def resolve_commute_origin(query: str, suburb_lookup: pd.DataFrame, listing_df: pd.DataFrame) -> dict[str, object]:
    text = str(query or "").strip()
    if not text:
        return {"matched": False, "reason": "empty"}

    clean = " ".join(text.split())
    clean_key = normalize_suburb_key(clean)
    suburb_only_key = normalize_suburb_key(re.sub(r"\b\d{4}\b", " ", clean))
    digits = re.sub(r"[^\d]", "", clean)
    postcode = digits[:4] if len(digits) >= 4 else ""

    if clean_key and not suburb_lookup.empty:
        suburb_candidates = [key for key in [clean_key, suburb_only_key] if key]
        for suburb_candidate in suburb_candidates:
            suburb_match = suburb_lookup.loc[suburb_lookup["geo_suburb_key"] == suburb_candidate].copy()
            if suburb_match.empty:
                suburb_match = suburb_lookup.loc[
                    suburb_lookup["suburb"].astype("string").str.upper().str.contains(suburb_candidate, na=False)
                ].copy()
            if not suburb_match.empty:
                row = suburb_match.iloc[0]
                return {
                    "matched": True,
                    "match_type": "suburb",
                    "label": str(row["suburb"]),
                    "origin_query": clean,
                    "latitude": float(row["centroid_latitude"]),
                    "longitude": float(row["centroid_longitude"]),
                }

    if postcode and "postcode" in suburb_lookup.columns:
        postcode_match = suburb_lookup.loc[suburb_lookup["postcode"].astype("string") == postcode].copy()
        if not postcode_match.empty:
            row = postcode_match.iloc[0]
            return {
                "matched": True,
                "match_type": "postcode",
                "label": f"{row['suburb']} {postcode}",
                "origin_query": clean,
                "latitude": float(row["centroid_latitude"]),
                "longitude": float(row["centroid_longitude"]),
            }

    if listing_df is not None and not listing_df.empty and "address" in listing_df.columns:
        address_frame = listing_df.copy()
        address_frame["address"] = _clean_string_series(address_frame["address"])
        address_frame["latitude"] = pd.to_numeric(address_frame.get("latitude"), errors="coerce")
        address_frame["longitude"] = pd.to_numeric(address_frame.get("longitude"), errors="coerce")
        address_frame = address_frame.loc[
            address_frame["address"].notna()
            & address_frame["latitude"].notna()
            & address_frame["longitude"].notna()
        ].copy()
        if not address_frame.empty:
            exact = address_frame.loc[address_frame["address"].astype("string").str.upper() == clean.upper()].copy()
            if exact.empty:
                exact = address_frame.loc[address_frame["address"].astype("string").str.upper().str.contains(clean.upper(), na=False)].copy()
            if not exact.empty:
                row = exact.iloc[0]
                return {
                    "matched": True,
                    "match_type": "address",
                    "label": str(row["address"]),
                    "origin_query": clean,
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"]),
                }

    return {"matched": False, "reason": "not_found", "origin_query": clean}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    return 2.0 * radius_km * math.asin(math.sqrt(a))


def _estimate_commute_minutes(distance_km: pd.Series | float, *, mode: str) -> pd.Series | float:
    config = COMMUTE_MODE_CONFIG.get(mode, COMMUTE_MODE_CONFIG["drive"])
    adjusted_distance = distance_km * float(config.get("distance_multiplier", 1.0))
    return (adjusted_distance / max(float(config["speed_kmh"]), 0.1) * 60.0) + float(config["fixed_minutes"])


def _haversine_series_km(
    *,
    origin_lat: float,
    origin_lon: float,
    target_lat: pd.Series,
    target_lon: pd.Series,
) -> pd.Series:
    radius_km = 6371.0
    origin_lat_rad = math.radians(origin_lat)
    target_lat_rad = np.radians(target_lat.astype(float))
    d_phi = np.radians(target_lat.astype(float) - float(origin_lat))
    d_lambda = np.radians(target_lon.astype(float) - float(origin_lon))
    a = np.sin(d_phi / 2.0) ** 2 + np.cos(origin_lat_rad) * np.cos(target_lat_rad) * np.sin(d_lambda / 2.0) ** 2
    return 2.0 * radius_km * np.arcsin(np.sqrt(a))


def compute_commute_suburb_frame(
    *,
    origin_lat: float,
    origin_lon: float,
    suburb_lookup: pd.DataFrame,
    mode: str,
) -> pd.DataFrame:
    if suburb_lookup is None or suburb_lookup.empty:
        return pd.DataFrame(columns=["geo_suburb_key", "suburb", "commute_distance_km", "commute_minutes"])

    frame = suburb_lookup.copy()
    latitudes = pd.to_numeric(frame.get("centroid_latitude"), errors="coerce")
    longitudes = pd.to_numeric(frame.get("centroid_longitude"), errors="coerce")
    frame = frame.loc[latitudes.notna() & longitudes.notna()].copy()
    if frame.empty:
        return pd.DataFrame(columns=["geo_suburb_key", "suburb", "commute_distance_km", "commute_minutes"])

    frame["commute_distance_km"] = _haversine_series_km(
        origin_lat=float(origin_lat),
        origin_lon=float(origin_lon),
        target_lat=pd.to_numeric(frame["centroid_latitude"], errors="coerce"),
        target_lon=pd.to_numeric(frame["centroid_longitude"], errors="coerce"),
    )
    frame["commute_minutes"] = _estimate_commute_minutes(frame["commute_distance_km"], mode=mode)
    return frame.sort_values(["commute_minutes", "suburb"], ascending=[True, True]).reset_index(drop=True)


def compute_commute_listing_frame(
    *,
    origin_lat: float,
    origin_lon: float,
    listing_df: pd.DataFrame,
    mode: str,
) -> pd.DataFrame:
    columns = ["listing_id", "suburb", "latitude", "longitude", "commute_distance_km", "commute_minutes"]
    if listing_df is None or listing_df.empty:
        return pd.DataFrame(columns=columns)

    frame = listing_df.copy()
    frame["latitude"] = pd.to_numeric(frame.get("latitude"), errors="coerce")
    frame["longitude"] = pd.to_numeric(frame.get("longitude"), errors="coerce")
    frame = frame.loc[frame["latitude"].notna() & frame["longitude"].notna()].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)

    frame["commute_distance_km"] = _haversine_series_km(
        origin_lat=float(origin_lat),
        origin_lon=float(origin_lon),
        target_lat=frame["latitude"],
        target_lon=frame["longitude"],
    )
    frame["commute_minutes"] = _estimate_commute_minutes(frame["commute_distance_km"], mode=mode)
    return frame.loc[:, [col for col in columns if col in frame.columns]].sort_values(
        ["commute_minutes", "suburb", "listing_id"],
        ascending=[True, True, True],
    ).reset_index(drop=True)


def _apply_external_numeric_display_filter(
    df: pd.DataFrame,
    *,
    numeric_col: str,
    min_value: float,
    max_value: float,
    valid_flag_col: str,
    missing_flag_col: str,
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df.copy()

    out = df.copy()
    numeric = pd.to_numeric(out.get(numeric_col), errors="coerce")
    has_numeric = numeric.notna()
    valid_numeric = has_numeric & numeric.between(float(min_value), float(max_value), inclusive="both")
    keep_mask = (~has_numeric) | valid_numeric

    out = out.loc[keep_mask].copy()
    out[valid_flag_col] = valid_numeric.loc[out.index].astype(bool)
    out[missing_flag_col] = (~has_numeric.loc[out.index]).astype(bool)
    return out


def _order_external_display_rows(
    df: pd.DataFrame,
    *,
    primary_sort_col: str,
    primary_sort_ascending: bool,
    valid_flag_col: str,
    recency_col: str | None = None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df.copy()

    out = df.copy()
    if valid_flag_col not in out.columns:
        out[valid_flag_col] = False
    out["_external_valid_price_rank"] = out[valid_flag_col].fillna(False).astype(int)

    sort_cols = ["_external_valid_price_rank"]
    ascending = [False]

    if primary_sort_col in out.columns:
        sort_cols.append(primary_sort_col)
        ascending.append(primary_sort_ascending)

    if recency_col and recency_col in out.columns:
        out["_external_recency_sort"] = pd.to_datetime(out[recency_col], errors="coerce")
        sort_cols.append("_external_recency_sort")
        ascending.append(False)

    for col in ("suburb", "address"):
        if col in out.columns:
            sort_cols.append(col)
            ascending.append(True)

    out = out.sort_values(by=sort_cols, ascending=ascending, na_position="last")
    return out.drop(columns=["_external_valid_price_rank", "_external_recency_sort"], errors="ignore")


def _format_price_display(price_min, price_max, raw_display) -> str:
    if pd.notna(price_min) and pd.notna(price_max):
        lower = format_price(price_min)
        upper = format_price(price_max)
        if int(round(float(price_min))) == int(round(float(price_max))):
            return f"Guide {lower}"
        return f"Guide {lower} – {upper}"
    cleaned = _clean_string_series(pd.Series([raw_display])).iloc[0]
    return str(cleaned) if pd.notna(cleaned) else "Price on request"


def _repair_suspicious_price_bounds(price_min, price_max) -> tuple[float, float, str]:
    if pd.isna(price_min) and pd.isna(price_max):
        return np.nan, np.nan, "missing"
    if pd.isna(price_min):
        return float(price_max), float(price_max), "single_bound"
    if pd.isna(price_max):
        return float(price_min), float(price_min), "single_bound"

    low = float(price_min)
    high = float(price_max)
    repair_flag = "original"

    if high < low:
        low, high = high, low
        repair_flag = "swapped"

    if low > 0 and high > low * PRICE_SANITY_MULTIPLIER:
        candidate = high
        for _ in range(PRICE_SANITY_MAX_ZERO_TRIMS):
            if candidate % 10 != 0:
                break
            candidate /= 10.0
            if low <= candidate <= low * PRICE_SANITY_MULTIPLIER:
                high = candidate
                repair_flag = "trimmed_trailing_zero"
                break

    return low, high, repair_flag


def _clean_string_series(series: pd.Series) -> pd.Series:
    out = series.astype("string").str.strip()
    return out.mask(out.isin(["", "nan", "None", "null", "NaN"]), pd.NA)


def _canonicalize_property_type(value) -> str:
    if pd.isna(value):
        return "unknown"
    text = str(value).strip().lower()
    if not text:
        return "unknown"
    text = re.sub(r"\s*&\s*", " and ", text)
    text = re.sub(r"[/_-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_property_type(value) -> tuple[str, str]:
    canonical = _canonicalize_property_type(value)

    subtype_aliases = {
        "house": "house",
        "free standing": "free standing",
        "freestanding": "free standing",
        "semi detached": "semi detached",
        "semidetached": "semi detached",
        "duplex": "duplex",
        "terrace": "terrace",
        "villa": "villa",
        "apartment": "apartment",
        "unit": "unit",
        "flat": "flat",
        "studio": "studio",
        "penthouse": "penthouse",
        "block of units": "block of units",
        "townhouse": "townhouse",
        "town house": "townhouse",
        "land": "land",
        "vacant land": "vacant land",
        "development site": "development site",
        "new land": "new land",
        "retirement": "retirement",
        "unknown": "unknown",
    }

    subtype = "unknown"
    group = "other"

    if canonical in {"house", "free standing", "freestanding", "semi detached", "semidetached", "duplex", "terrace", "villa"}:
        subtype = subtype_aliases.get(canonical, "house")
        group = "house"
    elif canonical in {"apartment", "unit", "flat", "studio", "penthouse", "block of units"}:
        subtype = subtype_aliases.get(canonical, "apartment")
        group = "apartment"
    elif canonical in {"townhouse", "town house"}:
        subtype = "townhouse"
        group = "townhouse"
    elif canonical in {"land", "vacant land", "development site", "new land"}:
        subtype = subtype_aliases.get(canonical, "land")
        group = "land"
    elif canonical == "retirement":
        subtype = "retirement"
        group = "other"
    elif canonical == "unknown":
        subtype = "unknown"
        group = "other"
    elif any(token in canonical for token in ["apartment", "unit", "flat"]):
        subtype = "apartment"
        group = "apartment"
    elif "studio" in canonical:
        subtype = "studio"
        group = "apartment"
    elif "penthouse" in canonical:
        subtype = "penthouse"
        group = "apartment"
    elif "block of units" in canonical:
        subtype = "block of units"
        group = "apartment"
    elif "town house" in canonical or "townhouse" in canonical:
        subtype = "townhouse"
        group = "townhouse"
    elif canonical in {"new house and land", "new home designs"}:
        subtype = "house"
        group = "house"
    elif "house" in canonical:
        subtype = "house"
        group = "house"
    elif canonical in {"new apartments and off the plan"}:
        subtype = "apartment"
        group = "apartment"
    elif "land" in canonical or "development site" in canonical:
        subtype = "land" if canonical == "land" else ("development site" if "development site" in canonical else "new land")
        group = "land"
    elif canonical in {"all sale", "car space", "rural", "acreage semi rural", "farm", "specialist farm", "rural lifestyle", "livestock", "mixed farming", "horticulture", "farmlet", "equine", "viticulture"}:
        subtype = "unknown"
        group = "other"

    return group, subtype


def _resolve_domain_listing_parquet_path() -> Path:
    configured = ""
    try:
        configured = str(
            st.secrets.get("domain_sale_listings_parquet", "")
            or st.secrets.get("domain_listings_parquet", "")
        ).strip()
    except Exception:
        configured = ""
    if not configured:
        configured = str(DEFAULT_DOMAIN_SALE_LISTINGS_PARQUET)
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    if not path.exists():
        legacy_path = Path(LEGACY_DOMAIN_SALE_LISTINGS_PARQUET).expanduser()
        if legacy_path.exists():
            return legacy_path
    return path


def get_domain_listing_source_status() -> dict[str, str | bool]:
    path = _resolve_domain_listing_parquet_path()
    return {
        "path": str(path),
        "env_var": DOMAIN_SALE_LISTINGS_ENV_VAR,
        "exists": path.exists(),
    }


def _resolve_domain_rent_listing_parquet_path() -> Path:
    configured = ""
    try:
        configured = str(st.secrets.get("domain_rent_listings_parquet", "")).strip()
    except Exception:
        configured = ""
    if not configured:
        configured = str(DEFAULT_DOMAIN_RENT_LISTINGS_PARQUET)
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    if not path.exists():
        legacy_path = Path(LEGACY_DOMAIN_RENT_LISTINGS_PARQUET).expanduser()
        if legacy_path.exists():
            return legacy_path
    return path


def get_domain_rent_source_status() -> dict[str, str | bool]:
    path = _resolve_domain_rent_listing_parquet_path()
    return {
        "path": str(path),
        "env_var": DOMAIN_RENT_LISTINGS_ENV_VAR,
        "exists": path.exists(),
        "default_listing_classification": STANDARD_RESIDENTIAL_LISTING_CLASSIFICATION,
    }


@st.cache_data(ttl=900, show_spinner=False)
def _load_domain_rent_classification_lookup(parquet_path_str: str) -> pd.DataFrame:
    parquet_path = Path(parquet_path_str)
    jsonl_path = parquet_path.parent / "nsw_rent_full_deduped.jsonl"
    if not jsonl_path.exists() and CURRENT_RENT_CLASSIFICATION_JSONL.exists():
        jsonl_path = CURRENT_RENT_CLASSIFICATION_JSONL
    if not jsonl_path.exists():
        return pd.DataFrame(columns=["listing_id", "listing_classification", "is_standard_rental"])

    lookup = pd.read_json(
        jsonl_path,
        lines=True,
        dtype={"listing_id": "string"},
    )
    required_columns = {"listing_id", "rental_listing_category", "is_standard_rental"}
    if not required_columns.issubset(lookup.columns):
        return pd.DataFrame(columns=["listing_id", "listing_classification", "is_standard_rental"])

    return (
        lookup.loc[:, ["listing_id", "rental_listing_category", "is_standard_rental"]]
        .rename(columns={"rental_listing_category": "listing_classification"})
        .dropna(subset=["listing_id"])
        .drop_duplicates(subset=["listing_id"], keep="last")
    )


def _prepare_domain_listing_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    for col in DOMAIN_LISTING_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA

    out = out[DOMAIN_LISTING_COLUMNS]

    for col in DOMAIN_LISTING_STRING_COLUMNS:
        out[col] = _clean_string_series(out[col])

    out["postcode"] = out["postcode"].astype("string").str.replace(r"\.0$", "", regex=True).str.zfill(4)
    out["postcode"] = out["postcode"].mask(out["postcode"].isin(["0000", "<NA>"]), pd.NA)

    for col in DOMAIN_LISTING_NUMERIC_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out["listing_date"] = pd.to_datetime(out["listing_date"], errors="coerce", format="mixed")
    property_norm = out["property_type"].map(_normalize_property_type)
    out["property_group"] = property_norm.map(lambda x: x[0])
    out["property_subtype"] = property_norm.map(lambda x: x[1])
    out["property_group_label"] = out["property_group"].map(PROPERTY_TYPE_GROUP_LABELS).fillna("Other")

    repaired_bounds = out.apply(
        lambda row: _repair_suspicious_price_bounds(row["price_min"], row["price_max"]),
        axis=1,
        result_type="expand",
    )
    repaired_bounds.columns = ["price_filter_min", "price_filter_max", "price_cleaning_flag"]
    out[["price_filter_min", "price_filter_max", "price_cleaning_flag"]] = repaired_bounds
    out["price_mid"] = np.where(
        out["price_filter_min"].notna() & out["price_filter_max"].notna(),
        (out["price_filter_min"] + out["price_filter_max"]) / 2.0,
        np.nan,
    )
    out["has_price"] = out["price_filter_min"].notna() & out["price_filter_max"].notna()
    out["has_coordinates"] = out["latitude"].notna() & out["longitude"].notna()
    out["price_display"] = out.apply(
        lambda row: _format_price_display(row["price_filter_min"], row["price_filter_max"], row["price_display"]),
        axis=1,
    )

    return out


def _classify_rent_listing(row: pd.Series) -> str:
    text_parts = [
        row.get("url"),
        row.get("address"),
        row.get("rent_display"),
        row.get("property_type"),
        row.get("description"),
    ]
    text = " ".join(str(value) for value in text_parts if pd.notna(value)).lower()

    if re.search(r"\b(boarding|boarder|boarders|boarding house)\b", text):
        return "boarding"
    if re.search(r"\b(short stay|short-term stay|holiday|holiday rental|vacation|airbnb|per night|nightly)\b", text):
        return "short_stay_holiday"
    if re.search(r"\b(room for rent|room to rent|room available|shared accommodation|share house|roomshare|room share)\b", text):
        return "room_share"
    if re.search(r"\b(car ?space|carpark|car park|parking space|secure parking|garage for lease|lock[- ]?up garage)\b", text):
        return "parking_car_space"
    if re.search(r"\b(storage|storage shed|storage sheds|self storage|shed\/|shed\b|shipping container|container storage|warehouse storage)\b", text):
        return "storage"
    return STANDARD_RESIDENTIAL_LISTING_CLASSIFICATION


def _prepare_domain_rent_listing_frame(
    df: pd.DataFrame,
    *,
    classification_lookup: pd.DataFrame | None = None,
    standard_residential_only: bool = True,
) -> pd.DataFrame:
    out = df.copy()

    for col in DOMAIN_RENT_LISTING_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA

    out = out[DOMAIN_RENT_LISTING_COLUMNS]

    for col in DOMAIN_RENT_LISTING_STRING_COLUMNS:
        out[col] = _clean_string_series(out[col])

    out["postcode"] = out["postcode"].astype("string").str.replace(r"\.0$", "", regex=True).str.zfill(4)
    out["postcode"] = out["postcode"].mask(out["postcode"].isin(["0000", "<NA>"]), pd.NA)

    for col in DOMAIN_RENT_LISTING_NUMERIC_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out["available_date"] = pd.to_datetime(out["available_date"], errors="coerce", format="mixed")
    property_norm = out["property_type"].map(_normalize_property_type)
    out["property_group"] = property_norm.map(lambda x: x[0])
    out["property_subtype"] = property_norm.map(lambda x: x[1])
    out["property_group_label"] = out["property_group"].map(PROPERTY_TYPE_GROUP_LABELS).fillna("Other")

    if classification_lookup is not None and not classification_lookup.empty:
        classification_lookup = classification_lookup.copy()
        classification_lookup["listing_id"] = classification_lookup["listing_id"].astype("string")
        out["listing_id"] = out["listing_id"].astype("string")
        out = out.merge(classification_lookup, on="listing_id", how="left")
    else:
        out["listing_classification"] = pd.NA
        out["is_standard_rental"] = pd.NA

    fallback_mask = out["listing_classification"].isna()
    if fallback_mask.any():
        out.loc[fallback_mask, "listing_classification"] = out.loc[fallback_mask].apply(_classify_rent_listing, axis=1)

    out["listing_classification"] = _clean_string_series(out["listing_classification"]).fillna(STANDARD_RESIDENTIAL_LISTING_CLASSIFICATION)
    out["is_standard_rental"] = out["listing_classification"].eq(STANDARD_RESIDENTIAL_LISTING_CLASSIFICATION)

    repaired_bounds = out.apply(
        lambda row: _repair_suspicious_price_bounds(row["rent_min"], row["rent_max"]),
        axis=1,
        result_type="expand",
    )
    repaired_bounds.columns = ["rent_filter_min", "rent_filter_max", "rent_cleaning_flag"]
    out[["rent_filter_min", "rent_filter_max", "rent_cleaning_flag"]] = repaired_bounds
    out["rent_mid"] = np.where(
        out["rent_filter_min"].notna() & out["rent_filter_max"].notna(),
        (out["rent_filter_min"] + out["rent_filter_max"]) / 2.0,
        np.nan,
    )
    out["has_rent"] = out["rent_filter_min"].notna() & out["rent_filter_max"].notna()
    out["has_coordinates"] = out["latitude"].notna() & out["longitude"].notna()

    if standard_residential_only:
        out = out.loc[out["listing_classification"] == STANDARD_RESIDENTIAL_LISTING_CLASSIFICATION].copy()

    return out


@st.cache_data(ttl=900, show_spinner=False)
def load_domain_sale_listings() -> pd.DataFrame:
    path = _resolve_domain_listing_parquet_path()
    if not path.exists():
        return pd.DataFrame(
            columns=DOMAIN_LISTING_COLUMNS + ["price_filter_min", "price_filter_max", "price_mid", "has_price", "has_coordinates", "price_cleaning_flag"]
        )

    df = pd.read_parquet(path, columns=DOMAIN_LISTING_COLUMNS)
    return _prepare_domain_listing_frame(df)


def apply_external_sale_listing_display_filter(df: pd.DataFrame) -> pd.DataFrame:
    return _apply_external_numeric_display_filter(
        df,
        numeric_col="price_mid",
        min_value=EXTERNAL_SALE_DISPLAY_MIN_PRICE,
        max_value=EXTERNAL_SALE_DISPLAY_MAX_PRICE,
        valid_flag_col="external_display_valid_price",
        missing_flag_col="external_display_missing_price",
    )


def order_external_sale_listing_display(
    df: pd.DataFrame,
    *,
    primary_sort_col: str,
    primary_sort_ascending: bool,
) -> pd.DataFrame:
    return _order_external_display_rows(
        df,
        primary_sort_col=primary_sort_col,
        primary_sort_ascending=primary_sort_ascending,
        valid_flag_col="external_display_valid_price",
        recency_col="listing_date",
    )


@st.cache_data(ttl=900, show_spinner=False)
def load_domain_rent_listings(*, standard_residential_only: bool = True) -> pd.DataFrame:
    path = _resolve_domain_rent_listing_parquet_path()
    fallback_columns = DOMAIN_RENT_LISTING_COLUMNS + [
        "property_group",
        "property_subtype",
        "property_group_label",
        "listing_classification",
        "is_standard_rental",
        "rent_filter_min",
        "rent_filter_max",
        "rent_mid",
        "has_rent",
        "has_coordinates",
        "rent_cleaning_flag",
    ]
    if not path.exists():
        return pd.DataFrame(columns=fallback_columns)

    df = pd.read_parquet(path, columns=DOMAIN_RENT_LISTING_COLUMNS)
    classification_lookup = _load_domain_rent_classification_lookup(str(path))
    return _prepare_domain_rent_listing_frame(
        df,
        classification_lookup=classification_lookup,
        standard_residential_only=standard_residential_only,
    )


def apply_external_rent_listing_display_filter(df: pd.DataFrame) -> pd.DataFrame:
    return _apply_external_numeric_display_filter(
        df,
        numeric_col="rent_mid",
        min_value=EXTERNAL_RENT_DISPLAY_MIN_WEEKLY,
        max_value=EXTERNAL_RENT_DISPLAY_MAX_WEEKLY,
        valid_flag_col="external_display_valid_rent",
        missing_flag_col="external_display_missing_rent",
    )


def order_external_rent_listing_display(
    df: pd.DataFrame,
    *,
    primary_sort_col: str,
    primary_sort_ascending: bool,
) -> pd.DataFrame:
    recency_col = "available_date" if "available_date" in df.columns else None
    return _order_external_display_rows(
        df,
        primary_sort_col=primary_sort_col,
        primary_sort_ascending=primary_sort_ascending,
        valid_flag_col="external_display_valid_rent",
        recency_col=recency_col,
    )


def _normalize_postcode_expr(expr: pl.Expr) -> pl.Expr:
    return (
        expr.cast(pl.Utf8)
        .str.strip_chars()
        .str.replace(r"\.0$", "")
        .str.zfill(4)
    )


def add_underlying_trend(
    df: pd.DataFrame,
    *,
    group_cols: list[str],
    date_col: str,
    value_col: str,
    out_col: str = "underlying_trend",
    tail_col: str = "underlying_trend_tail",
    window_days: int = 91,
) -> pd.DataFrame:
    if df is None or df.empty:
        out = pd.DataFrame() if df is None else df.copy()
        if not out.empty:
            out[out_col] = np.nan
            out[tail_col] = False
        return out

    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce").dt.normalize()
    out[value_col] = pd.to_numeric(out[value_col], errors="coerce")
    out[out_col] = np.nan
    out[tail_col] = False

    if not group_cols:
        group_iter = [(None, out.index)]
    else:
        group_iter = out.groupby(group_cols, dropna=False).groups.items()

    tail_days = max(int(window_days // 2), 1)
    min_periods = max(int(window_days // 3), 14)

    for _, idx in group_iter:
        idx = list(idx)
        sub = out.loc[idx, [date_col, value_col]].sort_values(date_col).copy()
        if sub.empty:
            continue
        trend = (
            sub[value_col]
            .rolling(window=window_days, center=True, min_periods=min_periods)
            .mean()
        )
        sub[out_col] = trend
        max_date = sub[date_col].max()
        sub[tail_col] = sub[date_col] > (max_date - pd.Timedelta(days=tail_days))
        out.loc[sub.index, out_col] = sub[out_col]
        out.loc[sub.index, tail_col] = sub[tail_col]

    return out


def list_dataset_labels() -> list[str]:
    labels = set()
    for p in MART_WEEKLY_DIR.glob("mart_weekly_nsw_*.parquet"):
        m = re.search(r"mart_weekly_nsw_(.+)\.parquet$", p.name)
        if m:
            labels.add(m.group(1))
    return sorted(labels)


def _normalize_level(level: str) -> str:
    if level is None:
        return "NSW"
    s = str(level).strip()
    if not s:
        return "NSW"
    s_low = s.lower()

    if s_low == "nsw":
        return "NSW"
    if s_low == "region":
        return "REGION"
    if s_low in {"region16", "market_region", "market region"}:
        return "REGION16"
    if s_low == "suburb":
        return "SUBURB"
    if s_low == "postcode":
        return "POSTCODE"

    if s_low.startswith("nsw"):
        return "NSW"
    if s_low.startswith("region16") or s_low.startswith("market_region") or s_low.startswith("market region"):
        return "REGION16"
    if s_low.startswith("region"):
        return "REGION"
    if s_low.startswith("suburb"):
        return "SUBURB"
    if s_low.startswith("postcode"):
        return "POSTCODE"

    if "全州" in s or "statewide" in s_low:
        return "NSW"
    if "16区" in s or "16 区" in s or "custom region" in s_low:
        return "REGION16"
    if "大悉尼" in s or "区域" in s or "greater sydney" in s_low or "rest of nsw" in s_low:
        return "REGION"
    if "城区" in s:
        return "SUBURB"
    if "邮编" in s:
        return "POSTCODE"

    s_up = s.upper()
    if s_up in {"NSW", "REGION", "REGION16", "SUBURB", "POSTCODE"}:
        return s_up

    return "NSW"


@st.cache_data(show_spinner=False)
def load_weekly(level: str, label: str) -> pd.DataFrame:
    level = _normalize_level(level)
    if level == "NSW":
        path = MART_WEEKLY_DIR / f"mart_weekly_nsw_{label}.parquet"
    elif level == "REGION":
        path = MART_WEEKLY_DIR / f"mart_weekly_region_{label}.parquet"
    elif level == "REGION16":
        path = MART_WEEKLY_DIR / f"mart_weekly_region16_{label}.parquet"
    elif level == "SUBURB":
        path = MART_WEEKLY_DIR / f"mart_weekly_suburb_{label}.parquet"
    elif level == "POSTCODE":
        path = MART_WEEKLY_DIR / f"mart_weekly_postcode_{label}.parquet"
    else:
        path = MART_WEEKLY_DIR / f"mart_weekly_nsw_{label}.parquet"

    if not path.exists():
        return pd.DataFrame()

    df = pd.read_parquet(path)
    if "event_week_start" in df.columns:
        df["event_week_start"] = pd.to_datetime(df["event_week_start"], errors="coerce")
    return df


@st.cache_data(show_spinner=False)
def load_monthly(level: str, label: str) -> pd.DataFrame:
    level = _normalize_level(level)
    if level == "NSW":
        path = MART_MONTHLY_DIR / f"mart_monthly_nsw_{label}.parquet"
    elif level == "REGION":
        path = MART_MONTHLY_DIR / f"mart_monthly_region_{label}.parquet"
    elif level == "REGION16":
        path = MART_MONTHLY_DIR / f"mart_monthly_region16_{label}.parquet"
    elif level == "SUBURB":
        path = MART_MONTHLY_DIR / f"mart_monthly_suburb_{label}.parquet"
    elif level == "POSTCODE":
        path = MART_MONTHLY_DIR / f"mart_monthly_postcode_{label}.parquet"
    else:
        path = MART_MONTHLY_DIR / f"mart_monthly_nsw_{label}.parquet"

    if not path.exists():
        return pd.DataFrame()

    df = pd.read_parquet(path)
    if "event_month_start" in df.columns:
        df["event_month_start"] = pd.to_datetime(df["event_month_start"], errors="coerce")
    return df


def load_daily_rolling(level: str) -> pl.DataFrame:
    level = _normalize_level(level)
    if level not in {"NSW", "REGION", "REGION16", "SUBURB", "POSTCODE"}:
        return pl.DataFrame()
    return _load_daily_rolling_cached(level, _daily_rolling_source_signature(level))


@st.cache_data(show_spinner=False)
def _load_daily_rolling_cached(level: str, source_signature: tuple[str, int, int]) -> pl.DataFrame:
    if IS_PUBLIC_MODE:
        return _load_public_daily_rolling(level)
    return _build_filtered_daily_rolling(level)


def _internal_daily_rolling_path(level: str) -> Path:
    path_map = {
        "NSW": MART_DAILY_ROLLING_DIR / "daily_rolling_nsw.parquet",
        "REGION": MART_DAILY_ROLLING_DIR / "daily_rolling_region.parquet",
        "REGION16": MART_DAILY_ROLLING_DIR / "daily_rolling_region16.parquet",
        "SUBURB": MART_DAILY_ROLLING_DIR / "daily_rolling_suburb.parquet",
        "POSTCODE": MART_DAILY_ROLLING_DIR / "daily_rolling_postcode.parquet",
    }
    return path_map[level]


def _daily_rolling_source_signature(level: str) -> tuple[str, int, int]:
    path = _public_daily_rolling_snapshot_path(level) if IS_PUBLIC_MODE else _internal_daily_rolling_path(level)
    if not path.exists():
        return (str(path), 0, 0)
    stat = path.stat()
    return (str(path), int(stat.st_size), int(stat.st_mtime_ns))


def _public_daily_rolling_snapshot_path(level: str) -> Path:
    snapshot_map = {
        "NSW": PUBLIC_MARKET_VIEW_DAILY_DIR / "daily_rolling_nsw.parquet",
        "REGION": PUBLIC_MARKET_VIEW_DAILY_DIR / "daily_rolling_region.parquet",
        "REGION16": PUBLIC_MARKET_VIEW_DAILY_DIR / "daily_rolling_region16.parquet",
        "SUBURB": PUBLIC_MARKET_VIEW_DAILY_DIR / "daily_rolling_suburb.parquet",
        "POSTCODE": PUBLIC_MARKET_VIEW_DAILY_DIR / "daily_rolling_postcode.parquet",
    }
    return snapshot_map[level]


@st.cache_data(show_spinner=False)
def _load_public_daily_rolling(level: str) -> pl.DataFrame:
    path = _public_daily_rolling_snapshot_path(level)
    if not path.exists():
        return pl.DataFrame()

    daily = pl.read_parquet(path)
    if "date" in daily.columns:
        daily = daily.with_columns(pl.col("date").cast(pl.Date))
    return daily


def _clean_region_series(s: pd.Series) -> pd.Series:
    x = s.astype(str).str.strip()
    null_tokens = {"none", "nan", "na", "n/a", "null", "unknow", "unknown", ""}
    x = x.where(~x.str.lower().isin(null_tokens), "")
    x = x.where(~x.isin(["None", "nan", "NaN"]), "")
    return x


def _normalize_postcode(s: pd.Series) -> pd.Series:
    x = s.astype(str).str.strip()
    null_tokens = {"none", "nan", "na", "n/a", "null", "unknow", "unknown", ""}
    x = x.where(~x.str.lower().isin(null_tokens), "")
    x = x.str.replace(r"\.0$", "", regex=True).str.strip()
    x_digits = x.str.extract(r"(\d+)", expand=False).fillna("")
    x_digits = x_digits.where(x_digits == "", x_digits.str.zfill(4))
    return x_digits


def normalize_region_values(df: pd.DataFrame, level: str) -> pd.DataFrame:
    level = _normalize_level(level)
    d = df.copy()
    if "region" not in d.columns:
        d["region"] = "NSW" if level == "NSW" else ""
    if level == "POSTCODE":
        d["region"] = _normalize_postcode(d["region"])
    else:
        d["region"] = _clean_region_series(d["region"])
    return d


def _expand_region16_segments_daily(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df

    required_cols = {"postcode", "region_name", "dwelling_group", "date", "purchase_price"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"REGION16 daily expansion missing required columns: {sorted(missing)}; "
            f"available columns: {df.columns}"
        )

    segment_frames: list[pl.DataFrame] = []
    for definition in REGION16_SEGMENT_DEFINITIONS:
        segment_df = df.filter(
            (pl.col("region_name") == definition["base_region"])
            & pl.col("postcode").is_in(definition["postcodes"])
        )
        if segment_df.is_empty():
            continue
        segment_frames.append(
            segment_df.with_columns(pl.lit(definition["segment_region"]).alias("region_name"))
        )

    if not segment_frames:
        return df

    return pl.concat([df, *segment_frames], how="vertical")


@st.cache_data(show_spinner=False)
def load_dim_suburb_postcode() -> pl.DataFrame:
    path = BASE_DIR / "Processed" / "dim" / "dim_suburb_postcode.csv"
    if not path.exists():
        return pl.DataFrame()

    df = pl.read_csv(path, schema_overrides={"suburb": pl.Utf8, "postcode": pl.Utf8})
    df = df.with_columns([
        pl.col("suburb").str.strip_chars(),
        pl.col("postcode").str.strip_chars().str.replace(r"\.0$", "").str.zfill(4),
    ])

    for c in ["primary_postcode_sales_rows", "suburb_total_sales_rows", "primary_postcode_share"]:
        if c in df.columns:
            df = df.with_columns(pl.col(c).cast(pl.Float64))

    df = df.filter(pl.col("suburb").is_not_null() & (pl.col("suburb") != ""))
    df = df.filter(pl.col("postcode").is_not_null() & (pl.col("postcode") != ""))
    return df


@st.cache_data(show_spinner=False)
def load_dim_postcode_gccsa() -> pl.DataFrame:
    path = BASE_DIR / "Processed" / "dim" / "dim_postcode_gccsa.csv"
    if not path.exists():
        return pl.DataFrame()

    df = pl.read_csv(
        path,
        columns=["postcode", "region_group"],
        schema_overrides={"postcode": pl.Utf8, "region_group": pl.Utf8}
    )
    df = df.with_columns([
        pl.col("postcode").str.strip_chars().str.replace(r"\.0$", "").str.zfill(4),
        pl.col("region_group").str.strip_chars(),
    ])
    df = df.filter(pl.col("postcode").is_not_null() & (pl.col("postcode") != ""))
    return df


def _fact_sales_source_signature() -> tuple[tuple[str, int, int], ...]:
    fact_dir = BASE_DIR / "Processed" / "fact_sales"
    fact_files = sorted(fact_dir.glob("fact_sales_*.parquet"))
    return tuple(
        (str(path), int(path.stat().st_size), int(path.stat().st_mtime_ns))
        for path in fact_files
        if path.exists()
    )


def _load_global_filtered_fact_sales() -> pl.DataFrame:
    return _load_global_filtered_fact_sales_cached(_fact_sales_source_signature())


@st.cache_data(ttl=3600, show_spinner=False)
def _load_global_filtered_fact_sales_cached(source_signature: tuple[tuple[str, int, int], ...]) -> pl.DataFrame:
    fact_files = [Path(item[0]) for item in source_signature]
    if not fact_files:
        return pl.DataFrame()

    columns = ["suburb", "postcode", "contract_date", "purchase_price", "dwelling_group"]
    fact = pl.concat(
        [pl.read_parquet(path, columns=columns) for path in fact_files],
        how="vertical_relaxed",
    )

    fact = fact.filter(
        pl.col("dwelling_group").is_in(["HOUSE", "UNIT"]),
        pl.col("purchase_price").is_not_null(),
        pl.col("purchase_price") >= ANALYTICS_PRICE_MIN,
        pl.col("purchase_price") <= ANALYTICS_PRICE_MAX,
    )
    if fact.is_empty():
        return pl.DataFrame()

    return (
        fact.with_columns([
            pl.col("contract_date").cast(pl.Date).alias("date"),
            _normalize_postcode_expr(pl.col("postcode")).alias("postcode"),
            pl.col("suburb").cast(pl.Utf8).str.strip_chars().alias("suburb"),
            pl.col("dwelling_group").cast(pl.Utf8).str.strip_chars().alias("dwelling_group"),
        ])
        .filter(pl.col("date").is_not_null())
        .filter(pl.col("suburb").is_not_null() & (pl.col("suburb") != ""))
        .select(["suburb", "postcode", "date", "purchase_price", "dwelling_group"])
    )


@st.cache_data(ttl=3600, show_spinner=False)
def load_suburb_price_bounds() -> pl.DataFrame:
    fact = _load_global_filtered_fact_sales()
    if fact.is_empty():
        return pl.DataFrame()

    bounds = (
        fact.group_by(["suburb", "dwelling_group"])
        .agg([
            pl.len().alias("history_rows"),
            pl.col("purchase_price").quantile(ADAPTIVE_PRICE_P5).alias("p5_price"),
            pl.col("purchase_price").quantile(ADAPTIVE_PRICE_P95).alias("p95_price"),
        ])
        .with_columns([
            pl.max_horizontal(
                pl.lit(float(ANALYTICS_PRICE_MIN)),
                pl.col("p5_price") * ADAPTIVE_LOWER_MULTIPLIER,
            ).alias("local_lower"),
            pl.min_horizontal(
                pl.lit(float(ANALYTICS_PRICE_MAX)),
                pl.col("p95_price") * ADAPTIVE_UPPER_MULTIPLIER,
            ).alias("local_upper"),
        ])
        .with_columns(
            (
                (pl.col("history_rows") >= ADAPTIVE_MIN_HISTORY_ROWS)
                & pl.col("local_lower").is_not_null()
                & pl.col("local_upper").is_not_null()
                & (pl.col("local_lower") <= pl.col("local_upper"))
            ).alias("use_adaptive_band")
        )
        .select(["suburb", "dwelling_group", "history_rows", "local_lower", "local_upper", "use_adaptive_band"])
    )
    return bounds


@st.cache_data(ttl=3600, show_spinner=False)
def load_filtered_fact_sales() -> pl.DataFrame:
    fact = _load_global_filtered_fact_sales()
    if fact.is_empty():
        return pl.DataFrame()

    bounds = load_suburb_price_bounds()
    if not bounds.is_empty():
        fact = (
            fact.join(bounds, on=["suburb", "dwelling_group"], how="left")
            .filter(
                pl.col("use_adaptive_band").fill_null(False).not_()
                | (
                    (pl.col("purchase_price") >= pl.col("local_lower"))
                    & (pl.col("purchase_price") <= pl.col("local_upper"))
                )
            )
            .drop(["history_rows", "local_lower", "local_upper", "use_adaptive_band"], strict=False)
        )

    return fact.select(["suburb", "postcode", "date", "purchase_price", "dwelling_group"])


def load_public_market_view_price_band_snapshot(level: str, regions_selected: tuple[str, ...], dwelling: str) -> pl.DataFrame:
    if not IS_PUBLIC_MODE:
        return pl.DataFrame()

    scope_payload = json.dumps(
        {
            "level": str(level or "").strip().upper(),
            "dwelling": str(dwelling or "").strip().upper(),
            "regions": [str(region).strip() for region in regions_selected],
        },
        ensure_ascii=True,
        sort_keys=True,
    )
    scope_hash = hashlib.sha1(scope_payload.encode("utf-8")).hexdigest()[:12]
    snapshot_path = PUBLIC_MARKET_VIEW_PRICE_BAND_DIR / f"market_view_price_band_{scope_hash}.parquet"
    if snapshot_path.exists():
        return pl.read_parquet(snapshot_path)

    fact_dir = BASE_DIR / "Processed" / "fact_sales"
    fact_bytes = sum(path.stat().st_size for path in fact_dir.glob("fact_sales_*.parquet") if path.exists())
    if fact_bytes > EXTERNAL_MARKET_VIEW_FACT_BYTES_THRESHOLD:
        print(
            "[market-view] external mode skipped full fact_sales load for price-band data "
            f"because committed fact parquet size is {fact_bytes} bytes."
        )
    return pl.DataFrame()


def _build_filtered_daily_rolling(level: str) -> pl.DataFrame:
    fact = load_filtered_fact_sales()
    if fact.is_empty():
        return pl.DataFrame()

    if level == "NSW":
        scoped = fact.with_columns(pl.lit("NSW").alias("region"))
    elif level == "REGION":
        dim_gccsa = load_dim_postcode_gccsa()
        if dim_gccsa.is_empty():
            return pl.DataFrame()
        scoped = (
            fact.join(
                dim_gccsa
                .filter(pl.col("region_group").is_in(list(ALLOWED_REGION_GROUPS)))
                .select(["postcode", "region_group"])
                .unique(subset=["postcode"]),
                on="postcode",
                how="inner",
            )
            .with_columns(pl.col("region_group").alias("region"))
        )
    elif level == "REGION16":
        dim_region16 = load_dim_region16()
        if dim_region16.is_empty():
            return pl.DataFrame()
        scoped = fact.join(
            dim_region16.select(["postcode", "region_name"]).unique(subset=["postcode"]),
            on="postcode",
            how="inner",
        )
        scoped = _expand_region16_segments_daily(scoped)
        scoped = scoped.with_columns(pl.col("region_name").alias("region"))
    elif level == "SUBURB":
        scoped = fact.with_columns(pl.col("suburb").alias("region")).filter(pl.col("suburb") != "")
    elif level == "POSTCODE":
        scoped = fact.with_columns(pl.col("postcode").alias("region")).filter(pl.col("postcode") != "")
    else:
        return pl.DataFrame()

    scoped = scoped.select(["region", "dwelling_group", "date", "purchase_price"])
    if scoped.is_empty():
        return pl.DataFrame()

    max_date = scoped.select(pl.col("date").max()).item()
    result = (
        scoped.sort(["region", "dwelling_group", "date"])
        .group_by_dynamic(
            index_column="date",
            every="1d",
            period="28d",
            closed="right",
            label="right",
            group_by=["region", "dwelling_group"],
        )
        .agg([
            pl.col("purchase_price").median().alias("rolling_median"),
            pl.col("purchase_price").len().alias("sales_28d"),
        ])
        .filter(pl.col("date") <= max_date)
        .with_columns(
            pl.when(pl.col("sales_28d") >= 5)
            .then(pl.col("rolling_median"))
            .otherwise(None)
            .alias("rolling_median")
        )
        .with_columns([
            pl.col("rolling_median")
            .pct_change(28)
            .over(["region", "dwelling_group"])
            .alias("mom"),
            pl.col("rolling_median")
            .pct_change(84)
            .over(["region", "dwelling_group"])
            .alias("qoq"),
        ])
        .select(["date", "region", "dwelling_group", "rolling_median", "sales_28d", "mom", "qoq"])
    )
    return result.with_columns(pl.col("date").cast(pl.Date))


@st.cache_data(show_spinner=False)
def load_dim_region16() -> pl.DataFrame:
    path = BASE_DIR / "Processed" / "dim" / "dim_region16_mapping.csv"
    if not path.exists():
        return pl.DataFrame()

    df = pl.read_csv(
        path,
        schema_overrides={
            "region_id": pl.Int64,
            "region_key": pl.Utf8,
            "region_name": pl.Utf8,
            "postcode": pl.Utf8,
            "source_suburbs": pl.Utf8,
        }
    )

    required_cols = {"region_id", "region_key", "region_name", "postcode"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"dim_region16_mapping.csv missing required columns: {sorted(missing)}; "
            f"available columns: {df.columns}"
        )

    df = df.with_columns([
        pl.col("region_key").cast(pl.Utf8).str.strip_chars(),
        pl.col("region_name").cast(pl.Utf8).str.strip_chars(),
        pl.when(pl.col("suburb").is_not_null())
          .then(pl.col("suburb").cast(pl.Utf8).str.strip_chars())
          .otherwise(pl.lit(None, dtype=pl.Utf8))
          .alias("suburb"),
        pl.when(pl.col("suburb_key").is_not_null())
          .then(pl.col("suburb_key").cast(pl.Utf8).str.strip_chars().str.to_lowercase())
          .otherwise(pl.lit(None, dtype=pl.Utf8))
          .alias("suburb_key"),
        pl.col("postcode").cast(pl.Utf8).str.strip_chars().str.replace(r"\.0$", "").str.zfill(4),
        pl.when(pl.col("source_suburbs").is_not_null())
          .then(pl.col("source_suburbs").cast(pl.Utf8).str.strip_chars())
          .otherwise(pl.lit(None, dtype=pl.Utf8))
          .alias("source_suburbs"),
    ])

    keep_cols = [
        c
        for c in [
            "region_id",
            "region_key",
            "region_name",
            "suburb",
            "suburb_key",
            "postcode",
            "source_suburbs",
        ]
        if c in df.columns
    ]
    df = df.select(keep_cols).unique()

    df = df.filter(
        pl.col("region_key").is_not_null() & (pl.col("region_key") != "") &
        pl.col("region_name").is_not_null() & (pl.col("region_name") != "") &
        pl.col("postcode").is_not_null() & (pl.col("postcode") != "")
    )

    dup_postcodes = (
        df.select(["postcode", "region_key"])
          .unique()
          .group_by("postcode")
          .agg(pl.len().alias("n"))
          .filter(pl.col("n") > 1)
    )
    if dup_postcodes.height > 0:
        raise ValueError(
            "[CONFLICT] Same postcode maps to multiple REGION16 rows in dim_region16_mapping.csv"
        )

    return df
