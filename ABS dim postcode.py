# ABS dim postcode.py
# Build NSW postcode -> GCCSA (Greater Sydney / Rest of NSW)

from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(r"C:\Users\jonat\PycharmProjects\NSWpropertyData")

POA_XLSX = BASE_DIR / "Reference" / "ABS" / "POA_2021_AUST.xlsx"
MB_XLSX  = BASE_DIR / "Reference" / "ABS" / "MB_2021_AUST.xlsx"

OUT_DIR = BASE_DIR / "Processed" / "dim"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "dim_postcode_gccsa.csv"


def norm_postcode(s):
    return (
        s.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(4)
    )


def main():

    if not POA_XLSX.exists():
        raise FileNotFoundError(f"Missing: {POA_XLSX}")
    if not MB_XLSX.exists():
        raise FileNotFoundError(f"Missing: {MB_XLSX}")

    print("Reading POA file...")
    poa = pd.read_excel(
        POA_XLSX,
        usecols=["MB_CODE_2021", "POA_CODE_2021", "POA_NAME_2021", "AREA_ALBERS_SQKM"],
        dtype={"MB_CODE_2021": "string", "POA_CODE_2021": "string"},
        engine="openpyxl"
    )

    print("Reading MB file...")
    mb = pd.read_excel(
        MB_XLSX,
        usecols=["MB_CODE_2021", "GCCSA_NAME_2021", "STATE_NAME_2021"],
        dtype={"MB_CODE_2021": "string"},
        engine="openpyxl"
    )

    print("Joining allocation tables...")
    j = poa.merge(mb, on="MB_CODE_2021", how="left", validate="m:1")

    # Keep NSW only
    j = j[j["STATE_NAME_2021"] == "New South Wales"].copy()

    j["AREA_ALBERS_SQKM"] = pd.to_numeric(j["AREA_ALBERS_SQKM"], errors="coerce").fillna(0)

    # Aggregate area per postcode x GCCSA
    agg = (
        j.groupby(["POA_CODE_2021", "POA_NAME_2021", "GCCSA_NAME_2021"])["AREA_ALBERS_SQKM"]
        .sum()
        .reset_index(name="area_weight_sqkm")
    )

    # For each postcode pick GCCSA with largest area
    agg = agg.sort_values(
        ["POA_CODE_2021", "area_weight_sqkm", "GCCSA_NAME_2021"],
        ascending=[True, False, True]
    )

    best = agg.groupby("POA_CODE_2021", as_index=False).head(1).copy()

    best["postcode"] = norm_postcode(best["POA_CODE_2021"])
    best["postcode_name"] = best["POA_NAME_2021"].astype(str).str.strip()
    best["gccsa_name"] = best["GCCSA_NAME_2021"].astype(str).str.strip()

    best["region_group"] = np.where(
        best["gccsa_name"].str.lower() == "greater sydney",
        "Greater Sydney",
        "Rest of NSW"
    )

    out = best[[
        "postcode",
        "region_group",
        "gccsa_name",
        "area_weight_sqkm",
        "postcode_name"
    ]].sort_values("postcode").reset_index(drop=True)

    out.to_csv(OUT_CSV, index=False, encoding="utf-8")

    print("\nSaved:", OUT_CSV)
    print("Total NSW postcodes:", len(out))
    print("\nRegion split:")
    print(out["region_group"].value_counts())


if __name__ == "__main__":
    main()