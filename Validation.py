from pathlib import Path
import pandas as pd

BASE_DIR = Path(r"C:\Users\jonat\PycharmProjects\NSWpropertyData")
FACT_PATH = BASE_DIR / "Processed" / "fact_sales" / "fact_sales_2026.parquet"

def main():
    df = pd.read_parquet(FACT_PATH).copy()

    # 1) 日期范围 & NaT
    df["contract_date"] = pd.to_datetime(df["contract_date"], errors="coerce")
    print("\n=== DATE RANGE ===")
    print("min:", df["contract_date"].min())
    print("max:", df["contract_date"].max())
    print("NaT rows:", df["contract_date"].isna().sum())

    # 2) 按周统计（看是不是只到某几周/某个断点）
    df["week"] = df["contract_date"].dt.to_period("W").astype(str)
    wk = df.groupby(["week", "dwelling_group"]).size().reset_index(name="n").sort_values("week")
    print("\n=== WEEKLY COUNTS (tail 20 weeks) ===")
    print(wk.tail(40).to_string(index=False))

    # 3) 如果你 fact 里有 source_file / ingest_batch / event_week_start 之类字段，查它
    candidates = [c for c in ["source_file", "source_path", "ingest_batch", "event_week_start"] if c in df.columns]
    print("\n=== EXTRA FIELDS FOUND ===", candidates)

    for c in candidates:
        print(f"\n--- {c} TOP 20 ---")
        print(df[c].value_counts().head(20).to_string())

if __name__ == "__main__":
    main()