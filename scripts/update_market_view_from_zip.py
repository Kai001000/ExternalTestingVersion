import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile


BASE_DIR = Path(__file__).resolve().parents[1]
INBOX_DIR = BASE_DIR / "RawData" / "1 page update"
DAT_ROOT = BASE_DIR / "RawData" / "DAT"

REFRESH_MANIFEST_SCRIPT = BASE_DIR / "refresh_dat_manifest.py"
BUILD_FACT_SCRIPT = BASE_DIR / "build_fact_sales_year.py"
BUILD_DAILY_SCRIPT = BASE_DIR / "build_mart_daily_rolling.py"


def log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}")


def fail(message: str, *, exit_code: int = 1) -> None:
    log(f"ERROR: {message}")
    raise SystemExit(exit_code)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update Market View data from a manually downloaded NSW Valuer General zip."
    )
    parser.add_argument(
        "--zip-path",
        type=Path,
        default=None,
        help="Optional explicit path to the downloaded bulk PSI zip.",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Optional explicit target date in YYYYMMDD format.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow reuse of an existing destination folder by clearing and re-extracting it.",
    )
    return parser.parse_args()


def newest_zip(inbox_dir: Path) -> Path:
    if not inbox_dir.exists():
        fail(f"Inbox folder does not exist: {inbox_dir}")
    candidates = [path for path in inbox_dir.glob("*.zip") if path.is_file()]
    if not candidates:
        fail(f"No zip files found in inbox folder: {inbox_dir}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def infer_target_date(zip_path: Path, explicit_date: str | None) -> str:
    if explicit_date:
        if not re.fullmatch(r"\d{8}", explicit_date):
            fail(f"Invalid --date value: {explicit_date} (expected YYYYMMDD)")
        return explicit_date

    name = zip_path.stem
    ymd_match = re.search(r"(20\d{2})(\d{2})(\d{2})", name)
    if ymd_match:
        return ymd_match.group(0)

    dmy_match = re.search(r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)", name)
    if dmy_match:
        dd, mm, yyyy = dmy_match.groups()
        return f"{yyyy}{mm}{dd}"

    return datetime.now().strftime("%Y%m%d")


def destination_dir(target_date: str) -> Path:
    target_year = target_date[:4]
    return DAT_ROOT / target_year / target_date


def clear_directory(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def prepare_destination(dest_dir: Path, force: bool) -> None:
    if dest_dir.exists():
        existing = list(dest_dir.iterdir())
        if existing and not force:
            fail(
                f"Destination already exists and is not empty: {dest_dir}. "
                f"Use --force to clear and reuse it."
            )
        if existing and force:
            log(f"Clearing existing destination: {dest_dir}")
            clear_directory(dest_dir)
    else:
        dest_dir.mkdir(parents=True, exist_ok=True)


def extract_zip(zip_path: Path, dest_dir: Path) -> list[Path]:
    extracted: list[Path] = []
    with ZipFile(zip_path, "r") as archive:
        members = archive.namelist()
        if not members:
            fail(f"Zip file is empty: {zip_path}")
        archive.extractall(dest_dir)
    for path in dest_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() == ".dat":
            extracted.append(path)
    return sorted(extracted)


def run_command(command: list[str], *, step_name: str) -> None:
    printable = subprocess.list2cmdline(command)
    log(f"Running {step_name}: {printable}")
    completed = subprocess.run(command, cwd=BASE_DIR)
    if completed.returncode != 0:
        fail(f"{step_name} failed with exit code {completed.returncode}")
    log(f"Completed {step_name}")


def main() -> None:
    args = parse_args()
    zip_path = args.zip_path if args.zip_path else newest_zip(INBOX_DIR)
    zip_path = zip_path.expanduser().resolve()
    if not zip_path.exists():
        fail(f"Zip file not found: {zip_path}")
    if zip_path.suffix.lower() != ".zip":
        fail(f"Provided file is not a zip: {zip_path}")

    target_date = infer_target_date(zip_path, args.date)
    dest_dir = destination_dir(target_date)
    target_year = int(target_date[:4])

    log(f"Selected zip: {zip_path}")
    log(f"Target date: {target_date}")
    log(f"Destination: {dest_dir}")

    prepare_destination(dest_dir, args.force)

    extracted_dat_files = extract_zip(zip_path, dest_dir)
    if not extracted_dat_files:
        fail(f"No .DAT files were extracted from {zip_path} into {dest_dir}")

    log(f"Extracted {len(extracted_dat_files)} DAT files")
    preview = ", ".join(path.name for path in extracted_dat_files[:5])
    if preview:
        log(f"Sample DAT files: {preview}")

    python_exe = sys.executable
    run_command(
        [python_exe, str(REFRESH_MANIFEST_SCRIPT), "--min_year", str(target_year), "--max_year", str(target_year)],
        step_name="refresh_dat_manifest",
    )

    fact_cmd = [
        python_exe,
        str(BUILD_FACT_SCRIPT),
        "--min_year",
        str(target_year),
        "--max_year",
        str(target_year),
        "--rebuild_if_inputs_newer",
    ]
    if args.force:
        fact_cmd.append("--overwrite")
    run_command(fact_cmd, step_name="build_fact_sales_year")

    run_command([python_exe, str(BUILD_DAILY_SCRIPT)], step_name="build_mart_daily_rolling")

    log("Market View update completed successfully")
    log(f"Zip: {zip_path}")
    log(f"DAT destination: {dest_dir}")
    log(f"Target year rebuilt: {target_year}")
    log("Pipeline steps completed: refresh_dat_manifest -> build_fact_sales_year -> build_mart_daily_rolling")


if __name__ == "__main__":
    main()
