# build_mart_monthly_all_years.py
from pathlib import Path
import re
import pandas as pd
import numpy as np

BASE_DIR = Path(r"C:\Users\jonat\PycharmProjects\NSWpropertyData")
FACT_DIR = BASE_DIR / "Processed" / "fact_sales"
OUT_DIR = BASE_DIR / "Processed" / "mart_monthly"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DIM_DIR = BASE_DIR / "Processed" / "dim"
DIM_DIR.mkdir(parents=True, exist_ok=True)

DIM_GCCSA_PATH = DIM_DIR / "dim_postcode_gccsa.csv"
DIM_REGION16_PATH = DIM_DIR / "dim_region16_mapping.csv"

PRICE_MAX = 100_000_000
PRICE_MIN_EXCLUSIVE = 0

REQUIRED_FACT_COLS = {
    "sale_key",
    "dwelling_group",
    "purchase_price",
    "contract_date",
    "event_week_start",
    "suburb",
    "postcode",
}

REQUIRED_DIM_GCCSA_COLS = {"postcode", "region_group"}
REQUIRED_DIM_REGION16_COLS = {"region_id", "region_key", "region_name", "suburb_key", "postcode"}

ALLOWED_REGION_GROUPS = {"Greater Sydney", "Rest of NSW"}


def _ensure_datetime(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _norm_postcode_series(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
         .str.strip()
         .str.replace(r"\.0$", "", regex=True)
    )


def _norm_suburb_series(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
         .str.strip()
         .str.replace(r"\s+", " ", regex=True)
    )


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


def _load_dim_gccsa(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"[MISSING DIM] {path}\n"
            f"Please create postcode -> region_group dim first."
        )

    d = pd.read_csv(path, dtype=str)
    missing = REQUIRED_DIM_GCCSA_COLS - set(d.columns)
    if missing:
        raise ValueError(f"[BAD DIM SCHEMA] {path.name} missing columns: {sorted(missing)}")

    d = d.copy()
    d["postcode"] = _norm_postcode_series(d["postcode"])
    d["region_group"] = d["region_group"].astype(str).str.strip()
    d.loc[~d["region_group"].isin(ALLOWED_REGION_GROUPS), "region_group"] = np.nan
    d = d.dropna(subset=["postcode"]).drop_duplicates(subset=["postcode"], keep="first")

    return d


def _load_dim_region16(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"[MISSING DIM] {path}\n"
            f"Please create the Market Region compatibility dim first."
        )

    d = pd.read_csv(path, dtype=str)
    missing = REQUIRED_DIM_REGION16_COLS - set(d.columns)
    if missing:
        raise ValueError(f"[BAD DIM SCHEMA] {path.name} missing columns: {sorted(missing)}")

    d = d.copy()
    d["region_id"] = pd.to_numeric(d["region_id"], errors="coerce").astype("Int64")
    d["region_key"] = d["region_key"].astype(str).str.strip()
    d["region_name"] = d["region_name"].astype(str).str.strip()
    d["suburb_key"] = d["suburb_key"].astype(str).str.strip().str.lower()
    d["postcode"] = _norm_postcode_series(d["postcode"])

    d = d.drop_duplicates(subset=["suburb_key", "postcode"], keep="first")
    return d


def _attach_region_group(df: pd.DataFrame, dim_gccsa: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["postcode"] = _norm_postcode_series(out["postcode"])
    out = out.merge(dim_gccsa, on="postcode", how="left")
    out["region_group"] = out["region_group"].fillna("Unknown")
    return out


def _attach_region16(df: pd.DataFrame, dim_region16: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["postcode"] = _norm_postcode_series(out["postcode"])
    out["suburb"] = _norm_suburb_series(out["suburb"])
    out["suburb_key"] = _make_suburb_key_series(out["suburb"])

    out = out.merge(
        dim_region16[["region_id", "region_key", "region_name", "suburb_key", "postcode"]],
        on=["suburb_key", "postcode"],
        how="left",
    )

    out["region16_name"] = out["region_name"].fillna("Unknown")
    out["region16_key"] = out["region_key"].fillna("unknown")
    return out


def _load_and_filter_fact(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)

    missing = REQUIRED_FACT_COLS - set(df.columns)
    if missing:
        raise ValueError(f"[BAD FACT SCHEMA] {path.name} missing columns: {sorted(missing)}")

    df = df.copy()
    df["postcode"] = _norm_postcode_series(df["postcode"])
    df["suburb"] = _norm_suburb_series(df["suburb"])

    df = _ensure_datetime(df, "contract_date")
    df = _ensure_datetime(df, "event_week_start")

    df = df[df["dwelling_group"].isin(["HOUSE", "UNIT"])].copy()
    df = df[df["purchase_price"].notna()].copy()
    df = df[(df["purchase_price"] > PRICE_MIN_EXCLUSIVE) & (df["purchase_price"] <= PRICE_MAX)].copy()
    df = df[df["contract_date"].notna()].copy()
    df = df[df["event_week_start"].notna()].copy()

    return df


def _add_month_start_from_contract(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["event_month_start"] = df["contract_date"].dt.to_period("M").dt.to_timestamp()
    return df


def _build_level(df: pd.DataFrame, level: str) -> pd.DataFrame:
    df2 = _add_month_start_from_contract(df)

    if level == "NSW":
        df2["region"] = "NSW"

    elif level == "REGION":
        if "region_group" not in df2.columns:
            raise ValueError("[REGION LEVEL] region_group missing.")
        df2["region"] = df2["region_group"].astype(str).str.strip()
        allowed = ALLOWED_REGION_GROUPS | {"Unknown"}
        df2 = df2[df2["region"].isin(allowed)].copy()

    elif level == "REGION16":
        if "region16_name" not in df2.columns:
            raise ValueError("[REGION16 LEVEL] region16_name missing.")
        df2["region"] = df2["region16_name"].astype(str).str.strip()
        df2 = df2[df2["region"] != ""].copy()

    elif level == "SUBURB":
        df2["region"] = df2["suburb"].astype(str).str.strip()
        df2 = df2[df2["region"] != ""].copy()

    elif level == "POSTCODE":
        df2["region"] = _norm_postcode_series(df2["postcode"])
        df2 = df2[df2["region"] != ""].copy()

    else:
        raise ValueError("Invalid level")

    mart = (
        df2.groupby(["event_month_start", "region", "dwelling_group"], dropna=False)
           .agg(
               monthly_sales_count=("sale_key", "size"),
               monthly_median_price=("purchase_price", "median"),
               monthly_max_price=("purchase_price", "max"),
               monthly_min_price=("purchase_price", "min"),
           )
           .reset_index()
    )

    return mart


def main():
    fact_files = sorted(FACT_DIR.glob("fact_sales_*.parquet"))
    if not fact_files:
        raise FileNotFoundError(f"No fact_sales files found under: {FACT_DIR}")

    dim_gccsa = _load_dim_gccsa(DIM_GCCSA_PATH)
    dim_region16 = _load_dim_region16(DIM_REGION16_PATH)

    dfs = []
    years = []

    for f in fact_files:
        m = re.search(r"fact_sales_(\d{4})\.parquet", f.name)
        if m:
            years.append(int(m.group(1)))

        d = _load_and_filter_fact(f)
        d = _attach_region_group(d, dim_gccsa)
        d = _attach_region16(d, dim_region16)
        dfs.append(d)

    df = pd.concat(dfs, ignore_index=True)
    label = f"{min(years)}_{max(years)}" if years else "all_years"

    print("REGION_GROUP counts:")
    print(df["region_group"].value_counts(dropna=False))

    print("\nMarket Region counts (legacy REGION16 token):")
    print(df["region16_name"].value_counts(dropna=False).head(30))

    print("\nBuilding MONTHLY mart for years:", sorted(years) if years else "(unknown)")
    print("Rows after filters:", f"{len(df):,}")
    print("contract_date min/max:", df["contract_date"].min(), df["contract_date"].max())
    print("purchase_price min/max:", int(df["purchase_price"].min()), int(df["purchase_price"].max()))
    print("Dim GCCSA:", DIM_GCCSA_PATH)
    print("Dim Market Region (legacy REGION16 path):", DIM_REGION16_PATH)

    _build_level(df, "NSW").to_parquet(OUT_DIR / f"mart_monthly_nsw_{label}.parquet", index=False)
    _build_level(df, "REGION").to_parquet(OUT_DIR / f"mart_monthly_region_{label}.parquet", index=False)
    _build_level(df, "REGION16").to_parquet(OUT_DIR / f"mart_monthly_region16_{label}.parquet", index=False)
    _build_level(df, "SUBURB").to_parquet(OUT_DIR / f"mart_monthly_suburb_{label}.parquet", index=False)
    _build_level(df, "POSTCODE").to_parquet(OUT_DIR / f"mart_monthly_postcode_{label}.parquet", index=False)

    print("Monthly mart built successfully.")
    print("Saved to:", OUT_DIR)


if __name__ == "__main__":
    main()
