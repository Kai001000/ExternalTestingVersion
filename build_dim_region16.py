# build_dim_region16.py
from __future__ import annotations

from pathlib import Path
import pandas as pd


BASE_DIR = Path(r"C:\Users\jonat\PycharmProjects\NSWpropertyData")
DIM_DIR = BASE_DIR / "Processed" / "dim"
DIM_DIR.mkdir(parents=True, exist_ok=True)

IN_XLSX = BASE_DIR / "Reference" / "ABS" / "sydney_16_region_suburb_postcode_mapping.xlsx"
OUT_CSV = DIM_DIR / "dim_region16_mapping.csv"

REQUIRED_COLS = {
    "region_id",
    "region_key",
    "region_name",
    "suburb_input",
    "suburb_key",
    "postcode",
    "state",
}


def _norm_text_series(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
         .str.strip()
         .str.replace(r"\s+", " ", regex=True)
    )


def _norm_postcode_series(s: pd.Series) -> pd.Series:
    x = (
        s.astype(str)
         .str.strip()
         .str.replace(r"\.0$", "", regex=True)
    )
    x = x.str.extract(r"(\d+)", expand=False).fillna("")
    x = x.where(x == "", x.str.zfill(4))
    return x


def _make_suburb_key_series(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
         .str.strip()
         .str.lower()
         .str.replace(r"&", " and ", regex=True)
         .str.replace(r"[^a-z0-9]+", "_", regex=True)
         .str.replace(r"_+", "_", regex=True)
         .str.strip("_")
    )


def _find_header_row(raw: pd.DataFrame) -> int:
    """
    Scan raw sheet rows and find the row that contains the actual column headers.
    """
    required_probe = {"region_id", "region_key", "region_name", "suburb_input", "postcode"}

    for i in range(len(raw)):
        vals = raw.iloc[i].fillna("").astype(str).str.strip().str.lower().tolist()
        vals_set = set(vals)
        if required_probe.issubset(vals_set):
            return i

    preview = raw.head(10).fillna("").astype(str)
    raise ValueError(
        "[BAD SCHEMA] Could not find header row containing required columns.\n"
        f"Preview first 10 rows:\n{preview.to_string(index=True, header=False)}"
    )


def _read_mapping_sheet(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name="mapping", header=None, engine="openpyxl")
    header_row = _find_header_row(raw)

    print(f"Detected header row at Excel row index: {header_row}")

    df = pd.read_excel(path, sheet_name="mapping", header=header_row, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    return df


def main():
    if not IN_XLSX.exists():
        raise FileNotFoundError(f"Missing mapping file: {IN_XLSX}")

    print("Reading mapping file:", IN_XLSX)
    df = _read_mapping_sheet(IN_XLSX)

    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(
            f"[BAD SCHEMA] mapping sheet missing columns: {sorted(missing)}\n"
            f"Available columns: {list(df.columns)}"
        )

    d = df.copy()

    # keep NSW only
    d["state"] = _norm_text_series(d["state"])
    d = d[d["state"].str.upper() == "NSW"].copy()

    d["region_id"] = pd.to_numeric(d["region_id"], errors="coerce").astype("Int64")
    d["region_key"] = _norm_text_series(d["region_key"]).str.lower()
    d["region_name"] = _norm_text_series(d["region_name"])

    d["suburb"] = _norm_text_series(d["suburb_input"])
    d["suburb_key_generated"] = _make_suburb_key_series(d["suburb"])
    d["suburb_key_from_file"] = _norm_text_series(d["suburb_key"]).str.lower()
    d["postcode"] = _norm_postcode_series(d["postcode"])

    # compare generated suburb_key vs file suburb_key
    mismatch = d[
        (d["suburb_key_from_file"] != "") &
        (d["suburb_key_from_file"] != d["suburb_key_generated"])
    ].copy()

    if not mismatch.empty:
        print("[WARN] suburb_key mismatch found between generated key and file key.")
        print(
            mismatch[["suburb", "suburb_key_from_file", "suburb_key_generated"]]
            .drop_duplicates()
            .head(20)
            .to_string(index=False)
        )

    d = d[
        d["region_id"].notna() &
        (d["region_key"] != "") &
        (d["region_name"] != "") &
        (d["postcode"] != "")
    ].copy()

    if d.empty:
        raise ValueError("No valid rows remain after cleaning mapping file.")

    # ---------------------------------------------------------
    # REGION16 is now postcode-level:
    # if a postcode belongs to a region, all suburb rows within that
    # postcode are intentionally included downstream.
    # ---------------------------------------------------------
    out = d[[
        "region_id",
        "region_key",
        "region_name",
        "postcode",
    ]].drop_duplicates().copy()

    # strict QA:
    # same postcode cannot map to multiple region_keys
    conflict = (
        out.groupby(["postcode"])["region_key"]
           .nunique()
           .reset_index(name="n_region_keys")
    )
    conflict = conflict[conflict["n_region_keys"] > 1]

    if not conflict.empty:
        bad = out.merge(conflict[["postcode"]], on=["postcode"], how="inner")
        raise ValueError(
            "[CONFLICT] Same postcode maps to multiple region_keys.\n"
            f"{bad.sort_values(['postcode', 'region_key']).to_string(index=False)}"
        )

    # optional summary of representative suburb inputs from source file
    postcode_suburb_summary = (
        d.groupby(["region_id", "region_key", "region_name", "postcode"])["suburb"]
         .apply(lambda x: " | ".join(sorted(pd.Series(x).dropna().astype(str).str.strip().unique().tolist())))
         .reset_index(name="source_suburbs")
    )

    out = out.merge(
        postcode_suburb_summary,
        on=["region_id", "region_key", "region_name", "postcode"],
        how="left"
    )

    out = out.sort_values(["region_id", "region_name", "postcode"]).reset_index(drop=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")

    print("\nSaved:", OUT_CSV)
    print("Total postcode mapping rows:", len(out))
    print("Distinct regions:", out["region_key"].nunique())
    print("Distinct postcodes:", out["postcode"].nunique())

    print("\nPostcodes per region:")
    print(
        out.groupby(["region_id", "region_name"])
           .agg(
               postcodes=("postcode", "nunique"),
               source_rows=("source_suburbs", "count"),
           )
           .reset_index()
           .to_string(index=False)
    )

    print("\nSample output:")
    print(out.head(20).to_string(index=False))


if __name__ == "__main__":
    main()