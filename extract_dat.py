import os
import re
import csv
import hashlib
from pathlib import Path
from zipfile import ZipFile

BASE = Path(r"C:\Users\jonat\PycharmProjects\NSWpropertyData")
ZIP_DIR = BASE / "RawData" / "Zip"
DAT_DIR = BASE / "RawData" / "DAT"
MANIFEST_DIR = BASE / "RawData" / "manifest"
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
DAT_DIR.mkdir(parents=True, exist_ok=True)

def sha256_file(path: Path, chunk_size=1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def safe_name(name: str) -> str:
    # avoid weird chars
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)

def extract_all_dat():
    manifest_path = MANIFEST_DIR / "dat_manifest.csv"
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "year_zip", "inner_zip", "dat_member",
            "out_path", "bytes", "sha256"
        ])

        year_zips = sorted(ZIP_DIR.glob("*.zip"))
        if not year_zips:
            raise FileNotFoundError(f"No zip files found in {ZIP_DIR}")

        for year_zip in year_zips:
            year_match = re.search(r"(19|20)\d{2}", year_zip.name)
            year = year_match.group(0) if year_match else "unknown_year"
            out_year_dir = DAT_DIR / year
            out_year_dir.mkdir(parents=True, exist_ok=True)

            print(f"[YEAR] {year_zip.name}")

            with ZipFile(year_zip, "r") as z_year:
                members = z_year.namelist()

                # 1) find inner zips (weekly) and direct .DATs (some years may have direct DAT)
                inner_zips = [m for m in members if m.lower().endswith(".zip")]
                direct_dats = [m for m in members if m.lower().endswith(".dat")]

                # extract direct DATs
                for dat_member in direct_dats:
                    out_path = out_year_dir / safe_name(Path(dat_member).name)
                    if not out_path.exists():
                        out_path.write_bytes(z_year.read(dat_member))
                    w.writerow([year_zip.name, "", dat_member, str(out_path), out_path.stat().st_size, sha256_file(out_path)])

                # extract DATs from inner zips
                for inner in inner_zips:
                    inner_name = safe_name(Path(inner).name)
                    out_inner_dir = out_year_dir / inner_name.replace(".zip", "")
                    out_inner_dir.mkdir(parents=True, exist_ok=True)

                    # read inner zip bytes (zip-in-zip)
                    inner_bytes = z_year.read(inner)
                    # open as ZipFile from bytes
                    import io
                    with ZipFile(io.BytesIO(inner_bytes), "r") as z_inner:
                        for m in z_inner.namelist():
                            if m.lower().endswith(".dat"):
                                out_path = out_inner_dir / safe_name(Path(m).name)
                                if not out_path.exists():
                                    out_path.write_bytes(z_inner.read(m))
                                w.writerow([year_zip.name, inner, m, str(out_path), out_path.stat().st_size, sha256_file(out_path)])

    print(f"Done. Manifest saved to: {manifest_path}")

if __name__ == "__main__":
    extract_all_dat()