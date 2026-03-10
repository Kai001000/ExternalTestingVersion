# build_dim_suburb_postcode.py
# Build dim: suburb -> primary postcode (based on NSW sales fact rows)
#
# Output:
#   Processed/dim/dim_suburb_postcode.csv
#
# Logic:
#   - Normalize suburb (strip, collapse spaces)
#   - Normalize postcode (digits, zfill 4)
#   - Count rows by (suburb, postcode)
#   - For each suburb, pick postcode with max count (tie-break: smaller postcode)
#   - Provide share = top_count / suburb_total_count as a mapping confidence indicator
#
# Notes:
#   - This does NOT rely on ABS for suburb->postcode (ABS doesn't provide suburb mapping directly).
#   - It uses your transaction behavior (sales rows), which is consistent with your ranking metrics.

from __future__ import annotations

from pathlib import Path
import re
import sys
import pandas as pd


# ====== project paths (match your project style) ======
BASE_DIR = Path(r"C:\Users\jonat\PycharmProjects\NSWpropertyData")
PROCESSED_DIR = BASE_DIR / "Processed"
DIM_DIR = PROCESSED_DIR / "dim"
DIM_DIR.mkdir(parents=True, exist_ok=True)

OUT_CSV = DIM_DIR / "dim_suburb_postcode.csv"


# -------------------------
# Helpers
# -------------------------
def _norm_suburb(s: pd.Series) -> pd.Series:
    x = s.astype(str).str.strip()
    # collapse multi spaces
    x = x.str.replace(r"\s+", " ", regex=True)
    # normalize obvious null tokens
    null_tokens = {"", "none", "nan", "na", "n/a", "null", "unknown", "unknow"}
    x = x.where(~x.str.lower().isin(null_tokens), "")
    return x


def _norm_postcode(s: pd.Series) -> pd.Series:
    x = s.astype(str).str.strip()
    null_tokens = {"", "none", "nan", "na", "n/a", "null", "unknown", "unknow"}
    x = x.where(~x.str.lower().isin(null_tokens), "")
    # keep digits only
    x = x.str.replace(r"\.0$", "", regex=True)
    x = x.str.extract(r"(\d+)", expand=False).fillna("")
    # zfill to 4 digits but keep blank as blank
    x = x.where(x == "", x.str.zfill(4))
    return x


def _pick_first_existing(cols: list[str], candidates: list[str]) -> str | None:
    cols_low = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in cols_low:
            return cols_low[cand.lower()]
    return None


def _find_fact_file() -> Path | None:
    """
    Try to locate a row-level fact file automatically.
    You can still pass a path as CLI arg.
    """
    candidates = []

    # Common folders in your project
    search_dirs = [
        PROCESSED_DIR / "fact",
        PROCESSED_DIR / "silver",
        PROCESSED_DIR / "bronze",
        PROCESSED_DIR,
    ]

    # Common filename patterns
    patterns = [
        re.compile(r"fact.*sales.*\.(parquet|csv)$", re.IGNORECASE),
        re.compile(r"sales.*fact.*\.(parquet|csv)$", re.IGNORECASE),
        re.compile(r"fact_.*\.(parquet|csv)$", re.IGNORECASE),
    ]

    for d in search_dirs:
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            name = p.name
            if any(ptn.search(name) for ptn in patterns):
                candidates.append(p)

    if not candidates:
        return None

    # Prefer parquet > csv, and prefer most recently modified
    def score(p: Path) -> tuple[int, float]:
        ext_score = 2 if p.suffix.lower() == ".parquet" else 1
        mtime = p.stat().st_mtime
        return (ext_score, mtime)

    candidates = sorted(candidates, key=score, reverse=True)
    return candidates[0]


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported file type: {path}")


# -------------------------
# Main
# -------------------------
def main():
    # Allow user to pass file path
    # Usage:
    #   python build_dim_suburb_postcode.py
    #   python build_dim_suburb_postcode.py C:\path\to\fact_sales.parquet
    in_path: Path | None = None
    if len(sys.argv) >= 2:
        in_path = Path(sys.argv[1])
        if not in_path.exists():
            raise FileNotFoundError(f"Input file not found: {in_path}")
    else:
        in_path = _find_fact_file()

    if in_path is None:
        raise FileNotFoundError(
            "Could not find a row-level sales fact file automatically.\n"
            "Please pass it explicitly, e.g.:\n"
            "  python build_dim_suburb_postcode.py C:\\Users\\jonat\\PycharmProjects\\NSWpropertyData\\Processed\\fact\\fact_sales.parquet"
        )

    print("Reading fact file:", in_path)
    df = _read_table(in_path)
    if df.empty:
        raise ValueError("Fact file is empty.")

    # Heuristic column detection
    suburb_col = _pick_first_existing(
        list(df.columns),
        candidates=[
            "suburb",
            "suburb_name",
            "locality",
            "locality_name",
            "suburb_locality",
            "property_suburb",
        ],
    )
    postcode_col = _pick_first_existing(
        list(df.columns),
        candidates=[
            "postcode",
            "post_code",
            "post code",
            "poa",
            "poa_code",
            "postal_code",
            "postalcode",
            "zip",
        ],
    )

    if suburb_col is None or postcode_col is None:
        raise KeyError(
            "Cannot detect suburb/postcode columns in your fact file.\n"
            f"Detected suburb_col={suburb_col}, postcode_col={postcode_col}\n\n"
            "Available columns:\n"
            f"{list(df.columns)}\n\n"
            "Fix options:\n"
            "1) Rename your fact columns to 'suburb' and 'postcode', OR\n"
            "2) Update the candidates list in this script."
        )

    print(f"Using columns: suburb='{suburb_col}', postcode='{postcode_col}'")

    d = df[[suburb_col, postcode_col]].copy()
    d.rename(columns={suburb_col: "suburb", postcode_col: "postcode"}, inplace=True)

    d["suburb"] = _norm_suburb(d["suburb"])
    d["postcode"] = _norm_postcode(d["postcode"])

    # Drop blanks
    d = d[(d["suburb"] != "") & (d["postcode"] != "")].copy()
    if d.empty:
        raise ValueError("After normalization, no valid suburb/postcode rows remain.")

    # Count rows per pair
    agg = (
        d.groupby(["suburb", "postcode"], as_index=False)
        .size()
        .rename(columns={"size": "sales_row_count"})
    )

    # Total per suburb
    tot = (
        agg.groupby("suburb", as_index=False)["sales_row_count"]
        .sum()
        .rename(columns={"sales_row_count": "suburb_total_sales_rows"})
    )

    agg = agg.merge(tot, on="suburb", how="left", validate="m:1")
    agg["share"] = agg["sales_row_count"] / agg["suburb_total_sales_rows"]

    # Pick primary postcode per suburb: max count; tie-break: smaller postcode
    agg = agg.sort_values(
        ["suburb", "sales_row_count", "postcode"],
        ascending=[True, False, True],
    )

    best = agg.groupby("suburb", as_index=False).head(1).copy()

    out = best[[
        "suburb",
        "postcode",
        "sales_row_count",
        "suburb_total_sales_rows",
        "share",
    ]].copy()

    out.rename(columns={
        "sales_row_count": "primary_postcode_sales_rows",
        "share": "primary_postcode_share",
    }, inplace=True)

    out = out.sort_values(["primary_postcode_share", "suburb_total_sales_rows"], ascending=[False, False]).reset_index(drop=True)

    out.to_csv(OUT_CSV, index=False, encoding="utf-8")

    print("\nSaved:", OUT_CSV)
    print("Total suburbs mapped:", len(out))
    print("Example rows:")
    print(out.head(10).to_string(index=False))


if __name__ == "__main__":
    main()