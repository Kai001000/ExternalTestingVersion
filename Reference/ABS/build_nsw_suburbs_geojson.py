import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import shapefile


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ZIP_PATH = REPO_ROOT / "Reference" / "ABS" / "SAL_2021_AUST_GDA2020_SHP.zip"
OUTPUT_PATH = REPO_ROOT / "Reference" / "ABS" / "nsw_suburbs.geojson"
NSW_STATE_CODE = "1"
SUBURB_JOIN_ALIASES = {
    "CESSNOCK WEST": "CESSNOCK",
    "PATONGA BEACH": "PATONGA",
}


def normalise_suburb_key(value: str | None) -> str:
    if not value:
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


def _load_listing_suburbs() -> set[str]:
    try:
        from utils.data import load_domain_sale_listings
    except Exception:
        return set()

    df = load_domain_sale_listings()
    suburbs = {
        normalise_suburb_key(value)
        for value in df["suburb"].dropna().tolist()
        if str(value).strip()
    }
    return {value for value in suburbs if value}


def _round_geometry_coords(node):
    if isinstance(node, (list, tuple)):
        if node and isinstance(node[0], (int, float)):
            return [round(float(node[0]), 6), round(float(node[1]), 6)]
        return [_round_geometry_coords(item) for item in node]
    return node


def build_geojson() -> None:
    temp_dir = tempfile.mkdtemp(prefix="abs_sal_")
    try:
        with zipfile.ZipFile(ZIP_PATH) as zip_file:
            zip_file.extractall(temp_dir)

        shp_path = Path(temp_dir) / "SAL_2021_AUST_GDA2020.shp"
        reader = shapefile.Reader(str(shp_path), encoding="utf-8")

        features = []
        for shape_record in reader.iterShapeRecords():
            record = shape_record.record.as_dict()
            if record.get("STE_CODE21") != NSW_STATE_CODE:
                continue
            if shape_record.shape.shapeType == shapefile.NULL:
                continue

            suburb_name = str(record["SAL_NAME21"]).strip()
            join_key = normalise_suburb_key(suburb_name)
            if not join_key:
                continue

            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        # `join_key` comes from ABS `SAL_NAME21` and is the field used by the Budget map.
                        "feature_id": record["SAL_CODE21"],
                        "suburb_name": suburb_name,
                        "suburb_code": record["SAL_CODE21"],
                        "state_code": record["STE_CODE21"],
                        "state_name": record["STE_NAME21"],
                        "join_key": join_key,
                    },
                    "geometry": {
                        "type": shape_record.shape.__geo_interface__["type"],
                        "coordinates": _round_geometry_coords(shape_record.shape.__geo_interface__["coordinates"]),
                    },
                }
            )

        reader.close()

        geojson = {"type": "FeatureCollection", "features": features}
        OUTPUT_PATH.write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")

        listing_suburbs = _load_listing_suburbs()
        geojson_keys = {feature["properties"]["join_key"] for feature in features}
        matched = listing_suburbs & geojson_keys
        unmatched = sorted(listing_suburbs - geojson_keys)

        print(f"Wrote {OUTPUT_PATH}")
        print(f"NSW suburb polygons: {len(features)}")
        print(f"Listing suburbs: {len(listing_suburbs)}")
        print(f"Successful joins: {len(matched)}")
        print("Unmatched suburb examples:", ", ".join(unmatched[:12]) if unmatched else "none")
        print("Join field: ABS SAL_NAME21 -> GeoJSON properties.join_key")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    build_geojson()
