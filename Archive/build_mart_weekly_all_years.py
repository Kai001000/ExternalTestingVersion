# build_mart_weekly_all_years.py
from pathlib import Path
import re
import numpy as np
import pandas as pd

BASE_DIR = Path(r"/")
FACT_DIR = BASE_DIR / "Processed" / "fact_sales"
OUT_DIR = BASE_DIR / "Processed" / "mart_weekly"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- NEW: Geo dim for Greater Sydney vs Rest of NSW (Route A) ----
DIM_DIR = BASE_DIR / "Processed" / "dim"
DIM_DIR.mkdir(parents=True, exist_ok=True)
DIM_GCCSA_PATH = DIM_DIR / "dim_postcode_gccsa.csv"  # postcode -> region_group

PRICE_MAX = 100_000_000
PRICE_MIN_EXCLUSIVE = 0

# ---- Add REGION level params ----
SIGNAL_PARAMS = {
    "NSW":      {"target_n": 80, "cap_days": 45},
    "REGION":   {"target_n": 60, "cap_days": 60},   # NEW
    "SUBURB":   {"target_n": 30, "cap_days": 90},
    "POSTCODE": {"target_n": 20, "cap_days": 120},
}

REQUIRED_FACT_COLS = {
    "sale_key",
    "dwelling_group",
    "purchase_price",
    "event_week_start",
    "contract_date",
    "suburb",
    "postcode",
}

REQUIRED_DIM_COLS = {"postcode", "region_group"}
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


def _load_dim_gccsa(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"[MISSING DIM] {path}\n"
            f"Please create it (Route A): postcode -> region_group.\n"
            f"Expected columns: {sorted(list(REQUIRED_DIM_COLS))}\n"
            f"Allowed region_group: {sorted(list(ALLOWED_REGION_GROUPS))}"
        )

    d = pd.read_csv(path, dtype=str)
    missing = REQUIRED_DIM_COLS - set(d.columns)
    if missing:
        raise ValueError(f"[BAD DIM SCHEMA] {path.name} missing columns: {sorted(missing)}")

    d = d.copy()
    d["postcode"] = _norm_postcode_series(d["postcode"])
    d["region_group"] = d["region_group"].astype(str).str.strip()

    # Keep only allowed values; others become NaN
    d.loc[~d["region_group"].isin(ALLOWED_REGION_GROUPS), "region_group"] = np.nan

    # De-dup postcode to 1 row (stable)
    d = d.dropna(subset=["postcode"]).drop_duplicates(subset=["postcode"], keep="first")

    return d


def _attach_region_group(df: pd.DataFrame, dim_gccsa: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["postcode"] = _norm_postcode_series(out["postcode"])
    out = out.merge(dim_gccsa, on="postcode", how="left")

    # If mapping missing, keep as "Unknown" (but still let pipeline run)
    out["region_group"] = out["region_group"].fillna("Unknown")
    return out


def _load_and_filter_fact(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)

    missing = REQUIRED_FACT_COLS - set(df.columns)
    if missing:
        raise ValueError(f"[BAD FACT SCHEMA] {path.name} missing columns: {sorted(missing)}")

    df = df.copy()
    df["postcode"] = _norm_postcode_series(df["postcode"])
    df["suburb"] = df["suburb"].astype(str).str.strip()

    df = _ensure_datetime(df, "event_week_start")
    df = _ensure_datetime(df, "contract_date")

    df = df[df["dwelling_group"].isin(["HOUSE", "UNIT"])].copy()
    df = df[df["purchase_price"].notna()].copy()
    df = df[(df["purchase_price"] > PRICE_MIN_EXCLUSIVE) & (df["purchase_price"] <= PRICE_MAX)].copy()
    df = df[df["event_week_start"].notna() & df["contract_date"].notna()].copy()

    # sale_key as stable tiebreaker
    df["sale_key"] = df["sale_key"].astype(str)

    return df


def _confidence_band(n_sales: int, span_days: int, target_n: int, cap_days: int) -> str:
    if n_sales >= target_n and span_days <= cap_days:
        return "High"
    if n_sales >= max(10, int(target_n * 0.6)) and span_days <= int(cap_days * 2):
        return "Medium"
    return "Low"


def _compute_weekly_signal(tx: pd.DataFrame, level: str, week_keys: pd.DataFrame) -> pd.DataFrame:
    """
    Stable signal selection with tie-break:
      - window_end = event_week_start (exclusive)
      - eligible: contract_date in [window_start, window_end)
      - order by (contract_date, sale_key) ASC
      - take the last target_n rows (i.e., most recent; within same date pick largest sale_key)
    """
    params = SIGNAL_PARAMS[level]
    target_n = int(params["target_n"])
    cap_days = int(params["cap_days"])

    tx = tx[["region", "dwelling_group", "contract_date", "purchase_price", "sale_key"]].copy()
    tx = tx.dropna(subset=["region", "dwelling_group", "contract_date", "purchase_price", "sale_key"]).copy()
    tx["contract_date"] = pd.to_datetime(tx["contract_date"], errors="coerce")
    tx = tx[tx["contract_date"].notna()].copy()
    tx["sale_key"] = tx["sale_key"].astype(str)

    week_keys = week_keys[["event_week_start", "region", "dwelling_group"]].drop_duplicates().copy()
    week_keys["event_week_start"] = pd.to_datetime(week_keys["event_week_start"], errors="coerce")
    week_keys = week_keys[week_keys["event_week_start"].notna()].copy()

    out_rows = []

    for (region, dg), g in tx.groupby(["region", "dwelling_group"], sort=False):
        weeks = (
            week_keys[(week_keys["region"] == region) & (week_keys["dwelling_group"] == dg)]
            .sort_values("event_week_start")["event_week_start"]
            .to_list()
        )
        if not weeks:
            continue

        # stable ordering: (contract_date, sale_key) ascending
        g = g.sort_values(["contract_date", "sale_key"], ascending=[True, True]).reset_index(drop=True)

        dates = g["contract_date"].to_numpy(dtype="datetime64[ns]")
        prices = g["purchase_price"].to_numpy(dtype=float)

        for ws in weeks:
            ws = pd.Timestamp(ws)

            window_end = np.datetime64(ws)  # exclusive
            window_start = np.datetime64(ws - pd.Timedelta(days=cap_days))

            lo = np.searchsorted(dates, window_start, side="left")
            hi = np.searchsorted(dates, window_end, side="left")  # exclude ws day

            eligible_n = hi - lo
            if eligible_n <= 0:
                out_rows.append({
                    "event_week_start": ws,
                    "region": region,
                    "dwelling_group": dg,
                    "signal_price": np.nan,
                    "signal_n_sales": 0,
                    "signal_span_days": np.nan,
                    "signal_confidence": "Low",
                })
                continue

            use_n = min(target_n, eligible_n)
            start_i = hi - use_n

            use_prices = prices[start_i:hi]
            use_dates = dates[start_i:hi]

            signal_price = float(np.median(use_prices))

            # inclusive span
            span_days = int((use_dates[-1] - use_dates[0]) / np.timedelta64(1, "D")) + 1

            conf = _confidence_band(use_n, span_days, target_n=target_n, cap_days=cap_days)

            out_rows.append({
                "event_week_start": ws,
                "region": region,
                "dwelling_group": dg,
                "signal_price": signal_price,
                "signal_n_sales": int(use_n),
                "signal_span_days": int(span_days),
                "signal_confidence": conf,
            })

    return pd.DataFrame(out_rows)


def _build_level(df: pd.DataFrame, level: str) -> pd.DataFrame:
    if level == "NSW":
        df2 = df.copy()
        df2["region"] = "NSW"


    elif level == "REGION":

        df2 = df.copy()

        if "region_group" not in df2.columns:
            raise ValueError("[REGION LEVEL] region_group missing. Did you join dim_postcode_gccsa.csv?")

        df2["region"] = df2["region_group"].astype(str).str.strip()

        allowed = ALLOWED_REGION_GROUPS | {"Unknown"}

        df2 = df2[df2["region"].isin(allowed)].copy()

        # You may choose to drop Unknown here; I keep it to avoid silent data loss
        # df2 = df2[df2["region"] != "Unknown"].copy()

    elif level == "SUBURB":
        df2 = df.copy()
        df2["region"] = df2["suburb"].astype(str).str.strip()
        df2 = df2[df2["region"] != ""].copy()

    elif level == "POSTCODE":
        df2 = df.copy()
        df2["region"] = _norm_postcode_series(df2["postcode"])
        df2 = df2[df2["region"] != ""].copy()

    else:
        raise ValueError("Invalid level")

    mart = (
        df2.groupby(["event_week_start", "region", "dwelling_group"], dropna=False)
           .agg(
               weekly_sales_count=("sale_key", "size"),
               weekly_median_price=("purchase_price", "median"),
               weekly_max_price=("purchase_price", "max"),
               weekly_min_price=("purchase_price", "min"),
           )
           .reset_index()
    )

    week_keys = mart[["event_week_start", "region", "dwelling_group"]].drop_duplicates()
    signal_df = _compute_weekly_signal(df2, level=level, week_keys=week_keys)

    mart = mart.merge(
        signal_df,
        on=["event_week_start", "region", "dwelling_group"],
        how="left",
        validate="1:1",
    )
    return mart


def main():
    fact_files = sorted(FACT_DIR.glob("fact_sales_*.parquet"))
    if not fact_files:
        raise FileNotFoundError(f"No fact_sales files found under: {FACT_DIR}")

    # Load dim once
    dim_gccsa = _load_dim_gccsa(DIM_GCCSA_PATH)

    dfs, years = [], []
    for f in fact_files:
        m = re.search(r"fact_sales_(\d{4})\.parquet", f.name)
        if m:
            years.append(int(m.group(1)))
        d = _load_and_filter_fact(f)
        d = _attach_region_group(d, dim_gccsa)
        dfs.append(d)

    df = pd.concat(dfs, ignore_index=True)
    label = f"{min(years)}_{max(years)}" if years else "all_years"
    print("REGION_GROUP counts:")
    print(df["region_group"].value_counts(dropna=False))

    print("Building WEEKLY mart for years:", sorted(years) if years else "(unknown)")
    print("Rows after filters:", f"{len(df):,}")
    print("event_week_start min/max:", df["event_week_start"].min(), df["event_week_start"].max())
    print("contract_date   min/max:", df["contract_date"].min(), df["contract_date"].max())
    print("purchase_price  min/max:", int(df["purchase_price"].min()), int(df["purchase_price"].max()))
    print("Signal params:", SIGNAL_PARAMS)
    print("Signal window rule: window_end = event_week_start (exclude current week)")
    print("Signal tie-break: order by (contract_date, sale_key)")
    print("Dim mapping:", DIM_GCCSA_PATH)

    _build_level(df, "NSW").to_parquet(OUT_DIR / f"mart_weekly_nsw_{label}.parquet", index=False)
    _build_level(df, "REGION").to_parquet(OUT_DIR / f"mart_weekly_region_{label}.parquet", index=False)   # NEW
    _build_level(df, "SUBURB").to_parquet(OUT_DIR / f"mart_weekly_suburb_{label}.parquet", index=False)
    _build_level(df, "POSTCODE").to_parquet(OUT_DIR / f"mart_weekly_postcode_{label}.parquet", index=False)

    print("Weekly mart built successfully.")
    print("Saved to:", OUT_DIR)


if __name__ == "__main__":
    main()