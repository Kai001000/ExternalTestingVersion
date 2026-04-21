# build_dim_region16.py
from __future__ import annotations

from pathlib import Path
import pandas as pd


BASE_DIR = Path(r"C:\Users\jonat\PycharmProjects\NSWpropertyData")
DIM_DIR = BASE_DIR / "Processed" / "dim"
DIM_DIR.mkdir(parents=True, exist_ok=True)

IN_XLSX = BASE_DIR / "Reference" / "ABS" / "sydney_16_region_suburb_postcode_mapping.xlsx"
IN_SUPPLEMENT_CSV = BASE_DIR / "Reference" / "ABS" / "market_region_mapping_overrides.csv"
SUBURB_POSTCODE_DIM_CSV = DIM_DIR / "dim_suburb_postcode.csv"
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


def _read_mapping_supplement(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=[
            "region_id",
            "region_key",
            "region_name",
            "suburb_input",
            "suburb_key",
            "suburb_official_sal_2021",
            "postcode",
            "state",
            "mmm_2023",
            "postcode_in_uploaded_POA_2021",
            "match_note",
            "source_dataset",
            "source_url",
        ])

    df = pd.read_csv(path, dtype=str).fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _load_suburb_postcode_dim(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["suburb", "suburb_key", "postcode"])

    df = pd.read_csv(path, dtype=str).fillna("")
    if not {"suburb", "postcode"}.issubset(df.columns):
        return pd.DataFrame(columns=["suburb", "suburb_key", "postcode"])

    out = df.copy()
    out["suburb"] = _norm_text_series(out["suburb"])
    out["suburb_key"] = _make_suburb_key_series(out["suburb"])
    out["postcode"] = _norm_postcode_series(out["postcode"])
    out = out[
        (out["suburb"] != "")
        & (out["suburb_key"] != "")
        & (out["postcode"] != "")
    ][["suburb", "suburb_key", "postcode"]].drop_duplicates()
    return out


def main():
    if not IN_XLSX.exists():
        raise FileNotFoundError(f"Missing mapping file: {IN_XLSX}")

    print("Reading mapping file:", IN_XLSX)
    df = _read_mapping_sheet(IN_XLSX)
    supplement = _read_mapping_supplement(IN_SUPPLEMENT_CSV)
    if not supplement.empty:
        print("Reading Market Region supplement:", IN_SUPPLEMENT_CSV)
        df = pd.concat([df, supplement], ignore_index=True, sort=False)

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
    # Legacy internal token = REGION16.
    # Canonical product meaning = Market Region.
    # Market Region assignment is postcode-level. Downstream consumers
    # should be able to attribute every suburb in a mapped postcode to
    # that Market Region without assuming the layer is fixed at 16 rows.
    # ---------------------------------------------------------
    postcode_scope = d[[
        "region_id",
        "region_key",
        "region_name",
        "postcode",
    ]].drop_duplicates().copy()

    # strict QA:
    # same postcode cannot map to multiple region_keys
    conflict = (
        postcode_scope.groupby(["postcode"])["region_key"]
           .nunique()
           .reset_index(name="n_region_keys")
    )
    conflict = conflict[conflict["n_region_keys"] > 1]

    if not conflict.empty:
        bad = postcode_scope.merge(conflict[["postcode"]], on=["postcode"], how="inner")
        raise ValueError(
            "[CONFLICT] Same postcode maps to multiple region_keys.\n"
            f"{bad.sort_values(['postcode', 'region_key']).to_string(index=False)}"
        )

    postcode_suburb_summary = (
        d.groupby(["region_id", "region_key", "region_name", "postcode"])["suburb"]
         .apply(lambda x: " | ".join(sorted(pd.Series(x).dropna().astype(str).str.strip().unique().tolist())))
         .reset_index(name="source_suburbs")
    )

    suburb_dim = _load_suburb_postcode_dim(SUBURB_POSTCODE_DIM_CSV)
    if suburb_dim.empty:
        expanded = d[[
            "region_id",
            "region_key",
            "region_name",
            "suburb",
            "suburb_key_generated",
            "postcode",
        ]].rename(
            columns={
                "suburb": "suburb",
                "suburb_key_generated": "suburb_key",
            }
        )
    else:
        expanded = postcode_scope.merge(suburb_dim, on="postcode", how="left")
        expanded["suburb"] = expanded["suburb"].fillna("")
        expanded["suburb_key"] = expanded["suburb_key"].fillna("")

        source_fallback = d[[
            "region_id",
            "region_key",
            "region_name",
            "suburb",
            "suburb_key_generated",
            "postcode",
        ]].rename(columns={"suburb_key_generated": "suburb_key"})
        expanded = pd.concat([expanded, source_fallback], ignore_index=True, sort=False)

    out = expanded.merge(
        postcode_suburb_summary,
        on=["region_id", "region_key", "region_name", "postcode"],
        how="left"
    )

    out["suburb"] = _norm_text_series(out["suburb"])
    out["suburb_key"] = _norm_text_series(out["suburb_key"]).str.lower()
    out = out[
        (out["suburb"] != "")
        & (out["suburb_key"] != "")
        & (out["postcode"] != "")
    ].drop_duplicates(subset=["region_key", "postcode", "suburb_key"]).copy()

    out = out.sort_values(["region_id", "region_name", "postcode"]).reset_index(drop=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")

    print("\nSaved:", OUT_CSV)
    print("Total Market Region mapping rows:", len(out))
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
