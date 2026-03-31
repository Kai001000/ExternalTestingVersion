# build_mart_daily_rolling.py
from pathlib import Path
import polars as pl

BASE_DIR = Path(__file__).parent
FACT_DIR = BASE_DIR / "Processed" / "fact_sales"
OUT_DIR = BASE_DIR / "Processed" / "mart_daily_rolling"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DIM_DIR = BASE_DIR / "Processed" / "dim"
DIM_GCCSA_PATH = DIM_DIR / "dim_postcode_gccsa.csv"
DIM_REGION16_PATH = DIM_DIR / "dim_region16_mapping.csv"

PRICE_MAX = 100_000_000
PRICE_MIN_EXCLUSIVE = 0
ALLOWED_REGION_GROUPS = {"Greater Sydney", "Rest of NSW"}


def _make_suburb_key_expr(col_name: str) -> pl.Expr:
    return (
        pl.col(col_name)
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.to_lowercase()
        .str.replace_all(r"&", " and ")
        .str.replace_all(r"[^a-z0-9]+", "_")
        .str.replace_all(r"_+", "_")
        .str.strip_chars("_")
    )


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

    if fact["contract_date"].dtype != pl.Date:
        fact = fact.with_columns(pl.col("contract_date").cast(pl.Date))

    fact = (
        fact.with_columns([
            pl.col("contract_date").alias("date"),
            pl.col("postcode").cast(pl.Utf8).str.strip_chars().str.replace(r"\.0$", "").alias("postcode"),
            pl.col("suburb").cast(pl.Utf8).str.strip_chars().alias("suburb"),
            _make_suburb_key_expr("suburb").alias("suburb_key"),
        ])
        .filter(pl.col("date").is_not_null())
    )

    return fact


def _load_dim_gccsa() -> pl.DataFrame:
    if not DIM_GCCSA_PATH.exists():
        return pl.DataFrame()

    dim = pl.read_csv(
        DIM_GCCSA_PATH,
        columns=["postcode", "region_group"],
        schema_overrides={"postcode": pl.Utf8, "region_group": pl.Utf8},
    )

    dim = (
        dim.with_columns([
            pl.col("postcode").str.strip_chars().str.replace(r"\.0$", ""),
            pl.col("region_group").str.strip_chars(),
        ])
        .filter(pl.col("region_group").is_in(ALLOWED_REGION_GROUPS))
        .select(["postcode", "region_group"])
        .unique(subset=["postcode"])
    )
    return dim


def _load_dim_region16() -> pl.DataFrame:
    if not DIM_REGION16_PATH.exists():
        return pl.DataFrame()

    dim = pl.read_csv(
        DIM_REGION16_PATH,
        schema_overrides={
            "region_id": pl.Int64,
            "region_key": pl.Utf8,
            "region_name": pl.Utf8,
            "postcode": pl.Utf8,
            "source_suburbs": pl.Utf8,
        },
    )

    required_cols = {"region_id", "region_key", "region_name", "postcode"}
    missing = required_cols - set(dim.columns)
    if missing:
        raise ValueError(
            f"DIM_REGION16 missing required columns: {sorted(missing)} | "
            f"available={dim.columns}"
        )

    dim = (
        dim.with_columns([
            pl.col("region_key").cast(pl.Utf8).str.strip_chars(),
            pl.col("region_name").cast(pl.Utf8).str.strip_chars(),
            pl.col("postcode").cast(pl.Utf8).str.strip_chars().str.replace(r"\.0$", ""),
        ])
        .filter(
            pl.col("region_key").is_not_null() &
            (pl.col("region_key") != "") &
            pl.col("region_name").is_not_null() &
            (pl.col("region_name") != "") &
            pl.col("postcode").is_not_null() &
            (pl.col("postcode") != "")
        )
        .select(["region_id", "region_key", "region_name", "postcode"])
        .unique(subset=["postcode"])
    )

    # QA: postcode should map to one region only
    dup_postcodes = (
        dim.group_by("postcode")
           .agg(pl.len().alias("n"))
           .filter(pl.col("n") > 1)
    )
    if dup_postcodes.height > 0:
        raise ValueError(
            "[CONFLICT] Same postcode maps to multiple REGION16 rows.\n"
            f"{dup_postcodes}"
        )

    return dim


def _build_level(
    fact: pl.DataFrame,
    level: str,
    dim_gccsa: pl.DataFrame | None = None,
    dim_region16: pl.DataFrame | None = None,
) -> pl.DataFrame:
    if level == "NSW":
        df = fact.with_columns(pl.lit("NSW").alias("region"))

    elif level == "REGION":
        if dim_gccsa is None or dim_gccsa.is_empty():
            return pl.DataFrame()
        df = fact.join(dim_gccsa, on="postcode", how="inner")
        df = df.with_columns(pl.col("region_group").alias("region"))

    elif level == "REGION16":
        if dim_region16 is None or dim_region16.is_empty():
            return pl.DataFrame()
        # REGION16 is postcode-based by design
        df = fact.join(dim_region16, on="postcode", how="inner")
        df = df.with_columns(pl.col("region_name").alias("region"))

    elif level == "SUBURB":
        df = fact.with_columns(pl.col("suburb").alias("region")).filter(pl.col("region") != "")

    elif level == "POSTCODE":
        df = fact.with_columns(pl.col("postcode").alias("region")).filter(pl.col("region") != "")

    else:
        return pl.DataFrame()

    if df.height == 0:
        return pl.DataFrame()

    df = df.select(["region", "dwelling_group", "date", "purchase_price"])
    max_date = df.select(pl.col("date").max()).item()

    result = (
        df.sort(["region", "dwelling_group", "date"])
        .group_by_dynamic(
            index_column="date",
            every="1d",
            period="28d",
            closed="right",
            label="right",
            group_by=["region", "dwelling_group"],
        )
        .agg([
            pl.col("purchase_price").median().alias("rolling_median"),
            pl.col("purchase_price").len().alias("sales_28d"),
        ])
    )
    result = result.filter(pl.col("date") <= max_date)

    result = (
        result.with_columns(
            pl.when(pl.col("sales_28d") >= 5)
            .then(pl.col("rolling_median"))
            .otherwise(None)
            .alias("rolling_median")
        )
        .with_columns([
            pl.col("rolling_median")
            .pct_change(28)
            .over(["region", "dwelling_group"])
            .alias("mom"),

            pl.col("rolling_median")
            .pct_change(84)
            .over(["region", "dwelling_group"])
            .alias("qoq"),
        ])
        .select(["date", "region", "dwelling_group", "rolling_median", "sales_28d", "mom", "qoq"])
    )

    return result


def main():
    print("Loading fact data...")
    fact = _load_fact()
    print(f"Total fact rows after filters: {fact.height:,}")

    dim_gccsa = _load_dim_gccsa()
    print(f"Dim GCCSA loaded: {dim_gccsa.height:,} rows")

    dim_region16 = _load_dim_region16()
    print(f"Dim REGION16 loaded: {dim_region16.height:,} rows")

    if not dim_region16.is_empty():
        matched = fact.join(dim_region16, on="postcode", how="inner").height
        print(f"REGION16 matched fact rows (postcode-based): {matched:,}")

    levels = ["NSW", "REGION", "REGION16", "SUBURB", "POSTCODE"]

    for level in levels:
        print(f"Building {level}...")
        df = _build_level(
            fact,
            level,
            dim_gccsa=dim_gccsa if level == "REGION" else None,
            dim_region16=dim_region16 if level == "REGION16" else None,
        )

        if df.is_empty():
            print(f"  -> No data for {level}")
            continue

        out_path = OUT_DIR / f"daily_rolling_{level.lower()}.parquet"
        df.write_parquet(out_path)
        print(f"  -> Saved {df.height:,} rows to {out_path}")

    print("Done.")


if __name__ == "__main__":
    main()
