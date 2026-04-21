from __future__ import annotations

from pathlib import Path
import pandas as pd


BASE_DIR = Path(r"C:\Users\jonat\PycharmProjects\NSWpropertyData")
DIM_DIR = BASE_DIR / "Processed" / "dim"
OUT_DIR = DIM_DIR / "validation_market_region"
OUT_DIR.mkdir(parents=True, exist_ok=True)

REGION16_PATH = DIM_DIR / "dim_region16_mapping.csv"
SUBURB_POSTCODE_DIM_PATH = DIM_DIR / "dim_suburb_postcode.csv"   # 按你的真实文件名改

REQUIRED_REGION16_COLS = {
    "region_id", "region_key", "region_name", "suburb", "suburb_key", "postcode"
}

# 这里尽量兼容不同 dim_suburb_postcode 字段名
SUBURB_CANDIDATE_COLS = ["suburb", "suburb_official", "suburb_name", "suburb_official_sal_2021"]
POSTCODE_CANDIDATE_COLS = ["postcode", "postcode_str"]
SUBURB_KEY_CANDIDATE_COLS = ["suburb_key"]


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


def _pick_first_existing(df: pd.DataFrame, candidates: list[str], label: str) -> str:
    for c in candidates:
        if c in df.columns:
            return c
    raise ValueError(f"Could not find a valid column for {label}. Candidates tried: {candidates}")


def _load_region16(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    df = pd.read_csv(path, dtype=str)
    missing = REQUIRED_REGION16_COLS - set(df.columns)
    if missing:
        raise ValueError(
            f"dim_region16_mapping.csv missing columns: {sorted(missing)}\n"
            f"Available columns: {list(df.columns)}"
        )

    d = df.copy()
    d["region_id"] = pd.to_numeric(d["region_id"], errors="coerce").astype("Int64")
    d["region_key"] = _norm_text_series(d["region_key"]).str.lower()
    d["region_name"] = _norm_text_series(d["region_name"])
    d["suburb"] = _norm_text_series(d["suburb"])
    d["suburb_key"] = _norm_text_series(d["suburb_key"]).str.lower()
    d["postcode"] = _norm_postcode_series(d["postcode"])

    d = d[
        d["region_id"].notna() &
        (d["region_key"] != "") &
        (d["region_name"] != "") &
        (d["suburb_key"] != "") &
        (d["postcode"] != "")
    ].drop_duplicates().copy()

    return d


def _load_suburb_postcode_dim(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=str)
    elif path.suffix.lower() in [".xlsx", ".xls"]:
        df = pd.read_excel(path, dtype=str, engine="openpyxl")
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")

    suburb_col = _pick_first_existing(df, SUBURB_CANDIDATE_COLS, "suburb")
    postcode_col = _pick_first_existing(df, POSTCODE_CANDIDATE_COLS, "postcode")

    suburb_key_col = None
    for c in SUBURB_KEY_CANDIDATE_COLS:
        if c in df.columns:
            suburb_key_col = c
            break

    out = df.copy()
    out["suburb_raw"] = _norm_text_series(out[suburb_col])
    out["postcode"] = _norm_postcode_series(out[postcode_col])

    if suburb_key_col:
        out["suburb_key"] = _norm_text_series(out[suburb_key_col]).str.lower()
    else:
        out["suburb_key"] = _make_suburb_key_series(out["suburb_raw"])

    out = out[
        (out["suburb_raw"] != "") &
        (out["suburb_key"] != "") &
        (out["postcode"] != "")
    ][["suburb_raw", "suburb_key", "postcode"]].drop_duplicates().copy()

    return out


def main():
    print("Loading Market Region mapping...")
    region16 = _load_region16(REGION16_PATH)
    print(f"Market Region rows: {len(region16):,}")

    print("Loading suburb-postcode dimension...")
    dim_sp = _load_suburb_postcode_dim(SUBURB_POSTCODE_DIM_PATH)
    print(f"suburb-postcode distinct rows: {len(dim_sp):,}")

    # ---------------------------------------------------
    # 1) 精确逻辑：suburb_key + postcode
    # ---------------------------------------------------
    exact = region16.merge(
        dim_sp,
        on=["suburb_key", "postcode"],
        how="left",
        validate="1:m"
    )

    exact["matched_exact"] = exact["suburb_raw"].notna()

    exact_out = exact[[
        "region_id", "region_key", "region_name",
        "suburb", "suburb_key", "postcode",
        "suburb_raw", "matched_exact"
    ]].sort_values(["region_id", "postcode", "suburb_key"])

    exact_out.to_csv(
        OUT_DIR / "validation_market_region_included_suburbs_exact.csv",
        index=False,
        encoding="utf-8"
    )

    unmatched_exact = exact_out[~exact_out["matched_exact"]].copy()
    unmatched_exact.to_csv(
        OUT_DIR / "validation_market_region_exact_unmatched_rows.csv",
        index=False,
        encoding="utf-8"
    )

    # ---------------------------------------------------
    # 2) postcode-only 逻辑：postcode
    # ---------------------------------------------------
    postcode_only = region16[["region_id", "region_key", "region_name", "postcode"]].drop_duplicates().merge(
        dim_sp,
        on="postcode",
        how="left",
        validate="1:m"
    )

    postcode_only = postcode_only.sort_values(["region_id", "postcode", "suburb_key"]).reset_index(drop=True)
    postcode_only.to_csv(
        OUT_DIR / "validation_market_region_included_suburbs_postcode_only.csv",
        index=False,
        encoding="utf-8"
    )

    # ---------------------------------------------------
    # 3) postcode 扩散检查：
    #    某个 region 的某个 postcode 下，dim_sp 里有的 suburb，
    #    但 region16 mapping 里没显式列出来
    # ---------------------------------------------------
    region16_keys = region16[[
        "region_id", "region_key", "region_name", "postcode", "suburb_key"
    ]].drop_duplicates().copy()
    region16_keys["in_mapping"] = True

    postcode_expansion = postcode_only.merge(
        region16_keys,
        on=["region_id", "region_key", "region_name", "postcode", "suburb_key"],
        how="left"
    )

    postcode_expansion["in_mapping"] = postcode_expansion["in_mapping"].fillna(False)
    postcode_expansion["would_be_extra_if_postcode_only"] = ~postcode_expansion["in_mapping"]

    postcode_expansion = postcode_expansion[[
        "region_id", "region_key", "region_name",
        "postcode", "suburb_raw", "suburb_key",
        "in_mapping", "would_be_extra_if_postcode_only"
    ]].sort_values(["region_id", "postcode", "suburb_key"])

    postcode_expansion.to_csv(
        OUT_DIR / "validation_market_region_postcode_expansion.csv",
        index=False,
        encoding="utf-8"
    )

    extra_rows = postcode_expansion[postcode_expansion["would_be_extra_if_postcode_only"]].copy()
    extra_rows.to_csv(
        OUT_DIR / "validation_market_region_postcode_only_extra_rows.csv",
        index=False,
        encoding="utf-8"
    )

    # ---------------------------------------------------
    # 4) 摘要统计
    # ---------------------------------------------------
    summary = (
        postcode_expansion.groupby(["region_id", "region_key", "region_name"])
        .agg(
            postcode_only_suburbs=("suburb_key", "nunique"),
            extra_suburbs_if_postcode_only=("would_be_extra_if_postcode_only", "sum"),
        )
        .reset_index()
    )

    mapping_count = (
        region16.groupby(["region_id", "region_key", "region_name"])
        .agg(mapping_rows=("suburb_key", "nunique"))
        .reset_index()
    )

    summary = summary.merge(
        mapping_count,
        on=["region_id", "region_key", "region_name"],
        how="left"
    )

    summary["delta_vs_mapping"] = summary["postcode_only_suburbs"] - summary["mapping_rows"]

    summary = summary.sort_values(["region_id", "region_name"])
    summary.to_csv(
        OUT_DIR / "validation_market_region_summary.csv",
        index=False,
        encoding="utf-8"
    )

    print("\nSaved outputs to:", OUT_DIR)
    print("\nSummary:")
    print(summary.to_string(index=False))

    if not extra_rows.empty:
        print("\n[WARN] Found suburbs that would be incorrectly included under postcode-only logic.")
        print(extra_rows.head(30).to_string(index=False))
    else:
        print("\n[OK] No extra suburbs found under postcode-only logic.")


if __name__ == "__main__":
    main()
