# build_mart_daily_rolling.py (Polars version, updated API)
from pathlib import Path
import polars as pl

BASE_DIR = Path(__file__).parent
FACT_DIR = BASE_DIR / "Processed" / "fact_sales"
OUT_DIR = BASE_DIR / "Processed" / "mart_daily_rolling"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DIM_DIR = BASE_DIR / "Processed" / "dim"
DIM_GCCSA_PATH = DIM_DIR / "dim_postcode_gccsa.csv"

PRICE_MAX = 100_000_000
PRICE_MIN_EXCLUSIVE = 0
ALLOWED_REGION_GROUPS = {"Greater Sydney", "Rest of NSW"}


def _load_fact() -> pl.DataFrame:
    fact_files = sorted(FACT_DIR.glob("fact_sales_*.parquet"))
    if not fact_files:
        raise FileNotFoundError("No fact files found.")

    dfs = [pl.read_parquet(f) for f in fact_files]
    fact = pl.concat(dfs)

    fact = fact.filter(
        pl.col("dwelling_group").is_in(["HOUSE", "UNIT"]),
        pl.col("purchase_price").is_not_null(),
        pl.col("purchase_price") > PRICE_MIN_EXCLUSIVE,
        pl.col("purchase_price") <= PRICE_MAX,
    )

    # 确保 contract_date 是 Date 类型
    if fact["contract_date"].dtype != pl.Date:
        fact = fact.with_columns(pl.col("contract_date").cast(pl.Date))
    fact = fact.with_columns(pl.col("contract_date").alias("date")).filter(pl.col("date").is_not_null())

    fact = fact.with_columns([
        pl.col("postcode").cast(pl.Utf8).str.strip_chars().str.replace(r"\.0$", "").alias("postcode"),
        pl.col("suburb").cast(pl.Utf8).str.strip_chars().alias("suburb"),
    ])
    return fact


def _load_dim_gccsa() -> pl.DataFrame:
    if not DIM_GCCSA_PATH.exists():
        return pl.DataFrame()
    dim = pl.read_csv(
        DIM_GCCSA_PATH,
        columns=["postcode", "region_group"],
        schema_overrides={"postcode": pl.Utf8, "region_group": pl.Utf8}
    )
    dim = dim.with_columns([
        pl.col("postcode").str.strip_chars().str.replace(r"\.0$", ""),
        pl.col("region_group").str.strip_chars(),
    ]).filter(pl.col("region_group").is_in(ALLOWED_REGION_GROUPS))
    return dim.select(["postcode", "region_group"]).unique(subset=["postcode"])


def _build_level(fact: pl.DataFrame, level: str, dim_gccsa: pl.DataFrame = None) -> pl.DataFrame:
    if level == "NSW":
        df = fact.with_columns(pl.lit("NSW").alias("region"))
    elif level == "REGION":
        if dim_gccsa is None or dim_gccsa.is_empty():
            return pl.DataFrame()
        df = fact.join(dim_gccsa, on="postcode", how="inner")
        df = df.with_columns(pl.col("region_group").alias("region"))
    elif level == "SUBURB":
        df = fact.with_columns(pl.col("suburb").alias("region")).filter(pl.col("region") != "")
    elif level == "POSTCODE":
        df = fact.with_columns(pl.col("postcode").alias("region")).filter(pl.col("region") != "")
    else:
        return pl.DataFrame()

    if df.height == 0:
        return pl.DataFrame()

    df = df.select(["region", "dwelling_group", "date", "purchase_price"])

    # 新版 Polars group_by_dynamic: 使用 group_by 参数，不再需要 check_sorted
    result = (
        df.sort(["region", "dwelling_group", "date"])
        .group_by_dynamic(
            index_column="date",
            every="1d",
            period="28d",
            closed="right",
            group_by=["region", "dwelling_group"],  # 之前是 by
        )
        .agg([
            pl.col("purchase_price").median().alias("rolling_median"),
            pl.col("purchase_price").len().alias("sales_28d"),
        ])
    )

    result = result.with_columns(
        pl.when(pl.col("sales_28d") >= 5)
        .then(pl.col("rolling_median"))
        .otherwise(None)
        .alias("rolling_median")
    )

    result = result.with_columns([
        pl.col("rolling_median")
        .pct_change(28)
        .over(["region", "dwelling_group"])
        .alias("mom"),
        pl.col("rolling_median")
        .pct_change(84)
        .over(["region", "dwelling_group"])
        .alias("qoq"),
    ])

    return result.select(["date", "region", "dwelling_group", "rolling_median", "sales_28d", "mom", "qoq"])


def main():
    print("Loading fact data...")
    fact = _load_fact()
    print(f"Total rows: {fact.height}")

    dim_gccsa = _load_dim_gccsa()
    print(f"Dim GCCSA loaded: {dim_gccsa.height} rows")

    levels = ["NSW", "REGION", "SUBURB", "POSTCODE"]
    for level in levels:
        print(f"Building {level}...")
        df = _build_level(fact, level, dim_gccsa if level == "REGION" else None)
        if df.is_empty():
            print(f"  -> No data for {level}")
            continue
        out_path = OUT_DIR / f"daily_rolling_{level.lower()}.parquet"
        df.write_parquet(out_path)
        print(f"  -> Saved {df.height} rows to {out_path}")

    print("Done.")


if __name__ == "__main__":
    main()