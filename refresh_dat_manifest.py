# refresh_dat_manifest.py
import argparse
import hashlib
import re
from datetime import datetime
from pathlib import Path
import pandas as pd

# =====================
# Config
# =====================
BASE_DIR = Path(r"C:\Users\jonat\PycharmProjects\NSWpropertyData")
DAT_ROOT = BASE_DIR / "RawData" / "DAT"
MANIFEST_DIR = BASE_DIR / "RawData" / "manifest"
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH = MANIFEST_DIR / "dat_manifest.csv"

# =====================
# Helpers
# =====================
def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def parse_week_start_from_filename(fname: str):
    # e.g. 708_SALES_DATA_NNME_29122025.DAT -> 29/12/2025
    m = re.search(r"_(\d{8})\.DAT$", fname, re.IGNORECASE)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%d%m%Y").date()

def infer_year_from_path(p: Path) -> int | None:
    # expect ...\RawData\DAT\2025\...\xxx.DAT
    parts = [x for x in p.parts]
    try:
        i = [s.upper() for s in parts].index("DAT")
        y = parts[i + 1]
        if re.fullmatch(r"\d{4}", y):
            return int(y)
    except Exception:
        pass

    m = re.search(r"(19\d{2}|20\d{2})", str(p))
    if m:
        return int(m.group(1))
    return None

def list_dat_files_from_years(dat_root: Path, min_year: int, max_year: int | None = None) -> list[Path]:
    """
    Only scan folders: DAT/<year>/... where min_year <= year <= max_year (if provided)
    """
    if not dat_root.exists():
        raise FileNotFoundError(f"DAT root not found: {dat_root}")

    year_dirs = []
    for child in dat_root.iterdir():
        if child.is_dir() and re.fullmatch(r"\d{4}", child.name):
            y = int(child.name)
            if y < min_year:
                continue
            if max_year is not None and y > max_year:
                continue
            year_dirs.append(child)

    year_dirs = sorted(year_dirs, key=lambda p: int(p.name))

    dat_files: list[Path] = []
    for yd in year_dirs:
        # support both .DAT and .dat
        dat_files.extend(sorted(yd.rglob("*.DAT")))
        dat_files.extend(sorted(yd.rglob("*.dat")))

    # de-dup
    dat_files = sorted(list(set(dat_files)))
    return dat_files

def load_existing_manifest_cache(manifest_path: Path) -> dict[str, dict]:
    """
    Return dict keyed by out_path:
      { out_path: {"bytes": int, "sha256": str, "year":..., "week_start":..., "dat_member":... } }
    Only uses existing columns; schema unchanged.
    """
    if not manifest_path.exists():
        return {}

    try:
        old = pd.read_csv(manifest_path, dtype={"out_path": str})
        # tolerate missing columns
        for c in ["out_path", "bytes", "sha256"]:
            if c not in old.columns:
                return {}
        old = old.dropna(subset=["out_path"]).copy()
        cache = {}
        for _, r in old.iterrows():
            op = str(r["out_path"])
            cache[op] = {
                "bytes": int(r["bytes"]) if pd.notna(r["bytes"]) else None,
                "sha256": str(r["sha256"]) if pd.notna(r["sha256"]) else None,
            }
        return cache
    except Exception:
        # if old manifest corrupted, just rebuild
        return {}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min_year", type=int, default=2015, help="Only scan DAT/<year>/ where year >= min_year")
    parser.add_argument("--max_year", type=int, default=None, help="Optional: only scan DAT/<year>/ where year <= max_year")
    parser.add_argument("--force_rehash", action="store_true", help="Force recompute sha256 for all files (slow)")
    args = parser.parse_args()

    min_year = args.min_year
    max_year = args.max_year

    dat_files = list_dat_files_from_years(DAT_ROOT, min_year=min_year, max_year=max_year)
    if not dat_files:
        print(f"No .DAT files found under {DAT_ROOT} for year range [{min_year}, {max_year or '∞'}]")
        return

    # incremental cache
    cache = load_existing_manifest_cache(MANIFEST_PATH)
    reuse_hits = 0
    rehash_hits = 0

    rows = []
    total = len(dat_files)
    print(f"Scanning files: {total} | years=[{min_year}, {max_year or '∞'}] | incremental={'OFF' if args.force_rehash else 'ON'}")

    for i, p in enumerate(dat_files, start=1):
        if i % 500 == 0:
            print(f"Scanning {i}/{total} ... (reuse={reuse_hits}, rehash={rehash_hits})")

        y = infer_year_from_path(p)
        ws = parse_week_start_from_filename(p.name)
        size = p.stat().st_size
        out_path = str(p)

        old = cache.get(out_path)

        if (not args.force_rehash) and old and (old.get("bytes") == size) and old.get("sha256"):
            # size unchanged -> reuse hash (fast path)
            s256 = old["sha256"]
            reuse_hits += 1
        else:
            s256 = sha256_file(p)
            rehash_hits += 1

        rows.append({
            "year": y,
            "week_start": ws,
            "dat_member": p.name,
            "out_path": out_path,
            "bytes": size,
            "sha256": s256,
        })

    df = pd.DataFrame(rows)

    # QA: report issues loudly
    missing_year = int(df["year"].isna().sum())
    missing_week = int(df["week_start"].isna().sum())
    if missing_year > 0:
        print(f"[WARN] year missing rows: {missing_year}")
        print(df[df["year"].isna()][["out_path"]].head(20).to_string(index=False))
    if missing_week > 0:
        print(f"[WARN] week_start missing rows: {missing_week}")
        print(df[df["week_start"].isna()][["dat_member", "out_path"]].head(20).to_string(index=False))

    df.sort_values(["year", "week_start", "dat_member", "out_path"], inplace=True)
    df.to_csv(MANIFEST_PATH, index=False, encoding="utf-8")

    year_min = df["year"].dropna().min() if "year" in df.columns else None
    year_max = df["year"].dropna().max() if "year" in df.columns else None

    print(f"Saved manifest: {MANIFEST_PATH} | rows={len(df)} | years={year_min}..{year_max}")
    print(f"Incremental stats: reuse={reuse_hits} | rehash={rehash_hits} | force_rehash={args.force_rehash}")

if __name__ == "__main__":
    main()