import math
from typing import Any

import pandas as pd


_WORLD_TILE_SIZE = 256.0
_DEFAULT_CENTER = {"lat": -32.8, "lon": 147.0}
NSW_MAP_BOUNDS = {
    "west": 140.8,
    "east": 154.7,
    "south": -37.7,
    "north": -28.0,
}
NSW_DEFAULT_CENTER = {"lat": -32.4, "lon": 147.0}
NSW_DEFAULT_ZOOM = 5.35
NSW_MIN_ZOOM = 5.1
NSW_MAX_ZOOM = 12.2


def _coerce_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _scan_geometry_bounds(node: Any, bounds: list[float | None]) -> None:
    if not isinstance(node, list) or not node:
        return
    first = node[0]
    if isinstance(first, (int, float)):
        if len(node) < 2:
            return
        lon = _coerce_number(node[0])
        lat = _coerce_number(node[1])
        if lon is None or lat is None:
            return
        bounds[0] = lon if bounds[0] is None else min(bounds[0], lon)
        bounds[1] = lat if bounds[1] is None else min(bounds[1], lat)
        bounds[2] = lon if bounds[2] is None else max(bounds[2], lon)
        bounds[3] = lat if bounds[3] is None else max(bounds[3], lat)
        return
    for child in node:
        _scan_geometry_bounds(child, bounds)


def _bounds_from_geometry(geometry: dict[str, Any] | None) -> tuple[float, float, float, float] | None:
    if not isinstance(geometry, dict):
        return None
    bounds: list[float | None] = [None, None, None, None]
    _scan_geometry_bounds(geometry.get("coordinates"), bounds)
    if any(value is None for value in bounds):
        return None
    return bounds[0], bounds[1], bounds[2], bounds[3]


def _bounds_from_geojson(geojson: dict[str, Any] | None, suburb_key: str | None) -> tuple[float, float, float, float] | None:
    if not geojson or not suburb_key:
        return None
    combined: tuple[float, float, float, float] | None = None
    for feature in geojson.get("features", []):
        properties = feature.get("properties", {}) if isinstance(feature, dict) else {}
        if str(properties.get("join_key") or "").strip() != suburb_key:
            continue
        feature_bounds = _bounds_from_geometry(feature.get("geometry"))
        if feature_bounds is None:
            continue
        if combined is None:
            combined = feature_bounds
        else:
            combined = (
                min(combined[0], feature_bounds[0]),
                min(combined[1], feature_bounds[1]),
                max(combined[2], feature_bounds[2]),
                max(combined[3], feature_bounds[3]),
            )
    return combined


def _bounds_from_points(frame: pd.DataFrame, lat_col: str, lon_col: str) -> tuple[float, float, float, float] | None:
    if frame.empty or lat_col not in frame.columns or lon_col not in frame.columns:
        return None
    coords = frame[[lat_col, lon_col]].apply(pd.to_numeric, errors="coerce").dropna()
    if coords.empty:
        return None
    min_lat = float(coords[lat_col].min())
    max_lat = float(coords[lat_col].max())
    min_lon = float(coords[lon_col].min())
    max_lon = float(coords[lon_col].max())
    return min_lon, min_lat, max_lon, max_lat


def _center_from_bounds(bounds: tuple[float, float, float, float]) -> dict[str, float]:
    min_lon, min_lat, max_lon, max_lat = bounds
    return {"lat": (min_lat + max_lat) / 2.0, "lon": (min_lon + max_lon) / 2.0}


def _mercator_lat_fraction(min_lat: float, max_lat: float) -> float:
    def _lat_rad(lat: float) -> float:
        sin_value = math.sin(lat * math.pi / 180.0)
        rad = math.log((1.0 + sin_value) / (1.0 - sin_value)) / 2.0
        return max(min(rad, math.pi), -math.pi) / 2.0

    fraction = (_lat_rad(max_lat) - _lat_rad(min_lat)) / math.pi
    return max(fraction, 1e-9)


def _zoom_for_bounds(
    bounds: tuple[float, float, float, float],
    *,
    width_px: float = 1120.0,
    height_px: float = 760.0,
    padding_ratio: float = 0.82,
    min_zoom: float = 5.0,
    max_zoom: float = 12.8,
) -> float:
    min_lon, min_lat, max_lon, max_lat = bounds
    lon_fraction = max((max_lon - min_lon) / 360.0, 1e-9)
    lat_fraction = _mercator_lat_fraction(min_lat, max_lat)
    effective_width = max(width_px * padding_ratio, 1.0)
    effective_height = max(height_px * padding_ratio, 1.0)
    lon_zoom = math.log(effective_width / (_WORLD_TILE_SIZE * lon_fraction), 2)
    lat_zoom = math.log(effective_height / (_WORLD_TILE_SIZE * lat_fraction), 2)
    return float(max(min(min(lon_zoom, lat_zoom), max_zoom), min_zoom))


def resolve_budget_map_view(
    *,
    selected_suburb: str,
    suburb_key: str | None,
    map_summary: pd.DataFrame,
    map_df: pd.DataFrame,
    boundary_geojson: dict[str, Any] | None = None,
) -> tuple[dict[str, float], float]:
    if selected_suburb != "__ALL__":
        polygon_bounds = _bounds_from_geojson(boundary_geojson, suburb_key)
        if polygon_bounds is not None:
            return _center_from_bounds(polygon_bounds), _zoom_for_bounds(polygon_bounds)

        focused_summary = map_summary.loc[map_summary["suburb"] == selected_suburb].copy() if "suburb" in map_summary.columns else pd.DataFrame()
        focused_points = map_df.loc[map_df["suburb"] == selected_suburb].copy() if "suburb" in map_df.columns else pd.DataFrame()

        point_bounds = _bounds_from_points(focused_points, "latitude", "longitude")
        if point_bounds is not None:
            return _center_from_bounds(point_bounds), _zoom_for_bounds(point_bounds, max_zoom=12.2)

        summary_bounds = _bounds_from_points(focused_summary, "map_latitude", "map_longitude")
        if summary_bounds is not None:
            return _center_from_bounds(summary_bounds), 11.2

    center_source = map_summary if not map_summary.empty else map_df
    if center_source.empty:
        return _DEFAULT_CENTER.copy(), 5.0

    lat_col = "map_latitude" if "map_latitude" in center_source.columns else "latitude"
    lon_col = "map_longitude" if "map_longitude" in center_source.columns else "longitude"
    center = {
        "lat": float(pd.to_numeric(center_source[lat_col], errors="coerce").dropna().median()),
        "lon": float(pd.to_numeric(center_source[lon_col], errors="coerce").dropna().median()),
    }
    return center, 5.0


def clamp_to_nsw_map_view(center: dict[str, float] | None, zoom: float | None) -> tuple[dict[str, float], float]:
    current_center = dict(center or NSW_DEFAULT_CENTER)
    lat = float(current_center.get("lat", NSW_DEFAULT_CENTER["lat"]))
    lon = float(current_center.get("lon", NSW_DEFAULT_CENTER["lon"]))
    clamped_center = {
        "lat": min(max(lat, NSW_MAP_BOUNDS["south"]), NSW_MAP_BOUNDS["north"]),
        "lon": min(max(lon, NSW_MAP_BOUNDS["west"]), NSW_MAP_BOUNDS["east"]),
    }
    clamped_zoom = float(NSW_DEFAULT_ZOOM if zoom is None else zoom)
    clamped_zoom = max(min(clamped_zoom, NSW_MAX_ZOOM), NSW_MIN_ZOOM)
    return clamped_center, clamped_zoom
