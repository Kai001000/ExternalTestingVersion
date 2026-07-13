import re
from collections.abc import Iterable

import pandas as pd
import polars as pl


POSTCODE_LABEL_PREFIX = "Postcode "


def normalize_area_suburb(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "nat"}:
        return ""
    return " ".join(text.split())


def normalize_area_suburb_key(value: object) -> str:
    return normalize_area_suburb(value).casefold()


def normalize_area_postcode(value: object) -> str:
    text = normalize_area_suburb(value)
    if text.startswith(POSTCODE_LABEL_PREFIX):
        text = text[len(POSTCODE_LABEL_PREFIX):].strip()
    text = re.sub(r"\.0$", "", text)
    digits = re.sub(r"\D+", "", text)
    return digits.zfill(4) if digits else ""


def is_area_postcode_value(value: object) -> bool:
    text = normalize_area_suburb(value)
    if text.startswith(POSTCODE_LABEL_PREFIX):
        text = text[len(POSTCODE_LABEL_PREFIX):].strip()
    text = re.sub(r"\.0$", "", text)
    return bool(re.fullmatch(r"\d{4}", text))


def coerce_selected_area_label(selected_label: object, options: list[str]) -> str | None:
    if not options:
        return None
    selected = str(selected_label) if selected_label is not None else None
    if selected in options:
        return selected
    selected_key = normalize_area_suburb_key(selected)
    for option in options:
        if normalize_area_suburb_key(option) == selected_key:
            return option
    return options[0]


def _unique_clean_values(frame: pl.DataFrame, column: str) -> list[str]:
    if frame is None or frame.is_empty() or column not in frame.columns:
        return []
    cleaned = (
        frame
        .select(pl.col(column).cast(pl.Utf8).str.strip_chars().alias("_value"))
        .filter(pl.col("_value").is_not_null() & (pl.col("_value") != ""))
        .unique()
        .sort("_value")
    )
    return cleaned["_value"].to_list()


def build_area_options_from_frames(
    daily_suburb: pl.DataFrame,
    daily_postcode: pl.DataFrame,
    dim_suburb_postcode: pl.DataFrame,
) -> list[tuple[str, str]]:
    suburb_postcode_by_key: dict[str, str] = {}
    suburb_value_by_key: dict[str, str] = {}

    if dim_suburb_postcode is not None and not dim_suburb_postcode.is_empty():
        required = {"suburb", "postcode"}
        if required.issubset(set(dim_suburb_postcode.columns)):
            dim_rows = (
                dim_suburb_postcode
                .select([
                    pl.col("suburb").cast(pl.Utf8).str.strip_chars().alias("suburb"),
                    pl.col("postcode").cast(pl.Utf8).str.strip_chars().str.replace(r"\.0$", "").str.zfill(4).alias("postcode"),
                ])
                .filter(
                    pl.col("suburb").is_not_null()
                    & (pl.col("suburb") != "")
                    & pl.col("postcode").is_not_null()
                    & (pl.col("postcode") != "")
                )
                .unique(subset=["suburb", "postcode"])
                .sort(["suburb", "postcode"])
                .to_dicts()
            )
            for row in dim_rows:
                suburb = normalize_area_suburb(row.get("suburb"))
                key = normalize_area_suburb_key(suburb)
                if not key:
                    continue
                suburb_value_by_key.setdefault(key, suburb)
                suburb_postcode_by_key.setdefault(key, normalize_area_postcode(row.get("postcode")))

    for suburb in _unique_clean_values(daily_suburb, "region"):
        key = normalize_area_suburb_key(suburb)
        if key:
            suburb_value_by_key.setdefault(key, normalize_area_suburb(suburb))

    area_items: dict[str, str] = {}
    for key, suburb in suburb_value_by_key.items():
        postcode = suburb_postcode_by_key.get(key, "")
        label = f"{suburb} ({postcode})" if postcode else suburb
        area_items.setdefault(label, suburb)

    postcodes = set(_unique_clean_values(daily_postcode, "region"))
    postcodes.update(postcode for postcode in suburb_postcode_by_key.values() if postcode)
    for postcode in sorted(normalize_area_postcode(value) for value in postcodes):
        if postcode:
            area_items.setdefault(f"{POSTCODE_LABEL_PREFIX}{postcode}", postcode)

    return sorted(area_items.items(), key=lambda item: item[0].casefold())


def filter_market_scope_for_regions(
    df_scope: pd.DataFrame,
    level: str,
    regions_selected: Iterable[object],
) -> pd.DataFrame:
    if df_scope is None or df_scope.empty:
        return df_scope
    selected_values = [value for value in regions_selected if normalize_area_suburb(value)]
    if not selected_values:
        return df_scope
    if str(level or "").strip().upper() != "AREA":
        return df_scope[df_scope["region"].isin(selected_values)].copy()

    selected_postcodes = {
        normalize_area_postcode(value)
        for value in selected_values
        if is_area_postcode_value(value)
    }
    selected_suburbs = {
        normalize_area_suburb_key(value)
        for value in selected_values
        if not is_area_postcode_value(value)
    }
    region = df_scope["region"].astype("string")
    mask = pd.Series(False, index=df_scope.index)
    if selected_postcodes:
        mask |= region.map(normalize_area_postcode).isin(selected_postcodes)
    if selected_suburbs:
        mask |= region.map(normalize_area_suburb_key).isin(selected_suburbs)
    return df_scope[mask].copy()
