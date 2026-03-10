# build_fact_sales_year.py
import argparse
import re
from pathlib import Path
from datetime import datetime, timedelta, date
import pandas as pd

BASE_DIR = Path(r"C:\Users\jonat\PycharmProjects\NSWpropertyData")
MANIFEST_PATH = BASE_DIR / "RawData" / "manifest" / "dat_manifest.csv"

OUT_DIR = BASE_DIR / "Processed" / "fact_sales"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- STRICT: Only accept reasonable contract dates ----
MIN_REASONABLE_DATE = date(2010, 1, 1)
MAX_REASONABLE_DATE = date(2030, 12, 31)


def safe_int(x):
    x = ("" if x is None else str(x)).strip()
    if x == "":
        return None
    try:
        return int(float(x))
    except:
        return None


def is_reasonable(d: date | None) -> bool:
    if d is None:
        return False
    return MIN_REASONABLE_DATE <= d <= MAX_REASONABLE_DATE


def safe_contract_date(x):
    """
    Try parse:
    1) YYYYMMDD
    2) Encoded 02YYMMDD / 10YYMMDD → 20YYMMDD
    """
    s = ("" if x is None else str(x)).strip()
    if not s:
        return None

    # Normal
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except:
        pass

    # Encoded
    if len(s) == 8 and s[:2] in ("02", "10") and s[2:].isdigit():
        candidate = "20" + s[2:]
        try:
            return datetime.strptime(candidate, "%Y%m%d").date()
        except:
            return None

    return None


def safe_dt_yyyymmdd_hhmm(x):
    x = ("" if x is None else str(x)).strip()
    if not x:
        return None
    try:
        return datetime.strptime(x, "%Y%m%d %H:%M")
    except:
        return None


def parse_week_start_from_filename(fname: str):
    m = re.search(r"_(\d{8})\.DAT$", fname, re.IGNORECASE)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%d%m%Y").date()


def classify_dwelling_group(nature, unit_no, legal_desc):
    nature = (nature or "").strip().upper()
    if nature != "R":
        return None

    if (unit_no or "").strip():
        return "UNIT"

    if legal_desc and re.search(r"/SP\d+|SP\d+", legal_desc, re.IGNORECASE):
        return "UNIT"

    return "HOUSE"


def make_sale_key(district, prop_id, sale_counter, dealing_no):
    return "|".join([
        (district or "").strip(),
        (prop_id or "").strip(),
        (sale_counter or "").strip(),
        (dealing_no or "").strip()
    ])


def week_start_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def parse_dat_file(path: Path):
    rows = []
    current_b = None
    current_c_parts = []
    file_week_start = parse_week_start_from_filename(path.name)

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue

            parts = line.split(";")
            rtype = parts[0].strip().upper()

            if rtype == "B":

                # flush previous record
                if current_b is not None:
                    legal_desc = "".join(current_c_parts).strip() or None
                    current_b["legal_desc"] = legal_desc

                    dg = classify_dwelling_group(
                        current_b.get("nature_of_property"),
                        current_b.get("unit_number"),
                        legal_desc,
                    )
                    current_b["dwelling_group"] = dg

                    if dg == "HOUSE" or dg == "UNIT":
                        current_b["sale_key"] = make_sale_key(
                            current_b.get("district_code"),
                            current_b.get("property_id"),
                            current_b.get("sale_counter"),
                            current_b.get("dealing_number"),
                        )
                        rows.append(current_b)

                current_c_parts = []

                # ---- STRICT: ONLY contract_date ----
                contract_d = safe_contract_date(parts[13] if len(parts) > 13 else None)

                if not is_reasonable(contract_d):
                    # Drop this record entirely
                    current_b = None
                    continue

                event_d = contract_d
                event_ws = week_start_monday(event_d)

                current_b = {
                    "source_file": path.name,
                    "file_week_start": file_week_start,

                    "district_code": parts[1].strip() if len(parts) > 1 else None,
                    "property_id": parts[2].strip() if len(parts) > 2 else None,
                    "sale_counter": parts[3].strip() if len(parts) > 3 else None,
                    "registered_at": safe_dt_yyyymmdd_hhmm(parts[4] if len(parts) > 4 else None),

                    "unit_number": parts[5].strip() if len(parts) > 5 else None,
                    "house_number": parts[6].strip() if len(parts) > 6 else None,
                    "street_number_suffix": parts[7].strip() if len(parts) > 7 else None,
                    "street_name": parts[8].strip() if len(parts) > 8 else None,
                    "suburb": parts[9].strip() if len(parts) > 9 else None,
                    "postcode": parts[10].strip() if len(parts) > 10 else None,

                    "contract_date": contract_d,
                    "event_date": event_d,
                    "event_week_start": event_ws,
                    "event_basis": "contract",

                    "purchase_price": safe_int(parts[15] if len(parts) > 15 else None),

                    "nature_of_property": parts[17].strip() if len(parts) > 17 else None,
                    "property_description": parts[18].strip() if len(parts) > 18 else None,

                    "dealing_number": parts[23].strip() if len(parts) > 23 else None,
                }

            elif rtype == "C":
                if current_b is not None and len(parts) > 5 and parts[5].strip():
                    current_c_parts.append(parts[5].strip())

    # flush last
    if current_b is not None:
        legal_desc = "".join(current_c_parts).strip() or None
        current_b["legal_desc"] = legal_desc

        dg = classify_dwelling_group(
            current_b.get("nature_of_property"),
            current_b.get("unit_number"),
            legal_desc,
        )
        current_b["dwelling_group"] = dg

        if dg == "HOUSE" or dg == "UNIT":
            current_b["sale_key"] = make_sale_key(
                current_b.get("district_code"),
                current_b.get("property_id"),
                current_b.get("sale_counter"),
                current_b.get("dealing_number"),
            )
            rows.append(current_b)

    return rows


def try_write_parquet(df: pd.DataFrame, path: Path) -> bool:
    try:
        df.to_parquet(path, index=False)
        return True
    except Exception as e:
        print("Parquet write failed:", repr(e))
        return False


def _max_input_mtime(paths: list[Path]) -> float | None:
    mtimes = []
    for p in paths:
        try:
            if p.exists():
                mtimes.append(p.stat().st_mtime)
        except:
            pass
    return max(mtimes) if mtimes else None


def should_rebuild_year(out_parquet: Path, input_paths: list[Path]) -> bool:
    """
    Rebuild if:
      - output doesn't exist
      - any input DAT is newer than output parquet
    """
    if not out_parquet.exists():
        return True

    try:
        out_mtime = out_parquet.stat().st_mtime
    except:
        # if can't stat output, safer to rebuild
        return True

    max_in = _max_input_mtime(input_paths)
    if max_in is None:
        # no inputs -> don't rebuild
        return False

    return max_in > out_mtime


def build_one_year(mf: pd.DataFrame, year: int, overwrite: bool, rebuild_if_inputs_newer: bool):
    out_parquet = OUT_DIR / f"fact_sales_{year}.parquet"

    mf_year = mf[mf["year"] == year].copy()
    if mf_year.empty:
        print(f"[SKIP] No rows in manifest for year={year}")
        return

    paths = [Path(p) for p in mf_year["out_path"].tolist()]

    if out_parquet.exists() and not overwrite:
        if rebuild_if_inputs_newer and should_rebuild_year(out_parquet, paths):
            print(f"[REBUILD] Inputs newer than output for year={year}: {out_parquet.name}")
        else:
            print(f"[SKIP] Exists: {out_parquet} (use --overwrite to rebuild)")
            return

    all_rows = []
    for i, p in enumerate(paths, start=1):
        if i % 200 == 0:
            print(f"Year {year}: Parsed {i}/{len(paths)} files...")
        all_rows.extend(parse_dat_file(p))

    df = pd.DataFrame(all_rows)

    if "sale_key" in df.columns:
        df = df.drop_duplicates(subset=["sale_key"])

    df = df[df["purchase_price"].notna() & (df["purchase_price"] > 0)]
    df = df[df["dwelling_group"].isin(["HOUSE", "UNIT"])]

    print(f"\nfact_sales_{year} rows:", len(df))
    print("event_week_start min/max:", df["event_week_start"].min(), df["event_week_start"].max())
    print("purchase_price min/max:", df["purchase_price"].min(), df["purchase_price"].max())

    if try_write_parquet(df, out_parquet):
        print("Saved:", out_parquet)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min_year", type=int, default=2015)
    parser.add_argument("--max_year", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true", help="Rebuild existing fact_sales_YYYY.parquet")
    parser.add_argument(
        "--rebuild_if_inputs_newer",
        action="store_true",
        help="If output exists, rebuild year when any input DAT is newer than the parquet (default behavior).",
    )
    parser.add_argument(
        "--no_rebuild_if_inputs_newer",
        action="store_true",
        help="Disable input-newer detection; keep original skip behavior unless --overwrite.",
    )
    args = parser.parse_args()

    if not MANIFEST_PATH.exists():
        raise FileNotFoundError("Run refresh_dat_manifest.py first.")

    mf = pd.read_csv(MANIFEST_PATH)
    mf = mf[mf["year"].notna()].copy()
    mf["year"] = mf["year"].astype(int)

    years = sorted(mf["year"].unique().tolist())
    years = [y for y in years if y >= args.min_year]
    if args.max_year is not None:
        years = [y for y in years if y <= args.max_year]

    if not years:
        print(f"[SKIP] No years found in manifest for range [{args.min_year}, {args.max_year or '∞'}]")
        return

    # default: rebuild_if_inputs_newer = True unless explicitly disabled
    rebuild_if_inputs_newer = True
    if args.no_rebuild_if_inputs_newer:
        rebuild_if_inputs_newer = False
    if args.rebuild_if_inputs_newer:
        rebuild_if_inputs_newer = True

    print(f"Years to build: {years[0]}..{years[-1]} (n={len(years)}) | overwrite={args.overwrite} | rebuild_if_inputs_newer={rebuild_if_inputs_newer}")

    for y in years:
        build_one_year(mf, y, overwrite=args.overwrite, rebuild_if_inputs_newer=rebuild_if_inputs_newer)


if __name__ == "__main__":
    main()