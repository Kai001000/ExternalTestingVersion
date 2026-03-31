import os
from pathlib import Path

# ====== project paths ======
BASE_DIR = Path(__file__).resolve().parent.parent

MART_WEEKLY_DIR = BASE_DIR / "Processed" / "mart_weekly"          # 仍保留（排名表可能还需要）
MART_MONTHLY_DIR = BASE_DIR / "Processed" / "mart_monthly"        # 仍保留（备用）
MART_DAILY_ROLLING_DIR = BASE_DIR / "Processed" / "mart_daily_rolling"   # 新增

# ====== guards ======
PRICE_MAX = 100_000_000
PRICE_MIN_EXCLUSIVE = 0

# ====== app mode ======
APP_MODE = os.getenv("APP_MODE", "internal").strip().lower() or "internal"
if APP_MODE not in {"internal", "external"}:
    APP_MODE = "internal"
IS_EXTERNAL_MODE = APP_MODE == "external"

# rolling windows (in weeks) – 可能不再使用，但保留
ROLL_WINDOWS = {
    "roll4": 4,
    "roll13": 13,
    "roll26": 26,
}

# ====== ranking config ======
TOP_N_RANK = 5

# sales thresholds to reduce noise
MIN_SALES_STABLE_MOM = 10
MIN_SALES_STABLE_QOQ = 30

# ====== app current listing dataset ======
CURRENT_LISTINGS_DIR = BASE_DIR / "data" / "current"
CURRENT_SALE_LISTINGS_PARQUET = CURRENT_LISTINGS_DIR / "nsw_sale_listings_current.parquet"
CURRENT_RENT_LISTINGS_PARQUET = CURRENT_LISTINGS_DIR / "nsw_rent_listings_current.parquet"
CURRENT_RENT_CLASSIFICATION_JSONL = CURRENT_LISTINGS_DIR / "nsw_rent_full_deduped.jsonl"

# ====== external listing dataset (legacy / fallback) ======
DOMAIN_SALE_LISTINGS_ENV_VAR = "DOMAIN_SALE_LISTINGS_PARQUET"
LEGACY_DOMAIN_SALE_LISTINGS_PARQUET = (
    Path(os.getenv(DOMAIN_SALE_LISTINGS_ENV_VAR, "")).expanduser()
    if os.getenv(DOMAIN_SALE_LISTINGS_ENV_VAR, "").strip()
    else (
        BASE_DIR.parent
        / "DomainListing"
        / "data"
        / "production_adaptive_nsw_v3_final"
        / "nsw_sale_listings_final.parquet"
    )
)

DOMAIN_RENT_LISTINGS_ENV_VAR = "DOMAIN_RENT_LISTINGS_PARQUET"
LEGACY_DOMAIN_RENT_LISTINGS_PARQUET = (
    Path(os.getenv(DOMAIN_RENT_LISTINGS_ENV_VAR, "")).expanduser()
    if os.getenv(DOMAIN_RENT_LISTINGS_ENV_VAR, "").strip()
    else (
        BASE_DIR.parent
        / "DomainListing"
        / "data"
        / "production_adaptive_nsw_rent_v1_final"
        / "nsw_rent_listings_final.parquet"
    )
)

STANDARD_RESIDENTIAL_LISTING_CLASSIFICATION = "standard_residential"

DEFAULT_DOMAIN_SALE_LISTINGS_PARQUET = CURRENT_SALE_LISTINGS_PARQUET
DEFAULT_DOMAIN_RENT_LISTINGS_PARQUET = CURRENT_RENT_LISTINGS_PARQUET

# Backward compatibility for existing sale imports.
DOMAIN_LISTINGS_ENV_VAR = DOMAIN_SALE_LISTINGS_ENV_VAR
DEFAULT_DOMAIN_LISTINGS_PARQUET = DEFAULT_DOMAIN_SALE_LISTINGS_PARQUET
